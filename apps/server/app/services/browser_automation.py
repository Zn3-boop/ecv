"""
浏览器自动化服务 - 搜索和导航控制
原有browser_controller的代码
"""

import subprocess
import re
from dataclasses import dataclass, field
from typing import Literal


# ============== Prompt 模板 ==============

BROWSER_PROMPT_TEMPLATE = """你是一个浏览器控制助手。用户会用自然语言描述他们想要执行的浏览器操作。

## 支持的操作类型

1. **search** - 搜索
   - 用户想搜索某些内容
   - 提取关键词作为 search_query

2. **open** - 打开URL
   - 用户想打开一个特定的URL
   - 提取URL作为 url

3. **navigate** - 导航
   - 用户想导航到某个网站
   - 提取URL作为 url

## 浏览器偏好

- edge / chrome / firefox / default（默认系统浏览器）

## 输出格式

返回JSON格式：
{
  "type": "search/open/navigate",
  "url": "具体的网址（如果有）",
  "search_query": "搜索关键词（如果是搜索）",
  "browser": "edge/chrome/firefox/default",
  "new_window": true/false,
  "raw_command": "原始用户命令"
}

## 示例

输入："用Chrome搜索Python教程"
输出：{"type": "search", "search_query": "Python教程", "browser": "chrome", "new_window": true, "raw_command": "用Chrome搜索Python教程"}

输入："打开百度"
输出：{"type": "open", "url": "https://www.baidu.com", "browser": "default", "new_window": true, "raw_command": "打开百度"}
"""


# ============== 数据模型 ==============

@dataclass
class BrowserAction:
    """浏览器操作"""
    type: Literal["search", "open", "navigate"]
    url: str | None = None
    search_query: str | None = None
    browser: str = "default"
    new_window: bool = True
    raw_command: str = ""


# ============== 解析函数 ==============

def parse_browser_intent(command: str) -> BrowserAction:
    """
    解析浏览器意图
    
    Args:
        command: 用户自然语言命令
        
    Returns:
        BrowserAction: 解析后的操作
    """
    command_lower = command.lower()
    
    # 判断操作类型
    action_type = "open"
    if any(kw in command_lower for kw in ["搜索", "search", "查一下", "帮我搜"]):
        action_type = "search"
    elif any(kw in command_lower for kw in ["导航", "navigate", "去", "转到", "进入"]):
        action_type = "navigate"
    
    # 提取搜索关键词
    search_query = None
    if action_type == "search":
        # 移除搜索相关关键词，提取剩余部分作为搜索词
        temp = command
        for kw in ["搜索", "search", "搜一下", "帮我搜", "查一下"]:
            temp = temp.replace(kw, "")
        for kw in ["用chrome", "用edge", "用firefox", "chrome", "edge", "firefox"]:
            temp = temp.replace(kw, "")
        search_query = temp.strip()
    
    # 判断浏览器
    browser = "default"
    if "chrome" in command_lower:
        browser = "chrome"
    elif "edge" in command_lower:
        browser = "edge"
    elif "firefox" in command_lower:
        browser = "firefox"
    
    # 判断是否新窗口
    new_window = True
    
    # 提取URL
    url = None
    if action_type in ["open", "navigate"]:
        # 尝试提取URL
        url_patterns = [
            r'https?://[^\s]+',
            r'www\.[^\s]+\.[^\s]+',
        ]
        for pattern in url_patterns:
            matches = re.findall(pattern, command)
            if matches:
                url = matches[0]
                if not url.startswith('http'):
                    url = 'https://' + url
                break
        
        # 如果没有URL，使用常用网站映射
        if not url:
            website_map = {
                "百度": "https://www.baidu.com",
                "google": "https://www.google.com",
                "github": "https://github.com",
                "bilibili": "https://www.bilibili.com",
                "微博": "https://weibo.com",
                "知乎": "https://www.zhihu.com",
            }
            for name, site_url in website_map.items():
                if name in command:
                    url = site_url
                    break
    
    return BrowserAction(
        type=action_type,
        url=url,
        search_query=search_query,
        browser=browser,
        new_window=new_window,
        raw_command=command,
    )


# ============== 搜索 URL 构建 ==============

def build_search_url(action: BrowserAction) -> str:
    """
    构建搜索URL
    
    Args:
        action: 浏览器操作
        
    Returns:
        str: 搜索URL
    """
    if action.search_query:
        encoded_query = action.search_query.replace(' ', '+')
        return f"https://www.bing.com/search?q={encoded_query}"
    return ""


# ============== 浏览器命令执行 ==============

def execute_browser_action(action: BrowserAction) -> dict:
    """
    执行浏览器操作
    
    Args:
        action: 浏览器操作
        
    Returns:
        dict: 执行结果
    """
    try:
        # 确定浏览器命令
        browser_cmd = _get_browser_cmd(action.browser)
        
        # 构建URL
        url = action.url
        if action.type == "search":
            url = build_search_url(action)
        
        if not url:
            return {
                "success": False,
                "error": "无法构建URL",
                "browser": action.browser,
            }
        
        # 构建完整命令
        cmd_parts = _build_open_command(browser_cmd, url, action.new_window)

        # 执行
        result = subprocess.run(
            cmd_parts,
            shell=False,
            capture_output=True,
            timeout=10,
        )

        return {
            "success": result.returncode == 0,
            "message": f"已在{_get_browser_name(action.browser)}中打开",
            "browser": action.browser,
            "url": url,
            "command": ' '.join(cmd_parts),
        }
        
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "执行超时",
            "browser": action.browser,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "browser": action.browser,
        }


def _get_browser_cmd(browser: str) -> str:
    """获取浏览器启动命令"""
    if browser == "chrome":
        return "chrome"
    elif browser == "firefox":
        return "firefox"
    elif browser == "edge":
        return "msedge"
    else:
        # 默认浏览器
        return "start"


def _get_browser_name(browser: str) -> str:
    """获取浏览器名称"""
    names = {
        "chrome": "Chrome",
        "firefox": "Firefox",
        "edge": "Edge",
        "default": "默认浏览器",
    }
    return names.get(browser, "默认浏览器")


def _build_open_command(browser_cmd: str, url: str, new_window: bool) -> list[str]:
    """构建打开命令的参数数组（避免 shell=True）"""
    if browser_cmd == "start":
        return ['cmd', '/c', 'start', '', url]
    elif browser_cmd == "chrome":
        parts = ['cmd', '/c', 'start', 'chrome']
        if new_window:
            parts.append('--new-window')
        parts.append(url)
        return parts
    elif browser_cmd == "firefox":
        parts = ['cmd', '/c', 'start', 'firefox']
        if new_window:
            parts.append('-new-window')
        parts.append(url)
        return parts
    elif browser_cmd == "msedge":
        parts = ['cmd', '/c', 'start', 'msedge']
        if new_window:
            parts.append('-new-window')
        parts.append(url)
        return parts
    else:
        return ['cmd', '/c', 'start', '', url]


# ============== 格式化函数 ==============

def format_browser_action_json(action: BrowserAction) -> str:
    """格式化浏览器操作 为 JSON 字符串"""
    import json
    return json.dumps({
        "type": action.type,
        "url": action.url,
        "search_query": action.search_query,
        "browser": action.browser,
        "new_window": action.new_window,
        "raw_command": action.raw_command,
    }, ensure_ascii=False, indent=2)