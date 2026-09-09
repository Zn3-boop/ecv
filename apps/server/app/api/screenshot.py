"""
截图API路由
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.screenshot import capture_screen, capture_all_monitors, capture_window

router = APIRouter(prefix="/screenshot", tags=["screenshot"])


class CaptureRequest(BaseModel):
    """截图请求"""
    monitor: int = Field(default=1, description="显示器编号（1为主屏）")
    output_path: str | None = Field(default=None, description="保存路径")


class CaptureWindowRequest(BaseModel):
    """窗口截图请求"""
    window_title: str = Field(..., description="窗口标题（模糊匹配）")


class ScreenshotResponse(BaseModel):
    """截图响应"""
    success: bool
    file_path: str | None = None
    width: int = 0
    height: int = 0
    error: str | None = None
    message: str


@router.post("/capture", response_model=ScreenshotResponse)
async def take_screenshot(request: CaptureRequest):
    """
    截取屏幕
    
    示例: POST /screenshot/capture
    {"monitor": 1}
    """
    result = capture_screen(monitor=request.monitor, output_path=request.output_path)
    
    return ScreenshotResponse(
        success=result.success,
        file_path=result.file_path,
        width=result.width,
        height=result.height,
        error=result.error,
        message=result.message,
    )


@router.post("/capture-window", response_model=ScreenshotResponse)
async def take_window_screenshot(request: CaptureWindowRequest):
    """
    截取指定窗口
    
    示例: POST /screenshot/capture-window
    {"window_title": "Visual Studio Code"}
    """
    result = capture_window(window_title=request.window_title)
    
    return ScreenshotResponse(
        success=result.success,
        file_path=result.file_path,
        width=result.width,
        height=result.height,
        error=result.error,
        message=result.message,
    )
