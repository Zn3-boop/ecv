from __future__ import annotations

# ========== HuggingFace 下载代理配置 ==========
import json
import os
import urllib.request

def _setup_hf_proxy():
    """自动检测代理并配置 HuggingFace 下载"""
    env_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    if env_proxy:
        print(f"[HF] 使用环境变量代理: {env_proxy}")
        _apply_proxy(env_proxy)
        return
    
    candidates = [
        "http://127.0.0.1:7890", "http://127.0.0.1:7897",
        "http://127.0.0.1:1080", "http://127.0.0.1:10809",
    ]
    
    for proxy in candidates:
        try:
            handler = urllib.request.ProxyHandler({"https": proxy})
            opener = urllib.request.build_opener(handler)
            opener.open("https://huggingface.co", timeout=3)
            print(f"[HF] 自动检测到可用代理: {proxy}")
            _apply_proxy(proxy)
            return
        except Exception:
            continue
    
    print("[HF] 无可用代理，切换到 HuggingFace 国内镜像")
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

def _apply_proxy(proxy_url: str):
    os.environ["HTTP_PROXY"] = proxy_url
    os.environ["HTTPS_PROXY"] = proxy_url
    handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
    urllib.request.install_opener(urllib.request.build_opener(handler))
    hf_home = os.getenv("HF_HOME", "d:/hf_cache")
    os.makedirs(hf_home, exist_ok=True)
    os.environ["HF_HOME"] = hf_home
    os.environ["TRANSFORMERS_CACHE"] = f"{hf_home}/transformers"

_setup_hf_proxy()
# ============================================

import re
import urllib.parse
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.automation import parse_user_command, _validate_and_filter_commands, filter_invalid_commands, Command
from app.services.context_manager import context_manager
from app.services.llm.orchestrator import run_agent_workflow, run_command_workflow
from app.services.response_separator import separator
from app.services.storage import add_assistant_output, add_conversation_message, create_voice_turn, ensure_conversation, get_conversation, get_history_for_llm, list_conversation_messages
from app.services.voice_provider import VoiceProviderError, voice_provider
from app.utils.response_cleaner import cleaner

router = APIRouter(prefix='/voice', tags=['voice'])


class VoiceCommandRequest(BaseModel):
    transcript: str = Field(..., min_length=1)
    mode: str = Field(default='voice')
    system_context: dict[str, Any] | None = Field(default=None)
    voice_context: dict[str, Any] | None = Field(default=None)
    conversation_id: int | None = Field(default=None)
    role_prompt: str | None = Field(default=None)


class VoiceCommandResponse(BaseModel):
    transcript: str
    normalized_text: str
    intent: str
    reply: str
    analysis: str = ""
    thinking: str = ""
    advice: str = ""
    risk_warning: str = ""
    review_notes: str | None = None
    review_source: str | None = None
    speech_text: str
    tts_content: str | None = None
    tts_required: bool = False
    used_system_context: bool = False
    used_voice_context: bool = False
    used_fallback: bool = False
    fallback_reason: str | None = None
    speech_provider: str = 'browser'
    tts_audio_base64: str | None = None
    tts_mime_type: str | None = None
    tts_fallback_used: bool = False
    tts_available: bool = False
    browser_tts_recommended: bool = False
    speech_capabilities: dict[str, Any] | None = None
    commands: list[dict[str, Any]] = Field(default_factory=list)
    command_execution_mode: str = 'none'
    context_info: dict[str, Any] = Field(default_factory=dict)


class VoiceTranscribeRequest(BaseModel):
    audio_base64: str = Field(..., min_length=1)
    filename: str = Field(default='voice.webm')
    mime_type: str = Field(default='audio/webm')
    locale: str = Field(default='zh-CN')
    session_id: str | None = None
    turn_id: str | None = None
    wake_word_enabled: bool = False
    interruption_enabled: bool = False


class VoiceTranscribeResponse(BaseModel):
    transcript: str
    provider: str
    model: str
    fallback_used: bool = False
    stt_available: bool = False
    manual_input_required: bool = False
    message: str | None = None
    wake_word_detected: bool = False
    wake_word: str | None = None
    session_id: str | None = None
    turn_id: str | None = None
    interruption_enabled: bool = False


class VoiceSynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1)
    format: str = Field(default='mp3')
    session_id: str | None = None
    turn_id: str | None = None
    interruption_token: str | None = None


class VoiceSynthesizeResponse(BaseModel):
    provider: str
    model: str
    voice: str
    mime_type: str
    audio_base64: str
    fallback_used: bool = False
    interruption_token: str | None = None


class VoiceRuntimeResponse(BaseModel):
    provider: str
    enabled: bool
    stt_enabled: bool
    tts_enabled: bool
    stt_model: str
    tts_model: str
    tts_voice: str
    base_url: str
    supports_cloud_stt: bool
    supports_cloud_tts: bool
    recommended_next_steps: list[str]


class VoiceStatusResponse(BaseModel):
    provider: str
    enabled: bool
    available: bool
    stt_enabled: bool
    tts_enabled: bool
    stt_available: bool
    tts_available: bool
    stt_model: str
    tts_model: str
    tts_voice: str
    base_url: str
    last_error: str | None = None
    last_error_stage: str | None = None
    last_error_type: str | None = None
    last_error_code: str | None = None
    last_upload_mime_type: str | None = None
    local_whisper_compute_type: str | None = None
    local_whisper_device: str | None = None
    local_whisper_model_loaded: bool | None = None


from app.services.intent_detector import (
    CONTENT_GENERATE_KEYWORDS, SEARCH_KEYWORDS,
    detect_intent, _is_simple_single_action, _is_single_app_only,
)

# 内容生成相关关键词（保留引用兼容，实际定义在 intent_detector）

