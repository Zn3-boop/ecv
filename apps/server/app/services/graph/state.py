"""
编码强制约束：

1. 所有节点禁止原地修改AgentState，必须 return {key:value} 返回全新字典；

2. RetryPolicy仅对 transient瞬时错误生效，security / business错误直接进入fallback；

3. D级模型推论不写入MemoryStore长期记忆，只允许存在会话state；

4. raw_query永远不可覆盖；改写全部生成 standalone_query / retrieval_queries；

5. 高危动作通过 interrupt_before=["approval_node"]拦截；

6. OTel GenAI Trace只存储参数hash，原始参数走opt-in独立存储。
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Literal, TypedDict

import os

from pydantic import BaseModel, Field

_logger = logging.getLogger(__name__)

ERROR_TYPE_TRANSIENT = "transient"
ERROR_TYPE_BUSINESS = "business"
ERROR_TYPE_SECURITY = "security"

class AgentState(TypedDict, total=False):
    # ========== 基础会话 & 可观测 ==========
    raw_query: str                      # 用户原始输入，【禁止改写】审计兜底
    standalone_query: str               # 指代消解、补全省略后的独立可理解查询
    retrieval_queries: list[str]        # 多条用于检索的改写query
    session_id: str
    trace_id: str
    user_id: str

    # ========== 快慢脑 ==========
    fast_brain_decision: str
    need_slow_brain: bool
    fast_brain_msg: str
    fast_brain_mode: str                          # fast_answer / review_by_slow / full_slow
    fast_brain_result: str                        # 快脑输出内容（Ollama决策摘要）
    fast_brain_confidence: float                  # logprobs置信度 [0,1]
    fast_brain_intent: str                        # 快脑识别的意图类型

    # ========== 意图 & 路由 & 澄清 ==========
    intent: str
    intent_confidence: float
    entities: dict[str, Any]
    route_target: str
    route_confidence: float
    agent_input: dict[str, Any]
    needs_clarification: bool
    clarification_message: str
    clarification_reason_code: str          # B6: 澄清原因码(AMBIGUOUS_ENTITY 等)
    clarification_options: list[dict[str, Any]]  # B6: 结构化选项按钮 [{id,label,recommended,impact}]

    # ========== 风险 & HITL审批 ==========
    risk_level: Literal["low", "medium", "high", "critical"]
    risk_reason: str
    approval_required: bool
    approval_status: Literal["pending", "ok", "reject"]

    # ========== 工具执行 & 错误 ==========
    tool_name: str
    tool_args: dict[str, Any]
    tool_result: dict[str, Any]
    last_error: str | None
    error_type: Literal["transient", "business", "security", ""]
    retry_count: int

    # ========== Governor治理循环 ==========
    governor_trigger: Literal["light", "full", ""]
    governor_scan_result: dict[str, Any]

    # ========== Supervisor诊断Agent ==========
    enable_auto_diagnose: bool
    diagnose_trigger: bool
    diagnose_trace_id: str | None
    correction_signal_id: str | None
    correction_signal_status: Literal["open", "processing", "resolved", ""]

    # ========== Tool-Search 工具延迟加载 ==========
    tool_search_query: str
    tool_search_hit_list: list[str]
    tool_loaded_schema: list[dict[str, Any]]

    # ========== 证据记忆层 ==========
    evidence: dict[str, Any]
    memory_summary: str

    # ========== M6 长会话瘦身（双层摘要：远期摘要 + 近期保留） ==========
    memory_recent_turns: list[dict[str, Any]]  # 近期轮次完整保留(空=未压缩)
    session_compacted: bool                    # 本turn是否触发会话压缩
    memory_token_reduction: float              # 会话压缩后 token 节省百分比

    # ========== 任务完成验证 (M15/H5/H13) ==========
    completion_evidence: dict[str, Any]  # 任务完成证据包：文件存在/文本非空/进程存活等
    task_verified: bool                  # 是否经过独立验证（工具ok ≠ 任务完成）

    # ========== 自校正循环 ==========
    correction_loop_count: int
    max_correction_loop: int
    correction_reason: str | None

    # ========== 多步规划执行 ==========
    is_multi_step: bool
    plan_steps: list[dict[str, Any]]
    current_step_index: int
    step_results: list[dict[str, Any]]

    # ========== RAG检索增强 ==========
    rag_query: str
    rag_rewrite_queries: list[str]
    rag_user_acl: list[str]
    rag_results: list[dict[str, Any]]
    rag_context: str
    rag_evidence_ids: list[str]
    rag_evidence_map: dict[str, Any]
    rag_contradiction: dict[str, Any]
    rag_should_refuse: bool

    # ========== 自进化Agent ==========
    enable_evolve_feedback: bool
    evolve_level: int
    evolve_record_id: str
    evolve_context: dict[str, Any]

    # ========== 智能代码搜索 ==========
    code_search_type: str
    code_search_results: list[dict[str, Any]]
    code_search_stats: dict[str, Any]

    # ========== Task-Planner 规划-分步执行-迭代交付 ==========
    task_plan_enabled: bool
    task_plan_items: list[dict[str, Any]]
    task_plan_current_idx: int
    task_plan_results: list[dict[str, Any]]
    task_plan_status: Literal["planning", "executing", "blocked", "completed", ""]
    current_sub_plan: dict[str, Any]
    history_log: list[str]
    agent_result: str
    all_finished: bool

    # ========== Governor + HITL 人工审批 ==========
    correction_signal: dict[str, Any]
    correction_loops: int
    needs_hitl: bool
    hitl_decision: str
    hitl_comment: str

def init_state(
    raw_query: str,
    session_id: str = "",
    trace_id: str = "",
    user_id: str = "",
) -> AgentState:
    sid = session_id or str(uuid.uuid4())[:8]
    tid = trace_id or str(uuid.uuid4())
    return AgentState(
        raw_query=raw_query,
        standalone_query="",
        retrieval_queries=[],
        session_id=sid,
        trace_id=tid,
        user_id=user_id,
        intent="",
        intent_confidence=0.0,
        entities={},
        route_target="",
        route_confidence=0.0,
        agent_input={},
        tool_name="",
        tool_args={},
        tool_result={},
        last_error=None,
        error_type="",
        approval_required=False,
        approval_status="pending",
        risk_level="low",
        risk_reason="",
        evidence={},
        memory_summary="",
        memory_recent_turns=[],
        session_compacted=False,
        memory_token_reduction=0.0,
        completion_evidence={},
        task_verified=False,
        needs_clarification=False,
        clarification_message="",
        clarification_reason_code="",
        clarification_options=[],
        retry_count=0,
        fast_brain_decision="",
        need_slow_brain=True,
        fast_brain_msg="",
        fast_brain_mode="",
        fast_brain_result="",
        fast_brain_confidence=0.0,
        fast_brain_intent="",
        governor_trigger="",
        governor_scan_result={},
        enable_auto_diagnose=False,
        diagnose_trigger=False,
        diagnose_trace_id=None,
        correction_signal_id=None,
        correction_signal_status="",
        tool_search_query="",
        tool_search_hit_list=[],
        tool_loaded_schema=[],
        correction_loop_count=0,
        max_correction_loop=int(os.getenv("MAX_CORRECTION_LOOP", "2")),
        correction_reason=None,
        is_multi_step=False,
        plan_steps=[],
        current_step_index=0,
        step_results=[],
        rag_query="",
        rag_rewrite_queries=[],
        rag_user_acl=[],
        rag_results=[],
        rag_context="",
        rag_evidence_ids=[],
        rag_evidence_map={},
        rag_contradiction={},
        rag_should_refuse=False,
        evolve_level=1,
        enable_evolve_feedback=os.getenv("ENABLE_EVOLVE_FEEDBACK", "false").lower() in ("true", "1", "yes"),
        evolve_record_id="",
        evolve_context={},
        code_search_type="",
        code_search_results=[],
        code_search_stats={},
        task_plan_enabled=os.getenv("TASK_PLAN_ENABLED", "true").lower() in ("true", "1", "yes"),
        task_plan_items=[],
        task_plan_current_idx=0,
        task_plan_results=[],
        task_plan_status="",
        current_sub_plan={},
        history_log=[],
        agent_result="",
        all_finished=False,
        correction_signal={},
        correction_loops=0,
        needs_hitl=False,
        hitl_decision="",
        hitl_comment="",
    )

class TaskPlanItemModel(BaseModel):
    step_index: int = Field(ge=0)
    description: str = Field(min_length=1, max_length=8000)
    status: Literal["pending", "done", "completed", "blocked", "failed"] = "pending"
    depends_on: list[int] = Field(default_factory=list)
    priority: Literal["P0", "P1", "P2"] = "P1"
    deliverable: str = Field(default="", max_length=8000)
    expected_output: str = Field(default="", max_length=8000)
    agent: str = ""
    action: str = ""
    blocked_reason: str = Field(default="", max_length=2000)
    deliverable_size: int | None = None
    retry_count: int = Field(default=0, ge=0)

class TaskPlanResultModel(BaseModel):
    step_index: int
    tool_name: str = ""
    tool_result: dict[str, Any] = Field(default_factory=dict)

_VALID_STATUSES = frozenset({"pending", "done", "completed", "blocked", "failed"})
_VALID_PRIORITIES = frozenset({"P0", "P1", "P2"})

def validate_task_plan_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    validated = []
    for item in items:
        if not isinstance(item, dict):
            _logger.warning(f"TaskPlanItem校验不通过: 非dict类型({type(item).__name__}), 跳过")
            continue
        try:
            m = TaskPlanItemModel.model_validate(item)
            d = m.model_dump()
            d["agent"] = ""
            d["action"] = ""
            validated.append(d)
        except Exception as e:
            raw_step = item.get("step_index", 0)
            safe_item = {
                "step_index": max(raw_step, 0) if isinstance(raw_step, int) else 0,
                "description": str(item.get("description", ""))[:8000] or "unknown",
                "status": item.get("status", "pending") if item.get("status") in _VALID_STATUSES else "pending",
                "depends_on": [d for d in item.get("depends_on", []) if isinstance(d, int)],
                "priority": item.get("priority", "P1") if item.get("priority") in _VALID_PRIORITIES else "P1",
                "deliverable": str(item.get("deliverable", ""))[:8000],
                "expected_output": str(item.get("expected_output", ""))[:8000],
                "agent": "",
                "action": "",
                "blocked_reason": str(item.get("blocked_reason", ""))[:2000],
                "retry_count": max(item.get("retry_count", 0), 0),
            }
            _logger.warning(
                f"TaskPlanItem校验不通过, error={e}, raw_keys={list(item.keys())}, safe_fixed_step={safe_item['step_index']}"
            )
            validated.append(safe_item)
    return validated

class AgentStateModel(BaseModel):
    """Pydantic校验模型，用于HTTP接口入参校验。"""
    model_config = {"extra": "allow"}

    raw_query: str = Field(..., description="原始用户输入，不可覆盖")
    standalone_query: str = ""
    retrieval_queries: list[str] = Field(default_factory=list)
    session_id: str = ""
    trace_id: str = ""
    user_id: str = ""