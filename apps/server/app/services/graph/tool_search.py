from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

import yaml

logger = logging.getLogger(__name__)


TOOL_RULE_MAP: dict[str, list[str]] = {
    "启动": ["launch_app", "app:launch"],
    "打开": ["launch_app", "app:launch"],
    "关闭": ["kill_process", "process:kill"],
    "结束": ["kill_process", "process:kill"],
    "杀掉": ["kill_process", "process:kill"],
    "进程": ["query_process", "process:top", "process:list"],
    "监控": ["system:info", "process:top", "system_monitor"],
    "cpu": ["system:info", "process:top"],
    "内存": ["system:info", "process:top"],
    "磁盘": ["disk:list", "disk:cleanup"],
    "清理": ["temp:scan", "disk:cleanup"],
    "优化": ["temp:scan", "disk:cleanup"],
    "垃圾": ["temp:scan", "disk:cleanup"],
    "搜索": ["browser:search"],
    "查一下": ["browser:search"],
    "百度": ["browser:search"],
    "安装": ["store:install", "store:search"],
    "卸载": ["store:uninstall"],
    "应用商店": ["store:search", "store:list"],
    "生成": ["content:generate"],
    "写": ["content:generate"],
    "写代码": ["content:generate"],
    "写文章": ["content:generate"],
    "创建项目": ["ide:launch"],
    "请求": ["network:request"],
    "网络": ["network:request"],
    "截图": ["image:screenshot"],
    "截屏": ["image:screenshot"],
    "识别": ["image:ocr"],
    "OCR": ["image:ocr"],
    "文字识别": ["image:ocr"],
    "理解": ["image:understand"],
    "图片理解": ["image:understand"],
    "描述图片": ["image:understand"],
    "二维码": ["image:read_qr"],
    "扫码": ["image:read_qr"],
    "图片": ["image:resize", "image:convert", "image:filter", "image:analyze"],
    "滤镜": ["image:filter"],
    "灰度": ["image:filter"],
    "边缘检测": ["image:filter"],
    "图片对比": ["image:compare"],
    "计算": ["algo:calculate"],
    "加密": ["algo:encrypt"],
    "解密": ["algo:decrypt"],
    "压缩": ["algo:compress"],
    "解压": ["algo:decompress"],
    "哈希": ["algo:hash"],
    "画图": ["algo:plot"],
    "可视化": ["algo:plot"],
    "数据转换": ["algo:convert_data"],
    "UUID": ["algo:generate"],
    "密码": ["algo:generate"],
    "RAG": ["rag:index", "rag:query"],
    "知识库": ["rag:index", "rag:query", "rag:stats"],
    "检索": ["rag:query", "browser:search"],
    "建库": ["rag:index"],
    "索引": ["rag:index"],
    "向量": ["rag:index", "rag:query"],
    "进化": ["evolve:feedback", "evolve:evaluate", "evolve:stats"],
    "自进化": ["evolve:feedback", "evolve:evaluate", "evolve:stats"],
    "技能": ["evolve:feedback", "evolve:share"],
    "回滚": ["evolve:rollback"],
    "找代码": ["code:search", "code:glob", "code:grep"],
    "搜代码": ["code:search", "code:glob", "code:grep"],
    "找文件": ["code:glob"],
    "搜文件": ["code:glob"],
}

