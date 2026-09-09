from __future__ import annotations

import json
import re
from typing import Any

from app.services.llm.context_builder import summarize_system_context, summarize_voice_context
from app.services.llm.provider import LLMProviderError, provider
from app.utils.response_cleaner import LEAKAGE_FALLBACK_MESSAGE, cleaner


GENERATOR_SYSTEM_PROMPT = """
你是 Windows 桌面助手，只能使用以下工具完成任务。

## 可用工具（禁止生成不在此列表的工具）
- system:info / process:top / process:list / disk:list / temp:scan
- disk:cleanup / disk:cleanup_advanced / temp:cleanup / system:recycle / system:browser-cache / system:cleanmgr / system:hibernate / system:wechat-cache
- process:kill (危险，最多2个，用于关闭/结束应用程序)
- app:launch (path必须是绝对路径或常见应用名如 notepad.exe/WeChat.exe/Code.exe，浏览器搜索用url参数)
- ide:launch (ide=vscode/cursor, action=create_project/open_file, files=[{path,template}], project_name=可选, auto_preview=布尔值)
- content:generate (生成文章/代码/文档/网页，参数: task/content_type/theme/style/length/output_path/auto_open)
- browser:search (浏览器搜索，参数: query/browser)
- clipboard:write / notify / network:request
- store:search (搜索应用商店，参数: query)
- store:install (安装应用，参数: package_id, app_name=可选)
- store:uninstall (卸载应用，参数: package_id)
- store:list (列出已安装应用，参数: 无)

## 关闭应用规则（重要！）
- "关闭XX"/"关掉XX"/"退出XX"/"结束XX" → process:kill，params填 {"name": "进程名.exe"}
- 常见进程名映射：百度网盘=BaiduNetdisk.exe, 微信=WeChat.exe, QQ=QQ.exe, Chrome=chrome.exe, Edge=msedge.exe, VSCode=Code.exe, Word=WINWORD.EXE, MongoDB=mongod.exe
- 绝对禁止关闭：explorer.exe, svchost.exe, csrss.exe, dwm.exe 等系统进程
- "关闭XX"绝不是搜索意图！不要把"关闭百度网盘"理解成搜索！

## 删除/卸载应用规则（重要！优先使用 store 工具！）
- "删除XX应用"/"卸载XX"/"移除XX" → store:uninstall，params填 {"package_id": "XX"}
- "安装XX" → store:install，params填 {"package_id": "XX", "app_name": "XX"}
- "搜索应用XX" → store:search，params填 {"query": "XX"}
- store 工具通过 winget 包管理器操作，有输入校验和超时保护，比直接用 system:command 更安全
- 示例："删除MongoDB应用" → {"tool":"store:uninstall","params":{"package_id":"MongoDB"}}
- 示例："安装VSCode" → {"tool":"store:install","params":{"package_id":"Microsoft.VisualStudioCode","app_name":"VS Code"}}

## 任务类型区分（严格规则）
- "打开VSCode + 写代码" → ide:launch（不是 app:launch）
- "打开浏览器搜索" → app:launch（带 url 参数）或 browser:search
- "写文章/生成页面"（不指定IDE）→ content:generate
- "打开记事本写XXX" → app:launch(notepad) + content:generate
- "关闭/退出/结束 XX" → process:kill（不是搜索！）

## 复合指令拆分规则（必须遵守）
如果用户说多个动作，必须拆成多个独立任务：
- "打开A和B" → 两个 app:launch 任务
- "打开记事本写XXX" → app:launch + content:generate
- "打开Word写XXX" → 只用 content:generate（auto_open=true会自动启动Word打开文件，不要再单独app:launch Word，否则会多开两个Word实例）
- "搜索XX然后写文章" → app:launch(带搜索url) + content:generate
- "打开VSCode写登录页然后浏览器预览" → ide:launch(vscode) + app:launch(浏览器预览)

## 场景匹配（严格按关键词）
- "打开/启动/运行" → app:launch
- "打开VSCode/IDE + 写/创建" → ide:launch
- "搜索/查/找" → app:launch(path=浏览器, url=搜索地址)
- "写/生成/创建/撰写" + 文档/文章/代码/页面 → content:generate
- "卡/慢/清理/优化" → system:info + disk:cleanup
- 其他无关请求 → 拒绝，不生成任务

## 安全规则
- 禁止kill: explorer.exe, csrss.exe, smss.exe, services.exe, lsass.exe, winlogon.exe, dwm.exe
- app:launch 的 path 可以是常见应用名（notepad.exe, WeChat.exe, Code.exe, msedge.exe）
- 单次最多6个任务，process:kill最多2个

## 输出格式（严格JSON数组）
不要任何解释文字，不要markdown代码块，直接输出：
[{"tool":"app:launch","params":{"path":"..."},"reason":"...","confidence":0.95,"reasoning":"...","dangerous":false,"requires_confirmation":false}]

## 示例（必须学习）
用户: "打开记事本写这是测试"
输出: [{"tool":"app:launch","params":{"path":"notepad.exe"},"reason":"打开记事本","confidence":0.95,"reasoning":"用户要打开记事本","dangerous":false,"requires_confirmation":false},{"tool":"content:generate","params":{"task":"这是测试","content_type":"document","theme":"测试","length":"短"},"reason":"生成文本内容","confidence":0.9,"reasoning":"用户要写入测试内容","dangerous":false,"requires_confirmation":false}]

用户: "打开微信和QQ"
输出: [{"tool":"app:launch","params":{"path":"WeChat.exe"},"reason":"打开微信","confidence":0.95,"reasoning":"用户要打开微信","dangerous":false,"requires_confirmation":false},{"tool":"app:launch","params":{"path":"QQ.exe"},"reason":"打开QQ","confidence":0.95,"reasoning":"用户要打开QQ","dangerous":false,"requires_confirmation":false}]

用户: "搜索AI应用然后写篇文章"
输出: [{"tool":"app:launch","params":{"path":"msedge.exe","url":"https://www.baidu.com/s?wd=AI%E5%BA%94%E7%94%A8"},"reason":"搜索AI应用资料","confidence":0.95,"reasoning":"用户要搜索AI应用","dangerous":false,"requires_confirmation":false},{"tool":"content:generate","params":{"task":"关于AI应用的文章","content_type":"word","theme":"AI应用","length":"中"},"reason":"生成文章","confidence":0.9,"reasoning":"用户要写关于AI应用的文章","dangerous":false,"requires_confirmation":false}]

用户: "打开VSCode写个登录页面"
输出: [{"tool":"ide:launch","params":{"ide":"vscode","action":"create_project","project_name":"login-page","files":[{"path":"index.html","template":"modern_login"}],"auto_preview":false},"reason":"打开VSCode创建登录页面","confidence":0.92,"reasoning":"用户明确指定VSCode创建页面，属于编码创建意图","dangerous":false,"requires_confirmation":false}]

用户: "电脑很卡"
输出: [{"tool":"system:info","params":{},"reason":"检查系统状态","confidence":0.95,"reasoning":"用户反映电脑卡顿","dangerous":false,"requires_confirmation":false},{"tool":"process:top","params":{"max":10},"reason":"查看高占用进程","confidence":0.9,"reasoning":"需要查看高占用进程","dangerous":false,"requires_confirmation":false},{"tool":"disk:cleanup","params":{},"reason":"清理临时文件","confidence":0.85,"reasoning":"用户明确说卡，允许清理","dangerous":false,"requires_confirmation":false}]

用户: "删除MongoDB应用"
输出: [{"tool":"store:uninstall","params":{"package_id":"MongoDB"},"reason":"卸载MongoDB应用","confidence":0.92,"reasoning":"用户要删除MongoDB应用，使用store:uninstall通过winget安全卸载","dangerous":true,"requires_confirmation":true}]

用户: "卸载Chrome"
输出: [{"tool":"store:uninstall","params":{"package_id":"Google Chrome"},"reason":"卸载Chrome","confidence":0.92,"reasoning":"用户要卸载Chrome浏览器","dangerous":true,"requires_confirmation":true}]

用户: "安装VSCode"
输出: [{"tool":"store:install","params":{"package_id":"Microsoft.VisualStudioCode","app_name":"VS Code"},"reason":"安装VSCode","confidence":0.92,"reasoning":"用户要安装VSCode","dangerous":false,"requires_confirmation":true}]
""".strip()


