from __future__ import annotations

import json
import traceback
import uuid
from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.automation import parse_user_command
from app.services.llm.generator import generate_structured
from app.services.intent_detector import detect_intent

router = APIRouter(prefix="/agent", tags=["agent"])

DESKTOP_EXECUTOR_URL = "http://127.0.0.1:9000/execute"

AUTO_EXEC_SAFE_TOOLS = {
    'file:list', 'file:read', 'file:search',
    'system:info', 'system:env',
    'app:launch', 'clipboard:write',
    'notify', 'disk:list', 'temp:scan',
    'process:list', 'process:top', 'network:request',
    'content:generate', 'browser:search', 'ide:launch',
    'store:search', 'store:list',
}

DESTRUCTIVE_COMMAND_PATTERNS = ['uninstall', 'remove', 'delete', 'format', 'rmdir', 'rd /s', 'del /f']


# ===== 工具白名单 =====
ALLOWED_TOOLS = {
    'file:list', 'file:read', 'file:write', 'file:delete', 'file:search',
    'system:info', 'system:command', 'app:launch', 'clipboard:write',
    'notify', 'disk:list', 'temp:scan', 'temp:cleanup', 'disk:cleanup',
    'process:list', 'process:top', 'process:kill', 'network:request', 'system:env',
    'content:generate',
    'browser:search',
    'ide:launch',
    'store:search', 'store:install', 'store:uninstall', 'store:list',
}

# 工具 → 人类可读描述
TOOL_DESCRIPTIONS = {
    'process:kill': '结束进程（需要确认）',
    'temp:cleanup': '清理临时文件',
    'disk:cleanup': '清理磁盘临时文件',
    'process:top': '查看高占用进程',
    'system:info': '查看系统信息',
    'notify': '发送桌面通知',
    'content:generate': '生成文章/代码/文档/网页',
    'app:launch': '启动应用程序',
    'browser:search': '浏览器搜索',
    'ide:launch': '打开IDE创建项目/文件',
    'store:search': '搜索应用商店中的应用',
    'store:install': '安装应用（需要确认）',
    'store:uninstall': '卸载应用（需要确认）',
    'store:list': '列出已安装的应用',
}


class UserCommand(BaseModel):
    text: str = Field(..., description="用户输入的文本（STT转写结果）")
    session_id: str = Field(..., description="会话ID")
    context: dict[str, Any] | None = Field(default=None, description="系统上下文（可选）")
    auto_execute: bool = Field(default=True, description="是否自动执行低风险命令")


class ActionCommand(BaseModel):
    id: str = Field(..., description="命令ID")
    type: str = Field(..., description="命令类型：read/write/system/destructive")
    tool: str = Field(..., description="工具名称")
    params: dict[str, Any] = Field(default_factory=dict, description="工具参数")
    reason: str = Field(default="", description="执行原因")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="置信度")
    reasoning: str = Field(default="", description="AI识别推理依据")
    executed: bool = Field(default=False, description="是否已自动执行")
    exec_result: dict[str, Any] | None = Field(default=None, description="执行结果")


class SolutionMethod(BaseModel):
    id: str = Field(..., description="方法ID")
    title: str = Field(..., description="解决方法标题")
    description: str = Field(..., description="详细说明")
    steps: list[str] = Field(default_factory=list, description="执行步骤")
    commands: list[ActionCommand] = Field(default_factory=list, description="对应的技术命令")
    risk: str = Field(default="low", description="风险等级：low/medium/high")
    auto_executable: bool = Field(default=False, description="是否可自动执行")
    manual_steps: list[str] = Field(default_factory=list, description="需要手动执行的步骤")


class AgentResponse(BaseModel):
    analysis: str = Field(..., description="意图分析结果")
    solutions: list[SolutionMethod] = Field(default_factory=list, description="AI找到的解决方法列表")
    commands: list[ActionCommand] = Field(default_factory=list, description="可执行命令列表")
    reply_text: str = Field(..., description="给用户的回复文本（TTS用）")
    executed_count: int = Field(default=0, description="已自动执行的命令数")


