"""
系统应用启动器服务

安全地启动 Windows 系统应用（记事本、计算器、资源管理器等）
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any

# 允许启动的白名单应用
APP_WHITELIST: dict[str, dict[str, Any]] = {
    "app:notepad": {
        "cmd": "notepad.exe",
        "args_template": '"{path}"',  # 支持打开指定文件，空路径则新建
        "is_dangerous": False,
        "category": "productivity",
    },
    "app:calc": {
        "cmd": "calc.exe",
        "args_template": "",
        "is_dangerous": False,
        "category": "productivity",
    },
    "app:explorer": {
        "cmd": "explorer.exe",
        "args_template": '"{path}"',  # 打开文件夹
        "is_dangerous": False,
        "category": "system",
    },
    "app:cmd": {
        "cmd": "cmd.exe",
        "args_template": "/k {command}",
        "is_dangerous": True,  # 需要二次确认
        "category": "system",
    },
    "app:powershell": {
        "cmd": "powershell.exe",
        "args_template": "-noexit -c {command}",
        "is_dangerous": True,
        "category": "system",
    },
    "app:browser": {
        "cmd": "start",
        "args_template": '"" "{path}"',
        "is_dangerous": False,
        "category": "network",
    },
    "app:wordpad": {
        "cmd": "write.exe",
        "args_template": '"{path}"',
        "is_dangerous": False,
        "category": "productivity",
    },
    "app:mspaint": {
        "cmd": "mspaint.exe",
        "args_template": '"{path}"',
        "is_dangerous": False,
        "category": "productivity",
    },
    "app:taskmgr": {
        "cmd": "taskmgr.exe",
        "args_template": "",
        "is_dangerous": False,
        "category": "system",
    },
    "app:control": {
        "cmd": "control.exe",
        "args_template": "",
        "is_dangerous": False,
        "category": "system",
    },
    "app:regedit": {
        "cmd": "regedit.exe",
        "args_template": '"{path}"',
        "is_dangerous": True,  # 注册表编辑器需要确认
        "category": "system",
    },
    "app:devmgmt": {
        "cmd": "devmgmt.msc",
        "args_template": "",
        "is_dangerous": False,
        "category": "system",
    },
    "app:services": {
        "cmd": "services.msc",
        "args_template": "",
        "is_dangerous": False,
        "category": "system",
    },
    # Office 应用
    "app:word": {
        "cmd": "winword.exe",
        "args_template": '"{path}"',
        "is_dangerous": False,
        "category": "office",
    },
    "app:excel": {
        "cmd": "excel.exe",
        "args_template": '"{path}"',
        "is_dangerous": False,
        "category": "office",
    },
    "app:powerpoint": {
        "cmd": "powerpnt.exe",
        "args_template": '"{path}"',
        "is_dangerous": False,
        "category": "office",
    },
    "app:outlook": {
        "cmd": "outlook.exe",
        "args_template": "",
        "is_dangerous": False,
        "category": "office",
    },
    # 应用商店
    "app:lenovo-store": {
        "cmd": "lenovo",
        "args_template": "",
        "is_dangerous": False,
        "category": "store",
    },
    "app:microsoft-store": {
        "cmd": "ms-windows-store://",
        "args_template": "",
        "is_dangerous": False,
        "category": "store",
    },
}


@dataclass
class SystemAppAction:
    """系统应用操作数据结构"""
    type: str = ""  # 'app:notepad' | 'app:calc' | ...
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    is_dangerous: bool = False
    priority: int = 50


@dataclass
class ExecuteResult:
    """执行结果"""
    success: bool
    executed_command: str
    pid: int | None = None
    error: str | None = None
    message: str = ""


def sanitize_path(input_path: str) -> str:
    """
    路径安全检查，防止命令注入
    
    Args:
        input_path: 用户提供的路径
        
    Returns:
        清理后的安全路径
    """
    if not input_path:
        return ""

    # 1. 清理首尾空白
    cleaned = input_path.strip()

    # 2. 移除可能导致问题的引号
    cleaned = cleaned.strip('"\'')

    # 3. 白名单方式：只保留路径安全字符（字母、数字、盘符、反斜杠、冒号、点、空格、连字符、下划线）
    cleaned = re.sub(r'[^A-Za-z0-9_\-.\ \\/:]', '', cleaned)

    # 4. 限制相对路径遍历
    cleaned = cleaned.replace('..', '')

    # 5. 规范化反斜杠（Windows路径）
    cleaned = cleaned.replace('/', '\\')

    return cleaned


def execute_system_app(action: SystemAppAction) -> ExecuteResult:
    """
    安全执行系统应用
    
    Args:
        action: 系统应用操作
        
    Returns:
        ExecuteResult: 执行结果
    """
    app_config = APP_WHITELIST.get(action.type)
    
    if not app_config:
        return ExecuteResult(
            success=False,
            executed_command="",
            error=f"未知应用类型: {action.type}，不在白名单内"
        )
    
    # 构建命令参数
    args_template = app_config["args_template"]
    params = action.params or {}
    
    # 替换路径占位符
    if "path" in params and params["path"]:
        safe_path = sanitize_path(str(params["path"]))
        args_template = args_template.replace("{path}", safe_path)
    else:
        args_template = args_template.replace("{path}", "")
    
    # 替换命令占位符
    if "command" in params and params["command"]:
        safe_command = sanitize_path(str(params["command"]))
        args_template = args_template.replace("{command}", safe_command)
    else:
        args_template = args_template.replace("{command}", "")
    
    # 清理残留的占位符
    args_template = re.sub(r'\{[a-z]+\}', '', args_template).strip()
    
    # 构建完整命令
    cmd = app_config["cmd"]
    
    # 构建命令参数数组（避免 shell=True）
    if cmd in ["lenovo", "ms-windows-store://"]:
        if cmd == "lenovo":
            cmd_parts = ['cmd', '/c', 'start', '', 'https://lenovo.com/software']
        else:
            cmd_parts = ['cmd', '/c', 'start', '', 'ms-windows-store://']
    elif cmd.endswith(".exe"):
        cmd_parts = ['cmd', '/c', 'start', '', cmd]
        if args_template:
            cmd_parts.append(args_template)
    else:
        # 执行 msc 文件（mmc 命令）
        cmd_parts = ['cmd', '/c', 'start', '', cmd]

    full_command = ' '.join(cmd_parts)

    try:
        result = subprocess.run(
            cmd_parts,
            shell=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            return ExecuteResult(
                success=True,
                executed_command=full_command,
                message=action.description or f"已启动 {action.type}",
            )
        else:
            return ExecuteResult(
                success=False,
                executed_command=full_command,
                error=result.stderr or f"执行失败，退出码: {result.returncode}"
            )
            
    except subprocess.TimeoutExpired:
        return ExecuteResult(
            success=False,
            executed_command=full_command,
            error="执行超时（10秒）"
        )
    except Exception as e:
        return ExecuteResult(
            success=False,
            executed_command=full_command,
            error=str(e)
        )


def parse_app_intent(user_command: str) -> SystemAppAction | None:
    """
    解析自然语言为结构化应用操作（兜底解析）
    
    当 LLM 输出模糊时，后端自动识别用户意图
    
    Args:
        user_command: 用户输入的自然语言命令
        
    Returns:
        SystemAppAction 或 None
    """
    lower = user_command.lower()
    
    # 记事本
    if "记事本" in user_command or "notepad" in lower:
        # 提取文件路径
        path_match = re.search(r'([a-zA-Z]:\\[^\s"\'<>]+)|"([a-zA-Z]:\\[^\"]+)"', user_command)
        file_path = path_match.group(1) or path_match.group(2) if path_match else None
        
        return SystemAppAction(
            type="app:notepad",
            params={"path": file_path} if file_path else {},
            description=file_path and f"用记事本打开 {file_path}" or "打开记事本",
            is_dangerous=False,
            priority=10,
        )
    
    # 计算器
    if "计算器" in user_command or "calc" in lower:
        return SystemAppAction(
            type="app:calc",
            params={},
            description="打开计算器",
            is_dangerous=False,
            priority=10,
        )
    
    # 资源管理器 / 文件夹
    if any(kw in user_command for kw in ["文件夹", "资源管理器", "打开目录", "explorer"]):
        path_match = re.search(r'([a-zA-Z]:\\[^\s"\'<>]+)', user_command)
        folder_path = path_match.group(1) if path_match else "."
        
        return SystemAppAction(
            type="app:explorer",
            params={"path": folder_path},
            description=f"打开资源管理器: {folder_path}",
            is_dangerous=False,
            priority=10,
        )
    
    # 任务管理器
    if "任务管理器" in user_command or "task manager" in lower or "taskmgr" in lower:
        return SystemAppAction(
            type="app:taskmgr",
            params={},
            description="打开任务管理器",
            is_dangerous=False,
            priority=10,
        )
    
    # 控制面板
    if "控制面板" in user_command or "control panel" in lower:
        return SystemAppAction(
            type="app:control",
            params={},
            description="打开控制面板",
            is_dangerous=False,
            priority=10,
        )
    
    # 命令行 / CMD
    if any(kw in lower for kw in ["命令行", "cmd", "命令提示符"]):
        return SystemAppAction(
            type="app:cmd",
            params={},
            description="打开命令提示符",
            is_dangerous=True,
            priority=10,
        )
    
    # PowerShell
    if "powershell" in lower:
        return SystemAppAction(
            type="app:powershell",
            params={},
            description="打开 PowerShell",
            is_dangerous=True,
            priority=10,
        )
    
    # 注册表编辑器
    if "注册表" in user_command or "regedit" in lower:
        return SystemAppAction(
            type="app:regedit",
            params={},
            description="打开注册表编辑器",
            is_dangerous=True,
            priority=10,
        )
    
    # 画图
    if "画图" in user_command or "mspaint" in lower:
        path_match = re.search(r'([a-zA-Z]:\\[^\s"\'<>]+)|"([a-zA-Z]:\\[^\"]+)"', user_command)
        file_path = path_match.group(1) or path_match.group(2) if path_match else None
        
        return SystemAppAction(
            type="app:mspaint",
            params={"path": file_path} if file_path else {},
            description=file_path and f"用画图打开 {file_path}" or "打开画图",
            is_dangerous=False,
            priority=10,
        )
    
    # 写字板
    if "写字板" in user_command or "wordpad" in lower:
        path_match = re.search(r'([a-zA-Z]:\\[^\s"\'<>]+)|"([a-zA-Z]:\\[^\"]+)"', user_command)
        file_path = path_match.group(1) or path_match.group(2) if path_match else None
        
        return SystemAppAction(
            type="app:wordpad",
            params={"path": file_path} if file_path else {},
            description=file_path and f"用写字板打开 {file_path}" or "打开写字板",
            is_dangerous=False,
            priority=10,
        )
    
    # 设备管理器
    if "设备管理器" in user_command or "device manager" in lower:
        return SystemAppAction(
            type="app:devmgmt",
            params={},
            description="打开设备管理器",
            is_dangerous=False,
            priority=10,
        )
    
    # 服务
    if "服务" in user_command and ("管理" in user_command or "services" in lower):
        return SystemAppAction(
            type="app:services",
            params={},
            description="打开服务管理器",
            is_dangerous=False,
            priority=10,
        )
    
    # Word 文档 - 匹配 "用Word打开 D:\xxx.docx" 或 "打开 Word xxx"
    if any(kw in user_command.lower() for kw in ["word", "winword"]):
        # 尝试匹配标准路径格式
        path_match = re.search(r'([A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*\.doc[x]?)', user_command)
        file_path = path_match.group(1) if path_match else None
        
        # 如果没匹配到标准路径，尝试提取"打开"后面的内容作为文件名
        if not file_path:
            # 匹配 "打开xxx" 或 "用Word打开xxx" 后面的非关键词内容
            for pattern in [r'(?:打开|用.*?打开)\s*(.+?)(?:\s*$|\s+[，,]|\s+[用用])', 
                           r'(?:打开|用.*?打开)\s*(\S+)']:
                name_match = re.search(pattern, user_command)
                if name_match:
                    potential_name = name_match.group(1).strip()
                    # 过滤掉关键词
                    if potential_name and potential_name.lower() not in ['word', 'winword', '打开', 'wps']:
                        file_path = potential_name
                        break
        
        return SystemAppAction(
            type="app:word",
            params={"path": file_path} if file_path else {},
            description=file_path and f"用Word打开 {file_path}" or "打开Word",
            is_dangerous=False,
            priority=10,
        )
    
    # Excel 表格
    if any(kw in user_command.lower() for kw in ["excel", "xlsx", "xls"]):
        path_match = re.search(r'([A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*\.xls[x]?)', user_command)
        file_path = path_match.group(1) if path_match else None
        return SystemAppAction(
            type="app:excel",
            params={"path": file_path} if file_path else {},
            description=file_path and f"用Excel打开 {file_path}" or "打开Excel",
            is_dangerous=False,
            priority=10,
        )
    
    # PowerPoint 演示文稿
    if any(kw in user_command.lower() for kw in ["powerpoint", "ppt", "幻灯片"]):
        path_match = re.search(r'([A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*\.ppt[x]?)', user_command)
        file_path = path_match.group(1) if path_match else None
        return SystemAppAction(
            type="app:powerpoint",
            params={"path": file_path} if file_path else {},
            description=file_path and f"用PowerPoint打开 {file_path}" or "打开PowerPoint",
            is_dangerous=False,
            priority=10,
        )
    
    # 联想应用商店
    if any(kw in lower for kw in ["联想应用商店", "lenovo应用商店", "联想商店", "lenovo store"]):
        return SystemAppAction(
            type="app:lenovo-store",
            params={},
            description="打开联想应用商店",
            is_dangerous=False,
            priority=10,
        )
    
    # 微软应用商店
    if any(kw in user_command for kw in ["微软应用商店", "Microsoft Store", "应用商店", "windows商店"]):
        return SystemAppAction(
            type="app:microsoft-store",
            params={},
            description="打开Microsoft Store",
            is_dangerous=False,
            priority=10,
        )
    
    # 打开文件（通用）
    if any(kw in lower for kw in ["打开文件", "打开 ", "open "]) and not any(kw in lower for kw in ["浏览器", "edge", "chrome"]):
        # 尝试匹配任何文件路径
        path_match = re.search(r'([a-zA-Z]:\\[^\s"\'<>]+)|"([a-zA-Z]:\\[^\"]+)"', user_command)
        if path_match:
            file_path = path_match.group(1) or path_match.group(2)
            # 根据扩展名判断类型
            if file_path.endswith('.doc') or file_path.endswith('.docx'):
                return SystemAppAction(
                    type="app:word",
                    params={"path": file_path},
                    description=f"用Word打开 {file_path}",
                    is_dangerous=False,
                    priority=10,
                )
            elif file_path.endswith('.xls') or file_path.endswith('.xlsx'):
                return SystemAppAction(
                    type="app:excel",
                    params={"path": file_path},
                    description=f"用Excel打开 {file_path}",
                    is_dangerous=False,
                    priority=10,
                )
            elif file_path.endswith('.ppt') or file_path.endswith('.pptx'):
                return SystemAppAction(
                    type="app:powerpoint",
                    params={"path": file_path},
                    description=f"用PowerPoint打开 {file_path}",
                    is_dangerous=False,
                    priority=10,
                )
            elif file_path.endswith('.txt'):
                return SystemAppAction(
                    type="app:notepad",
                    params={"path": file_path},
                    description=f"用记事本打开 {file_path}",
                    is_dangerous=False,
                    priority=10,
                )
            elif file_path.endswith('.png') or file_path.endswith('.jpg') or file_path.endswith('.jpeg') or file_path.endswith('.bmp'):
                return SystemAppAction(
                    type="app:mspaint",
                    params={"path": file_path},
                    description=f"用画图打开 {file_path}",
                    is_dangerous=False,
                    priority=10,
                )
            else:
                # 通用打开：使用 explorer /select 打开文件所在目录并选中
                return SystemAppAction(
                    type="app:explorer",
                    params={"path": file_path},
                    description=f"打开文件 {file_path}",
                    is_dangerous=False,
                    priority=10,
                )
    
    return None


def parse_memory_cleanup_intent(user_command: str) -> dict | None:
    """
    解析内存清理意图
    
    Args:
        user_command: 用户输入的自然语言命令
        
    Returns:
        dict 包含 target_percent 或 None
    """
    lower = user_command.lower()
    
    # 检测内存清理关键词
    memory_keywords = ["清理内存", "清内存", "降低内存", "释放内存", "内存使用率"]
    if not any(kw in lower for kw in memory_keywords):
        return None
    
    # 提取目标百分比
    target_percent = 75.0  # 默认目标
    
    # 尝试提取数字
    percent_match = re.search(r'(\d+)%?', user_command)
    if percent_match:
        target_percent = float(percent_match.group(1))
        if target_percent > 100:
            target_percent = 100
    
    return {
        "type": "memory:cleanup",
        "target_percent": target_percent,
        "description": f"清理内存，降低到 {target_percent}% 以下",
    }


def parse_file_search_intent(user_command: str) -> dict | None:
    """
    解析文件搜索意图
    
    Args:
        user_command: 用户输入的自然语言命令
        
    Returns:
        dict 包含 path 和 search_term 或 None
    """
    lower = user_command.lower()
    
    # 检测文件搜索关键词
    search_keywords = ["搜索", "查找", "找", "搜索文件", "找文件", "打开资源管理器"]
    if not any(kw in lower for kw in search_keywords):
        return None
    
    # 提取盘符和路径
    path = "D:\\"
    path_match = re.search(r'([A-Z]:\\[^"\'<>\\s]*)', user_command)
    if path_match:
        path = path_match.group(1)
        # 确保路径以反斜杠结尾
        if not path.endswith('\\'):
            path += '\\'
    
    # 提取搜索词
    search_term = ""
    for kw in ["搜索", "查找", "找"]:
        if kw in lower:
            idx = lower.find(kw)
            search_term = user_command[idx + len(kw):].strip()
            # 去掉常见前缀
            for prefix in ["一下", "一下", "找", " "]:
                if search_term.startswith(prefix):
                    search_term = search_term[len(prefix):].strip()
            break
    
    return {
        "type": "file:search",
        "path": path,
        "search_term": search_term,
        "description": f"在 {path} 中搜索 {search_term}",
    }


def cleanup_memory(target_percent: float = 75.0) -> dict[str, Any]:
    """
    清理内存，降低到指定百分比以下
    
    Args:
        target_percent: 目标内存使用率（百分比）
        
    Returns:
        dict: 包含清理结果的字典
    """
    import psutil
    
    # 获取当前内存使用率
    mem = psutil.virtual_memory()
    current_percent = mem.percent
    
    result = {
        "current_percent": current_percent,
        "target_percent": target_percent,
        "available_mb": mem.available / (1024 * 1024),
        "total_mb": mem.total / (1024 * 1024),
        "actions_taken": [],
        "success": True,
    }
    
    # 如果已经低于目标，直接返回
    if current_percent <= target_percent:
        result["message"] = f"内存使用率 {current_percent:.1f}% 已低于目标 {target_percent}%，无需清理"
        return result
    
    # 尝试清理内存的方法
    try:
        # 方法1: 垃圾回收
        import gc
        gc.collect()
        result["actions_taken"].append("执行Python垃圾回收")
        
        # 方法2: 清理工作集（使用 PowerShell）
        cleanup_cmd = '''
        $before = (Get-Process | Measure-Object WorkingSet64 -Sum).Sum / 1MB
        [System.GC]::Collect()
        [System.GC]::WaitForPendingFinalizers()
        [System.GC]::Collect()
        $after = (Get-Process | Measure-Object WorkingSet64 -Sum).Sum / 1MB
        Write-Output "Cleaned: $([math]::Round($before - $after, 2)) MB"
        '''
        
        proc = subprocess.run(
            ["powershell", "-Command", cleanup_cmd],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.stdout:
            result["actions_taken"].append(f"清理工作集: {proc.stdout.strip()}")
        
        # 重新获取内存
        mem = psutil.virtual_memory()
        result["new_percent"] = mem.percent
        result["available_mb"] = mem.available / (1024 * 1024)
        
        if mem.percent <= target_percent:
            result["success"] = True
            result["message"] = f"内存清理成功！从 {current_percent:.1f}% 降到 {mem.percent:.1f}%，已低于目标 {target_percent}%"
        else:
            result["message"] = f"已尽力清理，内存从 {current_percent:.1f}% 降到 {mem.percent:.1f}%，仍高于目标 {target_percent}%"
            
    except Exception as e:
        result["success"] = False
        result["error"] = str(e)
        result["message"] = f"清理过程中出错: {str(e)}"
    
    return result


def search_file_in_explorer(path: str, search_term: str) -> dict[str, Any]:
    """
    在资源管理器中搜索文件
    
    Args:
        path: 搜索起始路径，如 D:\
        search_term: 搜索关键词
        
    Returns:
        dict: 搜索结果
    """
    # 安全检查
    if not path or len(path) < 2:
        path = "D:\\"

    # 路径白名单校验：只允许盘符开头的路径
    if not re.match(r'^[A-Za-z]:[\\/][A-Za-z0-9 _\-.\\/:]*$', path):
        return {
            "success": False,
            "error": f"非法路径格式: {path}",
            "message": "路径必须为盘符开头的绝对路径"
        }
    # 禁止路径遍历
    if ".." in path:
        return {
            "success": False,
            "error": "路径不允许包含 ..",
            "message": "路径不允许包含 .."
        }

    # 去掉搜索词中的危险字符
    safe_term = re.sub(r'[;&|`$<>]', '', search_term)
    
    result = {
        "path": path,
        "search_term": safe_term,
        "command": "",
        "success": True,
    }
    
    try:
        # 使用参数数组调用 explorer.exe，避免 shell=True
        subprocess.run(['explorer.exe', path], shell=False, timeout=5)
        result["command"] = f'explorer.exe "{path}"'
        result["message"] = f"已在资源管理器打开 {path}"
        
    except Exception as e:
        result["success"] = False
        result["error"] = str(e)
        result["message"] = f"打开资源管理器失败: {str(e)}"
    
    return result


# LLM Prompt 模板：强制 LLM 输出结构化 JSON
SYSTEM_APP_PROMPT_TEMPLATE = '''
当用户要求打开系统应用（记事本、计算器、资源管理器等）时，你必须按以下 JSON 格式输出，不要输出任何其他文字：

{
  "type": "app:notepad",
  "params": {
    "path": "可选的文件路径，如 D:\\\\test.txt"
  },
  "description": "打开记事本"
}

可用应用类型：
- app:notepad：记事本，params.path 为要打开的文件路径（可选）
- app:calc：计算器，无参数
- app:explorer：资源管理器，params.path 为文件夹路径
- app:taskmgr：任务管理器，无参数
- app:control：控制面板，无参数
- app:cmd：命令提示符，无参数
- app:powershell：PowerShell，无参数
- app:mspaint：画图，params.path 为图片路径（可选）
- app:wordpad：写字板，params.path 为文档路径（可选）
- app:regedit：注册表编辑器，无参数
- app:devmgmt：设备管理器，无参数
- app:services：服务管理器，无参数

规则：
- 如果用户说"打开记事本"，type 必须是 "app:notepad"
- 如果用户说"用记事本打开 D:\\\\test.txt"，params.path 必须是 "D:\\\\test.txt"
- 禁止输出任何解释性文字，只输出 JSON
'''


def get_available_apps() -> list[dict[str, Any]]:
    """获取所有可用应用列表"""
    return [
        {
            "type": app_type,
            "cmd": config["cmd"],
            "is_dangerous": config["is_dangerous"],
            "category": config["category"],
        }
        for app_type, config in APP_WHITELIST.items()
    ]


def format_app_action_json(action: SystemAppAction) -> str:
    """将 SystemAppAction 格式化为 JSON 字符串"""
    import json
    
    return json.dumps({
        "type": action.type,
        "params": action.params,
        "description": action.description,
        "is_dangerous": action.is_dangerous,
        "priority": action.priority,
    }, ensure_ascii=False, indent=2)