from __future__ import annotations

from typing import Any

from app.services.hooks.plugins.base import PromptBuilder


class DefaultPromptBuilder(PromptBuilder):
    """
    默认Prompt构造器:
    - 区分RAG/Web来源
    - 优先使用内部知识库
    - 要求标注引用来源
    - 不确定的内容不编造
    """

    _TEMPLATE = """【参考资料（内部知识库）】
{rag_content}

【参考资料（互联网检索，注意信息可能存在偏差）】
{web_content}

用户问题：{question}

要求：
1. 优先使用内部知识库内容；内部资料不足时，再使用网络检索信息
2. 区分信息来源，不确定的内容不要编造
3. 回答中标注引用来源"""

    def build(self, fused_context: str, query: str, metadata: dict[str, Any] | None = None) -> str:
        meta = metadata or {}
        rag_content = meta.get("rag_content", "")
        web_content = meta.get("web_content", "")

        if not rag_content and not web_content:
            return fused_context

        return self._TEMPLATE.format(
            rag_content=rag_content or "（无相关内部资料）",
            web_content=web_content or "（无相关网络资料）",
            question=query,
        )


class ConcisePromptBuilder(PromptBuilder):
    """
    精简Prompt构造器: 适合上下文窗口紧张的场景。
    """

    _TEMPLATE = """参考: {context}

问题: {question}
请基于参考内容回答，优先内部知识库，不确定请说明。"""

    def build(self, fused_context: str, query: str, metadata: dict[str, Any] | None = None) -> str:
        return self._TEMPLATE.format(context=fused_context, question=query)


class StructuredPromptBuilder(PromptBuilder):
    """
    结构化Prompt构造器: 带来源标注、证据ID、矛盾提示。
    R10: 证据回溯 + 压幻觉。
    R12: 矛盾片段处理。
    """

    _TEMPLATE = """## 参考资料

{evidence_block}

## 矛盾提示
{contradiction_hint}

## 用户问题
{question}

## 回答要求
1. 每条引用标注来源 [来源:内部/网络] 和证据ID
2. 内部知识库优先，网络信息需标注"待验证"
3. 存在矛盾时，列出各来源说法，不偏信任一方
4. 不确定的内容明确说明，不编造"""

    def build(self, fused_context: str, query: str, metadata: dict[str, Any] | None = None) -> str:
        meta = metadata or {}
        evidence_ids = meta.get("evidence_ids", [])
        contradiction = meta.get("contradiction", {})

        if evidence_ids:
            ids_str = ", ".join(evidence_ids[:10])
            evidence_block = f"证据ID: [{ids_str}]\n\n{fused_context}"
        else:
            evidence_block = fused_context

        has_contradiction = contradiction.get("has_contradiction", False)
        if has_contradiction:
            details = contradiction.get("details", [])
            hint_parts = []
            for d in details[:3]:
                hint_parts.append(f"- {d.get('summary', '存在矛盾')}")
            contradiction_hint = "\n".join(hint_parts) if hint_parts else "检测到矛盾片段，请对比各来源"
        else:
            contradiction_hint = "无"

        return self._TEMPLATE.format(
            evidence_block=evidence_block,
            contradiction_hint=contradiction_hint,
            question=query,
        )