from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)
ENV = os.getenv("GRAPH_ENV", "dev")

if ENV == "prod":
    try:
        from prometheus_client import Counter, Histogram, Gauge
    except ImportError:
        logger.warning("prometheus_client未安装，降级为dev内存模式")
        ENV = "dev"

if ENV == "prod":
    fast_brain_filter_total = Counter("fast_brain_filter_total", "快脑过滤计数", ["reason"])
    fallback_triggered_total = Counter("fallback_triggered_total", "降级触发次数")
    tool_search_invoked_total = Counter("tool_search_invoked_total", "工具检索调用次数")
    tool_search_zero_hit_total = Counter("tool_search_zero_hit_total", "检索0命中")
    governor_light_scan_total = Counter("governor_light_scan_total", "轻量扫描")
    governor_full_scan_total = Counter("governor_full_scan_total", "全量扫描")
    governor_signal_generated_total = Counter("governor_signal_generated_total", "生成纠错信号")
    supervisor_diagnose_signal_total = Counter("supervisor_diagnose_signal_total", "supervisor诊断信号")
    graph_node_duration_seconds = Histogram("graph_node_duration_seconds", "节点耗时", ["node"])
    signal_status_open_total = Gauge("signal_status_open_total", "open状态信号")
    signal_status_resolved_total = Gauge("signal_status_resolved_total", "resolved状态信号")
    graph_clarification_trigger_total = Counter("graph_clarification_trigger_total", "澄清触发")
    graph_security_blocked_total = Counter("graph_security_blocked_total", "安全拦截", ["reason"])
    graph_tool_failure_total = Counter("graph_tool_failure_total", "工具失败", ["tool"])

    graph_correction_trigger_total = Counter("graph_correction_trigger_total", "自校正循环触发总次数")
    graph_correction_success_total = Counter("graph_correction_success_total", "自校正循环成功次数")
    graph_correction_exhaust_total = Counter("graph_correction_exhaust_total", "校正达到上限终止次数")
    graph_correction_timeout_total = Counter("graph_correction_timeout_total", "LLM重写超时次数")

    def inc_counter(name: str, labels: dict[str, str] | None = None):
        labels = labels or {}
        if name == "fallback_triggered_total":
            fallback_triggered_total.inc()
        elif name == "tool_search_invoked_total":
            tool_search_invoked_total.inc()
        elif name == "tool_search_zero_hit_total":
            tool_search_zero_hit_total.inc()
        elif name == "governor_light_scan_total":
            governor_light_scan_total.inc()
        elif name == "governor_full_scan_total":
            governor_full_scan_total.inc()
        elif name == "governor_signal_generated_total":
            governor_signal_generated_total.inc()
        elif name == "supervisor_diagnose_signal_total":
            supervisor_diagnose_signal_total.inc()
        elif name == "graph_clarification_trigger_total":
            graph_clarification_trigger_total.inc()
        elif name == "graph_security_blocked_total":
            graph_security_blocked_total.labels(**labels).inc()
        elif name == "graph_tool_failure_total":
            graph_tool_failure_total.labels(**labels).inc()
        elif name == "graph_correction_trigger_total":
            graph_correction_trigger_total.inc()
        elif name == "graph_correction_success_total":
            graph_correction_success_total.inc()
        elif name == "graph_correction_exhaust_total":
            graph_correction_exhaust_total.inc()
        elif name == "graph_correction_timeout_total":
            graph_correction_timeout_total.inc()
        elif name == "fast_brain_filter_total":
            fast_brain_filter_total.labels(**labels).inc()
        elif name == "signal_status_open_total":
            signal_status_open_total.inc()
        elif name == "signal_status_resolved_total":
            signal_status_resolved_total.inc()

    def observe_duration(name: str, seconds: float, labels: dict[str, str] | None = None):
        labels = labels or {}
        if name == "graph_node_duration_seconds":
            graph_node_duration_seconds.labels(**labels).observe(seconds)

    def gauge_set_open(v: int):
        signal_status_open_total.set(v)

    def gauge_set_resolved(v: int):
        signal_status_resolved_total.set(v)

    def get_all_counters():
        return {}

    def get_all_histograms():
        return {}

else:
    _counters: dict[str, int] = {}
    _histograms: dict[str, list[float]] = {}

    def inc_counter(name: str, labels: dict[str, str] | None = None):
        key = name
        if labels:
            key += "{" + ",".join(f"{k}={v}" for k, v in sorted(labels.items())) + "}"
        _counters[key] = _counters.get(key, 0) + 1

    def observe_duration(name: str, seconds: float, labels: dict[str, str] | None = None):
        key = name
        if labels:
            key += "{" + ",".join(f"{k}={v}" for k, v in sorted(labels.items())) + "}"
        if key not in _histograms:
            _histograms[key] = []
        _histograms[key].append(seconds)

    def gauge_set_open(v: int):
        pass

    def gauge_set_resolved(v: int):
        pass

    def get_all_counters():
        return dict(_counters)

    def get_all_histograms():
        return {k: list(v) for k, v in _histograms.items()}


class NodeMetrics:
    def __init__(self, node_name: str):
        self.node_name = node_name
        self._start = 0.0

    def __enter__(self):
        self._start = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        dur = time.monotonic() - self._start
        observe_duration("graph_node_duration_seconds", dur, {"node": self.node_name})
        return False

    @staticmethod
    def count_clarification():
        inc_counter("graph_clarification_trigger_total")

    @staticmethod
    def count_injection_blocked():
        inc_counter("graph_security_blocked_total", {"reason": "injection"})

    @staticmethod
    def count_high_risk_blocked():
        inc_counter("graph_security_blocked_total", {"reason": "high_risk"})

    @staticmethod
    def count_tool_failure(tool_name: str):
        inc_counter("graph_tool_failure_total", {"tool": tool_name})

    @staticmethod
    def count_fallback_triggered():
        inc_counter("fallback_triggered_total")

    @staticmethod
    def count_signal_open():
        inc_counter("signal_status_open_total")

    @staticmethod
    def count_signal_resolved():
        inc_counter("signal_status_resolved_total")

    @staticmethod
    def count_correction_trigger():
        inc_counter("graph_correction_trigger_total")

    @staticmethod
    def count_correction_success():
        inc_counter("graph_correction_success_total")

    @staticmethod
    def count_correction_exhaust():
        inc_counter("graph_correction_exhaust_total")

    @staticmethod
    def count_correction_timeout():
        inc_counter("graph_correction_timeout_total")