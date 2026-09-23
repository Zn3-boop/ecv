from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_REGRESSION_DIR = os.path.join(os.path.expanduser("~"), ".ecv_regression")


class RegressionSuite:
    """
    故障→修复→资产闭环:
    1. 收集失败用例 → 2. 修复后自动重跑 → 3. 通过则固化为回归集
    """

    def __init__(self, suite_dir: str = ""):
        self.suite_dir = suite_dir or DEFAULT_REGRESSION_DIR
        os.makedirs(self.suite_dir, exist_ok=True)
        self._suite_file = os.path.join(self.suite_dir, "regression_suite.json")
        self._results_file = os.path.join(self.suite_dir, "regression_results.json")
        self._cases: list[dict[str, Any]] = self._load_suite()

    def _load_suite(self) -> list[dict[str, Any]]:
        if os.path.exists(self._suite_file):
            try:
                with open(self._suite_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_suite(self):
        with open(self._suite_file, "w", encoding="utf-8") as f:
            json.dump(self._cases, f, ensure_ascii=False, indent=2)

    def add_failure_case(
        self,
        query: str,
        error: str,
        expected: str = "",
        category: str = "bug",
        trace_id: str = "",
    ) -> str:
        case_id = f"reg_{int(time.time()*1000)}"
        case = {
            "id": case_id,
            "query": query,
            "error": error,
            "expected": expected,
            "category": category,
            "trace_id": trace_id,
            "added_at": time.time(),
            "status": "open",
            "rerun_count": 0,
            "last_rerun_at": 0,
            "last_rerun_result": "",
        }
        self._cases.append(case)
        self._save_suite()
        logger.info(f"回归集: 添加失败用例 {case_id}: {query[:50]}")
        return case_id

    def mark_fixed(self, case_id: str, fix_description: str = "") -> bool:
        for case in self._cases:
            if case["id"] == case_id:
                case["status"] = "fixed"
                case["fix_description"] = fix_description
                case["fixed_at"] = time.time()
                self._save_suite()
                logger.info(f"回归集: 标记修复 {case_id}")
                return True
        return False

    def get_open_cases(self) -> list[dict[str, Any]]:
        return [c for c in self._cases if c["status"] == "open"]

    def get_fixed_cases(self) -> list[dict[str, Any]]:
        return [c for c in self._cases if c["status"] == "fixed"]

    async def rerun_fixed_cases(self) -> dict[str, Any]:
        """
        重跑所有标记为 fixed 的用例，验证修复是否真正生效。
        返回 {case_id: {"passed": bool, "reply": str, "error": str}}
        """
        fixed = self.get_fixed_cases()
        if not fixed:
            return {}

        results: dict[str, Any] = {}
        for case in fixed:
            try:
                from app.services.llm.orchestrator import run_agent_workflow
                workflow_result = await run_agent_workflow(
                    message=case["query"],
                    mode="default",
                )
                reply = workflow_result.get("reply", "")
                has_error = workflow_result.get("used_fallback", False)
                passed = bool(reply) and not has_error

                if case.get("expected"):
                    passed = passed and case["expected"].lower() in reply.lower()

                results[case["id"]] = {
                    "passed": passed,
                    "reply": reply[:200],
                    "error": "",
                }

                case["rerun_count"] += 1
                case["last_rerun_at"] = time.time()
                case["last_rerun_result"] = "pass" if passed else "fail"

                if passed:
                    case["status"] = "verified"
                    logger.info(f"回归集: 验证通过 {case['id']}")
                else:
                    case["status"] = "regression"
                    logger.warning(f"回归集: 回归失败 {case['id']}")

            except Exception as e:
                results[case["id"]] = {"passed": False, "reply": "", "error": str(e)}
                case["status"] = "regression"

        self._save_suite()

        summary = {
            "total": len(fixed),
            "verified": sum(1 for r in results.values() if r["passed"]),
            "regression": sum(1 for r in results.values() if not r["passed"]),
            "timestamp": time.time(),
        }
        self._save_rerun_results(summary, results)
        return results

    def _save_rerun_results(self, summary: dict[str, Any], details: dict[str, Any]):
        record = {"summary": summary, "details": details}
        with open(self._results_file, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

    async def run_lint_and_tests(self) -> dict[str, Any]:
        """
        运行 lint + 测试，收集交付证据。
        """
        results: dict[str, Any] = {"timestamp": time.time()}

        try:
            r = subprocess.run(
                ["python", "-m", "ruff", "check", "app/services/"],
                capture_output=True, text=True, timeout=60, cwd=os.getcwd(),
            )
            results["ruff"] = {
                "exit_code": r.returncode,
                "output": r.stdout[:2000] if r.returncode != 0 else "clean",
            }
        except Exception as e:
            results["ruff"] = {"error": str(e)}

        try:
            r = subprocess.run(
                ["python", "-m", "pytest", "app/services/graph/tests/", "app/services/hooks/", "-v", "--tb=short"],
                capture_output=True, text=True, timeout=120, cwd=os.getcwd(),
            )
            results["pytest"] = {
                "exit_code": r.returncode,
                "output": r.stdout[-2000:] if r.returncode != 0 else "all passed",
            }
        except Exception as e:
            results["pytest"] = {"error": str(e)}

        results["all_passed"] = (
            results.get("ruff", {}).get("exit_code", 1) == 0
            and results.get("pytest", {}).get("exit_code", 1) == 0
        )
        return results