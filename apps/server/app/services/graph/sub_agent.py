from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def sub_agent_invoke(user_query: str, session_id: str = "sub") -> dict[str, Any]:
    """
    子Agent调用入口, 被task_planner_node分派调用
    复用主图, 但使用独立session避免状态污染
    """
    try:
        from app.services.graph.graph import build_agent_graph, build_invoke_config
        from app.services.graph.state import init_state

        graph = build_agent_graph()
        sub_state = init_state(raw_query=user_query, user_id="sub_agent", session_id=session_id)
        cfg = build_invoke_config(user_id="sub_agent", session_id=session_id, trace_id=sub_state["trace_id"])
        result = await graph.ainvoke(sub_state, config=cfg)
        return {"content": result.get("memory_summary", result.get("raw_response", ""))}
    except Exception as e:
        logger.warning(f"sub_agent_invoke失败: {e}")
        return {"content": "", "error": str(e)}