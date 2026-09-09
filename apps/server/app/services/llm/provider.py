import json
import os
from pathlib import Path
from typing import Any

import httpx as httpx

# 加载 .env 文件 (provider.py -> services -> app -> apps -> server)
_env_file = Path(__file__).parent.parent.parent.parent / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)

from app.services.llm.rate_limiter import rate_limiter


class LLMProviderError(RuntimeError):
    """Raised when the configured LLM provider request fails."""


class LLMContextTooLongError(LLMProviderError):
    """Raised when the upstream provider rejects the request because the context is too long."""


class LLMRateLimitError(LLMProviderError):
    """Raised when the upstream provider rate limits the request."""


class LLMModelDisabledError(LLMProviderError):
    """Raised when the configured model is disabled or unavailable."""


class LLMUpstreamServerError(LLMProviderError):
    """Raised when the upstream provider returns a 5xx error."""


class LLMBadResponseError(LLMProviderError):
    """Raised when the upstream provider returns an unexpected payload."""


def _classify_provider_error(status_code: int, response_text: str) -> LLMProviderError:
    normalized = (response_text or "").lower()
    message = f"LLM provider request failed: {status_code} {response_text}"

    if status_code in {400, 413, 414} and any(
        token in normalized
        for token in {"context", "token", "too long", "maximum context", "prompt is too long", "invalid_request"}
    ):
        return LLMContextTooLongError(message)
    if status_code in {401, 403, 404} and any(
        token in normalized
        for token in {"disabled", "unavailable", "not found", "no such model", "model"}
    ):
        return LLMModelDisabledError(message)
    if status_code == 429:
        return LLMRateLimitError(message)
    if status_code >= 500:
        return LLMUpstreamServerError(message)
    return LLMProviderError(message)


class LLMProvider:
    def __init__(self) -> None:
        # 优先从 ProviderManager 读取动态配置
        self._provider = self._load_active_provider()
        if self._provider:
            self.api_key = self._provider.api_key
            self.base_url = self._provider.api_url.rstrip("/")
            self.model = self._provider.model
            self.timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "45"))
            self.enabled = True
        else:
            # 降级到 .env 配置
            self.api_key = os.getenv("LLM_API_KEY", "").strip()
            self.base_url = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
            self.model = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")
            self.timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "45"))
            self.enabled = bool(self.api_key)

    def _load_active_provider(self):
        """从 ProviderManager 获取第一个启用的 provider"""
        try:
            from app.services.provider_manager import get_provider_manager
            pm = get_provider_manager()
            for p in pm.providers.values():
                if not p.enabled:
                    continue
                if not p.model:
                    continue
                if p.api_key:
                    return p
                if self._is_local_url(p.api_url):
                    return p
        except Exception:
            pass
        return None

    @staticmethod
    def _is_local_url(api_url: str) -> bool:
        try:
            from urllib.parse import urlparse
            host = urlparse(str(api_url or "")).hostname or ""
            return host in ("localhost", "127.0.0.1", "::1")
        except Exception:
            return False

    async def _request(
        self,
        payload: dict[str, Any],
        *,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """底层请求方法，返回完整 response JSON"""
        if not self.enabled:
            raise LLMProviderError("LLM provider is not configured. Please set LLM_API_KEY.")

        # 缓存 key 基于 payload 的 messages + model + temperature（不含 tools，因为工具调用不缓存）
        cache_key_payload = {
            "model": payload.get("model"),
            "messages": payload.get("messages"),
            "temperature": payload.get("temperature"),
            "response_format": payload.get("response_format"),
        } if use_cache else None

        if use_cache and cache_key_payload:
            cached = rate_limiter.get_cached(
                system_prompt="",  # 兼容旧缓存接口，实际用完整 payload
                user_prompt=json.dumps(cache_key_payload, ensure_ascii=False),
                temperature=payload.get("temperature", 0.2),
                response_format=payload.get("response_format"),
            )
            if cached is not None:
                # 解析缓存的 JSON
                try:
                    return json.loads(cached)
                except json.JSONDecodeError:
                    pass

        await rate_limiter.wait_turn()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        app_name = os.getenv("LLM_APP_NAME", "AI Desktop Agent")
        referer = os.getenv("LLM_HTTP_REFERER", "http://localhost")
        if referer:
            headers["HTTP-Referer"] = referer
        if app_name:
            headers["X-Title"] = app_name

        # 兼容不同平台的 URL 格式：检查是否已包含 chat/completions 或其他路径
        url = self.base_url
        # 检查URL是否已经包含了completion相关路径
        # 注意：/v4 和 /v1 结尾的路径仍需要拼接 /chat/completions
        has_completion_path = any(
            url.endswith(suffix) 
            for suffix in ["/chat/completions", "/completions"]
        )
        if not has_completion_path:
            # 对于 /v4、/v1 等基础路径，需要拼接 /chat/completions
            url = f"{url}/chat/completions"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url,
                headers=headers,
                json=payload,
            )

        if response.status_code >= 400:
            raise _classify_provider_error(response.status_code, response.text)

        data = response.json()
        if use_cache and cache_key_payload:
            rate_limiter.set_cached(
                json.dumps(data, ensure_ascii=False),
                system_prompt="",
                user_prompt=json.dumps(cache_key_payload, ensure_ascii=False),
                temperature=payload.get("temperature", 0.2),
                response_format=payload.get("response_format"),
            )
        return data

    async def chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> str:
        """普通对话，返回文本内容"""
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if response_format:
            payload["response_format"] = response_format

        data = await self._request(payload, use_cache=use_cache)
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMBadResponseError(f"Unexpected LLM response: {json.dumps(data, ensure_ascii=False)}") from exc

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        """支持 function calling 的对话，返回完整 message dict（含 tool_calls）"""
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
        }

        data = await self._request(payload, use_cache=False)
        try:
            return data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMBadResponseError(f"Unexpected LLM response: {json.dumps(data, ensure_ascii=False)}") from exc


provider = LLMProvider()