FALLBACK_TEXT_MAP: dict[str, str] = {
    "LLMRateLimitError": "服务繁忙，请稍后再试。",
    "LLMContextTooLongError": "对话过长，已自动清理历史。",
    "LLMModelDisabledError": "当前模型不可用，已切换备用方案。",
    "LLMUpstreamServerError": "服务端异常，请检查网络后重试。",
    "LLMProviderError": "暂时无法处理，请稍后再试。",
    "UnicodeEncodeError": "编码异常，请稍后再试。",
    "LLMProviderNotConfigured": "当前服务未启用，请稍后再试。",
    "default": "暂时无法处理，请稍后再试。",
}


def _safe_fallback_reply(reason: str) -> str:
    cleaned = cleaner.clean(FALLBACK_TEXT_MAP.get(reason, FALLBACK_TEXT_MAP["default"]))
    return cleaned or LEAKAGE_FALLBACK_MESSAGE


def _build_generation_prompt(
    *,
    message: str,
    mode: str,
    system_summary: str,
    voice_summary: str,
) -> str:
    return (
        f"Agent 模式: {mode}\n"
        f"当前用户消息: {message}\n"
        f"系统监控摘要: {system_summary}\n"
        f"语音上下文摘要: {voice_summary}\n"
        "请生成最终回复，要求：\n"
        "- 1句结论 + 关键数据 + 已执行/待确认动作\n"
        "- 不超过3句话，适合TTS播报\n"
        "- 不要输出步骤列表、脚本、PowerShell命令\n"
        "- 有风险操作时简短询问，不要长篇建议\n"
    )


