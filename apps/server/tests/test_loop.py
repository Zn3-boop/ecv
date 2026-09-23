import os

os.environ["GRAPH_ENV"] = "dev"
os.environ["TOOL_DEF_CONFIG_PATH"] = "config/tools.yaml"
os.environ["LLM_MODE"] = "mock"

import pytest

from app.services.graph.graph import build_agent_graph, build_invoke_config
from app.services.graph.state import init_state, ERROR_TYPE_BUSINESS


def _get_fallback(tool_result: dict) -> bool | None:
    val = tool_result.get("fallback")
    if val is not None:
        return val
    data = tool_result.get("data")
    if isinstance(data, dict):
        return data.get("fallback")
    return None


@pytest.mark.asyncio
async def test_self_correction_loop_notrigger():
    """正常流程，不会触发校正循环"""
    g = build_agent_graph(interrupt_before_approval=False)
    s = init_state(raw_query="打开记事本", user_id="loop01")
    cfg = build_invoke_config(
        user_id=s["user_id"],
        session_id=s["session_id"],
        trace_id=s["trace_id"],
    )
    res = await g.ainvoke(s, config=cfg)
    assert res["correction_loop_count"] == 0


@pytest.mark.asyncio
async def test_self_correction_loop_max_limit():
    """模拟业务错误，达到最大循环次数后退出到error_fallback"""
    g = build_agent_graph(interrupt_before_approval=False)
    s = init_state(raw_query="打开记事本", user_id="loop02")
    s["max_correction_loop"] = 2
    s["last_error"] = "模拟业务校验失败"
    s["error_type"] = "business"
    cfg = build_invoke_config(
        user_id=s["user_id"],
        session_id=s["session_id"],
        trace_id=s["trace_id"],
    )
    res = await g.ainvoke(s, config=cfg)
    assert res["correction_loop_count"] <= 2
    assert _get_fallback(res["tool_result"]) is True


@pytest.mark.asyncio
async def test_self_correction_security_skip_loop():
    """security错误直接降级，禁止进入自校正循环"""
    g = build_agent_graph(interrupt_before_approval=False)
    s = init_state(raw_query="打开记事本", user_id="loop03")
    s["last_error"] = "安全拦截"
    s["error_type"] = "security"
    cfg = build_invoke_config(
        user_id=s["user_id"],
        session_id=s["session_id"],
        trace_id=s["trace_id"],
    )
    res = await g.ainvoke(s, config=cfg)
    assert res["correction_loop_count"] == 0
    assert _get_fallback(res["tool_result"]) is True


@pytest.mark.asyncio
async def test_correction_metrics_trigger():
    """验证校正触发埋点计数增加：注入业务错误后从post_validate_gate继续"""
    g = build_agent_graph(interrupt_before_approval=False)
    s = init_state(raw_query="打开记事本", user_id="loop-metrics-01")
    cfg = build_invoke_config(
        user_id=s["user_id"],
        session_id=s["session_id"],
        trace_id=s["trace_id"],
    )
    res = await g.ainvoke(s, config=cfg)
    assert res["correction_loop_count"] == 0
    await g.aupdate_state(
        config=cfg,
        values={
            "last_error": "模拟业务校验失败",
            "error_type": ERROR_TYPE_BUSINESS,
            "max_correction_loop": 1,
        },
        as_node="post_validate_gate",
    )
    res2 = await g.ainvoke(None, config=cfg)
    assert res2["correction_loop_count"] >= 1
    assert _get_fallback(res2.get("tool_result", {})) is True


@pytest.mark.asyncio
async def test_correction_exhaust_metrics():
    """校正达到上限，触发exhaust埋点"""
    g = build_agent_graph(interrupt_before_approval=False)
    s = init_state(raw_query="打开记事本", user_id="loop-metrics-02")
    cfg = build_invoke_config(
        user_id=s["user_id"],
        session_id=s["session_id"],
        trace_id=s["trace_id"],
    )
    res = await g.ainvoke(s, config=cfg)
    await g.aupdate_state(
        config=cfg,
        values={
            "last_error": "模拟业务校验失败",
            "error_type": ERROR_TYPE_BUSINESS,
            "max_correction_loop": 0,
        },
        as_node="post_validate_gate",
    )
    res2 = await g.ainvoke(None, config=cfg)
    assert res2["correction_loop_count"] == 0
    assert _get_fallback(res2.get("tool_result", {})) is True


@pytest.mark.asyncio
async def test_correction_fail_generate_pollution_signal():
    """校正异常自动生成pollution信号：直接调用节点，traced_execution抛异常"""
    from app.services.graph.nodes import rewrite_agent_input_node
    from app.services.graph.memory_store import get_governing_store
    from unittest.mock import patch

    s = init_state(raw_query="打开记事本", user_id="loop-sig-01")
    s["last_error"] = "模拟业务校验失败"
    s["error_type"] = ERROR_TYPE_BUSINESS
    s["correction_loop_count"] = 0

    def _raise_on_traced(name, attrs):
        raise RuntimeError("模拟traced_execution异常")

    with patch("app.services.graph.nodes._get_traced_execution", return_value=_raise_on_traced):
        result = await rewrite_agent_input_node(s)

    assert result.get("correction_signal_id"), "应生成pollution信号"
    assert result.get("correction_signal_status") == "open"
    store = get_governing_store()
    sig = store.get_signal(result["correction_signal_id"])
    assert sig is not None
    assert sig["signal_type"] == "pollution"