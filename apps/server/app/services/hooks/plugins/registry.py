from __future__ import annotations

import logging
import os
from typing import Any

import yaml

from app.services.hooks.plugins.base import (
    QueryRewriter,
    Retriever,
    FusionStrategy,
    DedupFilter,
    PromptBuilder,
    ResultValidator,
)
from app.services.hooks.plugins.query_rewriter import RuleBasedRewriter, LLMRewriter, CompositeRewriter
from app.services.hooks.plugins.retrievers import (
    RAGRetriever,
    DuckDuckGoRetriever,
    TavilyRetriever,
    SerpAPIRetriever,
    CodeSearchRetriever,
)
from app.services.hooks.plugins.fusion import (
    SimpleConcatFusion,
    WeightedFusion,
    RerankFusion,
    SourcePriorityFusion,
)
from app.services.hooks.plugins.dedup import (
    SimHashDedupFilter,
    RuleBasedFilter,
    RecencyFilter,
    CompositeDedupFilter,
)
from app.services.hooks.plugins.prompt_builder import (
    DefaultPromptBuilder,
    ConcisePromptBuilder,
    StructuredPromptBuilder,
)
from app.services.hooks.plugins.validation import (
    MinResultValidator,
    ScoreThresholdValidator,
    CompositeValidator,
)
from app.services.hooks.plugins.intent.recognizer import (
    IntentRecognizer,
    RuleBasedIntentRecognizer,
    LLMIntentRecognizer,
)
from app.services.hooks.plugins.intent.clarifier import (
    IntentClarifier,
    RuleBasedClarifier,
    LLMClarifier,
)

logger = logging.getLogger(__name__)

_BUILTIN_REWRITERS: dict[str, type[QueryRewriter]] = {
    "rule": RuleBasedRewriter,
    "llm": LLMRewriter,
}

_BUILTIN_RETRIEVERS: dict[str, type[Retriever]] = {
    "rag": RAGRetriever,
    "duckduckgo": DuckDuckGoRetriever,
    "tavily": TavilyRetriever,
    "serpapi": SerpAPIRetriever,
    "code_search": CodeSearchRetriever,
}

_BUILTIN_FUSIONS: dict[str, type[FusionStrategy]] = {
    "simple_concat": SimpleConcatFusion,
    "weighted": WeightedFusion,
    "rerank": RerankFusion,
    "source_priority": SourcePriorityFusion,
}

_BUILTIN_DEDUPS: dict[str, type[DedupFilter]] = {
    "simhash": SimHashDedupFilter,
    "rule_filter": RuleBasedFilter,
    "recency": RecencyFilter,
}

_BUILTIN_PROMPT_BUILDERS: dict[str, type[PromptBuilder]] = {
    "default": DefaultPromptBuilder,
    "concise": ConcisePromptBuilder,
    "structured": StructuredPromptBuilder,
}

_BUILTIN_VALIDATORS: dict[str, type[ResultValidator]] = {
    "min_result": MinResultValidator,
    "score_threshold": ScoreThresholdValidator,
}

_BUILTIN_INTENT_RECOGNIZERS: dict[str, type[IntentRecognizer]] = {
    "rule": RuleBasedIntentRecognizer,
    "llm": LLMIntentRecognizer,
}

_BUILTIN_CLARIFIERS: dict[str, type[IntentClarifier]] = {
    "rule": RuleBasedClarifier,
    "llm": LLMClarifier,
}