def _extract_theme(text: str) -> str:
    for pattern in [
        r'(?:关于|有关|围绕)["\u201c\u201d]?([^"\u201c\u201d，。！？\n]{2,30})["\u201c\u201d]?(?:的|之)?(?:文章|文档|报告|论文|内容|资料|信息)',
        r'(?:搜索|查找|查询|搜一下|查一下|查资料|找资料)([^，。！？\n]{2,30}?)(?:的|之)?(?:信息|资料|内容|相关)',
        r'(?:搜索|查找|查询|搜一下|查一下|查资料|找资料)([^，。！？\n]{2,30})',
        r'(?:撰写|编写|写|生成|创建|制作)(?:关于|有关|围绕)?["\u201c\u201d]?([^"\u201c\u201d，。！？\n]{2,30})["\u201c\u201d]?(?:的|之)?(?:文章|文档|报告|论文|内容)',
    ]:
        m = re.search(pattern, text)
        if m:
            theme = m.group(1).strip()
            for suffix in ['相关信息', '信息', '资料', '内容', '相关', '的文章', '的文档']:
                theme = theme.replace(suffix, '')
            return theme.strip() if theme.strip() else text[:20]
    return text[:20]


def _handle_close_intent(normalized_text: str) -> tuple[list[Command], str, bool]:
    """
    处理"关闭/结束 XXX"意图，生成 process:kill 命令。
    支持复合指令："打开百度网盘，关闭word" → 只处理关闭部分
    """
    from app.api.automation import Command
    commands = []
    reply_text = ""
    intent_handled = False
    lower_text = normalized_text.lower()

    close_patterns = re.findall(
        r'(?:关闭|结束|杀掉|停止|终止)\s*([^\s，,；;。！？\n]{1,20})',
        normalized_text,
    )
    for target in close_patterns:
        target_lower = target.lower()
        proc_name = None
        for key, proc in KNOWN_APPS_LAUNCH.items():
            if key in target_lower:
                proc_name = proc
                break
        if proc_name:
            commands.append(Command(
                tool="process:kill", type="destructive",
                params={"name": proc_name},
                reason=f"结束进程 {proc_name}",
                confidence=0.92, risk="high",
                require_confirmation=True, auto_execute=False,
            ))
            reply_text += f"准备结束 {proc_name}。"
            intent_handled = True
        else:
            commands.append(Command(
                tool="process:kill", type="destructive",
                params={"name": target},
                reason=f"结束进程 {target}",
                confidence=0.7, risk="high",
                require_confirmation=True, auto_execute=False,
            ))
            reply_text += f"准备结束 {target}。"
            intent_handled = True

    return commands, reply_text, intent_handled

def _local_fallback_decompose(text: str) -> list:
    """
    LLM 不可用时的本地降级任务分解。
    尽可能从文本中提取多个动作，生成 Command 列表。
    支持复合指令："打开A，关闭B" → 分别生成 app:launch 和 process:kill
    """
    from app.api.automation import Command
    normalized = text.lower()
    commands = []

    has_open = any(k in normalized for k in ['打开', '启动', '运行'])
    has_close = any(k in normalized for k in ['关闭', '结束', '杀掉', '停止', '终止'])
    has_write = any(k in text for k in ['写', '生成', '创建', '制作', '编写', '设计'])
    has_search = any(k in text for k in SEARCH_KEYWORDS)
    has_browse = any(k in normalized for k in ['预览', '浏览器', '查看'])
    has_system = any(k in normalized for k in ['cpu', '内存', '磁盘', '卡', '慢', '清理', '状态', '监控'])

    if has_close:
        close_commands, _, handled = _handle_close_intent(text)
        if handled and close_commands:
            commands.extend(close_commands)

    if has_open:
        open_text = text
        if has_close:
            open_parts = re.split(r'[，,；;]\s*(?:关闭|结束|杀掉|停止|终止)', text)
            open_text = open_parts[0] if open_parts else text
        app_commands, _, handled = handle_app_launch_intent(open_text)
        if handled and app_commands:
            commands.extend(app_commands)

    has_launch = any(cmd.tool == 'app:launch' for cmd in commands) or any(cmd.tool == 'ide:launch' for cmd in commands)

    if has_search:
        theme = _extract_theme(text)
        is_chinese = any('\u4e00' <= c <= '\u9fff' for c in theme)
        search_url = f"https://www.baidu.com/s?wd={urllib.parse.quote(theme)}" if is_chinese else f"https://www.google.com/search?q={urllib.parse.quote(theme)}"
        commands.append(Command(
            tool="app:launch", type="write",
            params={"path": "msedge.exe", "url": search_url},
            reason=f"搜索「{theme}」", confidence=0.85, risk="low",
            require_confirmation=False, auto_execute=True,
        ))

    if has_write:
        write_match = re.search(r'(?:写入|写上|输入|键入)\s*["\u201c\u201d]?(.+?)["\u201c\u201d]?\s*$', text)
        if write_match:
            theme = write_match.group(1).strip()
        else:
            theme = _extract_theme(text)
        content_type = 'word'
        if any(k in text for k in ['登录页面', '网页', 'html', '网站', '页面']):
            content_type = 'html'
        elif any(k in text for k in ['代码', '程序', '脚本', 'python']):
            content_type = 'python'
        
        is_simple_text = (
            len(theme) <= 30
            and not any(kw in theme for kw in ['页面', '网站', '论文', '文章', '代码', '程序', '设计', '报告', '方案', '系统', '项目', '登录'])
        )
        
        if is_simple_text and has_launch:
            commands.append(Command(
                tool="keyboard:type", type="write",
                params={"text": theme},
                reason=f"输入文本「{theme}」到当前窗口", confidence=0.90, risk="low",
                require_confirmation=False, auto_execute=True,
            ))
        else:
            commands.append(Command(
                tool="content:generate", type="write",
                params={"task": theme, "content_type": content_type, "theme": theme, "length": "中", "auto_open": True},
                reason=f"生成「{theme}」{content_type}内容", confidence=0.85, risk="low",
                require_confirmation=False, auto_execute=True,
            ))

    if has_browse:
        commands.append(Command(
            tool="app:launch", type="write",
            params={"path": "msedge.exe"},
            reason="打开浏览器预览", confidence=0.8, risk="low",
            require_confirmation=False, auto_execute=True,
        ))

    if has_system:
        commands.append(Command(
            tool="system:info", type="read", params={},
            reason="获取系统状态", confidence=0.9, risk="low",
            require_confirmation=False, auto_execute=True,
        ))
        commands.append(Command(
            tool="process:top", type="read", params={"max": 10},
            reason="查看高占用进程", confidence=0.85, risk="low",
            require_confirmation=False, auto_execute=True,
        ))

    if not commands:
        commands.append(Command(
            tool="system:info", type="read", params={},
            reason="获取系统整体状态", confidence=0.9, risk="low",
            require_confirmation=False, auto_execute=True,
        ))

    seen = set()
    unique = []
    for cmd in commands:
        sig = f"{cmd.tool}:{json.dumps(cmd.params, sort_keys=True, ensure_ascii=False)}"
        if sig not in seen:
            seen.add(sig)
            unique.append(cmd)
    return unique


