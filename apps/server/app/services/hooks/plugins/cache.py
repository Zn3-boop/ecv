from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class QueryCache:
    """
    B8: 查询改写缓存
    - 缓存key = 标准化原Query + 模型版本 + prompt版本
    - 上下文依赖时增加上下文指纹隔离, 不跨用户/跨版本复用
    - 支持TTL过期
    """

    def __init__(self, max_size: int = 1000, default_ttl_s: float = 3600.0):
        self._max_size = max_size
        self._ttl = default_ttl_s
        self._store: dict[str, tuple[Any, float]] = {}

    def _make_key(
        self,
        query: str,
        model_version: str = "",
        prompt_version: str = "",
        context_fingerprint: str = "",
    ) -> str:
        normalized = " ".join(query.lower().split())
        raw = f"{normalized}|{model_version}|{prompt_version}|{context_fingerprint}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    @staticmethod
    def context_fingerprint(context: dict[str, Any] | None) -> str:
        if not context:
            return ""
        relevant = {k: v for k, v in context.items() if k in ("user_id", "session_id", "lang")}
        return hashlib.md5(json.dumps(relevant, sort_keys=True, default=str).encode()).hexdigest()[:16]

    def get(
        self,
        query: str,
        model_version: str = "",
        prompt_version: str = "",
        context: dict[str, Any] | None = None,
    ) -> Any | None:
        ctx_fp = self.context_fingerprint(context)
        key = self._make_key(query, model_version, prompt_version, ctx_fp)
        entry = self._store.get(key)
        if entry is None:
            return None
        value, ts = entry
        if time.monotonic() - ts > self._ttl:
            del self._store[key]
            return None
        return value

    def set(
        self,
        query: str,
        value: Any,
        model_version: str = "",
        prompt_version: str = "",
        context: dict[str, Any] | None = None,
    ):
        ctx_fp = self.context_fingerprint(context)
        key = self._make_key(query, model_version, prompt_version, ctx_fp)
        if len(self._store) >= self._max_size:
            oldest_key = min(self._store, key=lambda k: self._store[k][1])
            del self._store[oldest_key]
        self._store[key] = (value, time.monotonic())

    def clear(self):
        self._store.clear()

    def stats(self) -> dict[str, Any]:
        now = time.monotonic()
        active = sum(1 for _, (_, ts) in self._store.items() if now - ts <= self._ttl)
        return {"total_keys": len(self._store), "active_keys": active, "max_size": self._max_size}


class DegradationChain:
    """
    B8: 降级链
    降级顺序: 模型 → 历史缓存 → 行为高置信对 → 规则改写 → 原始Query兜底
    永远不会挂。
    """

    def __init__(self, cache: QueryCache | None = None):
        self._cache = cache or QueryCache()

    async def resolve(
        self,
        raw_query: str,
        primary_fn: Any = None,
        rule_fn: Any = None,
        model_version: str = "",
        prompt_version: str = "",
        context: dict[str, Any] | None = None,
    ) -> Any:
        if primary_fn is not None:
            try:
                result = await primary_fn(raw_query, context)
                if result is not None:
                    self._cache.set(raw_query, result, model_version, prompt_version, context)
                    return result
            except Exception as e:
                logger.warning(f"主模型失败，开始降级: {e}")

        cached = self._cache.get(raw_query, model_version, prompt_version, context)
        if cached is not None:
            logger.info("降级: 使用缓存结果")
            return cached

        if rule_fn is not None:
            try:
                result = await rule_fn(raw_query, context)
                if result is not None:
                    return result
            except Exception as e:
                logger.warning(f"规则降级也失败: {e}")

        logger.info("降级兜底: 返回原始Query")
        return raw_query