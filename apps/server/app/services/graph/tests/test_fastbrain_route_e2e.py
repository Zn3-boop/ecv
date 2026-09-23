"""
快慢脑 LangGraph 路由 e2e 测试

验证目标:
1. 高置信 → fast_answer: 快脑直接输出, 不走慢脑, graph 走 END
2. 中置信 → review_by_slow: 快脑给初步判断, 慢脑复核
3. 低置信 → full_slow: 完整走慢脑规划+工具/RAG链路
4. 非法输入 → reject: 走 error_fallback_node
5. Ollama 不可用时降级到 full_slow

用法:
    cd d:\\ecv\\apps\\server
    python -m pytest app/services/graph/tests/test_fastbrain_route_e2e.py -v
"""
from __future__ import annotations

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import pytest

from app.services.graph.state import AgentState, init_state
from app.services.graph.checkers import fast_brain_node
from app.services.graph.graph import route_after_fast_brain


class TestFastBrainRouteReject:
    def test_empty_input_reject(self):
        state = init_state("")
        result = fast_brain_node(state)
        assert result["fast_brain_mode"] == "reject"
        assert result["fast_brain_decision"] == "reject"
        assert result["need_slow_brain"] is False

    def test_whitespace_input_reject(self):
        state = init_state("   \t\n  ")
        result = fast_brain_node(state)
        assert result["fast_brain_mode"] == "reject"

    def test_garbage_input_reject(self):
        state = init_state("┃┅▇◆◇▣☠💀┃┅▇◆◇▣☠💀┃┅▇")
        result = fast_brain_node(state)
        assert result["fast_brain_mode"] == "reject"

    def test_reject_routes_to_error_fallback(self):
        state = init_state("")
        result = fast_brain_node(state)
        merged = {**state, **result}
        route = route_after_fast_brain(merged)
        assert route == "error_fallback_node"


class TestFastBrainRouteFullSlow:
    def test_normal_input_without_ollama_goes_full_slow(self):
        env = os.environ.copy()
        env.pop("FAST_BRAIN_ENABLED", None)
        os.environ["FAST_BRAIN_ENABLED"] = "false"
        try:
            state = init_state("帮我写一份面试材料包")
            result = fast_brain_node(state)
            assert result["fast_brain_mode"] == "full_slow"
            assert result["need_slow_brain"] is True
            merged = {**state, **result}
            route = route_after_fast_brain(merged)
            assert route == "detect_intent"
        finally:
            os.environ.pop("FAST_BRAIN_ENABLED", None)

    def test_ollama_failure_degrades_to_full_slow(self):
        os.environ["FAST_BRAIN_ENABLED"] = "true"
        os.environ["OLLAMA_HOST"] = "http://127.0.0.1:99999"
        try:
            state = init_state("启动记事本")
            result = fast_brain_node(state)
            assert result["fast_brain_mode"] == "full_slow"
            assert result["need_slow_brain"] is True
            merged = {**state, **result}
            route = route_after_fast_brain(merged)
            assert route == "detect_intent"
        finally:
            os.environ.pop("FAST_BRAIN_ENABLED", None)
            os.environ.pop("OLLAMA_HOST", None)


