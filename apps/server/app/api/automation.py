from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import winreg
from contextlib import contextmanager
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.llm.generator import generate_structured
from app.services.software_index import find_software, get_software_index
from app.services.task_filter import filter_tasks as advanced_filter_tasks, validate_batch_execution

router = APIRouter(prefix="/automation", tags=["automation"])

# PostgreSQL 配置（可选）
_PG_ENABLED = os.getenv("PG_ENABLED", "false").lower() == "true"
_PG_DSN = os.getenv("PG_DSN", "")

# 回退到内存缓存（单进程模式）
_alert_dedup_cache: dict[str, float] = {}
_ALERT_DEDUP_WINDOW_SECONDS = 30.0

# ===== 任务过滤器常量 =====
PROTECTED_PROCESSES = frozenset([
    "explorer.exe", "csrss.exe", "smss.exe", "services.exe",
    "lsass.exe", "winlogon.exe", "svchost.exe", "System",
    "Registry", "Memory Compression", "dwm.exe", "wininit.exe",
])

MAX_TASKS_PER_BATCH = 8


def _check_process_exists(name: str) -> bool:
    """检查 Windows 进程是否存在（跨平台兼容）"""
    try:
        # Windows: 用 tasklist
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
        return name.lower() in result.stdout.lower()
    except Exception:
        # 非 Windows 环境或其他错误，跳过检查
        return True  # 放行


def _check_pid_exists(pid: int) -> bool:
    """检查 PID 是否存在"""
    if not pid or pid <= 0:
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
        return str(pid) in result.stdout
    except Exception:
        return True  # 放行


# ===== 失败记忆与路径查找 =====
_recent_failures: dict[str, dict] = {}

def record_task_failure(tool: str, params: dict, reason: str):
    """记录任务失败，防止 5 分钟内重复生成相同无效任务"""
    sig = f"{tool}:{json.dumps(params, sort_keys=True)}"
    _recent_failures[sig] = {"time": time.time(), "reason": reason}

def was_recent_failure(task: dict, window_seconds: int = 300) -> bool:
    """检查该任务是否在最近 N 秒内失败过"""
    sig = f"{task.get('tool', '')}:{json.dumps(task.get('params', {}), sort_keys=True)}"
    if sig in _recent_failures:
        if time.time() - _recent_failures[sig]["time"] < window_seconds:
            return True
    return False

