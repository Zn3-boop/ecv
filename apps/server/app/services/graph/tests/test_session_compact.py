"""
M6: 长会话瘦身（双层摘要）测试。

验证:
- session_compact 双层压缩：远期→memory_summary(far层)，近期完整保留(near层)
- 短会话不触发压缩
- 压缩触发后 far 层摘要作为 C 级系统实证写回 memory store（不只在 state 字段）
- turn_end_with_hooks（已接线终端节点）在长会话时产出双层摘要字段
"""

from __future__ import annotations

import asyncio

import pytest


def _build_long_history(turn_count: int = 30, chars_per_turn: int = 200) -> list[dict]:
    history = []
    for i in range(turn_count):
        role = "user" if i % 2 == 0 else "assistant"
        content = f"第{i+1}轮对话：" + "这是一段测试内容。" * (chars_per_turn // 10)
        history.append({"role": role, "content": content, "metadata": {}})
    return history


def _skip_init_hooks(monkeypatch):
    import app.services.hooks as hooks_mod

    monkeypatch.setattr(hooks_mod, "init_hooks", lambda: setattr(hooks_mod, "_initialized", True))
    hooks_mod._initialized = True


class TestSessionCompactShortHistory:
    def test_short_history_no_compaction(self, monkeypatch):
        _skip_init_hooks(monkeypatch)
        from app.services.hooks.graph_integration import session_compact

        turns = _build_long_history(4)
        out = asyncio.run(session_compact({"turn_history": turns}))
        assert out == {}


class TestSessionCompactLongHistory:
    def test_two_layer_summary(self, monkeypatch):
        _skip_init_hooks(monkeypatch)
        from app.services.hooks.graph_integration import session_compact

        turns = _build_long_history(30, 200)
        out = asyncio.run(session_compact({"turn_history": turns, "user_id": "u1"}))
        assert out.get("session_compacted") is True
        assert out["memory_summary"], "far层摘要不应为空"
        assert isinstance(out["memory_recent_turns"], list)
        assert len(out["memory_recent_turns"]) > 0, "near层近期轮次应保留"
        assert out["memory_token_reduction"] >= 0

    def test_far_summary_persisted_to_store(self, monkeypatch):
        _skip_init_hooks(monkeypatch)
        from app.services.hooks.graph_integration import session_compact
        from app.services.graph.memory_store import get_memory_store

        store = get_memory_store()
        turns = _build_long_history(30, 200)
        out = asyncio.run(session_compact({"turn_history": turns, "user_id": "u1", "session_id": "s1"}))
        assert out["session_compacted"] is True
        keys = store.list_keys("u1")
        assert any("session_compact_C_" in k for k in keys), f"应落盘 session_compact_C_* 证据, 实际 keys={keys}"

    def test_reduction_below_original(self, monkeypatch):
        _skip_init_hooks(monkeypatch)
        from app.services.hooks.graph_integration import session_compact
        from app.services.context_manager import ContextManager

        cm = ContextManager()
        turns = _build_long_history(30, 200)
        raw = sum(cm.estimate_tokens(str(t["content"])) for t in turns)
        out = asyncio.run(session_compact({"turn_history": turns}))
        assert out["session_compacted"] is True
        comp = sum(cm.estimate_tokens(str(c["content"])) for c in out["memory_recent_turns"]) + cm.estimate_tokens(
            out["memory_summary"]
        )
        assert comp < raw


class TestStateTurnHistory:
    def test_from_messages(self):
        from app.services.hooks.graph_integration import _state_turn_history

        state = {"messages": [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "在的"}]}
        turns = _state_turn_history(state)
        assert turns[0]["role"] == "user"
        assert turns[1]["role"] == "assistant"

    def test_from_history_log(self):
        from app.services.hooks.graph_integration import _state_turn_history

        state = {"history_log": ["log-a", "log-b"]}
        turns = _state_turn_history(state)
        assert len(turns) == 2
        assert turns[0]["role"] == "user"
        assert turns[1]["role"] == "assistant"


class TestTurnEndWiresSessionCompact:
    def test_long_session_produces_compact_fields(self, monkeypatch):
        _skip_init_hooks(monkeypatch)
        from app.services.hooks.graph_integration import turn_end_with_hooks
        from app.services.graph.state import init_state

        state = init_state("长会话任务", user_id="u1", session_id="s1")
        state["messages"] = _build_long_history(30, 200)

        out = asyncio.run(turn_end_with_hooks(state))
        assert out.get("session_compacted") is True
        assert out.get("memory_summary")
        assert isinstance(out.get("memory_recent_turns"), list)

    def test_short_session_no_compact(self, monkeypatch):
        _skip_init_hooks(monkeypatch)
        from app.services.hooks.graph_integration import turn_end_with_hooks
        from app.services.graph.state import init_state

        state = init_state("短会话", user_id="u1", session_id="s1")
        state["messages"] = _build_long_history(3, 50)

        out = asyncio.run(turn_end_with_hooks(state))
        assert out.get("session_compacted") is not True