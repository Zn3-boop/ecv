from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_RAGAS_DIR = os.path.join(os.path.expanduser("~"), ".ecv_ragas_results")


@dataclass
class RAGEvalCase:
    query: str
    expected_doc_ids: list[str] = field(default_factory=list)
    expected_answer: str = ""
    category: str = "general"
    difficulty: str = "medium"


@dataclass
class RetrievalMetrics:
    recall_at_k: float = 0.0
    mrr: float = 0.0
    hit_rate_at_5: float = 0.0
    precision_at_k: float = 0.0
    ndcg_at_k: float = 0.0


@dataclass
class GenerationMetrics:
    faithfulness: float = 0.0
    answer_relevance: float = 0.0
    context_relevance: float = 0.0


@dataclass
class RAGEvalResult:
    case: RAGEvalCase
    retrieved_doc_ids: list[str] = field(default_factory=list)
    generated_answer: str = ""
    retrieval_metrics: RetrievalMetrics = field(default_factory=RetrievalMetrics)
    generation_metrics: GenerationMetrics = field(default_factory=GenerationMetrics)
    latency_ms: float = 0.0
    error: str = ""


class RAGEvaluator:
    """
    RAG分层评测框架
    检索侧: Recall@K, MRR, HitRate@5, Precision@K, NDCG@K
    生成侧: Faithfulness, Answer Relevance, Context Relevance
    """

    def __init__(self, ragas_dir: str = ""):
        self.ragas_dir = ragas_dir or DEFAULT_RAGAS_DIR
        os.makedirs(self.ragas_dir, exist_ok=True)

    async def evaluate_retrieval(
        self,
        cases: list[RAGEvalCase],
        rag_service: Any,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """
        检索侧评测：对每个case执行检索，计算Recall@K/MRR/HitRate
        """
        results: list[RAGEvalResult] = []
        for case in cases:
            start = time.monotonic()
            try:
                query_result = await rag_service.query(
                    query=case.query,
                    top_k=top_k,
                )
                retrieved = query_result.get("retrieval", {}).get("results", [])
                retrieved_ids = [r.get("chunk_id", "") for r in retrieved]
                latency = (time.monotonic() - start) * 1000

                metrics = self._compute_retrieval_metrics(
                    expected=case.expected_doc_ids,
                    retrieved=retrieved_ids,
                    k=top_k,
                )

                results.append(RAGEvalResult(
                    case=case,
                    retrieved_doc_ids=retrieved_ids,
                    retrieval_metrics=metrics,
                    latency_ms=latency,
                ))
            except Exception as e:
                results.append(RAGEvalResult(
                    case=case,
                    error=str(e),
                    latency_ms=(time.monotonic() - start) * 1000,
                ))

        summary = self._aggregate_retrieval_results(results)
        self._save_results("retrieval_eval", summary, results)
        return summary

    async def evaluate_generation(
        self,
        cases: list[RAGEvalCase],
        rag_service: Any,
        llm_client: Any = None,
    ) -> dict[str, Any]:
        """
        生成侧评测：检索+生成，评估忠实度和答案相关性
        如果安装了RAGAS则使用RAGAS，否则用简化规则评估
        """
        try:
            return await self._evaluate_with_ragas(cases, rag_service)
        except ImportError:
            logger.info("RAGAS not installed, using simplified rule-based evaluation")
            return await self._evaluate_generation_simplified(cases, rag_service)

    async def _evaluate_with_ragas(
        self,
        cases: list[RAGEvalCase],
        rag_service: Any,
    ) -> dict[str, Any]:
        """
        使用RAGAS库进行标准评测
        """
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy, context_relevancy
        from datasets import Dataset

        eval_data: dict[str, list] = {
            "question": [],
            "answer": [],
            "contexts": [],
            "ground_truths": [],
        }

        for case in cases:
            query_result = await rag_service.query(query=case.query, top_k=5)
            retrieved = query_result.get("retrieval", {}).get("results", [])
            contexts = [r.get("content", "") for r in retrieved]

            answer = ""
            if "generation" in query_result:
                answer = query_result["generation"].get("answer", "")

            eval_data["question"].append(case.query)
            eval_data["answer"].append(answer)
            eval_data["contexts"].append(contexts)
            eval_data["ground_truths"].append([case.expected_answer] if case.expected_answer else [])

        dataset = Dataset.from_dict(eval_data)
        result = evaluate(
            dataset,
            metrics=[faithfulness, answer_relevancy, context_relevancy],
        )

        return {
            "engine": "ragas",
            "faithfulness": float(result.get("faithfulness", 0)),
            "answer_relevancy": float(result.get("answer_relevancy", 0)),
            "context_relevancy": float(result.get("context_relevancy", 0)),
            "case_count": len(cases),
        }

    async def _evaluate_generation_simplified(
        self,
        cases: list[RAGEvalCase],
        rag_service: Any,
    ) -> dict[str, Any]:
        """
        简化规则评估：不依赖RAGAS，用关键词重叠和长度比做近似评估
        """
        results: list[RAGEvalResult] = []
        for case in cases:
            try:
                query_result = await rag_service.query(query=case.query, top_k=5)
                retrieved = query_result.get("retrieval", {}).get("results", [])
                answer = query_result.get("generation", {}).get("answer", "")
                contexts_text = " ".join(r.get("content", "") for r in retrieved)

                faithfulness = self._estimate_faithfulness(answer, contexts_text)
                relevance = self._estimate_answer_relevance(case.query, answer)

                results.append(RAGEvalResult(
                    case=case,
                    generated_answer=answer,
                    generation_metrics=GenerationMetrics(
                        faithfulness=faithfulness,
                        answer_relevance=relevance,
                    ),
                ))
            except Exception as e:
                results.append(RAGEvalResult(case=case, error=str(e)))

        if not results:
            return {"engine": "simplified", "case_count": 0}

        avg_faith = sum(r.generation_metrics.faithfulness for r in results) / len(results)
        avg_rel = sum(r.generation_metrics.answer_relevance for r in results) / len(results)

        summary = {
            "engine": "simplified",
            "faithfulness": round(avg_faith, 4),
            "answer_relevance": round(avg_rel, 4),
            "case_count": len(results),
        }
        self._save_results("generation_eval", summary, results)
        return summary

    @staticmethod
    def _compute_retrieval_metrics(
        expected: list[str],
        retrieved: list[str],
        k: int = 5,
    ) -> RetrievalMetrics:
        if not expected:
            return RetrievalMetrics()

        expected_set = set(expected)
        retrieved_k = retrieved[:k]
        retrieved_set_k = set(retrieved_k)

        hits = expected_set & retrieved_set_k
        recall_at_k = len(hits) / len(expected_set) if expected_set else 0.0
        precision_at_k = len(hits) / k if k > 0 else 0.0
        hit_rate_at_5 = 1.0 if hits else 0.0

        mrr = 0.0
        for i, doc_id in enumerate(retrieved_k):
            if doc_id in expected_set:
                mrr = 1.0 / (i + 1)
                break

        dcg = 0.0
        for i, doc_id in enumerate(retrieved_k):
            rel = 1.0 if doc_id in expected_set else 0.0
            dcg += rel / (1.0 + (i + 1) - 1) if i > 0 else rel

        ideal_rels = sorted([1.0] * min(len(expected_set), k) + [0.0] * max(0, k - len(expected_set)), reverse=True)
        idcg = sum(ideal_rels)
        ndcg_at_k = dcg / idcg if idcg > 0 else 0.0

        return RetrievalMetrics(
            recall_at_k=round(recall_at_k, 4),
            mrr=round(mrr, 4),
            hit_rate_at_5=round(hit_rate_at_5, 4),
            precision_at_k=round(precision_at_k, 4),
            ndcg_at_k=round(ndcg_at_k, 4),
        )

    @staticmethod
    def _estimate_faithfulness(answer: str, context: str) -> float:
        if not answer or not context:
            return 0.0
        answer_words = set(answer.lower().split())
        context_words = set(context.lower().split())
        if not answer_words:
            return 0.0
        overlap = answer_words & context_words
        return len(overlap) / len(answer_words)

    @staticmethod
    def _estimate_answer_relevance(query: str, answer: str) -> float:
        if not answer:
            return 0.0
        query_words = set(query.lower().split())
        answer_words = set(answer.lower().split())
        if not query_words:
            return 0.0
        overlap = query_words & answer_words
        return len(overlap) / len(query_words)

    def _aggregate_retrieval_results(self, results: list[RAGEvalResult]) -> dict[str, Any]:
        valid = [r for r in results if not r.error]
        if not valid:
            return {"total": len(results), "errors": len(results)}

        avg_recall = sum(r.retrieval_metrics.recall_at_k for r in valid) / len(valid)
        avg_mrr = sum(r.retrieval_metrics.mrr for r in valid) / len(valid)
        avg_hit = sum(r.retrieval_metrics.hit_rate_at_5 for r in valid) / len(valid)
        avg_precision = sum(r.retrieval_metrics.precision_at_k for r in valid) / len(valid)
        avg_ndcg = sum(r.retrieval_metrics.ndcg_at_k for r in valid) / len(valid)
        avg_latency = sum(r.latency_ms for r in valid) / len(valid)

        by_category: dict[str, list[RAGEvalResult]] = {}
        for r in valid:
            cat = r.case.category
            by_category.setdefault(cat, []).append(r)

        category_metrics = {}
        for cat, cat_results in by_category.items():
            category_metrics[cat] = {
                "recall_at_k": round(sum(r.retrieval_metrics.recall_at_k for r in cat_results) / len(cat_results), 4),
                "mrr": round(sum(r.retrieval_metrics.mrr for r in cat_results) / len(cat_results), 4),
                "count": len(cat_results),
            }

        return {
            "total": len(results),
            "valid": len(valid),
            "errors": len(results) - len(valid),
            "recall_at_k": round(avg_recall, 4),
            "mrr": round(avg_mrr, 4),
            "hit_rate_at_5": round(avg_hit, 4),
            "precision_at_k": round(avg_precision, 4),
            "ndcg_at_k": round(avg_ndcg, 4),
            "avg_latency_ms": round(avg_latency, 1),
            "by_category": category_metrics,
        }

    def _save_results(self, name: str, summary: dict, results: list) -> None:
        ts = int(time.time())
        filepath = os.path.join(self.ragas_dir, f"{name}_{ts}.json")
        output = {
            "timestamp": ts,
            "summary": summary,
            "case_count": len(results),
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"RAG eval results saved to {filepath}")


def load_eval_cases(filepath: str) -> list[RAGEvalCase]:
    """
    从JSON文件加载评测集
    格式: [{"query": "...", "expected_doc_ids": [...], "expected_answer": "...", "category": "..."}]
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [
        RAGEvalCase(
            query=d.get("query", ""),
            expected_doc_ids=d.get("expected_doc_ids", []),
            expected_answer=d.get("expected_answer", ""),
            category=d.get("category", "general"),
            difficulty=d.get("difficulty", "medium"),
        )
        for d in data
    ]