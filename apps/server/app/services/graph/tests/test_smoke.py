"""
pytest smoke测试用例，跑通主链路冒烟
pytest apps/server/app/services/graph/tests/test_smoke.py -v
"""
from __future__ import annotations

import asyncio
import os

os.environ.setdefault("GRAPH_ENV", "dev")

from app.services.graph.graph import build_agent_graph, build_invoke_config
from app.services.graph.state import init_state


async def _test_graph_smoke_launch_notepad():
    graph = build_agent_graph(interrupt_before_approval=False)
    state_in = init_state(raw_query="打开记事本", user_id="test_01")
    cfg = build_invoke_config(
        user_id=state_in["user_id"],
        session_id=state_in["session_id"],
        trace_id=state_in["trace_id"],
    )
    res = await graph.ainvoke(state_in, config=cfg)
    assert res["raw_query"] == "打开记事本"
    assert res.get("standalone_query", "") != ""
    assert len(res.get("retrieval_queries", [])) > 0
    assert "tool_result" in res


def test_graph_smoke_launch_notepad():
    asyncio.run(_test_graph_smoke_launch_notepad())


async def _test_graph_smoke_clarification():
    graph = build_agent_graph(interrupt_before_approval=False)
    state_in = init_state(raw_query="帮我弄一下", user_id="test_02")
    cfg = build_invoke_config(
        user_id=state_in["user_id"],
        session_id=state_in["session_id"],
        trace_id=state_in["trace_id"],
    )
    res = await graph.ainvoke(state_in, config=cfg)
    assert res["raw_query"] == "帮我弄一下"
    assert res.get("needs_clarification") is True


def test_graph_smoke_clarification():
    asyncio.run(_test_graph_smoke_clarification())


async def _test_graph_smoke_fast_brain_reject():
    graph = build_agent_graph(interrupt_before_approval=False)
    state_in = init_state(raw_query="", user_id="test_03")
    cfg = build_invoke_config(
        user_id=state_in["user_id"],
        session_id=state_in["session_id"],
        trace_id=state_in["trace_id"],
    )
    res = await graph.ainvoke(state_in, config=cfg)
    assert res.get("fast_brain_decision") == "reject"
    assert res.get("need_slow_brain") is False


def test_graph_smoke_fast_brain_reject():
    asyncio.run(_test_graph_smoke_fast_brain_reject())