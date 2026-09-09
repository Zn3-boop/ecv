from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.utils.response_cleaner import LEAKAGE_FALLBACK_MESSAGE, cleaner

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "agent.db"

# 备份配置
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_ENABLED = os.getenv("BACKUP_ENABLED", "true").lower() == "true"
BACKUP_RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "7"))
BACKUP_RETENTION_COUNT = int(os.getenv("BACKUP_RETENTION_COUNT", "10"))


def _ensure_backup_dir() -> Path:
    """确保备份目录存在"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR


def _get_backup_path() -> Path:
    """生成带时间戳的备份文件路径"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _ensure_backup_dir() / f"agent_{timestamp}.db"


def _cleanup_old_backups() -> list[Path]:
    """清理过期的备份文件"""
    if not BACKUP_DIR.exists():
        return []
    
    # 按修改时间排序，最新的在前
    backups = sorted(BACKUP_DIR.glob("agent_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    removed = []
    now = datetime.now().timestamp()
    
    for backup in backups[BACKUP_RETENTION_COUNT:]:
        backup_age_days = (now - backup.stat().st_mtime) / 86400
        if backup_age_days > BACKUP_RETENTION_DAYS:
            backup.unlink(missing_ok=True)
            removed.append(backup)
    
    return removed


def backup_database() -> dict[str, Any]:
    """
    创建 SQLite 数据库备份
    返回备份结果信息
    """
    if not BACKUP_ENABLED:
        return {"success": False, "message": "Backup is disabled"}
    
    if not DB_PATH.exists():
        return {"success": False, "message": "Database file not found"}
    
    backup_path = _get_backup_path()
    
    try:
        # 使用 sqlite3 backup API 进行热备份
        source = sqlite3.connect(DB_PATH)
        dest = sqlite3.connect(backup_path)
        source.backup(dest)
        dest.close()
        source.close()
        
        # 清理旧备份
        removed = _cleanup_old_backups()
        
        return {
            "success": True,
            "backup_path": str(backup_path),
            "backup_size": backup_path.stat().st_size,
            "removed_count": len(removed),
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


def restore_from_backup(backup_name: str) -> dict[str, Any]:
    """
    从备份文件恢复数据库
    backup_name: 备份文件名，如 "agent_20240524_120000.db"
    """
    if not BACKUP_ENABLED:
        return {"success": False, "message": "Backup is disabled"}
    
    backup_path = BACKUP_DIR / backup_name
    if not backup_path.exists():
        return {"success": False, "message": f"Backup file not found: {backup_name}"}
    
    # 备份当前数据库
    current_backup = _get_backup_path()
    try:
        shutil.copy2(DB_PATH, current_backup)
    except Exception:
        pass  # 如果当前数据库不存在，跳过备份
    
    try:
        # 关闭所有连接后恢复
        shutil.copy2(backup_path, DB_PATH)
        return {
            "success": True,
            "restored_from": str(backup_path),
            "safety_backup": str(current_backup),
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


def list_backups() -> list[dict[str, Any]]:
    """列出所有可用备份"""
    if not BACKUP_DIR.exists():
        return []
    
    backups = []
    for path in sorted(BACKUP_DIR.glob("agent_*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = path.stat()
        backups.append({
            "name": path.name,
            "path": str(path),
            "size": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "age_days": (datetime.now().timestamp() - stat.st_mtime) / 86400,
        })
    
    return backups


@dataclass
class LLMHistoryMessage:
    role: str
    content: str
    timestamp: str | None = None
    is_meta: bool = False
    is_fallback: bool = False
    was_cleaned: bool = False


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_storage() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                role_prompt TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shortcuts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                target_id TEXT NOT NULL,
                label TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def list_conversations() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, role_prompt, created_at, updated_at FROM conversations ORDER BY updated_at DESC, id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def create_conversation(title: str, role_prompt: str = "") -> dict[str, Any]:
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO conversations (title, role_prompt) VALUES (?, ?)",
            (title, role_prompt),
        )
        conversation_id = cursor.lastrowid
        row = conn.execute(
            "SELECT id, title, role_prompt, created_at, updated_at FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        conn.commit()
    return dict(row)


def get_conversation(conversation_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, title, role_prompt, created_at, updated_at FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
    return dict(row) if row else None


def update_conversation(conversation_id: int, *, title: str, role_prompt: str) -> dict[str, Any] | None:
    with _connect() as conn:
        conn.execute(
            "UPDATE conversations SET title = ?, role_prompt = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (title, role_prompt, conversation_id),
        )
        row = conn.execute(
            "SELECT id, title, role_prompt, created_at, updated_at FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        conn.commit()
    return dict(row) if row else None


def delete_conversation(conversation_id: int) -> bool:
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        conn.execute("DELETE FROM conversation_messages WHERE conversation_id = ?", (conversation_id,))
        conn.commit()
    return cursor.rowcount > 0


def _parse_metadata(metadata_json: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(metadata_json or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _clean_history_content(raw_content: str) -> tuple[str, bool]:
    original = str(raw_content or "").strip()
    cleaned = original
    if not cleaned:
        return "", False

    patterns_to_remove = [
        r"原问题：角色设定：.*?当前用户消息：",
        r"原问题:.*?(?=系统监控摘要:|语音上下文摘要:|$)",
        r"初稿：.*?(?=审核意见：|$)",
        r"初稿:.*?(?=审核意见:|$)",
        r"审核意见：.*?(?=系统监控摘要：|$)",
        r"审核意见:.*?(?=系统监控摘要:|$)",
        r"内部改写要求（不要在最终回答中显式提及）:.*?(?=系统监控摘要:|$)",
        r"系统监控摘要：.*?(?=语音上下文摘要：|$)",
        r"系统监控摘要:.*?(?=语音上下文摘要:|$)",
        r"语音上下文摘要：.*?(?=当前仍走本地降级|$)",
        r"语音上下文摘要:.*?(?=当前仍走本地降级|$)",
        r"当前仍走本地降级草稿逻辑.*?$",
        r"已根据审核意见完成重写.*?$",
        r"LLM provider request failed:.*$",
        r"provider 错误.*$",
        r"审核意见.*$",
    ]
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL | re.MULTILINE)

    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, cleaned != original


def list_conversation_messages(conversation_id: int) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, conversation_id, role, content, metadata_json, created_at FROM conversation_messages WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["metadata"] = _parse_metadata(item.pop("metadata_json", "{}"))
        result.append(item)
    return result


def add_conversation_message(
    conversation_id: int,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload_metadata = dict(metadata or {})
    payload_metadata.setdefault("type", "assistant_output" if role == "assistant" else "user_input" if role == "user" else "generic")
    metadata_json = json.dumps(payload_metadata, ensure_ascii=False)
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO conversation_messages (conversation_id, role, content, metadata_json) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, metadata_json),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (conversation_id,),
        )
        row = conn.execute(
            "SELECT id, conversation_id, role, content, metadata_json, created_at FROM conversation_messages WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        conn.commit()
    item = dict(row)
    item["metadata"] = _parse_metadata(item.pop("metadata_json", "{}"))
    return item


def add_assistant_output(
    conversation_id: int,
    final_output: str,
    *,
    review_source: str | None = None,
    used_system_context: bool = False,
    used_voice_context: bool = False,
    fallback_reason: str | None = None,
    system_snapshot: dict[str, Any] | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cleaned_output = cleaner.clean(final_output)
    had_fallback = bool(fallback_reason) or cleaned_output == LEAKAGE_FALLBACK_MESSAGE
    persisted_output = "（此前服务暂时不可用，已简化回复）" if had_fallback else cleaned_output

    metadata: dict[str, Any] = {
        "type": "assistant_output",
        "review_source": review_source,
        "used_system_context": used_system_context,
        "used_voice_context": used_voice_context,
        "had_fallback": had_fallback,
        "fallback_reason": ((fallback_reason or "ResponseLeakageDetected") if had_fallback else "")[:100] or None,
        "system_snapshot": system_snapshot or {},
        "was_cleaned": cleaned_output != str(final_output or "").strip(),
    }
    if extra_meta:
        metadata.update(extra_meta)

    if metadata.get("used_fallback") or had_fallback:
        metadata["original_error"] = metadata.get("fallback_reason")
        metadata["enter_history"] = bool(metadata.get("enter_history", False))
        persisted_output = "（此前服务暂时不可用，已简化回复）"

    return add_conversation_message(conversation_id, "assistant", persisted_output, metadata)


def get_history_for_llm(
    conversation_id: int,
    limit: int = 6,
    *,
    max_chars: int = 4000,
) -> list[LLMHistoryMessage]:
    raw_messages = list_conversation_messages(conversation_id)
    sanitized: list[LLMHistoryMessage] = []

    for item in raw_messages:
        role = str(item.get("role", "")).strip()
        if role not in {"user", "assistant", "system"}:
            continue

        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        message_type = str(metadata.get("type", "")).strip().lower()
        is_meta = bool(metadata.get("is_meta")) or message_type in {"internal_meta", "meta", "draft", "review", "voice_turn"}
        is_fallback = (
            bool(metadata.get("had_fallback"))
            or bool(metadata.get("is_fallback"))
            or message_type == "fallback"
            or str(metadata.get("review_source", "")).strip().lower() in {"error_fallback", "unicode_fallback"}
        )

        if role == "assistant" and message_type and message_type != "assistant_output":
            continue
        if role == "user" and message_type and message_type != "user_input":
            continue
        if is_meta or is_fallback:
            continue

        cleaned_content, was_cleaned = _clean_history_content(str(item.get("content", "")))
        if not cleaned_content or len(cleaned_content) <= 10:
            continue

        sanitized.append(
            LLMHistoryMessage(
                role=role,
                content=cleaned_content,
                timestamp=item.get("created_at"),
                is_meta=is_meta,
                is_fallback=is_fallback,
                was_cleaned=was_cleaned,
            )
        )

    max_messages = max(limit * 2, 1)
    trimmed = sanitized[-max_messages:]

    if max_chars <= 0:
        return trimmed

    budgeted: list[LLMHistoryMessage] = []
    total_chars = 0
    for item in reversed(trimmed):
        item_len = len(item.content)
        if budgeted and total_chars + item_len > max_chars:
            break
        if not budgeted and item_len > max_chars:
            truncated_content = item.content[-max_chars:]
            budgeted.append(
                LLMHistoryMessage(
                    role=item.role,
                    content=truncated_content,
                    timestamp=item.timestamp,
                    is_meta=item.is_meta,
                    is_fallback=item.is_fallback,
                    was_cleaned=True,
                )
            )
            total_chars = len(truncated_content)
            break
        budgeted.append(item)
        total_chars += item_len

    return list(reversed(budgeted))


def ensure_conversation(title: str = "桌面语音会话", role_prompt: str = "") -> dict[str, Any]:
    conversations = list_conversations()
    if conversations:
        return conversations[0]
    return create_conversation(title=title, role_prompt=role_prompt)


def create_voice_turn(
    conversation_id: int,
    transcript: str,
    voice_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    turn_id = str((voice_context or {}).get("turn_id") or f"voice-turn-{uuid4().hex[:10]}")
    payload = {
        **(voice_context or {}),
        "turn_id": turn_id,
        "entry_type": "voice_turn",
        "transcript": transcript,
        "type": "voice_turn",
        "is_meta": True,
    }
    # voice_turn 作为 meta 信息存储，但 role 使用 system 以符合 add_conversation_message 的要求
    return add_conversation_message(conversation_id, "system", transcript, payload)


def list_shortcuts() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, name, content, category, created_at, updated_at FROM shortcuts ORDER BY updated_at DESC, id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def create_shortcut(name: str, content: str, category: str) -> dict[str, Any]:
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO shortcuts (name, content, category) VALUES (?, ?, ?)",
            (name, content, category),
        )
        row = conn.execute(
            "SELECT id, name, content, category, created_at, updated_at FROM shortcuts WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        conn.commit()
    return dict(row)


def delete_shortcut(shortcut_id: int) -> bool:
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM shortcuts WHERE id = ?", (shortcut_id,))
        conn.commit()
    return cursor.rowcount > 0


def list_favorites() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, kind, target_id, label, payload_json, created_at FROM favorites ORDER BY id DESC"
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["payload"] = json.loads(item.pop("payload_json") or "{}")
        result.append(item)
    return result


def create_favorite(kind: str, target_id: str, label: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload_json = json.dumps(payload or {}, ensure_ascii=False)
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO favorites (kind, target_id, label, payload_json) VALUES (?, ?, ?, ?)",
            (kind, target_id, label, payload_json),
        )
        row = conn.execute(
            "SELECT id, kind, target_id, label, payload_json, created_at FROM favorites WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        conn.commit()
    item = dict(row)
    item["payload"] = _parse_metadata(item.pop("payload_json", "{}"))
    return item


def delete_favorite(favorite_id: int) -> bool:
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM favorites WHERE id = ?", (favorite_id,))
        conn.commit()
    return cursor.rowcount > 0


def update_conversation_message(
    message_id: int,
    conversation_id: int,
    content: str,
) -> dict[str, Any] | None:
    """更新指定消息的内容"""
    with _connect() as conn:
        conn.execute(
            "UPDATE conversation_messages SET content = ? WHERE id = ? AND conversation_id = ?",
            (content, message_id, conversation_id),
        )
        row = conn.execute(
            "SELECT id, conversation_id, role, content, metadata_json, created_at FROM conversation_messages WHERE id = ?",
            (message_id,),
        ).fetchone()
        conn.commit()
        if not row:
            return None
        item = dict(row)
        item["metadata"] = _parse_metadata(item.pop("metadata_json", "{}"))
        return item


def search_conversation_history(
    conversation_id: int | None,
    keyword: str = "",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """
    搜索会话历史记录
    返回: (记录列表, 总数)
    
    将 user + system + assistant 消息聚合成"处理记录"
    """
    conn = _connect()
    try:
        if keyword.strip():
            where_clause = "WHERE cm.conversation_id = ? AND cm.content LIKE ?"
            params: tuple[int | str, ...] = (conversation_id, f"%{keyword}%")
        else:
            where_clause = "WHERE cm.conversation_id = ?"
            params = (conversation_id,)
        
        count_query = f"SELECT COUNT(*) as cnt FROM conversation_messages cm {where_clause}"
        total = conn.execute(count_query, params).fetchone()["cnt"]
        
        effective_limit = min(limit * 5, 500)
        query = f"""
            SELECT cm.id, cm.conversation_id, cm.role, cm.content, cm.metadata_json, cm.created_at
            FROM conversation_messages cm
            {where_clause}
            ORDER BY cm.id DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(query, (*params, effective_limit, offset)).fetchall()
        messages_asc = list(reversed([dict(row) for row in rows]))
        
        records = aggregate_history_records(messages_asc)
        
        page_records = records[:limit]
        return page_records, total
    finally:
        conn.close()


def search_all_sessions_history(
    keyword: str = "",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """
    跨会话搜索所有历史记录
    返回: (记录列表, 总数)
    """
    conn = _connect()
    try:
        if keyword.strip():
            where_clause = "WHERE cm.content LIKE ?"
            params: tuple[str, ...] = (f"%{keyword}%",)
        else:
            where_clause = ""
            params = ()
        
        query = f"""
            SELECT cm.id, cm.conversation_id, cm.role, cm.content, cm.metadata_json, cm.created_at,
                   c.title as conversation_title
            FROM conversation_messages cm
            JOIN conversations c ON cm.conversation_id = c.id
            {where_clause}
            ORDER BY cm.id DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(query, (*params, limit, offset)).fetchall()
        
        # 统计
        count_query = f"SELECT COUNT(*) as cnt FROM conversation_messages cm {where_clause}"
        total = conn.execute(count_query, params).fetchone()["cnt"]
        
        # 简单聚合成记录
        records = []
        for row in rows:
            item = dict(row)
            item["metadata"] = _parse_metadata(item.pop("metadata_json", "{}"))
            records.append(item)
        
        return records, total
    finally:
        conn.close()


def aggregate_history_records(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    将消息聚合成处理记录
    一次用户请求 + 系统反馈 + 助手指令 = 一条记录
    返回格式适配前端 SessionHistory 组件
    """
    records: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        created_at = msg.get("created_at", "")
        
        if role == "user":
            # 用户发起新请求，归档上一个
            if current:
                records.append(current)
            
            # 判断请求类型
            record_type = 'general'
            if re.search(r'cpu|CPU|处理器', content, re.IGNORECASE):
                record_type = 'cpu'
            elif re.search(r'c盘|磁盘|disk|cleanup|空间', content, re.IGNORECASE):
                record_type = 'disk'
            elif re.search(r'内存|memory|mem|ram', content, re.IGNORECASE):
                record_type = 'memory'
            elif re.search(r'清理|clean|临时文件|垃圾', content, re.IGNORECASE):
                record_type = 'cleanup'
            
            current = {
                "id": str(msg.get("id")),
                "timestamp": created_at,
                "query": content,
                "type": record_type,
                "actions": [],
                "status": "pending",
                "systemData": None,
            }
        elif role == "system" and current:
            current["systemData"] = content
            if len(current["actions"]) == 0 and ("监控" in content or "CPU" in content or "内存" in content):
                current["actions"].append("系统诊断")
        elif role == "assistant" and current:
            # 提取可执行指令
            exec_match = re.search(r'已识别到可执行指令[：:]\s*(.+?)[。\n]', content)
            if exec_match:
                current["actions"].append(exec_match.group(1).strip())
            
            # 提取任务数
            count_match = re.search(r'已为你生成\s*(\d+)\s*条.*?指令', content)
            if count_match:
                current["actionCount"] = int(count_match.group(1))
            
            # 状态判断
            if re.search(r'执行成功|已完成|已清理|完成', content):
                current["status"] = "completed"
            elif re.search(r'需确认|危险操作|确认执行', content):
                current["status"] = "confirm_required"
            elif re.search(r'失败|错误|error', content, re.IGNORECASE):
                current["status"] = "failed"
    
    if current:
        records.append(current)
    
    # 倒序返回（最新的在前）
    return list(reversed(records))