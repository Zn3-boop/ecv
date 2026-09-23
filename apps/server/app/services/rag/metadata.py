from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChunkMeta:
    chunk_id: str
    doc_id: str
    doc_title: str
    section_path: list[str]
    chunk_index: int
    version: int
    created_at: float
    updated_at: float
    source_type: str
    acl_tags: list[str]
    source_url: str
    checksum: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "doc_title": self.doc_title,
            "section_path": self.section_path,
            "chunk_index": self.chunk_index,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_type": self.source_type,
            "acl_tags": self.acl_tags,
            "source_url": self.source_url,
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ChunkMeta:
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


def make_chunk_meta(
    content: str,
    doc_id: str = "",
    doc_title: str = "",
    section_path: list[str] | None = None,
    chunk_index: int = 0,
    version: int = 1,
    source_type: str = "text",
    acl_tags: list[str] | None = None,
    source_url: str = "",
) -> ChunkMeta:
    now = time.time()
    checksum = hashlib.md5(content.encode("utf-8")).hexdigest()[:12]
    return ChunkMeta(
        chunk_id=f"chk_{uuid.uuid4().hex[:12]}",
        doc_id=doc_id or f"doc_{uuid.uuid4().hex[:8]}",
        doc_title=doc_title,
        section_path=section_path or [],
        chunk_index=chunk_index,
        version=version,
        created_at=now,
        updated_at=now,
        source_type=source_type,
        acl_tags=acl_tags or ["public"],
        source_url=source_url,
        checksum=checksum,
    )