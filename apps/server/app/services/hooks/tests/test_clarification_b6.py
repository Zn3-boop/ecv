"""
B6: 意图澄清结构化反问测试。

验证澄清节点输出的是"选项按钮"式结构化 JSON：
- need_clarification / clarification_message / clarification_reason_code
- clarification_options: [{id, label, recommended, impact}, ...]
而不是纯文本。

覆盖:
- _clarification_payload 全字段转换
- clarification_with_hooks 复用已有结构化信息（不丢弃 reason_code/options）
- clarification_with_hooks 新澄清分支产出结构化字段
- clarification_node（纯文本降级）也提供结构化外壳
"""

from __future__ import annotations

import asyncio


class _FakeClarifier:
    """返回固定 ClarificationResult 的假澄清器"""

    def __init__(self, result=None):
        self._result = result

    async def check_clarification(self, intent_result):
        return self._result


def _make_result():
    from app.services.hooks.plugins.intent.clarifier import (
        ClarificationOption,
        ClarificationReason,
        ClarificationResult,
    )

    return ClarificationResult(
        need_clarification=True,
        reason_code=ClarificationReason.AMBIGUOUS_ENTITY,
        question="你说的「苹果」是指什么？",
        options=[
            ClarificationOption(id="opt_0", label="手机品牌", recommended=True, impact="启动/打开 App"),
            ClarificationOption(id="opt_1", label="水果", recommended=False, impact=""),
        ],
    )


class TestClarificationPayload:
    def test_full_structured_fields(self):
        from app.services.hooks.graph_integration import _clarification_payload

        payload = _clarification_payload(_make_result())
        assert payload["needs_clarification"] is True
        assert payload["clarification_message"] == "你说的「苹果」是指什么？"
        assert payload["clarification_reason_code"] == "AMBIGUOUS_ENTITY"
        assert payload["clarification_options"] == [
            {"id": "opt_0", "label": "手机品牌", "recommended": True, "impact": "启动/打开 App"},
            {"id": "opt_1", "label": "水果", "recommended": False, "impact": ""},
        ]


class TestClarificationWithHooks:
    def test_reuses_structured_info(self, monkeypatch):
        from app.services.hooks import graph_integration as gi

        monkeypatch.setattr(gi, "init_hooks", lambda: None)

        state = {
            "raw_query": "帮我打开苹果",
            "clarification_message": "你说的「苹果」是指什么？",
            "clarification_reason_code": "AMBIGUOUS_ENTITY",
            "clarification_options": [{"id": "opt_0", "label": "手机品牌", "recommended": True, "impact": "启动App"}],
        }
        out = asyncio.run(gi.clarification_with_hooks(state))
        assert out["needs_clarification"] is True
        assert out["clarification_reason_code"] == "AMBIGUOUS_ENTITY"
        assert out["clarification_options"][0]["recommended"] is True
        assert out["clarification_options"][0]["impact"] == "启动App"

    def test_fresh_branch_produces_structured(self, monkeypatch):
        import app.services.hooks.plugins.registry as preg
        from app.services.hooks import graph_integration as gi

        monkeypatch.setattr(gi, "init_hooks", lambda: None)
        monkeypatch.setattr(preg, "load_plugin_config", lambda: {"clarifier": {"type": "rule"}})
        monkeypatch.setattr(preg, "get_plugin_registry", lambda: _FakeReg(_FakeClarifier(_make_result())))

        state = {"raw_query": "帮我打开苹果"}
        out = asyncio.run(gi.clarification_with_hooks(state))
        assert out["needs_clarification"] is True
        assert out["clarification_reason_code"] == "AMBIGUOUS_ENTITY"
        assert len(out["clarification_options"]) == 2
        assert out["clarification_options"][0]["recommended"] is True

    def test_no_clarification_when_not_needed(self, monkeypatch):
        import app.services.hooks.plugins.registry as preg
        from app.services.hooks import graph_integration as gi

        monkeypatch.setattr(gi, "init_hooks", lambda: None)
        monkeypatch.setattr(preg, "load_plugin_config", lambda: {"clarifier": {"type": "rule"}})

        class _NoClarify(_FakeClarifier):
            def __init__(self):
                from app.services.hooks.plugins.intent.clarifier import ClarificationResult

                super().__init__(ClarificationResult(need_clarification=False))

        monkeypatch.setattr(preg, "get_plugin_registry", lambda: _FakeReg(_NoClarify()))

        state = {"raw_query": "打开记事本"}
        out = asyncio.run(gi.clarification_with_hooks(state))
        assert out["needs_clarification"] is False


class TestClarificationNodePlain:
    def test_emits_structured_envelope(self):
        from app.services.graph.nodes import clarification_node
        from app.services.graph.state import init_state

        state = init_state("帮我打开苹果")
        out = asyncio.run(clarification_node(state))
        assert out["needs_clarification"] is True
        assert out["clarification_reason_code"] == "UNABLE_TO_PARSE"
        assert out["clarification_options"] == []
        assert out["clarification_message"]


class _FakeReg:
    def __init__(self, clarifier):
        self._clarifier = clarifier

    def get_clarifier(self, name):
        return self._clarifier