from __future__ import annotations

import re
import logging
from typing import Any

from app.services.rag.metadata import ChunkMeta, make_chunk_meta

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 600
DEFAULT_OVERLAP_RATIO = 0.12
MIN_CHUNK_SIZE = 100
MAX_CHUNK_SIZE = 1200


class Chunker:
    """
    R2: 结构化切分 + 重叠率 (400-800字, 10-15% overlap)
    R3: 四类切分法 (text/ocr/table/code)
    """

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap_ratio: float = DEFAULT_OVERLAP_RATIO,
    ):
        self.chunk_size = max(MIN_CHUNK_SIZE, min(chunk_size, MAX_CHUNK_SIZE))
        self.overlap_size = int(self.chunk_size * overlap_ratio)

    def chunk_text(
        self,
        text: str,
        doc_id: str = "",
        doc_title: str = "",
        source_type: str = "text",
        acl_tags: list[str] | None = None,
        source_url: str = "",
    ) -> list[dict[str, Any]]:
        if source_type == "code":
            return self._chunk_code(text, doc_id, doc_title, acl_tags, source_url)
        if source_type == "table":
            return self._chunk_table(text, doc_id, doc_title, acl_tags, source_url)
        if source_type == "scan":
            return self._chunk_scan(text, doc_id, doc_title, acl_tags, source_url)
        return self._chunk_structured(text, doc_id, doc_title, source_type, acl_tags, source_url)

    def _chunk_structured(
        self,
        text: str,
        doc_id: str,
        doc_title: str,
        source_type: str,
        acl_tags: list[str] | None,
        source_url: str,
    ) -> list[dict[str, Any]]:
        sections = self._split_by_structure(text)
        results: list[dict[str, Any]] = []
        chunk_idx = 0
        for section_path, content in sections:
            content = content.strip()
            if not content:
                continue
            if len(content) <= self.chunk_size:
                meta = make_chunk_meta(
                    content=content, doc_id=doc_id, doc_title=doc_title,
                    section_path=section_path, chunk_index=chunk_idx,
                    source_type=source_type, acl_tags=acl_tags, source_url=source_url,
                )
                results.append({"content": content, "meta": meta.to_dict()})
                chunk_idx += 1
            else:
                for chunk in self._sliding_window(content):
                    meta = make_chunk_meta(
                        content=chunk, doc_id=doc_id, doc_title=doc_title,
                        section_path=section_path, chunk_index=chunk_idx,
                        source_type=source_type, acl_tags=acl_tags, source_url=source_url,
                    )
                    results.append({"content": chunk, "meta": meta.to_dict()})
                    chunk_idx += 1
        return results

    def _split_by_structure(self, text: str) -> list[tuple[list[str], str]]:
        heading_pattern = re.compile(r'^(#{1,6}\s+.+|[一二三四五六七八九十]+[、．.].+|\d+[\.．]\s+.+)$', re.MULTILINE)
        parts = heading_pattern.split(text)
        sections: list[tuple[list[str], str]] = []
        current_path: list[str] = []
        current_content: list[str] = []
        i = 0
        while i < len(parts):
            part = parts[i]
            if heading_pattern.match(part.strip()):
                if current_content:
                    content = "\n".join(current_content).strip()
                    if content:
                        sections.append((list(current_path), content))
                    current_content = []
                heading_text = re.sub(r'^#{1,6}\s+', '', part.strip())
                current_path = [heading_text]
            else:
                current_content.append(part)
            i += 1
        if current_content:
            content = "\n".join(current_content).strip()
            if content:
                sections.append((list(current_path), content))
        if not sections:
            sections = [([], text)]
        return sections

    def _sliding_window(self, text: str) -> list[str]:
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            if end < len(text):
                last_period = max(
                    chunk.rfind("。"), chunk.rfind("。"), chunk.rfind("\n"),
                    chunk.rfind(". "), chunk.rfind("! "), chunk.rfind("? "),
                )
                if last_period > self.chunk_size * 0.5:
                    chunk = chunk[: last_period + 1]
                    end = start + last_period + 1
            chunks.append(chunk.strip())
            start = end - self.overlap_size
            if start <= (end - self.chunk_size):
                start = end - self.overlap_size
        return [c for c in chunks if c]

    def _chunk_code(
        self,
        text: str,
        doc_id: str,
        doc_title: str,
        acl_tags: list[str] | None,
        source_url: str,
    ) -> list[dict[str, Any]]:
        blocks = re.split(r'\n(?=(class |def |async def |function |public |private |protected ))', text)
        results: list[dict[str, Any]] = []
        chunk_idx = 0
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            if len(block) > MAX_CHUNK_SIZE:
                for sub in self._sliding_window(block):
                    meta = make_chunk_meta(
                        content=sub, doc_id=doc_id, doc_title=doc_title,
                        section_path=["code"], chunk_index=chunk_idx,
                        source_type="code", acl_tags=acl_tags, source_url=source_url,
                    )
                    results.append({"content": sub, "meta": meta.to_dict()})
                    chunk_idx += 1
            else:
                meta = make_chunk_meta(
                    content=block, doc_id=doc_id, doc_title=doc_title,
                    section_path=["code"], chunk_index=chunk_idx,
                    source_type="code", acl_tags=acl_tags, source_url=source_url,
                )
                results.append({"content": block, "meta": meta.to_dict()})
                chunk_idx += 1
        return results

    def _chunk_table(
        self,
        text: str,
        doc_id: str,
        doc_title: str,
        acl_tags: list[str] | None,
        source_url: str,
    ) -> list[dict[str, Any]]:
        rows = text.strip().split("\n")
        if not rows:
            return []
        header = rows[0]
        results: list[dict[str, Any]] = []
        chunk_idx = 0
        batch_size = max(1, self.chunk_size // max(len(r) for r in rows[:5]) if rows[:5] else 20)
        for i in range(0, len(rows), batch_size):
            batch = [header] + rows[i + 1 : i + batch_size + 1] if i == 0 else [header] + rows[i : i + batch_size]
            content = "\n".join(batch)
            meta = make_chunk_meta(
                content=content, doc_id=doc_id, doc_title=doc_title,
                section_path=["table"], chunk_index=chunk_idx,
                source_type="table", acl_tags=acl_tags, source_url=source_url,
            )
            results.append({"content": content, "meta": meta.to_dict()})
            chunk_idx += 1
        return results

    def _chunk_scan(
        self,
        text: str,
        doc_id: str,
        doc_title: str,
        acl_tags: list[str] | None,
        source_url: str,
    ) -> list[dict[str, Any]]:
        cleaned = re.sub(r'\s+', ' ', text).strip()
        return self._chunk_structured(cleaned, doc_id, doc_title, "scan", acl_tags, source_url)