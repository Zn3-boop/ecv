# 桌面控制工具白名单 API
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import subprocess
import os

router = APIRouter(prefix="/desktop-tools", tags=["桌面工具"])

# ===== 工具白名单定义 =====

# 系统工具白名单
SYSTEM_TOOLS = {
    "open_log_dir": {
        "name": "打开日志目录",
        "action": "explorer",
        "args": ["d:\\ecv\\logs"],
        "description": "打开项目日志目录",
        "risk": "low",
        "icon": "📁"
    },
    "open_project_dir": {
        "name": "打开项目目录",
        "action": "explorer", 
        "args": ["d:\\ecv"],
        "description": "打开项目根目录",
        "risk": "low",
        "icon": "📂"
    },
    "open_data_dir": {
        "name": "打开数据目录",
        "action": "explorer",
        "args": ["d:\\ecv\\data"],
        "description": "打开数据目录",
        "risk": "low", 
        "icon": "💾"
    },
    "run_diagnosis": {
        "name": "运行诊断脚本",
        "action": "powershell",
        "args": ["-ExecutionPolicy", "Bypass", "-File", "d:\\ecv\\diagnose_agent.py"],
        "description": "运行系统诊断脚本",
        "risk": "medium",
        "icon": "🔍"
    },
    "clean_memory": {
        "name": "清理内存",
        "action": "powershell",
        "args": ["-ExecutionPolicy", "Bypass", "-File", "d:\\ecv\\clean_mem.bat"],
        "description": "运行内存清理脚本",
        "risk": "medium",
        "icon": "🧹"
    },
    "check_disk": {
        "name": "检查磁盘空间",
        "action": "powershell",
        "args": ["-ExecutionPolicy", "Bypass", "-File", "d:\\ecv\\check_disk.ps1"],
        "description": "检查磁盘使用情况",
        "risk": "low",
        "icon": "💿"
    },
    "system_check": {
        "name": "系统检查",
        "action": "powershell",
        "args": ["-ExecutionPolicy", "Bypass", "-File", "d:\\ecv\\system_check.ps1"],
        "description": "运行完整系统检查",
        "risk": "low",
        "icon": "🔧"
    },
    "open_terminal": {
        "name": "打开终端",
        "action": "cmd",
        "args": ["/c", "start", "cmd"],
        "description": "打开新的命令行终端",
        "risk": "low",
        "icon": "⌨️"
    },
    "open_vscode": {
        "name": "打开VSCode",
        "action": "code",
        "args": ["d:\\ecv"],
        "description": "在VSCode中打开项目",
        "risk": "low",
        "icon": "💻"
    },
    "restart_services": {
        "name": "重启服务",
        "action": "cmd",
        "args": ["/c", "d:\\ecv\\start_all.bat"],
        "description": "重启所有服务",
        "risk": "high",
        "icon": "🔄"
    }
}

# ===== API 模型 =====

class ToolExecuteRequest(BaseModel):
    tool_id: str
    params: Optional[dict] = None

class ToolInfo(BaseModel):
    id: str
    name: str
    description: str
    risk: str
    icon: str

class ToolExecuteResponse(BaseModel):
    success: bool
    tool_id: str
    output: Optional[str] = None
    error: Optional[str] = None

# ===== API 端点 =====

@router.get("/list", response_model=List[ToolInfo])
async def list_tools():
    """列出所有可用的桌面控制工具"""
    return [
        ToolInfo(
            id=tool_id,
            name=tool["name"],
            description=tool["description"],
            risk=tool["risk"],
            icon=tool["icon"]
        )
        for tool_id, tool in SYSTEM_TOOLS.items()
    ]

@router.post("/execute", response_model=ToolExecuteResponse)
async def execute_tool(request: ToolExecuteRequest):
    """执行指定的桌面控制工具"""
    if request.tool_id not in SYSTEM_TOOLS:
        raise HTTPException(status_code=404, detail=f"工具 '{request.tool_id}' 不在白名单中")
    
    tool = SYSTEM_TOOLS[request.tool_id]
    
    try:
        # 构建命令
        cmd = [tool["action"]] + tool["args"]
        
        # 执行命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        return ToolExecuteResponse(
            success=result.returncode == 0,
            tool_id=request.tool_id,
            output=result.stdout if result.stdout else None,
            error=result.stderr if result.stderr else None
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="执行超时")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tool/{tool_id}", response_model=ToolInfo)
async def get_tool(tool_id: str):
    """获取指定工具的详细信息"""
    if tool_id not in SYSTEM_TOOLS:
        raise HTTPException(status_code=404, detail=f"工具 '{tool_id}' 不存在")
    
    tool = SYSTEM_TOOLS[tool_id]
    return ToolInfo(
        id=tool_id,
        name=tool["name"],
        description=tool["description"],
        risk=tool["risk"],
        icon=tool["icon"]
    )