TOOL_ALIAS_MAP: dict[str, list[str]] = {
    "launch_app": ["app:launch", "启动应用", "打开应用"],
    "query_process": ["process:top", "process:list", "查询进程", "进程列表"],
    "kill_process": ["process:kill", "结束进程", "杀进程"],
    "system:info": ["系统信息", "系统概览", "system_monitor"],
    "disk:list": ["磁盘信息", "磁盘列表"],
    "disk:cleanup": ["磁盘清理", "清理磁盘"],
    "temp:scan": ["临时文件扫描", "扫描垃圾"],
    "browser:search": ["浏览器搜索", "网页搜索", "搜索网页"],
    "network:request": ["HTTP请求", "发送请求"],
    "store:search": ["搜索应用", "应用搜索"],
    "store:install": ["安装应用"],
    "store:uninstall": ["卸载应用"],
    "store:list": ["应用列表", "已安装应用"],
    "content:generate": ["内容生成", "生成内容", "写内容"],
    "ide:launch": ["IDE启动", "创建项目"],
    "image:screenshot": ["截图", "截屏", "屏幕截图"],
    "image:ocr": ["OCR", "文字识别", "图片识别"],
    "image:understand": ["图片理解", "语义理解", "描述图片", "看图"],
    "image:resize": ["调整大小", "缩放图片"],
    "image:crop": ["裁剪图片", "剪裁"],
    "image:convert": ["格式转换", "图片转换"],
    "image:filter": ["滤镜", "图片处理", "灰度", "模糊"],
    "image:analyze": ["图像分析", "图片分析"],
    "image:read_qr": ["二维码", "扫码"],
    "image:compare": ["图片对比", "图片比较"],
    "algo:calculate": ["计算", "数学计算", "求值"],
    "algo:encrypt": ["加密", "AES加密"],
    "algo:decrypt": ["解密", "AES解密"],
    "algo:compress": ["压缩", "打包"],
    "algo:decompress": ["解压", "解压缩"],
    "algo:convert_data": ["数据转换", "格式转换"],
    "algo:generate": ["生成UUID", "生成密码", "随机生成"],
    "algo:hash": ["哈希", "摘要", "SHA"],
    "algo:plot": ["画图", "可视化", "图表"],
    "rag:index": ["RAG建库", "索引文档", "知识库入库"],
    "rag:query": ["RAG检索", "知识库查询", "语义搜索"],
    "rag:delete": ["RAG删除", "知识库删除"],
    "rag:stats": ["RAG统计", "知识库统计"],
    "evolve:feedback": ["自进化反馈", "经验学习", "技能沉淀"],
    "evolve:evaluate": ["进化评估", "评估进化结果"],
    "evolve:rollback": ["进化回滚", "版本回退"],
    "evolve:share": ["技能共享", "群体共享"],
    "evolve:stats": ["进化统计", "自进化统计"],
    "code:search": ["代码搜索", "智能搜索"],
    "code:glob": ["文件匹配", "Glob搜索"],
    "code:grep": ["内容搜索", "Grep搜索"],
}


@dataclass
class ToolDef:
    name: str
    description: str
    input_schema: dict[str, Any]
    alwaysLoad: bool = False
    defer_loading: bool = False


def _load_tool_defs_from_yaml() -> list[ToolDef]:
    cfg_path = os.getenv("TOOL_DEF_CONFIG_PATH", "config/tools.yaml")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            tool_list_raw = data.get("tool_list", [])
            result = []
            for t in tool_list_raw:
                result.append(ToolDef(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    input_schema=t.get("input_schema", {}),
                    alwaysLoad=t.get("alwaysLoad", False),
                    defer_loading=t.get("defer_loading", False),
                ))
            if result:
                return result
        except Exception as e:
            logger.warning(f"加载工具配置失败 {cfg_path}: {e}，使用默认值")
    return _default_tool_list()


def _default_tool_list() -> list[ToolDef]:
    return [
        ToolDef(
            name="launch_app",
            description="启动桌面应用，传入exe路径",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            alwaysLoad=True,
        ),
        ToolDef(
            name="query_process",
            description="查询系统进程列表",
            input_schema={"type": "object"},
            alwaysLoad=True,
        ),
        ToolDef(
            name="kill_process",
            description="结束指定进程",
            input_schema={"type": "object", "properties": {"name": {"type": "string"}}},
            alwaysLoad=True,
        ),
        ToolDef(
            name="system:info",
            description="获取系统概览信息，CPU、内存、磁盘等",
            input_schema={"type": "object"},
            defer_loading=True,
        ),
        ToolDef(
            name="process:top",
            description="获取高占用进程列表",
            input_schema={"type": "object", "properties": {"max": {"type": "integer"}}},
            defer_loading=True,
        ),
        ToolDef(
            name="disk:list",
            description="获取磁盘信息列表",
            input_schema={"type": "object"},
            defer_loading=True,
        ),
        ToolDef(
            name="disk:cleanup",
            description="执行磁盘清理",
            input_schema={"type": "object", "properties": {"max": {"type": "integer"}}},
            defer_loading=True,
        ),
        ToolDef(
            name="temp:scan",
            description="扫描临时文件和垃圾文件",
            input_schema={"type": "object", "properties": {"max": {"type": "integer"}}},
            defer_loading=True,
        ),
        ToolDef(
            name="browser:search",
            description="浏览器搜索关键词",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            defer_loading=True,
        ),
        ToolDef(
            name="network:request",
            description="发送HTTP网络请求",
            input_schema={"type": "object", "properties": {"url": {"type": "string"}, "method": {"type": "string"}}},
            defer_loading=True,
        ),
        ToolDef(
            name="store:search",
            description="搜索应用商店中的应用",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            defer_loading=True,
        ),
        ToolDef(
            name="store:install",
            description="安装应用商店中的应用",
            input_schema={"type": "object", "properties": {"package_id": {"type": "string"}}},
            defer_loading=True,
        ),
        ToolDef(
            name="store:uninstall",
            description="卸载应用",
            input_schema={"type": "object", "properties": {"package_id": {"type": "string"}}},
            defer_loading=True,
        ),
        ToolDef(
            name="store:list",
            description="列出已安装应用",
            input_schema={"type": "object"},
            defer_loading=True,
        ),
        ToolDef(
            name="content:generate",
            description="生成文章、代码、文档等内容",
            input_schema={"type": "object", "properties": {"task": {"type": "string"}, "content_type": {"type": "string"}}},
            defer_loading=True,
        ),
        ToolDef(
            name="ide:launch",
            description="通过IDE创建项目",
            input_schema={"type": "object", "properties": {"ide": {"type": "string"}, "project_name": {"type": "string"}}},
            defer_loading=True,
        ),
    ]