# 意图关键词 → 指令映射（作为最终降级兜底）
INTENT_TOOL_MAP = {
    "查看c盘": {"tool": "system:command", "params_template": {"command": "cmd /c dir C:\\"}, "type": "read", "reply": "正在查看C盘文件列表..."},
    "查看磁盘": {"tool": "system:command", "params_template": {"command": "cmd /c wmic logicaldisk get size,freespace,caption"}, "type": "read", "reply": "正在查看磁盘空间..."},
    "查看进程": {"tool": "process:list", "params_template": {}, "type": "read", "reply": "正在查看系统进程..."},
    "磁盘空间": {"tool": "system:info", "params_template": {}, "type": "read", "reply": "正在获取系统信息..."},
    "清理临时": {"tool": "system:command", "params_template": {"command": "cmd /c dir %TEMP%"}, "type": "read", "reply": "正在扫描临时文件..."},
    "查看内存": {"tool": "system:info", "params_template": {}, "type": "read", "reply": "正在获取系统内存信息..."},
    "清理内存": {"tool": "system:command", "params_template": {"command": "clean_mem.bat"}, "type": "system", "reply": "正在执行内存清理..."},
    "cpu过高": {"tool": "process:list", "params_template": {"max": 20}, "type": "read", "reply": "正在查看占用 CPU 最高的进程..."},
    "内存不足": {"tool": "system:info", "params_template": {}, "type": "read", "reply": "正在检查内存使用情况..."},
    "磁盘空间不足": {"tool": "system:command", "params_template": {"command": "cmd /c wmic logicaldisk get size,freespace,caption"}, "type": "read", "reply": "正在检查磁盘空间..."},
    "清理": {"tool": "system:command", "params_template": {"command": "cmd /c dir %TEMP%"}, "type": "read", "reply": "正在扫描可清理的临时文件..."},
    "记事本": {"tool": "app:launch", "params_template": {"path": "notepad.exe"}, "type": "write", "reply": "正在打开记事本..."},
    "微信": {"tool": "app:launch", "params_template": {"path": "WeChat.exe"}, "type": "write", "reply": "正在打开微信..."},
    "qq": {"tool": "app:launch", "params_template": {"path": "QQ.exe"}, "type": "write", "reply": "正在打开QQ..."},
    "浏览器": {"tool": "app:launch", "params_template": {"path": "msedge.exe"}, "type": "write", "reply": "正在打开浏览器..."},
    "vscode": {"tool": "app:launch", "params_template": {"path": "Code.exe"}, "type": "write", "reply": "正在打开VSCode..."},
    "edge": {"tool": "app:launch", "params_template": {"path": "msedge.exe"}, "type": "write", "reply": "正在打开Edge浏览器..."},
    "word": {"tool": "app:launch", "params_template": {"path": "WINWORD.EXE"}, "type": "write", "reply": "正在打开Word..."},
    "搜索": {"tool": "app:launch", "params_template": {"path": "msedge.exe", "url": "https://www.baidu.com/s?wd={query}"}, "type": "write", "reply": "正在搜索..."},
    "生成": {"tool": "content:generate", "params_template": {"task": "{query}", "content_type": "word", "length": "中"}, "type": "write", "reply": "正在生成内容..."},
    "写文章": {"tool": "content:generate", "params_template": {"task": "{query}", "content_type": "word", "length": "中"}, "type": "write", "reply": "正在撰写文章..."},
    "写页面": {"tool": "content:generate", "params_template": {"task": "{query}", "content_type": "html", "length": "中"}, "type": "write", "reply": "正在生成页面..."},
    "卸载": {"tool": "store:uninstall", "params_template": {"package_id": "{query}"}, "type": "destructive", "reply": "正在通过应用商店卸载..."},
    "移除": {"tool": "store:uninstall", "params_template": {"package_id": "{query}"}, "type": "destructive", "reply": "正在通过应用商店移除..."},
    "安装": {"tool": "store:install", "params_template": {"package_id": "{query}"}, "type": "write", "reply": "正在通过应用商店安装..."},
}


