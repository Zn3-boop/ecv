from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CheckpointData:
    """
    H4: 检查点数据
    - 保存: 原始目标 / 当前计划 / 产出物 / 剩余待办
    - 支持中断恢复
    - 状态外置(存到文件/State), 不塞历史
    """
    task_id: str
    original_goal: str = ""
    current_plan: str = ""
    artifacts: list[str] = field(default_factory=list)
    remaining_steps: list[str] = field(default_factory=list)
    completed_steps: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    def __post_init__(self):
        now = time.time()
        if self.created_at == 0.0:
            self.created_at = now
        self.updated_at = now

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "original_goal": self.original_goal,
            "current_plan": self.current_plan,
            "artifacts": self.artifacts,
            "remaining_steps": self.remaining_steps,
            "completed_steps": self.completed_steps,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CheckpointData:
        return cls(
            task_id=d.get("task_id", ""),
            original_goal=d.get("original_goal", ""),
            current_plan=d.get("current_plan", ""),
            artifacts=d.get("artifacts", []),
            remaining_steps=d.get("remaining_steps", []),
            completed_steps=d.get("completed_steps", []),
            metadata=d.get("metadata", {}),
            created_at=d.get("created_at", 0.0),
            updated_at=d.get("updated_at", 0.0),
        )


class CheckpointStore:
    """
    H4: 检查点存储
    - 默认文件存储(JSON)
    - 可替换为SQLite/Redis等
    """

    def __init__(self, store_dir: str = ""):
        if not store_dir:
            store_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data", "checkpoints")
        self._store_dir = store_dir
        os.makedirs(store_dir, exist_ok=True)

    def save(self, checkpoint: CheckpointData):
        path = os.path.join(self._store_dir, f"{checkpoint.task_id}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(checkpoint.to_dict(), f, ensure_ascii=False, indent=2)
            logger.debug(f"Checkpoint saved: {checkpoint.task_id}")
        except Exception as e:
            logger.warning(f"Checkpoint save failed: {e}")

    def load(self, task_id: str) -> CheckpointData | None:
        path = os.path.join(self._store_dir, f"{task_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return CheckpointData.from_dict(data)
        except Exception as e:
            logger.warning(f"Checkpoint load failed: {e}")
            return None

    def delete(self, task_id: str):
        path = os.path.join(self._store_dir, f"{task_id}.json")
        if os.path.exists(path):
            os.remove(path)

    def list_all(self) -> list[str]:
        if not os.path.exists(self._store_dir):
            return []
        return [f[:-5] for f in os.listdir(self._store_dir) if f.endswith(".json")]


_store_instance: CheckpointStore | None = None


def get_checkpoint_store() -> CheckpointStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = CheckpointStore()
    return _store_instance


async def checkpoint_hook(ctx: dict[str, Any]) -> dict[str, Any] | None:
    """
    H4: Checkpoint Hook
    - 在 turn_end 事件触发
    - 保存当前任务状态
    - 在 before_agent_start 事件触发时, 尝试恢复
    """
    action = ctx.get("checkpoint_action", "")
    task_id = ctx.get("task_id", "")
    if not task_id:
        return None

    store = get_checkpoint_store()

    if action == "save":
        checkpoint = CheckpointData(
            task_id=task_id,
            original_goal=ctx.get("original_goal", ""),
            current_plan=ctx.get("current_plan", ""),
            artifacts=ctx.get("artifacts", []),
            remaining_steps=ctx.get("remaining_steps", []),
            completed_steps=ctx.get("completed_steps", []),
            metadata=ctx.get("checkpoint_metadata", {}),
        )
        store.save(checkpoint)
        return {"checkpoint_saved": True, "task_id": task_id}

    if action == "restore":
        checkpoint = store.load(task_id)
        if checkpoint:
            logger.info(f"Checkpoint restored: {task_id}, completed: {len(checkpoint.completed_steps)} steps")
            return {
                "checkpoint_restored": True,
                "checkpoint_data": checkpoint.to_dict(),
            }
        return {"checkpoint_restored": False}

    return None


def create_checkpoint_hook() -> HookSpec:
    from app.services.hooks.types import HookEvent, HookLayer, HookMode
    from app.services.hooks.registry import HookSpec

    return HookSpec(
        name="checkpoint",
        event=HookEvent.TURN_END,
        callback=checkpoint_hook,
        mode=HookMode.OBSERVE,
        layer=HookLayer.AGENT,
        priority=90,
    )