from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_QUANT_DIR = os.path.join(os.path.expanduser("~"), ".ecv_quant_eval")


@dataclass
class QuantEvalCase:
    prompt: str
    expected_keywords: list[str] = field(default_factory=list)
    category: str = "general"
    max_tokens: int = 256


@dataclass
class QuantEvalResult:
    case: QuantEvalCase
    model: str = ""
    quantization: str = "fp16"
    output: str = ""
    keyword_hit_rate: float = 0.0
    output_length: int = 0
    latency_ms: float = 0.0
    error: str = ""


class QuantizationEvaluator:
    """
    量化质量衰减评测
    对比FP16/INT8/INT4在RAG/Function Calling/多语言三类任务上的质量衰减曲线
    """

    def __init__(self, quant_dir: str = ""):
        self.quant_dir = quant_dir or DEFAULT_QUANT_DIR
        os.makedirs(self.quant_dir, exist_ok=True)

    async def evaluate_model(
        self,
        cases: list[QuantEvalCase],
        model_name: str,
        base_url: str,
        quantization: str = "fp16",
        api_key: str = "",
    ) -> dict[str, Any]:
        """
        对指定模型+量化配置跑评测集
        """
        import httpx

        results: list[QuantEvalResult] = []
        headers = {
            "Content-Type": "application/json",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        for case in cases:
            start = time.monotonic()
            try:
                payload = {
                    "model": model_name,
                    "messages": [{"role": "user", "content": case.prompt}],
                    "max_tokens": case.max_tokens,
                    "temperature": 0.0,
                }
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(
                        f"{base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )

                if resp.status_code != 200:
                    results.append(QuantEvalResult(
                        case=case, model=model_name, quantization=quantization,
                        error=f"HTTP {resp.status_code}", latency_ms=(time.monotonic() - start) * 1000,
                    ))
                    continue

                data = resp.json()
                output = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                latency = (time.monotonic() - start) * 1000

                keyword_hit = 0.0
                if case.expected_keywords:
                    hits = sum(1 for kw in case.expected_keywords if kw.lower() in output.lower())
                    keyword_hit = hits / len(case.expected_keywords)

                results.append(QuantEvalResult(
                    case=case, model=model_name, quantization=quantization,
                    output=output, keyword_hit_rate=keyword_hit,
                    output_length=len(output), latency_ms=latency,
                ))
            except Exception as e:
                results.append(QuantEvalResult(
                    case=case, model=model_name, quantization=quantization,
                    error=str(e), latency_ms=(time.monotonic() - start) * 1000,
                ))

        summary = self._aggregate(results)
        self._save_results(model_name, quantization, summary, results)
        return summary

    async def compare_quantizations(
        self,
        cases: list[QuantEvalCase],
        configs: list[dict[str, str]],
    ) -> dict[str, Any]:
        """
        对比多个量化配置的质量衰减
        configs: [{"model_name": "...", "base_url": "...", "quantization": "fp16", "api_key": ""}, ...]
        """
        all_results: dict[str, dict[str, Any]] = {}

        for config in configs:
            quant = config.get("quantization", "unknown")
            logger.info(f"Evaluating {config.get('model_name', '')} ({quant})...")
            result = await self.evaluate_model(
                cases=cases,
                model_name=config["model_name"],
                base_url=config["base_url"],
                quantization=quant,
                api_key=config.get("api_key", ""),
            )
            all_results[quant] = result

        comparison = self._build_comparison(all_results)
        return comparison

    @staticmethod
    def _aggregate(results: list[QuantEvalResult]) -> dict[str, Any]:
        valid = [r for r in results if not r.error]
        if not valid:
            return {"total": len(results), "valid": 0, "errors": len(results)}

        avg_keyword_hit = sum(r.keyword_hit_rate for r in valid) / len(valid)
        avg_latency = sum(r.latency_ms for r in valid) / len(valid)
        avg_length = sum(r.output_length for r in valid) / len(valid)

        by_category: dict[str, list[QuantEvalResult]] = {}
        for r in valid:
            by_category.setdefault(r.case.category, []).append(r)

        category_metrics = {}
        for cat, cat_results in by_category.items():
            category_metrics[cat] = {
                "keyword_hit_rate": round(sum(r.keyword_hit_rate for r in cat_results) / len(cat_results), 4),
                "avg_latency_ms": round(sum(r.latency_ms for r in cat_results) / len(cat_results), 1),
                "count": len(cat_results),
            }

        return {
            "total": len(results),
            "valid": len(valid),
            "errors": len(results) - len(valid),
            "keyword_hit_rate": round(avg_keyword_hit, 4),
            "avg_latency_ms": round(avg_latency, 1),
            "avg_output_length": round(avg_length, 0),
            "by_category": category_metrics,
        }

    @staticmethod
    def _build_comparison(all_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
        comparison: dict[str, Any] = {"quantizations": list(all_results.keys())}

        quants = list(all_results.keys())
        if len(quants) >= 2:
            baseline_key = quants[0]
            baseline = all_results[baseline_key]
            baseline_hit = baseline.get("keyword_hit_rate", 0)

            degradation: dict[str, Any] = {}
            for qk in quants[1:]:
                q_hit = all_results[qk].get("keyword_hit_rate", 0)
                if baseline_hit > 0:
                    deg = (baseline_hit - q_hit) / baseline_hit
                else:
                    deg = 0.0
                degradation[qk] = {
                    "keyword_hit_rate": q_hit,
                    "degradation_ratio": round(deg, 4),
                    "quality_retention": round(1.0 - deg, 4),
                }

            comparison["baseline"] = baseline_key
            comparison["degradation_vs_baseline"] = degradation

        return comparison

    def _save_results(self, model: str, quant: str, summary: dict, results: list) -> None:
        ts = int(time.time())
        safe_model = model.replace("/", "_").replace("\\", "_")
        filepath = os.path.join(self.quant_dir, f"quant_{safe_model}_{quant}_{ts}.json")
        output = {
            "timestamp": ts,
            "model": model,
            "quantization": quant,
            "summary": summary,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"Quant eval results saved to {filepath}")