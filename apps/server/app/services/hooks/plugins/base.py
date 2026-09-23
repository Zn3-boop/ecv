from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RewriteType(str, Enum):
    NORMALIZE = "normalize"
    EXPAND = "expand"
    GENERALIZE = "generalize"
    CORRECT = "correct"


class DocSource(str, Enum):
    RAG = "rag"
    WEB = "web"
    CODE = "code"
    CUSTOM = "custom"


@dataclass
class RetrievedDoc:
    content: str
    source: DocSource = DocSource.RAG
    score: float = 0.5
    title: str = ""
    url: str = ""
    chunk_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "source": self.source.value,
            "score": self.score,
            "title": self.title,
            "url": self.url,
            "chunk_id": self.chunk_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RetrievedDoc:
        source_val = d.get("source", "rag")
        source = DocSource(source_val) if isinstance(source_val, str) else source_val
        return cls(
            content=d.get("content", ""),
            source=source,
            score=float(d.get("score", 0.5)),
            title=d.get("title", ""),
            url=d.get("url", ""),
            chunk_id=d.get("chunk_id", ""),
            metadata=d.get("metadata", {}),
        )


@dataclass
class RewriteResult:
    standalone_query: str
    rag_query: str
    web_query: str
    retrieval_queries: list[str] = field(default_factory=list)
    rewrite_types: list[RewriteType] = field(default_factory=list)
    confidence: float = 1.0


@dataclass
class FusionInput:
    rag_docs: list[RetrievedDoc] = field(default_factory=list)
    web_docs: list[RetrievedDoc] = field(default_factory=list)
    query: str = ""
    rag_weight: float = 0.7
    web_weight: float = 0.3


@dataclass
class ValidationResult:
    passed: bool
    reason: str = ""
    filtered_docs: list[RetrievedDoc] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class QueryRewriter(abc.ABC):
    """
    B1-B4: 查询改写插件接口
    - raw_query 永不覆盖 (B2)
    - 支持4种改写类型: normalize/expand/generalize/correct (B4)
    - 生成 rag_query / web_query / retrieval_queries
    """

    @abc.abstractmethod
    async def rewrite(self, raw_query: str, context: dict[str, Any] | None = None) -> RewriteResult:
        ...

    @property
    def name(self) -> str:
        return self.__class__.__name__


class Retriever(abc.ABC):
    """
    可插拔检索器接口
    - RAG向量检索 / Web搜索 / 代码搜索 / 自定义
    - 每个检索器独立超时控制
    """

    @abc.abstractmethod
    async def retrieve(self, query: str, top_k: int = 5, **kwargs: Any) -> list[RetrievedDoc]:
        ...

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @property
    def source(self) -> DocSource:
        return DocSource.CUSTOM


class FusionStrategy(abc.ABC):
    """
    结果融合策略插件接口
    - simple_concat / weighted / rerank (方案A/B/C)
    """

    @abc.abstractmethod
    async def fuse(self, fusion_input: FusionInput) -> str:
        ...

    @property
    def name(self) -> str:
        return self.__class__.__name__


class DedupFilter(abc.ABC):
    """
    去重与过滤插件接口
    - 文本相似度去重 / 规则过滤 / 时效性过滤
    """

    @abc.abstractmethod
    async def dedup_filter(self, docs: list[RetrievedDoc], query: str) -> list[RetrievedDoc]:
        ...

    @property
    def name(self) -> str:
        return self.__class__.__name__


class PromptBuilder(abc.ABC):
    """
    Prompt构造模板插件接口
    - 区分RAG/Web来源
    - 标注引用来源
    - 优先内部知识库
    """

    @abc.abstractmethod
    def build(self, fused_context: str, query: str, metadata: dict[str, Any] | None = None) -> str:
        ...

    @property
    def name(self) -> str:
        return self.__class__.__name__


class ResultValidator(abc.ABC):
    """
    H5: 验证门插件接口
    - Checker: 硬性检查
    - Evaluator: 软性评估
    """

    @abc.abstractmethod
    async def validate(self, docs: list[RetrievedDoc], query: str) -> ValidationResult:
        ...

    @property
    def name(self) -> str:
        return self.__class__.__name__