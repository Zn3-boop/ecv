"""
桌面应用控制服务 - 通用Windows应用控制
"""

import subprocess
import os
import winreg
import re
from dataclasses import dataclass
from typing import Any, Optional

# 进程黑名单：禁止通过 close_app 结束系统关键进程
_PROTECTED_PROCESS_NAMES = {
    "system", "idle", "registry", "smss.exe", "csrss.exe", "wininit.exe",
    "winlogon.exe", "services.exe", "lsass.exe", "svchost.exe", "explorer.exe",
    "electron.exe", "dwm.exe",
}

# 安全路径白名单正则：盘符开头，只允许路径字符
_SAFE_PATH_PATTERN = re.compile(r'^[A-Za-z]:[\\/][A-Za-z0-9 _\-.\\/:]*$')


def _sanitize_ps_string(value: str) -> str:
    """转义 PowerShell 字符串中的危险字符"""
    if not value:
        return ""
    # 替换单引号为双单引号（PowerShell 转义方式）
    return value.replace("'", "''")


def _validate_save_path(path: str) -> str:
    """校验保存路径，防止注入"""
    if not path:
        return ""
    cleaned = path.strip()
    if not _SAFE_PATH_PATTERN.match(cleaned):
        raise ValueError(f"非法路径格式: {path}")
    # 禁止路径遍历
    if ".." in cleaned:
        raise ValueError("路径不允许包含 .. ")
    return cleaned


@dataclass
class AppResult:
    """应用操作结果"""
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


def find_app_path(app_name: str) -> AppResult:
    """
    查找应用程序路径
    
    Args:
        app_name: 应用名称
        
    Returns:
        AppResult: 查找结果
    """
    # 常见应用的默认路径
    common_paths = {
        "notepad": r"C:\Windows\System32\notepad.exe",
        "记事本": r"C:\Windows\System32\notepad.exe",
        "calc": r"C:\Windows\System32\calc.exe",
        "计算器": r"C:\Windows\System32\calc.exe",
        "word": r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
        "excel": r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
        "ppt": r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
        "powershell": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        "cmd": r"C:\Windows\System32\cmd.exe",
        "explorer": r"C:\Windows\explorer.exe",
        "资源管理器": r"C:\Windows\explorer.exe",
        "taskmgr": r"C:\Windows\System32\taskmgr.exe",
        "任务管理器": r"C:\Windows\System32\taskmgr.exe",
        "control": r"C:\Windows\System32\control.exe",
        "控制面板": r"C:\Windows\System32\control.exe",
        "mspaint": r"C:\Windows\System32\mspaint.exe",
        "画图": r"C:\Windows\System32\mspaint.exe",
        # Windows系统设置 (通过URI打开，带主页/应用/个性化等页面)
        "设置": r"C:\Windows\System32\ms-settings:",
        "系统设置": r"C:\Windows\System32\ms-settings:",
        "windows设置": r"C:\Windows\System32\ms-settings:",
        "settings": r"C:\Windows\System32\ms-settings:",
    }
    
    name_lower = app_name.lower()
    
    # 检查已知路径
    if name_lower in common_paths:
        path = common_paths[name_lower]
        if os.path.exists(path):
            return AppResult(
                success=True,
                message=f"找到 {app_name}",
                data={"path": path, "name": app_name}
            )
    
    # 搜索注册表
    script = f'''
    $apps = @()
    $keys = @(
        "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths",
        "HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\App Paths",
        "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths"
    )
    foreach ($key in $keys) {{
        if (Test-Path $key) {{
            Get-ChildItem $key -ErrorAction SilentlyContinue | ForEach-Object {{
                $path = (Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue)."(Default)"
                if ($path) {{
                    $apps += @{{
                        "name" = $_.PSChildName
                        "path" = $path
                    }}
                }}
            }}
        }}
    }}
    $apps | ConvertTo-Json -Compress
    '''
    
    success, output = _run_powershell(script)
    
    if success and output.strip():
        try:
            import json
            if output.strip().startswith('{'):
                apps = [json.loads(output.strip())]
            else:
                apps = json.loads(output.strip())
            
            # 匹配应用名
            for app in apps:
                if app_name.lower() in app.get("name", "").lower():
                    return AppResult(
                        success=True,
                        message=f"找到 {app.get('name')}",
                        data={"path": app.get("path"), "name": app.get("name")}
                    )
        except:
            pass
    
    return AppResult(
        success=False,
        message=f"未找到应用 {app_name}",
        error="应用未安装或路径未知"
    )


def open_app(app_path: str) -> AppResult:
    """
    打开应用程序
    
    Args:
        app_path: 应用路径或名称
        
    Returns:
        AppResult: 打开结果
    """
    try:
        # 如果不是路径，尝试查找
        if not os.path.exists(app_path):
            find_result = find_app_path(app_path)
            if find_result.success:
                app_path = find_result.data["path"]
            else:
                return AppResult(
                    success=False,
                    message=f"无法打开 {app_path}",
                    error=f"路径不存在: {app_path}"
                )
        
        # 特殊处理 Windows URI (如 ms-settings:)
        if app_path.startswith("ms-") and ":" in app_path:
            subprocess.Popen(["cmd", "/c", "start", "", app_path], shell=False)
            return AppResult(
                success=True,
                message=f"已打开 Windows {app_path.split(':')[0].replace('ms-', '').title()} 设置",
                data={"path": app_path, "type": "uri"}
            )
        
        subprocess.Popen([app_path])
        
        return AppResult(
            success=True,
            message=f"已启动 {os.path.basename(app_path)}",
            data={"path": app_path}
        )
        
    except Exception as e:
        return AppResult(
            success=False,
            message=f"启动失败",
            error=str(e)
        )