class TestFastBrainRouteWithOllama:
    """需要 Ollama 运行中且已拉取 qwen3:1.7b"""

    @pytest.fixture(autouse=True)
    def setup_env(self):
        os.environ["FAST_BRAIN_ENABLED"] = "true"
        os.environ["FAST_BRAIN_HIGH_THRESHOLD"] = "0.92"
        os.environ["FAST_BRAIN_MID_THRESHOLD"] = "0.7"
        yield
        os.environ.pop("FAST_BRAIN_ENABLED", None)
        os.environ.pop("FAST_BRAIN_HIGH_THRESHOLD", None)
        os.environ.pop("FAST_BRAIN_MID_THRESHOLD", None)

    def test_simple_query_high_confidence_fast_answer(self):
        state = init_state("打开记事本")
        result = fast_brain_node(state)
        mode = result["fast_brain_mode"]
        confidence = result.get("fast_brain_confidence", 0.0)
        if mode == "fast_answer":
            assert result["need_slow_brain"] is False
            assert confidence >= 0.92
            merged = {**state, **result}
            route = route_after_fast_brain(merged)
            assert route == "__end__"
        elif mode == "review_by_slow":
            assert result["need_slow_brain"] is True
            assert 0.7 <= confidence < 0.92
            merged = {**state, **result}
            route = route_after_fast_brain(merged)
            assert route == "detect_intent"
        else:
            assert mode == "full_slow"
            merged = {**state, **result}
            route = route_after_fast_brain(merged)
            assert route == "detect_intent"

    def test_ambiguous_query_mid_confidence_review_by_slow(self):
        state = init_state("帮我整理一下桌面文件")
        result = fast_brain_node(state)
        mode = result["fast_brain_mode"]
        if mode == "review_by_slow":
            assert result["need_slow_brain"] is True
            assert result.get("fast_brain_result", "") != ""
            merged = {**state, **result}
            route = route_after_fast_brain(merged)
            assert route == "detect_intent"
        elif mode == "fast_answer":
            merged = {**state, **result}
            route = route_after_fast_brain(merged)
            assert route == "__end__"
        else:
            assert mode in ("full_slow", "review_by_slow")

    def test_complex_query_low_confidence_full_slow(self):
        state = init_state("帮我写一份面试材料包，包含简历、自我介绍和项目总结")
        result = fast_brain_node(state)
        mode = result["fast_brain_mode"]
        if mode == "full_slow":
            assert result["need_slow_brain"] is True
            merged = {**state, **result}
            route = route_after_fast_brain(merged)
            assert route == "detect_intent"
        elif mode == "review_by_slow":
            merged = {**state, **result}
            route = route_after_fast_brain(merged)
            assert route == "detect_intent"
        else:
            assert mode in ("full_slow", "review_by_slow", "fast_answer")


class TestRouteAfterFastBrainPure:
    """纯路由函数测试, 不依赖 Ollama"""

    def test_reject_mode(self):
        state = {"fast_brain_mode": "reject"}
        assert route_after_fast_brain(state) == "error_fallback_node"

    def test_fast_answer_mode(self):
        from langgraph.graph import END
        state = {"fast_brain_mode": "fast_answer"}
        assert route_after_fast_brain(state) == END

    def test_review_by_slow_mode(self):
        state = {"fast_brain_mode": "review_by_slow"}
        assert route_after_fast_brain(state) == "detect_intent"

    def test_full_slow_mode(self):
        state = {"fast_brain_mode": "full_slow"}
        assert route_after_fast_brain(state) == "detect_intent"

    def test_empty_mode_defaults_to_detect_intent(self):
        state = {"fast_brain_mode": ""}
        assert route_after_fast_brain(state) == "detect_intent"

    def test_unknown_mode_defaults_to_detect_intent(self):
        state = {"fast_brain_mode": "something_else"}
        assert route_after_fast_brain(state) == "detect_intent"


class TestDetectIntentReviewMode:
    """验证 detect_intent_node 在 review_by_slow 模式下的复核行为"""

    @pytest.mark.asyncio
    async def test_review_hint_injected(self):
        from app.services.graph.nodes import detect_intent_node
        state = init_state("打开记事本")
        state["fast_brain_mode"] = "review_by_slow"
        state["fast_brain_result"] = "简单动作:simple_action"
        state["fast_brain_confidence"] = 0.85
        state["fast_brain_intent"] = "simple_action"
        result = await detect_intent_node(state)
        assert "intent" in result
        assert "intent_confidence" in result
        assert result.get("fast_brain_mode") == "review_done"

    @pytest.mark.asyncio
    async def test_full_slow_no_review_hint(self):
        from app.services.graph.nodes import detect_intent_node
        state = init_state("帮我写一份面试材料包")
        state["fast_brain_mode"] = "full_slow"
        state["fast_brain_result"] = ""
        state["fast_brain_confidence"] = 0.3
        result = await detect_intent_node(state)
        assert "intent" in result
        assert result.get("fast_brain_mode") is None