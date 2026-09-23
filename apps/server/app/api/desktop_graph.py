"""
Desktop-Agent LangGraph 状态图 HTTP 接口层。
路由：会话执行、HITL人工审批、TimeTravel(checkpoint历史/fork分支)、
      Governor全量扫描、信号CRUD、Tool-Search查询、/metrics指标端点
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/desktop/graph", tags=["desktop-graph"])


# ---------------- Pydantic 请求响应模型 ----------------

class GraphInvokeRequest(BaseModel):
    raw_query: str = Field(..., min_length=1, max_length=2000, description="用户原始指令")
    user_id: str = Field(..., min_length=1, max_length=128, description="用户ID")
    session_id: Optional[str] = Field(default=None, min_length=1, max_length=64, description="会话ID，空则自动生成")

class GraphInvokeResponse(BaseModel):
    success: bool
    session_id: str
    trace_id: str
    result: dict[str, Any]
    is_interrupted: bool = Field(description="是否停在HITL审批中断点")

class ApprovalSubmitRequest(BaseModel):
    thread_id: str = Field(..., min_length=1, max_length=128, description="会话thread_id")
    approval_status: str = Field(..., description="审批结果: ok / reject")
    comment: Optional[str] = Field(default=None, max_length=500, description="审批备注")

class FullScanRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128, description="用户ID")

class SignalPatchRequest(BaseModel):
    status: str = Field(..., description="目标状态: processing / resolved")
    owner: str = Field(..., min_length=1, max_length=64, description="处理人")
    comment: str = Field(default="", max_length=500, description="处理备注")

class ForkCheckpointRequest(BaseModel):
    thread_id: str = Field(..., min_length=1, max_length=128, description="源会话thread_id")
    checkpoint_id: str = Field(..., min_length=1, max_length=128, description="源checkpoint ID")
    new_session_id: Optional[str] = Field(default=None, min_length=1, max_length=64, description="新会话ID，空则自动生成")

class ToolSearchQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200, description="工具检索关键词")
    top_k: int = Field(default=3, ge=1, le=20, description="返回top_k结果")


def _get_graph(request: Request) -> Any:
    graph = getattr(request.app.state, "graph", None)
    if graph is None:
        raise HTTPException(status_code=503, detail="LangGraph未初始化，请检查服务启动日志")
    return graph


# 1. 主执行接口
@router.post("/invoke", response_model=GraphInvokeResponse)
async def graph_invoke(req: GraphInvokeRequest, request: Request):
    from app.services.graph.graph import build_invoke_config
    from app.services.graph.state import init_state

    graph = _get_graph(request)
    session_id = req.session_id or str(uuid.uuid4())[:8]
    trace_id = str(uuid.uuid4())
    input_state = init_state(
        raw_query=req.raw_query,
        session_id=session_id,
        trace_id=trace_id,
        user_id=req.user_id,
    )
    cfg = build_invoke_config(
        user_id=req.user_id,
        session_id=session_id,
        trace_id=trace_id,
    )
    try:
        result = await graph.ainvoke(input_state, config=cfg)
    except Exception as e:
        logger.exception(f"graph.ainvoke失败: {e}")
        raise HTTPException(status_code=500, detail=f"图执行失败: {str(e)}")

    try:
        interrupt_history = await graph.aget_state(config=cfg)
        is_interrupted = bool(interrupt_history.next)
    except Exception:
        is_interrupted = False

    return GraphInvokeResponse(
        success=True,
        session_id=session_id,
        trace_id=trace_id,
        result=result,
        is_interrupted=is_interrupted,
    )


# 2. HITL人工审批接口：更新interrupt_before节点状态，恢复图执行
@router.post("/approval")
async def submit_approval(req: ApprovalSubmitRequest, request: Request):
    allowed_status = {"ok", "reject"}
    if req.approval_status not in allowed_status:
        raise HTTPException(status_code=400, detail=f"approval_status必须为 {allowed_status}")

    graph = _get_graph(request)
    config = {"configurable": {"thread_id": req.thread_id}}
    try:
        await graph.aupdate_state(
            config=config,
            values={"approval_status": req.approval_status},
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"审批状态更新失败: {str(e)}")

    if req.approval_status == "reject":
        return {
            "success": True,
            "thread_id": req.thread_id,
            "approval_status": "reject",
            "result": None,
        }

    try:
        result = await graph.ainvoke(None, config=config)
    except Exception as e:
        logger.exception(f"审批后恢复执行失败: {e}")
        raise HTTPException(status_code=500, detail=f"审批后恢复执行失败: {str(e)}")

    return {
        "success": True,
        "thread_id": req.thread_id,
        "approval_status": req.approval_status,
        "result": result,
    }


# 3. Time-Travel：获取checkpoint历史快照列表
@router.get("/checkpoints")
async def list_checkpoints(thread_id: str, request: Request):
    graph = _get_graph(request)
    config = {"configurable": {"thread_id": thread_id}}
    checkpoints = []
    try:
        async for ckpt in graph.aget_state_history(config):
            ckpt_id = ""
            if ckpt.config and "configurable" in ckpt.config:
                ckpt_id = ckpt.config["configurable"].get("checkpoint_id", "")
            checkpoints.append({
                "checkpoint_id": ckpt_id,
                "timestamp": ckpt.metadata.get("step") if ckpt.metadata else None,
                "next_nodes": list(ckpt.next),
            })
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"获取checkpoint历史失败: {str(e)}")
    return {"thread_id": thread_id, "checkpoints": checkpoints}


# 4. Time-Travel：fork从历史checkpoint分叉出新会话
@router.post("/fork")
async def fork_checkpoint(req: ForkCheckpointRequest, request: Request):
    graph = _get_graph(request)
    old_config = {"configurable": {"thread_id": req.thread_id}}
    new_sid = req.new_session_id or str(uuid.uuid4())[:8]
    new_tid = f"{req.thread_id.split('_')[0]}_{new_sid}"
    try:
        await graph.acopy_checkpoint(
            source_config=old_config,
            source_checkpoint_id=req.checkpoint_id,
            target_config={"configurable": {"thread_id": new_tid}},
        )
    except AttributeError:
        raise HTTPException(
            status_code=501,
            detail="当前checkpointer不支持acopy_checkpoint，请使用支持fork的checkpointer",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"fork失败: {str(e)}")
    return {
        "success": True,
        "new_thread_id": new_tid,
        "source_checkpoint_id": req.checkpoint_id,
    }


# 5. Governor接口：全量扫描
@router.post("/governor/full-scan")
async def governor_full_scan(req: FullScanRequest):
    from app.services.graph.memory_store import get_governing_store

    store = get_governing_store()
    scan_res = store.full_scan(user_id=req.user_id)
    return {
        "success": True,
        "conflict": scan_res["conflict"],
        "expired": scan_res["expired"],
        "signal_generated": scan_res["signal_generated"],
    }


# 6. 查询纠错信号列表
@router.get("/governor/signals")
async def list_signals(user_id: Optional[str] = None):
    from app.services.graph.memory_store import get_governing_store

    store = get_governing_store()
    sigs = store.list_signals(user_id=user_id or "")
    return {"signals": sigs}


# 7. PATCH更新信号状态（信号闭环）
@router.patch("/governor/signals/{signal_id}")
async def patch_signal(signal_id: str, body: SignalPatchRequest):
    from app.services.graph.memory_store import get_governing_store

    store = get_governing_store()
    ok = store.update_signal_status(
        sig_id=signal_id,
        status=body.status,
        owner=body.owner,
        comment=body.comment,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="signal不存在或非法状态流转")
    sig = store.get_signal(signal_id)
    return {"success": True, "signal_id": signal_id, "status": sig.get("status") if sig else None}


# 8. Tool-Search接口
@router.post("/tool-search/query")
async def tool_search_query(req: ToolSearchQueryRequest):
    from app.services.graph.tool_search import tool_search_instance

    hits = tool_search_instance.search_tool(req.query, top_k=req.top_k)
    hit_names = [t.name for t in hits]
    loaded = tool_search_instance.get_current_loaded_schema()
    return {"success": True, "hit_list": hit_names, "loaded_schema": loaded}


# ========== Governor + HITL 人工审批信号接口 ==========

class HitlSignalAckRequest(BaseModel):
    thread_id: str = Field(..., min_length=1, max_length=128, description="会话thread_id")
    comment: Optional[str] = Field(default=None, max_length=500, description="人工备注")

class HitlSignalDecisionRequest(BaseModel):
    thread_id: str = Field(..., min_length=1, max_length=128, description="会话thread_id")
    decision: str = Field(..., description="人工决策: approve / reject")
    comment: Optional[str] = Field(default=None, max_length=500, description="人工备注")


# 9. 查询会话当前校正信号状态
@router.get("/hitl/signal")
async def get_hitl_signal(thread_id: str = Query(..., min_length=1, max_length=128), request: Request = None):
    """
    查询会话当前Governor校正信号状态
    返回correction_signal、correction_loops、needs_hitl、task_plan状态
    """
    graph = _get_graph(request)
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state_snapshot = await graph.aget_state(config=config)
        values = state_snapshot.values
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"获取会话状态失败: {str(e)}")

    return {
        "success": True,
        "thread_id": thread_id,
        "correction_signal": values.get("correction_signal", {}),
        "correction_loops": values.get("correction_loops", 0),
        "needs_hitl": values.get("needs_hitl", False),
        "hitl_decision": values.get("hitl_decision", ""),
        "hitl_comment": values.get("hitl_comment", ""),
        "task_plan_status": values.get("task_plan_status", ""),
        "task_plan_enabled": values.get("task_plan_enabled", False),
        "clarification_message": values.get("clarification_message", ""),
        "next_nodes": list(state_snapshot.next),
    }


# 10. 人工ACK：确认看到pollution信号，仅标记已读，不恢复图执行
@router.post("/hitl/signal/ack")
async def ack_hitl_signal(req: HitlSignalAckRequest, request: Request):
    """
    人工ACK：确认看到pollution信号，保持暂停状态，仅记录人工备注
    图不会恢复执行，需要后续调用decision接口做approve/reject
    """
    graph = _get_graph(request)
    config = {"configurable": {"thread_id": req.thread_id}}
    try:
        state_snapshot = await graph.aget_state(config=config)
        values = state_snapshot.values
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"获取会话状态失败: {str(e)}")

    if not values.get("needs_hitl", False):
        raise HTTPException(status_code=400, detail="当前会话没有待人工处理的HITL信号")

    correction_signal = values.get("correction_signal", {})
    update = {
        "correction_signal": {
            **correction_signal,
            "ack": True,
            "ack_comment": req.comment or "",
        },
    }
    try:
        await graph.aupdate_state(config=config, values=update)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"ACK状态更新失败: {str(e)}")

    return {
        "success": True,
        "thread_id": req.thread_id,
        "status": "ack",
        "msg": "信号已标记已读，图保持暂停，等待decision接口approve/reject",
    }


# 11. 人工决策接口：approve放行 / reject终止任务，恢复图执行
@router.post("/hitl/signal/decision")
async def hitl_make_decision(req: HitlSignalDecisionRequest, request: Request):
    """
    统一人工决策接口：approve（放行继续执行）/ reject（终止任务）
    写入hitl_decision到state，恢复LangGraph图执行
    """
    if req.decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision只能是 approve / reject")

    graph = _get_graph(request)
    config = {"configurable": {"thread_id": req.thread_id}}
    try:
        state_snapshot = await graph.aget_state(config=config)
        values = state_snapshot.values
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"获取会话状态失败: {str(e)}")

    if not values.get("needs_hitl", False):
        raise HTTPException(status_code=400, detail="当前会话没有待人工审批的HITL信号")

    update = {
        "hitl_decision": req.decision,
        "hitl_comment": req.comment or "",
    }
    try:
        await graph.aupdate_state(config=config, values=update)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"决策状态写入失败: {str(e)}")

    try:
        from app.services.audit.signal_audit import update_audit_decision
        update_audit_decision(
            session_id=req.thread_id,
            hitl_decision=req.decision,
            hitl_comment=req.comment,
        )
    except Exception as audit_err:
        logger.warning(f"审计日志更新失败(非致命): {audit_err}")

    try:
        result = await graph.ainvoke(None, config=config)
    except Exception as e:
        logger.exception(f"决策后恢复图执行失败: {e}")
        raise HTTPException(status_code=500, detail=f"决策后恢复图执行失败: {str(e)}")

    if req.decision == "approve":
        return {
            "success": True,
            "thread_id": req.thread_id,
            "status": "approved",
            "msg": "人工放行，pollution信号已清除，任务继续执行",
            "result": result,
        }
    else:
        return {
            "success": True,
            "thread_id": req.thread_id,
            "status": "rejected",
            "msg": "人工拒绝，任务终止，进入memory_persist落盘",
            "result": result,
        }


# 12. 审计日志查询接口
@router.get("/hitl/signal/audit")
async def get_signal_audit_log(
    session_id: str = Query(..., min_length=1, max_length=255, description="会话ID"),
    limit: int = Query(default=20, ge=1, le=100, description="返回条数上限"),
):
    """
    查询会话的全部信号审计日志
    数据独立于LangGraph checkpoint，即使会话状态被清理，审计日志永久留存
    """
    try:
        from app.services.audit.signal_audit import query_audit_log
        records = query_audit_log(session_id=session_id, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"审计日志查询失败: {str(e)}")
    return {"success": True, "session_id": session_id, "records": records, "count": len(records)}