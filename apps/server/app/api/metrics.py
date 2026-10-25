from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.observability.metrics_collector import get_metrics_collector

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/llm")
async def get_llm_metrics(window_minutes: int = Query(default=5, ge=1, le=60)):
    """
    LLM调用指标汇总：TTFT/TPOT/P99延迟、token成本、重试率
    """
    collector = get_metrics_collector()
    return collector.get_llm_summary(window_minutes=window_minutes)


@router.get("/tools")
async def get_tool_metrics():
    """
    工具调用指标汇总：失败率、按工具分类统计
    """
    collector = get_metrics_collector()
    return collector.get_tool_summary()


@router.get("/session-cost/{session_id}")
async def get_session_cost(session_id: str):
    """
    单会话token成本追踪，超过基线2倍则告警
    """
    collector = get_metrics_collector()
    return collector.get_session_cost(session_id)