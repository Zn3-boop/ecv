from __future__ import annotations

import json
from typing import Any

from app.services.agents.registry import agent_registry
from app.services.intent_detector import detect_intent, extract_entities

INTENT_TO_AGENT_MAP: dict[str, str] = {
    "system_monitor": "system_monitor",
    "system_optimize": "system_clean",
    "system_scan": "system_clean",
    "desktop_control": "app_launch",
    "search_only": "browser",
    "store_action": "store",
    "content_gen": "content_gen",
}

ROUTE_CONFIDENCE_THRESHOLD = 0.7


def map_intent_to_agent(intent: str) -> str | None:
    return INTENT_TO_AGENT_MAP.get(intent)


def _adapt_llm_tool_args_to_agent(
    agent_name: str,
    func_args: dict[str, Any],
    user_query: str,
) -> dict[str, Any]:
    adapted = dict(func_args)

    if agent_name == "app_launch":
        if "action" not in adapted:
            adapted["action"] = "launch"
        if "path" not in adapted and "query" not in adapted:
            adapted["query"] = user_query

    elif agent_name == "system_monitor":
        if "action" not in adapted:
            adapted["action"] = "all"

    elif agent_name == "system_clean":
        if "action" not in adapted:
            adapted["action"] = "scan_and_cleanup"

    elif agent_name == "browser":
        if "action" not in adapted:
            adapted["action"] = "search"
        if "query" not in adapted:
            adapted["query"] = user_query

    elif agent_name == "store":
        if "action" not in adapted:
            adapted["action"] = "search"
        if "query" not in adapted and "package_id" not in adapted:
            adapted["query"] = user_query

    elif agent_name == "content_gen":
        if "action" not in adapted:
            adapted["action"] = "generate"
        if "task" not in adapted:
            adapted["task"] = user_query

    return adapted


def _get_traced_execution():
    try:
        from app.services.observability.tracing import traced_execution
        return traced_execution
    except Exception:
        return None


def build_clarification_message(user_query: str, intent: str, intent_confidence: float) -> dict[str, Any]:
    """
    意图澄清节点：低置信度时结构化反问用户确认意图。
    返回 {"needs_clarification": True, "message": ..., "suggested_intents": [...]}
    """
    known_intents = list(INTENT_TO_AGENT_MAP.keys())
    return {
        "needs_clarification": True,
        "message": f"我不太确定您的意图（置信度{intent_confidence:.0%}），您是想：",
        "suggested_intents": known_intents,
        "raw_query": user_query,
        "detected_intent": intent,
        "intent_confidence": intent_confidence,
    }


async def route_via_llm(
    user_query: str,
    tools: list[dict[str, Any]] | None = None,
    session: Any | None = None,
) -> tuple[str, dict[str, Any], float]:
    """
    路由逻辑：先走 intent_detector 快路径（含实体抽取），未命中走 LLM tool-call 慢路径。
    返回 (子Agent名称, 子Agent入参args, route_confidence)
    - route_confidence >= 0.7: 可直接执行
    - route_confidence < 0.7: 需走意图澄清节点
    """
    fast_intent, intent_confidence = detect_intent(user_query)
    if fast_intent and fast_intent != "llm_decompose":
        agent_name = map_intent_to_agent(fast_intent)
        if agent_name and agent_name in agent_registry:
            agent_args = extract_entities(user_query, fast_intent)
            return agent_name, agent_args, intent_confidence

    if tools is None:
        tools = agent_registry.all_tools()

    if not tools:
        return "system_monitor", {"action": "overview"}, 0.5

    from app.services.llm.generator import generate_with_tools

    traced_execution = _get_traced_execution()

    if traced_execution:
        with traced_execution("chat", {
            "gen_ai.operation.name": "chat",
            "gen_ai.system.name": "desktop-agent",
            "gen_ai.routing.path": "slow_llm_toolcall",
            "gen_ai.user.query": user_query[:200],
        }):
            llm_result = await generate_with_tools(
                message=user_query,
                mode="default",
                tools=tools,
            )
    else:
        llm_result = await generate_with_tools(
            message=user_query,
            mode="default",
            tools=tools,
        )

    tool_calls = llm_result.get("tool_calls", [])
    if tool_calls:
        first_call = tool_calls[0]
        func_name = first_call.get("function", {}).get("name", "")
        try:
            func_args = json.loads(first_call.get("function", {}).get("arguments", "{}"))
        except Exception:
            func_args = {}

        if func_name in agent_registry:
            adapted_args = _adapt_llm_tool_args_to_agent(func_name, func_args, user_query)
            return func_name, adapted_args, 0.8

        for agent in agent_registry._agents.values():
            if func_name in str(agent.parameters):
                adapted_args = _adapt_llm_tool_args_to_agent(
                    agent.name,
                    {"query": user_query, "tool_override": func_name, "tool_args": func_args},
                    user_query,
                )
                return agent.name, adapted_args, 0.7

    print(f"[Router] LLM slow path: no sub-agent matched for query='{user_query[:80]}', tool_calls={len(tool_calls)}")
    return "", {}, 0.2