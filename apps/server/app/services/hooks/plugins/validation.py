from __future__ import annotations

import logging
from typing import Any

from app.services.hooks.plugins.base import (
    ResultValidator,
    RetrievedDoc,
    ValidationResult,
)

logger = logging.getLogger(__name__)


class MinResultValidator(ResultValidator):
    """
    最小结果验证: 确保至少有1条有效结果。
    H5 Validation Gate — Checker层。
    """

    def __init__(self, min_results: int = 1, min_content_len: int = 10):
        self._min_results = min_results
        self._min_len = min_content_len

    async def validate(self, docs: list[RetrievedDoc], query: str) -> ValidationResult:
        valid = [d for d in docs if len(d.content.strip()) >= self._min_len]
        passed = len(valid) >= self._min_results
        return ValidationResult(
            passed=passed,
            reason="" if passed else f"有效结果不足: {len(valid)} < {self._min_results}",
            filtered_docs=valid,
            metrics={"total": len(docs), "valid": len(valid)},
        )


class ScoreThresholdValidator(ResultValidator):
    """
    分数阈值验证: 过滤低于阈值的低质量结果。
    """

    def __init__(self, min_score: float = 0.2):
        self._min_score = min_score

    async def validate(self, docs: list[RetrievedDoc], query: str) -> ValidationResult:
        filtered = [d for d in docs if d.score >= self._min_score]
        return ValidationResult(
            passed=len(filtered) > 0,
            reason="" if filtered else f"所有结果分数低于阈值 {self._min_score}",
            filtered_docs=filtered,
            metrics={"before": len(docs), "after": len(filtered)},
        )


class CompositeValidator(ResultValidator):
    """
    组合验证器: 串联多个验证器，全部通过才算通过。
    """

    def __init__(self, validators: list[ResultValidator]):
        self._validators = validators

    async def validate(self, docs: list[RetrievedDoc], query: str) -> ValidationResult:
        current = docs
        all_metrics: dict[str, Any] = {}
        for v in self._validators:
            result = await v.validate(current, query)
            all_metrics[v.name] = result.metrics
            current = result.filtered_docs
            if not result.passed:
                return ValidationResult(
                    passed=False,
                    reason=f"{v.name}: {result.reason}",
                    filtered_docs=current,
                    metrics=all_metrics,
                )
        return ValidationResult(passed=True, filtered_docs=current, metrics=all_metrics)