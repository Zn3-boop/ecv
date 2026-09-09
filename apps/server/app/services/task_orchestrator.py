"""
🎯 多步骤任务编排系统
自动分解复杂任务为可执行的任务列表
"""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"      # 待执行
    RUNNING = "running"      # 执行中
    SUCCESS = "success"      # 成功
    FAILED = "failed"        # 失败
    SKIPPED = "skipped"      # 跳过


class SubTask(BaseModel):
    """单个子任务"""
    id: str = Field(default="")
    title: str = Field(default="")
    description: str = Field(default="")
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    tool: str = Field(default="")           # 工具类型
    params: dict[str, Any] = Field(default_factory=dict)  # 工具参数
    result: str = Field(default="")         # 执行结果
    order: int = Field(default=0)          # 执行顺序
    depends_on: list[str] = Field(default_factory=list)  # 依赖的任务ID


class TaskWorkflow(BaseModel):
    """完整任务工作流"""
    id: str = Field(default="")
    user_request: str = Field(default="")  # 用户原始请求
    total_tasks: int = Field(default=0)
    completed_tasks: int = Field(default=0)
    tasks: list[SubTask] = Field(default_factory=list)
    current_task_index: int = Field(default=0)
    status: str = Field(default="pending")  # pending, running, completed, failed
    created_at: str = Field(default="")


# 全局任务存储
_task_workflows: dict[str, TaskWorkflow] = {}


def create_workflow_id() -> str:
    """生成唯一的工作流ID"""
    import time
    return f"workflow_{int(time.time() * 1000)}"


def generate_task_id() -> str:
    """生成唯一的任务ID"""
    import time
    import random
    return f"task_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"


# 任务模板库 - 定义常见任务的子任务组合
TASK_TEMPLATES = {
    "thesis_with_research": {
        "keywords": ["论文", "毕设", "毕业论文", "研究报告", "学术", "计算机毕设"],
        "tasks": [
            {
                "id": "browser_search",
                "title": "🔍 搜索相关资料",
                "description": "打开浏览器搜索计算机毕设相关主题和参考资料",
                "tool": "browser:search",
                "params_template": {"query": "计算机毕业设计选题 参考"},
                "order": 1
            },
            {
                "id": "generate_thesis",
                "title": "📝 生成论文内容",
                "description": "AI生成约1000字的论文内容，包含摘要、正文和结论，保存为Word文档",
                "tool": "content:generate",
                "params_template": {"content_type": "word", "theme": "计算机毕业设计", "length": "中", "auto_open": True},
                "order": 2,
                "depends_on": ["browser_search"]
            }
        ]
    },
    "login_page_project": {
        "keywords": ["登录页面", "网页", "html", "前端", "网站", "登录页"],
        "tasks": [
            {
                "id": "generate_login_page",
                "title": "🎨 生成登录页面代码",
                "description": "AI生成一个精美的登录页面HTML代码，保存到指定目录",
                "tool": "content:generate",
                "params_template": {"content_type": "html", "task": "登录页面", "theme": "用户登录", "style": "现代", "auto_open": True},
                "order": 1
            },
            {
                "id": "open_vscode",
                "title": "💻 打开VSCode编辑代码",
                "description": "启动VSCode进行代码编辑",
                "tool": "ide:launch",
                "params_template": {"ide": "vscode", "action": "open_file"},
                "order": 2,
                "depends_on": ["generate_login_page"]
            }
        ]
    },
    "browser_research": {
        "keywords": ["搜索", "查找", "查询", "浏览器"],
        "tasks": [
            {
                "title": "🌐 打开浏览器搜索",
                "description": "启动浏览器并搜索相关内容",
                "tool": "browser:search",
                "params_template": {},
                "order": 1
            },
            {
                "title": "📂 打开文件管理器",
                "description": "打开资源管理器查看下载的文件",
                "tool": "app:launch",
                "params_template": {"path": "explorer.exe"},
                "order": 2
            }
        ]
    }
}


def detect_workflow_type(user_request: str) -> str | None:
    """检测用户请求匹配哪种工作流模板"""
    request_lower = user_request.lower()
    
    # 检查关键词匹配度
    best_match = None
    best_score = 0
    
    for template_id, template in TASK_TEMPLATES.items():
        score = sum(1 for kw in template["keywords"] if kw in request_lower)
        if score > best_score:
            best_score = score
            best_match = template_id
    
    # 需要至少匹配2个关键词才触发模板
    if best_score >= 2:
        return best_match
    
    # 检查是否包含多步骤指示词
    multi_step_indicators = ["然后", "接着", "再", "最后", "之后", "同时", "并", "且", "并且"]
    if any(ind in user_request for ind in multi_step_indicators):
        return "custom_multi_step"
    
    return None


