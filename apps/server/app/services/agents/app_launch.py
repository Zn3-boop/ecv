from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.services.agents.base import SubAgentBase
from app.services.session_store import SessionStore

SHELL_METACHARACTERS = set("|;&$`\\!><\n\r\t")
SHELL_METACHAR_PATTERN = re.compile(r'[|;&\$`\\!><\n\r\t]')
HIGH_RISK_EXTENSIONS = {".bat", ".cmd", ".sh", ".ps1", ".vbs", ".wsf", ".scr", ".com"}
APPROVED_EXE_NAMES = {
    "WeChat.exe", "QQ.exe", "chrome.exe", "msedge.exe", "Code.exe",
    "WINWORD.EXE", "EXCEL.EXE", "POWERPNT.EXE", "notepad.exe", "calc.exe",
    "mspaint.exe", "Photoshop.exe", "BaiduNetdisk.exe", "DingTalk.exe",
    "Feishu.exe", "wps.exe",# "Cursor.exe", "idea64.exe", "pycharm64.exe",
    "firefox.exe", "Telegram.exe", "Discord.exe", "steam.exe",
    "Spotify.exe", "ms-teams.exe", "OUTLOOK.EXE", "notepad++.exe",
    "sublime_text.exe", "git.exe", "mongod.exe", "mysqld.exe",
    "redis-server.exe", "etcd.exe", "Code.exe",
}


class AppLaunchInput(BaseModel):
    action: Literal["launch", "kill", "launch_and_kill"] = Field(
        ..., description="操作类型"
    )
    path: str = Field(default="", description="应用路径或名称")
    url: str = Field(default="", description="可选URL")
    kill_name: str = Field(default="", description="要结束的进程名")
    kill_pid: int = Field(default=0, description="要结束的进程PID")

    @field_validator("path")
    @classmethod
    def path_no_shell_metacharacters(cls, v: str) -> str:
        if not v:
            return v
        found = SHELL_METACHAR_PATTERN.findall(v)
        if found:
            raise ValueError(
                f"path 包含 shell 元字符 {found}，存在命令注入风险，已拦截"
            )
        return v

    @field_validator("url")
    @classmethod
    def url_no_shell_metacharacters(cls, v: str) -> str:
        if not v:
            return v
        found = SHELL_METACHAR_PATTERN.findall(v)
        if found:
            raise ValueError(
                f"url 包含 shell 元字符 {found}，存在命令注入风险，已拦截"
            )
        return v

    @field_validator("kill_name")
    @classmethod
    def kill_name_no_shell_metacharacters(cls, v: str) -> str:
        if not v:
            return v
        found = SHELL_METACHAR_PATTERN.findall(v)
        if found:
            raise ValueError(
                f"kill_name 包含 shell 元字符 {found}，存在命令注入风险，已拦截"
            )
        return v


def check_path_risk(path: str) -> dict[str, Any]:
    """
    Harness 风险分级 Checker（独立非LLM硬编码）。
    返回 {"risk_level": "low"|"medium"|"high", "approval_required": bool, "reason": str}
    """
    if not path:
        return {"risk_level": "low", "approval_required": False, "reason": "空路径"}

    import os
    _, ext = os.path.splitext(path)
    ext_lower = ext.lower()

    if ext_lower in HIGH_RISK_EXTENSIONS:
        return {
            "risk_level": "high",
            "approval_required": True,
            "reason": f"脚本/系统可执行文件后缀 {ext_lower}，属于高风险变更",
        }

    basename = os.path.basename(path)
    system_dirs = {"windows", "system32", "syswow64", "system"}
    dir_lower = os.path.dirname(path).lower()
    if any(sd in dir_lower for sd in system_dirs):
        return {
            "risk_level": "high",
            "approval_required": True,
            "reason": f"路径位于系统目录，属于高风险变更",
        }

    if basename in APPROVED_EXE_NAMES:
        return {
            "risk_level": "medium",
            "approval_required": False,
            "reason": "已知桌面应用白名单，中风险直接放行",
        }

    return {
        "risk_level": "medium",
        "approval_required": False,
        "reason": "普通桌面应用启动，中风险放行",
    }


class AppLaunchAgent(SubAgentBase):
    name = "app_launch"
    description = "应用启停管理：启动桌面应用程序、结束进程"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["launch", "kill", "launch_and_kill"],
                "description": "操作类型：launch=启动应用, kill=结束进程, launch_and_kill=启动新应用并结束旧进程",
            },
            "path": {
                "type": "string",
                "description": "应用路径或名称，如 WeChat.exe、notepad.exe",
            },
            "url": {
                "type": "string",
                "description": "可选URL，浏览器启动时打开的网址",
            },
            "kill_name": {
                "type": "string",
                "description": "要结束的进程名（kill动作时使用）",
            },
            "kill_pid": {
                "type": "integer",
                "description": "要结束的进程PID（kill动作时使用）",
            },
        },
    }
    required_keys = ["action"]

    def validate_args(self, args: dict[str, Any]) -> None:
        for k in self.required_keys:
            if k not in args:
                raise ValueError(f"子Agent[{self.name}]缺少必填参数: {k}")
        try:
            AppLaunchInput(**args)
        except Exception as e:
            raise ValueError(f"子Agent[{self.name}]参数校验失败: {e}") from e

    async def run(self, args: dict[str, Any], session: SessionStore) -> dict[str, Any]:
        self.validate_args(args)
        action = args["action"]
        results: dict[str, Any] = {}
        lf_trace = args.get("_lf_trace")

        if action in ("launch", "launch_and_kill"):
            launch_args: dict[str, Any] = {"path": args.get("path", "")}
            if args.get("url"):
                launch_args["url"] = args["url"]

            risk_info = check_path_risk(launch_args.get("path", ""))
            results["risk_info"] = risk_info
            if risk_info["approval_required"]:
                results["launch"] = {
                    "ok": False,
                    "error": f"高风险操作需人工审批: {risk_info['reason']}",
                    "approval_required": True,
                }
                return results

            launch_result = await self.traced_tool_execute("app:launch", launch_args, session, lf_trace)
            results["launch"] = launch_result
            session.set_global("last_launched_app", args.get("path", ""))

        if action in ("kill", "launch_and_kill"):
            kill_args: dict[str, Any] = {}
            if args.get("kill_pid"):
                kill_args["pid"] = args["kill_pid"]
            if args.get("kill_name"):
                kill_args["name"] = args["kill_name"]
            kill_result = await self.traced_tool_execute("process:kill", kill_args, session, lf_trace)
            results["kill"] = kill_result

        return results