from __future__ import annotations

import logging
from typing import Any

from app.services.hooks.types import HookEvent
from app.services.hooks.registry import get_hook_engine, get_hook_registry, HookSpec
from app.services.hooks.plugins.registry import get_plugin_registry, load_plugin_config

logger = logging.getLogger(__name__)

_initialized = False


def init_hooks() -> None:
    """
    应用启动时调用：注册所有内置 Hook 到 HookRegistry。

    注册顺序 = 加载优先级：
    - 内置 Bundled (这里) → 全局 Global → 项目 Project
    - 同名 Hook 后注册覆盖前注册
    """
    global _initialized
    if _initialized:
        return

    registry = get_hook_registry()
    config = load_plugin_config()

    from app.services.hooks.builtin.rag_web_parallel import create_rag_web_parallel_hook
    registry.register(create_rag_web_parallel_hook())
    logger.info("Hook registered: rag_web_parallel (before_agent_start)")

    from app.services.hooks.builtin.tool_call_guard import create_tool_call_guard_hook
    registry.register(create_tool_call_guard_hook())
    logger.info("Hook registered: tool_call_guard (tool_call)")

    from app.services.hooks.builtin.context_manage import create_context_manage_hook
    registry.register(create_context_manage_hook())
    logger.info("Hook registered: context_manage (context_assemble)")

    from app.services.hooks.builtin.execution_protocol import create_execution_protocol_hook
    registry.register(create_execution_protocol_hook())
    logger.info("Hook registered: execution_protocol (before_agent_start)")

    from app.services.hooks.builtin.checkpoint import create_checkpoint_hook
    registry.register(create_checkpoint_hook())
    logger.info("Hook registered: checkpoint (turn_end)")

    _initialized = True

    avail = get_plugin_registry().list_available()
    for cat, items in avail.items():
        logger.info(f"Plugin category [{cat}]: {items}")

    logger.info(f"HookEngine initialized: {len(registry._hooks)} hooks registered")


async def dispatch_hook(event: HookEvent, context: dict[str, Any]) -> dict[str, Any]:
    """
    统一 Hook 分发入口。

    所有 LangGraph 节点通过此函数触发 Hook 事件，
    而不是直接调用 HookEngine。

    返回值：合并了 Hook 修改结果的 context 字典。
    如果 Hook 返回 {block: True}，context 中会包含 _blocked=True。
    """
    if not _initialized:
        init_hooks()

    engine = get_hook_engine()
    result = await engine.dispatch(event, context)

    if result.pop("_blocked", False):
        blocked_by = result.pop("_blocked_by", "unknown")
        logger.warning(f"Hook blocked execution: event={event.value} blocked_by={blocked_by}")
        result["_hook_blocked"] = True
        result["_hook_blocked_by"] = blocked_by
        # H12/A6: 透传阻断原因，供调用方给出可执行反馈
        if result.get("blocked_reason"):
            result["_hook_blocked_reason"] = result["blocked_reason"]

    return result