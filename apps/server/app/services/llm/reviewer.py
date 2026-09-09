from __future__ import annotations

import json
from typing import Any

from app.services.llm.context_builder import summarize_system_context
from app.services.llm.provider import LLMProviderError, provider
from app.utils.response_cleaner import cleaner


REVIEWER_SYSTEM_PROMPT = """
你是 AI Desktop Agent 的审核者模型。
请判断生成者回复是否满足以下要求：
1. 是否真正回答了用户问题；
2. 是否结合了系统监控上下文；
3. 是否给出了明确下一步建议；
4. 是否适合桌面端展示与语音播报。
输出 JSON：{"needs_revision": boolean, "feedback": string}
""".strip()


async def review(
    message: str,
    draft: str,
    *,
    system_context: dict[str, Any] | None = None,
    skip_llm_review: bool = False,
) -> dict[str, Any]:
    if provider.enabled and not skip_llm_review:
        system_summary = summarize_system_context(system_context)
        user_prompt = (
            f"用户问题: {message}\n"
            f"生成稿: {draft}\n"
            f"系统监控上下文: {system_summary}\n"
            "请仅输出 JSON，不要加 Markdown 代码块。"
        )

        try:
            raw = await provider.chat(
                system_prompt=REVIEWER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0,
                response_format={"type": "json_object"},
            )
            parsed = json.loads(raw)
            needs_revision = bool(parsed.get("needs_revision", False))
            feedback = str(parsed.get("feedback", "回答可直接返回。"))
            return {
                "needs_revision": needs_revision,
                "feedback": cleaner.clean(feedback),
                "draft_preview": cleaner.clean(draft[:120]),
                "review_source": "llm",
            }
        except (LLMProviderError, json.JSONDecodeError, TypeError, ValueError) as exc:
            fallback_feedback = f"审核模型调用失败，回退到规则审核：{exc}"
            return {
                "needs_revision": False,
                "feedback": cleaner.clean(fallback_feedback),
                "draft_preview": cleaner.clean(draft[:120]),
                "review_source": "rule",
            }
    else:
        fallback_feedback = "LLM provider not configured，回退到规则审核。"

    needs_revision = len(message.strip()) > 30 or "建议" not in draft
    feedback = (
        "回答可进一步结构化，补充更明确的执行步骤。"
        if needs_revision
        else "回答可直接返回。"
    )

    return {
        "needs_revision": needs_revision,
        "feedback": cleaner.clean(f"{feedback} {fallback_feedback}".strip()),
        "draft_preview": cleaner.clean(draft[:120]),
        "review_source": "rule",
    }