def find_app_path(name: str) -> str | None:
    """自动查找 Windows 应用绝对路径（注册表 + 常见目录）"""
    exe_name = name if name.endswith('.exe') else f"{name}.exe"
    
    # 1. 注册表 App Paths
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                          r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths") as key:
            try:
                with winreg.OpenKey(key, exe_name) as app_key:
                    path, _ = winreg.QueryValueEx(app_key, None)
                    if path and os.path.exists(path):
                        return path
            except FileNotFoundError:
                pass
    except Exception:
        pass
    
    # 2. 常见安装目录搜索（限制深度 3，避免遍历整个磁盘）
    search_roots = [
        os.environ.get('ProgramFiles', 'C:\\Program Files'),
        os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'),
        os.path.expandvars(r"%LocalAppData%\Programs"),
    ]
    for root in search_roots:
        if not os.path.exists(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            depth = dirpath.count(os.sep) - root.count(os.sep)
            if depth > 3:
                del dirnames[:]
                continue
            if exe_name in filenames:
                full = os.path.join(dirpath, exe_name)
                if os.path.exists(full):
                    return full
    return None


def filter_invalid_commands(commands: list[dict]) -> list[dict]:
    """
    后端任务过滤器 - 对 LLM/规则生成的任务进行预验证
    1. 去除重复
    2. 过滤近期失败过的任务（5分钟窗口）
    3. 过滤非法 process:kill (受保护进程/不存在进程)
    4. app:launch 自动查找绝对路径，找不到则过滤
    5. 截断过多任务
    """
    if not commands:
        return []
    
    seen = set()
    filtered = []
    
    for cmd in commands:
        tool = cmd.get("tool", "")
        params = cmd.get("params", {}) or {}
        
        # 1. 近期失败过滤（5分钟窗口）
        if was_recent_failure(cmd):
            print(f"[TaskFilter] 近期失败过滤: {tool} {params}")
            continue
        
        # 2. process:kill 验证
        if tool == "process:kill":
            pid = params.get("pid")
            name = params.get("name", "")
            
            # 必须有 pid 或 name
            if not pid and not name:
                continue  # 跳过：缺少目标
            
            # 检查保护进程
            if name and name.lower() in [p.lower() for p in PROTECTED_PROCESSES]:
                continue  # 跳过：受保护进程
            
            # 检查进程是否存在
            if name and not _check_process_exists(name):
                record_task_failure(tool, params, "进程未运行")
                continue  # 跳过：进程不存在
            
            if pid and not _check_pid_exists(pid):
                continue  # 跳过：PID 不存在
            
            # 强制要求确认
            cmd["require_confirmation"] = True
            cmd["risk"] = cmd.get("risk") or "high"
        
        # 3. app:launch 路径解析（核心修复）
        elif tool == "app:launch":
            path = params.get("path", "")
            url = params.get("url", "")
            if not path:
                continue  # 跳过：缺少路径
            
            # 短名/别名 → 尝试通过软件索引解析
            if not os.path.isabs(path):
                found = find_app_path(path)
                if found:
                    cmd["params"]["path"] = found
                    print(f"[TaskFilter] 路径解析: {path} -> {found}")
                else:
                    # 软件索引也没找到，保留短名让 Electron 端动态解析
                    # （Electron preValidateCommand 会调用 where/Get-Command/注册表/API）
                    print(f"[TaskFilter] 短名未解析: {path}，交给 Electron 动态解析")
            
            # 绝对路径但不存在 -> 尝试按文件名重新查找
            elif not os.path.exists(path):
                found = find_app_path(os.path.basename(path))
                if found:
                    cmd["params"]["path"] = found
                else:
                    record_task_failure(tool, params, "路径不存在")
                    continue  # 跳过：不生成无效任务
        
        # 3b. content:generate 验证
        elif tool == "content:generate":
            task = params.get("task", "") or params.get("theme", "")
            if not task:
                continue
            if "auto_open" not in params:
                params["auto_open"] = True
        
        # 3b2. store 工具验证
        elif tool == "store:uninstall":
            package_id = params.get("package_id", "")
            if not package_id:
                continue
            cmd["require_confirmation"] = True
            cmd["risk"] = cmd.get("risk") or "high"
        elif tool == "store:install":
            package_id = params.get("package_id", "")
            if not package_id:
                continue
            cmd["require_confirmation"] = True
            cmd["risk"] = cmd.get("risk") or "medium"
        elif tool == "store:search":
            query = params.get("query", "")
            if not query:
                continue
        elif tool == "store:list":
            pass
        
        # 3c. 过滤掉不存在的工具（LLM幻觉）
        elif tool not in {
            "system:info", "process:top", "process:list", "process:kill",
            "disk:list", "disk:cleanup", "disk:cleanup_advanced",
            "temp:scan", "temp:cleanup", "system:recycle", "system:browser-cache",
            "system:cleanmgr", "system:hibernate", "system:wechat-cache",
            "app:launch", "app:find-path", "content:generate",
            "browser:search", "ide:launch", "keyboard:type",
            "clipboard:write", "notify", "network:request",
            "file:list", "file:read", "file:write", "file:delete", "file:search",
            "system:command", "system:env",
            "store:search", "store:install", "store:uninstall", "store:list",
        }:
            print(f"[TaskFilter] 过滤掉不存在的工具: {tool}")
            record_task_failure(tool, params, "工具不存在")
            continue
        
        # 4. 去重（基于 tool + 关键参数）
        key = f"{tool}:{params.get('pid', '')}:{params.get('name', '')}:{params.get('path', '')}"
        key_hash = hashlib.md5(key.encode()).hexdigest()[:16]
        if key_hash in seen:
            continue  # 跳过：重复任务
        seen.add(key_hash)
        
        filtered.append(cmd)
    
    # 5. 截断过多任务
    if len(filtered) > MAX_TASKS_PER_BATCH:
        filtered = filtered[:MAX_TASKS_PER_BATCH]
    
    return filtered


def _get_pg_connection():
    """获取 PostgreSQL 连接"""
    if not _PG_ENABLED or not _PG_DSN:
        return None
    try:
        import psycopg2
        return psycopg2.connect(_PG_DSN)
    except Exception:
        return None


def _init_pg_tables(conn):
    """初始化 PostgreSQL 告警去重表"""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS alert_dedup (
                id SERIAL PRIMARY KEY,
                alert_key VARCHAR(255) NOT NULL,
                last_seen_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(alert_key)
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_alert_dedup_key ON alert_dedup(alert_key)
        """)
        conn.commit()


@contextmanager
def _pg_connection():
    """PostgreSQL 连接上下文管理器"""
    conn = _get_pg_connection()
    if conn:
        try:
            _init_pg_tables(conn)
            yield conn
        finally:
            conn.close()
    else:
        yield None


def _is_alert_duplicate_pg(alert_type: str, alert_title: str) -> bool:
    """PostgreSQL 版本的告警去重检查"""
    with _pg_connection() as conn:
        if conn is None:
            return False  # 降级到内存模式
        
        key = f"{alert_type}:{alert_title}"
        window = _ALERT_DEDUP_WINDOW_SECONDS
        
        with conn.cursor() as cur:
            # 尝试获取最后处理时间
            cur.execute(
                "SELECT last_seen_at FROM alert_dedup WHERE alert_key = %s",
                (key,)
            )
            row = cur.fetchone()
            
            if row:
                last_time = row[0]
                # 使用 SQL 计算时间差
                cur.execute(
                    "SELECT EXTRACT(EPOCH FROM (NOW() - %s)) < %s",
                    (last_time, window)
                )
                is_duplicate = cur.fetchone()[0]
                
                if is_duplicate:
                    # 更新最后访问时间
                    cur.execute(
                        "UPDATE alert_dedup SET last_seen_at = NOW() WHERE alert_key = %s",
                        (key,)
                    )
                    conn.commit()
                    return True
                else:
                    # 超时，更新时间戳
                    cur.execute(
                        "UPDATE alert_dedup SET last_seen_at = NOW() WHERE alert_key = %s",
                        (key,)
                    )
                    conn.commit()
                    return False
            else:
                # 新记录，插入
                cur.execute(
                    "INSERT INTO alert_dedup (alert_key, last_seen_at) VALUES (%s, NOW())",
                    (key,)
                )
                conn.commit()
                return False


def _cleanup_pg_dedup():
    """清理 PostgreSQL 中过期的去重记录"""
    with _pg_connection() as conn:
        if conn is None:
            return
        
        window = _ALERT_DEDUP_WINDOW_SECONDS * 2  # 2倍窗口期后清理
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM alert_dedup WHERE EXTRACT(EPOCH FROM (NOW() - last_seen_at)) > %s",
                (window,)
            )
            conn.commit()

# 指标历史趋势缓存：用于判断是短暂峰值还是持续问题
_metric_history: dict[str, list[tuple[float, float]]] = {}  # type -> [(timestamp, value), ...]
_MAX_HISTORY_POINTS = 10  # 保留最近 10 个数据点

def _record_metric(type: str, value: float) -> None:
    """记录指标历史趋势"""
    now = time.time()
    if type not in _metric_history:
        _metric_history[type] = []
    _metric_history[type].append((now, value))
    # 只保留最近 N 个点
    if len(_metric_history[type]) > _MAX_HISTORY_POINTS:
        _metric_history[type] = _metric_history[type][- _MAX_HISTORY_POINTS:]

def _analyze_trend(type: str, threshold: float = 80.0) -> dict[str, Any]:
    """分析指标趋势，返回趋势分析结果"""
    history = _metric_history.get(type, [])
    if len(history) < 3:
        return {
            "has_trend": False,
            "is_sustained": False,
            "trend_direction": "unknown",
            "avg_value": 0.0,
            "peak_count": 0,
            "analysis": "数据不足，无法判断趋势"
        }
    
    values = [v for _, v in history]
    avg_value = sum(values) / len(values)
    current_value = values[-1] if values else 0.0
    
    # 判断是否持续高于阈值
    sustained_threshold = threshold * 0.95
    above_count = sum(1 for v in values if v >= sustained_threshold)
    peak_count = sum(1 for v in values if v >= threshold)
    
    # 趋势方向：最近 3 个点 vs 前面所有点的平均值
    recent = values[-3:] if len(values) >= 3 else values
    older = values[:-3] if len(values) > 3 else values
    
    if older:
        older_avg = sum(older) / len(older)
        if recent[-1] > older_avg * 1.1:
            trend = "rising"
        elif recent[-1] < older_avg * 0.9:
            trend = "falling"
        else:
            trend = "stable"
    else:
        trend = "stable"
    
    is_sustained = above_count >= len(values) * 0.7  # 70% 以上时间都高于阈值
    
    # 生成分析文本
    if is_sustained:
        analysis = f"持续偏高：最近 {len(values)} 次采样中 {above_count} 次高于 {sustained_threshold:.0f}%，平均 {avg_value:.1f}%，当前 {current_value:.1f}%"
    elif peak_count > 0:
        analysis = f"偶发峰值：{peak_count} 次超过 {threshold}%，但未持续，当前 {current_value:.1f}%"
    else:
        analysis = f"波动正常：平均 {avg_value:.1f}%，当前 {current_value:.1f}%"
    
    return {
        "has_trend": True,
        "is_sustained": is_sustained,
        "trend_direction": trend,
        "avg_value": avg_value,
        "peak_count": peak_count,
        "analysis": analysis
    }

def _is_alert_duplicate(alert_type: str, alert_title: str) -> bool:
    """检查告警是否在去重窗口期内已处理过（优先 PostgreSQL，回退内存）"""
    key = f"{alert_type}:{alert_title}"
    
    # 优先使用 PostgreSQL（支持多进程/多实例）
    if _PG_ENABLED and _is_alert_duplicate_pg(alert_type, alert_title):
        return True
    
    # 回退到内存缓存（单进程模式）
    now = time.time()
    if key in _alert_dedup_cache:
        last_time = _alert_dedup_cache[key]
        if now - last_time < _ALERT_DEDUP_WINDOW_SECONDS:
            return True
    _alert_dedup_cache[key] = now
    # 清理过期缓存
    expired_keys = [k for k, t in _alert_dedup_cache.items() if now - t > _ALERT_DEDUP_WINDOW_SECONDS * 2]
    for k in expired_keys:
        _alert_dedup_cache.pop(k, None)
    return False


class AlertPayload(BaseModel):
    level: str = Field(..., description="Alert level: warning or critical")
    type: str = Field(..., description="Alert type such as cpu, memory, disk")
    title: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    system_context: dict[str, Any] | None = Field(default=None, description="Realtime monitor context from desktop")


class Command(BaseModel):
    tool: str = Field(..., description="Tool name")
    type: str = Field(default="read", description="read | network | destructive | system")
    params: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default="")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    risk: str = Field(default="medium", description="low | medium | high")
    require_confirmation: bool = Field(default=False)
    auto_execute: bool = Field(default=False, description="Whether backend should auto-execute this")


class AutomationResponse(BaseModel):
    summary: str
    action: str
    priority: str
    reply: str | None = None
    commands: list[Command] = Field(default_factory=list)


# 命令执行缓存：key -> timestamp
_command_cache: dict[str, float] = {}

# 🆕 命令去重缓存（60秒防抖）
CommandDedupeCache: dict[str, float] = {}
_COMMAND_DEDUP_WINDOW = 60.0


def _is_recently_executed(key: str, ttl_seconds: int = 60) -> bool:
    last = _command_cache.get(key)
    if last and (time.time() - last) < ttl_seconds:
        return True
    return False


def _mark_executed(key: str) -> None:
    _command_cache[key] = time.time()


def _pick_top_processes(system_context: dict[str, Any] | None, limit: int = 5) -> list[dict[str, Any]]:
    processes = (system_context or {}).get("processes", {}) if system_context else {}
    top = processes.get("topProcesses", []) if isinstance(processes, dict) else []
    return [item for item in top if isinstance(item, dict)][:limit]


def _get_memory_usage(system_context: dict[str, Any] | None) -> float:
    if not system_context:
        return 0.0
    return float(system_context.get("memory", {}).get("usagePercent", 0) or 0)


def _get_cpu_usage(system_context: dict[str, Any] | None) -> float:
    if not system_context:
        return 0.0
    return float(system_context.get("cpu", {}).get("usagePercent", 0) or 0)


def _get_disk_usage(system_context: dict[str, Any] | None) -> float:
    if not system_context:
        return 0.0
    disk = system_context.get("disk", {})
    disks = disk.get("disks", []) if isinstance(disk, dict) else []
    return max((d.get("usePercent", 0) for d in disks if isinstance(d, dict)), default=0)


DANGEROUS_PROCESS_NAMES = {
    "system", "idle", "registry", "smss.exe", "csrss.exe", "wininit.exe",
    "winlogon.exe", "services.exe", "lsass.exe", "svchost.exe", "explorer.exe",
    "electron.exe", "dwm.exe", "memory compression"
}


def _normalize_name(name: Any) -> str:
    return str(name or "").strip().lower()


def _validate_and_filter_commands(
    commands: list[Command],
    alert_type: str,
    system_context: dict[str, Any] | None,
    level: str,
) -> list[Command]:
    """验证命令安全性，补充缺失的关键命令，过滤重复"""
    validated: list[Command] = []
    seen_tools: set[str] = set()
    has_destructive = False
    has_relevant_action = False

    # 检查是否包含与告警类型相关的处置命令
    alert_tool_map = {
        "cpu": {"process:kill", "process:top", "process:list"},
        "memory": {"process:kill", "process:top", "process:list"},
        "disk": {"disk:cleanup", "temp:cleanup", "temp:scan", "disk:list"},
    }
    relevant_tools = alert_tool_map.get(alert_type, set())

    top_procs = _pick_top_processes(system_context, limit=10)
    proc_by_pid = {
        int(p.get("pid")): p
        for p in top_procs
        if isinstance(p, dict) and str(p.get("pid", "")).isdigit()
    }

    for cmd in commands:
        # 去重：同类型命令 60 秒内不重复
        cache_key = f"{cmd.tool}:{json.dumps(cmd.params, sort_keys=True)}"
        if cmd.type == "read" and _is_recently_executed(cache_key, 60):
            continue

        # 安全校验：process:kill（支持 pid 或 name 参数）
        if cmd.tool == "process:kill":
            pid = int(cmd.params.get("pid") or 0)
            name = cmd.params.get("name") or ""
            name_lower = name.lower() if name else ""
            
            # 🆕 按名称匹配：保护进程名含系统关键词的
            if name_lower:
                protected_patterns = ["system", "registry", "csrss", "smss", "winlogon", 
                    "services", "lsass", "svchost", "dwm", "wininit", "memory compression"]
                if any(p in name_lower for p in protected_patterns):
                    validated.append(Command(
                        tool="notify",
                        type="read",
                        params={"title": "高风险操作已拦截", "body": f"系统进程 {name} 不可结束，已跳过"},
                        reason=f"拦截结束系统进程 {name}", confidence=1.0, risk="low",
                    ))
                    continue
            
            # 🆕 只有 pid 时校验 pid
            if pid > 0:
                proc = proc_by_pid.get(pid, {})
                proc_name = _normalize_name(proc.get("name"))
                if proc_name in DANGEROUS_PROCESS_NAMES or pid in {0, 4}:
                    validated.append(Command(
                        tool="notify",
                        type="read",
                        params={"title": "高风险操作已拦截", "body": f"系统进程 {proc_name or pid} 不可结束，已跳过"},
                        reason=f"拦截结束系统进程 {proc_name}", confidence=1.0, risk="low",
                    ))
                    continue
            
            has_destructive = True
            # critical 级别且 confidence >= 0.7 的 kill 命令自动执行
            if level == "critical" and cmd.confidence >= 0.7:
                cmd.auto_execute = True
                cmd.require_confirmation = False

        if cmd.tool in relevant_tools:
            has_relevant_action = True

        if cmd.type == "read":
            _mark_executed(cache_key)

        validated.append(cmd)
        seen_tools.add(cmd.tool)

    # 补充缺失的关键命令：如果告警严重但没生成相关处置命令
    if level == "critical" and not has_relevant_action:
        if alert_type in ("cpu", "memory"):
            if "process:top" not in seen_tools:
                validated.insert(0, Command(
                    tool="process:top",
                    type="read",
                    params={"max": 5},
                    reason=f"自动补充：{alert_type} critical 告警必须定位高占用进程",
                    confidence=0.95,
                    risk="low",
                ))
        elif alert_type == "disk":
            if "temp:scan" not in seen_tools:
                validated.insert(0, Command(
                    tool="temp:scan",
                    type="read",
                    params={"max": 30},
                    reason="自动补充：磁盘 critical 告警必须扫描临时文件",
                    confidence=0.95,
                    risk="low",
                ))

    # critical 内存/CPU > 90% 时，自动补充 kill 命令（如果 LLM 没给）
    if level == "critical" and alert_type in ("cpu", "memory") and not has_destructive:
        mem_usage = _get_memory_usage(system_context)
        cpu_usage = _get_cpu_usage(system_context)
        if (alert_type == "memory" and mem_usage >= 90) or (alert_type == "cpu" and cpu_usage >= 90):
            top = _pick_top_processes(system_context, limit=1)
            if top:
                target = top[0]
                pid = target.get("pid")
                name = target.get("name", "unknown")
                if pid and _normalize_name(name) not in DANGEROUS_PROCESS_NAMES:
                    validated.append(Command(
                        tool="process:kill",
                        type="destructive",
                        params={"pid": pid},
                        reason=f"自动补充：{alert_type} 已达 critical 阈值，结束最高占用进程 {name}",
                        confidence=0.85,
                        risk="high",
                        require_confirmation=False,  # critical 自动执行
                        auto_execute=True,
                    ))

    return validated


def _extract_commands_from_llm(reply: str) -> list[Command]:
    """从 LLM 回复中提取 [COMMANDS]...[/COMMANDS] 格式的 JSON 命令"""
    if not reply:
        return []
    # 匹配 [COMMANDS] 标签
    patterns = [
        r'\[COMMANDS\](.*?)\[/COMMANDS\]',
        r'```json\s*(.*?)\s*```',
        r'"commands":\s*(\[.*?\])',
    ]
    for pattern in patterns:
        match = re.search(pattern, reply, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1).strip())
                if isinstance(data, list):
                    return [
                        Command(
                            tool=c.get("tool", "notify"),
                            type=c.get("type", "read"),
                            params=c.get("params", {}),
                            reason=c.get("reason", ""),
                            confidence=c.get("confidence", 0.8),
                            risk=c.get("risk", "medium"),
                            require_confirmation=c.get("require_confirmation", False),
                            auto_execute=c.get("auto_execute", False),
                        )
                        for c in data if isinstance(c, dict)
                    ]
            except Exception:
                continue
    return []


@router.post("/handle-alert", response_model=AutomationResponse)
async def handle_alert(payload: AlertPayload):
    # 30秒去重检查
    if _is_alert_duplicate(payload.type, payload.title):
        return AutomationResponse(
            summary=f"去重跳过：{payload.title}（30秒内已处理）",
            action="告警已在处理中，跳过重复触发。",
            priority="low",
            commands=[],
        )

    # 构建系统上下文摘要（提前获取，供硬性阈值拦截使用）
    mem_usage = _get_memory_usage(payload.system_context)
    cpu_usage = _get_cpu_usage(payload.system_context)
    disk_usage = _get_disk_usage(payload.system_context)

    # ===== 硬性阈值拦截：warning 级别且指标未达阈值，直接返回 notify =====
    if payload.level == "warning":
        if payload.type == "memory" and mem_usage < 90:
            return AutomationResponse(
                summary=f"内存 {mem_usage:.1f}%，未达自动处置阈值（90%）",
                action="仅通知，不执行 kill",
                priority="low",
                reply=f"内存使用 {mem_usage:.1f}%，属于正常偏高，无需结束进程。建议关闭不必要的程序。",
                commands=[Command(
                    tool="notify",
                    type="read",
                    params={
                        "title": "内存使用偏高",
                        "body": f"当前内存 {mem_usage:.1f}%，建议关闭不必要的程序。如持续上升到 90% 以上，系统将自动处置。"
                    },
                    reason="内存未达阈值，仅通知",
                    confidence=1.0,
                    risk="low",
                )],
            )
        
        if payload.type == "cpu" and cpu_usage < 85:
            return AutomationResponse(
                summary=f"CPU {cpu_usage:.1f}%，未达自动处置阈值（85%）",
                action="仅通知",
                priority="low",
                reply=f"CPU 使用 {cpu_usage:.1f}%，属于正常范围。",
                commands=[Command(
                    tool="notify",
                    type="read",
                    params={
                        "title": "CPU 使用正常",
                        "body": f"当前 CPU {cpu_usage:.1f}%，无需处置。"
                    },
                    reason="CPU 未达阈值",
                    confidence=1.0,
                    risk="low",
                )],
            )
    
    priority = "high" if payload.level == "critical" else "medium"
    
    # 记录指标趋势
    _record_metric("cpu", cpu_usage)
    _record_metric("memory", mem_usage)
    _record_metric("disk", disk_usage)
    
    # 分析指标趋势
    threshold = 80.0 if payload.level == "warning" else 70.0
    trend_analysis = _analyze_trend(payload.type, threshold)
    
    # 构建系统上下文摘要
    top_procs = _pick_top_processes(payload.system_context, limit=5)
    proc_summary = "；".join(
        f"{p.get('name', 'unknown')}(PID:{p.get('pid', '?')}, CPU:{p.get('cpu', 0)}%, MEM:{p.get('memoryLabel', '0')})"
        for p in top_procs
    ) or "暂无进程数据"
    
    # 趋势判断：偶发峰值不执行处置
    is_sustained = trend_analysis.get("is_sustained", False)
    trend_direction = trend_analysis.get("trend_direction", "unknown")
    
    summary = f"Agent 已接收 {payload.level} 级别告警：{payload.title}"
    summary += f"\n趋势分析：{trend_analysis['analysis']}"
    
    # 如果不是持续偏高（偶发峰值），只记录不执行处置
    if payload.level == "warning" and not is_sustained:
        return AutomationResponse(
            summary=summary,
            action=f"偶发峰值，已记录趋势（{trend_direction}），暂不执行处置。",
            priority="low",
            reply=f"检测到 {payload.title}，但趋势分析显示这是偶发峰值（{trend_analysis['analysis']}），暂不执行自动处置。如果问题持续，系统会自动执行。",
            commands=[],
        )
    
    # 持续偏高或 critical 级别才执行处置 - 继续处理
    prompt = f"""你是桌面运维 Agent。当前系统告警如下，你必须直接决定执行什么命令来解决问题，不要给出文字建议。

告警信息：
- 类型: {payload.type}
- 等级: {payload.level}
- 标题: {payload.title}
- 描述: {payload.message}

实时监控数据：
- CPU: {cpu_usage}% | 内存: {mem_usage}% | 磁盘: {disk_usage}%
- Top 进程: {proc_summary}

可用工具（清理类命令会大幅释放空间，优先使用）：
- process:top / process:list (read) — 查看进程
- process:kill (destructive) — 结束进程，params: {{"pid": number}} 或 {{"name": "进程名"}}
- disk:list / temp:scan (read) — 查看磁盘/扫描临时文件
- disk:cleanup (destructive) — 磁盘深度清理（多目录），params: {{"max": number}}
- temp:cleanup (destructive) — 临时文件清理，params: {{"path": "...", "max": number}}
- system:recycle (destructive) — 清空回收站，params: {{}}
- system:browser-cache (destructive) — 清理浏览器缓存，params: {{"browser": "all"}}
- notify (read) — 桌面通知，params: {{"title": string, "body": string}}
- system:info (read) — 系统信息

执行规则：
1. {payload.level} 级别告警必须至少生成一个与问题直接相关的处置命令
2. 如果内存/CPU > 90%，直接生成 process:kill 结束最高占用进程（非系统进程）
3. 如果磁盘 > 85%，生成 disk:cleanup + temp:cleanup + system:recycle + system:browser-cache（综合清理）
4. read/network 类型命令会自动执行，destructive 类型默认需要确认（但 critical 可设置 auto_execute=true）
5. 清理操作是安全的，放心生成
6. 不要生成重复命令，60 秒内执行过的同类命令会自动跳过

输出格式：
先一句话分析现状（含具体数值），然后：
[COMMANDS]
[
  {{"tool":"process:top","type":"read","params":{{"max":5}},"reason":"定位高占用进程"}},
  {{"tool":"process:kill","type":"destructive","params":{{"pid":12345}},"reason":"结束异常进程释放内存","auto_execute":true,"require_confirmation":false}}
]
[/COMMANDS]"""

    result = await generate_structured(
        prompt,
        mode="automation",
        system_context=payload.system_context,
        voice_context={
            "source": "automation-alert",
            "locale": "zh-CN",
            "device": "desktop",
        },
        output_schema="""
JSON 格式（纯数组，不要任何文字）：
[
  {"tool": "...", "type": "read|destructive|system|network", "params": {}, "reason": "...", "confidence": 0.8, "auto_execute": true/false, "require_confirmation": true/false}
]
"""
    )

    parsed = result.get("parsed")
    # 支持 parsed 为数组或 {"commands": [...]} 字典两种格式
    if isinstance(parsed, list):
        commands_raw = parsed
    elif isinstance(parsed, dict):
        commands_raw = parsed.get("commands", [])
    else:
        commands_raw = []
    
    # 直接解析 JSON 命令，不再用正则提取
    commands = [
        Command(
            tool=c.get("tool", "notify"),
            type=c.get("type", "read"),
            params=c.get("params", {}),
            reason=c.get("reason", ""),
            confidence=c.get("confidence", 0.8),
            risk=c.get("risk", "medium"),
            require_confirmation=c.get("require_confirmation", False),
            auto_execute=c.get("auto_execute", False),
        )
        for c in commands_raw if isinstance(c, dict)
    ]
    
    reply = result.get("content", "")
    
    # 验证、过滤、补充
    validated = _validate_and_filter_commands(
        commands, payload.type, payload.system_context, payload.level
    )

    # 构建 action 文本（给前端展示用）
    action_parts = []
    auto_cmds = [c for c in validated if c.auto_execute or c.type in ("read", "network")]
    pending_cmds = [c for c in validated if c.type == "destructive" and not c.auto_execute]
    
    if auto_cmds:
        action_parts.append(f"已自动执行: {', '.join(c.tool for c in auto_cmds)}")
    if pending_cmds:
        action_parts.append(f"待确认: {', '.join(c.tool for c in pending_cmds)}")
    if not validated:
        action_parts.append("未生成有效处置命令")

    action_text = "；".join(action_parts)

    return AutomationResponse(
        summary=summary,
        action=action_text,
        priority=priority,
        reply=reply,
        commands=validated,
    )


# === 以下是保留的工具函数，用于 parse_user_command ===

ACTION_MAP = {
    "disk": "建议检查磁盘空间使用情况，清理不必要的文件或临时文件。",
    "memory": "建议检查高占用进程，必要时结束非必要进程释放内存。",
    "cpu": "建议检查 CPU 占用情况，关闭高占用程序或重启资源占用服务。",
    "network": "建议检查网络连接状态，确认是否有异常流量或断连情况。",
}


def _build_action_text(alert_type: str, payload: Any, system_context: Any, llm_reply: str | None) -> str:
    """基于 LLM 回复构建动作描述"""
    if llm_reply:
        # 截取前100字符作为摘要
        summary = llm_reply[:100].strip()
        if len(llm_reply) > 100:
            summary += "..."
        return summary
    default = ACTION_MAP.get(alert_type, "建议关注并处理此告警。")
    return default


def parse_commands_from_suggestion(alert_type: str, suggestion: str, system_context: Any) -> list[Command]:
    """基于建议文本解析出命令（不再生成 pid:0 的无效 kill）"""
    commands: list[Command] = []
    normalized = suggestion.lower()
    
    if alert_type == "disk":
        commands.append(Command(
            tool="disk:list",
            type="read",
            params={},
            reason="获取磁盘使用情况",
            confidence=0.90,
            risk="low",
        ))
        if "清理" in normalized:
            commands.append(Command(
                tool="disk:cleanup",
                type="destructive",
                params={"max": 50},
                reason="清理磁盘空间",
                confidence=0.80,
                risk="high",
                require_confirmation=True,
            ))
    elif alert_type == "memory":
        commands.append(Command(
            tool="process:top",
            type="read",
            params={"max": 5},
            reason="查看高内存占用进程",
            confidence=0.92,
            risk="low",
        ))
        # 🆕 不再生成 pid:0 的无效 kill，只扫描，让用户或前端决定
    elif alert_type == "cpu":
        commands.append(Command(
            tool="process:top",
            type="read",
            params={"max": 5},
            reason="查看高 CPU 占用进程",
            confidence=0.92,
            risk="low",
        ))
        # 🆕 不再生成 pid:0 的无效 kill
    
    return commands


def parse_user_command(text: str) -> tuple[str, list[Command], str]:
    """解析用户自然语言命令，返回 (分析, 命令列表, 回复文本)"""
    normalized = text.strip()
    commands: list[Command] = []
    reply_text = ""
    analysis = ""

    # 统一转小写用于匹配（保留原始文本用于回复）
    nl = normalized.lower()

    # ---- 磁盘相关 ----
    if "查看磁盘" in normalized or "磁盘情况" in normalized or "磁盘状态" in normalized or "磁盘信息" in normalized:
        analysis = "检测到磁盘查看请求。将获取各磁盘的使用情况、已用空间和可用空间，判断是否需要清理。"
        commands.append(Command(
            tool="disk:list",
            type="read",
            params={},
            reason="获取各磁盘使用情况",
            confidence=0.93,
            risk="low",
            recommended=True,
        ))
        reply_text = "正在获取磁盘信息，请稍候。"

    elif "清理" in normalized and ("c盘" in nl or "系统盘" in normalized):
        # 🆕 C 盘综合清理：生成 4 个清理命令
        analysis = "检测到 C 盘综合清理请求。将执行磁盘清理、回收站清空、浏览器缓存清理、临时文件清理，一次性释放最大空间。"
        commands.append(Command(
            tool="disk:cleanup",
            type="destructive",
            params={"max": 100},
            reason="清理系统盘多个目录的临时文件和垃圾",
            confidence=0.88,
            risk="medium",
            require_confirmation=True,
        ))
        commands.append(Command(
            tool="system:recycle",
            type="destructive",
            params={},
            reason="清空回收站释放空间",
            confidence=0.82,
            risk="medium",
            require_confirmation=True,
        ))
        commands.append(Command(
            tool="system:browser-cache",
            type="destructive",
            params={"browser": "all"},
            reason="清理浏览器缓存（Edge/Chrome）",
            confidence=0.80,
            risk="medium",
            require_confirmation=True,
        ))
        commands.append(Command(
            tool="temp:cleanup",
            type="destructive",
            params={"max": 80},
            reason="清理系统临时目录",
            confidence=0.85,
            risk="medium",
            require_confirmation=True,
        ))
        reply_text = "正在执行 C 盘综合清理：磁盘清理 + 回收站 + 浏览器缓存 + 临时文件。"

    # ---- "看看C盘" / "查看C盘" / "C盘情况" ----
    elif ("c盘" in nl or "系统盘" in normalized) and ("查看" in normalized or "看看" in normalized or "情况" in normalized or "状态" in normalized or "信息" in normalized or "空间" in normalized):
        analysis = "检测到系统盘查看请求。将获取 C 盘使用率、已用/可用空间，并扫描临时文件占用情况。"
        commands.append(Command(
            tool="disk:list",
            type="read",
            params={},
            reason="获取系统盘使用情况",
            confidence=0.93,
            risk="low",
            recommended=True,
        ))
        commands.append(Command(
            tool="temp:scan",
            type="read",
            params={"max": 50},
            reason="同时扫描临时文件占用",
            confidence=0.88,
            risk="low",
        ))
        reply_text = "正在获取C盘信息和临时文件扫描。"

    # ---- CPU 相关 ----
    elif "cpu" in nl or "处理器" in normalized or "cpu状态" in nl or "cpu情况" in nl or "cpu使用" in nl:
        analysis = "检测到 CPU 诊断请求。将获取系统基本信息和高 CPU 占用进程列表，定位异常消耗源。"
        commands.append(Command(
            tool="system:info",
            type="read",
            params={},
            reason="获取系统 CPU 与基础运行信息",
            confidence=0.93,
            risk="low",
            recommended=True,
        ))
        commands.append(Command(
            tool="process:top",
            type="read",
            params={"max": 10},
            reason="查看高 CPU 占用进程",
            confidence=0.90,
            risk="low",
        ))
        reply_text = "正在获取 CPU 状态和高占用进程信息。"

    # ---- 进程相关 ----
    elif "查看进程" in normalized or "进程情况" in normalized or "进程状态" in normalized or "进程列表" in normalized:
        analysis = "检测到进程查看请求。将列出当前所有运行进程及其资源占用情况。"
        commands.append(Command(
            tool="process:list",
            type="read",
            params={"max": 20},
            reason="获取当前进程列表",
            confidence=0.92,
            risk="low",
            recommended=True,
        ))
        reply_text = "正在获取进程列表，请稍候。"

    # ---- 结束/关闭/杀掉 进程（支持按名称）----
    elif any(k in nl for k in ["结束", "关闭", "杀掉", "停止", "kill", "终止"]):
        analysis = "检测到进程结束请求。将直接查找并结束目标进程。"
        
        # 从文本中提取目标进程名
        known_apps = {
            '联想浏览器': 'SLBrowser.exe', 'slbrowser': 'SLBrowser.exe',
            '联想': 'SLBrowser.exe',  # 单独说"联想"也匹配浏览器
            '微信': 'WeChat.exe', 'wechat': 'WeChat.exe',
            '扣扣': 'QQ.exe', 'qq': 'QQ.exe',
            'edge': 'msedge.exe', 'edge浏览器': 'msedge.exe', '微软浏览器': 'msedge.exe',
            '浏览器': 'msedge.exe',  # 通用浏览器默认 Edge
            'chrome': 'chrome.exe', '谷歌浏览器': 'chrome.exe',
            '谷歌': 'chrome.exe',
            'vscode': 'Code.exe', 'code': 'Code.exe',
            'python': 'python.exe',
            'node': 'node.exe', 'nodejs': 'node.exe',
            '钉钉': 'DingTalk.exe', 'dingtalk': 'DingTalk.exe',
            '飞书': 'Feishu.exe', 'feishu': 'Feishu.exe',
            'steam': 'steam.exe',
            'epic': 'EpicGamesLauncher.exe',
        }
        
        target_name = None
        lower_text = normalized.lower()
        
        # 优先匹配完整名称（放前面避免被短关键词覆盖）
        for key in sorted(known_apps.keys(), key=len, reverse=True):
            if key in lower_text:
                target_name = known_apps[key]
                break
        
        if target_name:
            # 🎯 直接生成按名称结束的命令
            commands.append(Command(
                tool="process:kill",
                type="destructive",
                params={"name": target_name},  # 主进程会按名称查找 PID
                reason=f"结束进程 {target_name}",
                confidence=0.95,
                risk="high",
                require_confirmation=True,
            ))
            reply_text = f"准备结束 {target_name}。"
        else:
            # 不知道名字，列出进程让用户选
            commands.append(Command(
                tool="process:list",
                type="read",
                params={"max": 30},
                reason="列出所有进程供选择",
                confidence=0.80,
                risk="low",
            ))
            reply_text = "正在列出进程，请选择要结束的目标。"

    # ---- 临时文件清理 ----
    elif "清理临时" in normalized or "清理temp" in normalized or "临时文件" in normalized:
        analysis = "检测到临时文件清理请求。将扫描系统临时目录（temp/tmp/log/bak），列出可清理项后再执行。"
        commands.append(Command(
            tool="temp:scan",
            type="read",
            params={"max": 50},
            reason="扫描临时目录中的候选清理文件",
            confidence=0.90,
            risk="low",
            recommended=True,
        ))
        commands.append(Command(
            tool="temp:cleanup",
            type="destructive",
            params={"max": 80},
            reason="在你确认后清理临时目录中的 temp/tmp/log/bak 文件",
            confidence=0.84,
            risk="high",
            require_confirmation=True,
        ))
        reply_text = "已先扫描临时文件，并准备好待确认的清理操作。"

    # ---- 内存相关 ----
    elif "查看内存" in normalized or "内存情况" in normalized or "内存状态" in normalized or "内存信息" in normalized:
        analysis = "检测到内存查看请求。将获取系统内存总量、使用量和使用率，并定位高占用进程。"
        commands.append(Command(
            tool="system:info",
            type="read",
            params={},
            reason="获取系统内存与基础运行信息",
            confidence=0.93,
            risk="low",
            recommended=True,
        ))
        commands.append(Command(
            tool="process:top",
            type="read",
            params={"max": 10},
            reason="查看高内存占用进程",
            confidence=0.90,
            risk="low",
        ))
        reply_text = "正在获取系统内存信息，并定位高占用进程。"

    elif "清理内存" in normalized or "释放内存" in normalized:
        analysis = "检测到内存清理请求。将扫描高占用进程并自动生成结束命令。"
        commands.append(Command(
            tool="process:top",
            type="read",
            params={"max": 10},
            reason="定位高占用进程",
            confidence=0.90,
            risk="low",
            recommended=True,
        ))
        # 🆕 直接生成常见高内存应用的 kill 命令，Electron 端会按名称查找 PID 并过滤未运行的
        high_memory_apps = [
            ("chrome.exe", "Chrome"), ("msedge.exe", "Edge"), ("firefox.exe", "Firefox"),
            ("Code.exe", "VS Code"), ("pycharm64.exe", "PyCharm"), ("idea64.exe", "IDEA"),
            ("WeChat.exe", "微信"), ("DingTalk.exe", "钉钉"), ("QQ.exe", "QQ"),
            ("steam.exe", "Steam"), ("EpicGamesLauncher.exe", "Epic"),
        ]
        for proc_name, display_name in high_memory_apps:
            commands.append(Command(
                tool="process:kill",
                type="destructive",
                params={"name": proc_name},
                reason=f"结束 {display_name} 释放内存",
                confidence=0.70,
                risk="high",
                require_confirmation=True,
            ))
        reply_text = "已扫描高占用进程，并生成常见高内存应用（Chrome/Edge/VS Code/微信等）的结束命令。系统将自动检测哪些进程正在运行，仅结束实际存在的进程。勾选确认后执行即可释放内存。"

    # ---- 综合诊断 / 主机状态 / 系统状态 ----
    elif any(kw in normalized for kw in ["主机状态", "系统状态", "系统信息", "整体状态", "诊断", "体检", "检查状态", "状态检查"]):
        analysis = "检测到系统综合诊断请求。将全面收集 CPU、内存、进程和磁盘使用情况，评估系统健康状态并给出优化建议。"
        commands.append(Command(
            tool="system:info",
            type="read",
            params={},
            reason="获取系统整体运行信息",
            confidence=0.93,
            risk="low",
            recommended=True,
        ))
        commands.append(Command(
            tool="process:top",
            type="read",
            params={"max": 10},
            reason="查看高资源占用进程",
            confidence=0.90,
            risk="low",
        ))
        commands.append(Command(
            tool="disk:list",
            type="read",
            params={},
            reason="获取磁盘使用情况",
            confidence=0.90,
            risk="low",
        ))
        reply_text = "正在进行系统综合诊断，包括 CPU、内存、进程和磁盘。"

    # ---- 打开/启动 应用 ----
    elif any(k in normalized for k in ["打开", "启动", "运行", "开启"]):
        analysis = "检测到应用启动请求。将扫描已安装软件并打开目标程序。"
        
        # 从用户输入中提取应用名（去掉"打开"、"启动"等动词）
        app_query = normalized
        for verb in ["打开", "启动", "运行", "开启", "给我打开", "帮我打开"]:
            app_query = app_query.replace(verb, "")
        app_query = app_query.strip()
        
        if not app_query:
            reply_text = "请告诉我你想打开什么软件，比如：打开微信、打开浏览器、打开记事本。"
        else:
            # 使用软件索引自动查找（支持模糊匹配）
            entry = find_software(app_query)
            
            if entry and entry.exe_path:
                commands.append(Command(
                    tool="app:launch",
                    type="system",
                    params={"path": entry.exe_path},
                    reason=f"打开 {entry.name}",
                    confidence=0.95,
                    risk="low",
                ))
                reply_text = f"正在打开 {entry.name}。"
            else:
                # 未找到，生成友好提示
                commands.append(Command(
                    tool="notify",
                    type="read",
                    params={
                        "title": "未找到应用",
                        "body": f"未找到与「{app_query}」匹配的已安装软件。请确认软件名称，或尝试：打开微信、打开浏览器、打开记事本。"
                    },
                    reason=f"未找到软件: {app_query}",
                    confidence=1.0,
                    risk="low",
                ))
                reply_text = f"未找到「{app_query}」，请尝试其他名称。"

    # ---- 清理（通用）- 🆕 增强为综合清理 ----
    elif "清理" in normalized or "清理垃圾" in normalized or "垃圾清理" in normalized:
        analysis = "检测到综合清理请求。将执行磁盘清理、回收站清空、浏览器缓存清理，一次性释放最大空间。"
        commands.append(Command(
            tool="disk:cleanup",
            type="destructive",
            params={"max": 100},
            reason="清理多个目录的临时文件和垃圾",
            confidence=0.88,
            risk="medium",
            require_confirmation=True,
        ))
        commands.append(Command(
            tool="system:recycle",
            type="destructive",
            params={},
            reason="清空回收站释放空间",
            confidence=0.82,
            risk="medium",
            require_confirmation=True,
        ))
        commands.append(Command(
            tool="system:browser-cache",
            type="destructive",
            params={"browser": "all"},
            reason="清理浏览器缓存（Edge/Chrome）",
            confidence=0.80,
            risk="medium",
            require_confirmation=True,
        ))
        commands.append(Command(
            tool="temp:cleanup",
            type="destructive",
            params={"max": 80},
            reason="清理系统临时目录",
            confidence=0.85,
            risk="medium",
            require_confirmation=True,
        ))
        reply_text = "正在执行综合清理：磁盘清理 + 回收站 + 浏览器缓存 + 临时文件。"

    else:
        analysis = f"无法识别具体意图 '{normalized}'，将获取系统基础信息供参考。"
        reply_text = "未识别的指令，请尝试：查看磁盘、清理C盘、查看进程、清理临时、查看内存、释放内存、CPU状态、系统诊断"

    return analysis, commands, reply_text