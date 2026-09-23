"""
H12/A7: tool_call_guard Hook 单元测试。

覆盖：
- assess_tool_risk 四级风险分级
- tool_call_guard_hook 阻断行为（高风险未确认 / 已确认放行 / 不可逆必拒）
- dispatch_hook 阻断时风险等级/原因的透传（H12/A6 反馈充分）
- tool_execute_with_hooks 被阻断时返回 security 错误且不执行底层工具（执行链路接线）
"""

from __future__ import annotations

import asyncio

from app.services.hooks.builtin.tool_call_guard import (
    assess_tool_risk,
    RiskLevel,
    tool_call_guard_hook,
)


class TestAssessToolRisk:
    def test_high_risk_tool(self):
        level, reason = assess_tool_risk("shell_exec", {})
        assert level == RiskLevel.HIGH
        assert reason

    def test_medium_risk_tool(self):
        level, _ = assess_tool_risk("file_write", {})
        assert level == RiskLevel.MEDIUM

    def test_irreversible_dangerous_pattern(self):
        level, reason = assess_tool_risk("system:command", {"cmd": "rm -rf /"})
        assert level == RiskLevel.IRREVERSIBLE
        assert "rm" in reason and "-rf" in reason

    def test_low_risk_read(self):
        level, reason = assess_tool_risk("system:info", {})
        assert level == RiskLevel.LOW
        assert reason == ""


class TestToolCallGuardHook:
    def test_high_risk_blocks_without_confirm(self):
        res = asyncio.run(tool_call_guard_hook({
            "tool_name": "shell_exec",
            "tool_args": {"cmd": "whoami"},
            "user_confirmed": False,
        }))
        assert res["block"] is True
        assert res["risk_level"] == RiskLevel.HIGH
        assert res["needs_confirmation"] is True

    def test_high_risk_allows_with_confirm(self):
        res = asyncio.run(tool_call_guard_hook({
            "tool_name": "shell_exec",
            "tool_args": {"cmd": "whoami"},
            "user_confirmed": True,
        }))
        assert res.get("block") is not True
        assert res["risk_level"] == RiskLevel.HIGH

    def test_irreversible_always_blocks(self):
        res = asyncio.run(tool_call_guard_hook({
            "tool_name": "system:command",
            "tool_args": {"cmd": "rm -rf /"},
        }))
        assert res["block"] is True
        assert res["risk_level"] == RiskLevel.IRREVERSIBLE


class TestDispatchBlockPropagation:
    def test_block_metadata_propagated(self, monkeypatch):
        import app.services.hooks as hooks_mod
        from app.services.hooks import dispatch_hook
        from app.services.hooks.registry import get_hook_registry, HookSpec
        from app.services.hooks.types import HookEvent, HookMode, HookLayer

        async def blocking_hook(ctx):
            return {"block": True, "risk_level": "high", "blocked_reason": "测试阻断"}

        reg = get_hook_registry()
        reg.register(HookSpec(
            name="test_blocker", event=HookEvent.TOOL_CALL, callback=blocking_hook,
            mode=HookMode.MODIFY, layer=HookLayer.TOOL, priority=1,
        ))
        # 跳过真实 init_hooks 的重型插件加载
        monkeypatch.setattr(hooks_mod, "init_hooks", lambda: setattr(hooks_mod, "_initialized", True))
        try:
            result = asyncio.run(dispatch_hook(HookEvent.TOOL_CALL, {"tool_name": "x"}))
            assert result["_hook_blocked"] is True
            assert result["_hook_blocked_by"] == "test_blocker"
            assert result["_hook_blocked_reason"] == "测试阻断"
            assert result["risk_level"] == "high"
        finally:
            reg.unregister("test_blocker")