def detect_wake_word(text: str) -> tuple[bool, str | None]:
    wake_words = ['小智', 'agent', '助手', 'hey agent']
    normalized = text.lower().strip()
    compact = normalized.replace(' ', '')
    for item in wake_words:
        if item in compact or item.replace(' ', '') in compact:
            return True, item
    return False, None


def normalize_voice_text(text: str) -> str:
    normalized = text.strip()
    filler_tokens = ['老师帮我', '请帮我', '麻烦你', '一下', '1下']
    for token in filler_tokens:
        normalized = normalized.replace(token, '')
    result = normalized.strip(' ，。！？,.!?:;；')
    return result if result else text.strip()


def _parse_combo_intent(text: str, intent: str) -> list | None:
    """
    🆕 在 parse_user_command 之前拦截组合意图：打开+搜索、打开+URL
    解决 "打开edge搜索ai" 只打开 Edge 不搜索的问题
    """
    if intent != 'desktop_control':
        return None
    
    import urllib.parse
    from app.api.automation import Command
    
    lower_text = text.lower()
    
    # 模式A: "打开edge搜索ai" / "打开 Chrome 搜索 React"
    if '搜索' in text:
        parts = text.split('搜索', 1)
        if len(parts) == 2:
            query = parts[1].strip()
            # 去掉尾部语气词
            for suffix in ['打开', '关闭', '然后', '再', '并', '一下', '吧', '吗', '呢', '看看', '查查']:
                if query.endswith(suffix):
                    query = query[:-len(suffix)].strip()
            if query:
                # 判断浏览器
                browser = 'msedge.exe'
                if any(b in lower_text for b in ['chrome', '谷歌', 'google']):
                    browser = 'chrome.exe'
                elif any(b in lower_text for b in ['firefox', '火狐']):
                    browser = 'firefox.exe'
                
                # 中文用百度，英文用 Google
                is_chinese = any('\u4e00' <= c <= '\u9fff' for c in query)
                search_url = f"https://www.baidu.com/s?wd={urllib.parse.quote(query)}" if is_chinese else f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                
                return [Command(
                    tool="app:launch",
                    type="write",
                    params={"path": browser, "url": search_url},
                    reason=f"打开 {browser} 搜索「{query}」",
                    confidence=0.92,
                    risk="low",
                    require_confirmation=False,
                    auto_execute=True,
                )]
    
    return None


# ========== URL Scheme 配置 ==========
URL_SCHEMES = {
    '微信': 'weixin://',
    '微信搜索': 'weixin://',
    '淘宝': 'taobao://',
    '支付宝': 'alipay://',
    '京东': 'openapp.jdMobile://',
    '抖音': 'snssdk1128://',
    '小红书': 'xhs://',
    'QQ': 'mqq://',
    'QQ搜索': 'mqq://',
    '微博': 'sinaweibo://',
    '知乎': 'zhihu://',
}

# ========== 已知应用映射 ==========
KNOWN_APPS_LAUNCH = {
    # 社交类
    '微信': 'WeChat.exe', 'wechat': 'WeChat.exe',
    'qq': 'QQ.exe', 'QQ': 'QQ.exe',
    '钉钉': 'DingTalk.exe', '企业微信': 'WXWork.exe',
    '飞书': 'Feishu.exe', 'slack': 'Slack.exe',
    'discord': 'Discord.exe', 'teams': 'Teams.exe',
    'telegram': 'Telegram.exe', 'tg': 'Telegram.exe',
    'zoom': 'Zoom.exe',
    
    # 浏览器
    'edge': 'msedge.exe', '浏览器': 'msedge.exe',
    'chrome': 'chrome.exe', '谷歌': 'chrome.exe', 'google': 'chrome.exe',
    'firefox': 'firefox.exe', '火狐': 'firefox.exe',
    
    # 办公开发
    'vscode': 'Code.exe', 'code': 'Code.exe',
    'idea': 'idea64.exe', 'pycharm': 'pycharm64.exe',
    'notepad': 'notepad.exe', '记事本': 'notepad.exe', '文本编辑器': 'notepad.exe',
    'sublime': 'sublime_text.exe', 'notepad++': 'notepad++.exe',
    
    # 文档类
    'word': 'WINWORD.EXE', 'excel': 'EXCEL.EXE',
    'ppt': 'POWERPNT.EXE', 'powerpoint': 'POWERPNT.EXE',
    'wps': 'wps.exe', 'pdf': 'AcroRd32.exe',
    
    # 设计类
    'photoshop': 'Photoshop.exe', 'ps': 'Photoshop.exe',
    'figma': 'Figma.exe', '剪映': 'CapCut.exe', 'capcut': 'CapCut.exe',
    
    # 音乐视频
    '网易云': 'cloudmusic.exe', 'qq音乐': 'QQMusic.exe',
    'spotify': 'Spotify.exe', 'potplayer': 'PotPlayer64.exe',
    
    # 网盘/下载
    '百度网盘': 'BaiduNetdisk.exe', '百度云': 'BaiduNetdisk.exe', '百度云盘': 'BaiduNetdisk.exe',
    'baidunetdisk': 'BaiduNetdisk.exe', '百度网': 'BaiduNetdisk.exe',
    '迅雷': 'Thunder.exe', 'idm': 'IDMan.exe',
    
    # 游戏
    'steam': 'steam.exe', 'Epic': 'EpicGamesLauncher.exe', 'epic': 'EpicGamesLauncher.exe',
    
    # 系统工具
    '计算器': 'calc.exe', 'calc': 'calc.exe',
    '画图': 'mspaint.exe', '截图': 'SnippingTool.exe',
    '任务管理器': 'Taskmgr.exe', '控制面板': 'control.exe',
    '资源管理器': 'explorer.exe', '文件管理器': 'explorer.exe',
    '我的电脑': 'explorer.exe', '此电脑': 'explorer.exe',
    '回收站': 'explorer.exe',
    # Windows系统设置 (打开系统设置页面)
    '设置': 'ms-settings:', '系统设置': 'ms-settings:', 'windows设置': 'ms-settings:',
}

