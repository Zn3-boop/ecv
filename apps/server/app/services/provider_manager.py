"""
AI Provider 管理器 - 动态添加AI服务
支持 OpenAI 兼容格式的 API
"""

import os
import json
import re
import httpx
from dataclasses import dataclass, field
from typing import Any, Optional
from pathlib import Path


PROVIDERS_CONFIG_FILE = Path(__file__).parent.parent / "data" / "providers.json"


def _resolve_env_vars(value: str) -> str:
    """替换字符串中的 ${VAR_NAME} 为对应环境变量值"""
    if not value or not value.startswith("$"):
        return value
    return re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), ""), value)


@dataclass
class ProviderConfig:
    """AI Provider配置"""
    id: str
    name: str
    api_url: str
    api_key: str = ""
    model: str = "gpt-3.5-turbo"
    enabled: bool = True
    extra: dict = field(default_factory=dict)  # 额外参数如max_tokens等
    api_type: str = "openai"  # openai 或 anthropic
    
    def get_full_url(self) -> str:
        """获取完整的API URL，自动处理不同格式"""
        url = self.api_url.rstrip("/")
        
        # 如果URL已经包含完整路径，直接返回
        if "/chat/completions" in url or "/chatcompletion" in url:
            return url
        
        # 智谱AI特殊处理 - 他们的API路径是 /chat/completions
        if "bigmodel.cn" in url:
            return f"{url}/chat/completions"
        
        # MiniMax特殊处理（已经是完整路径）
        if "minimax.chat" in url and "/v1/text" in url:
            return url
        
        # 默认OpenAI格式
        return f"{url}/chat/completions"
    
    def get_headers(self) -> dict:
        """获取请求头"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        # OpenRouter需要额外的HTTP头
        if "openrouter" in self.api_url:
            headers["HTTP-Referer"] = "http://localhost"
            headers["X-Title"] = "AI Desktop Agent"
        
        return headers


class ProviderManager:
    """Provider管理器"""
    
    def __init__(self):
        self.providers: dict[str, ProviderConfig] = {}
        self._load()
    
    def _load(self):
        """从文件加载配置"""
        if PROVIDERS_CONFIG_FILE.exists():
            try:
                with open(PROVIDERS_CONFIG_FILE, encoding='utf-8') as f:
                    data = json.load(f)
                    for p in data.get("providers", []):
                        if "api_key" in p:
                            p["api_key"] = _resolve_env_vars(p["api_key"])
                        self.providers[p["id"]] = ProviderConfig(**p)
            except Exception as e:
                print(f"加载providers失败: {e}")
    
    def _save(self):
        """保存配置到文件"""
        PROVIDERS_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PROVIDERS_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "providers": [
                    {**vars(p), 'extra': p.extra}
                    for p in self.providers.values()
                ]
            }, f, ensure_ascii=False, indent=2)
    
    def add_provider(self, config: ProviderConfig) -> bool:
        """添加Provider"""
        if config.id in self.providers:
            return False
        self.providers[config.id] = config
        self._save()
        return True
    
    def update_provider(self, config: ProviderConfig) -> bool:
        """更新Provider"""
        if config.id not in self.providers:
            return False
        self.providers[config.id] = config
        self._save()
        return True
    
    def remove_provider(self, provider_id: str) -> bool:
        """删除Provider"""
        if provider_id not in self.providers:
            return False
        del self.providers[provider_id]
        self._save()
        return True
    
    def get_provider(self, provider_id: str) -> Optional[ProviderConfig]:
        """获取Provider"""
        return self.providers.get(provider_id)
    
    def list_providers(self) -> list[ProviderConfig]:
        """列出所有Provider"""
        return list(self.providers.values())
    
    async def chat_completion(
        self,
        provider_id: str,
        messages: list[dict],
        **kwargs
    ) -> dict:
        """
        调用Provider的chat completion API
        
        Args:
            provider_id: Provider ID
            messages: 消息列表 [{"role": "user", "content": "..."}]
            **kwargs: 额外参数如temperature, max_tokens等
            
        Returns:
            API响应结果
        """
        provider = self.get_provider(provider_id)
        if not provider:
            return {"error": f"Provider不存在: {provider_id}"}
        
        # 使用新的URL和headers处理方法
        headers = provider.get_headers()
        full_url = provider.get_full_url()
        
        # 根据API类型构建请求数据
        if provider.api_type == "anthropic" or "anthropic" in provider.api_url:
            # Anthropic 格式
            data = {
                "model": kwargs.get("model", provider.model),
                "messages": messages,
                **provider.extra,
                **{k: v for k, v in kwargs.items() if k not in ["model"]}
            }
        else:
            # OpenAI 格式
            data = {
                "model": kwargs.get("model", provider.model),
                "messages": messages,
                **provider.extra,
                **{k: v for k, v in kwargs.items() if k not in ["model"]}
            }
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    full_url,
                    headers=headers,
                    json=data
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"API错误 {e.response.status_code}: {e.response.text[:200]}"}
        except Exception as e:
            return {"error": f"请求失败: {str(e)}"}
    
    async def chat_stream(
        self,
        provider_id: str,
        messages: list[dict],
        callback=None,
        **kwargs
    ):
        """
        流式调用Provider
        
        Args:
            provider_id: Provider ID
            messages: 消息列表
            callback: 流式回调函数
        """
        provider = self.get_provider(provider_id)
        if not provider:
            yield {"error": f"Provider不存在: {provider_id}"}
            return
        
        headers = {"Content-Type": "application/json"}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"
        
        data = {
            "model": kwargs.get("model", provider.model),
            "messages": messages,
            "stream": True,
            **provider.extra,
            **{k: v for k, v in kwargs.items() if k not in ["model"]}
        }
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", provider.api_url, headers=headers, json=data) as resp:
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            content = line[6:]
                            if content == "[DONE]":
                                break
                            try:
                                chunk = json.loads(content)
                                if callback:
                                    callback(chunk)
                                yield chunk
                            except json.JSONDecodeError:
                                pass
        except Exception as e:
            yield {"error": f"流式请求失败: {str(e)}"}


# 全局单例
_manager = None

def get_provider_manager() -> ProviderManager:
    global _manager
    if _manager is None:
        _manager = ProviderManager()
    return _manager