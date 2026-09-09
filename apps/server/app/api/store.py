"""
应用商店管理API路由
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.store_manager import (
    search_app,
    install_app,
    uninstall_app,
    list_installed,
    get_winget_status,
)

router = APIRouter(prefix="/store", tags=["store"])


class StoreSearchRequest(BaseModel):
    """搜索应用请求"""
    query: str = Field(..., description="搜索关键词")


class StoreInstallRequest(BaseModel):
    """安装应用请求"""
    package_id: str = Field(..., description="应用包ID")
    app_name: str | None = Field(default=None, description="应用名称")


class StoreUninstallRequest(BaseModel):
    """卸载应用请求"""
    package_id: str = Field(..., description="应用包ID")


class StoreSearchResponse(BaseModel):
    """搜索响应"""
    success: bool
    message: str
    apps: list[dict] = []
    error: str | None = None


class StoreInstallResponse(BaseModel):
    """安装响应"""
    success: bool
    message: str
    package_id: str | None = None
    error: str | None = None


class StoreListResponse(BaseModel):
    """列表响应"""
    success: bool
    message: str
    apps: list[dict] = []
    error: str | None = None


class StoreStatusResponse(BaseModel):
    """状态响应"""
    success: bool
    message: str
    version: str | None = None
    error: str | None = None


@router.get("/status", response_model=StoreStatusResponse)
async def check_store_status():
    """
    检查Winget商店状态
    
    Winget是微软官方的Windows包管理器
    """
    result = await get_winget_status()
    return StoreStatusResponse(
        success=result.success,
        message=result.message,
        version=result.data.get("version") if result.data else None,
        error=result.error,
    )


@router.post("/search", response_model=StoreSearchResponse)
async def search_applications(request: StoreSearchRequest):
    """
    搜索应用
    
    示例: POST /store/search
    {"query": "vscode"}
    """
    result = await search_app(request.query)
    return StoreSearchResponse(
        success=result.success,
        message=result.message,
        apps=result.data.get("apps", []) if result.data else [],
        error=result.error,
    )


@router.post("/install", response_model=StoreInstallResponse)
async def install_application(request: StoreInstallRequest):
    """
    安装应用（需要管理员权限）
    
    示例: POST /store/install
    {"package_id": "Microsoft.VisualStudioCode", "app_name": "VS Code"}
    """
    # 安全提示：安装是危险操作
    if not request.package_id:
        raise HTTPException(status_code=400, detail="缺少应用包ID")
    
    result = await install_app(request.package_id, request.app_name)
    return StoreInstallResponse(
        success=result.success,
        message=result.message,
        package_id=request.package_id if result.success else None,
        error=result.error,
    )


@router.post("/uninstall", response_model=StoreInstallResponse)
async def uninstall_application(request: StoreUninstallRequest):
    """
    卸载应用（需要管理员权限）
    
    示例: POST /store/uninstall
    {"package_id": "Microsoft.VisualStudioCode"}
    """
    if not request.package_id:
        raise HTTPException(status_code=400, detail="缺少应用包ID")
    
    result = await uninstall_app(request.package_id)
    return StoreInstallResponse(
        success=result.success,
        message=result.message,
        package_id=request.package_id if result.success else None,
        error=result.error,
    )


@router.get("/installed", response_model=StoreListResponse)
async def get_installed_apps():
    """
    获取已安装应用列表
    """
    result = await list_installed()
    return StoreListResponse(
        success=result.success,
        message=result.message,
        apps=result.data.get("apps", []) if result.data else [],
        error=result.error,
    )