# ========== 辅助函数 ==========
def convert_chinese_drive_to_path(text: str) -> str:
    m = re.match(r'([a-zA-Z])\s*盘[/\\]?(.*)', text.replace('\\', '/'))
    if not m:
        return text
    drive = m.group(1).upper()
    rest = m.group(2).strip('/')
    return f"{drive}:\\{rest}"

DANGEROUS_APPS = frozenset([
    "cmd", "command", "powershell", "pwsh", "regedit", "registry",
    "taskkill", "format", "diskpart", "net", "sc", "schtasks",
])

def validate_app_safety(app_name: str) -> tuple[bool, str, str]:
    lower_name = app_name.lower().replace('.exe', '')
    for danger in DANGEROUS_APPS:
        if danger in lower_name:
            return False, "blocked", f"「{app_name}」属于系统管理工具，已被安全策略禁止"
    return True, "low", "安全"


def handle_app_launch_intent(normalized_text: str) -> tuple[list[Command], str, bool]:
    """
    处理应用启动/关闭意图，支持：
    - 简单启动："打开QQ"
    - 关闭应用："关闭word" / "结束微信"
    - 浏览器搜索："打开Edge搜索python"
    - URL Scheme："打开微信搜索xxx"
    - 文件路径："打开VSCode打开D盘项目"
    - 资源管理器："打开资源管理器里D盘xx"
    
    返回: (commands, reply_text, intent_handled)
    """
    commands = []
    reply_text = ""
    intent_handled = False
    lower_text = normalized_text.lower()
    
    # 🆕 模式0: "关闭/结束/杀掉 XXX" → process:kill
    has_close = any(k in normalized_text for k in ['关闭', '结束', '杀掉', '停止', '终止'])
    if has_close:
        close_target = None
        for key, proc in KNOWN_APPS_LAUNCH.items():
            if key in lower_text:
                close_target = proc
                break
        if close_target:
            commands.append(Command(
                tool="process:kill", type="destructive",
                params={"name": close_target},
                reason=f"结束进程 {close_target}",
                confidence=0.92, risk="high",
                require_confirmation=True, auto_execute=False,
            ))
            reply_text = f"准备结束 {close_target}。"
            intent_handled = True
            return commands, reply_text, True
    
    # 🆕 模式A: "打开浏览器搜索xxx" → 浏览器+搜索URL
    has_search = any(k in normalized_text for k in ['搜索', '搜一下', '查找'])
    search_match = re.search(r'(?:搜索|搜一下|查找|查一下)\s*(.+?)(?:\s*$|\s+打开|\s+关闭)', normalized_text)
    
    if search_match and any(b in lower_text for b in ['edge', 'chrome', '浏览器', 'google', '谷歌']):
        query = search_match.group(1).strip()
        is_chinese = any('\u4e00' <= c <= '\u9fff' for c in query)
        if is_chinese:
            search_url = f"https://www.baidu.com/s?wd={urllib.parse.quote(query)}"
        else:
            search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        
        browser = 'msedge.exe' if any(b in lower_text for b in ['edge', '浏览器']) else 'chrome.exe'
        commands.append(Command(
            tool="app:launch", type="write",
            params={"path": browser, "url": search_url},
            reason=f"启动 {browser} 搜索「{query}」",
            confidence=0.92, risk="low",
            require_confirmation=False, auto_execute=True,
        ))
        reply_text = f"正在用浏览器搜索「{query}」。"
        return commands, reply_text, True
    
    # 🆕 模式A2: "打开edge搜索ai" → 无需明确说"搜索"
    if has_search and any(b in lower_text for b in ['edge', 'chrome', 'google', '谷歌']):
        search_text = normalized_text.replace('打开', '').replace('搜索', '').replace('搜一下', '').replace('查找', '').strip()
        if search_text:
            is_chinese = any('\u4e00' <= c <= '\u9fff' for c in search_text)
            if is_chinese:
                search_url = f"https://www.baidu.com/s?wd={urllib.parse.quote(search_text)}"
            else:
                search_url = f"https://www.google.com/search?q={urllib.parse.quote(search_text)}"
            
            browser = 'msedge.exe' if any(b in lower_text for b in ['edge', '浏览器']) else 'chrome.exe'
            commands.append(Command(
                tool="app:launch", type="write",
                params={"path": browser, "url": search_url},
                reason=f"启动 {browser} 搜索「{search_text}」",
                confidence=0.92, risk="low",
                require_confirmation=False, auto_execute=True,
            ))
            reply_text = f"正在用浏览器搜索「{search_text}」。"
            return commands, reply_text, True
    
    # 🆕 模式B: "打开资源管理器里D盘xx" → 资源管理器+路径
    file_match = re.search(r'[Dd]盘[/\\](.+?)(?:\s*$|\s+打开|\s+关闭)', normalized_text)
    if file_match and any(a in lower_text for a in ['资源管理器', '文件管理器', 'explorer', '我的电脑', '此电脑']):
        raw_path = file_match.group(0)
        wsl_path = convert_chinese_drive_to_path(raw_path)
        commands.append(Command(
            tool="app:launch", type="write",
            params={"path": "explorer.exe", "args": [wsl_path]},
            reason=f"打开资源管理器并导航到 {wsl_path}",
            confidence=0.90, risk="low",
            require_confirmation=False, auto_execute=True,
        ))
        reply_text = f"正在打开资源管理器并导航到 {wsl_path}。"
        return commands, reply_text, True
    
    # 🆕 模式B2: "打开VSCode打开D盘项目" → IDE+路径
    if file_match and any(a in lower_text for a in ['vscode', 'code', 'pycharm', 'idea', 'notepad']):
        raw_path = file_match.group(0)
        wsl_path = convert_chinese_drive_to_path(raw_path)
        app_key = next((k for k in KNOWN_APPS_LAUNCH if k in lower_text), 'code')
        app_exe = KNOWN_APPS_LAUNCH.get(app_key, 'Code.exe')
        is_safe, _, reason = validate_app_safety(app_exe)
        if is_safe:
            commands.append(Command(
                tool="app:launch", type="write",
                params={"path": app_exe, "args": [wsl_path]},
                reason=f"启动 {app_exe} 打开 {wsl_path}",
                confidence=0.88, risk="low",
                require_confirmation=False, auto_execute=True,
            ))
            reply_text = f"正在打开 {app_exe} 并导航到 {wsl_path}。"
        else:
            reply_text = reason
        return commands, reply_text, True
    
    # 🆕 模式C: "打开QQ里的xx" 或 "打开记事本打开xx" 或 "打开记事本写xx" → 应用+文件名/内容
    file_in_app_pattern = re.search(r'打开(.+?)(?:里|打开|写|写入|编辑)(.+?)$', normalized_text)
    if file_in_app_pattern:
        app_name = file_in_app_pattern.group(1).strip()
        file_name = file_in_app_pattern.group(2).strip()
        matched_app = None
        for key, proc in KNOWN_APPS_LAUNCH.items():
            if key in app_name.lower() or app_name.lower() in key:
                matched_app = proc
                break
        if matched_app:
            is_safe, _, reason = validate_app_safety(matched_app)
            if is_safe:
                commands.append(Command(
                    tool="app:launch", type="write",
                    params={"path": matched_app, "args": [f'"{file_name}"']},
                    reason=f"用 {matched_app} 打开 {file_name}",
                    confidence=0.85, risk="low",
                    require_confirmation=False, auto_execute=True,
                ))
                reply_text = f"正在用 {matched_app} 打开 {file_name}。"
                return commands, reply_text, True
    
    # 🆕 模式D: 简单应用启动
    target_name = None
    for key in ['微信', 'wechat', 'qq', 'vscode', 'edge', 'chrome', '钉钉', 'steam', '网易云', '记事本', '计算器', '资源管理器', '设置']:
        if key in lower_text:
            target_name = KNOWN_APPS_LAUNCH.get(key)
            break
    
    if not target_name:
        for key, proc in KNOWN_APPS_LAUNCH.items():
            if key in lower_text:
                target_name = proc
                break
    
    if target_name:
        is_safe, _, reason = validate_app_safety(target_name)
        if is_safe:
            commands.append(Command(
                tool="app:launch", type="write",
                params={"path": target_name},
                reason=f"启动 {target_name}",
                confidence=0.95, risk="low",
                require_confirmation=False, auto_execute=True,
            ))
            reply_text = f"正在打开 {target_name}。"
        else:
            reply_text = reason
        return commands, reply_text, True
    
    return commands, reply_text, False


