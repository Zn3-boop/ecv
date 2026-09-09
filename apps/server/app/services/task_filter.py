"""
批量任务去重过滤服务

三层过滤管道：
1. 精确去重（same type + same params）
2. 语义去重（同类型查询合并）
3. 冲突检测（先查后杀、重复kill、危险操作限制）
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

# 保护的系统进程列表
PROTECTED_PROCESSES = frozenset([
    "explorer.exe", "csrss.exe", "smss.exe", "services.exe",
    "lsass.exe", "winlogon.exe", "svchost.exe", "System",
    "Registry", "Memory Compression", "dwm.exe", "wininit.exe",
    "winlogon", "dwm", "csrss", "smss", "services", "lsass",
])

# 危险进程名称（禁止结束的进程名关键词）
DANGEROUS_PROCESS_PATTERNS = frozenset([
    "system", "registry", "csrss", "smss", "winlogon",
    "services", "lsass", "svchost", "dwm", "wininit",
    "memory compression", "fontdrvhost", "wudfhost",
])

# 最大危险操作数量
MAX_DANGEROUS_PER_BATCH = 3

# 语义分组映射：同类查询归为一组
SEMANTIC_GROUPS = {
    "system:info": "query_system",
    "process:top": "query_system",
    "process:list": "query_system",
    "disk:usage": "query_system",
    "memory:usage": "query_system",
}


@dataclass
class AITask:
    """AI 任务数据结构"""
    id: str
    type: str           # 'system:info' | 'process:top' | 'process:kill' | 'browser:open' | ...
    tool: str           # 工具名称
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    is_dangerous: bool = False   # 是否危险操作
    priority: int = 100           # 优先级，数字小的先执行
    reason: str = ""             # 执行原因
    confidence: float = 0.8      # 置信度


@dataclass
class FilterResult:
    """过滤结果"""
    tasks: list[AITask]
    removed: list[AITask]
    reasons: list[str]
    warnings: list[str]


def task_to_aitask(task: dict | Any) -> AITask:
    """将字典或 Command 对象转换为 AITask"""
    if isinstance(task, AITask):
        return task
    
    # 支持字典格式
    if isinstance(task, dict):
        tool = task.get("tool", "")
        task_type = task.get("type", "read")
        is_dangerous = task_type in ("destructive",) or task.get("risk") == "high"
        
        return AITask(
            id=task.get("id", f"task_{hashlib.md5(json.dumps(task, sort_keys=True).encode()).hexdigest()[:8]}"),
            type=tool,
            tool=tool,
            params=task.get("params", {}),
            description=task.get("reason", task.get("description", "")),
            is_dangerous=is_dangerous,
            priority=task.get("priority", 100),
            reason=task.get("reason", ""),
            confidence=task.get("confidence", 0.8),
        )
    
    # 尝试从对象属性提取
    return AITask(
        id=getattr(task, "id", f"task_{time.time()}"),
        type=getattr(task, "tool", "unknown"),
        tool=getattr(task, "tool", "unknown"),
        params=getattr(task, "params", {}),
        description=getattr(task, "reason", ""),
        is_dangerous=getattr(task, "type", "read") == "destructive",
        priority=getattr(task, "priority", 100),
        reason=getattr(task, "reason", ""),
        confidence=getattr(task, "confidence", 0.8),
    )


def get_semantic_group(task: AITask) -> str | None:
    """获取任务的语义分组键"""
    return SEMANTIC_GROUPS.get(task.type)


def _check_pid_exists(pid: int) -> bool:
    """检查 PID 是否存在"""
    if not pid or pid <= 0:
        return False
    try:
        import subprocess
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
        return str(pid) in result.stdout
    except Exception:
        return True  # 默认放行，让执行层报错


def _check_process_protected(name: str) -> bool:
    """检查进程是否受保护"""
    if not name:
        return False
    name_lower = name.lower().replace(".exe", "")
    if name_lower in PROTECTED_PROCESSES:
        return True
    # 检查危险进程模式
    for pattern in DANGEROUS_PROCESS_PATTERNS:
        if pattern in name_lower:
            return True
    return False


def filter_tasks(raw_tasks: list[dict | AITask]) -> FilterResult:
    """
    三层过滤管道
    
    Args:
        raw_tasks: 原始任务列表
        
    Returns:
        FilterResult: 包含过滤后的任务、被移除的任务、原因和警告
    """
    removed: list[AITask] = []
    reasons: list[str] = []
    warnings: list[str] = []
    tasks: list[AITask] = []
    
    # 转换为 AITask 对象
    for task_dict in raw_tasks:
        tasks.append(task_to_aitask(task_dict))
    
    # === 第1层：精确去重（type + 关键参数指纹相同）===
    seen = set()
    deduped: list[AITask] = []
    
    for t in tasks:
        # 生成指纹
        params_str = json.dumps(t.params, sort_keys=True, default=str)
        fingerprint = f"{t.type}:{params_str}"
        fingerprint_hash = hashlib.md5(fingerprint.encode()).hexdigest()[:16]
        
        if fingerprint_hash in seen:
            removed.append(t)
            reasons.append(f"[去重] 任务 '{t.description or t.tool}' 与已有任务参数完全相同")
        else:
            seen.add(fingerprint_hash)
            deduped.append(t)
    
    tasks = deduped
    
    # === 第2层：语义去重（同类型系统查询合并，只保留最高优先级）===
    semantic_groups: dict[str, list[AITask]] = {}
    
    for t in tasks:
        group_key = get_semantic_group(t)
        if group_key:
            semantic_groups[group_key] = semantic_groups.get(group_key, [])
            semantic_groups[group_key].append(t)
    
    for group_key, group_tasks in semantic_groups.items():
        if len(group_tasks) > 1:
            # 按优先级排序（数字小的先执行）
            group_tasks.sort(key=lambda x: (x.priority, -x.confidence))
            keep = group_tasks[0]
            
            for i in range(1, len(group_tasks)):
                removed.append(group_tasks[i])
                reasons.append(
                    f"[语义合并] '{group_tasks[i].description or group_tasks[i].tool}' "
                    f"与 '{keep.description or keep.tool}' 属于同类查询，已合并"
                )
            
            # 从 tasks 中移除被合并的
            tasks = [t for t in tasks if t not in group_tasks[1:]]
    
    # === 第3层：冲突检测 ===
    
    # 规则3a：system:info 和 process:top 冲突（system:info 已包含进程概览）
    has_system_info = any(t.type == "system:info" for t in tasks)
    has_process_top = any(t.type == "process:top" for t in tasks)
    
    if has_system_info and has_process_top:
        to_remove = [t for t in tasks if t.type == "process:top"]
        for t in to_remove:
            removed.append(t)
            reasons.append(
                f"[冲突] '{t.description or t.tool}' 与系统信息查询重复，"
                f"system:info 已包含进程概览"
            )
        tasks = [t for t in tasks if t.type != "process:top"]
    
    # 规则3b：重复 kill 同一 PID
    kill_tasks = [t for t in tasks if t.type == "process:kill"]
    non_kill_tasks = [t for t in tasks if t.type != "process:kill"]
    deduped_kill: list[AITask] = []
    killed_pids: set[int] = set()
    
    for t in kill_tasks:
        pid = t.params.get("pid")
        if pid:
            pid = int(pid)
            if pid in killed_pids:
                removed.append(t)
                reasons.append(f"[冲突] PID {pid} 已被列入结束名单，跳过重复任务")
            elif not _check_pid_exists(pid):
                removed.append(t)
                reasons.append(f"[冲突] PID {pid} 已不存在，跳过")
            else:
                killed_pids.add(pid)
                deduped_kill.append(t)
        else:
            # 没有 pid 的 kill 任务需要 name 参数
            name = t.params.get("name", "")
            if not name:
                removed.append(t)
                reasons.append("[冲突] process:kill 缺少 PID 或名称，已跳过")
            elif _check_process_protected(name):
                removed.append(t)
                reasons.append(f"[冲突] 进程 '{name}' 是系统关键进程，禁止结束")
            else:
                deduped_kill.append(t)
    
    tasks = non_kill_tasks + deduped_kill
    
    # 规则3c：危险操作数量限制
    dangerous_count = sum(1 for t in tasks if t.is_dangerous)
    if dangerous_count > MAX_DANGEROUS_PER_BATCH:
        warnings.append(
            f"[安全] 危险操作共 {dangerous_count} 个，超过单次上限 {MAX_DANGEROUS_PER_BATCH} 个，"
            f"建议分批执行"
        )
    
    return FilterResult(
        tasks=tasks,
        removed=removed,
        reasons=reasons,
        warnings=warnings,
    )


def validate_batch_execution(tasks: list[AITask | dict]) -> dict[str, Any]:
    """
    批量执行前的最终确认检查
    
    Returns:
        包含 allowed 和 warnings 的字典
    """
    warnings: list[str] = []
    
    # 转换任务
    aitasks = [task_to_aitask(t) for t in tasks]
    
    dangerous = [t for t in aitasks if t.is_dangerous]
    
    if dangerous:
        tool_names = [t.tool for t in dangerous]
        warnings.append(f"⚠️ 包含 {len(dangerous)} 个危险操作（{'、'.join(tool_names)}），请确认")
    
    if len(dangerous) > MAX_DANGEROUS_PER_BATCH:
        warnings.append(
            f"🚫 危险操作超过 {MAX_DANGEROUS_PER_BATCH} 个，建议分批执行以避免误杀"
        )
        return {"allowed": False, "warnings": warnings, "dangerous_count": len(dangerous)}
    
    # 检查是否有自毁风险（结束当前进程或关键系统进程）
    for t in dangerous:
        if t.tool == "process:kill":
            pid = t.params.get("pid")
            name = t.params.get("name", "")
            
            # 检查是否是系统进程
            if name and _check_process_protected(name):
                warnings.append(f"💀 检测到可能结束后端服务自身的操作：{name}，已拦截")
                return {"allowed": False, "warnings": warnings, "blocked_task": t.id}
            
            # 检查是否是当前进程（粗略检查）
            if pid and int(pid) in (0, 4):
                warnings.append(f"💀 检测到尝试结束系统进程 PID {pid}，已拦截")
                return {"allowed": False, "warnings": warnings, "blocked_task": t.id}
    
    return {
        "allowed": True,
        "warnings": warnings,
        "dangerous_count": len(dangerous),
        "total_count": len(tasks),
    }


def format_filter_summary(result: FilterResult) -> str:
    """格式化过滤结果摘要"""
    lines = []
    
    if result.removed:
        lines.append(f"📋 已过滤 {len(result.removed)} 个任务：")
        for reason in result.reasons:
            lines.append(f"  • {reason}")
    else:
        lines.append("✅ 所有任务通过过滤")
    
    if result.warnings:
        lines.append("")
        lines.append("⚠️ 警告：")
        for warning in result.warnings:
            lines.append(f"  • {warning}")
    
    return "\n".join(lines)


# 缓存相关（用于防止短时间内重复执行）
_command_cache: dict[str, float] = {}
_COMMAND_CACHE_TTL = 60.0  # 60秒


def is_command_cached(cmd: AITask | dict, ttl_seconds: int = 60) -> bool:
    """检查命令是否在缓存中（短时间内执行过）"""
    if isinstance(cmd, dict):
        tool = cmd.get("tool", "")
        params = cmd.get("params", {})
    else:
        tool = cmd.tool
        params = cmd.params
    
    cache_key = f"{tool}:{json.dumps(params, sort_keys=True, default=str)}"
    last_time = _command_cache.get(cache_key)
    
    if last_time and (time.time() - last_time) < ttl_seconds:
        return True
    return False


def mark_command_executed(cmd: AITask | dict):
    """标记命令已执行"""
    if isinstance(cmd, dict):
        tool = cmd.get("tool", "")
        params = cmd.get("params", {})
    else:
        tool = cmd.tool
        params = cmd.params
    
    cache_key = f"{tool}:{json.dumps(params, sort_keys=True, default=str)}"
    _command_cache[cache_key] = time.time()


def clear_expired_cache():
    """清理过期的命令缓存"""
    now = time.time()
    expired = [k for k, t in _command_cache.items() if now - t > _COMMAND_CACHE_TTL * 2]
    for k in expired:
        _command_cache.pop(k, None)
