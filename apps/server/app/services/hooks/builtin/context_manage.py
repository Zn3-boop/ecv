from __future__ import annotations

import logging
from typing import Any

from app.services.hooks.types import HookEvent, HookLayer, HookMode
from app.services.hooks.registry import HookSpec

logger = logging.getLogger(__name__)


class ContextWindowManager:
    """
    A9: 上下文管理策略
    - Last N Observations: 最近N次完整保留, 更早的压缩成占位符
    - 上下文不是越多越好: 只保留近期细节, 久远历史压缩
    - few-shot轨迹演示很重要
    """

    def __init__(
        self,
        max_recent_observations: int = 5,
        max_context_chars: int = 8000,
        placeholder_prefix: str = "[之前动作：",
    ):
        self._max_recent = max_recent_observations
        self._max_chars = max_context_chars
        self._placeholder_prefix = placeholder_prefix

    def compress_messages(
        self,
        messages: list[dict[str, Any]],
        keep_system: bool = True,
        keep_demonstration: bool = True,
    ) -> list[dict[str, Any]]:
        if not messages:
            return messages

        system_msgs: list[dict[str, Any]] = []
        demo_msgs: list[dict[str, Any]] = []
        regular_msgs: list[dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role", "")
            if role == "system" and keep_system:
                system_msgs.append(msg)
            elif msg.get("is_demonstration", False) and keep_demonstration:
                demo_msgs.append(msg)
            else:
                regular_msgs.append(msg)

        if len(regular_msgs) <= self._max_recent:
            result = system_msgs + demo_msgs + regular_msgs
        else:
            older = regular_msgs[:-self._max_recent]
            recent = regular_msgs[-self._max_recent:]

            placeholders = []
            for msg in older:
                summary = self._summarize_message(msg)
                placeholders.append({
                    "role": "system",
                    "content": f"{self._placeholder_prefix}{summary}]",
                })

            result = system_msgs + demo_msgs + placeholders + recent

        result = self._truncate_to_budget(result)
        return result

    def _summarize_message(self, msg: dict[str, Any]) -> str:
        content = msg.get("content", "")
        role = msg.get("role", "unknown")
        tool_name = msg.get("tool_name", "")
        if tool_name:
            return f"调用了工具 {tool_name}"
        if len(content) > 50:
            return f"{role}: {content[:50]}..."
        return f"{role}: {content}"

    def _truncate_to_budget(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        total = sum(len(m.get("content", "")) for m in messages)
        if total <= self._max_chars:
            return messages

        result = []
        remaining_budget = self._max_chars
        for msg in messages:
            content = msg.get("content", "")
            if len(content) <= remaining_budget:
                result.append(msg)
                remaining_budget -= len(content)
            else:
                truncated = dict(msg)
                truncated["content"] = content[:remaining_budget] + "\n[...截断]"
                result.append(truncated)
                break

        return result


async def context_manage_hook(ctx: dict[str, Any]) -> dict[str, Any] | None:
    """
    A9: 上下文管理 Hook
    - 在 context_assemble 事件触发
    - 压缩过长消息列表
    - 保留 system prompt + demonstration + 最近N轮
    """
    messages = ctx.get("messages", [])
    if not messages:
        return None

    max_recent = ctx.get("context_max_recent", 5)
    max_chars = ctx.get("context_max_chars", 8000)

    manager = ContextWindowManager(
        max_recent_observations=max_recent,
        max_context_chars=max_chars,
    )

    compressed = manager.compress_messages(messages)

    original_count = len(messages)
    compressed_count = len(compressed)
    original_chars = sum(len(m.get("content", "")) for m in messages)
    compressed_chars = sum(len(m.get("content", "")) for m in compressed)

    if compressed_count < original_count or compressed_chars < original_chars:
        logger.info(
            f"上下文压缩: {original_count}→{compressed_count}条, "
            f"{original_chars}→{compressed_chars}字符"
        )
        return {"messages": compressed}

    return None


def create_context_manage_hook() -> HookSpec:
    return HookSpec(
        name="context_manage",
        event=HookEvent.CONTEXT_ASSEMBLE,
        callback=context_manage_hook,
        mode=HookMode.MODIFY,
        layer=HookLayer.AGENT,
        priority=50,
    )