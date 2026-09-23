from __future__ import annotations

import logging
from typing import Any

from app.services.hooks.plugins.base import (
    FusionStrategy,
    FusionInput,
    RetrievedDoc,
    DocSource,
)

logger = logging.getLogger(__name__)


class SimpleConcatFusion(FusionStrategy):
    """
    方案A: 简单拼接 — RAG片段在前，Web结果在后，统一截断。
    适合原型快速验证。
    """

    def __init__(self, max_content_len: int = 300, max_docs_per_source: int = 3):
        self._max_len = max_content_len
        self._max_docs = max_docs_per_source

    async def fuse(self, fusion_input: FusionInput) -> str:
        parts: list[str] = []
        rag_docs = fusion_input.rag_docs[: self._max_docs]
        web_docs = fusion_input.web_docs[: self._max_docs]

        if rag_docs:
            rag_text = "\n".join(d.content[: self._max_len] for d in rag_docs)
            parts.append(f"【内部知识库】\n{rag_text}")
        if web_docs:
            web_text = "\n".join(d.content[: self._max_len] for d in web_docs)
            parts.append(f"【互联网检索（可能存在偏差）】\n{web_text}")

        return "\n\n".join(parts)


class WeightedFusion(FusionStrategy):
    """
    方案C: 加权融合 — 区分来源可信度，内部知识库权重高，网络权重低。
    适合企业场景：优先相信内部资料，网络信息做补充。
    """

    def __init__(self, max_content_len: int = 300, max_total_docs: int = 6):
        self._max_len = max_content_len
        self._max_total = max_total_docs

    async def fuse(self, fusion_input: FusionInput) -> str:
        rag_weight = fusion_input.rag_weight
        web_weight = fusion_input.web_weight

        scored: list[tuple[str, str, float]] = []
        for doc in fusion_input.rag_docs:
            scored.append(("rag", doc.content[: self._max_len], doc.score * rag_weight))
        for doc in fusion_input.web_docs:
            scored.append(("web", doc.content[: self._max_len], doc.score * web_weight))

        scored.sort(key=lambda x: x[2], reverse=True)

        parts: list[str] = []
        for source, content, score in scored[: self._max_total]:
            label = "内部知识库" if source == "rag" else "互联网（可能有偏差）"
            parts.append(f"[{label}] {content}")

        return "\n\n".join(parts)


class RerankFusion(FusionStrategy):
    """
    方案B: 统一重排 — 把本地+网页全部丢进重排模型统一打分，取TopN。
    优先使用交叉编码器精排，不可用时降级为score排序。
    """

    def __init__(self, max_content_len: int = 300, max_total_docs: int = 6):
        self._max_len = max_content_len
        self._max_total = max_total_docs

    async def fuse(self, fusion_input: FusionInput) -> str:
        all_docs: list[RetrievedDoc] = list(fusion_input.rag_docs) + list(fusion_input.web_docs)

        if not all_docs:
            return ""

        query = fusion_input.query
        reranked = await self._try_cross_encoder_rerank(query, all_docs)
        if reranked is None:
            all_docs.sort(key=lambda d: d.score, reverse=True)
            reranked = all_docs

        return "\n\n".join(d.content[: self._max_len] for d in reranked[: self._max_total])

    async def _try_cross_encoder_rerank(
        self, query: str, docs: list[RetrievedDoc]
    ) -> list[RetrievedDoc] | None:
        try:
            from sentence_transformers import CrossEncoder
            import os

            model_name = os.getenv("RAG_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
            ce = CrossEncoder(model_name)
            pairs = [(query, d.content[:512]) for d in docs]
            scores = ce.predict(pairs)
            for i, score in enumerate(scores):
                docs[i] = RetrievedDoc(
                    content=docs[i].content,
                    source=docs[i].source,
                    score=float(score),
                    title=docs[i].title,
                    url=docs[i].url,
                    chunk_id=docs[i].chunk_id,
                    metadata={**docs[i].metadata, "rerank_score": float(score)},
                )
            docs.sort(key=lambda d: d.score, reverse=True)
            return docs
        except ImportError:
            logger.debug("CrossEncoder不可用，降级score排序")
            return None
        except Exception as e:
            logger.warning(f"交叉编码器精排失败: {e}")
            return None


class SourcePriorityFusion(FusionStrategy):
    """
    来源优先级融合: 按来源分组排序，每组内部按score排序。
    优先级: RAG > CODE > WEB > CUSTOM
    每组最多取N条，总结果截断到max_total。
    """

    _PRIORITY = {DocSource.RAG: 0, DocSource.CODE: 1, DocSource.WEB: 2, DocSource.CUSTOM: 3}

    def __init__(self, max_per_source: int = 3, max_total_docs: int = 8, max_content_len: int = 300):
        self._max_per_source = max_per_source
        self._max_total = max_total_docs
        self._max_len = max_content_len

    async def fuse(self, fusion_input: FusionInput) -> str:
        all_docs = list(fusion_input.rag_docs) + list(fusion_input.web_docs)
        by_source: dict[DocSource, list[RetrievedDoc]] = {}
        for doc in all_docs:
            by_source.setdefault(doc.source, []).append(doc)

        ordered: list[RetrievedDoc] = []
        for source in sorted(by_source.keys(), key=lambda s: self._PRIORITY.get(s, 99)):
            group = sorted(by_source[source], key=lambda d: d.score, reverse=True)
            ordered.extend(group[: self._max_per_source])

        parts: list[str] = []
        for doc in ordered[: self._max_total]:
            source_label = {
                DocSource.RAG: "内部知识库",
                DocSource.WEB: "互联网（可能有偏差）",
                DocSource.CODE: "项目代码",
                DocSource.CUSTOM: "自定义来源",
            }.get(doc.source, "未知来源")
            parts.append(f"[{source_label}] {doc.content[: self._max_len]}")

        return "\n\n".join(parts)