def _build_rewrite_prompt(
    *,
    message: str,
    draft: str,
    feedback: str,
    mode: str,
    system_summary: str,
    voice_summary: str,
) -> str:
    return (
        f"Agent 模式: {mode}\n"
        f"当前用户消息: {message}\n"
        f"待改写草稿: {draft}\n"
        f"内部改写要求（不要在最终回答中显式提及）: {feedback}\n"
        f"系统监控摘要: {system_summary}\n"
        f"语音上下文摘要: {voice_summary}\n"
        "请输出改写后的最终回答，保持结构化、简洁、可执行。\n"
        '禁止输出"审核意见""内部要求""系统提示""provider 错误"等字样。'
    )


async def generate(
    message: str,
    mode: str = "default",
    *,
    system_context: dict[str, Any] | None = None,
    voice_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sanitized_message = cleaner.sanitize_user_input(message)
    system_summary = summarize_system_context(system_context)
    voice_summary = summarize_voice_context(voice_context)
    user_prompt = _build_generation_prompt(
        message=sanitized_message or "请基于当前请求给出简洁回答",
        mode=mode,
        system_summary=system_summary,
        voice_summary=voice_summary,
    )

    if provider.enabled:
        try:
            response = await provider.chat(
                system_prompt=GENERATOR_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.2,
            )
            cleaned_response = cleaner.clean(response)
            used_fallback = cleaned_response == LEAKAGE_FALLBACK_MESSAGE
            return {
                "content": cleaned_response,
                "used_fallback": used_fallback,
                "fallback_reason": "ResponseLeakageDetected" if used_fallback else None,
            }
        except LLMProviderError as exc:
            fallback_reason = exc.__class__.__name__
    else:
        fallback_reason = "LLMProviderNotConfigured"

    return {
        "content": _safe_fallback_reply(fallback_reason),
        "used_fallback": True,
        "fallback_reason": fallback_reason,
        "tts_enabled": False,
        "tts_summary": "",
        "enter_history": False,
    }


async def rewrite(
    message: str,
    draft: str,
    feedback: str,
    mode: str = "default",
    *,
    system_context: dict[str, Any] | None = None,
    voice_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sanitized_message = cleaner.sanitize_user_input(message)
    safe_draft = cleaner.clean(draft)
    safe_feedback = cleaner.clean(feedback)
    system_summary = summarize_system_context(system_context)
    voice_summary = summarize_voice_context(voice_context)
    user_prompt = _build_rewrite_prompt(
        message=sanitized_message or "请输出简洁安全的最终回答",
        draft=safe_draft,
        feedback=safe_feedback,
        mode=mode,
        system_summary=system_summary,
        voice_summary=voice_summary,
    )

    if provider.enabled:
        try:
            response = await provider.chat(
                system_prompt=GENERATOR_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.15,
            )
            cleaned_response = cleaner.clean(response)
            used_fallback = cleaned_response == LEAKAGE_FALLBACK_MESSAGE
            return {
                "content": cleaned_response,
                "used_fallback": used_fallback,
                "fallback_reason": "ResponseLeakageDetected" if used_fallback else None,
            }
        except LLMProviderError as exc:
            fallback_reason = exc.__class__.__name__
    else:
        fallback_reason = "LLMProviderNotConfigured"

    return {
        "content": _safe_fallback_reply(fallback_reason),
        "used_fallback": True,
        "fallback_reason": fallback_reason,
        "tts_enabled": False,
        "tts_summary": "",
        "enter_history": False,
    }


# ===== 新增：支持工具调用的生成 =====

async def generate_with_tools(
    message: str,
    mode: str = "default",
    *,
    system_context: dict[str, Any] | None = None,
    voice_context: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    history_messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    支持 function calling 的生成。
    返回: {content, tool_calls, used_fallback, fallback_reason}
    """
    sanitized_message = cleaner.sanitize_user_input(message)
    system_summary = summarize_system_context(system_context)
    voice_summary = summarize_voice_context(voice_context)

    # 构建 messages 数组
    messages: list[dict[str, Any]] = []
    if history_messages:
        for h in history_messages:
            msg: dict[str, Any] = {
                "role": h["role"],
                "content": h.get("content", ""),
            }
            if h.get("tool_calls"):
                msg["tool_calls"] = h["tool_calls"]
            if h.get("tool_call_id"):
                msg["tool_call_id"] = h["tool_call_id"]
            messages.append(msg)

    # 系统 prompt + 用户请求
    user_prompt = (
        f"Agent 模式: {mode}\n"
        f"当前用户消息: {sanitized_message or '请基于当前请求给出简洁回答'}\n"
        f"系统监控摘要: {system_summary}\n"
        f"语音上下文摘要: {voice_summary}\n"
    )
    messages.append({"role": "user", "content": user_prompt})

    if not provider.enabled:
        return {
            "content": _safe_fallback_reply("LLMProviderNotConfigured"),
            "tool_calls": None,
            "used_fallback": True,
            "fallback_reason": "LLMProviderNotConfigured",
        }

    try:
        response_msg = await provider.chat_with_tools(
            messages=messages,
            tools=tools or [],
            temperature=0.2,
        )

        content = response_msg.get("content", "") or ""
        tool_calls = response_msg.get("tool_calls")

        cleaned = cleaner.clean(content)
        used_fallback = cleaned == LEAKAGE_FALLBACK_MESSAGE

        return {
            "content": cleaned,
            "tool_calls": tool_calls,
            "used_fallback": used_fallback,
            "fallback_reason": "ResponseLeakageDetected" if used_fallback else None,
        }
    except LLMProviderError as exc:
        return {
            "content": _safe_fallback_reply(exc.__class__.__name__),
            "tool_calls": None,
            "used_fallback": True,
            "fallback_reason": exc.__class__.__name__,
        }


# ===== 结构化 JSON 生成（保留兼容） =====

STRUCTURED_SYSTEM_PROMPT = """
你是 Windows 桌面助手，只输出纯 JSON 数组，不要任何其他文字。

## 核心分解原则
1. **逐动作分解**：用户说的每个动作都要生成对应的任务，不能遗漏
2. **动作识别**：识别文本中的所有动词和动作词（打开、写、生成、搜索、预览、查看、创建、启动、运行、结束、清理等）
3. **连接词拆分**："然后"、"再"、"并"、"接着"、"之后"、"同时" 表示多个动作的串联
4. **隐含动作补全**："浏览器预览" 隐含 "打开浏览器"，"写登录页面然后预览" 隐含 "打开浏览器预览"

## 任务类型定义

| 类型 | 触发条件 | 示例 |
|------|---------|------|
| app:launch | 用户要"打开/启动/运行"某个本地应用 | "打开微信"、"启动计算器" |
| ide:launch | 用户要打开代码编辑器并创建项目/文件 | "打开VSCode写个登录页面" |
| content:generate | 用户要"生成/创建/写/制作/设计"某个内容 | "写篇文章"、"生成HTML页面" |
| system:info | 用户询问系统状态 | "查看系统状态"、"CPU占用多少" |
| process:kill | 用户要结束进程 | "结束chrome" |
| notify | 发送桌面通知 | "提醒我" |
| clipboard:write | 写入剪贴板 | "复制到剪贴板" |

## 关键区分规则
1. **"打开VSCode + 写代码"** → `ide:launch`（编码创建意图）
2. **"打开浏览器搜索XXX"** → `app:launch`（path=浏览器, url=搜索URL）
3. **"生成/写/创建 + 文件类型"（不指定IDE）** → `content:generate`
4. **"打开记事本写XXX"** → `app:launch(notepad)` + `content:generate`（记事本不是IDE）
5. **"打开Word写报告"** → `content:generate`（auto_open=true会自动启动Word打开文件，不要再单独app:launch Word，否则会多开两个Word实例）
6. **"搜索XX然后写YY"** → `app:launch(浏览器搜索)` + `content:generate`

## 可用工具及参数
- app:launch (path=应用名或.exe, url=可选URL, args=可选文件路径数组)
- ide:launch (ide=vscode/cursor, action=create_project/open_file, files=[{path,template}], project_name=可选, auto_preview=布尔值)
- content:generate (task=任务描述, content_type=document/word/html/python, theme=核心主题, style=风格, length=短/中/长, output_path=可选, auto_open=布尔值)
- system:info, process:top, disk:cleanup, temp:cleanup
- process:kill (name或pid), notify, clipboard:write
- store:search (query=搜索关键词)
- store:install (package_id=包ID, app_name=应用名可选)
- store:uninstall (package_id=包ID)
- store:list (无参数)

## 参数提取规则
1. 从用户消息中提取核心动作对象，不要把整句话塞入参数
2. task/theme 只放核心词（如"登录页面"、"AI应用"），不放动词和连接词
3. content_type 根据上下文推断：网页/页面/HTML → html，代码/程序/脚本 → python，文档/文章/报告/Word → word
4. **path 参数规则（绝对禁止简写）**：必须填写完整可执行文件名，系统通过 where 命令解析完整路径。
   - Word → "WINWORD.EXE"，微信 → "WeChat.exe"，Edge → "msedge.exe"，记事本 → "notepad.exe"，Chrome → "chrome.exe"，Photoshop → "Photoshop.exe"，百度网盘 → "BaiduNetdisk.exe"
   - 严禁使用简写如 "word"、"wechat"、"edge"、"chrome"，这些在 where 命令中会解析失败
5. **关闭应用**：用户说"关闭/结束/杀掉 XXX"时，使用 process:kill 工具，params 填 {"name": "进程名.exe"}
6. **content:generate 必须带 auto_open: true**，确保生成后自动打开文件
7. **删除/卸载应用**：用户说"删除XX应用"/"卸载XX"/"移除XX"时，使用 store:uninstall 工具，params 填 {"package_id": "XX"}，标记 dangerous=true
8. **安装应用**：用户说"安装XX"时，使用 store:install 工具，params 填 {"package_id": "XX", "app_name": "XX"}
9. **搜索应用**：用户说"搜索应用XX"/"查找应用XX"时，使用 store:search 工具，params 填 {"query": "XX"}

## 系统上下文隔离（硬约束）
- 只根据用户明确说的话判断意图
- 禁止根据系统监控数据推测用户想清理/优化
- 除非用户明确说"卡/慢/清理/优化/结束"，否则禁止生成 disk:cleanup / temp:cleanup / process:kill

## 输出格式（严格JSON数组）
[
  {
    "tool": "工具名",
    "params": { ... },
    "confidence": 0.95,
    "reasoning": "识别依据"
  }
]

- confidence 范围 0.0-1.0，低于 0.7 需要用户确认
- reasoning 简短1句话
- 只输出 JSON 数组，不要 markdown，不要解释

## 示例

输入: "打开记事本写展示"
输出: [{"tool":"app:launch","params":{"path":"notepad.exe"},"confidence":0.95,"reasoning":"打开记事本"},{"tool":"content:generate","params":{"task":"展示","content_type":"document","theme":"展示","length":"短","auto_open":true},"confidence":0.9,"reasoning":"生成展示内容"}]

输入: "打开VSCode写个登录页面然后浏览器预览"
输出: [{"tool":"ide:launch","params":{"ide":"vscode","action":"create_project","project_name":"login-page","files":[{"path":"index.html","template":"modern_login"}],"auto_preview":true},"confidence":0.92,"reasoning":"VSCode创建登录页面"},{"tool":"app:launch","params":{"path":"msedge.exe","url":"file:///D:/AI_Generated/login-page/index.html"},"confidence":0.85,"reasoning":"浏览器预览"}]

输入: "搜索AI应用然后写篇文章"
输出: [{"tool":"app:launch","params":{"path":"msedge.exe","url":"https://www.baidu.com/s?wd=AI%E5%BA%94%E7%94%A8"},"confidence":0.95,"reasoning":"搜索AI应用"},{"tool":"content:generate","params":{"task":"AI应用文章","content_type":"word","theme":"AI应用","length":"中","auto_open":true},"confidence":0.9,"reasoning":"写AI应用文章"}]

输入: "打开Word写报告"
输出: [{"tool":"content:generate","params":{"task":"报告","content_type":"word","theme":"报告","length":"中","auto_open":true},"confidence":0.95,"reasoning":"content:generate的auto_open=true会自动启动Word打开文件，不需要单独app:launch避免多开"}]

输入: "打开微信搜索文件"
输出: [{"tool":"app:launch","params":{"path":"WeChat.exe"},"confidence":0.95,"reasoning":"打开微信"}]

输入: "写个登录页面"
输出: [{"tool":"content:generate","params":{"task":"登录页面","content_type":"html","theme":"用户登录","style":"现代","length":"中","output_path":"D:/AI_Generated/login.html","auto_open":true},"confidence":0.9,"reasoning":"生成登录页面HTML"}]

输入: "电脑很卡"
输出: [{"tool":"system:info","params":{},"confidence":0.95,"reasoning":"检查系统状态"},{"tool":"process:top","params":{"max":10},"confidence":0.9,"reasoning":"查看高占用进程"},{"tool":"disk:cleanup","params":{},"confidence":0.85,"reasoning":"用户说卡，允许清理"}]

输入: "打开Photoshop设计一个海报然后保存到桌面"
输出: [{"tool":"app:launch","params":{"path":"Photoshop.exe"},"confidence":0.95,"reasoning":"打开Photoshop"},{"tool":"content:generate","params":{"task":"海报设计","content_type":"document","theme":"海报","style":"创意","length":"短","auto_open":true},"confidence":0.85,"reasoning":"生成海报设计内容"}]

输入: "打开Chrome和微信"
输出: [{"tool":"app:launch","params":{"path":"chrome.exe"},"confidence":0.95,"reasoning":"打开Chrome"},{"tool":"app:launch","params":{"path":"WeChat.exe"},"confidence":0.95,"reasoning":"打开微信"}]

输入: "帮我写个Python爬虫脚本"
输出: [{"tool":"content:generate","params":{"task":"Python爬虫脚本","content_type":"python","theme":"网络爬虫","length":"中","auto_open":true},"confidence":0.92,"reasoning":"生成Python爬虫代码"}]

输入: "打开Edge搜索Python教程然后写个笔记"
输出: [{"tool":"app:launch","params":{"path":"msedge.exe","url":"https://www.baidu.com/s?wd=Python%E6%95%99%E7%A8%8B"},"confidence":0.95,"reasoning":"搜索Python教程"},{"tool":"content:generate","params":{"task":"Python学习笔记","content_type":"word","theme":"Python教程笔记","length":"中","auto_open":true},"confidence":0.88,"reasoning":"写Python笔记"}]

输入: "关闭Word"
输出: [{"tool":"process:kill","params":{"name":"WINWORD.EXE"},"confidence":0.92,"reasoning":"用户要关闭Word"}]

输入: "关闭百度网盘"
输出: [{"tool":"process:kill","params":{"name":"BaiduNetdisk.exe"},"confidence":0.92,"reasoning":"用户要关闭百度网盘，不是搜索！"}]

输入: "删除MongoDB应用"
输出: [{"tool":"store:uninstall","params":{"package_id":"MongoDB"},"confidence":0.92,"reasoning":"用户要删除MongoDB，使用store:uninstall通过winget安全卸载"}]

输入: "卸载Chrome"
输出: [{"tool":"store:uninstall","params":{"package_id":"Google Chrome"},"confidence":0.92,"reasoning":"用户要卸载Chrome浏览器"}]

输入: "安装VSCode"
输出: [{"tool":"store:install","params":{"package_id":"Microsoft.VisualStudioCode","app_name":"VS Code"},"confidence":0.92,"reasoning":"用户要安装VSCode"}]

输入: "打开百度网盘，关闭word"
输出: [{"tool":"app:launch","params":{"path":"BaiduNetdisk.exe"},"confidence":0.9,"reasoning":"打开百度网盘"},{"tool":"process:kill","params":{"name":"WINWORD.EXE"},"confidence":0.92,"reasoning":"关闭Word"}]

输入: "打开VSCode写个登录页面保存到D盘的login文件夹然后浏览器打开看看"
输出: [{"tool":"content:generate","params":{"task":"登录页面","content_type":"html","theme":"用户登录","style":"现代","length":"中","output_path":"D:/login","auto_open":true},"confidence":0.92,"reasoning":"生成登录页面HTML并保存到D盘login文件夹"},{"tool":"ide:launch","params":{"ide":"vscode","action":"open_file"},"confidence":0.85,"reasoning":"打开VSCode编辑代码"}]

输入: "打开浏览器搜索计算机毕设相关内容然后打开Word写一篇1000字论文"
输出: [{"tool":"app:launch","params":{"path":"msedge.exe","url":"https://www.baidu.com/s?wd=%E8%AE%A1%E7%AE%97%E6%9C%BA%E6%AF%95%E8%AE%BE%E7%9B%B8%E5%85%B3%E6%96%87%E4%BB%B6"},"confidence":0.95,"reasoning":"搜索计算机毕设相关文件"},{"tool":"content:generate","params":{"task":"计算机毕业设计论文","content_type":"word","theme":"计算机毕业设计","length":"中","auto_open":true},"confidence":0.9,"reasoning":"生成1000字论文"}]
""".strip()


async def generate_structured(
    message: str,
    mode: str = "default",
    *,
    system_context: dict[str, Any] | None = None,
    voice_context: dict[str, Any] | None = None,
    output_schema: str = "",
) -> dict[str, Any]:
    sanitized_message = cleaner.sanitize_user_input(message)
    system_summary = summarize_system_context(system_context)
    voice_summary = summarize_voice_context(voice_context)
    
    schema_hint = f"\nJSON Schema 要求:\n{output_schema}" if output_schema else ""
    
    user_prompt = (
        f"Agent 模式: {mode}\n"
        f"当前用户消息: {message}\n"
        f"系统监控摘要（仅供参考，禁止据此推测意图）: {system_summary}\n"
        f"语音上下文摘要: {voice_summary}\n"
        f"{schema_hint}\n\n"
        "【重要】只根据用户消息判断意图，只输出纯 JSON，不要任何其他文字。"
    )

    if not provider.enabled:
        return {
            "content": _safe_fallback_reply("LLMProviderNotConfigured"),
            "parsed": None,
            "used_fallback": True,
            "fallback_reason": "LLMProviderNotConfigured",
        }

    try:
        response = await provider.chat(
            system_prompt=STRUCTURED_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.1,
        )
        
        raw = response.strip()
        cleaned = raw
        cleaned = re.sub(r'^```json\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```\s*$', '', cleaned)
        cleaned = re.sub(r'^\s*\[SOLUTIONS\]\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*\[/SOLUTIONS\]\s*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'^\s*\[COMMANDS\]\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*\[/COMMANDS\]\s*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip()
        
        try:
            parsed = json.loads(cleaned)
            return {
                "content": cleaned,
                "parsed": parsed,
                "used_fallback": False,
                "fallback_reason": None,
            }
        except json.JSONDecodeError as e:
            return {
                "content": raw,
                "parsed": None,
                "used_fallback": True,
                "fallback_reason": f"JSONParseError: {str(e)}",
            }
                
    except LLMProviderError as exc:
        return {
            "content": _safe_fallback_reply(exc.__class__.__name__),
            "parsed": None,
            "used_fallback": True,
            "fallback_reason": exc.__class__.__name__,
        }