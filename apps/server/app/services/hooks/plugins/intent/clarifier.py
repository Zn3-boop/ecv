from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.services.hooks.plugins.intent.recognizer import IntentResult

logger = logging.getLogger(__name__)


class ClarificationReason(str, Enum):
    MISSING_OBJECT = "MISSING_OBJECT"
    AMBIGUOUS_ENTITY = "AMBIGUOUS_ENTITY"
    WORKFLOW_AMBIGUITY = "WORKFLOW_AMBIGUITY"
    WRITE_NOT_CONFIRMED = "WRITE_NOT_CONFIRMED"
    PERMISSION_UNCLEAR = "PERMISSION_UNCLEAR"
    CONTEXT_REF_UNRESOLVED = "CONTEXT_REF_UNRESOLVED"


@dataclass
class ClarificationOption:
    id: str
    label: str
    recommended: bool = False
    impact: str = ""


@dataclass
class ClarificationResult:
    """
    B6: 意图澄清结果
    - need_clarification: 是否需要澄清
    - reason_code: 澄清原因码
    - question: 澄清问题文本
    - options: 结构化选项 (前端可渲染为按钮)
    """
    need_clarification: bool = False
    reason_code: ClarificationReason | None = None
    question: str = ""
    options: list[ClarificationOption] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "need_clarification": self.need_clarification,
            "reason_code": self.reason_code.value if self.reason_code else None,
            "question": self.question,
            "options": [
                {"id": o.id, "label": o.label, "recommended": o.recommended, "impact": o.impact}
                for o in self.options
            ],
        }


class IntentClarifier(abc.ABC):
    """
    B6: 意图澄清插件接口
    - 核心原则: 能不猜就不猜, 猜不准就反问
    - 改写是补全信息, 澄清是问用户
    """

    @abc.abstractmethod
    async def check_clarification(
        self,
        intent_result: IntentResult,
        context: dict[str, Any] | None = None,
    ) -> ClarificationResult:
        ...

    @property
    def name(self) -> str:
        return self.__class__.__name__


class RuleBasedClarifier(IntentClarifier):
    """
    规则意图澄清器: 基于6个必须反问场景做检查。
    """

    _AMBIGUOUS_ENTITIES: dict[str, list[str]] = {
        "苹果": ["手机品牌(Apple)", "水果"],
        "小米": ["手机品牌(Xiaomi)", "粮食"],
        "阿里": ["阿里巴巴集团", "阿里云"],
    }

    async def check_clarification(
        self,
        intent_result: IntentResult,
        context: dict[str, Any] | None = None,
    ) -> ClarificationResult:
        entities = intent_result.entities
        raw = intent_result.raw_query

        for entity_key, meanings in self._AMBIGUOUS_ENTITIES.items():
            if entity_key in raw and "object" not in entities:
                return ClarificationResult(
                    need_clarification=True,
                    reason_code=ClarificationReason.AMBIGUOUS_ENTITY,
                    question=f'"{entity_key}"是指什么？',
                    options=[
                        ClarificationOption(id=f"opt_{i}", label=m, recommended=(i == 0))
                        for i, m in enumerate(meanings)
                    ],
                )

        if intent_result.is_write_action():
            has_confirm = (context or {}).get("user_confirmed_write", False)
            if not has_confirm:
                action_label = {
                    "write": "写入", "create": "创建", "update": "更新", "delete": "删除",
                }.get(intent_result.action.value, "操作")
                return ClarificationResult(
                    need_clarification=True,
                    reason_code=ClarificationReason.WRITE_NOT_CONFIRMED,
                    question=f"即将执行{action_label}操作，确认继续？",
                    options=[
                        ClarificationOption(id="confirm", label="确认执行", recommended=False, impact="将执行数据变更操作"),
                        ClarificationOption(id="cancel", label="取消", recommended=True, impact="不执行任何操作"),
                    ],
                )

        monitor_keywords = ["监控", "盯", "monitor", "watch"]
        query_keywords = ["查询", "查看", "查一次", "query", "check"]
        has_monitor = any(kw in raw for kw in monitor_keywords)
        has_query = any(kw in raw for kw in query_keywords)
        if has_monitor and not has_query and intent_result.intent.value != "monitor":
            return ClarificationResult(
                need_clarification=True,
                reason_code=ClarificationReason.WORKFLOW_AMBIGUITY,
                question="是查询一次，还是创建持续监控？",
                options=[
                    ClarificationOption(id="query_once", label="查询一次", recommended=True, impact="读取当前数据，结束后不继续监控"),
                    ClarificationOption(id="create_monitor", label="持续监控", recommended=False, impact="创建持续任务，需确认对象、频率和通知方式"),
                ],
            )

        return ClarificationResult(need_clarification=False)


class LLMClarifier(IntentClarifier):
    """
    LLM意图澄清器: 用大模型判断是否需要澄清。
    降级: LLM失败时回退到RuleBasedClarifier。
    """

    _FALLBACK = RuleBasedClarifier()

    _PROMPT_TEMPLATE = """你是意图澄清判断器。判断用户输入是否需要澄清才能执行。

6个必须反问的场景:
1. 缺少必填对象
2. 实体无法唯一确定(歧义)
3. 工作流歧义(查询一次 vs 持续监控)
4. 写操作未确认
5. 权限边界不明
6. 上下文指代无法恢复

不触发澄清: 对象明确、只读查询、概念规则咨询、缺失字段不影响结果

用户输入: {raw_query}
意图: {intent}
动作: {action}
实体: {entities}

严格按JSON输出:
{{"need_clarification": false, "reason_code": null, "question": "", "options": []}}
或
{{"need_clarification": true, "reason_code": "AMBIGUOUS_ENTITY", "question": "苹果是指什么？", "options": [{{"id": "opt_0", "label": "手机品牌", "recommended": true, "impact": ""}}]}}"""

    async def check_clarification(
        self,
        intent_result: IntentResult,
        context: dict[str, Any] | None = None,
    ) -> ClarificationResult:
        try:
            from app.services.llm.client import llm_parse_with_retry
            from pydantic import BaseModel, Field
            from typing import Optional

            class ClarifyOutput(BaseModel):
                need_clarification: bool = Field(default=False)
                reason_code: Optional[str] = Field(default=None)
                question: str = Field(default="")
                options: list[dict[str, Any]] = Field(default_factory=list)

            prompt = self._PROMPT_TEMPLATE.format(
                raw_query=intent_result.raw_query,
                intent=intent_result.intent.value,
                action=intent_result.action.value,
                entities=intent_result.entities,
            )
            result, _ = await llm_parse_with_retry(prompt, ClarifyOutput, max_retry=1, timeout=6.0)

            if result and result.need_clarification:
                reason = None
                if result.reason_code:
                    try:
                        reason = ClarificationReason(result.reason_code)
                    except ValueError:
                        pass
                options = [
                    ClarificationOption(
                        id=o.get("id", f"opt_{i}"),
                        label=o.get("label", ""),
                        recommended=o.get("recommended", False),
                        impact=o.get("impact", ""),
                    )
                    for i, o in enumerate(result.options)
                ]
                return ClarificationResult(
                    need_clarification=True,
                    reason_code=reason,
                    question=result.question,
                    options=options,
                )
            return ClarificationResult(need_clarification=False)
        except Exception as e:
            logger.warning(f"LLM澄清失败，降级规则澄清: {e}")
            return await self._FALLBACK.check_clarification(intent_result, context)