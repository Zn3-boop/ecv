from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LLMCallMetrics:
    ttft_ms: float = 0.0
    tpot_ms: float = 0.0
    total_latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    is_retry: bool = False
    error_type: str = ""


@dataclass
class ToolCallMetrics:
    tool_name: str = ""
    success: bool = True
    latency_ms: float = 0.0
    error: str = ""


class MetricsCollector:
    """
    生产级Agent可观测性指标采集器
    四个关键告警指标：
    1. 单任务token成本
    2. 工具调用失败率
    3. LLM延迟P99
    4. LLM重试率
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._llm_calls: list[LLMCallMetrics] = []
        self._tool_calls: list[ToolCallMetrics] = []
        self._session_costs: dict[str, float] = {}
        self._max_history = int(os.getenv("METRICS_MAX_HISTORY", "10000"))
        self._cost_alert_threshold = float(os.getenv("COST_ALERT_THRESHOLD", "2.0"))
        self._tool_failure_alert_threshold = float(os.getenv("TOOL_FAILURE_ALERT_THRESHOLD", "0.05"))
        self._llm_p99_alert_threshold_ms = float(os.getenv("LLM_P99_ALERT_THRESHOLD_MS", "10000"))
        self._llm_retry_alert_threshold = float(os.getenv("LLM_RETRY_ALERT_THRESHOLD", "0.3"))

        self._pricing: dict[str, dict[str, float]] = {
            "gpt-4o": {"prompt": 0.0025, "completion": 0.01},
            "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
            "qwen2.5-7b-instruct": {"prompt": 0.00004, "completion": 0.00012},
            "qwen2.5-72b-instruct": {"prompt": 0.0004, "completion": 0.0012},
        }

    def record_llm_call(self, metrics: LLMCallMetrics, session_id: str = "") -> dict[str, Any]:
        with self._lock:
            self._llm_calls.append(metrics)
            if len(self._llm_calls) > self._max_history:
                self._llm_calls = self._llm_calls[-self._max_history:]

        cost = self._compute_call_cost(metrics)
        if session_id and cost > 0:
            with self._lock:
                self._session_costs[session_id] = self._session_costs.get(session_id, 0.0) + cost

        alerts = self._check_llm_alerts(metrics)
        return {"cost_usd": cost, "alerts": alerts}

    def record_tool_call(self, metrics: ToolCallMetrics) -> dict[str, Any]:
        with self._lock:
            self._tool_calls.append(metrics)
            if len(self._tool_calls) > self._max_history:
                self._tool_calls = self._tool_calls[-self._max_history:]

        alerts = self._check_tool_alerts(metrics)
        return {"alerts": alerts}

    def get_llm_summary(self, window_minutes: int = 5) -> dict[str, Any]:
        cutoff = time.monotonic() - window_minutes * 60
        with self._lock:
            recent = self._llm_calls

        if not recent:
            return {"total_calls": 0}

        total = len(recent)
        retries = sum(1 for c in recent if c.is_retry)
        errors = sum(1 for c in recent if c.error_type)

        latencies = [c.total_latency_ms for c in recent if c.total_latency_ms > 0]
        ttfts = [c.ttft_ms for c in recent if c.ttft_ms > 0]
        tpots = [c.tpot_ms for c in recent if c.tpot_ms > 0]

        prompt_tokens = sum(c.prompt_tokens for c in recent)
        completion_tokens = sum(c.completion_tokens for c in recent)
        total_cost = sum(self._compute_call_cost(c) for c in recent)

        return {
            "total_calls": total,
            "retry_count": retries,
            "retry_rate": retries / total if total > 0 else 0.0,
            "error_count": errors,
            "error_rate": errors / total if total > 0 else 0.0,
            "latency_p50_ms": _percentile(latencies, 50),
            "latency_p95_ms": _percentile(latencies, 95),
            "latency_p99_ms": _percentile(latencies, 99),
            "ttft_p50_ms": _percentile(ttfts, 50),
            "ttft_p95_ms": _percentile(ttfts, 95),
            "ttft_p99_ms": _percentile(ttfts, 99),
            "tpot_p50_ms": _percentile(tpots, 50),
            "tpot_p95_ms": _percentile(tpots, 95),
            "tpot_p99_ms": _percentile(tpots, 99),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "total_cost_usd": round(total_cost, 6),
        }

    def get_tool_summary(self) -> dict[str, Any]:
        with self._lock:
            calls = self._tool_calls

        if not calls:
            return {"total_calls": 0}

        total = len(calls)
        failures = sum(1 for c in calls if not c.success)
        by_tool: dict[str, dict[str, int]] = {}
        for c in calls:
            if c.tool_name not in by_tool:
                by_tool[c.tool_name] = {"total": 0, "failures": 0}
            by_tool[c.tool_name]["total"] += 1
            if not c.success:
                by_tool[c.tool_name]["failures"] += 1

        return {
            "total_calls": total,
            "failure_count": failures,
            "failure_rate": failures / total if total > 0 else 0.0,
            "by_tool": by_tool,
        }

    def get_session_cost(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            cost = self._session_costs.get(session_id, 0.0)
        baseline = float(os.getenv("COST_BASELINE_USD", "0.01"))
        over_baseline = cost / baseline if baseline > 0 else 0.0
        return {
            "session_id": session_id,
            "cost_usd": round(cost, 6),
            "baseline_usd": baseline,
            "over_baseline_ratio": round(over_baseline, 2),
            "should_alert": over_baseline > self._cost_alert_threshold,
        }

    def _compute_call_cost(self, metrics: LLMCallMetrics) -> float:
        model_key = metrics.model.lower().replace("-", "").replace("_", "")
        pricing = None
        for key, prices in self._pricing.items():
            normalized_key = key.lower().replace("-", "").replace("_", "")
            if normalized_key == model_key:
                pricing = prices
                break

        if pricing is None:
            return 0.0

        prompt_cost = (metrics.prompt_tokens / 1000.0) * pricing.get("prompt", 0)
        completion_cost = (metrics.completion_tokens / 1000.0) * pricing.get("completion", 0)
        return prompt_cost + completion_cost

    def _check_llm_alerts(self, metrics: LLMCallMetrics) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []

        if metrics.total_latency_ms > self._llm_p99_alert_threshold_ms:
            alerts.append({
                "type": "llm_latency_high",
                "severity": "warning",
                "message": f"LLM latency {metrics.total_latency_ms:.0f}ms exceeds P99 threshold {self._llm_p99_alert_threshold_ms:.0f}ms",
                "model": metrics.model,
                "latency_ms": metrics.total_latency_ms,
            })

        if metrics.is_retry:
            with self._lock:
                recent = self._llm_calls[-100:]
            if recent:
                retry_rate = sum(1 for c in recent if c.is_retry) / len(recent)
                if retry_rate > self._llm_retry_alert_threshold:
                    alerts.append({
                        "type": "llm_retry_rate_high",
                        "severity": "warning",
                        "message": f"LLM retry rate {retry_rate:.1%} exceeds threshold {self._llm_retry_alert_threshold:.1%}",
                        "retry_rate": retry_rate,
                    })

        return alerts

    def _check_tool_alerts(self, metrics: ToolCallMetrics) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []

        if not metrics.success:
            with self._lock:
                recent = self._tool_calls[-100:]
            if recent:
                failure_rate = sum(1 for c in recent if not c.success) / len(recent)
                if failure_rate > self._tool_failure_alert_threshold:
                    alerts.append({
                        "type": "tool_failure_rate_high",
                        "severity": "warning",
                        "message": f"Tool failure rate {failure_rate:.1%} exceeds threshold {self._tool_failure_alert_threshold:.1%}",
                        "failure_rate": failure_rate,
                        "tool_name": metrics.tool_name,
                    })

        return alerts


def _percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = (pct / 100.0) * (len(sorted_vals) - 1)
    lower = int(idx)
    upper = lower + 1
    if upper >= len(sorted_vals):
        return sorted_vals[-1]
    frac = idx - lower
    return sorted_vals[lower] * (1 - frac) + sorted_vals[upper] * frac


_metrics_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector