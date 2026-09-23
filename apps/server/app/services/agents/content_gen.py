from __future__ import annotations

from typing import Any

from app.services.agents.base import SubAgentBase
from app.services.session_store import SessionStore


class ContentGenAgent(SubAgentBase):
    name = "content_gen"
    description = "内容生成与编码：生成文章、代码、文档、网页，或通过IDE创建项目"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["generate", "ide_create", "generate_and_open"],
                "description": "动作：generate=生成内容, ide_create=IDE创建项目, generate_and_open=生成后自动打开",
            },
            "task": {
                "type": "string",
                "description": "生成任务描述，如'登录页面'、'毕业论文'",
            },
            "content_type": {
                "type": "string",
                "enum": ["html", "python", "word", "document", "code", "article"],
                "description": "内容类型",
            },
            "theme": {"type": "string", "description": "主题"},
            "style": {"type": "string", "description": "风格"},
            "length": {"type": "string", "enum": ["短", "中", "长"], "description": "长度"},
            "ide": {
                "type": "string",
                "enum": ["vscode", "cursor"],
                "description": "IDE类型（ide_create动作时使用）",
            },
            "project_name": {
                "type": "string",
                "description": "项目名称（ide_create动作时使用）",
            },
        },
    }
    required_keys = ["action", "task"]

    async def run(self, args: dict[str, Any], session: SessionStore) -> dict[str, Any]:
        self.validate_args(args)
        action = args["action"]
        results: dict[str, Any] = {}
        lf_trace = args.get("_lf_trace")

        if action in ("generate", "generate_and_open"):
            gen_args: dict[str, Any] = {
                "task": args["task"],
                "content_type": args.get("content_type", "document"),
                "auto_open": action == "generate_and_open",
            }
            for key in ("theme", "style", "length", "output_path"):
                if args.get(key):
                    gen_args[key] = args[key]
            gen_result = await self.traced_tool_execute("content:generate", gen_args, session, lf_trace)
            results["generate"] = gen_result
            session.set_global("last_generated_content", gen_result)

        if action == "ide_create":
            ide_args: dict[str, Any] = {
                "ide": args.get("ide", "vscode"),
                "action": "create_project",
                "project_name": args.get("project_name", "untitled"),
                "files": [{"path": "index.html", "template": "modern_login"}],
            }
            ide_result = await self.traced_tool_execute("ide:launch", ide_args, session, lf_trace)
            results["ide_create"] = ide_result

        return results