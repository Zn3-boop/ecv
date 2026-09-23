from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.services.hooks.types import HookCallback, HookEvent, HookLayer, HookMode

logger = logging.getLogger(__name__)


class HookSpec:
    __slots__ = ("name", "event", "callback", "mode", "layer", "priority", "enabled")

    def __init__(
        self,
        name: str,
        event: HookEvent,
        callback: HookCallback,
        mode: HookMode = HookMode.OBSERVE,
        layer: HookLayer = HookLayer.AGENT,
        priority: int = 100,
        enabled: bool = True,
    ):
        self.name = name
        self.event = event
        self.callback = callback
        self.mode = mode
        self.layer = layer
        self.priority = priority
        self.enabled = enabled


class HookRegistry:
    """
    Hook注册中心:
    - 修改性Hook(modify): 串行+优先级, 保证状态可预测
    - 观测性Hook(observe): 并行执行+错误隔离, 单个插件崩不影响主流程
    - 加载优先级: builtin → global → project, 同名Hook覆盖
    """

    def __init__(self):
        self._hooks: dict[HookEvent, list[HookSpec]] = {}
        self._name_index: dict[str, HookSpec] = {}

    def register(self, spec: HookSpec):
        if spec.name in self._name_index:
            self.unregister(spec.name)
        if spec.event not in self._hooks:
            self._hooks[spec.event] = []
        self._hooks[spec.event].append(spec)
        self._hooks[spec.event].sort(key=lambda h: h.priority)
        self._name_index[spec.name] = spec
        logger.debug(f"Hook registered: {spec.name} event={spec.event.value} mode={spec.mode.value} pri={spec.priority}")

    def unregister(self, name: str):
        if name in self._name_index:
            spec = self._name_index.pop(name)
            if spec.event in self._hooks:
                self._hooks[spec.event] = [h for h in self._hooks[spec.event] if h.name != name]

    def get_hooks(self, event: HookEvent) -> list[HookSpec]:
        return [h for h in self._hooks.get(event, []) if h.enabled]

    def get_modify_hooks(self, event: HookEvent) -> list[HookSpec]:
        return [h for h in self.get_hooks(event) if h.mode == HookMode.MODIFY]

    def get_observe_hooks(self, event: HookEvent) -> list[HookSpec]:
        return [h for h in self.get_hooks(event) if h.mode == HookMode.OBSERVE]

    def list_all(self) -> list[dict[str, Any]]:
        result = []
        for event, specs in self._hooks.items():
            for spec in specs:
                result.append({
                    "name": spec.name,
                    "event": spec.event.value,
                    "mode": spec.mode.value,
                    "layer": spec.layer.name,
                    "priority": spec.priority,
                    "enabled": spec.enabled,
                })
        return result

    def enable(self, name: str):
        if name in self._name_index:
            self._name_index[name].enabled = True

    def disable(self, name: str):
        if name in self._name_index:
            self._name_index[name].enabled = False


class HookEngine:
    """
    Hook执行引擎:
    - 修改性Hook: 串行执行, 前一个的输出是后一个的输入
    - 观测性Hook: 并行执行, 错误隔离
    - 修改性Hook可返回 {block: True} 阻断后续执行
    """

    def __init__(self, registry: HookRegistry):
        self.registry = registry

    async def dispatch(self, event: HookEvent, context: dict[str, Any]) -> dict[str, Any]:
        ctx = dict(context)
        ctx["_event"] = event.value

        modify_hooks = self.registry.get_modify_hooks(event)
        for hook in modify_hooks:
            try:
                result = await hook.callback(ctx)
                if result is not None:
                    if result.get("block"):
                        ctx["_blocked"] = True
                        ctx["_blocked_by"] = hook.name
                        # H12/A6: 阻断时透传风险等级与原因，供下游给出充分反馈
                        if result.get("risk_level"):
                            ctx["risk_level"] = result["risk_level"]
                        if result.get("blocked_reason"):
                            ctx["blocked_reason"] = result["blocked_reason"]
                        if result.get("needs_confirmation"):
                            ctx["needs_confirmation"] = result["needs_confirmation"]
                        logger.info(f"Hook {hook.name} blocked execution for event {event.value}")
                        break
                    ctx.update(result)
            except Exception as e:
                logger.error(f"Modify hook {hook.name} failed: {e}")
                if event in (HookEvent.TOOL_CALL, HookEvent.BEFORE_TOOL_EXEC):
                    ctx["_hook_error"] = str(e)
                    break

        observe_hooks = self.registry.get_observe_hooks(event)
        if observe_hooks:
            tasks = []
            for hook in observe_hooks:
                tasks.append(self._safe_observe(hook, dict(ctx)))
            await asyncio.gather(*tasks, return_exceptions=True)

        ctx.pop("_event", None)
        return ctx

    async def _safe_observe(self, hook: HookSpec, ctx: dict[str, Any]):
        try:
            await hook.callback(ctx)
        except Exception as e:
            logger.warning(f"Observe hook {hook.name} failed (isolated): {e}")


_registry: HookRegistry | None = None
_engine: HookEngine | None = None


def get_hook_registry() -> HookRegistry:
    global _registry
    if _registry is None:
        _registry = HookRegistry()
    return _registry


def get_hook_engine() -> HookEngine:
    global _engine
    if _engine is None:
        _engine = HookEngine(get_hook_registry())
    return _engine