def open_file(file_path: str, app_name: str = None) -> AppResult:
    """
    用指定应用打开文件
    
    Args:
        file_path: 文件路径
        app_name: 应用名称（可选，不指定则用默认程序打开）
        
    Returns:
        AppResult: 打开结果
    """
    try:
        if not os.path.exists(file_path):
            return AppResult(
                success=False,
                message="文件不存在",
                error=f"{file_path} 不存在"
            )
        
        if app_name:
            # 查找应用路径
            find_result = find_app_path(app_name)
            if find_result.success:
                app_path = find_result.data["path"]
                subprocess.Popen([app_path, file_path])
                return AppResult(
                    success=True,
                    message=f"用 {app_name} 打开了 {os.path.basename(file_path)}",
                    data={"file": file_path, "app": app_name}
                )
            else:
                return AppResult(
                    success=False,
                    message=f"找不到应用 {app_name}",
                    error=find_result.error
                )
        else:
            # 用默认程序打开
            os.startfile(file_path)
            return AppResult(
                success=True,
                message=f"已用默认程序打开 {os.path.basename(file_path)}",
                data={"file": file_path}
            )
            
    except Exception as e:
        return AppResult(
            success=False,
            message="打开文件失败",
            error=str(e)
        )


def close_app(app_name: str) -> AppResult:
    """
    关闭应用程序

    Args:
        app_name: 应用名称（不含扩展名）

    Returns:
        AppResult: 关闭结果
    """
    # 进程黑名单校验：禁止结束系统关键进程
    name_lower = (app_name or "").strip().lower()
    if not name_lower:
        return AppResult(success=False, message="应用名不能为空", error="app_name is empty")
    # 补 .exe 后缀检查
    check_name = name_lower if name_lower.endswith('.exe') else f"{name_lower}.exe"
    if check_name in _PROTECTED_PROCESS_NAMES or name_lower in _PROTECTED_PROCESS_NAMES:
        return AppResult(
            success=False,
            message=f"进程 {app_name} 是系统关键进程，禁止结束",
            error="protected process"
        )

    safe_name = _sanitize_ps_string(name_lower)
    script = f'''
    $proc = Get-Process '{safe_name}' -ErrorAction SilentlyContinue
    if ($proc) {{
        $proc | Stop-Process -Force
        @{{ "success" = $true; "closed" = $proc.Count }} | ConvertTo-Json
    }} else {{
        @{{ "success" = $false; "closed" = 0 }} | ConvertTo-Json
    }}
    '''
    
    success, output = _run_powershell(script)
    
    if success and output.strip():
        try:
            import json
            result = json.loads(output.strip())
            if result.get("success"):
                return AppResult(
                    success=True,
                    message=f"已关闭 {result.get('closed')} 个 {app_name} 进程",
                    data={"closed": result.get("closed")}
                )
        except:
            pass
    
    return AppResult(
        success=True,
        message=f"未找到运行中的 {app_name} 进程",
        data={"closed": 0}
    )


def list_running_apps() -> AppResult:
    """
    列出正在运行的应用
    
    Returns:
        AppResult: 运行中的应用列表
    """
    script = '''
    Get-Process | Where-Object {$_.MainWindowTitle -ne ""} | Select-Object Name, ProcessName, Id, MainWindowTitle | ConvertTo-Json -Compress
    '''
    
    success, output = _run_powershell(script)
    
    if success and output.strip():
        try:
            import json
            if output.strip().startswith('{'):
                apps = [json.loads(output.strip())]
            else:
                apps = json.loads(output.strip())
            
            return AppResult(
                success=True,
                message=f"找到 {len(apps)} 个正在运行的应用",
                data={"apps": apps}
            )
        except:
            pass
    
    return AppResult(
        success=True,
        message="未找到正在运行的应用",
        data={"apps": []}
    )


def take_screenshot(save_path: str = None) -> AppResult:
    """
    截取屏幕截图
    
    Args:
        save_path: 保存路径（可选，默认保存到桌面）
        
    Returns:
        AppResult: 截图结果
    """
    import datetime

    if not save_path:
        save_path = os.path.join(
            os.path.expanduser("~"),
            "Desktop",
            f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        )
    else:
        try:
            save_path = _validate_save_path(save_path)
        except ValueError as e:
            return AppResult(success=False, message="截图失败", error=str(e))

    safe_path = _sanitize_ps_string(save_path)
    script = f'''
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen
    $bitmap = New-Object System.Drawing.Bitmap($screen.Bounds.Width, $screen.Bounds.Height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen($screen.Bounds.Location, [System.Drawing.Point]::Empty, $screen.Bounds.Size)
    $bitmap.Save('{safe_path}')
    $graphics.Dispose()
    $bitmap.Dispose()
    "OK"
    '''
    
    success, output = _run_powershell(script)
    
    if success and "OK" in output:
        return AppResult(
            success=True,
            message=f"截图已保存到 {save_path}",
            data={"path": save_path}
        )
    else:
        return AppResult(
            success=False,
            message="截图失败",
            error=output
        )