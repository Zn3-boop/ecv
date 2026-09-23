from __future__ import annotations

from typing import Any

from app.services.agents.base import SubAgentBase
from app.services.session_store import SessionStore


class BrowserAgent(SubAgentBase):
    name = "browser"
    description = "浏览器与网络：浏览器搜索关键词、发送HTTP网络请求"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["search", "request"],
                "description": "动作：search=浏览器搜索, request=发送HTTP请求",
            },
            "query": {
                "type": "string",
                "description": "搜索关键词（search动作时使用）",
            },
            "url": {
                "type": "string",
                "description": "请求URL（request动作时使用）",
            },
            "method": {
                "type": "string",
                "description": "HTTP方法（request动作时使用），默认GET",
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
            if not query:
                return {"error": "search动作需要query参数"}
            search_result = await self.traced_tool_execute("browser:search", {"query": query}, session, lf_trace)
            results["search"] = search_result
            session.set_global("last_search_query", query)

        if action == "request":
            url = args.get("url", "")
            if not url:
                return {"error": "request动作需要url参数"}
            req_args: dict[str, Any] = {"url": url, "method": args.get("method", "GET")}
            req_result = await self.traced_tool_execute("network:request", req_args, session, lf_trace)
            results["request"] = req_result

        return results