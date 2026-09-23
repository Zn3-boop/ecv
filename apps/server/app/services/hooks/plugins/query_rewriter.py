from __future__ import annotations

import logging
from typing import Any

from app.services.hooks.plugins.base import (
    QueryRewriter,
    RewriteResult,
    RewriteType,
)
from app.services.hooks.plugins.cache import QueryCache, DegradationChain

logger = logging.getLogger(__name__)

_query_cache = QueryCache(max_size=500, default_ttl_s=1800.0)
_degradation_chain = DegradationChain(cache=_query_cache)


class RuleBasedRewriter(QueryRewriter):
    """
    规则改写器: 纯规则，零LLM调用，毫秒级。
    - 去停用词生成web_query
    - 原样保留rag_query (向量库语义匹配不需要去停用词)
    - normalize + correct 两种改写类型
    """

    _STOP_WORDS = set("的了着过是在有和与或也都很还又再但而被把让给从向往到对于按照根据")
    _MAX_WEB_QUERY_LEN = 80

    async def rewrite(self, raw_query: str, context: dict[str, Any] | None = None) -> RewriteResult:
        standalone = raw_query.strip()
        rag_query = standalone
        web_query = self._strip_stop_words(standalone)
        retrieval = [rag_query]
        if web_query and web_query != rag_query:
            retrieval.append(web_query)

        rewrite_types = [RewriteType.NORMALIZE]
        corrected = self._simple_correct(standalone)
        if corrected != standalone:
            rewrite_types.append(RewriteType.CORRECT)
            retrieval.append(corrected)

        return RewriteResult(
            standalone_query=standalone,
            rag_query=rag_query,
            web_query=web_query[: self._MAX_WEB_QUERY_LEN],
            retrieval_queries=retrieval,
            rewrite_types=rewrite_types,
            confidence=1.0,
        )

    def _strip_stop_words(self, text: str) -> str:
        cleaned = "".join(ch for ch in text if ch not in self._STOP_WORDS)
        return " ".join(cleaned.split())

    def _simple_correct(self, text: str) -> str:
        corrections = {
            "LangGraph": "LangGraph",
            "langgraph": "LangGraph",
            "LangChain": "LangChain",
            "langchain": "LangChain",
        }
        result = text
        for wrong, right in corrections.items():
            if wrong in result and wrong != right:
                result = result.replace(wrong, right)
        return result


class LLMRewriter(QueryRewriter):
    """
    LLM改写器: 用大模型一次性生成rag_query + web_query。
    B3: 大模型清洗层 — 语义校验、标准化、纠错。
    降级: LLM失败时回退到RuleBasedRewriter。
    """

    _FALLBACK = RuleBasedRewriter()

    _PROMPT_TEMPLATE = """你是一个查询改写专家。请将用户原始问题改写为两种检索友好的形式。

规则:
1. rag_query: 语义描述式，适合向量库检索，保留完整语义
2. web_query: 简短关键词式，适合搜索引擎，去掉虚词，用空格分隔关键词
3. 不要改变用户核心需求
4. 如果用户有错别字，自动纠正
5. 如果有指代(如"它"、"这个")，根据上下文补全

用户原始问题: {raw_query}
上下文: {context}

请严格按JSON格式输出:
{{"rag_query": "...", "web_query": "...", "rewrite_types": ["normalize"], "confidence": 0.9}}"""

    async def rewrite(self, raw_query: str, context: dict[str, Any] | None = None) -> RewriteResult:
        cached = _query_cache.get(raw_query, context=context)
        if cached is not None:
            logger.debug(f"改写缓存命中: {raw_query[:30]}")
            return cached

        try:
            from app.services.llm.client import llm_parse_with_retry
            from pydantic import BaseModel, Field

            class RewriteOutput(BaseModel):
                rag_query: str = Field(default="")
                web_query: str = Field(default="")
                rewrite_types: list[str] = Field(default_factory=lambda: ["normalize"])
                confidence: float = Field(default=0.8)

            ctx_str = str(context or "")[:200]
            prompt = self._PROMPT_TEMPLATE.format(raw_query=raw_query, context=ctx_str)
            result, _ = await llm_parse_with_retry(prompt, RewriteOutput, max_retry=1, timeout=8.0)

            if result and result.rag_query:
                types = [RewriteType(t) for t in result.rewrite_types if t in [e.value for e in RewriteType]]
                rewrite_result = RewriteResult(
                    standalone_query=raw_query,
                    rag_query=result.rag_query,
                    web_query=result.web_query,
                    retrieval_queries=[result.rag_query, result.web_query],
                    rewrite_types=types or [RewriteType.NORMALIZE],
                    confidence=result.confidence,
                )
                _query_cache.set(raw_query, rewrite_result, context=context)
                return rewrite_result
        except Exception as e:
            logger.warning(f"LLM改写失败，降级规则改写: {e}")

        fallback_result = await self._FALLBACK.rewrite(raw_query, context)
        _query_cache.set(raw_query, fallback_result, context=context)
        return fallback_result


class CompositeRewriter(QueryRewriter):
    """
    组合改写器: 串联多个改写器，后一个可以基于前一个结果继续改写。
    用于: 规则预处理 → LLM精改写 的链路。
    """

    def __init__(self, rewriters: list[QueryRewriter]):
        self._rewriters = rewriters

    async def rewrite(self, raw_query: str, context: dict[str, Any] | None = None) -> RewriteResult:
        result: RewriteResult | None = None
        for rewriter in self._rewriters:
            result = await rewriter.rewrite(raw_query, context)
            if result and result.confidence >= 0.8:
                break
            raw_query = result.standalone_query if result else raw_query
        return result or RewriteResult(
            standalone_query=raw_query,
            rag_query=raw_query,
            web_query=raw_query,
        )