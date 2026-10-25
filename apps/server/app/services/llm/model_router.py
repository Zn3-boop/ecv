from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TaskComplexity(str, Enum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


TASK_MODEL_MAP = {
    TaskComplexity.SIMPLE: os.getenv("MODEL_SIMPLE", "qwen2.5-7b-instruct"),
    TaskComplexity.MEDIUM: os.getenv("MODEL_MEDIUM", "qwen2.5-7b-instruct"),
    TaskComplexity.COMPLEX: os.getenv("MODEL_COMPLEX", "qwen2.5-72b-instruct"),
}

TASK_TYPE_COMPLEXITY = {
    "classification": TaskComplexity.SIMPLE,
    "extraction": TaskComplexity.SIMPLE,
    "summarization": TaskComplexity.MEDIUM,
    "rag_qa": TaskComplexity.MEDIUM,
    "planning": TaskComplexity.COMPLEX,
    "reasoning": TaskComplexity.COMPLEX,
    "code_generation": TaskComplexity.COMPLEX,
    "multi_step": TaskComplexity.COMPLEX,
}


class ModelRouter:
    """
    多模型路由网关：按任务类型路由到不同模型
    - 7B：分类/抽取/简单问答（低延迟、低成本）
    - 72B：推理规划/代码生成/复杂多步（高质量）
    """

    def __init__(self):
        self._model_map = dict(TASK_MODEL_MAP)
        self._task_type_map = dict(TASK_TYPE_COMPLEXITY)
        self._routing_stats: dict[str, int] = {}

    def route(self, task_type: str = "", query: str = "", intent: str = "") -> dict[str, Any]:
        complexity = self._determine_complexity(task_type, query, intent)
        model = self._model_map.get(complexity, self._model_map[TaskComplexity.MEDIUM])

        self._routing_stats[model] = self._routing_stats.get(model, 0) + 1

        return {
            "model": model,
            "complexity": complexity.value,
            "task_type": task_type,
            "reason": self._routing_reason(complexity, task_type),
        }

    def route_by_token_estimate(self, estimated_input_tokens: int, estimated_output_tokens: int) -> dict[str, Any]:
        if estimated_input_tokens > 4000 or estimated_output_tokens > 500:
            complexity = TaskComplexity.COMPLEX
        elif estimated_input_tokens > 1000 or estimated_output_tokens > 100:
            complexity = TaskComplexity.MEDIUM
        else:
            complexity = TaskComplexity.SIMPLE

        model = self._model_map.get(complexity, self._model_map[TaskComplexity.MEDIUM])
        self._routing_stats[model] = self._routing_stats.get(model, 0) + 1

        return {
            "model": model,
            "complexity": complexity.value,
            "reason": f"input={estimated_input_tokens}tok, output={estimated_output_tokens}tok",
        }

    def _determine_complexity(self, task_type: str, query: str, intent: str) -> TaskComplexity:
        if task_type and task_type in self._task_type_map:
            return self._task_type_map[task_type]

        if intent:
            intent_lower = intent.lower()
            if any(kw in intent_lower for kw in ["plan", "reason", "code", "debug", "analyze", "compare"]):
                return TaskComplexity.COMPLEX
            if any(kw in intent_lower for kw in ["classify", "extract", "detect", "check"]):
                return TaskComplexity.SIMPLE

        if query:
            query_lower = query.lower()
            complex_keywords = ["分析", "对比", "规划", "设计", "为什么", "如何", "原因", "方案"]
            if any(kw in query_lower for kw in complex_keywords):
                return TaskComplexity.COMPLEX
            simple_keywords = ["是什么", "多少", "有没有", "是否", "查一下"]
            if any(kw in query_lower for kw in simple_keywords):
                return TaskComplexity.SIMPLE

        return TaskComplexity.MEDIUM

    @staticmethod
    def _routing_reason(complexity: TaskComplexity, task_type: str) -> str:
        reasons = {
            TaskComplexity.SIMPLE: "简单任务(分类/抽取)→7B模型(低延迟低成本)",
            TaskComplexity.MEDIUM: "中等任务(摘要/问答)→7B模型(平衡延迟与质量)",
            TaskComplexity.COMPLEX: "复杂任务(推理/规划)→72B模型(高质量)",
        }
        base = reasons.get(complexity, "")
        if task_type:
            return f"[{task_type}] {base}"
        return base

    def get_stats(self) -> dict[str, Any]:
        total = sum(self._routing_stats.values())
        return {
            "total_requests": total,
            "by_model": dict(self._routing_stats),
            "cost_saving_ratio": self._estimate_cost_saving(),
        }

    def _estimate_cost_saving(self) -> float:
        if not self._routing_stats:
            return 0.0
        simple_count = sum(v for k, v in self._routing_stats.items() if "7b" in k.lower())
        total = sum(self._routing_stats.values())
        if total == 0:
            return 0.0
        all_complex_cost = total * 10.0
        routed_cost = simple_count * 1.0 + (total - simple_count) * 10.0
        return (all_complex_cost - routed_cost) / all_complex_cost


_model_router: ModelRouter | None = None


def get_model_router() -> ModelRouter:
    global _model_router
    if _model_router is None:
        _model_router = ModelRouter()
    return _model_router