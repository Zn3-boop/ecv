from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Any

from app.services.hooks.plugins.base import (
    DedupFilter,
    RetrievedDoc,
)

logger = logging.getLogger(__name__)


class SimHashDedupFilter(DedupFilter):
    """
    SimHash文本相似度去重: 剔除高度重复片段。
    """

    def __init__(self, similarity_threshold: float = 0.85, hash_bits: int = 64):
        self._threshold = similarity_threshold
        self._bits = hash_bits

    async def dedup_filter(self, docs: list[RetrievedDoc], query: str) -> list[RetrievedDoc]:
        if not docs:
            return docs

        seen_hashes: list[int] = []
        result: list[RetrievedDoc] = []

        for doc in docs:
            h = self._simhash(doc.content)
            is_dup = False
            for existing_h in seen_hashes:
                if self._similarity(h, existing_h) >= self._threshold:
                    is_dup = True
                    break
            if not is_dup:
                seen_hashes.append(h)
                result.append(doc)

        return result

    def _simhash(self, text: str) -> int:
        tokens = text.lower().split()
        if not tokens:
            return 0
        v = [0] * self._bits
        for token in tokens:
            token_hash = int(hashlib.md5(token.encode()).hexdigest(), 16)
            for i in range(self._bits):
                if token_hash & (1 << i):
                    v[i] += 1
                else:
                    v[i] -= 1
        fingerprint = 0
        for i in range(self._bits):
            if v[i] > 0:
                fingerprint |= (1 << i)
        return fingerprint

    def _similarity(self, h1: int, h2: int) -> float:
        xor = h1 ^ h2
        diff_bits = bin(xor).count("1")
        return 1.0 - diff_bits / self._bits


class RuleBasedFilter(DedupFilter):
    """
    规则过滤: 去除广告/导航/404/太短文本。
    """

    _JUNK_PATTERNS = [
        re.compile(r"(cookie|privacy|subscribe|newsletter|sign\s*up|log\s*in)", re.I),
        re.compile(r"(404|not\s*found|page\s*not\s*found)", re.I),
        re.compile(r"(copyright|©|\u00a9)", re.I),
    ]
    _MIN_CONTENT_LEN = 5

    async def dedup_filter(self, docs: list[RetrievedDoc], query: str) -> list[RetrievedDoc]:
        result: list[RetrievedDoc] = []
        for doc in docs:
            if len(doc.content.strip()) < self._MIN_CONTENT_LEN:
                continue
            if any(p.search(doc.content[:200]) for p in self._JUNK_PATTERNS):
                continue
            result.append(doc)
        return result


class RecencyFilter(DedupFilter):
    """
    时效性过滤: 网络结果带时间戳，过期内容降权。
    metadata中需要 "published_date" 字段 (ISO格式)。
    """

    def __init__(self, max_age_days: int = 365, decay_factor: float = 0.5):
        self._max_age_days = max_age_days
        self._decay = decay_factor

    async def dedup_filter(self, docs: list[RetrievedDoc], query: str) -> list[RetrievedDoc]:
        now = time.time()
        result: list[RetrievedDoc] = []
        for doc in docs:
            pub_date = doc.metadata.get("published_date", "")
            if not pub_date:
                result.append(doc)
                continue
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                age_days = (now - dt.timestamp()) / 86400
                if age_days > self._max_age_days:
                    doc = RetrievedDoc(
                        content=doc.content,
                        source=doc.source,
                        score=doc.score * self._decay,
                        title=doc.title,
                        url=doc.url,
                        chunk_id=doc.chunk_id,
                        metadata={**doc.metadata, "recency_penalty": True},
                    )
                result.append(doc)
            except Exception:
                result.append(doc)
        return result


class CompositeDedupFilter(DedupFilter):
    """
    组合过滤器: 串联多个DedupFilter，依次执行。
    """

    def __init__(self, filters: list[DedupFilter]):
        self._filters = filters

    async def dedup_filter(self, docs: list[RetrievedDoc], query: str) -> list[RetrievedDoc]:
        current = docs
        for f in self._filters:
            current = await f.dedup_filter(current, query)
        return current