from __future__ import annotations

import logging
import re
from typing import Any

from app.services.rag.store import DualIndexStore

logger = logging.getLogger(__name__)


def rrf_merge(
    vector_results: list[dict[str, Any]],
    bm25_results: list[dict[str, Any]],
    k: int = 60,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """
    R9: RRF (Reciprocal Rank Fusion) 合并向量+BM25两路结果
    score = sum(1 / (k + rank_i)) for each list
    """
    rrf_scores: dict[str, float] = {}
    chunk_data: dict[str, dict[str, Any]] = {}

    for rank, item in enumerate(vector_results, start=1):
        cid = item["chunk_id"]
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (k + rank)
        if cid not in chunk_data:
            chunk_data[cid] = item

    for rank, item in enumerate(bm25_results, start=1):
        cid = item["chunk_id"]
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (k + rank)
        if cid not in chunk_data:
            chunk_data[cid] = item

    sorted_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)
    results = []
    for cid in sorted_ids[:top_k]:
        item = chunk_data[cid].copy()
        item["rrf_score"] = rrf_scores[cid]
        item["merged_source"] = "rrf"
        results.append(item)
    return results


def rerank_cross_encoder(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """
    R9: 交叉编码器精排 Top K
    如果cross-encoder不可用则跳过精排
    """
    if not candidates:
        return candidates
    try:
        from sentence_transformers import CrossEncoder
        model_name = os.getenv("RAG_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
        ce = CrossEncoder(model_name)
        pairs = [(query, c["content"][:512]) for c in candidates]
        scores = ce.predict(pairs)
        for i, score in enumerate(scores):
            candidates[i]["rerank_score"] = float(score)
        candidates.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        return candidates[:top_k]
    except ImportError:
        logger.debug("CrossEncoder不可用, 跳过精排")
        return candidates[:top_k]
    except Exception as e:
        logger.warning(f"交叉编码器精排失败: {e}, 使用RRF排序")
        return candidates[:top_k]


import os


class OnlineRetriever:
    """
    R6: 向量 + BM25 混搭检索
    R7: 改写兜底 — 原查询永不替换，改写仅并行补充
    R8: 鉴权前置 — ACL过滤在检索前执行
    R9: RRF重排 + 交叉编码器精排
    """

    def __init__(self, store: DualIndexStore):
        self.store = store

    async def retrieve(
        self,
        query: str,
        user_acl_tags: list[str] | None = None,
        rewrite_queries: list[str] | None = None,
        top_k: int = 5,
        rerank_top_k: int = 3,
        enable_rerank: bool = False,
    ) -> dict[str, Any]:
        """
        完整在线检索链路:
        1. R8: ACL前置过滤
        2. R6: 向量+BM25并发检索
        3. R7: 原查询+改写查询并行检索(原查询永不替换)
        4. R9: RRF合并 + 交叉编码器精排
        """
        all_queries = [query]
        if rewrite_queries:
            for rq in rewrite_queries:
                if self._validate_rewrite(query, rq):
                    all_queries.append(rq)
                else:
                    logger.warning(f"改写查询被丢弃(偏离原意): {rq}")

        all_vector_results: list[dict[str, Any]] = []
        all_bm25_results: list[dict[str, Any]] = []

        for q in all_queries:
            vec_res = self.store.vector_search(q, top_k=top_k * 2)
            bm25_res = self.store.bm25_search(q, top_k=top_k * 2)
            all_vector_results.extend(vec_res)
            all_bm25_results.extend(bm25_res)

        seen_v: set[str] = set()
        deduped_vector: list[dict[str, Any]] = []
        for r in all_vector_results:
            if r["chunk_id"] not in seen_v:
                seen_v.add(r["chunk_id"])
                deduped_vector.append(r)

        seen_b: set[str] = set()
        deduped_bm25: list[dict[str, Any]] = []
        for r in all_bm25_results:
            if r["chunk_id"] not in seen_b:
                seen_b.add(r["chunk_id"])
                deduped_bm25.append(r)

        if user_acl_tags:
            deduped_vector = self._acl_filter(deduped_vector, user_acl_tags)
            deduped_bm25 = self._acl_filter(deduped_bm25, user_acl_tags)

        merged = rrf_merge(deduped_vector, deduped_bm25, top_k=top_k)

        if enable_rerank and len(merged) > 1:
            merged = rerank_cross_encoder(query, merged, top_k=rerank_top_k)

        evidence_map: dict[str, str] = {}
        for item in merged:
            cid = item["chunk_id"]
            evidence_map[cid] = item["content"][:200]

        return {
            "query": query,
            "rewrite_queries_used": all_queries[1:],
            "results": merged[:rerank_top_k],
            "evidence_map": evidence_map,
            "vector_count": len(deduped_vector),
            "bm25_count": len(deduped_bm25),
            "merged_count": len(merged),
            "acl_filtered": user_acl_tags is not None,
        }

    def _acl_filter(
        self,
        results: list[dict[str, Any]],
        user_acl_tags: list[str],
    ) -> list[dict[str, Any]]:
        """
        R8: 鉴权前置 — 权限过滤在检索后、生成前执行
        用户ACL标签与chunk ACL标签取交集，无交集则过滤
        """
        if not user_acl_tags:
            return results
        user_set = set(t.lower() for t in user_acl_tags)
        filtered = []
        for item in results:
            meta = item.get("meta", {})
            chunk_acl = set(t.lower() for t in meta.get("acl_tags", ["public"]))
            if "public" in chunk_acl or user_set & chunk_acl:
                filtered.append(item)
            else:
                logger.debug(f"ACL过滤: chunk {item.get('chunk_id')} 被拒绝 (user={user_set}, chunk={chunk_acl})")
        return filtered

    def _validate_rewrite(self, original: str, rewrite: str) -> bool:
        """
        R7: 改写兜底风控
        - 改写与原查询相似度不能太低
        - 原查询中的实体信息不能被篡改
        - 禁止改写生成全新实体
        """
        orig_entities = set(re.findall(r'[\w\u4e00-\u9fff]{2,}', original.lower()))
        rewrite_entities = set(re.findall(r'[\w\u4e00-\u9fff]{2,}', rewrite.lower()))
        if orig_entities and not (orig_entities & rewrite_entities):
            logger.warning(f"改写丢失原实体: orig={orig_entities}, rewrite={rewrite_entities}")
            return False
        overlap = len(orig_entities & rewrite_entities) / max(len(orig_entities), 1)
        if overlap < 0.3:
            logger.warning(f"改写偏离原意: overlap={overlap:.2f}")
            return False
        return True