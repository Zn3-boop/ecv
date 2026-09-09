"""
桌面应用控制 API 路由
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.desktop_controller import (
    find_app_path,
    open_app,
    open_file,
    close_app,
    list_running_apps,
    take_screenshot,
)
from app.services.software_index import find_software

router = APIRouter(prefix="/desktop", tags=["desktop"])


class FindAppRequest(BaseModel):
    """查找应用请求"""
    name: str = Field(..., description="应用名称")


class OpenAppRequest(BaseModel):
    """打开应用请求"""
    path_or_name: str = Field(..., description="应用路径或名称")


class OpenFileRequest(BaseModel):
    """打开文件请求"""
    file_path: str = Field(..., description="文件路径")
    app_name: str | None = Field(default=None, description="应用名称（可选）")


class CloseAppRequest(BaseModel):
    """关闭应用请求"""
    app_name: str = Field(..., description="应用名称（不含扩展名）")


class ScreenshotRequest(BaseModel):
    """截图请求"""
    save_path: str | None = Field(default=None, description="保存路径（可选）")


class BaseResponse(BaseModel):
    """基础响应"""
    success: bool
    message: str
    data: dict | None = None
    error: str | None = None


@router.get("/software/find")
async def find_software_by_query(query: str = ""):
    """GET 端点：根据名称查找软件（供 Electron 调用）"""
    if not query:
        return {"name": "", "exe_path": "", "source": ""}
    entry = find_software(query)
    if entry and entry.exe_path:
        return {"name": entry.name, "exe_path": entry.exe_path, "source": entry.source}
    return {"name": query, "exe_path": "", "source": "not_found"}


@router.post("/find", response_model=BaseResponse)
async def find_application(request: FindAppRequest):
    """查找应用程序路径"""
    result = find_app_path(request.name)
    return BaseResponse(
        success=result.success,
        message=result.message,
        data=result.data,
        error=result.error
    )


@router.post("/open", response_model=BaseResponse)
async def open_application(request: OpenAppRequest):
    """打开应用程序"""
    result = open_app(request.path_or_name)
    return BaseResponse(
        success=result.success,
        message=result.message,
        data=result.data,
        error=result.error
    )


@router.post("/file/open", response_model=BaseResponse)
async def file_open(request: OpenFileRequest):
    """用指定应用打开文件"""
    result = open_file(request.file_path, request.app_name)
    return BaseResponse(
        success=result.success,
        message=result.message,
        data=result.data,
        error=result.error
    )


@router.post("/close", response_model=BaseResponse)
async def close_application(request: CloseAppRequest):
    """关闭应用程序"""
    result = close_app(request.app_name)
    return BaseResponse(
        success=result.success,
        message=result.message,
        data=result.data,
        error=result.error
    )


@router.get("/running", response_model=BaseResponse)
async def running_apps():
    """列出正在运行的应用"""
    result = list_running_apps()
    return BaseResponse(
        success=result.success,
        message=result.message,
        data=result.data,
        error=result.error
    )


@router.post("/screenshot", response_model=BaseResponse)
async def screenshot(request: ScreenshotRequest):
    """截取屏幕截图"""
    result = take_screenshot(request.save_path)
    return BaseResponse(
        success=result.success,
        message=result.message,
        data=result.data,
        error=result.error
    )