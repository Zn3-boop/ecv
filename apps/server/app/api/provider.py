"""
AI Provider API - 动态管理AI服务
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.services.provider_manager import ProviderConfig, get_provider_manager

router = APIRouter(prefix="/provider", tags=["provider"])


class AddProviderRequest(BaseModel):
    """添加Provider请求"""
    id: str = Field(..., description="唯一标识符，如: minimax, ollama, openai")
    name: str = Field(..., description="显示名称，如: MiniMax")
    api_url: str = Field(..., description="API地址，如: https://api.minimax.chat/v1/text/chatcompletion_v2")
    api_key: str = Field(default="", description="API密钥（可选）")
    model: str = Field(default="gpt-3.5-turbo", description="默认模型")
    enabled: bool = Field(default=True, description="是否启用")
    api_type: str = Field(default="openai", description="API类型: openai 或 anthropic")
    extra: dict = Field(default_factory=dict, description="额外参数如max_tokens, temperature等")


class UpdateProviderRequest(BaseModel):
    """更新Provider请求"""
    name: Optional[str] = None
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    enabled: Optional[bool] = None
    api_type: Optional[str] = None
    extra: Optional[dict] = None


class ProviderResponse(BaseModel):
    """Provider响应"""
    id: str
    name: str
    api_url: str
    api_key: str
    model: str
    enabled: bool
    api_type: str
    extra: dict


class ChatRequest(BaseModel):
    """聊天请求"""
    provider_id: str = Field(..., description="Provider ID")
    messages: list[dict] = Field(..., description="消息列表")
    model: Optional[str] = Field(default=None, description="指定模型（可选）")
    temperature: Optional[float] = Field(default=0.7, description="温度参数")
    max_tokens: Optional[int] = Field(default=2048, description="最大token数")


@router.get("/", response_model=list[ProviderResponse])
async def list_providers():
    """列出所有已配置的Provider"""
    manager = get_provider_manager()
    providers = manager.list_providers()
    return [
        ProviderResponse(
            id=p.id,
            name=p.name,
            api_url=p.api_url,
            api_key="***" if p.api_key else "",
            model=p.model,
            enabled=p.enabled,
            api_type=p.api_type,
            extra=p.extra
        )
        for p in providers
    ]


@router.post("/", response_model=dict)
async def add_provider(request: AddProviderRequest):
    """添加新的Provider"""
    manager = get_provider_manager()
    
    config = ProviderConfig(
        id=request.id,
        name=request.name,
        api_url=request.api_url,
        api_key=request.api_key,
        model=request.model,
        enabled=request.enabled,
        api_type=request.api_type,
        extra=request.extra
    )
    
    if manager.add_provider(config):
        return {"success": True, "message": f"已添加 {request.name}"}
    else:
        raise HTTPException(status_code=400, detail=f"Provider '{request.id}' 已存在")


@router.get("/{provider_id}", response_model=ProviderResponse)
async def get_provider(provider_id: str):
    """获取单个Provider"""
    manager = get_provider_manager()
    p = manager.get_provider(provider_id)
    if not p:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' 不存在")
    
    return ProviderResponse(
        id=p.id,
        name=p.name,
        api_url=p.api_url,
        api_key="***" if p.api_key else "",
        model=p.model,
        enabled=p.enabled,
        api_type=p.api_type,
        extra=p.extra
    )


@router.put("/{provider_id}", response_model=dict)
async def update_provider(provider_id: str, request: UpdateProviderRequest):
    """更新Provider"""
    manager = get_provider_manager()
    p = manager.get_provider(provider_id)
    if not p:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' 不存在")
    
    # 更新字段
    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if value is not None:
            setattr(p, key, value)
    
    if manager.update_provider(p):
        return {"success": True, "message": f"已更新 {provider_id}"}
    else:
        raise HTTPException(status_code=500, detail="更新失败")


@router.delete("/{provider_id}", response_model=dict)
async def delete_provider(provider_id: str):
    """删除Provider"""
    manager = get_provider_manager()
    if manager.remove_provider(provider_id):
        return {"success": True, "message": f"已删除 {provider_id}"}
    else:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' 不存在")


@router.post("/{provider_id}/test", response_model=dict)
async def test_provider(provider_id: str):
    """测试Provider连接"""
    manager = get_provider_manager()
    p = manager.get_provider(provider_id)
    if not p:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' 不存在")
    
    # 发送简单测试消息
    result = await manager.chat_completion(
        provider_id,
        messages=[{"role": "user", "content": "Hi, please reply with 'OK'"}],
        max_tokens=10
    )
    
    if "error" in result:
        return {"success": False, "message": "连接失败", "error": result["error"]}
    else:
        return {"success": True, "message": "连接成功", "response": result}


@router.post("/chat", response_model=dict)
async def chat_with_provider(request: ChatRequest):
    """与指定Provider对话（非流式）"""
    manager = get_provider_manager()
    p = manager.get_provider(request.provider_id)
    if not p:
        raise HTTPException(status_code=404, detail=f"Provider '{request.provider_id}' 不存在")
    
    result = await manager.chat_completion(
        request.provider_id,
        messages=request.messages,
        model=request.model or p.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens
    )
    
    if "error" in result:
        raise HTTPException(status_code=502, detail=result["error"])
    
    return result


@router.post("/preset/minimax")
async def add_minimax_preset():
    """添加MiniMax预设Provider"""
    manager = get_provider_manager()
    
    config = ProviderConfig(
        id="minimax",
        name="MiniMax",
        api_url="https://api.minimax.chat/v1/text/chatcompletion_v2",
        api_key="",  # 用户需要填入自己的key
        model="MiniMax-Text-01",
        extra={"temperature": 0.7, "max_tokens": 2048}
    )
    
    if "minimax" in manager.providers:
        return {"success": True, "message": "MiniMax已存在，请直接修改API Key"}
    
    manager.add_provider(config)
    return {"success": True, "message": "已添加MiniMax预设，请编辑填入API Key"}


@router.post("/preset/ollama")
async def add_ollama_preset():
    """添加Ollama预设Provider（本地）"""
    manager = get_provider_manager()
    
    config = ProviderConfig(
        id="ollama",
        name="Ollama (本地)",
        api_url="http://localhost:11434/v1/chat/completions",
        api_key="",  # Ollama不需要key
        model="qwen2.5:3b",
        extra={"temperature": 0.7, "max_tokens": 2048}
    )
    
    if "ollama" in manager.providers:
        return {"success": True, "message": "Ollama已存在，请直接修改"}
    
    manager.add_provider(config)
    return {"success": True, "message": "已添加Ollama预设，请确保本地Ollama服务运行中"}
