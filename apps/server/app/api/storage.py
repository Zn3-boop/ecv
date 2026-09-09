from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.storage import (
    add_conversation_message,
    backup_database,
    create_conversation,
    create_favorite,
    create_shortcut,
    delete_conversation,
    delete_favorite,
    delete_shortcut,
    get_conversation,
    list_backups,
    list_conversation_messages,
    list_conversations,
    list_favorites,
    list_shortcuts,
    restore_from_backup,
    search_all_sessions_history,
    search_conversation_history,
    update_conversation,
    update_conversation_message,
)

router = APIRouter(prefix="/storage", tags=["storage"])


class ConversationCreateRequest(BaseModel):
    title: str = Field(..., min_length=1)
    role_prompt: str = Field(default="")


class ConversationUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1)
    role_prompt: str = Field(default="")


class ConversationMessageCreateRequest(BaseModel):
    role: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    metadata: dict[str, Any] | None = Field(default=None)


class ShortcutCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    category: str = Field(default="general", min_length=1)


class FavoriteCreateRequest(BaseModel):
    kind: str = Field(..., min_length=1)
    target_id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    payload: dict[str, Any] | None = Field(default=None)


class ConversationMessageUpdateRequest(BaseModel):
    content: str = Field(..., min_length=1)


@router.get("/conversations")
async def get_conversations():
    return {"items": list_conversations()}


@router.post("/conversations")
async def post_conversation(payload: ConversationCreateRequest):
    return create_conversation(title=payload.title, role_prompt=payload.role_prompt)


@router.get("/conversations/{conversation_id}")
async def get_conversation_detail(conversation_id: int):
    conversation = get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "conversation": conversation,
        "messages": list_conversation_messages(conversation_id),
    }


@router.put("/conversations/{conversation_id}")
async def put_conversation(conversation_id: int, payload: ConversationUpdateRequest):
    updated = update_conversation(conversation_id, title=payload.title, role_prompt=payload.role_prompt)
    if not updated:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return updated


@router.delete("/conversations/{conversation_id}")
async def remove_conversation(conversation_id: int):
    deleted = delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True, "id": conversation_id}


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: int):
    conversation = get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"items": list_conversation_messages(conversation_id)}


@router.post("/conversations/{conversation_id}/messages")
async def post_message(conversation_id: int, payload: ConversationMessageCreateRequest):
    conversation = get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return add_conversation_message(
        conversation_id=conversation_id,
        role=payload.role,
        content=payload.content,
        metadata=payload.metadata,
    )


@router.patch("/conversations/{conversation_id}/messages/{message_id}")
async def patch_message(conversation_id: int, message_id: int, payload: ConversationMessageUpdateRequest):
    """更新指定消息的内容"""
    updated = update_conversation_message(
        message_id=message_id,
        conversation_id=conversation_id,
        content=payload.content,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Message not found")
    return updated


@router.get("/shortcuts")
async def get_shortcuts():
    return {"items": list_shortcuts()}


@router.post("/shortcuts")
async def post_shortcut(payload: ShortcutCreateRequest):
    return create_shortcut(name=payload.name, content=payload.content, category=payload.category)


@router.delete("/shortcuts/{shortcut_id}")
async def remove_shortcut(shortcut_id: int):
    deleted = delete_shortcut(shortcut_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Shortcut not found")
    return {"deleted": True, "id": shortcut_id}


@router.get("/favorites")
async def get_favorites():
    return {"items": list_favorites()}


@router.post("/favorites")
async def post_favorite(payload: FavoriteCreateRequest):
    return create_favorite(
        kind=payload.kind,
        target_id=payload.target_id,
        label=payload.label,
        payload=payload.payload,
    )


@router.delete("/favorites/{favorite_id}")
async def remove_favorite(favorite_id: int):
    deleted = delete_favorite(favorite_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Favorite not found")
    return {"deleted": True, "id": favorite_id}


# === 备份管理 API ===

@router.post("/backup")
async def create_backup():
    """创建数据库备份"""
    result = backup_database()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("message"))
    return result


@router.get("/backups")
async def get_backups():
    """列出所有可用备份"""
    return {"backups": list_backups()}


@router.post("/backups/{backup_name}/restore")
async def restore_backup(backup_name: str):
    """从指定备份恢复数据库"""
    result = restore_from_backup(backup_name)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


# === 历史搜索 API ===

@router.get("/history/search")
async def search_history(
    q: str = "",
    limit: int = 50,
    offset: int = 0,
    conversation_id: int | None = None,
):
    """
    搜索历史处理记录
    - q: 搜索关键词
    - limit/offset: 分页
    - conversation_id: 可选，限制在指定会话内搜索
    """
    if conversation_id is not None:
        # 单会话搜索
        conversation = get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        records, total = search_conversation_history(conversation_id, q, limit, offset)
    else:
        # 跨所有会话搜索
        records, total = search_all_sessions_history(q, limit, offset)
    
    return {"records": records, "total": total}