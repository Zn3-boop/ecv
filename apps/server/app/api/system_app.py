"""
系统应用控制 API 路由

提供安全启动 Windows 系统应用的 REST API 接口
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.system_app_controller import (
    APP_WHITELIST,
    SYSTEM_APP_PROMPT_TEMPLATE,
    ExecuteResult,
    SystemAppAction,
    execute_system_app,
    format_app_action_json,
    get_available_apps,
    parse_app_intent,
    cleanup_memory,
    search_file_in_explorer,
    parse_memory_cleanup_intent,
    parse_file_search_intent,
)

router = APIRouter(prefix="/system-app", tags=["system-app"])


class SystemAppExecuteRequest(BaseModel):
    """系统应用执行请求"""
    type: str = Field(..., description="应用类型，如 app:notepad")
    params: dict[str, Any] = Field(default_factory=dict, description="应用参数")
    description: str = Field(default="", description="描述")
    skip_confirmation: bool = Field(default=False, description="跳过危险操作确认")


class SystemAppExecuteResponse(BaseModel):
    """系统应用执行响应"""
    success: bool
    message: str
    type: str
    command: str
    is_dangerous: bool = False
    error: str | None = None


class SystemAppIntentRequest(BaseModel):
    """自然语言意图解析请求"""
    command: str = Field(..., description="用户自然语言命令，如'打开记事本'")


class SystemAppIntentResponse(BaseModel):
    """自然语言意图解析响应"""
    type: str | None = None
    params: dict[str, Any] = {}
    description: str | None = None
    is_dangerous: bool = False
    recognized: bool = False
    message: str = "无法识别应用启动意图"


class SystemAppNLPResponse(BaseModel):
    """自然语言一站式响应（解析+执行）"""
    intent: SystemAppIntentResponse
    result: SystemAppExecuteResponse


class SystemAppListResponse(BaseModel):
    """可用应用列表响应"""
    apps: list[dict[str, Any]]
    total: int


class SystemAppPromptResponse(BaseModel):
    """Prompt 模板响应"""
    template: str


# ========== API 端点 ==========


@router.post("/execute", response_model=SystemAppExecuteResponse)
async def execute_app(request: SystemAppExecuteRequest):
    """
    执行系统应用
    
    支持的应用：
    - app:notepad: 记事本
    - app:calc: 计算器
    - app:explorer: 资源管理器
    - app:cmd: 命令提示符
    - app:powershell: PowerShell
    - app:mspaint: 画图
    - app:wordpad: 写字板
    - app:taskmgr: 任务管理器
    - app:control: 控制面板
    - app:regedit: 注册表编辑器
    - app:devmgmt: 设备管理器
    - app:services: 服务管理器
    """
    # 验证应用类型
    if request.type not in APP_WHITELIST:
        raise HTTPException(
            status_code=400,
            detail=f"未知应用类型: {request.type}。可用类型: {', '.join(APP_WHITELIST.keys())}"
        )
    
    # 检查危险操作
    app_config = APP_WHITELIST[request.type]
    is_dangerous = app_config.get("is_dangerous", False)
    
    if is_dangerous and not request.skip_confirmation:
        # 返回需要确认的状态
        raise HTTPException(
            status_code=428,
            detail={
                "error": "CONFIRMATION_REQUIRED",
                "message": f"应用 {request.type} 是危险操作，需要 skip_confirmation=true",
                "is_dangerous": True,
            }
        )
    
    # 构建 Action
    action = SystemAppAction(
        type=request.type,
        params=request.params,
        description=request.description,
        is_dangerous=is_dangerous,
    )
    
    # 执行
    result = execute_system_app(action)
    
    return SystemAppExecuteResponse(
        success=result.success,
        message=result.message or (result.error and f"错误: {result.error}" or ""),
        type=request.type,
        command=result.executed_command,
        is_dangerous=is_dangerous,
        error=result.error,
    )


@router.post("/intent", response_model=SystemAppIntentResponse)
async def parse_intent(request: SystemAppIntentRequest):
    """
    解析用户应用启动意图
    
    从自然语言中提取要启动的应用类型
    """
    action = parse_app_intent(request.command)
    
    if action:
        return SystemAppIntentResponse(
            type=action.type,
            params=action.params,
            description=action.description,
            is_dangerous=action.is_dangerous,
            recognized=True,
            message=f"识别到: {action.description}",
        )
    
    return SystemAppIntentResponse(
        recognized=False,
        message="无法识别应用启动意图。请尝试：打开记事本、打开计算器、打开文件夹等"
    )


@router.post("/nlp", response_model=SystemAppNLPResponse)
async def nlp_app_control(request: SystemAppIntentRequest):
    """
    自然语言应用控制（解析+执行一站式）
    
    接收自然语言命令，自动解析意图并执行
    """
    # 1. 解析意图
    action = parse_app_intent(request.command)
    
    if action:
        # 检查危险操作确认
        if action.is_dangerous:
            return SystemAppNLPResponse(
                intent=SystemAppIntentResponse(
                    type=action.type,
                    params=action.params,
                    description=action.description,
                    is_dangerous=action.is_dangerous,
                    recognized=True,
                    message="识别到危险操作，需要确认才能执行",
                ),
                result=SystemAppExecuteResponse(
                    success=False,
                    message="危险操作需要确认",
                    type=action.type,
                    command="",
                    is_dangerous=True,
                    error="CONFIRMATION_REQUIRED",
                )
            )
        
        # 2. 执行
        result = execute_system_app(action)
        
        return SystemAppNLPResponse(
            intent=SystemAppIntentResponse(
                type=action.type,
                params=action.params,
                description=action.description,
                is_dangerous=action.is_dangerous,
                recognized=True,
                message=f"识别到: {action.description}",
            ),
            result=SystemAppExecuteResponse(
                success=result.success,
                message=result.message or "",
                type=action.type,
                command=result.executed_command,
                is_dangerous=action.is_dangerous,
                error=result.error,
            )
        )
    
    # 无法识别
    return SystemAppNLPResponse(
        intent=SystemAppIntentResponse(
            recognized=False,
            message="无法识别应用启动意图",
        ),
        result=SystemAppExecuteResponse(
            success=False,
            message="无法识别应用启动意图",
            type="",
            command="",
            error="INTENT_NOT_RECOGNIZED",
        )
    )


@router.post("/nlp-confirmed", response_model=SystemAppNLPResponse)
async def nlp_app_control_confirmed(request: SystemAppIntentRequest):
    """
    自然语言应用控制（带确认执行）
    
    用于危险操作需要用户确认后执行
    """
    action = parse_app_intent(request.command)
    
    if not action:
        raise HTTPException(
            status_code=400,
            detail="无法识别应用启动意图"
        )
    
    # 强制执行（跳过确认）
    action.skip_confirmation = True
    result = execute_system_app(action)
    
    return SystemAppNLPResponse(
        intent=SystemAppIntentResponse(
            type=action.type,
            params=action.params,
            description=action.description,
            is_dangerous=action.is_dangerous,
            recognized=True,
        ),
        result=SystemAppExecuteResponse(
            success=result.success,
            message=result.message or "",
            type=action.type,
            command=result.executed_command,
            is_dangerous=action.is_dangerous,
            error=result.error,
        )
    )


@router.get("/list", response_model=SystemAppListResponse)
async def list_apps():
    """
    获取所有可用系统应用列表
    """
    apps = get_available_apps()
    
    return SystemAppListResponse(
        apps=apps,
        total=len(apps)
    )


@router.get("/prompt", response_model=SystemAppPromptResponse)
async def get_prompt():
    """
    获取系统应用控制的 Prompt 模板
    
    用于引导 LLM 输出结构化的应用启动指令
    """
    return SystemAppPromptResponse(template=SYSTEM_APP_PROMPT_TEMPLATE)


class MemoryCleanupRequest(BaseModel):
    """内存清理请求"""
    target_percent: float = Field(default=75.0, description="目标内存使用率百分比")


class MemoryCleanupResponse(BaseModel):
    """内存清理响应"""
    success: bool
    current_percent: float
    target_percent: float
    new_percent: float | None = None
    available_mb: float
    total_mb: float
    actions_taken: list[str]
    message: str
    error: str | None = None


@router.post("/cleanup-memory", response_model=MemoryCleanupResponse)
async def cleanup_mem(request: MemoryCleanupRequest):
    """
    清理内存，降低到指定百分比以下
    
    示例：POST /system-app/cleanup-memory
    {"target_percent": 75}
    """
    result = cleanup_memory(target_percent=request.target_percent)
    return MemoryCleanupResponse(**result)


class FileSearchRequest(BaseModel):
    """文件搜索请求"""
    path: str = Field(default="D:\\", description="搜索起始路径")
    search_term: str = Field(default="", description="搜索关键词")


class FileSearchResponse(BaseModel):
    """文件搜索响应"""
    success: bool
    path: str
    search_term: str
    command: str
    message: str
    error: str | None = None


@router.post("/search-file", response_model=FileSearchResponse)
async def search_file(request: FileSearchRequest):
    """
    在资源管理器中打开指定路径并搜索文件
    
    示例：POST /system-app/search-file
    {"path": "D:\\", "search_term": "aits.1"}
    """
    result = search_file_in_explorer(path=request.path, search_term=request.search_term)
    return FileSearchResponse(**result)
