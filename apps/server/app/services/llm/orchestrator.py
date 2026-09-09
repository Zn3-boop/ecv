from __future__ import annotations

import os
from typing import Any

from app.services.llm.generator import generate_with_tools, generate, rewrite
from app.services.llm.reviewer import review
from app.services.tools.executor import execute_tool_calls
from app.utils.response_cleaner import cleaner


def _should_skip_llm_review(message: str, mode: str, voice_context: dict[str, Any] | None) -> bool:
    if os.getenv("LLM_REVIEW_ENABLED", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        return True
    if mode in {"automation", "voice"}:
        return True
    if voice_context and voice_context.get("source"):
        return True
    return len(message.strip()) < 120


# Force reload marker
async def run_agent_workflow(
    message: str,
    mode: str = "default",
    *,
    system_context: dict[str, Any] | None = None,
    voice_context: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    conversation_id: int | None = None,
) -> dict[str, Any]:
    """
    统一 Agent 工作流：
    1. LLM 决定是否需要工具 → 2. 执行工具 → 3. LLM 基于结果总结
    如果不需要工具，走纯文本生成（保留 review/rewrite 安全过滤）
    """
    # ===== 1. 加载历史上下文 =====
    history: list[dict[str, Any]] = []
    if conversation_id:
        from app.services.storage import list_conversation_messages
        raw = list_conversation_messages(conversation_id)
        # 取最近 20 条有效消息（user/assistant/system/tool）
        for item in raw[-20:]:
            role = item.get("role")
            if role not in ("user", "assistant", "system", "tool"):
                continue
            msg: dict[str, Any] = {"role": role, "content": item.get("content", "")}
            meta = item.get("metadata", {})
            if meta.get("tool_calls"):
                msg["tool_calls"] = meta["tool_calls"]
            if meta.get("tool_call_id"):
                msg["tool_call_id"] = meta["tool_call_id"]
            history.append(msg)

    # ===== 2. 第一轮 LLM（决定是否调工具） =====
    first = await generate_with_tools(
        message=message,
        mode=mode,
        system_context=system_context,
        voice_context=voice_context,
        tools=tools,
        history_messages=history,
    )

    # ===== 3. 如果 LLM 要求调工具（有硬上限，防止无限循环） =====
    MAX_AGENT_ROUNDS = 2
    if first.get("tool_calls"):
        # 保存 assistant 的 tool_calls 消息到数据库
        if conversation_id:
            from app.services.storage import add_conversation_message
            add_conversation_message(
                conversation_id,
                "assistant",
                first.get("content", "正在执行操作..."),
                {
                    "type": "assistant_output",
                    "tool_calls": first["tool_calls"],
                    "has_tool_calls": True,
                },
            )

        pending_tool_calls = first["tool_calls"]
        accumulated_history = history + [
            {"role": "assistant", "content": first.get("content", ""), "tool_calls": first["tool_calls"]},
        ]
        all_tool_results: list[dict[str, Any]] = []
        final_content = first.get("content", "")
        final_fallback = bool(first.get("used_fallback"))
        final_fallback_reason = first.get("fallback_reason")

        for round_num in range(MAX_AGENT_ROUNDS):
            tool_results = await execute_tool_calls(pending_tool_calls)
            all_tool_results.extend(tool_results)

            if conversation_id:
                from app.services.storage import add_conversation_message
                for tr in tool_results:
                    add_conversation_message(
                        conversation_id,
                        "tool",
                        tr["content"],
                        {
                            "type": "tool_result",
                            "tool_call_id": tr["tool_call_id"],
                        },
                    )

            accumulated_history = accumulated_history + tool_results
            is_final = round_num >= MAX_AGENT_ROUNDS - 1

            nxt = await generate_with_tools(
                message="基于上述工具执行结果，给用户一个简洁的总结。不要调用更多工具。" if is_final else "基于上述工具执行结果，继续完成用户请求。",
                mode=mode,
                system_context=system_context,
                voice_context=voice_context,
                tools=None if is_final else tools,
                history_messages=accumulated_history,
            )

            final_content = nxt.get("content", "")
            final_fallback = bool(first.get("used_fallback")) or bool(nxt.get("used_fallback"))
            final_fallback_reason = nxt.get("fallback_reason") or first.get("fallback_reason")

            if not nxt.get("tool_calls") or is_final:
                break

            if conversation_id:
                from app.services.storage import add_conversation_message
                add_conversation_message(
                    conversation_id,
                    "assistant",
                    nxt.get("content", "正在执行操作..."),
                    {
                        "type": "assistant_output",
                        "tool_calls": nxt["tool_calls"],
                        "has_tool_calls": True,
                    },
                )
            accumulated_history = accumulated_history + [
                {"role": "assistant", "content": nxt.get("content", ""), "tool_calls": nxt["tool_calls"]},
            ]
            pending_tool_calls = nxt["tool_calls"]

        return {
            "reply": final_content,
            "tool_calls": first.get("tool_calls"),
            "tool_results": all_tool_results,
            "used_system_context": bool(system_context),
            "used_voice_context": bool(voice_context),
            "used_fallback": final_fallback,
            "fallback_reason": final_fallback_reason,
        }

    # ===== 5. 无 tool_calls：走纯文本安全流程（保留 review/rewrite） =====
    draft = first.get("content", "")
    review_result = await review(
        message,
        draft,
        system_context=system_context,
        skip_llm_review=_should_skip_llm_review(message, mode, voice_context) or bool(first.get("used_fallback")),
    )

    final_reply = draft
    final_fallback = first.get("used_fallback")
    final_fallback_reason = first.get("fallback_reason")

    if review_result["needs_revision"] and not bool(first.get("used_fallback")):
        rewritten = await rewrite(
            message=message,
            draft=draft,
            feedback=review_result["feedback"],
            mode=mode,
            system_context=system_context,
            voice_context=voice_context,
        )
        final_reply = cleaner.clean(str(rewritten.get("content", draft)))
        final_fallback = bool(rewritten.get("used_fallback"))
        final_fallback_reason = rewritten.get("fallback_reason") or first.get("fallback_reason")
    else:
        final_reply = cleaner.clean(draft)

    return {
        "reply": final_reply,
        "review_source": "error_fallback" if first.get("used_fallback") else review_result.get("review_source", "rule"),
        "used_system_context": bool(system_context),
        "used_voice_context": bool(voice_context),
        "used_fallback": bool(final_fallback),
        "fallback_reason": final_fallback_reason,
    }


# ===== 保留兼容：结构化命令工作流 =====

COMMAND_SCHEMA = """
{
  "analysis": "string (分析当前问题，1-2句话，包含具体数值)",
  "thinking": "string (详细分析过程，判断逻辑)",
  "advice": "string (给用户的具体建议，包含操作步骤)",
  "risk_warning": "string (风险提示，如果有危险操作)",
  "needs_search": "boolean (是否需要搜索外部知识)",
  "search_query": "string (搜索关键词)",
  "commands": [
    {
      "tool": "string (工具名称，如 process:top, disk:list, temp:scan)",
      "type": "string (read|write|destructive|system|network)",
      "params": object (工具参数),
      "reason": "string (为什么执行这个命令)",
      "confidence": number (0-1, 置信度),
      "risk": "string (low|medium|high)"
    }
  ]
}
"""


async def run_command_workflow(
    message: str,
    mode: str = "default",
    *,
    system_context: dict[str, Any] | None = None,
    voice_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    生成结构化可执行命令的工作流（保留兼容旧接口）。
    """
    from app.services.llm.generator import generate_structured
    structured_result = await generate_structured(
        message=message,
        mode=mode,
        system_context=system_context,
        voice_context=voice_context,
        output_schema=COMMAND_SCHEMA,
    )
    
    parsed = structured_result.get("parsed")
    
    if parsed and isinstance(parsed, dict):
        commands = parsed.get("commands", [])
        valid_commands = [
            cmd for cmd in commands
            if isinstance(cmd, dict) and cmd.get("tool") and cmd.get("type")
        ]
        return {
            "analysis": parsed.get("analysis", ""),
            "commands": valid_commands,
            "reply": parsed.get("analysis") or "已生成分析和建议操作",
            "used_fallback": structured_result.get("used_fallback", False),
            "fallback_reason": structured_result.get("fallback_reason"),
        }
    
    return {
        "analysis": "",
        "commands": [],
        "reply": structured_result.get("content", ""),
        "used_fallback": True,
        "fallback_reason": structured_result.get("fallback_reason", "JSONParseError"),
    }