class PluginRegistry:
    """
    插件注册中心: 管理所有可插拔组件的实例化和查找。
    - 内置插件通过名称查找
    - 自定义插件通过register方法注册
    - 配置驱动: 从YAML/环境变量加载插件选择
    """

    def __init__(self):
        self._rewriters: dict[str, type[QueryRewriter]] = dict(_BUILTIN_REWRITERS)
        self._retrievers: dict[str, type[Retriever]] = dict(_BUILTIN_RETRIEVERS)
        self._fusions: dict[str, type[FusionStrategy]] = dict(_BUILTIN_FUSIONS)
        self._dedups: dict[str, type[DedupFilter]] = dict(_BUILTIN_DEDUPS)
        self._prompt_builders: dict[str, type[PromptBuilder]] = dict(_BUILTIN_PROMPT_BUILDERS)
        self._validators: dict[str, type[ResultValidator]] = dict(_BUILTIN_VALIDATORS)

        self._custom_rewriters: dict[str, QueryRewriter] = {}
        self._custom_retrievers: dict[str, Retriever] = {}
        self._custom_fusions: dict[str, FusionStrategy] = {}
        self._custom_dedups: dict[str, DedupFilter] = {}
        self._custom_prompt_builders: dict[str, PromptBuilder] = {}
        self._custom_validators: dict[str, ResultValidator] = {}

        self._intent_recognizers: dict[str, type[IntentRecognizer]] = dict(_BUILTIN_INTENT_RECOGNIZERS)
        self._clarifiers: dict[str, type[IntentClarifier]] = dict(_BUILTIN_CLARIFIERS)
        self._custom_intent_recognizers: dict[str, IntentRecognizer] = {}
        self._custom_clarifiers: dict[str, IntentClarifier] = {}

    def register_rewriter(self, name: str, rewriter: QueryRewriter):
        self._custom_rewriters[name] = rewriter

    def register_retriever(self, name: str, retriever: Retriever):
        self._custom_retrievers[name] = retriever

    def register_fusion(self, name: str, fusion: FusionStrategy):
        self._custom_fusions[name] = fusion

    def register_dedup(self, name: str, dedup: DedupFilter):
        self._custom_dedups[name] = dedup

    def register_prompt_builder(self, name: str, builder: PromptBuilder):
        self._custom_prompt_builders[name] = builder

    def register_validator(self, name: str, validator: ResultValidator):
        self._custom_validators[name] = validator

    def register_intent_recognizer(self, name: str, recognizer: IntentRecognizer):
        self._custom_intent_recognizers[name] = recognizer

    def register_clarifier(self, name: str, clarifier: IntentClarifier):
        self._custom_clarifiers[name] = clarifier

    def get_rewriter(self, name: str, **kwargs: Any) -> QueryRewriter:
        if name in self._custom_rewriters:
            return self._custom_rewriters[name]
        if name in self._rewriters:
            return self._rewriters[name](**kwargs)
        raise ValueError(f"未知改写器: {name}, 可用: {list(self._rewriters.keys())}")

    def get_retriever(self, name: str, **kwargs: Any) -> Retriever:
        if name in self._custom_retrievers:
            return self._custom_retrievers[name]
        if name in self._retrievers:
            return self._retrievers[name](**kwargs)
        raise ValueError(f"未知检索器: {name}, 可用: {list(self._retrievers.keys())}")

    def get_fusion(self, name: str, **kwargs: Any) -> FusionStrategy:
        if name in self._custom_fusions:
            return self._custom_fusions[name]
        if name in self._fusions:
            return self._fusions[name](**kwargs)
        raise ValueError(f"未知融合策略: {name}, 可用: {list(self._fusions.keys())}")

    def get_dedup(self, name: str, **kwargs: Any) -> DedupFilter:
        if name in self._custom_dedups:
            return self._custom_dedups[name]
        if name in self._dedups:
            return self._dedups[name](**kwargs)
        raise ValueError(f"未知去重过滤器: {name}, 可用: {list(self._dedups.keys())}")

    def get_prompt_builder(self, name: str, **kwargs: Any) -> PromptBuilder:
        if name in self._custom_prompt_builders:
            return self._custom_prompt_builders[name]
        if name in self._prompt_builders:
            return self._prompt_builders[name](**kwargs)
        raise ValueError(f"未知Prompt构造器: {name}, 可用: {list(self._prompt_builders.keys())}")

    def get_validator(self, name: str, **kwargs: Any) -> ResultValidator:
        if name in self._custom_validators:
            return self._custom_validators[name]
        if name in self._validators:
            return self._validators[name](**kwargs)
        raise ValueError(f"未知验证器: {name}, 可用: {list(self._validators.keys())}")

    def get_intent_recognizer(self, name: str, **kwargs: Any) -> IntentRecognizer:
        if name in self._custom_intent_recognizers:
            return self._custom_intent_recognizers[name]
        if name in self._intent_recognizers:
            return self._intent_recognizers[name](**kwargs)
        raise ValueError(f"未知意图识别器: {name}, 可用: {list(self._intent_recognizers.keys())}")

    def get_clarifier(self, name: str, **kwargs: Any) -> IntentClarifier:
        if name in self._custom_clarifiers:
            return self._custom_clarifiers[name]
        if name in self._clarifiers:
            return self._clarifiers[name](**kwargs)
        raise ValueError(f"未知澄清器: {name}, 可用: {list(self._clarifiers.keys())}")

    def list_available(self) -> dict[str, list[str]]:
        return {
            "rewriters": list(self._rewriters.keys()) + list(self._custom_rewriters.keys()),
            "retrievers": list(self._retrievers.keys()) + list(self._custom_retrievers.keys()),
            "fusions": list(self._fusions.keys()) + list(self._custom_fusions.keys()),
            "dedups": list(self._dedups.keys()) + list(self._custom_dedups.keys()),
            "prompt_builders": list(self._prompt_builders.keys()) + list(self._custom_prompt_builders.keys()),
            "validators": list(self._validators.keys()) + list(self._custom_validators.keys()),
            "intent_recognizers": list(self._intent_recognizers.keys()) + list(self._custom_intent_recognizers.keys()),
            "clarifiers": list(self._clarifiers.keys()) + list(self._custom_clarifiers.keys()),
        }


