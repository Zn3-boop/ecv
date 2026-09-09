"""
LLM Provider 适配层测试 - 验证多 Provider 兼容、异常分类、限流、缓存
可量化指标：异常分类覆盖率、缓存命中率、限流间隔
"""
import asyncio
import json
import time
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

SERVER_ROOT = Path(__file__).resolve().parent.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.services.llm.provider import (
    LLMProvider,
    LLMProviderError,
    LLMContextTooLongError,
    LLMRateLimitError,
    LLMModelDisabledError,
    LLMUpstreamServerError,
    LLMBadResponseError,
    _classify_provider_error,
)
from app.services.llm.rate_limiter import LLMRateLimiter, rate_limiter


class TestProviderErrorClassification:
    """异常分类处理测试"""

    def test_context_too_long_400(self):
        err = _classify_provider_error(400, "context window exceeded")
        assert isinstance(err, LLMContextTooLongError)

    def test_context_too_long_413(self):
        err = _classify_provider_error(413, "token limit too long")
        assert isinstance(err, LLMContextTooLongError)

    def test_context_too_long_prompt_too_long(self):
        err = _classify_provider_error(400, "prompt is too long")
        assert isinstance(err, LLMContextTooLongError)

    def test_rate_limit_429(self):
        err = _classify_provider_error(429, "Too many requests")
        assert isinstance(err, LLMRateLimitError)

    def test_model_disabled_404(self):
        err = _classify_provider_error(404, "model not found")
        assert isinstance(err, LLMModelDisabledError)

    def test_model_disabled_403(self):
        err = _classify_provider_error(403, "model is disabled")
        assert isinstance(err, LLMModelDisabledError)

    def test_upstream_server_error_500(self):
        err = _classify_provider_error(500, "Internal Server Error")
        assert isinstance(err, LLMUpstreamServerError)

    def test_upstream_server_error_502(self):
        err = _classify_provider_error(502, "Bad Gateway")
        assert isinstance(err, LLMUpstreamServerError)

    def test_upstream_server_error_503(self):
        err = _classify_provider_error(503, "Service Unavailable")
        assert isinstance(err, LLMUpstreamServerError)

    def test_generic_error_400(self):
        err = _classify_provider_error(400, "bad request syntax")
        assert isinstance(err, LLMProviderError)
        assert not isinstance(err, LLMContextTooLongError)

    def test_generic_error_418(self):
        err = _classify_provider_error(418, "I'm a teapot")
        assert isinstance(err, LLMProviderError)

    def test_all_error_types_are_subclass_of_base(self):
        """所有异常类型应继承自 LLMProviderError"""
        assert issubclass(LLMContextTooLongError, LLMProviderError)
        assert issubclass(LLMRateLimitError, LLMProviderError)
        assert issubclass(LLMModelDisabledError, LLMProviderError)
        assert issubclass(LLMUpstreamServerError, LLMProviderError)
        assert issubclass(LLMBadResponseError, LLMProviderError)

    def test_error_classification_coverage(self):
        """异常分类覆盖率统计"""
        test_cases = [
            (400, "context window exceeded", LLMContextTooLongError),
            (413, "too many tokens", LLMContextTooLongError),
            (429, "rate limited", LLMRateLimitError),
            (404, "model not found", LLMModelDisabledError),
            (403, "model disabled", LLMModelDisabledError),
            (500, "server error", LLMUpstreamServerError),
            (502, "bad gateway", LLMUpstreamServerError),
            (503, "unavailable", LLMUpstreamServerError),
            (400, "bad syntax", LLMProviderError),
            (418, "teapot", LLMProviderError),
        ]
        classified = 0
        for status, text, expected_type in test_cases:
            err = _classify_provider_error(status, text)
            if isinstance(err, expected_type):
                classified += 1

        coverage = classified / len(test_cases) * 100
        print(f"\n[异常分类] {len(test_cases)} 种场景, 精确分类 {classified} 个, 覆盖率 {coverage:.0f}%")
        assert coverage == 100


