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
    cannot_do: str = ""
    prerequisites: str = ""


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
                cannot_do="不能执行任何系统操作、不能读写文件、不能启动程序",
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "通知标题"},
                        "message": {"type": "string", "description": "通知内容"},
                    },
                },
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
                cannot_do="不能修改系统配置、不能执行命令",
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
                cannot_do="不能清理磁盘、不能删除文件",
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
                cannot_do="不能删除文件，只扫描不清理",
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
                cannot_do="不能清理系统保护目录、不能删除正在使用的文件",
                prerequisites="建议先执行 temp:scan 确认清理范围",
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
                cannot_do="不能格式化磁盘、不能删除系统文件",
                prerequisites="建议先执行 disk:list 确认磁盘状态",
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
                cannot_do="不能结束进程、不能修改进程优先级",
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
                cannot_do="不能结束进程、不能修改进程",
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
                cannot_do="不能结束系统关键进程(explorer/svchost等)、不能批量结束进程",
                prerequisites="建议先执行 process:list 确认目标PID",
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
                cannot_do="不能列出白名单外的目录、不能读取文件内容",
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
                cannot_do="不能搜索白名单外的目录、不能修改或删除文件",
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
                cannot_do="不能访问内网地址(127.0.0.1/localhost)、不能执行下载到系统目录外的路径",
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
                cannot_do="不能以管理员权限启动、不能启动系统关键服务",
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
                cannot_do="不能执行生成的代码、不能访问网络获取素材",
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
                cannot_do="不能获取搜索结果内容、不能自动点击搜索结果",
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
                cannot_do="不能执行需要管理员权限的操作、不能修改系统注册表",
            )
        )
        self.register(
            ToolDefinition(
                name="image:screenshot",
                description="截取屏幕或指定区域截图",
                category=ToolCategory.SYSTEM,
                command_type="read",
                risk="low",
                parameters={
                    "type": "object",
                    "properties": {
                        "region": {"type": "string", "description": "截图区域(空=全屏)"},
                        "output_path": {"type": "string", "description": "输出路径"},
                    },
                },
                examples=["截屏", "截图保存"],
                cannot_do="不能录制视频、不能持续监控屏幕",
            )
        )
        self.register(
            ToolDefinition(
                name="image:ocr",
                description="OCR文字识别",
                category=ToolCategory.SYSTEM,
                command_type="read",
                risk="low",
                parameters={
                    "type": "object",
                    "properties": {
                        "image_path": {"type": "string", "description": "图片路径"},
                        "lang": {"type": "string", "description": "语言", "default": "chi_sim+eng"},
                    },
                },
                examples=["识别图片文字", "OCR"],
                cannot_do="不能识别手写公式、不能处理PDF文档",
                prerequisites="需要先通过 image:screenshot 获取图片",
            )
        )
        self.register(
            ToolDefinition(
                name="image:understand",
                description="图像语义理解：用多模态大模型理解图片内容并回答关于图片的问题",
                category=ToolCategory.SYSTEM,
                command_type="read",
                risk="low",
                parameters={
                    "type": "object",
                    "properties": {
                        "image_path": {"type": "string", "description": "图片路径"},
                        "question": {"type": "string", "description": "对图片的问题或理解角度，如'这张图在做什么'"},
                    },
                    "required": ["image_path"],
                },
                examples=["理解这张图片", "描述一下这张图", "语义分析截图"],
                cannot_do="不能编辑/修改图片、不能识别视频内容",
                prerequisites="需要先通过 image:screenshot 获取图片；需要配置多模态模型 VISION_MODEL",
            )
        )
        self.register(
            ToolDefinition(
                name="algo:plot",
                description="数据可视化绘图（柱状图/折线图/饼图等）",
                category=ToolCategory.SYSTEM,
                command_type="write",
                risk="low",
                parameters={
                    "type": "object",
                    "properties": {
                        "data_path": {"type": "string", "description": "数据文件路径"},
                        "chart_type": {"type": "string", "description": "图表类型: bar/line/pie/scatter", "default": "bar"},
                        "title": {"type": "string", "description": "图表标题"},
                        "output_path": {"type": "string", "description": "输出图片路径"},
                    },
                },
                examples=["画柱状图", "数据可视化", "绘图"],
                cannot_do="不能处理实时数据流、不能生成交互式图表",
                prerequisites="需要数据文件已存在(data_path)",
            )
        )
        self.register(
            ToolDefinition(
                name="algo:calculate",
                description="数学表达式计算",
                category=ToolCategory.SYSTEM,
                command_type="read",
                risk="low",
                parameters={
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string", "description": "数学表达式"},
                    },
                },
                examples=["计算", "求值"],
                cannot_do="不能执行代码、不能访问文件系统",
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