def parse_multi_step_request(user_request: str) -> list[dict[str, Any]]:
    """
    解析用户的多步骤请求，提取各个任务
    """
    import re
    
    tasks = []
    task_id_counter = 1
    
    # 分割步骤
    steps = re.split(r'[，,、\s]+', user_request)
    
    # 步骤顺序词
    order_words = ['先', '第一', '首先', '第一步', '1', '一']
    then_words = ['然后', '接着', '再', '第二', '其次', '第二步', '2', '二']
    finally_words = ['最后', '最终', '第三', '3', '三']
    
    current_order = 1
    
    for step in steps:
        step = step.strip()
        if not step:
            continue
        
        # 确定顺序
        if any(w in step for w in order_words):
            order = 1
        elif any(w in step for w in then_words):
            order = 2
        elif any(w in step for w in finally_words):
            order = 3
        else:
            order = current_order
            current_order += 1
        
        # 分析每个步骤应该使用什么工具
        task = analyze_step_for_tool(step, task_id_counter, order)
        if task:
            tasks.append(task)
            task_id_counter += 1
    
    return tasks


def analyze_step_for_tool(step: str, task_num: int, order: int) -> dict[str, Any] | None:
    """分析单个步骤，确定应该使用什么工具"""
    step_lower = step.lower()
    
    task_id = f"task_{task_num}"
    task = {
        "id": task_id,
        "title": f"步骤{task_num}: {step[:20]}...",
        "description": step,
        "order": order,
        "depends_on": []
    }
    
    # 检测工具类型
    if any(kw in step_lower for kw in ['搜索', '搜一下', '查找', '查一下']):
        # 提取搜索关键词
        query = step.replace('搜索', '').replace('搜一下', '').replace('查找', '').replace('查一下', '')
        query = query.replace('打开浏览器', '').replace('打开edge', '').replace('打开chrome', '').strip()
        
        task["title"] = f"🔍 搜索: {query[:15]}"
        task["tool"] = "browser:search"
        task["params"] = {"query": query, "browser": "edge"}
        
    elif any(kw in step_lower for kw in ['打开浏览器', 'edge', 'chrome', 'google']):
        if 'chrome' in step_lower or '谷歌' in step:
            browser = "chrome"
            browser_name = "Chrome"
        else:
            browser = "edge"
            browser_name = "Edge"
        
        task["title"] = f"🌐 打开{browser_name}浏览器"
        task["tool"] = "app:launch"
        task["params"] = {"path": browser}
        
    elif any(kw in step_lower for kw in ['word', '文档', 'wps']):
        task["title"] = "📄 打开Word文档编辑器"
        task["tool"] = "app:launch"
        task["params"] = {"path": "word"}
        
    elif any(kw in step_lower for kw in ['vscode', 'code', 'ide']):
        task["title"] = "💻 打开VSCode编辑器"
        task["tool"] = "app:launch"
        task["params"] = {"path": "vscode"}
        
    elif any(kw in step_lower for kw in ['创建', '生成', '编写', '制作']):
        # 内容生成任务
        if '登录页面' in step or '网页' in step or 'html' in step:
            task["title"] = "🎨 生成登录页面HTML"
            task["tool"] = "content:generate"
            task["params"] = {"content_type": "html", "task": "登录页面"}
        elif '论文' in step or '文档' in step:
            task["title"] = "📝 生成论文内容"
            task["tool"] = "content:generate"
            task["params"] = {"content_type": "word", "length": "medium"}
        elif '代码' in step or '程序' in step:
            task["title"] = "💻 生成代码"
            task["tool"] = "content:generate"
            task["params"] = {"content_type": "python"}
        else:
            task["title"] = "📝 生成内容"
            task["tool"] = "content:generate"
            task["params"] = {"content_type": "html"}
            
    elif any(kw in step_lower for kw in ['文件管理器', '资源管理器', 'explorer', '我的电脑']):
        task["title"] = "📂 打开文件管理器"
        task["tool"] = "app:launch"
        task["params"] = {"path": "explorer.exe"}
        
    else:
        # 通用桌面控制
        task["title"] = f"⚙️ 执行: {step[:15]}"
        task["tool"] = "desktop:generic"
        task["params"] = {"action": step}
    
    return task


