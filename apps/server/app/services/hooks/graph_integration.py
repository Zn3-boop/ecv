from __future__ import annotations

import logging
from typing import Any

from app.services.hooks.types import HookEvent
from app.services.hooks import init_hooks, dispatch_hook
from app.services.graph.state import AgentState
from app.services.graph.metrics import NodeMetrics, inc_counter

logger = logging.getLogger(__name__)


def _clarification_payload(clarification: Any) -> dict[str, Any]:
    """B6: 将 ClarificationResult 转为结构化 state 字段（选项按钮式 JSON）。

    输出:
    - needs_clarification: True
    - clarification_message: 澄清问题文本
    - clarification_reason_code: 澄清原因码(如 AMBIGUOUS_ENTITY)
    - clarification_options: [{id,label,recommended,impact}, ...] 可供前端渲染为按钮
    """
    reason_code = ""
    try:
        if getattr(clarification, "reason_code", None):
            rc = clarification.reason_code
            reason_code = rc.value if hasattr(rc, "value") else str(rc)
    except Exception:
        reason_code = ""

    options: list[dict[str, Any]] = []
    for o in clarification.options or []:
        options.append({
            "id": getattr(o, "id", ""),
            "label": getattr(o, "label", ""),
            "recommended": getattr(o, "recommended", False),
            "impact": getattr(o, "impact", ""),
        })

    return {
        "needs_clarification": True,
        "clarification_message": getattr(clarification, "question", ""),
        "clarification_reason_code": reason_code,
        "clarification_options": options,
    }


async def rag_retrieve_with_hooks(state: AgentState) -> dict[str, Any]:
    """
    RAG 检索增强节点 (Hook 增强版)

    执行流程:
    1. dispatch BEFORE_AGENT_START → 触发 rag_web_parallel Hook
       → Hook 内部: 查询改写 → 并行检索(RAG+Web) → 去重 → 融合 → 验证 → Prompt构造
    2. 如果 Hook 返回了 fused_context / rag_results / web_results，直接使用
    3. 如果 Hook 未生效(被 block / 异常)，降级到原有 rag_retrieve_node 逻辑

    这就是 "Hook 是增强层，不是替代层" 的落地方式。
    """
    from app.services.hooks import init_hooks
    init_hooks()

    hook_ctx = {
        "raw_query": state.get("raw_query", ""),
        "standalone_query": state.get("standalone_query", ""),
        "retrieval_queries": state.get("retrieval_queries", []),
        "user_id": state.get("user_id", ""),
        "session_id": state.get("session_id", ""),
        "rag_user_acl": state.get("rag_user_acl", []) or (["admin"] if state.get("user_id", "") == "admin" else ["public"]),
    }

    result_ctx = await dispatch_hook(HookEvent.BEFORE_AGENT_START, hook_ctx)

    if result_ctx.get("_hook_blocked"):
        logger.warning("RAG+Web并行检索被Hook阻断，降级到原有RAG节点")
        return await _fallback_rag_retrieve(state)

    fused_context = result_ctx.get("fused_context", "")
    rag_results = result_ctx.get("rag_results", [])
    web_results = result_ctx.get("web_results", [])

    if fused_context or rag_results or web_results:
        rewrite_info = result_ctx.get("rewrite_result", {})
        validation_info = result_ctx.get("validation_result", {})

        return {
            "rag_query": rewrite_info.get("rag_query", state.get("raw_query", "")),
            "rag_results": rag_results,
            "rag_context": fused_context,
            "rag_evidence_ids": result_ctx.get("evidence_ids", []),
            "rag_evidence_map": result_ctx.get("evidence_map", {}),
            "rag_contradiction": result_ctx.get("contradiction", {}),
            "rag_should_refuse": not validation_info.get("passed", True),
            "evidence": {
                "rag_context": fused_context[:500],
                "rag_evidence_count": len(result_ctx.get("evidence_ids", [])),
                "web_result_count": len(web_results),
                "fusion_strategy": result_ctx.get("fusion_strategy", ""),
                "hook_enhanced": True,
            },
        }

    logger.info("Hook未返回检索结果，降级到原有RAG节点")
    return await _fallback_rag_retrieve(state)


async def _fallback_rag_retrieve(state: AgentState) -> dict[str, Any]:
    """降级：原有 rag_retrieve_node 逻辑（纯本地RAG，无Web并行）"""
    from app.services.graph.nodes import rag_retrieve_node
    return await rag_retrieve_node(state)


