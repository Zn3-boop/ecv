from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.utils.response_cleaner import cleaner


class CompressionStrategy(str, Enum):
    NONE = "none"
    SLIDING_WINDOW = "sliding"
    SUMMARY = "summary"
    HYBRID = "hybrid"


@dataclass
class ConversationTurn:
    role: str
    content: str
    timestamp: str | float | int | None = None
    metadata: dict[str, Any] | None = None
    is_meta: bool = False
    is_fallback: bool = False


class ContextManager:
    DEFAULT_MAX_TURNS = 6
    DEFAULT_MAX_TOKENS = 6000
    DEFAULT_MAX_CONTEXT_CHARS = 8000
    DEFAULT_MAX_SINGLE_MESSAGE_CHARS = 1000
    SUMMARY_THRESHOLD = 20
    MAX_SUMMARY_CHARS = 300

    def __init__(
        self,
        max_turns: int = DEFAULT_MAX_TURNS,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
        max_single_message_chars: int = DEFAULT_MAX_SINGLE_MESSAGE_CHARS,
        strategy: CompressionStrategy = CompressionStrategy.HYBRID,
    ) -> None:
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.max_context_chars = max_context_chars
        self.max_single_message_chars = max_single_message_chars
        self.strategy = strategy
        self._history_summary: str | None = None
        self._raw_history: list[ConversationTurn] = []

    def process(
        self,
        history: list[dict[str, Any]],
        current_message: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        turns = self._normalize_history(history)
        self._raw_history = turns.copy()

        if self.strategy == CompressionStrategy.NONE:
            return [self._turn_to_dict(turn) for turn in turns], None

        if self.strategy == CompressionStrategy.SLIDING_WINDOW:
            compressed, summary = self._apply_sliding_window(turns), None
        elif self.strategy == CompressionStrategy.SUMMARY:
            compressed, summary = self._apply_summary_compression(turns, current_message)
        else:
            compressed, summary = self._apply_hybrid_strategy(turns, current_message)

        compressed = self._finalize_context_items(compressed, has_summary=bool(summary))
        return compressed, summary

    def clean_content(self, raw_content: str) -> str:
        cleaned = cleaner.clean(str(raw_content or "").strip())
        if not cleaned:
            return ""

        cleaned = re.sub(r"原问题：角色设定：.*?当前用户消息：", "", cleaned, flags=re.DOTALL)
        patterns_to_remove = [
            r"初稿：.*?(?=审核意见：|$)",
            r"审核意见：.*?(?=系统监控摘要：|$)",
            r"系统监控摘要：.*?(?=语音上下文摘要：|$)",
            r"语音上下文摘要：.*?(?=当前仍走本地降级|$)",
            r"当前仍走本地降级草稿逻辑.*?$",
            r"已根据审核意见完成重写.*?$",
            r"建议：优先查看高占用进程.*$",
            r"LLM provider request failed:.*$",
        ]
        for pattern in patterns_to_remove:
            cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL | re.MULTILINE)

        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned

    def _normalize_history(self, history: list[dict[str, Any]]) -> list[ConversationTurn]:
        normalized: list[ConversationTurn] = []
        for message in history:
            role = str(message.get("role", "")).strip()
            if role not in {"user", "assistant", "system"}:
                continue

            metadata = message.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}

            is_meta = bool(message.get("is_meta")) or bool(metadata.get("is_meta"))
            is_fallback = bool(message.get("is_fallback")) or bool(metadata.get("had_fallback")) or bool(metadata.get("is_fallback"))
            if is_meta or is_fallback:
                continue

            content = self.clean_content(str(message.get("content", "")).strip())
            if not content:
                continue

            if len(content) > self.max_single_message_chars:
                content = content[: self.max_single_message_chars].rstrip() + "..."

            normalized.append(
                ConversationTurn(
                    role=role,
                    content=content,
                    timestamp=message.get("created_at") or message.get("timestamp"),
                    metadata=metadata,
                    is_meta=is_meta,
                    is_fallback=is_fallback,
                )
            )
        return normalized

    def _extract_recent_turns(self, turns: list[ConversationTurn], max_turns: int | None = None) -> list[ConversationTurn]:
        limit = max_turns or self.max_turns
        collected_turns: list[list[ConversationTurn]] = []
        current_turn: list[ConversationTurn] = []

        for turn in reversed(turns):
            current_turn.insert(0, turn)
            if turn.role == "user":
                collected_turns.insert(0, current_turn)
                current_turn = []
                if len(collected_turns) >= limit:
                    break

        flattened: list[ConversationTurn] = []
        for item in collected_turns:
            flattened.extend(item)
        return flattened

    def _apply_sliding_window(self, turns: list[ConversationTurn]) -> list[dict[str, Any]]:
        limited_turns = self._extract_recent_turns(turns, self.max_turns)
        return [self._turn_to_dict(turn) for turn in self._trim_to_token_budget(limited_turns)]

    def _apply_summary_compression(
        self,
        turns: list[ConversationTurn],
        current_message: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if len(turns) <= self.SUMMARY_THRESHOLD and self._estimate_turns_tokens(turns, current_message) <= self.max_tokens:
            return [self._turn_to_dict(turn) for turn in turns], None

        recent_turns = self._extract_recent_turns(turns, self.max_turns)
        old_turns = turns[: max(0, len(turns) - len(recent_turns))]
        summary = self._generate_history_summary(old_turns)
        self._history_summary = summary

        context: list[dict[str, Any]] = []
        if summary:
            context.append(
                {
                    "role": "system",
                    "content": f"历史对话摘要：{summary}",
                    "metadata": {"compressed": True, "source": "context_manager"},
                }
            )

        combined_turns = self._trim_to_token_budget(recent_turns, reserved_text=summary or "", current_message=current_message)
        combined_turns = combined_turns[-min(len(combined_turns), self.max_turns * 2 - 1) :]
        context.extend(self._turn_to_dict(turn) for turn in combined_turns)
        return context, summary

    def _apply_hybrid_strategy(
        self,
        turns: list[ConversationTurn],
        current_message: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if len(turns) <= self.max_turns and self._estimate_turns_tokens(turns, current_message) <= self.max_tokens:
            return [self._turn_to_dict(turn) for turn in turns], None
        return self._apply_summary_compression(turns, current_message)

    def _trim_to_token_budget(
        self,
        turns: list[ConversationTurn],
        reserved_text: str = "",
        current_message: str | None = None,
    ) -> list[ConversationTurn]:
        reserved_tokens = self.estimate_tokens(reserved_text) + self.estimate_tokens(current_message or "")
        budget = max(self.max_tokens - reserved_tokens, 0)

        selected: list[ConversationTurn] = []
        running_tokens = 0
        for turn in reversed(turns):
            turn_tokens = self.estimate_tokens(turn.content)
            if selected and running_tokens + turn_tokens > budget:
                break
            if not selected and turn_tokens > budget and budget > 0:
                selected.append(turn)
                break
            if budget == 0:
                break
            selected.append(turn)
            running_tokens += turn_tokens
        return list(reversed(selected))

    def _generate_history_summary(self, old_turns: list[ConversationTurn]) -> str | None:
        if not old_turns:
            return None

        normalized_chunks: list[str] = []
        for turn in old_turns:
            role_name = "用户" if turn.role == "user" else "助手"
            snippet = cleaner.clean(turn.content).replace("\n", " ").strip()
            snippet = re.sub(r"\s+", " ", snippet)
            if not snippet:
                continue
            normalized_chunks.append(f"{role_name}：{snippet[:120]}")

        if not normalized_chunks:
            return None

        summary = "；".join(normalized_chunks)
        summary = re.sub(r"\s+", " ", summary).strip("；， ")
        if len(summary) > self.MAX_SUMMARY_CHARS:
            summary = summary[: self.MAX_SUMMARY_CHARS - 1].rstrip() + "…"
        return summary or None

    def estimate_tokens(self, text: str) -> int:
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        english_words = len(re.findall(r"[a-zA-Z]+", text))
        other_chars = max(len(text) - chinese_chars - english_words, 0)
        return int(chinese_chars * 1.5 + english_words / 4 + other_chars * 0.25)

    def _estimate_turns_tokens(self, turns: list[ConversationTurn], current_message: str | None = None) -> int:
        total = sum(self.estimate_tokens(turn.content) for turn in turns)
        if current_message:
            total += self.estimate_tokens(current_message)
        return total

    def _finalize_context_items(self, items: list[dict[str, Any]], *, has_summary: bool) -> list[dict[str, Any]]:
        max_items = self.max_turns * 2 - 1
        if has_summary and items:
            if len(items) > max_items:
                return [items[0], *items[-(max_items - 1) :]]
            return items
        return items[-max_items:]

    def _format_history(self, turns: list[ConversationTurn]) -> str:
        parts = ["最近对话记忆："]
        for turn in turns:
            prefix = "用户：" if turn.role == "user" else "助手：" if turn.role == "assistant" else "系统："
            parts.append(f"{prefix}{turn.content}")
        return "\n".join(parts)

    def _truncate_from_head(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return "...(历史截断)...\n" + text[-max_chars:]

    def _fit_turns_to_char_budget(self, turns: list[ConversationTurn], available_chars: int) -> tuple[list[ConversationTurn], bool]:
        if available_chars <= 0:
            return [], bool(turns)

        selected: list[ConversationTurn] = []
        total_chars = 0
        was_truncated = False

        for turn in reversed(turns):
            prefix = "用户：" if turn.role == "user" else "助手：" if turn.role == "assistant" else "系统："
            remaining = available_chars - total_chars - len(prefix) - 1
            if remaining <= 0:
                was_truncated = True
                break

            content = turn.content
            per_message_cap = remaining
            if turn.role == "assistant":
                per_message_cap = min(per_message_cap, max(16, available_chars // 5))
                if len(content) > per_message_cap and selected:
                    was_truncated = True
                    continue
            elif turn.role == "user":
                per_message_cap = min(per_message_cap, max(18, available_chars // 2))

            if len(content) > per_message_cap:
                if per_message_cap < 12:
                    was_truncated = True
                    continue
                content = content[:per_message_cap].rstrip() + "..."
                was_truncated = True

            selected.append(
                ConversationTurn(
                    role=turn.role,
                    content=content,
                    timestamp=turn.timestamp,
                    metadata=turn.metadata,
                    is_meta=turn.is_meta,
                    is_fallback=turn.is_fallback,
                )
            )
            total_chars += len(prefix) + len(content) + 1

        return list(reversed(selected)), was_truncated or len(selected) < len(turns)

    def build_prompt(self, history: list[dict[str, Any]], current_user_msg: str, system_prompt: str) -> str:
        normalized_turns = self._normalize_history(history)
        recent_turns = self._extract_recent_turns(normalized_turns, self.max_turns)

        current_clean = self.clean_content(current_user_msg)
        available_chars = self.max_context_chars - len(system_prompt) - len(current_clean) - 200
        if available_chars < 0:
            available_chars = 0

        fitted_turns, was_truncated = self._fit_turns_to_char_budget(recent_turns, available_chars)
        history_text = self._format_history(fitted_turns) if fitted_turns else "最近对话记忆：无"
        if was_truncated and history_text != "最近对话记忆：无":
            history_text = "最近对话记忆：\n...(历史截断)...\n" + "\n".join(history_text.splitlines()[1:])

        return f"{system_prompt}\n\n{history_text}\n\n当前用户消息：{current_clean}\n"

    def get_context_length(self, history: list[dict[str, Any]]) -> int:
        normalized_turns = self._normalize_history(history)
        return self._estimate_turns_tokens(normalized_turns)

    def reset(self) -> None:
        self._history_summary = None
        self._raw_history = []

    @staticmethod
    def _turn_to_dict(turn: ConversationTurn) -> dict[str, Any]:
        return {
            "role": turn.role,
            "content": turn.content,
            "timestamp": turn.timestamp,
            "metadata": turn.metadata or {},
            "is_meta": turn.is_meta,
            "is_fallback": turn.is_fallback,
        }


context_manager = ContextManager(
    max_turns=6,
    max_tokens=6000,
    max_context_chars=8000,
    max_single_message_chars=1000,
    strategy=CompressionStrategy.HYBRID,
)