@router.get('/runtime', response_model=VoiceRuntimeResponse)
async def get_voice_runtime():
    runtime = voice_provider.get_runtime_config()
    enabled = bool(runtime['enabled'])
    return VoiceRuntimeResponse(
        provider=runtime['provider'],
        enabled=enabled,
        stt_enabled=bool(runtime.get('stt_enabled', enabled)),
        tts_enabled=bool(runtime.get('tts_enabled', enabled)),
        stt_model=runtime['stt_model'],
        tts_model=runtime['tts_model'],
        tts_voice=runtime['tts_voice'],
        base_url=runtime['base_url'],
        supports_cloud_stt=bool(runtime.get('stt_enabled', enabled)),
        supports_cloud_tts=bool(runtime.get('tts_enabled', enabled)),
        recommended_next_steps=[
            '接入真实云端 ASR 后，将前端 MediaRecorder 音频提交到 /voice/transcribe',
            '接入真实云端 TTS 后，优先播放后端返回的 audio_base64',
        ],
    )


async def _build_transcribe_response(
    *, audio_bytes: bytes, filename: str, mime_type: str,
    session_id: str | None, turn_id: str | None,
    wake_word_enabled: bool, interruption_enabled: bool,
):
    wake_word_detected, wake_word = detect_wake_word('')
    try:
        result = await voice_provider.transcribe_bytes(
            audio_bytes=audio_bytes, filename=filename, mime_type=mime_type,
        )
        # 🆕 兼容多种字段名
        transcript = (result.get('transcript') or result.get('text') or '').strip()
        provider = str(result.get('provider', 'local-browser'))
        model = str(result.get('model', 'browser-manual-confirmation'))
        fallback_used = bool(result.get('fallback_used', False)) or provider in {'mock', 'local-browser', 'browser'}
        stt_available = bool(result.get('stt_available', not fallback_used))
        manual_input_required = bool(result.get('manual_input_required', fallback_used))
        message = result.get('message')
        print(f"[Voice Transcribe] transcript='{transcript}', provider={provider}")
    except VoiceProviderError:
        transcript = ''
        provider = 'mock'
        model = 'mock-browser-fallback'
        fallback_used = True
        stt_available = False
        manual_input_required = True
        message = '语音服务暂不可用，请改为手动确认文本后发送给 Agent。'

    if wake_word_enabled:
        wake_word_detected, wake_word = detect_wake_word(transcript)

    return VoiceTranscribeResponse(
        transcript=transcript, provider=provider, model=model,
        fallback_used=fallback_used, stt_available=stt_available,
        manual_input_required=manual_input_required, message=message,
        wake_word_detected=wake_word_detected, wake_word=wake_word,
        session_id=session_id, turn_id=turn_id, interruption_enabled=interruption_enabled,
    )


@router.get('/status', response_model=VoiceStatusResponse)
async def get_voice_status():
    status = voice_provider.get_status()
    return VoiceStatusResponse(
        provider=str(status.get('provider', 'mock')),
        enabled=bool(status.get('enabled', False)),
        available=bool(status.get('available', False)),
        stt_enabled=bool(status.get('stt_enabled', False)),
        tts_enabled=bool(status.get('tts_enabled', False)),
        stt_available=bool(status.get('stt_available', False)),
        tts_available=bool(status.get('tts_available', False)),
        stt_model=str(status.get('stt_model', 'unknown')),
        tts_model=str(status.get('tts_model', 'unknown')),
        tts_voice=str(status.get('tts_voice', 'unknown')),
        base_url=str(status.get('base_url', 'unknown')),
        last_error=status.get('last_error'),
        last_error_stage=status.get('last_error_stage'),
        last_error_type=status.get('last_error_type'),
        last_error_code=status.get('last_error_code'),
        last_upload_mime_type=status.get('last_upload_mime_type'),
        local_whisper_compute_type=status.get('local_whisper_compute_type'),
        local_whisper_device=status.get('local_whisper_device'),
        local_whisper_model_loaded=status.get('local_whisper_model_loaded'),
    )


