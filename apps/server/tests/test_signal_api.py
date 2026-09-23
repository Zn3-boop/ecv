import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.desktop_graph_api import app
from app.services.graph.memory_store import (
    SIGNAL_STATUS_OPEN,
    SIGNAL_STATUS_PROCESSING,
    SIGNAL_STATUS_RESOLVED,
    get_governing_store,
)

API_PREFIX = "/desktop/governor/signals"


def _unique_user_id() -> str:
    return f"test_user_{uuid.uuid4().hex[:8]}"


def _unique_sig_id_not_exists() -> str:
    return f"sig_ghost_{uuid.uuid4().hex[:12]}"


@pytest.fixture()
def fresh_store():
    store = get_governing_store()
    snapshot = dict(store._signals)
    yield store
    store._signals = snapshot
    store._dump_signals()


@pytest.fixture()
async def client(fresh_store):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_signal_ack_resolve_flow(client, fresh_store):
    """信号完整生命周期 open -> ack(processing) -> resolve(resolved)"""
    user_id = _unique_user_id()
    sig_id = fresh_store.generate_correction_signal(
        user_id=user_id,
        signal_type="pollution",
        related_keys=[],
        detail="单元测试信号",
    )

    resp_ack = await client.post(
        f"{API_PREFIX}/{sig_id}/ack",
        json={"owner": "tester", "comment": "认领处理"},
    )
    assert resp_ack.status_code == 200
    assert resp_ack.json()["status"] == SIGNAL_STATUS_PROCESSING

    resp_resolve = await client.post(
        f"{API_PREFIX}/{sig_id}/resolve",
        json={"owner": "tester", "comment": "已修复"},
    )
    assert resp_resolve.status_code == 200
    assert resp_resolve.json()["status"] == SIGNAL_STATUS_RESOLVED

    resp_bad = await client.post(
        f"{API_PREFIX}/{sig_id}/ack",
        json={"owner": "tester"},
    )
    assert resp_bad.status_code == 400


@pytest.mark.asyncio
async def test_list_signals_filter(client, fresh_store):
    """信号列表过滤参数 signal_type + status"""
    user_id = _unique_user_id()
    fresh_store.generate_correction_signal(
        user_id=user_id,
        signal_type="pollution",
        related_keys=[],
        detail="过滤测试信号",
    )

    resp = await client.get(
        API_PREFIX,
        params={"signal_type": "pollution", "status": SIGNAL_STATUS_OPEN},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "signals" in data
    for s in data["signals"]:
        assert s["signal_type"] == "pollution"
        assert s["status"] == SIGNAL_STATUS_OPEN


@pytest.mark.asyncio
async def test_list_signals_by_user_id(client, fresh_store):
    """按 user_id 过滤信号列表"""
    user_a = _unique_user_id()
    user_b = _unique_user_id()
    fresh_store.generate_correction_signal(
        user_id=user_a, signal_type="pollution", related_keys=[], detail="A的信号",
    )
    fresh_store.generate_correction_signal(
        user_id=user_b, signal_type="conflict", related_keys=[], detail="B的信号",
    )

    resp = await client.get(API_PREFIX, params={"user_id": user_a})
    assert resp.status_code == 200
    signals = resp.json()["signals"]
    assert all(s["user_id"] == user_a for s in signals)


@pytest.mark.asyncio
async def test_list_signals_empty(client, fresh_store):
    """空信号列表场景"""
    ghost_user = _unique_user_id()
    resp = await client.get(API_PREFIX, params={"user_id": ghost_user})
    assert resp.status_code == 200
    assert resp.json()["signals"] == []


@pytest.mark.asyncio
async def test_signal_resolve_from_open(client, fresh_store):
    """信号直接从 open -> resolve（跳过 ack）"""
    user_id = _unique_user_id()
    sig_id = fresh_store.generate_correction_signal(
        user_id=user_id,
        signal_type="conflict",
        related_keys=["test_key"],
        detail="直接resolve测试",
    )

    resp = await client.post(
        f"{API_PREFIX}/{sig_id}/resolve",
        json={"owner": "admin", "comment": "直接关闭"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == SIGNAL_STATUS_RESOLVED


@pytest.mark.asyncio
async def test_signal_ack_not_found(client, fresh_store):
    """ack 不存在的信号返回 400"""
    ghost_id = _unique_sig_id_not_exists()
    resp = await client.post(
        f"{API_PREFIX}/{ghost_id}/ack",
        json={"owner": "tester"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_signal_resolve_not_found(client, fresh_store):
    """resolve 不存在的信号返回 400"""
    ghost_id = _unique_sig_id_not_exists()
    resp = await client.post(
        f"{API_PREFIX}/{ghost_id}/resolve",
        json={"owner": "tester"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_double_ack_rejected(client, fresh_store):
    """对 processing 状态的信号再次 ack 应失败"""
    user_id = _unique_user_id()
    sig_id = fresh_store.generate_correction_signal(
        user_id=user_id, signal_type="pollution", related_keys=[], detail="双ack测试",
    )
    resp1 = await client.post(f"{API_PREFIX}/{sig_id}/ack", json={"owner": "tester"})
    assert resp1.status_code == 200

    resp2 = await client.post(f"{API_PREFIX}/{sig_id}/ack", json={"owner": "tester"})
    assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_resolve_already_resolved_rejected(client, fresh_store):
    """对已 resolved 的信号再次 resolve 应失败"""
    user_id = _unique_user_id()
    sig_id = fresh_store.generate_correction_signal(
        user_id=user_id, signal_type="pollution", related_keys=[], detail="重复resolve测试",
    )
    resp1 = await client.post(f"{API_PREFIX}/{sig_id}/resolve", json={"owner": "admin"})
    assert resp1.status_code == 200

    resp2 = await client.post(f"{API_PREFIX}/{sig_id}/resolve", json={"owner": "admin"})
    assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_patch_signal(client, fresh_store):
    """PATCH 端点更新信号状态"""
    user_id = _unique_user_id()
    sig_id = fresh_store.generate_correction_signal(
        user_id=user_id, signal_type="pollution", related_keys=[], detail="patch测试",
    )

    resp = await client.patch(
        f"{API_PREFIX}/{sig_id}",
        json={"status": SIGNAL_STATUS_PROCESSING, "owner": "tester", "comment": "patch认领"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == SIGNAL_STATUS_PROCESSING


@pytest.mark.asyncio
async def test_patch_signal_not_found(client, fresh_store):
    """PATCH 不存在的信号返回 404"""
    ghost_id = _unique_sig_id_not_exists()
    resp = await client.patch(
        f"{API_PREFIX}/{ghost_id}",
        json={"status": SIGNAL_STATUS_PROCESSING, "owner": "tester"},
    )
    assert resp.status_code == 404