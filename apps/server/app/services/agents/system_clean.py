from __future__ import annotations

from typing import Any

from app.services.agents.base import SubAgentBase
from app.services.session_store import SessionStore


class SystemCleanAgent(SubAgentBase):
    name = "system_clean"
    description = "系统清理与优化：扫描临时文件、清理磁盘、优化系统性能"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["scan", "cleanup", "scan_and_cleanup"],
                "description": "清理动作：scan=仅扫描, cleanup=执行清理, scan_and_cleanup=扫描后清理",
            },
            "max_items": {
                "type": "integer",
                "description": "最大处理文件数，默认50",
            },
        },
    }
    required_keys = []

    async def run(self, args: dict[str, Any], session: SessionStore) -> dict[str, Any]:
        self.validate_args(args)
        action = args.get("action", "scan")
        max_items = args.get("max_items", 50)
        results: dict[str, Any] = {}
        lf_trace = args.get("_lf_trace")

        if action in ("scan", "scan_and_cleanup"):
            scan_result = await self.traced_tool_execute("temp:scan", {"max": max_items}, session, lf_trace)
            results["scan"] = scan_result
            session.set_global("last_temp_scan", scan_result)

        if action in ("cleanup", "scan_and_cleanup"):
            cleanup_result = await self.traced_tool_execute("disk:cleanup", {"max": max_items}, session, lf_trace)
            results["cleanup"] = cleanup_result
            session.set_global("last_cleanup_result", cleanup_result)

        return results