def filter_valid_commands(commands: list[dict]) -> tuple[list[dict], list[str]]:
    """过滤命令，分离可执行和需手动的"""
    valid = []
    manual = []
    for c in commands:
        tool = c.get('tool', '')
        if tool in ALLOWED_TOOLS:
            valid.append(c)
        else:
            manual.append(f"手动操作：{c.get('reason', tool)}（工具 {tool} 不可用）")
    return valid, manual


def _extract_app_name_from_action(text: str, action_words: list[str]) -> str:
    """从动作指令中提取应用名称，如 '删除MongoDB应用' → 'MongoDB'"""
    import re
    result = text
    for word in action_words:
        result = result.replace(word, '')
    result = re.sub(r'\s+', ' ', result).strip(' ，。！？、')
    return result if result else text


def _build_simple_commands(intent: str, text: str) -> list[ActionCommand]:
    """根据本地快路径意图构建命令列表"""
    commands = []
    if intent == 'system_monitor':
        commands.append(ActionCommand(
            id=f"cmd_{uuid.uuid4().hex[:8]}_0",
            type="read", tool="system:info", params={},
            reason="获取系统整体状态", confidence=0.95,
        ))
        commands.append(ActionCommand(
            id=f"cmd_{uuid.uuid4().hex[:8]}_1",
            type="read", tool="process:top", params={"max": 10},
            reason="查看高占用进程", confidence=0.9,
        ))
    elif intent == 'system_optimize':
        commands.append(ActionCommand(
            id=f"cmd_{uuid.uuid4().hex[:8]}_0",
            type="read", tool="system:info", params={},
            reason="获取系统状态以评估优化方案", confidence=0.9,
        ))
        commands.append(ActionCommand(
            id=f"cmd_{uuid.uuid4().hex[:8]}_1",
            type="read", tool="process:top", params={"max": 10},
            reason="查看高占用进程", confidence=0.9,
        ))
    elif intent == 'store_action':
        normalized = text.lower()
        has_uninstall = any(k in normalized for k in ['卸载', '移除'])
        has_install = any(k in normalized for k in ['安装'])
        has_store_search = any(k in normalized for k in ['搜索应用', '查找应用', '应用商店'])
        
        if has_uninstall:
            app_name = _extract_app_name_from_action(text, ['删除', '卸载', '移除', '应用', '软件', '程序'])
            commands.append(ActionCommand(
                id=f"cmd_{uuid.uuid4().hex[:8]}_0",
                type="destructive", tool="store:uninstall",
                params={"package_id": app_name},
                reason=f"卸载应用: {app_name}", confidence=0.92,
            ))
        elif has_install:
            app_name = _extract_app_name_from_action(text, ['安装', '应用', '软件', '程序'])
            commands.append(ActionCommand(
                id=f"cmd_{uuid.uuid4().hex[:8]}_0",
                type="write", tool="store:install",
                params={"package_id": app_name, "app_name": app_name},
                reason=f"安装应用: {app_name}", confidence=0.92,
            ))
        elif has_store_search:
            import re as _re
            query = _re.sub(r'(搜索|查找|应用商店|应用|软件)', '', text).strip()
            commands.append(ActionCommand(
                id=f"cmd_{uuid.uuid4().hex[:8]}_0",
                type="read", tool="store:search",
                params={"query": query or text},
                reason=f"搜索应用: {query or text}", confidence=0.92,
            ))
        else:
            commands.append(ActionCommand(
                id=f"cmd_{uuid.uuid4().hex[:8]}_0",
                type="read", tool="store:search",
                params={"query": text},
                reason=f"搜索应用: {text}", confidence=0.85,
            ))
    elif intent == 'desktop_control':
        normalized = text.lower()
        has_uninstall = any(k in normalized for k in ['卸载', '移除'])
        has_install = any(k in normalized for k in ['安装'])
        has_store_search = any(k in normalized for k in ['搜索应用', '查找应用', '应用商店'])
        
        if has_uninstall:
            app_name = _extract_app_name_from_action(text, ['删除', '卸载', '移除', '应用'])
            commands.append(ActionCommand(
                id=f"cmd_{uuid.uuid4().hex[:8]}_0",
                type="destructive", tool="store:uninstall",
                params={"package_id": app_name},
                reason=f"卸载应用: {app_name}", confidence=0.92,
            ))
        elif has_install:
            app_name = _extract_app_name_from_action(text, ['安装'])
            commands.append(ActionCommand(
                id=f"cmd_{uuid.uuid4().hex[:8]}_0",
                type="write", tool="store:install",
                params={"package_id": app_name, "app_name": app_name},
                reason=f"安装应用: {app_name}", confidence=0.92,
            ))
        elif has_store_search:
            import re as _re
            query = _re.sub(r'(搜索|查找|应用商店|应用)', '', text).strip()
            commands.append(ActionCommand(
                id=f"cmd_{uuid.uuid4().hex[:8]}_0",
                type="read", tool="store:search",
                params={"query": query or text},
                reason=f"搜索应用: {query or text}", confidence=0.92,
            ))
        else:
            from app.api.voice import handle_app_launch_intent
            app_commands, _, handled = handle_app_launch_intent(text)
            if handled and app_commands:
                for i, c in enumerate(app_commands):
                    if isinstance(c, dict):
                        commands.append(ActionCommand(
                            id=f"cmd_{uuid.uuid4().hex[:8]}_{i}",
                            type=c.get("type", "write"),
                            tool=c.get("tool", "app:launch"),
                            params=c.get("params", {}),
                            reason=c.get("reason", "启动应用"),
                            confidence=c.get("confidence", 0.85),
                        ))
                    else:
                        commands.append(ActionCommand(
                            id=f"cmd_{uuid.uuid4().hex[:8]}_{i}",
                            type=getattr(c, 'type', 'write'),
                            tool=getattr(c, 'tool', 'app:launch'),
                            params=getattr(c, 'params', {}),
                            reason=getattr(c, 'reason', '启动应用'),
                            confidence=getattr(c, 'confidence', 0.85),
                        ))
    elif intent == 'search_only':
        import urllib.parse
        from app.services.intent_detector import SEARCH_KEYWORDS
        theme = text
        for kw in sorted(SEARCH_KEYWORDS, key=len, reverse=True):
            if kw in text:
                theme = text.replace(kw, '', 1).strip()
                break
        is_chinese = any('\u4e00' <= c <= '\u9fff' for c in theme)
        search_url = f"https://www.baidu.com/s?wd={urllib.parse.quote(theme)}" if is_chinese else f"https://www.google.com/search?q={urllib.parse.quote(theme)}"
        commands.append(ActionCommand(
            id=f"cmd_{uuid.uuid4().hex[:8]}_0",
            type="write", tool="app:launch",
            params={"path": "msedge.exe", "url": search_url},
            reason=f"搜索「{theme}」", confidence=0.92,
        ))
    return commands


