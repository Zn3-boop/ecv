import os

os.environ["GRAPH_ENV"] = "dev"
os.environ["TOOL_DEF_CONFIG_PATH"] = "config/tools.yaml"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

pytest_plugins = ["pytest_asyncio"]

from app.api.desktop_graph_api import app
from app.services.graph.graph import build_agent_graph, build_invoke_config
from app.services.graph.state import init_state


@pytest.mark.asyncio
async def test_graph_smoke_launch():
    graph = build_agent_graph()
    inp = init_state(raw_query="打开记事本", user_id="test01")
    cfg = build_invoke_config(
        user_id=inp["user_id"],
        session_id=inp["session_id"],
        trace_id=inp["trace_id"],
    )
    res = await graph.ainvoke(inp, config=cfg)
    assert res["raw_query"] == "打开记事本"
    assert res["standalone_query"] != ""
    assert len(res["retrieval_queries"]) > 0


@pytest.mark.asyncio
async def test_graph_fastbrain_reject():
    graph = build_agent_graph()
    inp = init_state(raw_query="   ", user_id="test02")
    cfg = build_invoke_config(
        user_id=inp["user_id"],
        session_id=inp["session_id"],
        trace_id=inp["trace_id"],
    )
    res = await graph.ainvoke(inp, config=cfg)
    assert res.get("fast_brain_decision") == "reject"
    tr = res.get("tool_result", {})
    fallback = tr.get("fallback")
    if fallback is None and isinstance(tr.get("data"), dict):
        fallback = tr["data"].get("fallback")
    assert fallback is True


@pytest.mark.asyncio
async def test_api_invoke():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {"raw_query": "打开记事本", "user_id": "api-01"}
        resp = await ac.post("/desktop/graph/invoke", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


@pytest.mark.asyncio
async def test_api_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_metrics():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/metrics")
        assert resp.status_code == 200