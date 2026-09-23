"""
FastAPI 接口层 pytest 单元测试。
使用 httpx AsyncClient + pytest-asyncio 测试 desktop_graph router。

依赖：pip install pytest pytest-asyncio httpx
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("GRAPH_ENV", "dev")
os.environ.setdefault("LLM_MODE", "mock")

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.graph.state import init_state


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_test_app():
    from fastapi import FastAPI
    from app.api.desktop_graph import router

    app = FastAPI()
    app.include_router(router)

    try:
        from app.services.graph.graph import build_agent_graph, get_checkpointer
        cp = get_checkpointer()
        app.state.graph = build_agent_graph(checkpointer=cp)
    except Exception:
        app.state.graph = None

    return app


@pytest.mark.anyio
async def test_governor_full_scan_api():
    app = _make_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {"user_id": "test_user_001"}
        resp = await ac.post("/desktop/graph/governor/full-scan", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "conflict" in data
        assert "expired" in data
        assert "signal_generated" in data


@pytest.mark.anyio
async def test_list_signals_api():
    app = _make_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/desktop/graph/governor/signals", params={"user_id": "test_user_001"})
        assert resp.status_code == 200
        data = resp.json()
        assert "signals" in data


@pytest.mark.anyio
async def test_patch_signal_not_found():
    app = _make_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.patch(
            "/desktop/graph/governor/signals/sig_nonexistent",
            json={"status": "processing", "owner": "test", "comment": "test"},
        )
        assert resp.status_code == 404


@pytest.mark.anyio
async def test_tool_search_api():
    app = _make_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/desktop/graph/tool-search/query",
            json={"query": "registry", "top_k": 3},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "hit_list" in data
        assert "loaded_schema" in data


@pytest.mark.anyio
async def test_approval_invalid_status():
    app = _make_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/desktop/graph/approval",
            json={"thread_id": "t1", "approval_status": "invalid"},
        )
        assert resp.status_code == 400


@pytest.mark.anyio
async def test_graph_invoke_no_graph():
    from fastapi import FastAPI
    from app.api.desktop_graph import router

    app = FastAPI()
    app.include_router(router)
    app.state.graph = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/desktop/graph/invoke",
            json={"raw_query": "打开记事本", "user_id": "test_user"},
        )
        assert resp.status_code == 503