def _build_simple_reply(intent: str, text: str) -> str:
    """根据本地快路径意图构建回复文本"""
    if intent == 'system_monitor':
        return "正在检查系统状态。"
    elif intent == 'system_optimize':
        return "正在分析系统优化方案。"
    elif intent == 'store_action':
        return f"正在通过应用商店处理: {text}"
    elif intent == 'desktop_control':
        return f"正在执行: {text}"
    elif intent == 'search_only':
        return "正在搜索。"
    return f"正在处理: {text}"


async def _auto_execute_commands(commands: list[ActionCommand]) -> tuple[list[ActionCommand], int]:
    """自动执行低风险命令，返回更新后的命令列表和执行数"""
    from app.services.store_manager import search_app, install_app, uninstall_app, list_installed
    
    STORE_API_BASE = "http://127.0.0.1:8000"
    executed_count = 0
    updated = []
    for cmd in commands:
        if cmd.tool not in AUTO_EXEC_SAFE_TOOLS:
            updated.append(cmd)
            continue
        if cmd.tool == 'system:command':
            cmd_str = cmd.params.get('command', '').lower()
            if any(p in cmd_str for p in DESTRUCTIVE_COMMAND_PATTERNS):
                print(f"[AUTO_EXEC] SKIP destructive: {cmd_str}")
                updated.append(cmd)
                continue
        
        if cmd.tool.startswith('store:'):
            try:
                if cmd.tool == 'store:search':
                    query = cmd.params.get('query', '')
                    result = await search_app(query)
                    cmd.executed = True
                    cmd.exec_result = {"success": result.success, "message": result.message, "data": result.data, "error": result.error}
                    executed_count += 1
                    print(f"[AUTO_EXEC] store:search OK: {result.message}")
                elif cmd.tool == 'store:list':
                    result = await list_installed()
                    cmd.executed = True
                    cmd.exec_result = {"success": result.success, "message": result.message, "data": result.data, "error": result.error}
                    executed_count += 1
                    print(f"[AUTO_EXEC] store:list OK: {result.message}")
                elif cmd.tool == 'store:install':
                    package_id = cmd.params.get('package_id', '')
                    app_name = cmd.params.get('app_name')
                    result = await install_app(package_id, app_name)
                    cmd.executed = True
                    cmd.exec_result = {"success": result.success, "message": result.message, "data": result.data, "error": result.error}
                    executed_count += 1
                    print(f"[AUTO_EXEC] store:install OK: {result.message}")
                elif cmd.tool == 'store:uninstall':
                    package_id = cmd.params.get('package_id', '')
                    result = await uninstall_app(package_id)
                    cmd.executed = True
                    cmd.exec_result = {"success": result.success, "message": result.message, "data": result.data, "error": result.error}
                    executed_count += 1
                    print(f"[AUTO_EXEC] store:uninstall OK: {result.message}")
            except Exception as e:
                print(f"[AUTO_EXEC] {cmd.tool} ERROR: {e}")
            updated.append(cmd)
            continue
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(DESKTOP_EXECUTOR_URL, json={"tool": cmd.tool, "params": cmd.params})
                if resp.status_code == 200:
                    result = resp.json()
                    cmd.executed = True
                    cmd.exec_result = result
                    executed_count += 1
                    print(f"[AUTO_EXEC] {cmd.tool} OK: {json.dumps(result, ensure_ascii=False)[:200]}")
                else:
                    print(f"[AUTO_EXEC] {cmd.tool} FAIL: HTTP {resp.status_code}")
        except Exception as e:
            print(f"[AUTO_EXEC] {cmd.tool} ERROR: {e}")
        updated.append(cmd)
    return updated, executed_count


