from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.services.context_manager import context_manager
from app.services.llm.orchestrator import run_agent_workflow
from app.services.response_separator import separator
from app.services.storage import (
    add_assistant_output,
    add_conversation_message,
    ensure_conversation,
    get_conversation,
    get_history_for_llm,
    list_conversation_messages,
    search_conversation_history,
)
from app.services.tools.schema import TOOLS_SCHEMA
from app.utils.response_cleaner import cleaner

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User input message")
    mode: str = Field(default="default", description="Agent mode")
    system_context: dict[str, Any] | None = Field(default=None, description="Realtime desktop monitor context")
    voice_context: dict[str, Any] | None = Field(default=None, description="Voice/session context")
    conversation_id: int | None = Field(default=None, description="Persistent conversation id")
    role_prompt: str | None = Field(default=None, description="Role prompt override")


class ChatResponse(BaseModel):
    reply: str
    review_notes: str | None = None
    review_source: str | None = None
    used_system_context: bool = False
    used_voice_context: bool = False
    tts_content: str | None = None
    tts_required: bool = False
    conversation_id: int | None = None
    memory_messages: list[dict[str, Any]] = Field(default_factory=list)
    context_info: dict[str, Any] = Field(default_factory=dict)
    # 新增：前端可选消费
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    pending_confirm: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/agent", response_model=ChatResponse)
async def chat_with_agent(payload: ChatRequest):
    memory_messages: list[dict[str, Any]] = []
    effective_message = payload.message
    context_info: dict[str, Any] = {
        "original_turns": 0,
        "optimized_turns": 0,
        "history_summary": None,
        "context_strategy": context_manager.strategy.value,
        "estimated_tokens": 0,
        "history_was_cleaned": False,
        "history_was_truncated": False,
    }
    conversation_id = payload.conversation_id

    if conversation_id is None:
        auto_conversation = ensure_conversation(
            title="桌面文本会话",
            role_prompt=payload.role_prompt or "你是一个偏桌面效率、系统诊断与语音交互的 AI Agent",
        )
        conversation_id = int(auto_conversation["id"])

    conversation = get_conversation(conversation_id) if conversation_id is not None else None
    if conversation:
        memory_messages = list_conversation_messages(conversation_id)
        history_messages = get_history_for_llm(conversation_id, limit=6)
        history_candidates = [
            {
                "role": item.role,
                "content": item.content,
                "created_at": item.timestamp,
                "metadata": {},
                "is_meta": item.is_meta,
                "is_fallback": item.is_fallback,
            }
            for item in history_messages
        ]
        optimized_history, history_summary = context_manager.process(
            history=history_candidates,
            current_message=payload.message,
        )
        role_prompt = payload.role_prompt or conversation.get("role_prompt") or ""
        effective_message = context_manager.build_prompt(
            history=optimized_history,
            current_user_msg=payload.message,
            system_prompt=f"你是一个偏桌面效率、系统诊断与语音交互的 AI Agent。角色设定：{role_prompt or '默认桌面Agent'}",
        )
        context_info = {
            "original_turns": len(history_candidates),
            "optimized_turns": len(optimized_history),
            "history_summary": history_summary,
            "context_strategy": context_manager.strategy.value,
            "estimated_tokens": context_manager.get_context_length(optimized_history),
            "history_was_cleaned": any(item.was_cleaned for item in history_messages),
            "history_was_truncated": len(history_messages) < len([item for item in memory_messages if item.get("role") in {"user", "assistant", "system"}]),
        }

    # ===== 改造：传入 tools，让 LLM 自主决定 =====
    result = await run_agent_workflow(
        effective_message,
        payload.mode,
        system_context=payload.system_context,
        voice_context=payload.voice_context,
        tools=TOOLS_SCHEMA,
        conversation_id=conversation_id,
    )

    fallback_reason = str(result.get("fallback_reason") or "") or None

    # 提取待确认任务（从 tool_results 中筛选）
    pending_confirm: list[dict[str, Any]] = []
    for tr in result.get("tool_results", []):
        try:
            tr_content = json.loads(tr.get("content", "{}"))
            if tr_content.get("confirm_required"):
                pending_confirm.append(tr_content)
        except Exception:
            pass

    if conversation_id is not None:
        add_conversation_message(
            conversation_id,
            "user",
            context_manager.clean_content(payload.message),
            {
                **(payload.voice_context or {}),
                "type": "user_input",
            },
        )
        # 保存 assistant 输出，附带工具调用元数据
        extra_meta: dict[str, Any] = {}
        if result.get("tool_calls"):
            extra_meta["tool_calls"] = result["tool_calls"]
        if result.get("tool_results"):
            extra_meta["tool_results"] = result["tool_results"]

        add_assistant_output(
            conversation_id,
            cleaner.clean(result["reply"]),
            review_source=result.get("review_source"),
            used_system_context=bool(result.get("used_system_context", False)),
            used_voice_context=bool(result.get("used_voice_context", False)),
            fallback_reason=fallback_reason,
            system_snapshot=payload.system_context,
            extra_meta=extra_meta,
        )
        memory_messages = list_conversation_messages(conversation_id)

    # 清洗响应中的内部标记，并拆分展示内容 / TTS 内容
    result["reply"] = cleaner.clean(result["reply"])
    if result.get("review_notes"):
        result["review_notes"] = cleaner.clean(result["review_notes"])

    tts_content, display_content = separator.separate(
        full_response=result["reply"],
        user_intent=payload.mode,
    )
    result["reply"] = display_content
    result["tts_content"] = tts_content
    result["tts_required"] = bool(tts_content.strip())

    return ChatResponse(
        **result,
        conversation_id=conversation_id,
        memory_messages=memory_messages,
        context_info=context_info,
        tool_calls=result.get("tool_calls", []),
        pending_confirm=pending_confirm,
    )


class ContextCompressRequest(BaseModel):
    history: list[dict[str, Any]] = Field(default_factory=list)
    current_message: str | None = None


@router.post("/context/compress")
async def compress_context(payload: ContextCompressRequest):
    optimized_history, history_summary = context_manager.process(
        history=payload.history,
        current_message=payload.current_message,
    )
    return {
        "success": True,
        "message": "历史已压缩" if history_summary else "历史记录较短，无需压缩",
        "compressed_history": optimized_history,
        "compression_summary": history_summary,
        "original_turns": len(payload.history),
        "new_turns": len(optimized_history),
        "estimated_tokens": context_manager.get_context_length(optimized_history),
        "context_strategy": context_manager.strategy.value,
    }


# ===== 新增：历史记录搜索接口（供前端 SessionHistory 使用） =====
@router.get("/history/search")
async def search_history(
    conversation_id: int,
    q: str = Query(default="", description="搜索关键词"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """
    搜索会话历史处理记录，返回聚合后的"处理记录"列表
    """
    records, total = search_conversation_history(conversation_id, q, limit, offset)
    return {
        "records": records,
        "total": total,
        "q": q,
        "limit": limit,
        "offset": offset,
    }
