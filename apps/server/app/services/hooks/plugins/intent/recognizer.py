from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class IntentType(str, Enum):
    QUERY = "query"
    ANALYZE = "analyze"
    DIAGNOSE = "diagnose"
    GENERATE = "generate"
    MODIFY = "modify"
    MONITOR = "monitor"
    NAVIGATE = "navigate"
    UNKNOWN = "unknown"


class ActionType(str, Enum):
    READ = "read"
    WRITE = "write"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


@dataclass
class IntentResult:
    """
    B5: 意图识别 & 参数抽取结果
    - intent: 任务意图
    - action: 读写动作
    - entities: 抽取出的实体 (object, metric, time_range, scope, constraints)
    - confidence: 置信度
    - raw_query: 原始查询 (B2: 永不覆盖)
    """
    intent: IntentType = IntentType.UNKNOWN
    action: ActionType = ActionType.READ
    entities: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    raw_query: str = ""
    standalone_query: str = ""

    def is_write_action(self) -> bool:
        return self.action in (ActionType.WRITE, ActionType.CREATE, ActionType.UPDATE, ActionType.DELETE)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent.value,
            "action": self.action.value,
            "entities": self.entities,
            "confidence": self.confidence,
            "raw_query": self.raw_query,
            "standalone_query": self.standalone_query,
        }


class IntentRecognizer(abc.ABC):
    """
    B5: 意图识别插件接口
    - 把自然语言解析成结构化任务参数
    - 意图只描述用户想做什么, Skill路由交给下游 (B5坑)
    """

    @abc.abstractmethod
    async def recognize(self, raw_query: str, context: dict[str, Any] | None = None) -> IntentResult:
        ...

    @property
    def name(self) -> str:
        return self.__class__.__name__


class RuleBasedIntentRecognizer(IntentRecognizer):
    """
    规则意图识别器: 基于关键词匹配, 零LLM调用。
    """

    _INTENT_PATTERNS: dict[IntentType, list[str]] = {
        IntentType.QUERY: ["怎么", "如何", "什么是", "查询", "查找", "搜索", "how", "what", "where", "find", "search"],
        IntentType.ANALYZE: ["分析", "对比", "统计", "趋势", "analyze", "compare", "statistics", "trend"],
        IntentType.DIAGNOSE: ["诊断", "排查", "为什么", "报错", "失败", "diagnose", "debug", "why", "error"],
        IntentType.GENERATE: ["生成", "创建", "写", "帮我写", "generate", "create", "write", "make"],
        IntentType.MODIFY: ["修改", "更新", "替换", "改", "modify", "update", "change", "edit", "fix"],
        IntentType.MONITOR: ["监控", "盯", "跟踪", "关注", "monitor", "watch", "track", "observe"],
        IntentType.NAVIGATE: ["打开", "跳转", "去", "进入", "open", "go", "navigate", "visit"],
    }

    _WRITE_KEYWORDS = {"修改", "更新", "删除", "创建", "写", "添加", "移除", "update", "delete", "create", "write", "add", "remove", "modify"}

    _TIME_PATTERNS: list[tuple[str, str]] = [
        ("今天", "today"), ("昨天", "yesterday"), ("本周", "this_week"),
        ("上周", "last_week"), ("本月", "this_month"), ("上月", "last_month"),
        ("近7天", "last_7d"), ("近30天", "last_30d"), ("近90天", "last_90d"),
    ]

    async def recognize(self, raw_query: str, context: dict[str, Any] | None = None) -> IntentResult:
        query_lower = raw_query.lower()

        intent = IntentType.UNKNOWN
        max_matches = 0
        for intent_type, patterns in self._INTENT_PATTERNS.items():
            matches = sum(1 for p in patterns if p in query_lower)
            if matches > max_matches:
                max_matches = matches
                intent = intent_type

        action = ActionType.WRITE if any(kw in query_lower for kw in self._WRITE_KEYWORDS) else ActionType.READ

        entities: dict[str, Any] = {}
        for cn, en in self._TIME_PATTERNS:
            if cn in raw_query:
                entities["time_range"] = en
                break

        confidence = min(0.5 + max_matches * 0.15, 1.0) if max_matches > 0 else 0.3

        return IntentResult(
            intent=intent,
            action=action,
            entities=entities,
            confidence=confidence,
            raw_query=raw_query,
            standalone_query=raw_query,
        )


class LLMIntentRecognizer(IntentRecognizer):
    """
    LLM意图识别器: 用大模型做意图识别+实体抽取。
    降级: LLM失败时回退到RuleBasedIntentRecognizer。
    """

    _FALLBACK = RuleBasedIntentRecognizer()

    _PROMPT_TEMPLATE = """你是意图识别引擎。分析用户输入，输出结构化意图。

规则:
1. intent: query/analyze/diagnose/generate/modify/monitor/navigate/unknown
2. action: read/write/create/update/delete
3. entities: 抽取 object(操作对象), metric(指标), time_range(时间), scope(范围), constraints(约束)
4. 当前输入实体 > 历史上下文; 只补指代, 不能编造不存在的事实

用户输入: {raw_query}
上下文: {context}

严格按JSON输出:
{{"intent":"query","action":"read","entities":{{"object":"","metric":"","time_range":"","scope":"","constraints":[]}},"confidence":0.9}}"""

    async def recognize(self, raw_query: str, context: dict[str, Any] | None = None) -> IntentResult:
        try:
            from app.services.llm.client import llm_parse_with_retry
            from pydantic import BaseModel, Field
            from typing import Optional

            class IntentOutput(BaseModel):
                intent: str = Field(default="unknown")
                action: str = Field(default="read")
                entities: dict[str, Any] = Field(default_factory=dict)
                confidence: float = Field(default=0.7)

            ctx_str = str(context or "")[:200]
            prompt = self._PROMPT_TEMPLATE.format(raw_query=raw_query, context=ctx_str)
            result, _ = await llm_parse_with_retry(prompt, IntentOutput, max_retry=1, timeout=6.0)

            if result and result.intent != "unknown":
                try:
                    intent = IntentType(result.intent)
                except ValueError:
                    intent = IntentType.UNKNOWN
                try:
                    action = ActionType(result.action)
                except ValueError:
                    action = ActionType.READ

                return IntentResult(
                    intent=intent,
                    action=action,
                    entities=result.entities,
                    confidence=result.confidence,
                    raw_query=raw_query,
                    standalone_query=raw_query,
                )
        except Exception as e:
            logger.warning(f"LLM意图识别失败，降级规则识别: {e}")

        return await self._FALLBACK.recognize(raw_query, context)