async def tool_execute_with_hooks(state: AgentState) -> dict[str, Any]:
    """
    工具执行增强节点 (Hook 增强版)

    执行流程:
    1. dispatch TOOL_CALL → 触发 tool_call_guard Hook
       → Hook 内部: 风险评估 → 高风险阻断/审批
    2. 如果 Hook 阻断，直接返回错误
    3. 否则继续原有工具执行逻辑
    """
    init_hooks()

    tool_name = state.get("tool_name", "")
    tool_args = state.get("tool_args", {})

    hook_ctx = {
        "tool_name": tool_name,
        "tool_args": tool_args,
        "user_id": state.get("user_id", ""),
        "raw_query": state.get("raw_query", ""),
    }

    result_ctx = await dispatch_hook(HookEvent.TOOL_CALL, hook_ctx)

    if result_ctx.get("_hook_blocked"):
        blocked_by = result_ctx.get("_hook_blocked_by", "unknown")
        risk_level = result_ctx.get("risk_level", "unknown")
        blocked_reason = result_ctx.get("_hook_blocked_reason", "") or result_ctx.get("blocked_reason", "")
        reason_txt = f"：{blocked_reason}" if blocked_reason else ""
        return {
            "tool_result": {"ok": False, "error": f"工具调用被安全Hook阻断: risk={risk_level}, by={blocked_by}{reason_txt}"},
            "last_error": f"Tool call blocked by {blocked_by}: risk={risk_level}{reason_txt}",
            "error_type": "security",
        }

    from app.services.graph.nodes import tool_execute_node
    return await tool_execute_node(state)


async def context_assemble_with_hooks(state: AgentState) -> dict[str, Any]:
    """
    上下文组装增强节点 (Hook 增强版)

    执行流程:
    1. dispatch CONTEXT_ASSEMBLE → 触发 context_manage Hook
       → Hook 内部: 消息压缩、近期保留、远期占位符、预算截断
    2. Hook 返回压缩后的 messages
    """
    init_hooks()

    hook_ctx = {
        "messages": state.get("messages", []),
        "raw_query": state.get("raw_query", ""),
        "session_id": state.get("session_id", ""),
    }

    result_ctx = await dispatch_hook(HookEvent.CONTEXT_ASSEMBLE, hook_ctx)

    compressed_messages = result_ctx.get("messages")
    if compressed_messages:
        return {"messages": compressed_messages}

    return {}


def _state_turn_history(state: AgentState) -> list[dict[str, Any]]:
    """从会话 state 中提取对话轮次历史，供会话压缩使用。"""
    msgs = state.get("messages") or []
    if msgs:
        return [
            {
                "role": str(m.get("role", "user")) if m.get("role") in ("user", "assistant", "system") else "user",
                "content": str(m.get("content", "")),
            }
            for m in msgs
            if str(m.get("content", "")).strip()
        ]
    history_log = state.get("history_log") or []
    return [
        {"role": "assistant" if i % 2 else "user", "content": str(line)}
        for i, line in enumerate(history_log)
        if str(line).strip()
    ]


