from __future__ import annotations

import atexit
import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "agent.db"

_session_table_created = False

def _ensure_table() -> None:
    global _session_table_created
    if _session_table_created:
        return
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_stores (
                conversation_id TEXT PRIMARY KEY,
                global_context TEXT NOT NULL DEFAULT '{}',
                agent_local_ctx TEXT NOT NULL DEFAULT '{}',
                call_history TEXT NOT NULL DEFAULT '[]',
                created_at REAL NOT NULL
            )
        """)
        conn.commit()
        conn.close()
        _session_table_created = True
    except Exception:
        _session_table_created = True

@dataclass
class SessionStore:
    conversation_id: str
    global_context: dict[str, Any] = field(default_factory=dict)
    agent_local_ctx: dict[str, dict[str, Any]] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    call_history: list[dict[str, Any]] = field(default_factory=list)
    _dirty: bool = field(default=False, repr=False)
    _persist_timer: Any = field(default=None, repr=False)
    _persist_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def get_global(self, key: str, default: Any = None) -> Any:
        return self.global_context.get(key, default)

    def set_global(self, key: str, value: Any) -> None:
        self.global_context[key] = value
        self._dirty = True
        self._schedule_persist()

    def get_local(self, agent_name: str, key: str, default: Any = None) -> Any:
        return self.agent_local_ctx.get(agent_name, {}).get(key, default)

    def set_local(self, agent_name: str, key: str, value: Any) -> None:
        if agent_name not in self.agent_local_ctx:
            self.agent_local_ctx[agent_name] = {}
        self.agent_local_ctx[agent_name][key] = value
        self._dirty = True
        self._schedule_persist()

    def log_call(self, agent_name: str, args: dict[str, Any], result: dict[str, Any], elapsed_ms: float = 0.0) -> None:
        self.call_history.append({
            "agent": agent_name,
            "args": args,
            "result_keys": list(result.keys()) if isinstance(result, dict) else None,
            "elapsed_ms": round(elapsed_ms, 2),
            "timestamp": time.time(),
        })
        self._dirty = True
        self._schedule_persist()

    def _schedule_persist(self) -> None:
        try:
            if hasattr(self, '_persist_timer') and self._persist_timer:
                return
            self._persist_timer = threading.Timer(0.5, self.persist)
            self._persist_timer.daemon = True
            self._persist_timer.start()
        except Exception:
            self.persist()

    def snapshot(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "global_context_keys": list(self.global_context.keys()),
            "agent_local_ctx_keys": {k: list(v.keys()) for k, v in self.agent_local_ctx.items()},
            "call_count": len(self.call_history),
            "created_at": self.created_at,
        }

    def persist(self) -> None:
        if not self._dirty:
            return
        with self._persist_lock:
            try:
                _ensure_table()
                conn = sqlite3.connect(_DB_PATH)
                conn.execute(
                    """INSERT OR REPLACE INTO session_stores
                       (conversation_id, global_context, agent_local_ctx, call_history, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        self.conversation_id,
                        json.dumps(self.global_context, ensure_ascii=False, default=str),
                        json.dumps(self.agent_local_ctx, ensure_ascii=False, default=str),
                        json.dumps(self.call_history[-50:], ensure_ascii=False, default=str),
                        self.created_at,
                    ),
                )
                conn.commit()
                conn.close()
                self._dirty = False
                self._persist_timer = None
            except Exception:
                pass

class SessionStoreManager:
    _instances: dict[str, SessionStore] = {}

    @classmethod
    def get_or_create(cls, conversation_id: str) -> SessionStore:
        if conversation_id not in cls._instances:
            session = cls._load_from_db(conversation_id)
            if session is None:
                session = SessionStore(conversation_id=conversation_id)
            cls._instances[conversation_id] = session
        return cls._instances[conversation_id]

    @classmethod
    def _load_from_db(cls, conversation_id: str) -> SessionStore | None:
        try:
            _ensure_table()
            conn = sqlite3.connect(_DB_PATH)
            row = conn.execute(
                "SELECT global_context, agent_local_ctx, call_history, created_at FROM session_stores WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            conn.close()
            if row is None:
                return None
            return SessionStore(
                conversation_id=conversation_id,
                global_context=json.loads(row[0]),
                agent_local_ctx=json.loads(row[1]),
                call_history=json.loads(row[2]),
                created_at=row[3],
            )
        except Exception:
            return None

    @classmethod
    def get(cls, conversation_id: str) -> SessionStore | None:
        return cls._instances.get(conversation_id)

    @classmethod
    def clear(cls, conversation_id: str) -> bool:
        if conversation_id in cls._instances:
            session = cls._instances.pop(conversation_id)
            try:
                _ensure_table()
                conn = sqlite3.connect(_DB_PATH)
                conn.execute("DELETE FROM session_stores WHERE conversation_id = ?", (conversation_id,))
                conn.commit()
                conn.close()
            except Exception:
                pass
            return True
        return False

    @classmethod
    def list_sessions(cls) -> list[dict[str, Any]]:
        return [s.snapshot() for s in cls._instances.values()]

    @classmethod
    def clear_all(cls) -> int:
        count = len(cls._instances)
        cls._instances.clear()
        try:
            _ensure_table()
            conn = sqlite3.connect(_DB_PATH)
            conn.execute("DELETE FROM session_stores")
            conn.commit()
            conn.close()
        except Exception:
            pass
        return count

    @classmethod
    def flush_all(cls) -> None:
        for session in cls._instances.values():
            session.persist()

atexit.register(SessionStoreManager.flush_all)