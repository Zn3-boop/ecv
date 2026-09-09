from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ToolCategory(str, Enum):
    SYSTEM = "system"
    FILE = "file"
    PROCESS = "process"
    NETWORK = "network"
    DANGEROUS = "dangerous"
    NOTIFICATION = "notification"


@dataclass
class ToolDefinition:
    name: str
    description: str
    category: ToolCategory
    parameters: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    examples: list[str] = field(default_factory=list)
    command_type: str = "read"
    risk: str = "low"
    recommended: bool = False


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        self.register(
            ToolDefinition(
                name="notify",
                description="显示桌面通知，告知当前检测结果或执行状态",
                category=ToolCategory.NOTIFICATION,
                command_type="read",
                risk="low",
                examples=["提醒我当前 CPU 很高", "弹出通知"],
            )
        )
        self.register(
            ToolDefinition(
                name="system:info",
                description="获取系统基础信息，包括平台、CPU、内存、运行时长",
                category=ToolCategory.SYSTEM,
                command_type="read",
                risk="low",
                examples=["查看系统信息", "机器基础信息"],
            )
        )
        self.register(
            ToolDefinition(
                name="disk:list",
                description="获取磁盘分区、总容量、已用空间和剩余空间",
                category=ToolCategory.SYSTEM,
                command_type="read",
                risk="low",
                examples=["查看磁盘空间", "C盘空间还有多少"],
            )
        )
        self.register(
            ToolDefinition(
                name="temp:scan",
                description="扫描临时目录中的候选清理文件",
                category=ToolCategory.FILE,
                command_type="read",
                risk="low",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "要扫描的临时目录路径，可为空"},
                        "max": {"type": "integer", "description": "最多返回多少项"},
                    },
                },
                examples=["扫描临时文件", "看看 temp 目录里有什么"],
            )
        )
        self.register(
            ToolDefinition(
                name="temp:cleanup",
                description="清理临时目录中的 temp/tmp/log/bak 文件",
                category=ToolCategory.DANGEROUS,
                command_type="destructive",
                risk="high",
                requires_confirmation=True,
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "要清理的临时目录路径，可为空"},
                        "max": {"type": "integer", "description": "最多删除多少项"},
                    },
                },
                examples=["清理临时文件", "删除 temp 文件"],
            )
        )
        self.register(
            ToolDefinition(
                name="disk:cleanup",
                description="执行受控磁盘清理，当前以临时目录清理为主",
                category=ToolCategory.DANGEROUS,
                command_type="destructive",
                risk="high",
                requires_confirmation=True,
                parameters={
                    "type": "object",
                    "properties": {
                        "drive": {"type": "string", "description": "磁盘盘符，如 C"},
                        "path": {"type": "string", "description": "临时目录路径，可为空"},
                        "max": {"type": "integer", "description": "最多清理多少项"},
                    },
                },
                examples=["清理C盘", "清理磁盘空间"],
                recommended=True,
            )
        )
        self.register(
            ToolDefinition(
                name="process:list",
                description="获取当前进程列表",
                category=ToolCategory.PROCESS,
                command_type="read",
                risk="low",
                parameters={
                    "type": "object",
                    "properties": {
                        "max": {"type": "integer", "description": "最多返回多少个进程"},
                    },
                },
                examples=["查看进程", "列出进程"],
            )
        )
        self.register(
            ToolDefinition(
                name="process:top",
                description="按资源占用返回最值得关注的进程",
                category=ToolCategory.PROCESS,
                command_type="read",
                risk="low",
                parameters={
                    "type": "object",
                    "properties": {
                        "max": {"type": "integer", "description": "最多返回多少个进程"},
                    },
                },
                examples=["哪些进程最占内存", "高占用进程"],
                recommended=True,
            )
        )
        self.register(
            ToolDefinition(
                name="process:kill",
                description="结束指定 PID 的进程",
                category=ToolCategory.DANGEROUS,
                command_type="destructive",
                risk="high",
                requires_confirmation=True,
                parameters={
                    "type": "object",
                    "properties": {
                        "pid": {"type": "integer", "description": "要结束的进程 PID"},
                    },
                    "required": ["pid"],
                },
                examples=["关闭某个进程", "结束 chrome 进程"],
            )
        )
        self.register(
            ToolDefinition(
                name="file:list",
                description="列出白名单目录中的文件和文件夹",
                category=ToolCategory.FILE,
                command_type="read",
                risk="low",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "目录路径"},
                        "max": {"type": "integer", "description": "最多返回多少项"},
                    },
                    "required": ["path"],
                },
                examples=["查看下载目录", "列出桌面文件"],
            )
        )
        self.register(
            ToolDefinition(
                name="file:search",
                description="在白名单目录中按模式搜索文件",
                category=ToolCategory.FILE,
                command_type="read",
                risk="low",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "目录路径"},
                        "pattern": {"type": "string", "description": "文件名模式，如 *.tmp"},
                        "max": {"type": "integer", "description": "最多返回多少项"},
                    },
                    "required": ["path", "pattern"],
                },
                examples=["搜索 tmp 文件", "查找日志文件"],
            )
        )
        # 添加 network:request 工具
        self.register(
            ToolDefinition(
                name="network:request",
                description="发送 HTTP/HTTPS 网络请求，用于获取外部数据或下载文件",
                category=ToolCategory.NETWORK,
                command_type="network",
                risk="medium",
                requires_confirmation=True,
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "目标 URL"},
                        "method": {"type": "string", "description": "HTTP 方法，如 GET、POST", "enum": ["GET", "POST", "PUT", "DELETE"]},
                        "headers": {"type": "object", "description": "请求头"},
                        "body": {"type": "string", "description": "请求体"},
                        "timeout": {"type": "integer", "description": "超时时间（秒）"},
                    },
                    "required": ["url"],
                },
                examples=["下载文件", "获取网络数据", "发送 HTTP 请求"],
            )
        )
        # 添加 app:launch 工具
        self.register(
            ToolDefinition(
                name="app:launch",
                description="启动桌面应用程序，如微信、浏览器、记事本等",
                category=ToolCategory.SYSTEM,
                command_type="system",
                risk="low",
                requires_confirmation=False,
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "应用程序路径或名称，如 WeChat.exe、msedge.exe、notepad.exe"},
                    },
                    "required": ["path"],
                },
                examples=["打开微信", "启动浏览器", "打开记事本"],
            )
        )
        # 添加 content:generate 工具
        self.register(
            ToolDefinition(
                name="content:generate",
                description="生成文章、代码、HTML页面、Word文档、PPT大纲等内容",
                category=ToolCategory.SYSTEM,
                command_type="write",
                risk="low",
                requires_confirmation=False,
                parameters={
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "生成任务描述"},
                        "content_type": {"type": "string", "description": "内容类型：html/python/word/ppt/document/code", "enum": ["html", "python", "word", "ppt", "document", "code", "article"]},
                        "theme": {"type": "string", "description": "主题"},
                        "style": {"type": "string", "description": "风格"},
                        "length": {"type": "string", "description": "长度：短/中/长"},
                        "output_path": {"type": "string", "description": "输出路径（可选）"},
                    },
                    "required": ["task"],
                },
                examples=["生成登录页面HTML", "写一篇关于AI的文章", "创建Python脚本"],
            )
        )
        # 添加 browser:search（映射到 app:launch 带 url）
        self.register(
            ToolDefinition(
                name="browser:search",
                description="打开浏览器并搜索指定关键词",
                category=ToolCategory.NETWORK,
                command_type="write",
                risk="low",
                requires_confirmation=False,
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"},
                        "browser": {"type": "string", "description": "浏览器程序名", "default": "msedge.exe"},
                    },
                    "required": ["query"],
                },
                examples=["搜索AI应用", "查找计算机毕设资料"],
            )
        )
        # 添加 desktop:generic（通用桌面操作，由工作流执行器处理）
        self.register(
            ToolDefinition(
                name="desktop:generic",
                description="通用桌面操作，如保存文件、拖拽、点击等（由执行器解析）",
                category=ToolCategory.SYSTEM,
                command_type="write",
                risk="low",
                requires_confirmation=False,
                parameters={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "description": "操作描述"},
                    },
                },
                examples=["保存文件到指定目录", "拖拽文件到桌面"],
            )
        )

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list_tools(self, category: ToolCategory | None = None) -> list[ToolDefinition]:
        if category is None:
            return list(self._tools.values())
        return [tool for tool in self._tools.values() if tool.category == category]

    def match_tools(self, user_query: str, limit: int = 5) -> list[ToolDefinition]:
        query = user_query.lower().strip()
        if not query:
            return []

        scored: list[tuple[ToolDefinition, int]] = []
        for tool in self._tools.values():
            corpus = [tool.name, tool.description, *tool.examples]
            score = 0
            for item in corpus:
                normalized = item.lower()
                if query in normalized:
                    score += 4
                score += sum(1 for token in normalized.replace(":", " ").split() if token and token in query)
            if score > 0:
                scored.append((tool, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return [item[0] for item in scored[:limit]]


tool_registry = ToolRegistry()