from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_RATCHET_DIR = os.path.join(os.path.expanduser("~"), ".ecv_ratchet")


@dataclass
class RatchetStep:
    step_id: str
    name: str
    config_overrides: dict[str, Any] = field(default_factory=dict)
    baseline_pass_at_1: float = 0.0
    current_pass_at_1: float = 0.0
    status: str = "pending"
    regression_allowed: float = 0.02
    verified_at: float = 0.0


class RatchetLoop:
    """
    H9: Ratchet Loop — 逐步扩大能力，每步验证不退化才推进。

    流程:
    1. 建立基线 (baseline Pass@1)
    2. 逐个启用新能力 (Hook/插件/检索器)
    3. 每步跑回归集，若 Pass@1 不低于 baseline - regression_allowed → 推进
    4. 若退化 → 回滚该步，记录原因
    5. 最终输出安全能力边界
    """

    def __init__(self, ratchet_dir: str = ""):
        self.ratchet_dir = ratchet_dir or DEFAULT_RATCHET_DIR
        os.makedirs(self.ratchet_dir, exist_ok=True)
        self._state_file = os.path.join(self.ratchet_dir, "ratchet_state.json")
        self._steps: list[RatchetStep] = []
        self._baseline_pass_at_1: float = 0.0
        self._current_step_idx: int = 0

    def define_capability_ladder(self) -> list[RatchetStep]:
        """
        定义能力阶梯：从最保守到最激进
        """
        return [
            RatchetStep(
                step_id="ratchet_01",
                name="base_graph",
                config_overrides={"HOOKS_ENABLED": "false"},
            ),
            RatchetStep(
                step_id="ratchet_02",
                name="hooks_on",
                config_overrides={"HOOKS_ENABLED": "true", "HOOK_RAG_ENABLED": "false", "HOOK_WEB_ENABLED": "false"},
            ),
            RatchetStep(
                step_id="ratchet_03",
                name="rag_only",
                config_overrides={"HOOKS_ENABLED": "true", "HOOK_RAG_ENABLED": "true", "HOOK_WEB_ENABLED": "false"},
            ),
            RatchetStep(
                step_id="ratchet_04",
                name="rag_plus_web",
                config_overrides={"HOOKS_ENABLED": "true", "HOOK_RAG_ENABLED": "true", "HOOK_WEB_ENABLED": "true"},
            ),
            RatchetStep(
                step_id="ratchet_05",
                name="rerank_on",
                config_overrides={"HOOKS_ENABLED": "true", "HOOK_RAG_ENABLED": "true", "HOOK_WEB_ENABLED": "true", "HOOK_RERANK_ENABLED": "true"},
            ),
            RatchetStep(
                step_id="ratchet_06",
                name="llm_intent",
                config_overrides={"HOOKS_ENABLED": "true", "HOOK_RAG_ENABLED": "true", "HOOK_WEB_ENABLED": "true", "HOOK_INTENT_RECOGNIZER": "llm"},
            ),
            RatchetStep(
                step_id="ratchet_07",
                name="llm_rewrite",
                config_overrides={"HOOKS_ENABLED": "true", "HOOK_RAG_ENABLED": "true", "HOOK_WEB_ENABLED": "true", "HOOK_REWRITER": "llm"},
            ),
            RatchetStep(
                step_id="ratchet_08",
                name="full_power",
                config_overrides={"HOOKS_ENABLED": "true", "HOOK_RAG_ENABLED": "true", "HOOK_WEB_ENABLED": "true", "HOOK_RERANK_ENABLED": "true", "HOOK_INTENT_RECOGNIZER": "llm", "HOOK_REWRITER": "llm"},
            ),
        ]

    async def establish_baseline(
        self,
        eval_cases: list[Any],
    ) -> float:
        """
        第0步：跑最保守配置，建立基线 Pass@1
        """
        steps = self.define_capability_ladder()
        if not steps:
            return 0.0

        baseline_step = steps[0]
        logger.info(f"Ratchet: 建立基线 — {baseline_step.name}")

        original_env = self._apply_env(baseline_step.config_overrides)
        try:
            pass_at_1 = await self._measure_pass_at_1(eval_cases)
        finally:
            self._restore_env(original_env)

        baseline_step.baseline_pass_at_1 = pass_at_1
        baseline_step.current_pass_at_1 = pass_at_1
        baseline_step.status = "verified"
        baseline_step.verified_at = time.time()

        self._steps = [baseline_step]
        self._baseline_pass_at_1 = pass_at_1
        self._current_step_idx = 1

        logger.info(f"Ratchet: 基线 Pass@1 = {pass_at_1:.4f}")
        return pass_at_1

    async def advance(
        self,
        eval_cases: list[Any],
        max_steps: int = 0,
    ) -> dict[str, Any]:
        """
        逐步推进能力阶梯
        """
        steps = self.define_capability_ladder()
        if not self._steps:
            await self.establish_baseline(eval_cases)

        remaining = steps[self._current_step_idx:]
        if max_steps > 0:
            remaining = remaining[:max_steps]

        results: list[dict[str, Any]] = []

        for step in remaining:
            logger.info(f"Ratchet: 尝试推进 — {step.name} ({step.step_id})")

            original_env = self._apply_env(step.config_overrides)
            try:
                current_pass = await self._measure_pass_at_1(eval_cases)
            finally:
                self._restore_env(original_env)

            step.current_pass_at_1 = current_pass
            step.baseline_pass_at_1 = self._baseline_pass_at_1

            threshold = self._baseline_pass_at_1 - step.regression_allowed
            if current_pass >= threshold:
                step.status = "verified"
                step.verified_at = time.time()
                self._steps.append(step)
                self._current_step_idx += 1
                logger.info(
                    f"Ratchet: ✅ 推进成功 — {step.name} "
                    f"Pass@1={current_pass:.4f} >= threshold={threshold:.4f}"
                )
                results.append({
                    "step": step.name,
                    "status": "verified",
                    "pass_at_1": current_pass,
                    "threshold": threshold,
                })
            else:
                step.status = "regression"
                logger.warning(
                    f"Ratchet: ❌ 退化 — {step.name} "
                    f"Pass@1={current_pass:.4f} < threshold={threshold:.4f}, 回滚"
                )
                results.append({
                    "step": step.name,
                    "status": "regression",
                    "pass_at_1": current_pass,
                    "threshold": threshold,
                })
                break

        self._save_state()
        return {
            "baseline": self._baseline_pass_at_1,
            "verified_steps": [s.name for s in self._steps if s.status == "verified"],
            "regressed_step": next((s.name for s in self._steps if s.status == "regression"), None),
            "safe_capability_boundary": self._get_safe_boundary(),
            "details": results,
        }

    async def _measure_pass_at_1(self, eval_cases: list[Any]) -> float:
        passed = 0
        total = len(eval_cases)
        if total == 0:
            return 0.0
        for case in eval_cases:
            try:
                from app.services.llm.orchestrator import run_agent_workflow
                query = case.query if hasattr(case, "query") else str(case)
                result = await run_agent_workflow(message=query, mode="default")
                reply = result.get("reply", "")
                if reply and not result.get("used_fallback", False):
                    passed += 1
            except Exception:
                pass
        return passed / total

    def _apply_env(self, overrides: dict[str, Any]) -> dict[str, str | None]:
        original: dict[str, str | None] = {}
        for k, v in overrides.items():
            original[k] = os.environ.get(k)
            os.environ[k] = str(v)
        return original

    def _restore_env(self, original: dict[str, str | None]):
        for k, v in original.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _get_safe_boundary(self) -> dict[str, Any]:
        verified = [s for s in self._steps if s.status == "verified"]
        if not verified:
            return {"max_safe_config": {}, "pass_at_1": 0.0}
        last = verified[-1]
        return {
            "max_safe_config": last.config_overrides,
            "max_safe_name": last.name,
            "pass_at_1": last.current_pass_at_1,
            "steps_verified": len(verified),
        }

    def _save_state(self):
        state = {
            "baseline_pass_at_1": self._baseline_pass_at_1,
            "current_step_idx": self._current_step_idx,
            "steps": [
                {
                    "step_id": s.step_id,
                    "name": s.name,
                    "config_overrides": s.config_overrides,
                    "baseline_pass_at_1": s.baseline_pass_at_1,
                    "current_pass_at_1": s.current_pass_at_1,
                    "status": s.status,
                    "regression_allowed": s.regression_allowed,
                    "verified_at": s.verified_at,
                }
                for s in self._steps
            ],
        }
        with open(self._state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def load_state(self) -> dict[str, Any] | None:
        if not os.path.exists(self._state_file):
            return None
        with open(self._state_file, "r", encoding="utf-8") as f:
            return json.load(f)