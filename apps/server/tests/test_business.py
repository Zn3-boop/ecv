"""
业务单元测试扩充：记忆Store、Governor治理、Tool-Search、信号持久化、LLM client。

用法：
    cd d:\\ecv\\apps\\server
    python -m pytest tests/test_business.py -v
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time

import pytest

from app.services.graph.state import init_state


# ==================== MemoryStore 测试 ====================

class TestMemoryStoreCRUD:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="test_memstore_")

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _make_store(self):
        from app.services.graph.memory_store import MemoryStore
        return MemoryStore(store_dir=self.tmp_dir)

    def test_put_and_get(self):
        store = self._make_store()
        store.put("u1", "app_notepad", {"path": "C:\\notepad.exe"}, level="A", owner="test")
        result = store.get("u1", "app_notepad")
        assert result is not None
        assert result["value"]["path"] == "C:\\notepad.exe"

    def test_d_level_rejected(self):
        store = self._make_store()
        store.put("u1", "inference_1", {"intent": "launch"}, level="D", owner="test")
        result = store.get("u1", "inference_1")
        assert result is None

    def test_list_keys(self):
        store = self._make_store()
        store.put("u1", "k1", {"v": 1}, level="A", owner="test")
        store.put("u1", "k2", {"v": 2}, level="A", owner="test")
        keys = store.list_keys("u1")
        assert set(keys) == {"k1", "k2"}

    def test_append_only_preserves_revision(self):
        store = self._make_store()
        store.put("u1", "fact1", {"ver": 1}, level="A", owner="test")
        store.put("u1", "fact1", {"ver": 2}, level="A", owner="test")
        result = store.get("u1", "fact1")
        assert result["value"]["ver"] == 2
        assert len(result["page_revision"]) >= 1
        assert result["page_revision"][0]["value"]["ver"] == 1

    def test_user_isolation(self):
        store = self._make_store()
        store.put("u1", "key1", {"v": 1}, level="A", owner="test")
        store.put("u2", "key1", {"v": 2}, level="A", owner="test")
        assert store.get("u1", "key1")["value"]["v"] == 1
        assert store.get("u2", "key1")["value"]["v"] == 2

    def test_put_user_preference(self):
        store = self._make_store()
        store.put_user_preference("u1", "notepad", owner="test")
        store.put_user_preference("u1", "notepad", owner="test")
        result = store.get("u1", "pref_app_notepad")
        assert result["value"]["launch_count"] == 2


# ==================== Governor 治理测试 ====================

class TestGovernorFullScan:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="test_governor_")

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _make_governing_store(self):
        from app.services.graph.memory_store import MemoryStore, SelfGoverningMemoryStore
        base = MemoryStore(store_dir=self.tmp_dir)
        return SelfGoverningMemoryStore(base_store=base)

    def test_full_scan_returns_structure(self):
        store = self._make_governing_store()
        result = store.full_scan(user_id="u1")
        assert "conflict" in result
        assert "expired" in result
        assert "signal_generated" in result

    def test_conflict_detection(self):
        store = self._make_governing_store()
        store.store.put("u1", "app_a", {"v": 1}, level="A", owner="test")
        store.store.put("u1", "app_b", {"v": 2}, level="A", owner="test")
        conflicts = store._detect_conflict("u1")
        assert len(conflicts) >= 1

    def test_expired_detection(self):
        store = self._make_governing_store()
        past_time = "2000-01-01T00:00:00"
        store.store.put("u1", "old_item", {"v": 1}, level="C", owner="test", expire_at=past_time)
        expired = store._detect_expired("u1")
        assert len(expired) >= 1

    def test_put_memory_triggers_scan(self):
        store = self._make_governing_store()
        result = store.put_memory(
            user_id="u1",
            key="test_key",
            value={"data": 42},
            evidence_level="A",
            owner="test",
        )
        assert "conflict" in result
        assert "expired" in result


# ==================== 信号持久化测试 ====================

class TestSignalPersistence:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="test_signal_persist_")

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _make_governing_store(self):
        from app.services.graph.memory_store import MemoryStore, SelfGoverningMemoryStore
        base = MemoryStore(store_dir=self.tmp_dir)
        return SelfGoverningMemoryStore(base_store=base)

    def test_signal_written_to_disk(self):
        store = self._make_governing_store()
        sig_id = store.generate_correction_signal(
            user_id="u1",
            signal_type="conflict",
            related_keys=["k1"],
            detail="test conflict",
        )
        signal_file = os.path.join(self.tmp_dir, "signals", "signals.json")
        assert os.path.exists(signal_file)
        with open(signal_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert sig_id in data

    def test_signal_survives_restart(self):
        store1 = self._make_governing_store()
        sig_id = store1.generate_correction_signal(
            user_id="u1",
            signal_type="expired",
            related_keys=["k1"],
            detail="test expired",
        )
        from app.services.graph.memory_store import MemoryStore, SelfGoverningMemoryStore
        base2 = MemoryStore(store_dir=self.tmp_dir)
        store2 = SelfGoverningMemoryStore(base_store=base2)
        sig = store2.get_signal(sig_id)
        assert sig is not None
        assert sig["status"] == "open"

    def test_signal_status_update_persists(self):
        store = self._make_governing_store()
        sig_id = store.generate_correction_signal(
            user_id="u1",
            signal_type="conflict",
            related_keys=["k1"],
            detail="test",
        )
        ok = store.update_signal_status(sig_id, "processing", owner="admin")
        assert ok
        from app.services.graph.memory_store import MemoryStore, SelfGoverningMemoryStore
        base2 = MemoryStore(store_dir=self.tmp_dir)
        store2 = SelfGoverningMemoryStore(base_store=base2)
        sig = store2.get_signal(sig_id)
        assert sig["status"] == "processing"


# ==================== Tool-Search 测试 ====================

class TestToolSearchExtended:
    def test_search_by_name(self):
        from app.services.graph.tool_search import ToolDef, ToolSearch
        tools = [
            ToolDef(name="app_launch", description="启动应用", input_schema={}),
            ToolDef(name="app_kill", description="结束应用", input_schema={}),
            ToolDef(name="screenshot", description="截图", input_schema={}),
        ]
        ts = ToolSearch(tools)
        hits = ts.search_tool("launch", top_k=2)
        assert len(hits) == 1
        assert hits[0].name == "app_launch"

    def test_search_by_description(self):
        from app.services.graph.tool_search import ToolDef, ToolSearch
        tools = [
            ToolDef(name="tool_a", description="截图工具", input_schema={}),
        ]
        ts = ToolSearch(tools)
        hits = ts.search_tool("截图", top_k=3)
        assert len(hits) == 1

    def test_search_empty_query(self):
        from app.services.graph.tool_search import ToolDef, ToolSearch
        tools = [ToolDef(name="t1", description="d1", input_schema={})]
        ts = ToolSearch(tools)
        assert ts.search_tool("", top_k=3) == []
        assert ts.search_tool("   ", top_k=3) == []

    def test_search_no_match(self):
        from app.services.graph.tool_search import ToolDef, ToolSearch
        tools = [ToolDef(name="t1", description="d1", input_schema={})]
        ts = ToolSearch(tools)
        assert ts.search_tool("nonexistent", top_k=3) == []

    def test_always_load_on_init(self):
        from app.services.graph.tool_search import ToolDef, ToolSearch
        tools = [
            ToolDef(name="core", description="核心", input_schema={}, alwaysLoad=True),
            ToolDef(name="lazy", description="懒加载", input_schema={}, defer_loading=True),
        ]
        ts = ToolSearch(tools)
        loaded_names = [t.name for t in ts.loaded]
        assert "core" in loaded_names
        assert "lazy" not in loaded_names

    def test_load_defer_tool(self):
        from app.services.graph.tool_search import ToolDef, ToolSearch
        tools = [
            ToolDef(name="lazy", description="懒加载", input_schema={}, defer_loading=True),
        ]
        ts = ToolSearch(tools)
        ok = ts.load_tool_schema("lazy")
        assert ok
        loaded_names = [t.name for t in ts.loaded]
        assert "lazy" in loaded_names

    def test_search_tool_cannot_defer(self):
        from app.services.graph.tool_search import ToolDef, ToolSearch
        tools = [
            ToolDef(name="tool_search", description="检索工具", input_schema={}, defer_loading=True),
        ]
        ts = ToolSearch(tools)
        loaded_names = [t.name for t in ts.loaded]
        assert "tool_search" in loaded_names


# ==================== LLM Client 测试 ====================

class TestLLMClientHelpers:
    def test_is_transient_timeout(self):
        from app.services.llm.client import is_transient_llm_error
        try:
            from openai import APITimeoutError
            assert is_transient_llm_error(APITimeoutError(request=None)) is True
        except ImportError:
            pass

    def test_is_transient_connection_error(self):
        from app.services.llm.client import is_transient_llm_error
        try:
            from openai import APIConnectionError
            assert is_transient_llm_error(APIConnectionError(request=None)) is True
        except ImportError:
            pass

    def test_is_transient_business_error_false(self):
        from app.services.llm.client import is_transient_llm_error
        assert is_transient_llm_error(ValueError("bad input")) is False
        assert is_transient_llm_error(Exception("generic")) is False

    def test_fallback_values(self):
        from app.services.llm.client import (
            IntentDetectOutput,
            EntityExtractOutput,
            RouteOutput,
            QueryRewriteOutput,
        )
        i = IntentDetectOutput(intent="test", intent_confidence=0.5)
        assert i.intent == "test"
        e = EntityExtractOutput(entities={"k": "v"})
        assert e.entities == {"k": "v"}
        r = RouteOutput(route_target="node1", agent_input={}, route_confidence=0.8)
        assert r.route_target == "node1"
        q = QueryRewriteOutput(standalone_query="q", retrieval_queries=["q1", "q2"])
        assert len(q.retrieval_queries) == 2


# ==================== Metrics 测试 ====================

class TestMetricsDevMode:
    def test_counter_increment(self):
        from app.services.graph.metrics import inc_counter, get_all_counters
        before = get_all_counters().get("test_counter", 0)
        inc_counter("test_counter")
        after = get_all_counters().get("test_counter", 0)
        assert after == before + 1

    def test_counter_with_labels(self):
        from app.services.graph.metrics import inc_counter, get_all_counters
        inc_counter("test_labelled", labels={"reason": "timeout"})
        counters = get_all_counters()
        assert "test_labelled{reason=timeout}" in counters

    def test_histogram_observe(self):
        from app.services.graph.metrics import observe_duration, get_all_histograms
        observe_duration("test_hist", 0.5, {"node": "fast_brain"})
        histograms = get_all_histograms()
        key = "test_hist{node=fast_brain}"
        assert key in histograms
        assert 0.5 in histograms[key]

    def test_node_metrics_context_manager(self):
        from app.services.graph.metrics import NodeMetrics, get_all_histograms
        with NodeMetrics("test_node"):
            time.sleep(0.01)
        histograms = get_all_histograms()
        key = "graph_node_duration_seconds{node=test_node}"
        assert key in histograms
        assert histograms[key][-1] >= 0.01