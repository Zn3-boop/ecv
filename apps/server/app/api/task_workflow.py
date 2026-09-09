"""
🎯 多步骤任务编排 API
支持复杂任务的自动分解和执行
"""

from __future__ import annotations

import asyncio
import subprocess
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.task_orchestrator import (
    create_workflow, get_workflow, update_task_status,
    format_workflow_display, TaskStatus, SubTask
)
from app.api.automation import Command
from app.services.tools.executor import execute_tool_calls
from app.api.content_generator import generate_content, GenerateRequest

router = APIRouter(prefix='/task-workflow', tags=['task-workflow'])


class CreateWorkflowRequest(BaseModel):
    """创建工作流请求"""
    user_request: str = Field(..., description="用户的复杂任务描述")
    auto_execute: bool = Field(default=True, description="是否自动执行任务")


class WorkflowStatusResponse(BaseModel):
    """工作流状态响应"""
    workflow_id: str
    user_request: str
    total_tasks: int
    completed_tasks: int
    status: str
    tasks: list[dict[str, Any]]
    formatted_display: str


class ExecuteTaskRequest(BaseModel):
    """执行任务请求"""
    workflow_id: str = Field(..., description="工作流ID")
    task_id: str = Field(..., description="要执行的任务ID")
    skip_dependencies: bool = Field(default=False, description="是否跳过依赖检查")


# 全局命令存储，用于前端显示
_workflow_commands: dict[str, list[dict[str, Any]]] = {}


@router.post('/create', response_model=WorkflowStatusResponse)
async def create_task_workflow(request: CreateWorkflowRequest):
    """
    🎯 创建任务工作流
    将复杂的用户请求分解为可执行的任务列表
    """
    # 创建工作流
    workflow = create_workflow(request.user_request)
    
    # 生成命令列表
    commands = []
    for task in workflow.tasks:
        cmd = create_command_from_task(task)
        if cmd:
            commands.append(cmd.model_dump() if hasattr(cmd, 'model_dump') else cmd)
    
    # 存储命令
    _workflow_commands[workflow.id] = commands
    
    return WorkflowStatusResponse(
        workflow_id=workflow.id,
        user_request=workflow.user_request,
        total_tasks=workflow.total_tasks,
        completed_tasks=workflow.completed_tasks,
        status=workflow.status,
        tasks=[task.model_dump() for task in workflow.tasks],
        formatted_display=format_workflow_display(workflow)
    )


@router.get('/status/{workflow_id}', response_model=WorkflowStatusResponse)
async def get_workflow_status(workflow_id: str):
    """获取工作流状态"""
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")
    
    return WorkflowStatusResponse(
        workflow_id=workflow.id,
        user_request=workflow.user_request,
        total_tasks=workflow.total_tasks,
        completed_tasks=workflow.completed_tasks,
        status=workflow.status,
        tasks=[task.model_dump() for task in workflow.tasks],
        formatted_display=format_workflow_display(workflow)
    )


@router.get('/commands/{workflow_id}')
async def get_workflow_commands(workflow_id: str):
    """获取工作流的所有命令，用于前端展示和执行"""
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")
    
    commands = _workflow_commands.get(workflow_id, [])
    
    return {
        "workflow_id": workflow_id,
        "total_tasks": workflow.total_tasks,
        "completed_tasks": workflow.completed_tasks,
        "commands": commands,
        "formatted_tasks": format_workflow_display(workflow)
    }