def load_plugin_config() -> dict[str, Any]:
    """
    从YAML配置文件 + 环境变量加载插件配置。
    环境变量优先级高于YAML。
    """
    config: dict[str, Any] = {
        "rewriter": {"type": "rule"},
        "retrievers": [
            {"type": "rag", "top_k": 5},
            {"type": "duckduckgo"},
        ],
        "fusion": {"type": "weighted", "rag_weight": 0.7, "web_weight": 0.3},
        "dedup_filters": [
            {"type": "simhash"},
            {"type": "rule_filter"},
        ],
        "prompt_builder": {"type": "default"},
        "validators": [
            {"type": "min_result", "min_results": 1},
        ],
        "timeouts": {"rag": 5.0, "web": 8.0},
        "max_context_chars": 4000,
    }

    config_path = os.getenv("HOOKS_PLUGIN_CONFIG", "")
    if not config_path:
        candidates = [
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "config", "hooks_plugins.yaml"),
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "config", "hooks_plugins.yaml"),
        ]
        for c in candidates:
            if os.path.exists(c):
                config_path = c
                break

    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                file_config = yaml.safe_load(f) or {}
            _deep_merge(config, file_config)
        except Exception as e:
            logger.warning(f"加载插件配置失败 {config_path}: {e}")

    _apply_env_overrides(config)
    return config


def _deep_merge(base: dict, override: dict):
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _apply_env_overrides(config: dict[str, Any]):
    env_map = {
        "HOOK_REWRITER": ("rewriter", "type"),
        "HOOK_FUSION_STRATEGY": ("fusion", "type"),
        "HOOK_RAG_WEIGHT": ("fusion", "rag_weight"),
        "HOOK_WEB_WEIGHT": ("fusion", "web_weight"),
        "HOOK_RAG_TIMEOUT": ("timeouts", "rag"),
        "HOOK_WEB_TIMEOUT": ("timeouts", "web"),
        "HOOK_PROMPT_BUILDER": ("prompt_builder", "type"),
    }
    for env_key, (section, field) in env_map.items():
        val = os.getenv(env_key)
        if val is not None:
            if section not in config:
                config[section] = {}
            if field in ("rag_weight", "web_weight", "rag", "web"):
                val = float(val)
            config[section][field] = val


_registry_instance: PluginRegistry | None = None


def get_plugin_registry() -> PluginRegistry:
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = PluginRegistry()
    return _registry_instance