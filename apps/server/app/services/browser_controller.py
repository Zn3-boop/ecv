"""
浏览器控制服务 - Edge/Chrome标签页操作
"""

import subprocess
import json
import re
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class BrowserResult:
    """浏览器操作结果"""
    success: bool
    message: str
    data: Any = None
    error: str | None = None


def _run_powershell(script: str) -> tuple[bool, str]:
    """执行PowerShell脚本"""
    try:
        result = subprocess.run(
            ['powershell', '-Command', script],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stdout
    except Exception as e:
        return False, str(e)


def get_edge_tabs() -> BrowserResult:
    """
    获取Edge浏览器所有标签页信息
    
    Returns:
        BrowserResult: 标签页列表
    """
    script = '''
    $tabs = @()
    $procs = Get-Process msedge -ErrorAction SilentlyContinue
    if ($procs) {
        foreach ($proc in $procs) {
            if ($proc.MainWindowTitle -ne "") {
                $title = $proc.MainWindowTitle
                $url = ""
                # 提取URL（通常在标题末尾）
                if ($title -match " - (.+) - Microsoft Edge$") {
                    $url = $matches[1]
                    $title = $title -replace " - .+ - Microsoft Edge$", ""
                } elseif ($title -match " - (.+) - 个人 - Microsoft Edge$") {
                    $url = $matches[1]
                    $title = $title -replace " - .+ - 个人 - Microsoft Edge$", ""
                }
                $tabs += @{
                    "title" = $title
                    "url" = $url
                    "pid" = $proc.Id
                }
            }
        }
    }
    $tabs | ConvertTo-Json -Compress
    '''
    
    success, output = _run_powershell(script)
    
    if success and output.strip():
        try:
            # 处理单个对象 vs 数组
            if output.strip().startswith('{'):
                tabs = [json.loads(output.strip())]
            else:
                tabs = json.loads(output.strip())
            
            return BrowserResult(
                success=True,
                message=f"找到 {len(tabs)} 个Edge标签页",
                data={"tabs": tabs}
            )
        except json.JSONDecodeError:
            return BrowserResult(
                success=True,
                message="找到标签页（解析失败）",
                data={"raw": output}
            )
    else:
        return BrowserResult(
            success=True,
            message="Edge未运行或无标签页",
            data={"tabs": []}
        )


def get_chrome_tabs() -> BrowserResult:
    """
    获取Chrome浏览器所有标签页信息
    
    Returns:
        BrowserResult: 标签页列表
    """
    script = '''
    $tabs = @()
    $procs = Get-Process chrome -ErrorAction SilentlyContinue
    if ($procs) {
        foreach ($proc in $procs) {
            if ($proc.MainWindowTitle -ne "") {
                $title = $proc.MainWindowTitle
                $url = ""
                if ($title -match " - Google Chrome$") {
                    $url = $title -replace " - Google Chrome$", ""
                }
                $tabs += @{
                    "title" = $title
                    "url" = $url
                    "pid" = $proc.Id
                }
            }
        }
    }
    $tabs | ConvertTo-Json -Compress
    '''
    
    success, output = _run_powershell(script)
    
    if success and output.strip():
        try:
            if output.strip().startswith('{'):
                tabs = [json.loads(output.strip())]
            else:
                tabs = json.loads(output.strip())
            
            return BrowserResult(
                success=True,
                message=f"找到 {len(tabs)} 个Chrome标签页",
                data={"tabs": tabs}
            )
        except json.JSONDecodeError:
            return BrowserResult(
                success=True,
                message="找到标签页（解析失败）",
                data={"raw": output}
            )
    else:
        return BrowserResult(
            success=True,
            message="Chrome未运行或无标签页",
            data={"tabs": []}
        )


def open_url(url: str, browser: str = "edge") -> BrowserResult:
    """
    在浏览器中打开URL
    
    Args:
        url: 目标URL
        browser: 浏览器类型 ("edge" 或 "chrome")
        
    Returns:
        BrowserResult: 操作结果
    """
    try:
        browser_lower = browser.lower()
        if browser_lower == "chrome":
            result = subprocess.run(
                ['cmd', '/c', 'start', 'chrome', url],
                shell=False, capture_output=True, timeout=10
            )
        else:  # edge
            result = subprocess.run(
                ['cmd', '/c', 'start', 'msedge', url],
                shell=False, capture_output=True, timeout=10
            )

        return BrowserResult(
            success=True,
            message=f"已在{browser}中打开 {url}",
            data={"url": url, "browser": browser}
        )
        
    except Exception as e:
        return BrowserResult(
            success=False,
            message=f"打开URL失败",
            error=str(e)
        )


def close_tab_by_title(title_pattern: str, browser: str = "edge") -> BrowserResult:
    """
    根据标题关闭标签页
    
    Args:
        title_pattern: 标题关键词
        browser: 浏览器类型
        
    Returns:
        BrowserResult: 操作结果
    """
    # 注意：通过进程关闭标签页比较复杂，这里只提供查找功能
    if browser.lower() == "chrome":
        get_tabs_func = get_chrome_tabs
        process_name = "chrome"
    else:
        get_tabs_func = get_edge_tabs
        process_name = "msedge"
    
    result = get_tabs_func()
    
    if result.success and result.data.get("tabs"):
        matching = [t for t in result.data["tabs"] if title_pattern.lower() in t.get("title", "").lower()]
        
        if matching:
            return BrowserResult(
                success=True,
                message=f"找到 {len(matching)} 个匹配的标签页",
                data={"matching_tabs": matching}
            )
    
    return BrowserResult(
        success=True,
        message=f"未找到包含 '{title_pattern}' 的标签页",
        data={"matching_tabs": []}
    )


def get_all_browser_info() -> BrowserResult:
    """
    获取所有浏览器（Edge和Chrome）的标签页信息
    
    Returns:
        BrowserResult: 所有标签页信息
    """
    edge_result = get_edge_tabs()
    chrome_result = get_chrome_tabs()
    
    return BrowserResult(
        success=True,
        message="浏览器信息获取完成",
        data={
            "edge_tabs": edge_result.data.get("tabs", []) if edge_result.success else [],
            "chrome_tabs": chrome_result.data.get("tabs", []) if chrome_result.success else []
        }
    )


def take_browser_screenshot(browser: str = "edge") -> BrowserResult:
    """
    获取浏览器当前页面的截图（通过窗口截图）
    
    Args:
        browser: 浏览器类型
        
    Returns:
        BrowserResult: 截图结果（返回窗口信息）
    """
    if browser.lower() == "chrome":
        process_name = "chrome"
        window_title_pattern = "*chrome*"
    else:
        process_name = "msedge"
        window_title_pattern = "*microsoft edge*"
    
    script = f'''
    $proc = Get-Process {process_name} -ErrorAction SilentlyContinue | Where-Object {{$_.MainWindowTitle -ne ""}} | Select-Object -First 1
    if ($proc) {{
        @{{
            "exists" = $true
            "title" = $proc.MainWindowTitle
            "pid" = $proc.Id
            "message" = "浏览器正在运行"
        }} | ConvertTo-Json
    }} else {{
        @{{
            "exists" = $false
            "message" = "浏览器未运行"
        }} | ConvertTo-Json
    }}
    '''
    
    success, output = _run_powershell(script)
    
    if success and output.strip():
        try:
            info = json.loads(output.strip())
            return BrowserResult(
                success=True,
                message=info.get("message", "浏览器信息获取完成"),
                data=info
            )
        except:
            pass
    
    return BrowserResult(
        success=False,
        message="获取浏览器信息失败",
        error="未知错误"
    )