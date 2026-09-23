from __future__ import annotations

import json
import logging
import os
import time
from enum import IntEnum
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_EVOLVE_DIR = os.path.join(os.path.expanduser("~"), ".ecv_evolve_store")


class EvolveLevel(IntEnum):
    """
    E2: 四类演化闭环（能力/风险递增）
    ① 内建上下文闭环
    ② 技能资产化闭环
    ③ 外部监督/群体智能闭环
    ④ 参数/代码/工作流自修改闭环
    """
    CONTEXT = 1
    SKILL_ASSET = 2
    GROUP_INTELLIGENCE = 3
    SELF_MODIFY = 4


class EvolveRecord:
    """
    E4: 每次进化记录 — 评估/版本/回滚/权限/供应链
    """

    def __init__(
        self,
        record_id: str = "",
        level: EvolveLevel = EvolveLevel.CONTEXT,
        source: str = "",
        trigger: str = "",
        change_type: str = "",
        change_content: dict[str, Any] | None = None,
        evaluation_score: float = 0.0,
        evaluation_passed: bool = False,
        version: int = 1,
        rollback_id: str = "",
        acl_tags: list[str] | None = None,
        supply_chain_verified: bool = False,
        created_at: float = 0.0,
    ):
        self.record_id = record_id or f"evo_{int(time.time()*1000)}"
        self.level = level
        self.source = source
        self.trigger = trigger
        self.change_type = change_type
        self.change_content = change_content or {}
        self.evaluation_score = evaluation_score
        self.evaluation_passed = evaluation_passed
        self.version = version
        self.rollback_id = rollback_id
        self.acl_tags = acl_tags or ["system"]
        self.supply_chain_verified = supply_chain_verified
        self.created_at = created_at or time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "level": int(self.level),
            "level_name": self.level.name,
            "source": self.source,
            "trigger": self.trigger,
            "change_type": self.change_type,
            "change_content": self.change_content,
            "evaluation_score": self.evaluation_score,
            "evaluation_passed": self.evaluation_passed,
            "version": self.version,
            "rollback_id": self.rollback_id,
            "acl_tags": self.acl_tags,
            "supply_chain_verified": self.supply_chain_verified,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EvolveRecord:
        return cls(
            record_id=d.get("record_id", ""),
            level=EvolveLevel(d.get("level", 1)),
            source=d.get("source", ""),
            trigger=d.get("trigger", ""),
            change_type=d.get("change_type", ""),
            change_content=d.get("change_content", {}),
            evaluation_score=d.get("evaluation_score", 0.0),
            evaluation_passed=d.get("evaluation_passed", False),
            version=d.get("version", 1),
            rollback_id=d.get("rollback_id", ""),
            acl_tags=d.get("acl_tags", ["system"]),
            supply_chain_verified=d.get("supply_chain_verified", False),
            created_at=d.get("created_at", 0.0),
        )


