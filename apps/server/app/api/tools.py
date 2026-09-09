
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.automation import Command, parse_user_command
from app.services.tool_registry import ToolCategory, tool_registry
from app.services.tools.executor import execute_tool_calls

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolDescriptor(BaseModel):
    name: str
    description: str
    category: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False
    command_type: str = "read"
    risk: str = "low"
    recommended: bool = False
    examples: list[str] = Field(default_factory=list)


class ToolListResponse(BaseModel):
    items: list[ToolDescriptor] = Field(default_factory=list)


class ToolSuggestRequest(BaseModel):
    text: str = Field(..., min_length=1, description="User natural language request")


class ToolSuggestResponse(BaseModel):
    analysis: str
    reply_text: str
    matched_tools: list[ToolDescriptor] = Field(default_factory=list)
    commands: list[Command] = Field(default_factory=list)


def _serialize_tool(tool) -> ToolDescriptor:
    return ToolDescriptor(
        name=tool.name,
        description=tool.description,
        category=tool.category.value if isinstance(tool.category, ToolCategory) else str(tool.category),
        parameters=tool.parameters,
        requires_confirmation=tool.requires_confirmation,
        command_type=tool.command_type,
        risk=tool.risk,
        recommended=tool.recommended,
        examples=tool.examples,
    )


@router.get("", response_model=ToolListResponse)
async def list_tools(category: str | None = Query(default=None)):
    resolved_category = None
    if category:
        try:
            resolved_category = ToolCategory(category)
        except ValueError:
            resolved_category = None

    items = [_serialize_tool(tool) for tool in tool_registry.list_tools(resolved_category)]
    return ToolListResponse(items=items)


@router.post("/suggest", response_model=ToolSuggestResponse)
async def suggest_tools(payload: ToolSuggestRequest):
    analysis, commands, reply_text = parse_user_command(payload.text)
    matched_tools = [_serialize_tool(tool) for tool in tool_registry.match_tools(payload.text)]
    return ToolSuggestResponse(
        analysis=analysis,
        reply_text=reply_text,
        matched_tools=matched_tools,
        commands=commands,
    )


class ToolExecuteRequest(BaseModel):
    commands: list[dict[str, Any]] = Field(default_factory=list, description="要执行的命令列表")


class ToolExecuteResponse(BaseModel):
    success: bool = True
    results: list[dict[str, Any]] = Field(default_factory=list)
    message: str = ""


@router.post("/execute", response_model=ToolExecuteResponse)
async def execute_tools(payload: ToolExecuteRequest):
    """执行命令列表，返回执行结果"""
    if not payload.commands:
        return ToolExecuteResponse(success=False, message="没有要执行的命令")
    
    results = []
    for cmd in payload.commands:
        tool_name = cmd.get("toolName") or cmd.get("tool") or cmd.get("name", "")
        params = cmd.get("params") or cmd.get("arguments") or {}
        
        # 调用 executor 执行工具
        try:
            tool_calls = [{
                "id": f"call_{i}",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(params) if isinstance(params, dict) else str(params),
                }
            }]
            result = await execute_tool_calls(tool_calls)
            if result:
                results.append({
                    "tool": tool_name,
                    "success": True,
                    "result": result[0].get("content", ""),
                })
            else:
                results.append({
                    "tool": tool_name,
                    "success": False,
                    "error": "执行返回为空",
                })
        except Exception as e:
            results.append({
                "tool": tool_name,
                "success": False,
                "error": str(e),
            })
    
    return ToolExecuteResponse(
        success=all(r.get("success", False) for r in results),
        results=results,
        message=f"执行了 {len(results)} 个命令",
    )
