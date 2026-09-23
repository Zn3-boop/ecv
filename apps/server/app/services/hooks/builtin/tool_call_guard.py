from __future__ import annotations

import logging
import re
from typing import Any

from app.services.hooks.types import HookEvent, HookLayer, HookMode
from app.services.hooks.registry import HookSpec

logger = logging.getLogger(__name__)

_DANGEROUS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"rm\s+-rf", re.I),
    re.compile(r"del\s+/[sSqQ]", re.I),
    re.compile(r"format\s+[A-Za-z]:", re.I),
    re.compile(r"shutdown", re.I),
    re.compile(r"DROP\s+TABLE", re.I),
    re.compile(r"TRUNCATE\s+TABLE", re.I),
    re.compile(r"DELETE\s+FROM\s+\w+\s*;", re.I),
    re.compile(r">\s*/dev/sd", re.I),
    re.compile(r"chmod\s+-R\s+777", re.I),
    re.compile(r"curl\s+.*\|\s*sh", re.I),
    re.compile(r"wget\s+.*\|\s*bash", re.I),
]

_HIGH_RISK_TOOLS: set[str] = {
    "shell_exec",
    "file_delete",
    "db_execute",
    "system_command",
    "registry_edit",
}

_MEDIUM_RISK_TOOLS: set[str] = {
    "file_write",
    "file_update",
    "db_update",
    "config_update",
    "api_post",
}


class RiskLevel:
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    IRREVERSIBLE = "irreversible"


def assess_tool_risk(tool_name: str, tool_args: dict[str, Any]) -> tuple[str, str]:
    """
    H12: 风险分级
    - 低风险读取: 直接执行, 记录证据
    - 中风险变更: 按规则执行, 保留审计日志
    - 高风险动作: 必须人工审批
    - 不可逆动作: 默认拒绝, 用户显式授权
    """
    if tool_name in _HIGH_RISK_TOOLS:
        return RiskLevel.HIGH, f"高风险工具: {tool_name}"

    if tool_name in _MEDIUM_RISK_TOOLS:
        return RiskLevel.MEDIUM, f"中风险变更工具: {tool_name}"

    args_str = str(tool_args)
    for pattern in _DANGEROUS_PATTERNS:
        if pattern.search(args_str):
            return RiskLevel.IRREVERSIBLE, f"检测到危险指令: {pattern.pattern}"

    return RiskLevel.LOW, ""


async def tool_call_guard_hook(ctx: dict[str, Any]) -> dict[str, Any] | None:
    """
    H12/A7: 工具调用安全拦截 Hook
    - 拦截即将执行的工具调用
    - 检测危险指令
    - 高风险/不可逆动作需要用户确认
    - 返回 {block: True} 阻断执行
    """
    tool_name = ctx.get("tool_name", "")
    tool_args = ctx.get("tool_args", {})
    if not tool_name:
        return None

    risk_level, reason = assess_tool_risk(tool_name, tool_args)

    if risk_level == RiskLevel.IRREVERSIBLE:
        logger.warning(f"工具调用被阻断(不可逆): {tool_name} - {reason}")
        return {
            "block": True,
            "blocked_reason": reason,
            "risk_level": risk_level,
        }

    if risk_level == RiskLevel.HIGH:
        user_confirmed = ctx.get("user_confirmed", False)
        if not user_confirmed:
            logger.info(f"高风险工具需确认: {tool_name} - {reason}")
            return {
                "block": True,
                "blocked_reason": f"需要用户确认: {reason}",
                "risk_level": risk_level,
                "needs_confirmation": True,
                "confirmation_message": f"即将执行高风险操作: {tool_name}。{reason}。确认继续？",
            }

    if risk_level == RiskLevel.MEDIUM:
        logger.info(f"中风险工具调用(审计): {tool_name} - {reason}")
        return {
            "risk_level": risk_level,
            "audit_note": reason,
        }

    return {"risk_level": risk_level}


def create_tool_call_guard_hook(
    extra_dangerous_patterns: list[str] | None = None,
    extra_high_risk_tools: set[str] | None = None,
) -> HookSpec:
    global _DANGEROUS_PATTERNS, _HIGH_RISK_TOOLS
    if extra_dangerous_patterns:
        for p in extra_dangerous_patterns:
            _DANGEROUS_PATTERNS.append(re.compile(p, re.I))
    if extra_high_risk_tools:
        _HIGH_RISK_TOOLS.update(extra_high_risk_tools)

    return HookSpec(
        name="tool_call_guard",
        event=HookEvent.TOOL_CALL,
        callback=tool_call_guard_hook,
        mode=HookMode.MODIFY,
        layer=HookLayer.TOOL,
        priority=5,
    )