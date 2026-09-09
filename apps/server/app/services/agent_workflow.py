from __future__ import annotations

import json
from typing import Any

from app.api.automation import Command


AGENT_SYSTEM_PROMPT = """你是 AI Desktop Agent，一个真正的桌面运维专家。

你的工作流程：
1. 观察：分析用户请求和系统数据
2. 思考：判断问题原因，决定是否需要搜索外部知识
3. 行动：调用工具收集更多信息或直接解决问题
4. 验证：检查执行结果，确认问题是否解决

核心能力：
- 你能判断进程是否危险（如病毒、挖矿程序、流氓软件）
- 你能判断哪些文件可以安全删除
- 你能根据系统状态给出具体、可操作的解决方案
- 你不会只是罗列数据，而是给出结论和行动

判断规则（内置知识）：
- 高CPU进程：如果是 chrome.exe/node.exe/electron.exe 等正常程序，建议关闭标签页而非结束进程
- 如果是 svchost.exe/system 等系统进程，绝对不能结束
- 如果是未知程序或名称可疑（如 xmrig/miner/随机字符），可能是挖矿病毒，建议结束
- 内存泄漏：如果某个进程内存持续增长且非必要，建议重启该程序
- 磁盘清理：Windows 更新缓存、临时文件、回收站可安全清理；用户文档不可删

输出格式（严格JSON）：
{
  "analysis": "一句话诊断结论",
  "thinking": "分析过程，包含对进程/文件的具体判断",
  "needs_search": false,
  "search_query": "",
  "actions": [
    {"tool": "...", "type": "...", "params": {}, "reason": "为什么做这个操作"}
  ],
  "advice": "给用户的最终建议，包含具体数值和结果预期",
  "risk_warning": "如果有风险操作，提醒用户"
}
"""


def summarize_system_context(system_context: dict[str, Any] | None) -> str:
    """将系统上下文转换为简洁摘要"""
    if not system_context:
        return "无可用系统数据"
    
    parts = []
    if "hostname" in system_context:
        parts.append(f"主机: {system_context['hostname']}")
    if "cpu" in system_context:
        parts.append(f"CPU: {system_context['cpu']}")
    if "memory" in system_context:
        parts.append(f"内存: {system_context['memory']}")
    if "disk" in system_context:
        parts.append(f"磁盘: {system_context['disk']}")
    
    return "; ".join(parts) if parts else "系统数据不足"


async def run_agent(
    user_request: str,
    system_context: dict[str, Any] | None,
    execution_history: list[dict] | None = None,
    llm_callable=None,  # 传入 LLM 调用函数
) -> dict[str, Any]:
    """运行真正的 Agent 工作流"""
    
    system_summary = summarize_system_context(system_context)
    history_str = json.dumps(execution_history or [], ensure_ascii=False, indent=2)
    
    # 构建 prompt
    prompt = f"""用户请求: {user_request}
系统监控摘要: {system_summary}
已执行过的操作: {history_str}

请作为运维专家分析这个问题。不要只是收集数据，要给出诊断结论和具体解决方案。

如果涉及进程分析，请根据进程名判断是否正常：
- 正常进程（浏览器/开发工具）：chrome.exe, firefox.exe, msedge.exe, node.exe, code.exe, cursor.exe, python.exe, electron.exe
- 系统进程（绝对不能结束）：svchost.exe, csrss.exe, services.exe, lsass.exe, wininit.exe, smss.exe, winlogon.exe
- 可疑进程（可能是病毒）：名称是随机字符、包含 miner/xmrig/bitcoin/coin、路径在临时目录

如果涉及磁盘清理，请判断：
- 可安全删除：*.tmp, *.temp, *.log, 回收站, Windows更新缓存
- 不可删除：用户文档、程序安装目录、系统文件

请输出JSON，包含 analysis/thinking/actions/advice。
"""
    
    # 调用 LLM
    if llm_callable:
        try:
            result = await llm_callable(prompt)
            if result and isinstance(result, dict):
                parsed = result
            else:
                parsed = _parse_llm_response(result)
        except Exception as e:
            parsed = None
    else:
        # 降级：返回基本诊断
        return _get_fallback_result(user_request)
    
    if not parsed or not isinstance(parsed, dict):
        return _get_fallback_result(user_request)
    
    # 转换 actions 为 Command 对象
    actions = []
    for a in parsed.get("actions", []):
        if isinstance(a, dict):
            actions.append(Command(
                tool=a.get("tool", "notify"),
                type=a.get("type", "read"),
                params=a.get("params", {}),
                reason=a.get("reason", ""),
                confidence=0.85,
                risk="high" if a.get("type") == "destructive" else "low",
                require_confirmation=a.get("type") == "destructive",
            ))
    
    return {
        "analysis": parsed.get("analysis", ""),
        "thinking": parsed.get("thinking", ""),
        "needs_search": parsed.get("needs_search", False),
        "search_query": parsed.get("search_query", ""),
        "actions": actions,
        "advice": parsed.get("advice", ""),
        "risk_warning": parsed.get("risk_warning", ""),
    }


