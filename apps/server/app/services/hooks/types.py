from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Awaitable


class HookLayer(Enum):
    """
    Pi Agent Hooks 四层生命周期:
    Layer1: Session会话层 — 会话启停/分叉/上下文压缩
    Layer2: Agent核心循环层 — turn/上下文组装/LLM前后/流式chunk
    Layer3: 工具执行管道层 — tool_call拦截/参数修改/权限校验/结果改写
    Layer4: Provider传输层 — LLM请求payload/response拦截/鉴权/代理
    """
    SESSION = 1
    AGENT = 2
    TOOL = 3
    PROVIDER = 4


class HookEvent(Enum):
    # Layer1: Session会话层
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    SESSION_COMPACT = "session_compact"
    SESSION_FORK = "session_fork"

    # Layer2: Agent核心循环层
    BEFORE_AGENT_START = "before_agent_start"
    AFTER_AGENT_END = "after_agent_end"
    TURN_START = "turn_start"
    TURN_END = "turn_end"
    CONTEXT_ASSEMBLE = "context_assemble"
    BEFORE_LLM_CALL = "before_llm_call"
    AFTER_LLM_CALL = "after_llm_call"
    MESSAGE_CHUNK = "message_chunk"
    QUERY_REWRITE = "query_rewrite"
    RETRIEVAL_START = "retrieval_start"
    RETRIEVAL_END = "retrieval_end"
    FUSION_COMPLETE = "fusion_complete"

    # Layer3: 工具执行管道层
    TOOL_CALL = "tool_call"
    BEFORE_TOOL_EXEC = "before_tool_exec"
    AFTER_TOOL_EXEC = "after_tool_exec"
    VALIDATION_GATE = "validation_gate"

    # Layer4: Provider传输层
    BEFORE_PROVIDER_REQUEST = "before_provider_request"
    AFTER_PROVIDER_RESPONSE = "after_provider_response"


class HookMode(Enum):
    MODIFY = "modify"
    OBSERVE = "observe"


HookCallback = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]