class TestExecuteWithHooksBlocked:
    def test_blocked_does_not_execute_tool(self, monkeypatch):
        import app.services.hooks as hooks_mod
        from app.services.hooks import graph_integration as gi
        from app.services.hooks.registry import get_hook_registry, HookSpec
        from app.services.hooks.types import HookEvent, HookMode, HookLayer
        from app.services.graph.state import init_state

        async def blocker(ctx):
            return {"block": True, "risk_level": "high", "blocked_reason": "风险过高"}

        reg = get_hook_registry()
        reg.register(HookSpec(
            name="test_blocker2", event=HookEvent.TOOL_CALL, callback=blocker,
            mode=HookMode.MODIFY, layer=HookLayer.TOOL, priority=1,
        ))
        monkeypatch.setattr(hooks_mod, "init_hooks", lambda: setattr(hooks_mod, "_initialized", True))

        async def _boom(state):
            raise AssertionError("被阻断时不应执行底层工具")

        monkeypatch.setattr("app.services.graph.nodes.tool_execute_node", _boom)

        state = init_state("shell")
        state["tool_name"] = "shell_exec"
        state["tool_args"] = {"cmd": "whoami"}

        try:
            out = asyncio.run(gi.tool_execute_with_hooks(state))
            assert out["error_type"] == "security"
            assert out["tool_result"]["ok"] is False
            assert "high" in out["last_error"]
            assert "风险过高" in out["last_error"]
        finally:
            reg.unregister("test_blocker2")


class TestExecutorGuardBypassClosed:
    """P1-2: orchestrator 旁路(execute_tool_calls→_execute_single_tool)也被 tool_call_guard 覆盖，
    不再绕过护栏。此前 llm/orchestrator 直接走 _execute_single_tool，护栏只在 graph 的
    tool_execute_with_hooks 触发，此处验证单点汇聚后旁路同样被阻断。"""

    def test_single_tool_blocks_on_orchestrator_path(self, monkeypatch):
        import app.services.hooks as hooks_mod
        from app.services.hooks.registry import get_hook_registry, HookSpec
        from app.services.hooks.types import HookEvent, HookMode, HookLayer
        from app.services.tools.executor import _execute_single_tool

        async def blocker(ctx):
            return {"block": True, "risk_level": "irreversible", "blocked_reason": "检测到危险指令"}

        reg = get_hook_registry()
        reg.register(HookSpec(
            name="test_orch_blocker", event=HookEvent.TOOL_CALL, callback=blocker,
            mode=HookMode.MODIFY, layer=HookLayer.TOOL, priority=1,
        ))
        monkeypatch.setattr(hooks_mod, "init_hooks", lambda: setattr(hooks_mod, "_initialized", True))
        try:
            out = asyncio.run(_execute_single_tool("system:command", {"cmd": "rm -rf /"}))
            assert out["status"] == "error"
            assert out["data"]["code"] == "BLOCKED_BY_GUARD"
            assert out["data"]["risk_level"] == "irreversible"
            # security/权限类阻断，而非普通 execution
            assert out["error"]["type"] == "permission"
            assert "护栏阻断" in out["summary"]
        finally:
            reg.unregister("test_orch_blocker")

    def test_low_risk_passes_through_orchestrator_path(self, monkeypatch):
        import app.services.hooks as hooks_mod
        from app.services.hooks.registry import get_hook_registry, HookSpec
        from app.services.hooks.types import HookEvent, HookMode, HookLayer
        from app.services.tools.executor import _execute_single_tool

        async def pass_through(ctx):
            return {"risk_level": "low"}

        reg = get_hook_registry()
        reg.register(HookSpec(
            name="test_orch_pass", event=HookEvent.TOOL_CALL, callback=pass_through,
            mode=HookMode.MODIFY, layer=HookLayer.TOOL, priority=1,
        ))
        monkeypatch.setattr(hooks_mod, "init_hooks", lambda: setattr(hooks_mod, "_initialized", True))
        try:
            # 无阻断 → 不返回 BLOCKED_BY_GUARD，继续走工具逻辑（工具不存在会报 not-found，但绝不能被误报阻断）
            out = asyncio.run(_execute_single_tool("no_such_tool_abc", {"query": "os"}))
            assert out["data"].get("code") != "BLOCKED_BY_GUARD"
        finally:
            reg.unregister("test_orch_pass")
