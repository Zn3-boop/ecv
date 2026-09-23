from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class ProtocolType(str, Enum):
    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    INVESTIGATION = "investigation"


@dataclass
class ProtocolStep:
    name: str
    description: str
    is_mandatory: bool = True
    validation_command: str = ""
    rollback_command: str = ""


@dataclass
class ExecutionProtocol:
    """
    H3: 执行协议 — 定义Agent必须按哪种标准流程干活
    - Feature Loop: 确认验收标准→实现→单测→文档→校验→提交
    - Bugfix Loop: 复现+可复现测试→修复→回归→lint→提交
    - Refactor Loop: 锁基线可跑→只改结构不改行为→持续测试→提交
    - Investigation Loop: 列假设→实验取证→输出结论, 不直接改代码
    """
    protocol_type: ProtocolType
    steps: list[ProtocolStep] = field(default_factory=list)
    current_step: int = 0
    completed_steps: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_current_step(self) -> ProtocolStep | None:
        if 0 <= self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None

    def advance(self) -> bool:
        if self.current_step < len(self.steps) - 1:
            step = self.steps[self.current_step]
            self.completed_steps.append(step.name)
            self.current_step += 1
            return True
        return False

    def is_complete(self) -> bool:
        return self.current_step >= len(self.steps) - 1 and len(self.completed_steps) >= len(self.steps) - 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_type": self.protocol_type.value,
            "steps": [{"name": s.name, "description": s.description, "mandatory": s.is_mandatory} for s in self.steps],
            "current_step": self.current_step,
            "completed_steps": self.completed_steps,
        }


BUILTIN_PROTOCOLS: dict[ProtocolType, list[ProtocolStep]] = {
    ProtocolType.FEATURE: [
        ProtocolStep("confirm_acceptance", "确认验收标准", True),
        ProtocolStep("implement", "实现功能", True),
        ProtocolStep("unit_test", "编写单元测试", True, validation_command="pytest"),
        ProtocolStep("document", "编写文档", False),
        ProtocolStep("validate", "校验验收标准", True),
        ProtocolStep("submit", "提交代码等待评审", True, validation_command="git diff --stat"),
    ],
    ProtocolType.BUGFIX: [
        ProtocolStep("reproduce", "复现问题+编写可复现测试", True),
        ProtocolStep("fix", "修复问题", True),
        ProtocolStep("regression", "回归测试", True, validation_command="pytest"),
        ProtocolStep("lint", "代码风格检查", True, validation_command="ruff check"),
        ProtocolStep("submit", "提交修复", True),
    ],
    ProtocolType.REFACTOR: [
        ProtocolStep("lock_baseline", "锁基线: 确保当前可运行", True, validation_command="pytest"),
        ProtocolStep("refactor", "只改结构不改行为", True),
        ProtocolStep("continuous_test", "持续测试确认行为不变", True, validation_command="pytest"),
        ProtocolStep("submit", "提交重构", True),
    ],
    ProtocolType.INVESTIGATION: [
        ProtocolStep("list_hypotheses", "列出假设", True),
        ProtocolStep("experiment", "实验取证", True),
        ProtocolStep("conclude", "输出结论(不直接改代码)", True),
    ],
}


def get_protocol(protocol_type: ProtocolType | str) -> ExecutionProtocol:
    if isinstance(protocol_type, str):
        protocol_type = ProtocolType(protocol_type)
    steps = BUILTIN_PROTOCOLS.get(protocol_type, [])
    return ExecutionProtocol(protocol_type=protocol_type, steps=list(steps))


def register_protocol(protocol_type: ProtocolType, steps: list[ProtocolStep]):
    BUILTIN_PROTOCOLS[protocol_type] = steps


async def execution_protocol_hook(ctx: dict[str, Any]) -> dict[str, Any] | None:
    """
    H3: 执行协议 Hook
    - 在 before_agent_start 事件触发
    - 根据任务类型选择执行协议
    - 注入协议步骤到上下文
    """
    protocol_type_str = ctx.get("execution_protocol", "")
    if not protocol_type_str:
        return None

    try:
        protocol_type = ProtocolType(protocol_type_str)
    except ValueError:
        logger.warning(f"未知执行协议: {protocol_type_str}")
        return None

    protocol = get_protocol(protocol_type)
    current = protocol.get_current_step()

    logger.info(f"执行协议: {protocol_type.value}, 首步: {current.name if current else 'N/A'}")

    return {
        "execution_protocol_state": protocol.to_dict(),
        "current_step": {
            "name": current.name,
            "description": current.description,
            "is_mandatory": current.is_mandatory,
            "validation_command": current.validation_command,
        } if current else None,
    }


def create_execution_protocol_hook() -> HookSpec:
    from app.services.hooks.types import HookEvent, HookLayer, HookMode
    from app.services.hooks.registry import HookSpec

    return HookSpec(
        name="execution_protocol",
        event=HookEvent.BEFORE_AGENT_START,
        callback=execution_protocol_hook,
        mode=HookMode.MODIFY,
        layer=HookLayer.AGENT,
        priority=20,
    )