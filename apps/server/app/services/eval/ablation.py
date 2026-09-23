from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_EVAL_DIR = os.path.join(os.path.expanduser("~"), ".ecv_eval_results")


@dataclass
class EvalCase:
    query: str
    expected_intent: str = ""
    expected_tools: list[str] = field(default_factory=list)
    expected_keywords: list[str] = field(default_factory=list)
    category: str = "general"


@dataclass
class EvalResult:
    case: EvalCase
    actual_intent: str = ""
    actual_tools: list[str] = field(default_factory=list)
    actual_reply: str = ""
    latency_ms: float = 0.0
    passed: bool = False
    scores: dict[str, float] = field(default_factory=dict)
    error: str = ""


@dataclass
class AblationConfig:
    name: str
    hooks_enabled: bool = True
    rag_enabled: bool = True
    web_enabled: bool = True
    fusion_strategy: str = "weighted"
    rerank_enabled: bool = False
    context_compress: bool = True
    cache_enabled: bool = True
    intent_recognizer: str = "rule"
    rewriter: str = "rule"


class AblationRunner:
    """
    A10: 消融实验框架
    - 逐个关闭组件，测量对 Pass@1 / 延迟 / 覆盖率 的影响
    - 结果持久化到 JSON，支持跨运行对比
    """

    def __init__(self, eval_dir: str = ""):
        self.eval_dir = eval_dir or DEFAULT_EVAL_DIR
        os.makedirs(self.eval_dir, exist_ok=True)

    def _standard_ablation_configs(self) -> list[AblationConfig]:
        return [
            AblationConfig(name="full", hooks_enabled=True, rag_enabled=True, web_enabled=True, context_compress=True, cache_enabled=True),
            AblationConfig(name="no_web", hooks_enabled=True, rag_enabled=True, web_enabled=False, context_compress=True, cache_enabled=True),
            AblationConfig(name="no_rag", hooks_enabled=True, rag_enabled=False, web_enabled=True, context_compress=True, cache_enabled=True),
            AblationConfig(name="no_hooks", hooks_enabled=False, rag_enabled=True, web_enabled=True, context_compress=False, cache_enabled=False),
            AblationConfig(name="no_compress", hooks_enabled=True, rag_enabled=True, web_enabled=True, context_compress=False, cache_enabled=True),
            AblationConfig(name="no_cache", hooks_enabled=True, rag_enabled=True, web_enabled=True, context_compress=True, cache_enabled=False),
            AblationConfig(name="rule_only", hooks_enabled=True, rag_enabled=True, web_enabled=True, intent_recognizer="rule", rewriter="rule"),
            AblationConfig(name="no_rerank", hooks_enabled=True, rag_enabled=True, web_enabled=True, rerank_enabled=False),
        ]

    async def run_single(
        self,
        case: EvalCase,
        config: AblationConfig,
    ) -> EvalResult:
        start = time.monotonic()
        result = EvalResult(case=case)

        env_overrides = {
            "HOOKS_ENABLED": str(config.hooks_enabled).lower(),
            "HOOK_RAG_ENABLED": str(config.rag_enabled).lower(),
            "HOOK_WEB_ENABLED": str(config.web_enabled).lower(),
            "HOOK_FUSION_STRATEGY": config.fusion_strategy,
            "HOOK_RERANK_ENABLED": str(config.rerank_enabled).lower(),
            "HOOK_CONTEXT_COMPRESS": str(config.context_compress).lower(),
            "HOOK_CACHE_ENABLED": str(config.cache_enabled).lower(),
            "HOOK_REWRITER": config.rewriter,
        }

        original_env: dict[str, str | None] = {}
        for k, v in env_overrides.items():
            original_env[k] = os.environ.get(k)
            os.environ[k] = v

        try:
            from app.services.llm.orchestrator import run_agent_workflow
            workflow_result = await run_agent_workflow(
                message=case.query,
                mode="default",
            )

            result.actual_reply = workflow_result.get("reply", "")
            result.actual_tools = [tc.get("function", {}).get("name", "") for tc in (workflow_result.get("tool_calls") or [])]

            if case.expected_intent:
                from app.services.intent_detector import detect_intent
                intent, conf = detect_intent(case.query)
                result.actual_intent = intent

            result.passed = self._check_pass(case, result)
            result.scores = self._compute_scores(case, result)

        except Exception as e:
            result.error = str(e)
            result.passed = False
        finally:
            for k, v in original_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        result.latency_ms = (time.monotonic() - start) * 1000
        return result

    def _check_pass(self, case: EvalCase, result: EvalResult) -> bool:
        if case.expected_intent and result.actual_intent != case.expected_intent:
            return False
        if case.expected_tools:
            for t in case.expected_tools:
                if t not in result.actual_tools:
                    return False
        if case.expected_keywords:
            reply_lower = result.actual_reply.lower()
            for kw in case.expected_keywords:
                if kw.lower() not in reply_lower:
                    return False
        if not result.actual_reply and not result.actual_tools:
            return False
        return True

    def _compute_scores(self, case: EvalCase, result: EvalResult) -> dict[str, float]:
        scores: dict[str, float] = {}
        if case.expected_keywords:
            reply_lower = result.actual_reply.lower()
            hit = sum(1 for kw in case.expected_keywords if kw.lower() in reply_lower)
            scores["keyword_recall"] = hit / len(case.expected_keywords)
        if case.expected_tools:
            hit = sum(1 for t in case.expected_tools if t in result.actual_tools)
            scores["tool_recall"] = hit / len(case.expected_tools)
        scores["has_reply"] = 1.0 if result.actual_reply else 0.0
        return scores

    async def run_ablation(
        self,
        cases: list[EvalCase],
        configs: list[AblationConfig] | None = None,
    ) -> dict[str, Any]:
        if configs is None:
            configs = self._standard_ablation_configs()

        all_results: dict[str, list[EvalResult]] = {}

        for config in configs:
            logger.info(f"=== 消融实验: {config.name} ===")
            config_results: list[EvalResult] = []
            for case in cases:
                r = await self.run_single(case, config)
                config_results.append(r)
            all_results[config.name] = config_results

        summary = self._summarize(all_results)
        self._save_results(summary)
        return summary

    def _summarize(self, all_results: dict[str, list[EvalResult]]) -> dict[str, Any]:
        summary: dict[str, Any] = {"timestamp": time.time(), "configs": {}}
        for name, results in all_results.items():
            total = len(results)
            passed = sum(1 for r in results if r.passed)
            avg_latency = sum(r.latency_ms for r in results) / max(total, 1)
            pass_at_1 = passed / max(total, 1)

            keyword_recalls = [r.scores.get("keyword_recall", 0) for r in results if "keyword_recall" in r.scores]
            tool_recalls = [r.scores.get("tool_recall", 0) for r in results if "tool_recall" in r.scores]

            summary["configs"][name] = {
                "total": total,
                "passed": passed,
                "pass_at_1": round(pass_at_1, 4),
                "avg_latency_ms": round(avg_latency, 1),
                "avg_keyword_recall": round(sum(keyword_recalls) / max(len(keyword_recalls), 1), 4) if keyword_recalls else None,
                "avg_tool_recall": round(sum(tool_recalls) / max(len(tool_recalls), 1), 4) if tool_recalls else None,
                "errors": sum(1 for r in results if r.error),
            }
        return summary

    def _save_results(self, summary: dict[str, Any]) -> str:
        ts = int(time.time())
        path = os.path.join(self.eval_dir, f"ablation_{ts}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        logger.info(f"消融实验结果已保存: {path}")
        return path

    def load_latest_results(self) -> dict[str, Any] | None:
        files = sorted(
            [f for f in os.listdir(self.eval_dir) if f.startswith("ablation_") and f.endswith(".json")],
            reverse=True,
        )
        if not files:
            return None
        with open(os.path.join(self.eval_dir, files[0]), "r", encoding="utf-8") as f:
            return json.load(f)