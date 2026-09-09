from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheEntry:
    value: str
    expires_at: float


# Config reload marker
class LLMRateLimiter:
    def __init__(self) -> None:
        self.min_interval_seconds = float(os.getenv("LLM_MIN_INTERVAL_SECONDS", "0.5"))
        self.cache_ttl_seconds = float(os.getenv("LLM_CACHE_TTL_SECONDS", "120"))
        self.max_cache_entries = int(os.getenv("LLM_CACHE_MAX_ENTRIES", "128"))
        self._last_request_ts = 0.0
        self._lock = asyncio.Lock()
        self._cache: dict[str, CacheEntry] = {}

    def _make_cache_key(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        response_format: dict[str, Any] | None,
    ) -> str:
        payload = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "temperature": temperature,
            "response_format": response_format,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get_cached(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        response_format: dict[str, Any] | None,
    ) -> str | None:
        key = self._make_cache_key(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            response_format=response_format,
        )
        entry = self._cache.get(key)
        if not entry:
            return None
        if entry.expires_at < time.time():
            self._cache.pop(key, None)
            return None
        return entry.value

    def set_cached(
        self,
        value: str,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        response_format: dict[str, Any] | None,
    ) -> None:
        key = self._make_cache_key(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            response_format=response_format,
        )
        if len(self._cache) >= self.max_cache_entries:
            oldest_key = next(iter(self._cache.keys()), None)
            if oldest_key:
                self._cache.pop(oldest_key, None)
        self._cache[key] = CacheEntry(value=value, expires_at=time.time() + self.cache_ttl_seconds)

    async def wait_turn(self) -> None:
        async with self._lock:
            now = time.time()
            wait_seconds = self.min_interval_seconds - (now - self._last_request_ts)
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            self._last_request_ts = time.time()


rate_limiter = LLMRateLimiter()