from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = BASE_DIR / "data"
AUDIT_DB_PATH = DATA_DIR / "audit.db"

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS signal_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    trace_id TEXT,
    signal_type TEXT NOT NULL,
    signal_reason TEXT,
    correction_loops INTEGER NOT NULL DEFAULT 0,
    hitl_decision TEXT,
    hitl_comment TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_signal_audit_session ON signal_audit_log(session_id);
CREATE INDEX IF NOT EXISTS idx_signal_audit_user ON signal_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_signal_audit_created ON signal_audit_log(created_at);
"""


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(AUDIT_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_table() -> None:
    with _connect() as conn:
        conn.executescript(_TABLE_DDL)


_ensure_table()


class SignalAuditRecord(BaseModel):
    session_id: str
    user_id: str
    trace_id: Optional[str] = None
    signal_type: str
    signal_reason: Optional[str] = None
    correction_loops: int = 0
    hitl_decision: Optional[str] = None
    hitl_comment: Optional[str] = None


def write_signal_audit(record: SignalAuditRecord) -> int:
    _ensure_table()
    sql = """
        INSERT INTO signal_audit_log (
            session_id, user_id, trace_id, signal_type, signal_reason,
            correction_loops, hitl_decision, hitl_comment
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    with _connect() as conn:
        cur = conn.execute(
            sql,
            (
                record.session_id,
                record.user_id,
                record.trace_id,
                record.signal_type,
                record.signal_reason,
                record.correction_loops,
                record.hitl_decision,
                record.hitl_comment,
            ),
        )
        conn.commit()
        return cur.lastrowid


def update_audit_decision(
    session_id: str,
    hitl_decision: str,
    hitl_comment: Optional[str] = None,
) -> bool:
    _ensure_table()
    sql = """
        UPDATE signal_audit_log
        SET hitl_decision = ?, hitl_comment = ?,
            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        WHERE id = (
            SELECT id FROM signal_audit_log
            WHERE session_id = ?
            ORDER BY created_at DESC LIMIT 1
        )
    """
    with _connect() as conn:
        cur = conn.execute(sql, (hitl_decision, hitl_comment or "", session_id))
        conn.commit()
        return cur.rowcount > 0


def query_audit_log(session_id: str, limit: int = 20) -> list[dict[str, Any]]:
    _ensure_table()
    sql = """
        SELECT * FROM signal_audit_log
        WHERE session_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    """
    with _connect() as conn:
        rows = conn.execute(sql, (session_id, limit)).fetchall()
        return [dict(r) for r in rows]