async def session_compact(
    ctx: dict[str, Any],
    manager: Any | None = None,
) -> dict[str, Any]:
    """
    M6 长会话瘦身（双层摘要）核心逻辑。

    对会话历史做"双层摘要"压缩：
    - 远期轮次 → 提炼为 memory_summary（far 层）
    - 近期轮次完整保留 → memory_recent_turns（near 层）

    流程：
    1. dispatch SESSION_COMPACT → 会话级压缩 Hook 参与
    2. 套用双层 ContextManager（ContextManager.process 即为双层策略）
    3. 将 far 层摘要作为 C 级系统实证写回 memory store（不只在 state 字段）

    返回：若未触发压缩返回 {}；否则返回压缩后的双层摘要字段。
    """
    from app.services.context_manager import (
        CompressionStrategy,
        ContextManager,
    )
    from app.services.hooks import dispatch_hook
    from app.services.hooks.types import HookEvent
    from app.services.graph.memory_store import EVIDENCE_LEVEL_C, get_memory_store

    turns = ctx.get("turn_history") or []
    if not turns:
        return {}

    max_recent_turns = int(ctx.get("compact_max_recent_turns", ContextManager.DEFAULT_MAX_TURNS))
    max_context_chars = int(ctx.get("compact_max_context_chars", ContextManager.DEFAULT_MAX_CONTEXT_CHARS))

    # 1) 会话级 Hook 参与（SESSION_COMPACT）
    await dispatch_hook(
        HookEvent.SESSION_COMPACT,
        {"turn_history": turns, "user_id": ctx.get("user_id", "")},
    )

    # 2) 双层 ContextManager 压缩
    if manager is None:
        manager = ContextManager(
            max_turns=max_recent_turns,
            max_context_chars=max_context_chars,
            strategy=CompressionStrategy.HYBRID,
        )
    compressed, summary = manager.process(turns)

    # 未超过阈值 → 不触发压缩
    if summary is None and len(compressed) == len(turns):
        return {}

    raw_tokens = sum(manager.estimate_tokens(str(t.get("content", ""))) for t in turns)
    comp_tokens = (
        sum(manager.estimate_tokens(str(c.get("content", ""))) for c in compressed)
        + (manager.estimate_tokens(summary) if summary else 0)
    )
    reduction = max(0.0, (1 - (comp_tokens / raw_tokens)) * 100) if raw_tokens else 0.0

    # 3) far 层摘要作为系统实证写回 store
    try:
        user_id = ctx.get("user_id") or ctx.get("session_id") or "default"
        store = get_memory_store()
        import time

        store.put(
            user_id,
            key=f"session_compact_C_{int(time.time() * 1000)}",
            value={
                "memory_summary": summary or "",
                "recent_turn_count": len(compressed),
                "original_turn_count": len(turns),
                "token_reduction_pct": round(reduction, 2),
                "session_id": ctx.get("session_id", ""),
            },
            level=EVIDENCE_LEVEL_C,
            owner="system",
        )
    except Exception:
        logger.exception("session_compact 持久化失败(不影响主流程)")

    return {
        "memory_summary": summary or "",
        "memory_recent_turns": compressed,
        "session_compacted": True,
        "memory_token_reduction": round(reduction, 2),
    }


async def turn_end_with_hooks(state: AgentState) -> dict[str, Any]:
    """
    Turn 结束增强节点 (Hook 增强版)

    执行流程:
    1. dispatch TURN_END → 触发 checkpoint Hook
       → Hook 内部: 保存检查点(目标/计划/产出物/剩余步骤)
    2. dispatch SESSION_COMPACT + 双层摘要 → M6 长会话瘦身
    """
    init_hooks()

    hook_ctx = {
        "checkpoint_action": "save",
        "task_id": state.get("session_id", ""),
        "original_goal": state.get("raw_query", ""),
        "completed_steps": state.get("step_results", []),
        "remaining_steps": [],
        "checkpoint_metadata": {
            "intent": state.get("intent", ""),
            "route_target": state.get("route_target", ""),
        },
        "user_id": state.get("user_id", ""),
        "session_id": state.get("session_id", ""),
    }

    result_ctx = await dispatch_hook(HookEvent.TURN_END, hook_ctx)

    result: dict[str, Any] = {}
    if result_ctx.get("checkpoint_saved"):
        result["evidence"] = {
            **state.get("evidence", {}),
            "checkpoint_saved": True,
            "task_id": result_ctx.get("task_id", ""),
        }

    # M6: 长会话瘦身（双层摘要），仅在触发压缩时向 state 追加结果
    compact_ctx = dict(hook_ctx)
    compact_ctx["turn_history"] = _state_turn_history(state)
    compact = await session_compact(compact_ctx)
    if compact:
        result["memory_summary"] = compact["memory_summary"]
        result["memory_recent_turns"] = compact["memory_recent_turns"]
        result["session_compacted"] = True
        result["memory_token_reduction"] = compact["memory_token_reduction"]

    return result