class TestRateLimiter:
    """请求限流测试"""

    def test_cache_key_deterministic(self):
        rl = LLMRateLimiter()
        key1 = rl._make_cache_key(
            system_prompt="test", user_prompt="hello", temperature=0.2, response_format=None
        )
        key2 = rl._make_cache_key(
            system_prompt="test", user_prompt="hello", temperature=0.2, response_format=None
        )
        assert key1 == key2

    def test_cache_key_differs_for_different_input(self):
        rl = LLMRateLimiter()
        key1 = rl._make_cache_key(
            system_prompt="test", user_prompt="hello", temperature=0.2, response_format=None
        )
        key2 = rl._make_cache_key(
            system_prompt="test", user_prompt="world", temperature=0.2, response_format=None
        )
        assert key1 != key2

    def test_cache_set_and_get(self):
        rl = LLMRateLimiter()
        rl.set_cached(
            "cached_result",
            system_prompt="sys", user_prompt="usr", temperature=0.2, response_format=None,
        )
        result = rl.get_cached(
            system_prompt="sys", user_prompt="usr", temperature=0.2, response_format=None,
        )
        assert result == "cached_result"

    def test_cache_miss(self):
        rl = LLMRateLimiter()
        result = rl.get_cached(
            system_prompt="nonexist", user_prompt="nope", temperature=0.5, response_format=None,
        )
        assert result is None

    def test_cache_ttl_expiry(self):
        import os
        old = os.environ.get("LLM_CACHE_TTL_SECONDS")
        os.environ["LLM_CACHE_TTL_SECONDS"] = "0.01"
        try:
            rl = LLMRateLimiter()
            rl.set_cached(
                "expiring",
                system_prompt="s", user_prompt="u", temperature=0.2, response_format=None,
            )
            time.sleep(0.02)
            result = rl.get_cached(
                system_prompt="s", user_prompt="u", temperature=0.2, response_format=None,
            )
            assert result is None
        finally:
            if old is not None:
                os.environ["LLM_CACHE_TTL_SECONDS"] = old
            else:
                os.environ.pop("LLM_CACHE_TTL_SECONDS", None)

    def test_cache_max_entries_eviction(self):
        import os
        old = os.environ.get("LLM_CACHE_MAX_ENTRIES")
        os.environ["LLM_CACHE_MAX_ENTRIES"] = "3"
        try:
            rl = LLMRateLimiter()
            for i in range(5):
                rl.set_cached(
                    f"value_{i}",
                    system_prompt="sys", user_prompt=f"prompt_{i}", temperature=0.2, response_format=None,
                )
            assert len(rl._cache) <= 3
        finally:
            if old is not None:
                os.environ["LLM_CACHE_MAX_ENTRIES"] = old
            else:
                os.environ.pop("LLM_CACHE_MAX_ENTRIES", None)

    def test_rate_limit_interval(self):
        """限流间隔测试"""
        import os
        old = os.environ.get("LLM_MIN_INTERVAL_SECONDS")
        os.environ["LLM_MIN_INTERVAL_SECONDS"] = "0.05"
        try:
            rl = LLMRateLimiter()

            async def _run():
                start = time.perf_counter()
                await rl.wait_turn()
                await rl.wait_turn()
                elapsed = time.perf_counter() - start
                return elapsed

            elapsed = asyncio.run(_run())
            print(f"\n[限流] 两次请求间隔: {elapsed*1000:.1f}ms (预期 >= 50ms)")
            assert elapsed >= 0.04
        finally:
            if old is not None:
                os.environ["LLM_MIN_INTERVAL_SECONDS"] = old
            else:
                os.environ.pop("LLM_MIN_INTERVAL_SECONDS", None)

    def test_cache_hit_rate_benchmark(self):
        """缓存命中率基准测试"""
        rl = LLMRateLimiter()
        hits = 0
        total = 100

        for i in range(total):
            if i % 3 == 0:
                rl.set_cached(
                    f"result_{i}",
                    system_prompt="sys", user_prompt=f"q_{i}", temperature=0.2, response_format=None,
                )

            result = rl.get_cached(
                system_prompt="sys", user_prompt=f"q_{i}", temperature=0.2, response_format=None,
            )
            if result is not None:
                hits += 1

        hit_rate = hits / total * 100
        print(f"\n[缓存] {total} 次查询, 命中 {hits} 次, 命中率 {hit_rate:.1f}%")
        assert hit_rate > 0


class TestProviderManager:
    """多 Provider 管理测试"""

    def test_provider_config_dataclass(self):
        from app.services.provider_manager import ProviderConfig

        config = ProviderConfig(
            id="test",
            name="Test Provider",
            api_url="https://api.example.com/v1",
            api_key="sk-test",
            model="gpt-4",
        )
        assert config.id == "test"
        assert config.enabled is True
        assert config.api_type == "openai"

    def test_provider_url_auto_completion(self):
        from app.services.provider_manager import ProviderConfig

        config = ProviderConfig(
            id="test",
            name="Test",
            api_url="https://api.example.com/v1",
            api_key="sk-test",
        )
        full_url = config.get_full_url()
        assert "/chat/completions" in full_url

    def test_provider_url_already_complete(self):
        from app.services.provider_manager import ProviderConfig

        config = ProviderConfig(
            id="test",
            name="Test",
            api_url="https://api.example.com/v1/chat/completions",
            api_key="sk-test",
        )
        full_url = config.get_full_url()
        assert full_url == "https://api.example.com/v1/chat/completions"

    def test_provider_headers_with_api_key(self):
        from app.services.provider_manager import ProviderConfig

        config = ProviderConfig(
            id="test",
            name="Test",
            api_url="https://api.example.com/v1",
            api_key="sk-test",
        )
        headers = config.get_headers()
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer sk-test"

    def test_provider_headers_without_api_key(self):
        from app.services.provider_manager import ProviderConfig

        config = ProviderConfig(
            id="local",
            name="Local",
            api_url="http://localhost:11434/v1",
        )
        headers = config.get_headers()
        assert "Authorization" not in headers

    def test_openrouter_extra_headers(self):
        from app.services.provider_manager import ProviderConfig

        config = ProviderConfig(
            id="or",
            name="OpenRouter",
            api_url="https://openrouter.ai/api/v1",
            api_key="sk-or",
        )
        headers = config.get_headers()
        assert "HTTP-Referer" in headers
        assert "X-Title" in headers


class TestProviderLocalUrlDetection:
    """本地 URL 检测"""

    def test_localhost_is_local(self):
        assert LLMProvider._is_local_url("http://localhost:11434/v1") is True

    def test_127_is_local(self):
        assert LLMProvider._is_local_url("http://127.0.0.1:8000/v1") is True

    def test_remote_is_not_local(self):
        assert LLMProvider._is_local_url("https://api.openai.com/v1") is False

    def test_empty_url(self):
        assert LLMProvider._is_local_url("") is False