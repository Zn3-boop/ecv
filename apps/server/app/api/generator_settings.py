"""内容生成器设置API"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional

from app.services.generator_config import config, update_config, GeneratorConfig

router = APIRouter(prefix="/content/settings", tags=["content_settings"])


class UpdateSettingsRequest(BaseModel):
    """更新设置请求"""
    llm_provider: Optional[str] = Field(default=None, description="LLM提供者：ollama/openai/azure")
    llm_model: Optional[str] = Field(default=None, description="模型名称")
    default_content_type: Optional[str] = Field(default=None, description="默认内容类型")
    default_output_dir: Optional[str] = Field(default=None, description="默认输出目录")
    auto_open_file: Optional[bool] = Field(default=None, description="生成后自动打开文件")
    auto_open_browser: Optional[bool] = Field(default=None, description="生成后自动打开浏览器")
    enable_llm_generation: Optional[bool] = Field(default=None, description="启用LLM生成模式")
    enable_system_control: Optional[bool] = Field(default=None, description="启用系统控制模式")


class SettingsResponse(BaseModel):
    """设置响应"""
    config: GeneratorConfig
    message: str


@router.get("/", response_model=SettingsResponse)
async def get_settings():
    """获取当前设置"""
    return SettingsResponse(
        config=config,
        message="当前设置"
    )


@router.post("/", response_model=SettingsResponse)
async def update_settings(req: UpdateSettingsRequest):
    """更新设置"""
    updated = update_config(
        llm_provider=req.llm_provider,
        llm_model=req.llm_model,
        default_content_type=req.default_content_type,
        default_output_dir=req.default_output_dir,
        auto_open_file=req.auto_open_file,
        auto_open_browser=req.auto_open_browser,
        enable_llm_generation=req.enable_llm_generation,
        enable_system_control=req.enable_system_control
    )
    return SettingsResponse(
        config=updated,
        message="设置已更新"
    )


@router.post("/reset", response_model=SettingsResponse)
async def reset_settings():
    """重置为默认设置"""
    global config
    from app.services.generator_config import get_config
    config = get_config()
    return SettingsResponse(
        config=config,
        message="设置已重置为默认值"
    )


@router.get("/modes")
async def get_modes():
    """获取当前启用的模式"""
    return {
        "llm_generation": config.enable_llm_generation,
        "system_control": config.enable_system_control,
        "active_modes": [
            "LLM生成" if config.enable_llm_generation else None,
            "系统控制" if config.enable_system_control else None
        ]
    }


@router.post("/modes/toggle")
async def toggle_mode(mode: str, enabled: bool):
    """切换模式开关"""
    if mode == "llm":
        update_config(enable_llm_generation=enabled)
        return {"mode": "LLM生成", "enabled": enabled}
    elif mode == "system":
        update_config(enable_system_control=enabled)
        return {"mode": "系统控制", "enabled": enabled}
    else:
        return {"error": "无效的模式"}, 400