@router.post("/command", response_model=AgentResponse)
async def handle_user_command(cmd: UserCommand):
    text = cmd.text.strip()
    auto_exec = cmd.auto_execute
    
    # ===== 第零层：本地快路径（简单单动作直接执行，无需 LLM）=====
    intent = detect_intent(text)
    if intent != 'llm_decompose':
        simple_commands = _build_simple_commands(intent, text)
        if simple_commands:
            if auto_exec:
                simple_commands, exec_count = await _auto_execute_commands(simple_commands)
                reply = _build_simple_reply(intent, text)
                if exec_count > 0:
                    reply += f"（已自动执行 {exec_count} 个操作）"
                return AgentResponse(
                    analysis=f"本地规则识别意图: {intent}",
                    commands=simple_commands,
                    reply_text=reply,
                    executed_count=exec_count,
                )
            return AgentResponse(
                analysis=f"本地规则识别意图: {intent}",
                commands=simple_commands,
                reply_text=_build_simple_reply(intent, text),
            )
    
    # ===== 第一层：LLM 结构化意图识别（优先）=====
    try:
        llm_result = await generate_structured(
            text,
            mode="command",
            system_context=cmd.context,
            voice_context={"source": "user-command", "locale": "zh-CN"},
        )
        
        parsed = llm_result.get("parsed")
        if parsed and isinstance(parsed, list) and len(parsed) > 0:
            action_commands = []
            for i, item in enumerate(parsed):
                if not isinstance(item, dict):
                    continue

                tool = item.get("tool", "")
                
                # 保险闸：用户没提清理/结束，禁止生成危险工具
                if tool in ("disk:cleanup", "temp:cleanup", "process:kill"):
                    user_text_lower = text.lower()
                    if not any(k in user_text_lower for k in ["卡", "慢", "清理", "优化", "结束", "杀", "删除", "卸载"]):
                        print(f"[FILTER] 用户未提清理，过滤掉 {tool}")
                        continue  # 跳过这个工具
                
                if tool not in ALLOWED_TOOLS:
                    continue
                if tool == "process:kill":
                    params = item.get("params", {})
                    if not params.get("pid") and not params.get("name"):
                        continue
                
                item_type = item.get("type", "write")
                if tool == "store:uninstall":
                    item_type = "destructive"
                elif tool == "store:install":
                    item_type = "write"

                action_commands.append(ActionCommand(
                    id=f"cmd_{uuid.uuid4().hex[:8]}_{i}",
                    type=item_type,
                    tool=tool,
                    params=item.get("params", {}),
                    reason=item.get("reason", f"用户请求: {text}"),
                    confidence=item.get("confidence", 0.85),
                    reasoning=item.get("reasoning", ""),
                ))
            
            if action_commands:
                if auto_exec:
                    action_commands, exec_count = await _auto_execute_commands(action_commands)
                    reply = f"已为您规划 {len(action_commands)} 个操作"
                    if exec_count > 0:
                        reply += f"，已自动执行 {exec_count} 个"
                    return AgentResponse(
                        analysis=f"AI 分析用户意图: {text}",
                        commands=action_commands,
                        reply_text=reply,
                        executed_count=exec_count,
                    )
                return AgentResponse(
                    analysis=f"AI 分析用户意图: {text}",
                    commands=action_commands,
                    reply_text=f"已为您规划 {len(action_commands)} 个操作，请确认执行"
                )
    except Exception as e:
        print(f"[AGENT LLM ERROR] {traceback.format_exc()}")
    
    # ===== 第二层：旧版 parse_user_command（兼容）=====
    try:
        analysis, commands, reply_text = parse_user_command(text)
        action_commands = []
        for parsed_cmd in (commands if isinstance(commands, list) else []):
            if hasattr(parsed_cmd, 'model_dump'):
                d = parsed_cmd.model_dump()
            elif isinstance(parsed_cmd, dict):
                d = parsed_cmd
            else:
                d = {'tool': getattr(parsed_cmd, 'tool', ''),
                     'type': getattr(parsed_cmd, 'type', 'read'),
                     'params': getattr(parsed_cmd, 'params', {}),
                     'reason': getattr(parsed_cmd, 'reason', ''),
                     'confidence': getattr(parsed_cmd, 'confidence', 0.8)}
            action_commands.append(ActionCommand(
                id=d.get('id', f"cmd_{uuid.uuid4().hex[:8]}"),
                type=d.get('type', 'read'),
                tool=d.get('tool', ''),
                params=d.get('params', {}),
                reason=d.get('reason', f"用户请求: {text}"),
                confidence=d.get('confidence', 0.8),
                reasoning=d.get('reasoning', ''),
            ))
        if action_commands:
            if auto_exec:
                action_commands, exec_count = await _auto_execute_commands(action_commands)
                reply = reply_text or f"已收到指令：{text}"
                if exec_count > 0:
                    reply += f"（已自动执行 {exec_count} 个操作）"
                return AgentResponse(
                    analysis=analysis,
                    commands=action_commands,
                    reply_text=reply,
                    executed_count=exec_count,
                )
            return AgentResponse(
                analysis=analysis,
                commands=action_commands,
                reply_text=reply_text or f"已收到指令：{text}"
            )
    except Exception:
        pass
    
    # ===== 第三层：关键词降级兜底 =====
    matched_intent = None
    matched_key = None
    for keyword, tool_config in INTENT_TOOL_MAP.items():
        if keyword in text.lower():
            matched_intent = tool_config
            matched_key = keyword
            break
    
    if not matched_intent:
        supported = "、".join(list(INTENT_TOOL_MAP.keys())[:15]) + "等"
        return AgentResponse(
            analysis=f"用户输入: {text}，无法识别意图",
            commands=[],
            reply_text=f"我理解你想：{text}，暂时还不支持。目前支持：{supported}"
        )
    
    # 处理搜索/生成关键词中的 {query} 替换
    params = dict(matched_intent["params_template"])
    query = text.lower()
    for key in matched_intent["params_template"].keys():
        if isinstance(params[key], str) and "{query}" in params[key]:
            clean_query = query.replace(matched_key, "").strip(" ，。！？")
            if not clean_query:
                clean_query = "通用"
            params[key] = params[key].replace("{query}", clean_query)
    
    action = ActionCommand(
        id=f"cmd_{uuid.uuid4().hex[:8]}",
        type=matched_intent["type"],
        tool=matched_intent["tool"],
        params=params,
        reason=f"用户请求: {text}",
        confidence=0.95,
        reasoning=f"关键词匹配识别到意图 [{matched_key}]",
    )
    if auto_exec:
        [action], exec_count = await _auto_execute_commands([action])
        reply = matched_intent["reply"]
        if exec_count > 0:
            reply += f"（已自动执行）"
        return AgentResponse(
            analysis=f"关键词匹配识别到意图 [{matched_key}]: {text}",
            commands=[action],
            reply_text=reply,
            executed_count=exec_count,
        )
    return AgentResponse(
        analysis=f"关键词匹配识别到意图 [{matched_key}]: {text}",
        commands=[action],
        reply_text=matched_intent["reply"]
    )