def _parse_llm_response(response: str | dict) -> dict | None:
    """解析 LLM 返回的 JSON 响应"""
    if isinstance(response, dict):
        return response

    if isinstance(response, str):
        # 尝试直接解析
        try:
            return json.loads(response)
        except (json.JSONDecodeError, TypeError):
            pass

        # 尝试提取 ```json ... ``` 代码块
        import re
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except (json.JSONDecodeError, TypeError):
                pass

        # 尝试提取第一个完整的 JSON 对象（支持嵌套花括号）
        start = response.find('{')
        while start != -1:
            depth = 0
            end = -1
            for i in range(start, len(response)):
                if response[i] == '{':
                    depth += 1
                elif response[i] == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end != -1:
                try:
                    return json.loads(response[start:end])
                except (json.JSONDecodeError, TypeError):
                    pass
            start = response.find('{', start + 1)
    return None


def _get_fallback_result(user_request: str) -> dict[str, Any]:
    """降级结果：基于关键词生成基本诊断"""
    request_lower = user_request.lower()
    
    # 基于关键词生成 actions
    actions = []
    
    if any(k in request_lower for k in ['cpu', '处理器', '卡顿', '卡']):
        actions.append(Command(
            tool="process:top",
            type="read",
            params={"max": 10},
            reason="查看 CPU 占用最高的进程",
            confidence=0.9,
            risk="low",
        ))
        actions.append(Command(
            tool="system:info",
            type="read",
            params={},
            reason="获取系统基本信息",
            confidence=0.9,
            risk="low",
        ))
    
    if any(k in request_lower for k in ['内存', 'memory', 'memory']):
        actions.append(Command(
            tool="process:top",
            type="read",
            params={"max": 10},
            reason="查看内存占用最高的进程",
            confidence=0.9,
            risk="low",
        ))
    
    if any(k in request_lower for k in ['磁盘', 'c盘', 'c盘', '空间', '硬盘']):
        actions.append(Command(
            tool="disk:list",
            type="read",
            params={},
            reason="获取所有磁盘的使用情况",
            confidence=0.9,
            risk="low",
        ))
        actions.append(Command(
            tool="temp:scan",
            type="read",
            params={"max": 100},
            reason="扫描可清理的临时文件",
            confidence=0.85,
            risk="low",
        ))
    
    if any(k in request_lower for k in ['清理', 'clean', '垃圾']):
        actions.append(Command(
            tool="temp:scan",
            type="read",
            params={"max": 100},
            reason="扫描临时文件",
            confidence=0.9,
            risk="low",
        ))
    
    if not actions:
        actions.append(Command(
            tool="system:info",
            type="read",
            params={},
            reason="获取系统整体状态",
            confidence=0.9,
            risk="low",
        ))
    
    return {
        "analysis": "正在分析您的请求...",
        "thinking": "基于您的请求关键词，生成诊断命令收集系统信息。",
        "needs_search": False,
        "search_query": "",
        "actions": actions,
        "advice": "已生成诊断命令，请执行后查看详细分析。",
        "risk_warning": "",
    }


async def search_knowledge(query: str) -> str:
    """搜索本地知识库"""
    knowledge_base = {
        "chrome 高 cpu": """Chrome 高CPU排查：
1. 按 Shift+Esc 打开 Chrome 任务管理器，找出具体标签页
2. 关闭不必要的标签页，特别是视频网站、在线工具
3. 禁用不用的扩展：chrome://extensions/
4. 如果某个标签页持续高CPU，可能是网页挖矿脚本，关闭它
5. 终极方案：重启 Chrome""",
        
        "内存不足": """内存不足解决方案：
1. 结束不必要的程序
2. 检查是否有内存泄漏的程序
3. 增加虚拟内存
4. 重启释放内存
5. 考虑增加物理内存""",
        
        "c盘清理": """C盘清理方案：
1. 运行磁盘清理(cleanmgr)
2. 删除临时文件(%temp%)
3. 清空回收站
4. 清理Windows更新缓存
5. 关闭休眠释放hiberfil.sys""",
        
        "系统卡顿": """系统卡顿排查：
1. 检查CPU/内存占用
2. 查看磁盘是否100%占用
3. 检查是否有Windows更新在后台
4. 扫描病毒
5. 检查启动项""",
    }
    
    query_lower = query.lower()
    for key, value in knowledge_base.items():
        if key in query_lower:
            return value
    
    return f"关于 '{query}' 的知识：建议搜索具体解决方案，或提供更多系统信息以便分析。"