async def detect_intent_with_hooks(state: AgentState) -> dict[str, Any]:
    """
    意图识别增强节点 (Hook 增强版)

    执行流程:
    1. 用 PluginRegistry 的 IntentRecognizer 做意图识别+参数抽取
    2. 用 PluginRegistry 的 IntentClarifier 做澄清判断
    3. 如果需要澄清，直接返回澄清信息
    4. 否则返回识别结果，降级到原有 detect_intent_node
    """
    with NodeMetrics("detect_intent"):
        init_hooks()
        raw_query = state.get("raw_query", "")

        try:
            from app.services.hooks.plugins.registry import get_plugin_registry, load_plugin_config
            config = load_plugin_config()
            plugin_reg = get_plugin_registry()

            recognizer_name = config.get("intent_recognizer", {}).get("type", "rule")
            recognizer = plugin_reg.get_intent_recognizer(recognizer_name)

            intent_result = await recognizer.recognize(
                raw_query,
                context={
                    "session_id": state.get("session_id", ""),
                    "user_id": state.get("user_id", ""),
                },
            )

            clarifier_name = config.get("clarifier", {}).get("type", "rule")
            clarifier = plugin_reg.get_clarifier(clarifier_name)
            clarification = await clarifier.check_clarification(intent_result)

            result: dict[str, Any] = {
                "intent": intent_result.intent.value,
                "intent_confidence": intent_result.confidence,
                "entities": intent_result.entities,
                "standalone_query": intent_result.standalone_query,
            }

            if clarification.need_clarification:
                result.update(_clarification_payload(clarification))

            return result

        except Exception as e:
            logger.warning(f"Hook意图识别失败，降级到原有节点: {e}")
            from app.services.graph.nodes import detect_intent_node
            return await detect_intent_node(state)


async def clarification_with_hooks(state: AgentState) -> dict[str, Any]:
    """
    澄清增强节点 (Hook 增强版)

    执行流程:
    1. 如果 detect_intent_with_hooks 已经产出了结构化澄清信息，直接使用
    2. 否则用 IntentClarifier 重新判断
    3. 降级到原有 clarification_node
    """
    with NodeMetrics("clarification_node"):
        inc_counter("graph_clarification_trigger_total")
        init_hooks()

        if state.get("clarification_message"):
            return {
                "needs_clarification": True,
                "clarification_message": state.get("clarification_message", ""),
                "clarification_reason_code": state.get("clarification_reason_code", ""),
                "clarification_options": state.get("clarification_options", []) or [],
                "standalone_query": state.get("raw_query", ""),
            }

        try:
            from app.services.hooks.plugins.registry import get_plugin_registry, load_plugin_config
            config = load_plugin_config()
            plugin_reg = get_plugin_registry()

            from app.services.hooks.plugins.intent.recognizer import IntentResult, IntentType, ActionType
            intent_result = IntentResult(
                raw_query=state.get("raw_query", ""),
                intent=IntentType(state.get("intent", "unknown")) if state.get("intent") else IntentType.UNKNOWN,
                confidence=state.get("intent_confidence", 0.0),
            )

            clarifier_name = config.get("clarifier", {}).get("type", "rule")
            clarifier = plugin_reg.get_clarifier(clarifier_name)
            clarification = await clarifier.check_clarification(intent_result)

            if clarification.need_clarification:
                payload = _clarification_payload(clarification)
                payload["standalone_query"] = state.get("raw_query", "")
                return payload

            return {"needs_clarification": False}

        except Exception as e:
            logger.warning(f"Hook澄清失败，降级到原有节点: {e}")
            from app.services.graph.nodes import clarification_node
            return await clarification_node(state)


async def extract_entities_with_hooks(state: AgentState) -> dict[str, Any]:
    """
    实体抽取增强节点 (Hook 增强版)

    执行流程:
    1. 用 PluginRegistry 的 QueryRewriter 做查询改写
    2. 产出 standalone_query + retrieval_queries
    3. 降级到原有 extract_entities_node
    """
    with NodeMetrics("extract_entities"):
        init_hooks()
        raw_query = state.get("raw_query", "")
        intent = state.get("intent", "")

        try:
            from app.services.hooks.plugins.registry import get_plugin_registry, load_plugin_config
            config = load_plugin_config()
            plugin_reg = get_plugin_registry()

            rewriter_name = config.get("rewriter", {}).get("type", "rule")
            rewriter = plugin_reg.get_rewriter(rewriter_name)

            rewrite_result = await rewriter.rewrite(
                raw_query,
                context={
                    "intent": intent,
                    "session_id": state.get("session_id", ""),
                    "user_id": state.get("user_id", ""),
                },
            )

            from app.services.graph.nodes import _extract_entities
            entities = await _extract_entities(raw_query, intent)

            return {
                "entities": entities,
                "standalone_query": rewrite_result.standalone_query,
                "retrieval_queries": rewrite_result.retrieval_queries,
            }

        except Exception as e:
            logger.warning(f"Hook实体抽取失败，降级到原有节点: {e}")
            from app.services.graph.nodes import extract_entities_node
            return await extract_entities_node(state)