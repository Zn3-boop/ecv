"""
内存限流中间件：基于 IP + 路径 的滑动窗口限流。
生产环境建议替换为 Redis + lua脚本 或 API Gateway 限流。

环境变量：
  RATE_LIMIT_ENABLED  - 是否启用限流（默认 true）
  RATE_LIMIT_RPS      - 每秒请求数上限（默认 10）
  RATE_LIMIT_BURST    - 突发窗口内最大请求数（默认 30）
"""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in {"true", "1", "yes"}
RATE_LIMIT_RPS = int(os.getenv("RATE_LIMIT_RPS", "10"))
RATE_LIMIT_BURST = int(os.getenv("RATE_LIMIT_BURST", "30"))
WINDOW_SECONDS = 1.0

_buckets: dict[str, list[float]] = defaultdict(list)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"
    return f"{ip}:{request.url.path}"


def _check_rate_limit(key: str) -> bool:
    now = time.monotonic()
    window_start = now - WINDOW_SECONDS
    bucket = _buckets[key]
    while bucket and bucket[0] < window_start:
        bucket.pop(0)
    if len(bucket) >= RATE_LIMIT_BURST:
        return False
    bucket.append(now)
    return True


async def rate_limit_middleware(request: Request, call_next):
    if not RATE_LIMIT_ENABLED:
        return await call_next(request)

    if request.method == "GET" and request.url.path in {"/health", "/health/ready", "/health/live", "/metrics", "/docs", "/openapi.json"}:
        return await call_next(request)

    key = _client_key(request)
    if not _check_rate_limit(key):
        logger.warning(f"Rate limit exceeded: {key}")
        return JSONResponse(
            status_code=429,
            content={"detail": "请求过于频繁，请稍后再试"},
        )

    return await call_next(request)