@router.post("/solve-problems", response_model=AgentResponse)
async def solve_problems(cmd: UserCommand):
    text = cmd.text.strip()
    
    # 初始化默认值，避免变量未定义错误
    mem = {}
    cpu = {}
    disk = {}
    system_info = ""
    
    if cmd.context:
        mem = cmd.context.get("memory", {})
        cpu = cmd.context.get("cpu", {})
        disk = cmd.context.get("disk", {})
        system_info = f"当前系统状态：内存 {mem.get('usagePercent', 'N/A')}% | CPU {cpu.get('usagePercent', 'N/A')}% | 磁盘 {disk.get('usagePercent', 'N/A')}%"
    
    # 构建严格的白名单提示
    allowed_tools_desc = "\n".join([
        f"- {t}: {TOOL_DESCRIPTIONS.get(t, '系统工具')}" 
        for t in sorted(ALLOWED_TOOLS)
    ])
    
    cpu_usage = cpu.get('usagePercent', 0) if cpu else 0
    mem_usage = mem.get('usagePercent', 0) if mem else 0
    disk_usage = disk.get('usagePercent', 0) if disk else 0
    
    cpu_status = "处于高负载" if cpu_usage >= 80 else "运行正常"
    
    prompt = f"""你是桌面运维专家。用户问题：{text}
当前系统状态：内存 {mem_usage}% | CPU {cpu_usage}% | 磁盘 {disk_usage}%

【强制规则】
1. 必须引用上面的真实系统数据（CPU {cpu_usage}%, 内存 {mem_usage}% 等），禁止泛泛而谈
2. 如果 CPU < 50%，明确说"CPU 正常，无需处置"
3. 如果 50% <= CPU < 80%，给出具体进程优化建议（必须调用 process:top 获取真实进程）
4. 如果 CPU >= 80%，才考虑结束进程，且必须指定真实 PID
5. 禁止输出"关闭不必要的后台程序""检查病毒"等无法落地的建议
6. 每个方案的 steps 必须是可执行的具体动作，不能是建议性文字

可用工具（严格限制，只能使用这些）：
{allowed_tools_desc}

输出格式（纯 JSON 数组）：
[
  {{
    "id": "sol_1",
    "title": "查看 CPU 详细状态",
    "description": "当前 CPU {cpu_usage}%，{cpu_status}",
    "steps": ["执行 system:info 获取详细 CPU 数据", "执行 process:top 查看占用最高的进程"],
    "risk": "low",
    "auto_executable": true,
    "commands": [
      {{"tool": "system:info", "type": "read", "params": {{}}, "reason": "获取 CPU 详细状态"}},
      {{"tool": "process:top", "type": "read", "params": {{"max": 5}}, "reason": "查看高占用进程"}}
    ],
    "manual_steps": []
  }}
]"""

    try:
        result = await generate_structured(
            prompt,
            mode="general",
            system_context=cmd.context,
            voice_context={"source": "user-problem", "locale": "zh-CN"},
        )
        
        solutions = []
        parsed = result.get("parsed")
        
        if parsed and isinstance(parsed, list):
            for item in parsed:
                sol_id = item.get("id", f"sol_{uuid.uuid4().hex[:8]}")
                raw_commands = item.get("commands", [])
                
                # 过滤有效命令
                valid_cmds, manual_steps = filter_valid_commands(raw_commands)
                
                commands_list = [
                    ActionCommand(
                        id=f"{sol_id}_cmd_{i}",
                        tool=c.get("tool", "notify"),
                        type=c.get("type", "read"),
                        params=c.get("params", {}),
                        reason=c.get("reason", item.get("title", "")),
                        confidence=0.85
                    )
                    for i, c in enumerate(valid_cmds)
                ]
                
                # 合并 manual_steps
                all_manual = item.get("manual_steps", []) + manual_steps
                
                solutions.append(SolutionMethod(
                    id=sol_id,
                    title=item.get("title", "未命名方案"),
                    description=item.get("description", ""),
                    steps=item.get("steps", []),
                    commands=commands_list,
                    risk=item.get("risk", "medium"),
                    auto_executable=item.get("auto_executable", False) and len(commands_list) > 0,
                    manual_steps=all_manual
                ))
        
        # 如果没解析到，降级为关键词匹配
        if not solutions:
            analysis, parsed_commands, reply_text = parse_user_command(text)
            action_commands = [
                ActionCommand(
                    id=f"cmd_{uuid.uuid4().hex[:8]}",
                    type=c.get('type', 'read'),
                    tool=c.get('tool', ''),
                    params=c.get('params', {}),
                    reason=c.get('reason', text),
                    confidence=c.get('confidence', 0.8)
                ) for c in (parsed_commands if isinstance(parsed_commands, list) else [])
            ]
            return AgentResponse(
                analysis=f"LLM 未返回有效 JSON，降级为关键词匹配：{text}",
                solutions=[],
                commands=action_commands,
                reply_text=reply_text or f"找到 {len(action_commands)} 个可执行操作"
            )
        
        all_commands = []
        for sol in solutions:
            all_commands.extend(sol.commands)
        
        return AgentResponse(
            analysis=f"AI 分析问题：{text}",
            solutions=solutions,
            commands=all_commands,
            reply_text=f"找到 {len(solutions)} 个解决方案，请选择一个执行"
        )
        
    except Exception as e:
        return AgentResponse(
            analysis=f"分析用户问题：{text}",
            solutions=[],
            commands=[],
            reply_text=f"抱歉，分析问题时出现错误：{str(e)}"
        )