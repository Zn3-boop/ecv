from __future__ import annotations

from typing import Any

from app.services.agents.base import SubAgentBase
from app.services.session_store import SessionStore


class StoreAgent(SubAgentBase):
    name = "store"
    description = "应用商店操作：搜索、安装、卸载应用，列出已安装应用"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["search", "install", "uninstall", "list"],
                "description": "动作：search=搜索应用, install=安装, uninstall=卸载, list=列出已安装",
            },
            "package_id": {
                "type": "string",
                "description": "应用包ID（install/uninstall时使用）",
            },
            "app_name": {
                "type": "string",
                "description": "应用名称（install时可选）",
            },
            "query": {
                "type": "string",
                "description": "搜索关键词（search时使用）",
            },
        },
    }
    required_keys = ["action"]

    async def run(self, args: dict[str, Any], session: SessionStore) -> dict[str, Any]:
        self.validate_args(args)
        action = args["action"]
        results: dict[str, Any] = {}
        lf_trace = args.get("_lf_trace")

        if action == "search":
            query = args.get("query", "")
            search_result = await self.traced_tool_execute("store:search", {"query": query}, session, lf_trace)
            results["search"] = search_result

        elif action == "install":
            package_id = args.get("package_id", "")
            install_args: dict[str, Any] = {"package_id": package_id}
            if args.get("app_name"):
                install_args["app_name"] = args["app_name"]
            install_result = await self.traced_tool_execute("store:install", install_args, session, lf_trace)
            results["install"] = install_result

        elif action == "uninstall":
            package_id = args.get("package_id", "")
            uninstall_result = await self.traced_tool_execute("store:uninstall", {"package_id": package_id}, session, lf_trace)
            results["uninstall"] = uninstall_result

        elif action == "list":
            list_result = await self.traced_tool_execute("store:list", {}, session, lf_trace)
            results["list"] = list_result

        return results