def create_workflow(user_request: str) -> TaskWorkflow:
    """
    根据用户请求创建完整的工作流
    """
    workflow_id = create_workflow_id()
    workflow = TaskWorkflow(
        id=workflow_id,
        user_request=user_request,
        status="pending"
    )
    
    # 检测工作流类型
    workflow_type = detect_workflow_type(user_request)
    
    if workflow_type and workflow_type in TASK_TEMPLATES:
        # 使用模板创建任务
        template = TASK_TEMPLATES[workflow_type]
        
        # 提取用户指定的搜索关键词
        search_query = extract_search_query(user_request)
        
        # 提取输出路径（如"保存到D盘的login_page文件夹"）
        output_path = extract_output_path(user_request)
        
        for i, task_def in enumerate(template["tasks"]):
            task = SubTask(
                id=task_def["id"] if "id" in task_def else f"task_{i+1}",
                title=task_def["title"],
                description=task_def["description"],
                tool=task_def["tool"],
                params=task_def["params_template"].copy() if isinstance(task_def.get("params_template"), dict) else {},
                order=task_def.get("order", i + 1),
                depends_on=task_def.get("depends_on", [])
            )
            
            # 如果是搜索任务，替换查询关键词
            if task.tool == "browser:search" and search_query:
                task.params["query"] = search_query
                task.title = f"🔍 搜索: {search_query[:15]}"
            
            # 如果是内容生成任务，添加输出路径
            if task.tool == "content:generate" and output_path:
                task.params["output_path"] = output_path
                if "登录页面" in user_request or "html" in user_request.lower():
                    task.title = f"🎨 生成登录页面HTML到{output_path}"
            
            workflow.tasks.append(task)
            
    elif workflow_type == "custom_multi_step" or "然后" in user_request or "接着" in user_request:
        # 自定义多步骤请求
        steps = parse_multi_step_request(user_request)
        for step_task in steps:
            task = SubTask(
                id=step_task["id"],
                title=step_task["title"],
                description=step_task["description"],
                tool=step_task["tool"],
                params=step_task.get("params", {}),
                order=step_task["order"],
                depends_on=step_task.get("depends_on", [])
            )
            workflow.tasks.append(task)
            
    else:
        # 单一任务
        task_def = analyze_step_for_tool(user_request, 1, 1)
        if task_def:
            task = SubTask(
                id=task_def["id"],
                title=task_def["title"],
                description=task_def["description"],
                tool=task_def["tool"],
                params=task_def.get("params", {}),
                order=1
            )
            workflow.tasks.append(task)
    
    # 按顺序排序
    workflow.tasks.sort(key=lambda t: t.order)
    
    # 更新任务计数
    workflow.total_tasks = len(workflow.tasks)
    
    # 存储工作流
    _task_workflows[workflow_id] = workflow
    
    return workflow


def extract_search_query(user_request: str) -> str | None:
    """从用户请求中提取搜索关键词"""
    import re
    
    # 匹配模式: "搜索xxx" 或 "搜一下xxx"
    patterns = [
        r'搜索([^\s，。,、]+)',
        r'搜一下([^\s，。,、]+)',
        r'查找([^\s，。,、]+)',
        r'查一下([^\s，。,、]+)',
        r'搜索\s*([^\s，。,、]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, user_request)
        if match:
            return match.group(1).strip()
    
    return None


def extract_output_path(user_request: str) -> str | None:
    """从用户请求中提取输出路径（如"保存到D盘的login_page文件夹" -> "D:/login_page/index.html"）"""
    import re
    
    patterns = [
        r'保存到(.+?)文件夹',
        r'保存到(.+?)',
        r'保存到\s*(.+?)(?:\s|$|，|。)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, user_request)
        if match:
            path_str = match.group(1).strip()
            # 解析盘符和文件夹名
            # 例如: "D盘的login_page" -> "D:/login_page"
            # 或者: "D:/login_page" -> "D:/login_page"
            drive_match = re.match(r'([A-Za-z]):[/\\]*(.+)', path_str)
            if drive_match:
                drive = drive_match.group(1).upper()
                folder = drive_match.group(2).strip()
                return f"{drive}:/{folder}"
            # 处理没有盘符的情况，如"login_page文件夹"
            elif not re.match(r'^[A-Za-z]:', path_str):
                return f"./{path_str}"
    
    return None


def get_workflow(workflow_id: str) -> TaskWorkflow | None:
    """获取工作流"""
    return _task_workflows.get(workflow_id)


def update_task_status(workflow_id: str, task_id: str, status: TaskStatus, result: str = "") -> bool:
    """更新任务状态"""
    workflow = _task_workflows.get(workflow_id)
    if not workflow:
        return False
    
    for task in workflow.tasks:
        if task.id == task_id:
            task.status = status
            if result:
                task.result = result
            workflow.completed_tasks = sum(1 for t in workflow.tasks if t.status in [TaskStatus.SUCCESS, TaskStatus.SKIPPED])
            
            # 更新工作流状态
            if workflow.completed_tasks == workflow.total_tasks:
                workflow.status = "completed"
            elif any(t.status == TaskStatus.RUNNING for t in workflow.tasks):
                workflow.status = "running"
            
            return True
    
    return False


def format_workflow_display(workflow: TaskWorkflow) -> str:
    """格式化工作流显示为可读文本"""
    lines = []
    lines.append(f"\n📋 **任务清单** ({workflow.completed_tasks}/{workflow.total_tasks})\n")
    
    for i, task in enumerate(workflow.tasks, 1):
        status_icon = {
            TaskStatus.PENDING: "⬜",
            TaskStatus.RUNNING: "🔄",
            TaskStatus.SUCCESS: "✅",
            TaskStatus.FAILED: "❌",
            TaskStatus.SKIPPED: "⏭️"
        }.get(task.status, "⬜")
        
        checkbox = "☐" if task.status == TaskStatus.PENDING else "☑"
        lines.append(f"{checkbox} **{i}. {task.title}**")
        lines.append(f"   └ {task.description}")
        if task.result:
            lines.append(f"   └ 结果: {task.result}")
        lines.append("")
    
    return "\n".join(lines)