class ToolSearch:
    """
    Tool-Search 工具延迟加载：
    - alwaysLoad=True：高频工具，启动直接加载
    - defer_loading=True：长尾工具，按需检索加载
    防止工具数量膨胀时大量 schema 占满 LLM 上下文窗口。

    风险提示：
    - 检索召回不准会导致需要的高危工具无法加载；高频工具必须设置 alwaysLoad=True
    - 检索工具本身不能设置 defer_loading=True，否则模型无法发起检索
    """

    def __init__(self, tool_list: list[ToolDef]):
        self.all_tools: list[ToolDef] = tool_list
        self.loaded: list[ToolDef] = [t for t in tool_list if t.alwaysLoad]
        for t in self.all_tools:
            if t.defer_loading and "search" in t.name.lower():
                logger.warning(
                    f"ToolSearch风险: 检索工具 '{t.name}' 设置了 defer_loading=True，"
                    f"模型将无法发起检索，已强制修正为 alwaysLoad=True"
                )
                t.defer_loading = False
                t.alwaysLoad = True
                if t not in self.loaded:
                    self.loaded.append(t)

    def search_tool(self, query: str, top_k: int = 3) -> list[ToolDef]:
        if not query or not query.strip():
            logger.debug("Tool-Search: 空query返回空列表")
            return []
        q_low = query.lower()
        scored: dict[str, float] = {}
        for keyword, tool_names in TOOL_RULE_MAP.items():
            if keyword in q_low:
                for tn in tool_names:
                    scored[tn] = scored.get(tn, 0.0) + 10.0
        for t in self.all_tools:
            if q_low in t.name.lower():
                scored[t.name] = scored.get(t.name, 0.0) + 5.0
            if q_low in t.description.lower():
                scored[t.name] = scored.get(t.name, 0.0) + 3.0
            aliases = TOOL_ALIAS_MAP.get(t.name, [])
            for alias in aliases:
                if q_low in alias.lower() or alias.lower() in q_low:
                    scored[t.name] = scored.get(t.name, 0.0) + 4.0
        for token in re.findall(r'[\w\u4e00-\u9fff]+', q_low):
            for t in self.all_tools:
                if token in t.name.lower() or token in t.description.lower():
                    scored[t.name] = scored.get(t.name, 0.0) + 1.0
        name_to_tool = {t.name: t for t in self.all_tools}
        sorted_names = sorted(scored.keys(), key=lambda n: scored[n], reverse=True)
        hits = [name_to_tool[n] for n in sorted_names if n in name_to_tool]
        if not hits:
            logger.info(f"ToolSearch: query='{query}' 命中0个工具")
        return hits[:top_k]

    def load_tool_schema(self, tool_name: str) -> bool:
        for t in self.all_tools:
            if t.name == tool_name and t not in self.loaded:
                self.loaded.append(t)
                logger.info(f"ToolSearch: loaded defer_loading tool '{tool_name}'")
                return True
        return False

    def get_current_loaded_schema(self) -> list[dict[str, Any]]:
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in self.loaded
        ]

    def get_loaded_names(self) -> list[str]:
        return [t.name for t in self.loaded]


tool_search_instance = ToolSearch(tool_list=_load_tool_defs_from_yaml())