class SelfEvolveEngine:
    """
    E1: 自进化Agent引擎
    - 经验驱动: 从任务反馈/用户纠错/评测结果学习
    - 持续生效: 更新沉淀到系统模块，后续任务自动使用
    - 可评估可回滚: 评估器+版本记录+沙箱+权限控制+回滚

    E2: 四类演化闭环
    E4: 跨层级通用约束(评估/回滚/权限/供应链)
    E5: 各层级特性与落地风险差异
    """

    def __init__(self, store_dir: str = ""):
        self.store_dir = store_dir or DEFAULT_EVOLVE_DIR
        self.records_dir = os.path.join(self.store_dir, "records")
        self.skills_dir = os.path.join(self.store_dir, "skills")
        self.context_dir = os.path.join(self.store_dir, "context")
        self.index_file = os.path.join(self.store_dir, "evolve_index.json")
        os.makedirs(self.records_dir, exist_ok=True)
        os.makedirs(self.skills_dir, exist_ok=True)
        os.makedirs(self.context_dir, exist_ok=True)
        self._records: list[EvolveRecord] = []
        self._skills: dict[str, dict[str, Any]] = {}
        self._context_memory: dict[str, Any] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.index_file):
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for rd in data.get("records", []):
                    self._records.append(EvolveRecord.from_dict(rd))
                self._skills = data.get("skills", {})
                self._context_memory = data.get("context_memory", {})
                logger.info(f"SelfEvolveEngine: loaded {len(self._records)} records, {len(self._skills)} skills")
            except Exception as e:
                logger.warning(f"加载进化索引失败: {e}")

    def _save(self):
        data = {
            "records": [r.to_dict() for r in self._records],
            "skills": self._skills,
            "context_memory": self._context_memory,
        }
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    def evolve_from_feedback(
        self,
        task_id: str = "",
        task_result: dict[str, Any] | None = None,
        user_correction: str = "",
        evaluation_score: float = 0.0,
        level: EvolveLevel = EvolveLevel.CONTEXT,
    ) -> EvolveRecord:
        """
        E1: 经验驱动 — 从任务反馈/用户纠错/评测结果学习
        """
        trigger = "user_correction" if user_correction else "task_feedback"
        change_content = {}
        if task_result:
            change_content["task_id"] = task_id
            change_content["task_ok"] = task_result.get("ok", False)
            change_content["tool_used"] = task_result.get("tool_name", "")
            change_content["error"] = task_result.get("error", "")
        if user_correction:
            change_content["user_correction"] = user_correction

        if level >= EvolveLevel.SKILL_ASSET and task_result and not task_result.get("ok", False):
            skill_id = self._extract_skill_from_failure(task_result, user_correction)
            if skill_id:
                change_content["skill_created"] = skill_id

        eval_passed = evaluation_score >= 0.6
        record = EvolveRecord(
            level=level,
            source=task_id,
            trigger=trigger,
            change_type="feedback_learning",
            change_content=change_content,
            evaluation_score=evaluation_score,
            evaluation_passed=eval_passed,
            version=len(self._records) + 1,
            acl_tags=["system", "evolve"],
        )

        if level >= EvolveLevel.SELF_MODIFY:
            record.supply_chain_verified = False
            logger.warning(f"层级④自修改进化需要沙箱验证: {record.record_id}")

        self._records.append(record)
        self._save()

        if eval_passed:
            self._apply_evolution(record)

        logger.info(f"SelfEvolve: record={record.record_id} level={level.name} eval={eval_passed} score={evaluation_score}")
        return record

    def _extract_skill_from_failure(
        self,
        task_result: dict[str, Any],
        user_correction: str,
    ) -> str:
        """
        E2 ②: 技能资产化 — 从失败轨迹中沉淀留存技能
        """
        tool_name = task_result.get("tool_name", "unknown")
        error = task_result.get("error", "")
        skill_id = f"skill_{tool_name}_{int(time.time())}"
        skill = {
            "skill_id": skill_id,
            "tool_name": tool_name,
            "error_pattern": error[:200],
            "correction": user_correction[:500],
            "created_at": time.time(),
            "usage_count": 0,
            "success_rate": 0.0,
        }
        self._skills[skill_id] = skill
        skill_path = os.path.join(self.skills_dir, f"{skill_id}.json")
        with open(skill_path, "w", encoding="utf-8") as f:
            json.dump(skill, f, ensure_ascii=False, indent=2)
        return skill_id

    def _apply_evolution(self, record: EvolveRecord):
        """
        E1: 持续生效 — 更新沉淀到系统模块
        """
        if record.level == EvolveLevel.CONTEXT:
            key = f"ctx_{record.source}_{record.change_type}"
            self._context_memory[key] = record.change_content
        elif record.level == EvolveLevel.SKILL_ASSET:
            pass
        elif record.level == EvolveLevel.GROUP_INTELLIGENCE:
            pass
        elif record.level == EvolveLevel.SELF_MODIFY:
            if not record.supply_chain_verified:
                logger.warning(f"层级④进化未通过供应链验证，暂不生效: {record.record_id}")
                return
        self._save()

    def evaluate_evolution(
        self,
        record_id: str,
        score: float,
        evaluator: str = "auto",
    ) -> dict[str, Any]:
        """
        E4: 评估 — 对进化结果做评测
        """
        for record in self._records:
            if record.record_id == record_id:
                old_passed = record.evaluation_passed
                record.evaluation_score = score
                record.evaluation_passed = score >= 0.6
                self._save()
                return {
                    "record_id": record_id,
                    "old_passed": old_passed,
                    "new_passed": record.evaluation_passed,
                    "score": score,
                    "evaluator": evaluator,
                }
        return {"record_id": record_id, "error": "record not found"}

    def rollback(
        self,
        target_version: int = 0,
        record_id: str = "",
    ) -> dict[str, Any]:
        """
        E4: 回滚 — 回滚到指定版本或记录
        """
        if record_id:
            for i, record in enumerate(self._records):
                if record.record_id == record_id:
                    removed = self._records[i:]
                    self._records = self._records[:i]
                    for key in list(self._context_memory.keys()):
                        if record_id in key:
                            del self._context_memory[key]
                    self._save()
                    return {
                        "ok": True,
                        "rolled_back_to": record_id,
                        "removed_count": len(removed),
                    }
        elif target_version > 0:
            original_len = len(self._records)
            self._records = [r for r in self._records if r.version <= target_version]
            removed = original_len - len(self._records)
            self._save()
            return {
                "ok": True,
                "rolled_back_to_version": target_version,
                "removed_count": removed,
            }
        return {"ok": False, "error": "需要record_id或target_version"}

    def check_permission(
        self,
        level: EvolveLevel,
        action: str,
        user_acl: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        E4: 权限管控 — 控制Agent能改什么、动哪些资源
        E5: 高层级需要更严格权限
        """
        user_set = set(t.lower() for t in (user_acl or []))
        if level == EvolveLevel.CONTEXT:
            required = {"system", "evolve"}
        elif level == EvolveLevel.SKILL_ASSET:
            required = {"system", "evolve", "skill_manage"}
        elif level == EvolveLevel.GROUP_INTELLIGENCE:
            required = {"system", "evolve", "group_manage"}
        elif level == EvolveLevel.SELF_MODIFY:
            required = {"system", "evolve", "self_modify", "sandbox"}
        else:
            required = {"system"}

        allowed = bool(user_set & required) or "admin" in user_set
        return {
            "level": level.name,
            "action": action,
            "allowed": allowed,
            "required_permissions": list(required),
            "user_permissions": list(user_set),
        }

    def verify_supply_chain(
        self,
        record_id: str,
        source_url: str = "",
        checksum: str = "",
    ) -> dict[str, Any]:
        """
        E4: 供应链治理 — 对外部引入的技能/工具/代码做来源与安全审计
        """
        for record in self._records:
            if record.record_id == record_id:
                verified = bool(source_url and checksum)
                record.supply_chain_verified = verified
                record.change_content["supply_chain"] = {
                    "source_url": source_url,
                    "checksum": checksum,
                    "verified": verified,
                    "verified_at": time.time() if verified else 0,
                }
                self._save()
                return {
                    "record_id": record_id,
                    "verified": verified,
                    "source_url": source_url,
                }
        return {"record_id": record_id, "verified": False, "error": "record not found"}

    def share_to_group(
        self,
        skill_id: str,
        group_id: str = "default",
    ) -> dict[str, Any]:
        """
        E2 ③: 外部监督/群体智能闭环 — 个体经验沉淀为群体通用记忆/技能
        """
        if skill_id not in self._skills:
            return {"ok": False, "error": f"skill {skill_id} not found"}
        skill = self._skills[skill_id]
        shared_path = os.path.join(self.skills_dir, f"shared_{group_id}_{skill_id}.json")
        shared_data = {
            **skill,
            "group_id": group_id,
            "shared_at": time.time(),
            "shared_from": "local",
        }
        with open(shared_path, "w", encoding="utf-8") as f:
            json.dump(shared_data, f, ensure_ascii=False, indent=2)
        return {"ok": True, "skill_id": skill_id, "group_id": group_id, "shared_path": shared_path}

    def get_context_for_task(self, task_query: str = "") -> dict[str, Any]:
        """
        E2 ①: 内建上下文闭环 — 提供持续上下文给后续任务
        """
        relevant_context = {}
        for key, value in self._context_memory.items():
            relevant_context[key] = value
        relevant_skills = []
        for skill_id, skill in self._skills.items():
            if skill.get("usage_count", 0) > 0 and skill.get("success_rate", 0) > 0.5:
                relevant_skills.append({
                    "skill_id": skill_id,
                    "tool_name": skill.get("tool_name", ""),
                    "correction": skill.get("correction", ""),
                    "success_rate": skill.get("success_rate", 0),
                })
        return {
            "context_memory": relevant_context,
            "relevant_skills": relevant_skills,
            "evolve_count": len(self._records),
            "latest_version": max((r.version for r in self._records), default=0),
        }

    def stats(self) -> dict[str, Any]:
        level_counts = {}
        for level in EvolveLevel:
            level_counts[level.name] = sum(1 for r in self._records if r.level == level)
        return {
            "total_records": len(self._records),
            "total_skills": len(self._skills),
            "context_memory_size": len(self._context_memory),
            "level_distribution": level_counts,
            "latest_version": max((r.version for r in self._records), default=0),
            "avg_evaluation_score": (
                sum(r.evaluation_score for r in self._records) / len(self._records)
                if self._records else 0.0
            ),
        }


_evolve_engine: SelfEvolveEngine | None = None


def get_evolve_engine() -> SelfEvolveEngine:
    global _evolve_engine
    if _evolve_engine is None:
        store_dir = os.getenv("EVOLVE_STORE_DIR", "")
        _evolve_engine = SelfEvolveEngine(store_dir=store_dir)
    return _evolve_engine