from __future__ import annotations

from app.services.hooks.plugins.base import (
    QueryRewriter,
    Retriever,
    FusionStrategy,
    DedupFilter,
    PromptBuilder,
    ResultValidator,
    RetrievedDoc,
    RewriteResult,
    FusionInput,
    ValidationResult,
    RewriteType,
    DocSource,
)
from app.services.hooks.plugins.intent.recognizer import IntentRecognizer, IntentResult, IntentType, ActionType
from app.services.hooks.plugins.intent.clarifier import IntentClarifier, ClarificationResult, ClarificationReason
from app.services.hooks.plugins.cache import QueryCache, DegradationChain
from app.services.hooks.plugins.registry import PluginRegistry

__all__ = [
    "QueryRewriter",
    "Retriever",
    "FusionStrategy",
    "DedupFilter",
    "PromptBuilder",
    "ResultValidator",
    "RetrievedDoc",
    "RewriteResult",
    "FusionInput",
    "ValidationResult",
    "RewriteType",
    "DocSource",
    "IntentRecognizer",
    "IntentResult",
    "IntentType",
    "ActionType",
    "IntentClarifier",
    "ClarificationResult",
    "ClarificationReason",
    "QueryCache",
    "DegradationChain",
    "PluginRegistry",
]