@router.post('/transcribe', response_model=VoiceTranscribeResponse)
async def transcribe_voice(payload: VoiceTranscribeRequest):
    import base64
    try:
        audio_bytes = base64.b64decode(payload.audio_base64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail='Invalid audio_base64 payload') from exc
    return await _build_transcribe_response(
        audio_bytes=audio_bytes, filename=payload.filename, mime_type=payload.mime_type,
        session_id=payload.session_id, turn_id=payload.turn_id,
        wake_word_enabled=payload.wake_word_enabled, interruption_enabled=payload.interruption_enabled,
    )


@router.post('/transcribe-upload', response_model=VoiceTranscribeResponse)
async def transcribe_voice_upload(
    file: UploadFile = File(...),
    locale: str = Form(default='zh-CN'),
    session_id: str | None = Form(default=None),
    turn_id: str | None = Form(default=None),
    wake_word_enabled: bool = Form(default=False),
    interruption_enabled: bool = Form(default=False),
):
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail='Uploaded audio file is empty')
    return await _build_transcribe_response(
        audio_bytes=audio_bytes, filename=file.filename or 'voice.webm',
        mime_type=file.content_type or 'audio/webm',
        session_id=session_id, turn_id=turn_id,
        wake_word_enabled=wake_word_enabled, interruption_enabled=interruption_enabled,
    )


@router.post('/synthesize', response_model=VoiceSynthesizeResponse)
async def synthesize_voice(payload: VoiceSynthesizeRequest):
    try:
        result = await voice_provider.synthesize_text(text=payload.text, format=payload.format)
    except VoiceProviderError as exc:
        result = {
            'provider': 'mock', 'model': 'mock-browser-fallback',
            'voice': 'browser-speech-synthesis', 'mime_type': 'text/plain',
            'audio_base64': '', 'fallback_used': True, 'error': str(exc),
        }
    except Exception as exc:
        result = {
            'provider': 'mock', 'model': 'mock-browser-fallback',
            'voice': 'browser-speech-synthesis', 'mime_type': 'text/plain',
            'audio_base64': '', 'fallback_used': True, 'error': str(exc),
        }

    return VoiceSynthesizeResponse(
        provider=str(result.get('provider', 'mock')),
        model=str(result.get('model', 'mock-browser-fallback')),
        voice=str(result.get('voice', 'browser-speech-synthesis')),
        mime_type=str(result.get('mime_type', 'audio/mpeg')),
        audio_base64=str(result.get('audio_base64', '')),
        fallback_used=str(result.get('provider', 'mock')) == 'mock' or result.get('fallback_used', False),
        interruption_token=payload.interruption_token,
    )


