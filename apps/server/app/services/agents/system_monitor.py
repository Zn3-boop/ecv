from __future__ import annotations

from typing import Any

from app.services.agents.base import SubAgentBase
from app.services.session_store import SessionStore


class SystemMonitorAgent(SubAgentBase):
    name = "system_monitor"
    description = "系统监控与诊断：查看CPU、内存、磁盘、进程状态，分析系统性能问题"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["overview", "top_processes", "disk_info", "all"],
                "description": "监控动作：overview=系统概览, top_processes=高占用进程, disk_info=磁盘信息, all=全部",
            },
            "max_processes": {
                "type": "integer",
                "description": "返回进程数量，默认10",
            },
        },
    }
    required_keys = []

    async def run(self, args: dict[str, Any], session: SessionStore) -> dict[str, Any]:
        self.validate_args(args)
        action = args.get("action", "all")
        max_proc = args.get("max_processes", 10)
        results: dict[str, Any] = {}
        lf_trace = args.get("_lf_trace")

        if action in ("overview", "all"):
            sys_info = await self.traced_tool_execute("system:info", {}, session, lf_trace)
            results["system_info"] = sys_info
            session.set_global("last_system_info", sys_info)

        if action in ("top_processes", "all"):
            proc_info = await self.traced_tool_execute("process:top", {"max": max_proc}, session, lf_trace)
            results["top_processes"] = proc_info
            session.set_global("last_top_processes", proc_info)

        if action in ("disk_info", "all"):
            disk_info = await self.traced_tool_execute("disk:list", {}, session, lf_trace)
            results["disk_info"] = disk_info
            session.set_global("last_disk_info", disk_info)

        return results