@router.post('/execute-task', response_model=dict[str, Any])
async def execute_single_task(request: ExecuteTaskRequest):
    """
    执行单个任务
    """
    workflow = get_workflow(request.workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")
    
    # 找到任务
    task = None
    for t in workflow.tasks:
        if t.id == request.task_id:
            task = t
            break
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 检查依赖
    if not request.skip_dependencies and task.depends_on:
        for dep_id in task.depends_on:
            dep_task = next((t for t in workflow.tasks if t.id == dep_id), None)
            if dep_task and dep_task.status != TaskStatus.SUCCESS:
                return {
                    "success": False,
                    "error": f"依赖任务未完成: {dep_task.title}",
                    "task_id": task.id,
                    "status": "waiting_dependency"
                }
    
    # 更新状态为运行中
    update_task_status(workflow.id, task.id, TaskStatus.RUNNING)
    
    # 执行任务
    result = await execute_task(task)
    
    # 更新状态
    if result["success"]:
        update_task_status(workflow.id, task.id, TaskStatus.SUCCESS, result.get("message", ""))
    else:
        update_task_status(workflow.id, task.id, TaskStatus.FAILED, result.get("error", ""))
    
    return {
        "success": result["success"],
        "task_id": task.id,
        "result": result,
        "workflow_id": workflow.id
    }


@router.post('/execute-all', response_model=dict[str, Any])
async def execute_all_tasks(workflow_id: str):
    """
    自动执行工作流中的所有任务
    """
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")
    
    results = []
    workflow.status = "running"
    
    for task in workflow.tasks:
        # 检查依赖
        can_execute = True
        if task.depends_on:
            for dep_id in task.depends_on:
                dep_task = next((t for t in workflow.tasks if t.id == dep_id), None)
                if dep_task and dep_task.status != TaskStatus.SUCCESS:
                    can_execute = False
                    update_task_status(workflow.id, task.id, TaskStatus.SKIPPED, f"依赖任务失败: {dep_task.title}")
                    break
        
        if not can_execute:
            continue
        
        # 更新状态
        update_task_status(workflow.id, task.id, TaskStatus.RUNNING)
        
        # 执行任务
        result = await execute_task(task)
        results.append({
            "task_id": task.id,
            "title": task.title,
            "success": result["success"],
            "result": result
        })
        
        # 更新状态
        if result["success"]:
            update_task_status(workflow.id, task.id, TaskStatus.SUCCESS, result.get("message", ""))
        else:
            update_task_status(workflow.id, task.id, TaskStatus.FAILED, result.get("error", ""))
            # 如果任务失败，后续依赖任务可能需要跳过
            for t in workflow.tasks:
                if task.id in t.depends_on:
                    # 标记依赖当前失败任务的任务
                    pass
    
    # 获取更新后的工作流
    updated_workflow = get_workflow(workflow_id)
    
    return {
        "workflow_id": workflow_id,
        "total_tasks": len(results),
        "completed_tasks": sum(1 for r in results if r["success"]),
        "results": results,
        "status": updated_workflow.status if updated_workflow else "completed",
        "formatted_tasks": format_workflow_display(updated_workflow) if updated_workflow else ""
    }


def create_command_from_task(task: SubTask) -> Command | None:
    """根据任务创建Command对象"""
    if task.tool == "app:launch":
        return Command(
            tool="app:launch",
            type="write",
            params=task.params,
            reason=task.title,
            confidence=0.95,
            risk="low",
            require_confirmation=False,
            auto_execute=task.order <= 2
        )
    elif task.tool == "browser:search":
        query = task.params.get("query", "")
        import urllib.parse
        if any('\u4e00' <= c <= '\u9fff' for c in query):
            url = f"https://www.baidu.com/s?wd={urllib.parse.quote(query)}"
        else:
            url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        
        browser = task.params.get("browser", "msedge.exe")
        return Command(
            tool="app:launch",
            type="write",
            params={"path": browser, "url": url},
            reason=f"搜索: {query}",
            confidence=0.92,
            risk="low",
            require_confirmation=False,
            auto_execute=True
        )
    elif task.tool == "content:generate":
        return Command(
            tool="content:generate",
            type="write",
            params={
                "task": task.params.get("task", task.title),
                "content_type": task.params.get("content_type", "word"),
                "theme": task.params.get("theme", ""),
                "style": task.params.get("style", "现代"),
                "length": task.params.get("length", "中"),
                "output_path": task.params.get("output_path", ""),
            },
            reason=task.title,
            confidence=0.9,
            risk="low",
            require_confirmation=False,
            auto_execute=True
        )
    elif task.tool == "desktop:generic":
        return Command(
            tool="desktop:generic",
            type="write",
            params=task.params,
            reason=task.title,
            confidence=0.8,
            risk="low",
            require_confirmation=False,
            auto_execute=True
        )
    
    return None


# 全局存储搜索结果，供后续任务使用
_search_results = {}


async def execute_task(task: SubTask) -> dict[str, Any]:
    """执行单个任务"""
    try:
        if task.tool == "app:launch":
            # 使用完整路径启动应用
            path = task.params.get("path", "")
            url = task.params.get("url", "")
            
            # 应用完整路径映射
            app_paths = {
                'msedge.exe': r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                'WINWORD.EXE': r'C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE',
                'Code.exe': r'C:\Users\13268\AppData\Local\Programs\Microsoft VS Code\Code.exe',
            }
            
            # 如果是简单命令，尝试转换为完整路径
            if path in app_paths:
                path = app_paths[path]
            
            # 如果路径不存在，尝试查找
            import os
            if not os.path.exists(path):
                # 尝试在PATH中查找
                try:
                    result = subprocess.run(['where', path.split('\\')[-1] if '\\' in path else path], 
                                          capture_output=True, text=True, shell=True)
                    if result.returncode == 0:
                        path = result.stdout.strip().split('\n')[0]
                except:
                    pass
            
            if url:
                cmd = [path, url]
            else:
                cmd = [path]
            
            proc = subprocess.Popen(cmd, shell=True)
            
            return {
                "success": True,
                "message": f"已启动: {path}",
                "process_id": proc.pid
            }
            
        elif task.tool == "browser:search":
            # 浏览器搜索 - 记录搜索结果供后续使用
            query = task.params.get("query", "")
            browser = task.params.get("browser", "msedge.exe")
            
            import urllib.parse
            if any('\u4e00' <= c <= '\u9fff' for c in query):
                url = f"https://www.baidu.com/s?wd={urllib.parse.quote(query)}"
            else:
                url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            
            proc = subprocess.Popen([browser, url], shell=True)
            
            # 保存搜索关键词供后续任务使用
            workflow_id = task.params.get("workflow_id", "default")
            _search_results[workflow_id] = {
                "query": query,
                "url": url,
                "browser": browser
            }
            
            return {
                "success": True,
                "message": f"已在{browser}中搜索: {query}",
                "process_id": proc.pid,
                "search_data": {
                    "query": query,
                    "url": url
                }
            }
            
        elif task.tool == "content:generate":
            # 内容生成 - 使用搜索结果增强内容
            workflow_id = task.params.get("workflow_id", "default")
            search_data = _search_results.get(workflow_id, {})
            
            # 构建增强的prompt，包含搜索信息
            base_task = task.params.get("task", "内容")
            search_query = search_data.get("query", "")
            
            enhanced_task = base_task
            if search_query:
                enhanced_task = f"{base_task}\n\n参考搜索关键词: {search_query}"
            
            gen_req = GenerateRequest(
                task=enhanced_task,
                content_type=task.params.get("content_type", "html"),
                style=task.params.get("style", "现代"),
                length=task.params.get("length", "中"),
                output_path=task.params.get("output_path", ""),
                auto_open=task.params.get("auto_open", True),
            )
            
            result = await generate_content(gen_req)
            
            return {
                "success": result.success,
                "message": result.output_file if result.success else result.message,
                "file": result.output_file,
                "content": result.content if hasattr(result, 'content') else None
            }
        
        elif task.tool == "desktop:generic":
            # 通用桌面操作 - 解析描述文本中的关键操作
            action = task.params.get("action", task.description)
            
            # 检查是否包含文件保存操作
            if "保存到" in action or "保存" in action:
                # 尝试解析保存路径
                import re
                save_match = re.search(r'保存到(.+?)文件夹', action)
                if save_match:
                    folder_name = save_match.group(1).strip()
                    return {
                        "success": True,
                        "message": f"文件保存任务已识别: {folder_name}，将在后续步骤保存"
                    }
            
            # 其他通用操作返回成功（因为具体操作由 Electron 主进程处理）
            return {
                "success": True,
                "message": f"桌面操作已接收: {action[:50]}"
            }
        
        else:
            return {
                "success": False,
                "error": f"未知工具类型: {task.tool}"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }