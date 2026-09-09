"""
任务过滤 API 路由

提供批量任务去重过滤的 REST API 接口
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.task_filter import (
    AITask,
    FilterResult,
    filter_tasks,
    format_filter_summary,
    task_to_aitask,
    validate_batch_execution,
)

router = APIRouter(prefix="/task-filter", tags=["task-filter"])


class TaskFilterRequest(BaseModel):
    """任务过滤请求"""
    tasks: list[dict[str, Any]] = Field(..., description="原始任务列表")
    skip_validation: bool = Field(default=False, description="是否跳过执行前验证")


class TaskItem(BaseModel):
    """过滤后的任务项"""
    id: str
    type: str
    tool: str
    params: dict[str, Any]
    description: str
    is_dangerous: bool
    priority: int


class FilterResponse(BaseModel):
    """过滤响应"""
    filtered_tasks: list[TaskItem]
    removed_count: int
    reasons: list[str]
    warnings: list[str]
    summary: str
    validation: dict[str, Any]


@router.post("/filter", response_model=FilterResponse)
async def filter_task_list(request: TaskFilterRequest):
    """
    对批量任务进行去重过滤
    
    三层过滤：
    1. 精确去重（type + params 完全相同）
    2. 语义去重（同类型系统查询合并）
    3. 冲突检测（先查后杀、重复kill、危险操作限制）
    """
    # 执行过滤
    result = filter_tasks(request.tasks)
    
    # 转换过滤后的任务为响应格式
    filtered_tasks = [
        TaskItem(
            id=t.id,
            type=t.type,
            tool=t.tool,
            params=t.params,
            description=t.description,
            is_dangerous=t.is_dangerous,
            priority=t.priority,
        )
        for t in result.tasks
    ]
    
    # 执行验证（除非明确跳过）
    validation = {}
    if not request.skip_validation:
        validation = validate_batch_execution(result.tasks)
    
    return FilterResponse(
        filtered_tasks=filtered_tasks,
        removed_count=len(result.removed),
        reasons=result.reasons,
        warnings=result.warnings,
        summary=format_filter_summary(result),
        validation=validation,
    )


class BatchValidationRequest(BaseModel):
    """批量执行验证请求"""
    tasks: list[dict[str, Any]] = Field(..., description="要执行的任务列表")


class ValidationResponse(BaseModel):
    """验证响应"""
    allowed: bool
    warnings: list[str]
    dangerous_count: int
    total_count: int
    blocked_task: str | None = None


@router.post("/validate", response_model=ValidationResponse)
async def validate_batch(request: BatchValidationRequest):
    """
    批量执行前的最终确认检查
    
    返回是否允许执行以及警告信息
    """
    result = validate_batch_execution(request.tasks)
    
    return ValidationResponse(
        allowed=result.get("allowed", True),
        warnings=result.get("warnings", []),
        dangerous_count=result.get("dangerous_count", 0),
        total_count=result.get("total_count", len(request.tasks)),
        blocked_task=result.get("blocked_task"),
    )


class TestFilterRequest(BaseModel):
    """测试过滤请求"""
    test_cases: list[dict[str, Any]] = Field(..., description="测试用例列表")
    description: str = Field(default="", description="测试描述")


class TestFilterResponse(BaseModel):
    """测试过滤响应"""
    results: list[dict[str, Any]]
    summary: str


@router.post("/test", response_model=TestFilterResponse)
async def test_filter(request: TestFilterRequest):
    """
    测试任务过滤功能
    
    用于验证过滤逻辑是否正确
    """
    results = []
    
    for i, task in enumerate(request.test_cases):
        # 添加 ID
        task_with_id = dict(task)
        if "id" not in task_with_id:
            task_with_id["id"] = f"test_{i}"
        
        result = filter_tasks([task_with_id])
        
        results.append({
            "input": task_with_id,
            "passed": len(result.tasks) > 0,
            "removed": len(result.removed) > 0,
            "reasons": result.reasons,
            "warnings": result.warnings,
        })
    
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    
    summary = f"测试完成：{passed} 通过，{failed} 失败"
    
    return TestFilterResponse(
        results=results,
        summary=summary,
    )
