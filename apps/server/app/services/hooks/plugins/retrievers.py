from __future__ import annotations

import logging
from typing import Any

from app.services.hooks.plugins.base import (
    Retriever,
    RetrievedDoc,
    DocSource,
)

logger = logging.getLogger(__name__)


class RAGRetriever(Retriever):
    """
    本地向量库检索器: 调用项目已有 RAGService。
    R6: 向量+BM25混搭, R7: 原查询永不替换, R8: ACL鉴权前置, R9: RRF重排。
    """

    def __init__(self, top_k: int = 5, enable_rerank: bool = False):
        self._top_k = top_k
        self._enable_rerank = enable_rerank

    async def retrieve(self, query: str, top_k: int = 5, **kwargs: Any) -> list[RetrievedDoc]:
        try:
            from app.services.rag import get_rag_service

            rag = get_rag_service()
            user_acl = kwargs.get("user_acl", ["public"])
            rewrite_queries = kwargs.get("rewrite_queries")
            result = await rag.query(
                query=query,
                user_acl_tags=user_acl,
                rewrite_queries=rewrite_queries,
                top_k=top_k or self._top_k,
                rerank_top_k=3,
                enable_rerank=self._enable_rerank,
            )
            raw_results = result.get("retrieval", {}).get("results", [])
            return [
                RetrievedDoc(
                    content=r.get("content", ""),
                    source=DocSource.RAG,
                    score=float(r.get("rrf_score", r.get("score", 0.5))),
                    title=r.get("doc_title", ""),
                    chunk_id=r.get("chunk_id", ""),
                    metadata=r,
                )
                for r in raw_results
            ]
        except Exception as e:
            logger.debug(f"RAG检索失败: {e}")
            return []

    @property
    def source(self) -> DocSource:
        return DocSource.RAG


class DuckDuckGoRetriever(Retriever):
    """
    DuckDuckGo即时回答检索器 (免费, 无需API Key)。
    """

    def __init__(self, timeout: float = 6.0):
        self._timeout = timeout

    async def retrieve(self, query: str, top_k: int = 5, **kwargs: Any) -> list[RetrievedDoc]:
        try:
            import aiohttp

            url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1"
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=self._timeout)
                ) as resp:
                    data = await resp.json()
                    results: list[RetrievedDoc] = []

                    abstract = data.get("Abstract", "")
                    if abstract:
                        results.append(
                            RetrievedDoc(
                                content=abstract,
                                source=DocSource.WEB,
                                score=0.7,
                                title=data.get("Heading", ""),
                                url=data.get("AbstractURL", ""),
                            )
                        )

                    for topic in data.get("RelatedTopics", [])[: top_k - len(results)]:
                        if isinstance(topic, dict) and topic.get("Text"):
                            results.append(
                                RetrievedDoc(
                                    content=topic["Text"],
                                    source=DocSource.WEB,
                                    score=0.5,
                                    title=topic.get("Text", "")[:100],
                                    url=topic.get("FirstURL", ""),
                                )
                            )
                    return results[:top_k]
        except Exception as e:
            logger.debug(f"DuckDuckGo搜索失败: {e}")
            return []

    @property
    def source(self) -> DocSource:
        return DocSource.WEB


class TavilyRetriever(Retriever):
    """
    Tavily搜索检索器 (专为AI Agent设计, 返回干净内容)。
    需要环境变量 TAVILY_API_KEY。
    """

    def __init__(self, api_key: str = "", timeout: float = 8.0, search_depth: str = "basic"):
        self._api_key = api_key
        self._timeout = timeout
        self._search_depth = search_depth

    async def retrieve(self, query: str, top_k: int = 5, **kwargs: Any) -> list[RetrievedDoc]:
        import os

        api_key = self._api_key or os.getenv("TAVILY_API_KEY", "")
        if not api_key:
            logger.debug("Tavily API Key未配置，跳过")
            return []

        try:
            import aiohttp

            payload = {
                "api_key": api_key,
                "query": query,
                "max_results": top_k,
                "search_depth": self._search_depth,
                "include_answer": True,
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.tavily.com/search",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self._timeout),
                ) as resp:
                    data = await resp.json()
                    results: list[RetrievedDoc] = []

                    answer = data.get("answer", "")
                    if answer:
                        results.append(
                            RetrievedDoc(
                                content=answer,
                                source=DocSource.WEB,
                                score=0.8,
                                title="Tavily AI Answer",
                            )
                        )

                    for r in data.get("results", [])[: top_k - len(results)]:
                        results.append(
                            RetrievedDoc(
                                content=r.get("content", ""),
                                source=DocSource.WEB,
                                score=float(r.get("score", 0.5)),
                                title=r.get("title", ""),
                                url=r.get("url", ""),
                            )
                        )
                    return results
        except Exception as e:
            logger.debug(f"Tavily搜索失败: {e}")
            return []

    @property
    def source(self) -> DocSource:
        return DocSource.WEB


class SerpAPIRetriever(Retriever):
    """
    SerpAPI Google搜索检索器。
    需要环境变量 SERPAPI_KEY。
    """

    def __init__(self, api_key: str = "", timeout: float = 8.0):
        self._api_key = api_key
        self._timeout = timeout

    async def retrieve(self, query: str, top_k: int = 5, **kwargs: Any) -> list[RetrievedDoc]:
        import os

        api_key = self._api_key or os.getenv("SERPAPI_KEY", "")
        if not api_key:
            logger.debug("SerpAPI Key未配置，跳过")
            return []

        try:
            import aiohttp

            url = "https://serpapi.com/search"
            params = {
                "q": query,
                "api_key": api_key,
                "engine": "google",
                "num": top_k,
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, params=params, timeout=aiohttp.ClientTimeout(total=self._timeout)
                ) as resp:
                    data = await resp.json()
                    results: list[RetrievedDoc] = []
                    for r in data.get("organic_results", [])[:top_k]:
                        results.append(
                            RetrievedDoc(
                                content=r.get("snippet", ""),
                                source=DocSource.WEB,
                                score=0.6,
                                title=r.get("title", ""),
                                url=r.get("link", ""),
                            )
                        )
                    return results
        except Exception as e:
            logger.debug(f"SerpAPI搜索失败: {e}")
            return []

    @property
    def source(self) -> DocSource:
        return DocSource.WEB


class CodeSearchRetriever(Retriever):
    """
    项目代码语义搜索检索器。
    """

    async def retrieve(self, query: str, top_k: int = 5, **kwargs: Any) -> list[RetrievedDoc]:
        try:
            from app.services.code_search import get_code_search_service

            svc = get_code_search_service()
            root_dir = kwargs.get("root_dir", ".")
            result = await svc.search(
                query=query,
                root_dir=root_dir,
                max_results=top_k,
                user_acl=kwargs.get("user_acl", ["public"]),
            )
            items = result.get("results", [])
            return [
                RetrievedDoc(
                    content=item.get("content", ""),
                    source=DocSource.CODE,
                    score=float(item.get("score", 0.5)),
                    title=item.get("file_path", ""),
                    metadata=item,
                )
                for item in items
            ]
        except Exception as e:
            logger.debug(f"代码搜索失败: {e}")
            return []

    @property
    def source(self) -> DocSource:
        return DocSource.CODE