@router.post('/command', response_model=VoiceCommandResponse)
async def handle_voice_command(payload: VoiceCommandRequest):
    try:
        normalized_text = normalize_voice_text(payload.transcript)
        if not normalized_text:
            normalized_text = '请给出诊断建议。'
        intent = detect_intent(normalized_text)

        merged_voice_context = {'source': 'desktop-text-simulated', 'locale': 'zh-CN', 'device': 'desktop'}
        if payload.voice_context:
            merged_voice_context.update(payload.voice_context)

        effective_message = normalized_text
        conversation_id = payload.conversation_id
        context_info = {
            'original_turns': 0, 'optimized_turns': 0, 'history_summary': None,
            'context_strategy': context_manager.strategy.value, 'estimated_tokens': 0,
            'history_was_cleaned': False, 'history_was_truncated': False,
        }

        if conversation_id is None:
            auto_conversation = ensure_conversation(
                title='桌面语音会话',
                role_prompt=payload.role_prompt or '你是一个偏桌面效率、系统诊断与语音交互的 AI Agent',
            )
            conversation_id = int(auto_conversation['id'])

        conversation = get_conversation(conversation_id) if conversation_id is not None else None
        if conversation:
            history_messages = get_history_for_llm(conversation_id, limit=6)
            sanitized_history = [
                {'role': item.role, 'content': item.content, 'created_at': item.timestamp,
                 'metadata': {}, 'is_meta': item.is_meta, 'is_fallback': item.is_fallback}
                for item in history_messages
            ]
            role_prompt = payload.role_prompt or conversation.get('role_prompt') or ''
            optimized_history, history_summary = context_manager.process(
                history=sanitized_history, current_message=normalized_text,
            )
            effective_message = context_manager.build_prompt(
                history=optimized_history, current_user_msg=normalized_text,
                system_prompt=f"你是一个偏桌面效率、系统诊断与语音交互的 AI Agent。角色设定：{role_prompt or '默认桌面Agent'}",
            )
            context_info = {
                'original_turns': len(sanitized_history), 'optimized_turns': len(optimized_history),
                'history_summary': history_summary, 'context_strategy': context_manager.strategy.value,
                'estimated_tokens': context_manager.get_context_length(optimized_history),
                'history_was_cleaned': any(item.was_cleaned for item in history_messages),
                'history_was_truncated': False,
            }
        else:
            effective_message = normalized_text

        commands = []
        reply_text = ""
        analysis = ""
        review_source = None
        used_system_context = False
        used_voice_context = False
        used_fallback = False
        fallback_reason = None
        agent_analysis = ""
        agent_thinking = ""
        agent_advice = ""
        agent_risk_warning = ""

        # 🆕 尝试解析命令
        parsed_analysis, parsed_commands, parsed_reply = parse_user_command(normalized_text)
        if parsed_commands:
            alert_type = 'memory'
            if any(k in normalized_text.lower() for k in ['磁盘', 'disk', 'c盘', '空间']):
                alert_type = 'disk'
            parsed_commands = _validate_and_filter_commands(parsed_commands, alert_type=alert_type, system_context=payload.system_context, level='warning')

        # ===== 意图分发：简单单动作走本地快路径，其他全部走 LLM =====

        if intent == 'system_monitor' or intent == 'system_optimize':
            # 快路径1：纯系统监控/优化，本地规则足够
            if parsed_commands:
                commands = parsed_commands
                reply_text = parsed_reply
                analysis = parsed_analysis
            else:
                commands.append(Command(
                    tool="system:info", type="read", params={},
                    reason="获取系统整体状态", confidence=0.95, risk="low",
                    require_confirmation=False, auto_execute=True,
                ))
                commands.append(Command(
                    tool="process:top", type="read", params={"max": 10},
                    reason="查看高占用进程", confidence=0.9, risk="low",
                    require_confirmation=False, auto_execute=True,
                ))
                reply_text = "正在检查系统状态。"
            analysis = analysis or f"识别到系统监控请求"
            review_source = 'local_rule'
            used_voice_context = True

        elif intent == 'desktop_control':
            # 快路径2：纯单应用启动（已确认无复合动作）
            app_commands, app_reply, handled = handle_app_launch_intent(normalized_text)
            if handled and app_commands:
                commands = app_commands
                reply_text = app_reply
            elif parsed_commands:
                commands = parsed_commands
                reply_text = parsed_reply
            else:
                reply_text = "未识别到目标应用，请明确说出要打开的应用名称。"
            analysis = parsed_analysis or f"识别到应用启动指令"
            review_source = 'local_rule'
            used_voice_context = True

        elif intent == 'search_only':
            # 快路径3：纯搜索（无打开/生成等复合动作）
            theme = _extract_theme(normalized_text)
            is_chinese = any('\u4e00' <= c <= '\u9fff' for c in theme)
            search_url = f"https://www.baidu.com/s?wd={urllib.parse.quote(theme)}" if is_chinese else f"https://www.google.com/search?q={urllib.parse.quote(theme)}"
            commands.append(Command(
                tool="app:launch", type="write",
                params={"path": "msedge.exe", "url": search_url},
                reason=f"搜索「{theme}」", confidence=0.92, risk="low",
                require_confirmation=False, auto_execute=True,
            ))
            reply_text = f"正在搜索「{theme}」。"
            analysis = f"识别到搜索请求: {theme}"
            review_source = 'local_rule'
            used_voice_context = True

        else:
            # ===== LLM 分解路径：所有复合/模糊指令 =====
            from app.services.llm.generator import generate_structured
            llm_ok = False
            try:
                structured = await generate_structured(
                    normalized_text, payload.mode,
                    system_context=payload.system_context,
                    voice_context=merged_voice_context,
                )
                parsed = structured.get("parsed")
                if parsed and isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict) and item.get("tool"):
                            tool = item["tool"]
                            params = item.get("params", {})
                            confidence = item.get("confidence", 0.8)
                            reasoning = item.get("reasoning", "")
                            cmd_type = "write" if tool in ("app:launch", "ide:launch", "content:generate", "disk:cleanup", "temp:cleanup", "clipboard:write", "notify") else "read"
                            if tool == "process:kill":
                                cmd_type = "destructive"
                            is_dangerous = cmd_type == "destructive"
                            commands.append(Command(
                                tool=tool,
                                type=cmd_type,
                                params=params,
                                reason=reasoning or tool,
                                confidence=confidence,
                                risk="high" if is_dangerous else "low",
                                require_confirmation=is_dangerous,
                                auto_execute=not is_dangerous,
                            ))
                    llm_ok = True
                    reply_text = f"已为你规划 {len(commands)} 个任务。"
                    analysis = f"LLM分解: {normalized_text} → {len(commands)} 个任务"
                    review_source = 'llm_structured'
                    used_voice_context = True
                elif parsed and isinstance(parsed, dict) and parsed.get("commands"):
                    for item in parsed["commands"]:
                        if isinstance(item, dict) and item.get("tool"):
                            tool = item["tool"]
                            params = item.get("params", {})
                            confidence = item.get("confidence", 0.8)
                            reasoning = item.get("reasoning", item.get("reason", ""))
                            cmd_type = item.get("type", "read")
                            is_dangerous = cmd_type == "destructive" or item.get("risk") == "high"
                            commands.append(Command(
                                tool=tool,
                                type=cmd_type,
                                params=params,
                                reason=reasoning or tool,
                                confidence=confidence,
                                risk="high" if is_dangerous else "low",
                                require_confirmation=is_dangerous,
                                auto_execute=not is_dangerous,
                            ))
                    llm_ok = True
                    reply_text = f"已为你规划 {len(commands)} 个任务。"
                    analysis = f"LLM分解: {normalized_text} → {len(commands)} 个任务"
                    review_source = 'llm_structured'
                    used_voice_context = True
            except Exception as e:
                print(f"[Voice] LLM分解失败: {e}")

            if not llm_ok:
                # LLM 不可用 → 本地降级兜底
                fallback_cmds = _local_fallback_decompose(normalized_text)
                if fallback_cmds:
                    commands = fallback_cmds
                    reply_text = f"已为你规划 {len(commands)} 个任务（本地模式）。"
                    analysis = f"本地降级分解: {normalized_text}"
                    review_source = 'local_fallback'
                    used_fallback = True
                    fallback_reason = 'LLMUnavailable'
                else:
                    reply_text = "暂时无法处理此指令，请稍后再试。"
                    analysis = ""
                    review_source = 'local_fallback'
                    used_fallback = True
                    fallback_reason = 'LLMUnavailable'
                used_voice_context = True

        # 🆕 桌面控制意图：严格过滤，只允许桌面控制命令
        if intent == 'desktop_control' and commands:
            allowed_tools = {'app:launch', 'browser:open', 'browser:search', 'process:kill', 'process:list', 'process:top', 'window:close', 'app:close', 'content:generate', 'ide:launch', 'keyboard:type', 'system:info', 'disk:list', 'temp:scan'}
            original_tools = [c.tool for c in commands]
            commands = [c for c in commands if c.tool in allowed_tools]
            filtered = [t for t in original_tools if t not in allowed_tools]
            if filtered:
                print(f"[Voice] 桌面意图过滤掉非桌面命令: {filtered}")

        # 🆕 后端去重：相同工具+参数只保留第一个
        if commands:
            seen = set()
            unique_commands = []
            for cmd in commands:
                tool = cmd.get("tool") if isinstance(cmd, dict) else cmd.tool
                params = cmd.get("params") if isinstance(cmd, dict) else cmd.params
                sig = f"{tool}:{json.dumps(params, sort_keys=True)}"
                if sig not in seen:
                    seen.add(sig)
                    unique_commands.append(cmd)
            commands = unique_commands

        # 🆕 最终安全过滤：过滤无效 process:kill
        commands_dict = [command if isinstance(command, dict) else command.model_dump() for command in commands]
        if commands_dict:
            commands_dict = filter_invalid_commands(commands_dict)

        # ========== 回复生成 ==========
        if commands_dict:
            cmd_reasons = [c.get('reason', c.get('tool', 'unknown')) for c in commands_dict]
            reply = f"已规划 {len(commands_dict)} 个任务：{', '.join(cmd_reasons)}"
            speech_text = f"已规划 {len(commands_dict)} 个任务"
            agent_analysis = analysis or f"已识别到 {len(commands_dict)} 条可执行命令"
            agent_thinking = ""
            agent_advice = reply_text
            agent_risk_warning = ""
            review_notes = None
            used_system_context = bool(payload.system_context)
            used_voice_context = True
        else:
            reply = reply_text or "暂时无法处理此指令。"
            speech_text = reply[:120]
            agent_analysis = analysis or ""
            agent_thinking = ""
            agent_advice = ""
            agent_risk_warning = ""
            review_notes = None
            used_system_context = bool(payload.system_context)
            used_voice_context = True

        # ========== TTS 处理 ==========
        fallback_tts_enabled = True  # 简化处理
        fallback_tts_summary = cleaner.clean(str(reply)[:120])
        fallback_enter_history = True

        tts_content, display_content = separator.separate(
            full_response=reply,
            user_intent=intent,
        )
        reply = display_content
        speech_text = cleaner.clean(tts_content or speech_text or f'语音指令已处理。{reply}')
        
        tts_audio_base64: str | None = None
        tts_mime_type: str | None = None
        speech_provider = 'browser'
        tts_fallback_used = True
        tts_available = False

        runtime = voice_provider.get_runtime_config()

        if speech_text.strip():
            try:
                synthesized = await voice_provider.synthesize_text(text=speech_text)
                tts_audio_base64 = str(synthesized.get('audio_base64', '')) or None
                tts_mime_type = str(synthesized.get('mime_type', 'audio/mpeg'))
                speech_provider = str(synthesized.get('provider', 'browser'))
                tts_fallback_used = bool(synthesized.get('fallback_used', False)) or speech_provider in {'mock', 'browser'}
                tts_available = bool(runtime.get('tts_enabled', False))
            except Exception:
                pass  # 保持浏览器回退

        # ========== 历史记录 ==========
        if conversation_id is not None and get_conversation(conversation_id):
            create_voice_turn(conversation_id, payload.transcript, merged_voice_context)
            add_conversation_message(
                conversation_id,
                'user',
                context_manager.clean_content(payload.transcript),
                {
                    **merged_voice_context,
                    'type': 'user_input',
                },
            )
            add_assistant_output(
                conversation_id,
                reply if fallback_enter_history else "（此前服务暂时不可用，已简化回复）",
                review_source=review_source,
                used_system_context=used_system_context,
                used_voice_context=used_voice_context,
                fallback_reason=fallback_reason,
                system_snapshot=payload.system_context or merged_voice_context,
                extra_meta={
                    'used_fallback': used_fallback,
                    'enter_history': fallback_enter_history,
                    'tts_enabled': fallback_tts_enabled,
                },
            )

        # ========== 最终返回 ==========
        return VoiceCommandResponse(
            transcript=payload.transcript,
            normalized_text=normalized_text,
            intent=intent,
            reply=reply,
            analysis=agent_analysis,
            thinking=agent_thinking,
            advice=agent_advice,
            risk_warning=agent_risk_warning,
            review_notes=None,
            review_source=review_source,
            speech_text=speech_text,
            tts_content=tts_content,
            tts_required=bool((tts_content or '').strip()),
            used_system_context=used_system_context,
            used_voice_context=used_voice_context,
            used_fallback=used_fallback,
            fallback_reason=fallback_reason,
            speech_provider=speech_provider,
            tts_audio_base64=tts_audio_base64,
            tts_mime_type=tts_mime_type,
            tts_fallback_used=tts_fallback_used,
            tts_available=tts_available,
            browser_tts_recommended=tts_fallback_used or not tts_audio_base64,
            speech_capabilities={
                'supports_cloud_stt': bool(runtime.get('stt_enabled', False)),
                'supports_cloud_tts': bool(runtime.get('tts_enabled', False)),
                'supports_wake_word': True,
                'supports_long_session': True,
                'supports_interruption_control': True,
            },
            commands=commands_dict,
            command_execution_mode='local_first',
            context_info=context_info,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        fallback_reply = '当前系统监控服务暂时不可用。\n\n请先打开任务管理器，按 CPU 排序，优先检查占用最高的非必要进程。'
        fallback_tts, fallback_display = separator.separate(full_response=fallback_reply, user_intent='error')
        return VoiceCommandResponse(
            transcript=payload.transcript, normalized_text=payload.transcript.strip(), intent='error',
            reply=fallback_display, review_notes=None, review_source='error_fallback',
            speech_text=cleaner.clean(fallback_tts), tts_content=cleaner.clean(fallback_tts),
            tts_required=len(fallback_tts.strip()) > 10, used_system_context=False, used_voice_context=False,
            used_fallback=True, fallback_reason='VoiceCommandUnhandledError',
            speech_provider='mock', tts_audio_base64=None, tts_mime_type=None,
            tts_fallback_used=True, tts_available=False, browser_tts_recommended=True,
            speech_capabilities={
                'supports_cloud_stt': False, 'supports_cloud_tts': False,
                'supports_wake_word': False, 'supports_long_session': False, 'supports_interruption_control': False,
            },
            commands=[], command_execution_mode='error_fallback',
            context_info={'original_turns': 0, 'optimized_turns': 0, 'history_summary': None,
                         'context_strategy': context_manager.strategy.value, 'estimated_tokens': 0,
                         'history_was_cleaned': False, 'history_was_truncated': False},
        )