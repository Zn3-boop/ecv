from __future__ import annotations

import os
import uuid
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.services.graph.graph import build_agent_graph, build_invoke_config
from app.services.graph.state import init_state
from app.services.graph.memory_store import get_governing_store

app = FastAPI(title="Desktop-Agent Graph API", version="1.0")
graph = build_agent_graph()


class GraphInvokeRequest(BaseModel):
    raw_query: str
    user_id: str
    session_id: Optional[str] = None


class GraphInvokeResponse(BaseModel):
    success: bool
    session_id: str
    trace_id: str
    result: dict[str, Any]
    is_interrupted: bool = False


class ApprovalSubmitRequest(BaseModel):
    thread_id: str
    approval_status: str
    comment: Optional[str] = None


class FullScanRequest(BaseModel):
    user_id: str


class SignalPatchRequest(BaseModel):
    status: str
    owner: str
    comment: str = ""


class SignalAckRequest(BaseModel):
    owner: str
    comment: Optional[str] = ""


class SignalResolveRequest(BaseModel):
    owner: str
    comment: Optional[str] = ""


class ForkCheckpointRequest(BaseModel):
    thread_id: str
    checkpoint_id: str
    new_session_id: Optional[str] = None


@app.post("/desktop/graph/invoke", response_model=GraphInvokeResponse)
async def graph_invoke(req: GraphInvokeRequest):
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
    result = await graph.ainvoke(input_state, config=cfg)
    interrupt_history = await graph.aget_state(config=cfg)
    is_interrupted = bool(interrupt_history.next)
    return GraphInvokeResponse(
        success=True,
        session_id=session_id,
        trace_id=trace_id,
        result=result,
        is_interrupted=is_interrupted,
    )


@app.post("/desktop/graph/approval")
async def submit_approval(req: ApprovalSubmitRequest):
    allowed_status = {"ok", "reject"}
    if req.approval_status not in allowed_status:
        raise HTTPException(status_code=400, detail=f"status必须为 {allowed_status}")
    config = {"configurable": {"thread_id": req.thread_id}}
    await graph.aupdate_state(config=config, values={"approval_status": req.approval_status})
    return {"success": True, "thread_id": req.thread_id, "approval_status": req.approval_status}


@app.get("/desktop/graph/checkpoints")
async def list_checkpoints(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    ckpt_list = []
    async for ckpt in graph.aget_state_history(config):
        ckpt_list.append({
            "checkpoint_id": ckpt.checkpoint_id,
            "metadata": ckpt.metadata,
            "next_nodes": list(ckpt.next),
        })
    return {"thread_id": thread_id, "checkpoints": ckpt_list}


@app.post("/desktop/graph/fork")
async def fork_checkpoint(req: ForkCheckpointRequest):
    old_config = {"configurable": {"thread_id": req.thread_id}}
    new_sid = req.new_session_id or str(uuid.uuid4())[:8]
    new_tid = f"{req.thread_id.split('_')[0]}_{new_sid}"
    new_config = {"configurable": {"thread_id": new_tid}}
    try:
        await graph.acopy_checkpoint(
            source_config=old_config,
            source_checkpoint_id=req.checkpoint_id,
            target_config=new_config,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"fork失败:{str(e)}")
    return {"success": True, "new_thread_id": new_tid, "source_checkpoint_id": req.checkpoint_id}


@app.post("/desktop/governor/full-scan")
async def governor_full_scan(req: FullScanRequest):
    store = get_governing_store()
    res = store.full_scan(user_id=req.user_id)
    return {"success": True, **res}


@app.get("/desktop/governor/signals")
async def list_signals(
    user_id: Optional[str] = None,
    signal_type: Optional[str] = None,
    status: Optional[str] = None,
):
    store = get_governing_store()
    sigs = store.list_signals(user_id=user_id)
    if signal_type:
        sigs = [s for s in sigs if s.get("signal_type") == signal_type]
    if status:
        sigs = [s for s in sigs if s.get("status") == status]
    return {"signals": sigs}


@app.patch("/desktop/governor/signals/{signal_id}")
async def patch_signal(signal_id: str, body: SignalPatchRequest):
    store = get_governing_store()
    ok = store.update_signal_status(
        sig_id=signal_id,
        status=body.status,
        owner=body.owner,
        comment=body.comment,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="signal不存在或者非法状态流转")
    sig = store.get_signal(signal_id)
    return {"success": ok, "signal_id": signal_id, "status": sig.get("status")}


@app.post("/desktop/governor/signals/{signal_id}/ack")
async def signal_ack(signal_id: str, body: SignalAckRequest):
    store = get_governing_store()
    ok = store.update_signal_status(
        sig_id=signal_id,
        status="processing",
        owner=body.owner,
        comment=body.comment,
    )
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="ack失败：信号不存在或非法状态流转，仅open状态可以ack",
        )
    sig = store.get_signal(signal_id)
    return {"success": ok, "signal_id": signal_id, "status": sig.get("status")}


@app.post("/desktop/governor/signals/{signal_id}/resolve")
async def signal_resolve(signal_id: str, body: SignalResolveRequest):
    store = get_governing_store()
    ok = store.update_signal_status(
        sig_id=signal_id,
        status="resolved",
        owner=body.owner,
        comment=body.comment,
    )
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="resolve失败：信号不存在或非法状态流转",
        )
    sig = store.get_signal(signal_id)
    return {"success": ok, "signal_id": signal_id, "status": sig.get("status")}


@app.post("/desktop/tool-search/query")
async def tool_search_query(query: str, top_k: int = 3):
    from app.services.graph.tool_search import tool_search_instance
    hits = tool_search_instance.search_tool(query, top_k=top_k)
    hit_names = [x.name for x in hits]
    loaded = tool_search_instance.get_current_loaded_schema()
    return {"success": True, "hit_list": hit_names, "loaded_schema": loaded}


@app.get("/metrics")
async def metrics_endpoint():
    env = os.getenv("GRAPH_ENV", "dev")
    if env == "prod":
        from prometheus_client import generate_latest
        return generate_latest()
    else:
        from app.services.graph.metrics import get_all_counters, get_all_histograms
        return {"counters": get_all_counters(), "histograms": get_all_histograms()}


@app.get("/health")
async def health():
    return {"ok": True}