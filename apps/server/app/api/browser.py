"""
浏览器控制 API 路由

提供浏览器自动搜索控制的 REST API 接口
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.browser_automation import (
    BROWSER_PROMPT_TEMPLATE,
    BrowserAction,
    build_search_url,
    execute_browser_action,
    format_browser_action_json,
    parse_browser_intent,
)
from app.api.agent import handle_user_command, UserCommand

router = APIRouter(prefix="/browser", tags=["browser"])


class BrowserIntentRequest(BaseModel):
    """浏览器意图解析请求"""
    command: str = Field(..., description="用户输入的自然语言命令")


class BrowserIntentResponse(BaseModel):
    """浏览器意图解析响应"""
    type: str = Field(..., description="操作类型：search/open/navigate")
    url: str | None = Field(default=None, description="目标URL（navigate类型时）")
    search_query: str | None = Field(default=None, description="搜索关键词（search类型时）")
    browser: str = Field(..., description="浏览器偏好：edge/chrome/firefox/default")
    new_window: bool = Field(default=True, description="是否新窗口打开")
    raw_command: str = Field(..., description="原始命令")
    search_url: str | None = Field(default=None, description="构建的搜索URL")


@router.post("/intent", response_model=BrowserIntentResponse)
async def parse_intent(request: BrowserIntentRequest):
    """
    解析用户浏览器指令

    统一走 agent 主链路意图识别，从 AgentResponse 中提取浏览器参数，
    消除与 parse_browser_intent 的重复解析逻辑。
    """
    agent_resp = await handle_user_command(
        UserCommand(text=request.command, session_id="browser-intent")
    )

    browser_type = "open"
    url = None
    search_query = None
    browser = "default"
    new_window = True

    for cmd in agent_resp.commands:
        if cmd.tool == "browser:search":
            browser_type = "search"
            search_query = cmd.params.get("query", cmd.params.get("search_query", ""))
            browser = cmd.params.get("browser", "default")
            break
        if cmd.tool == "app:launch":
            launch_url = cmd.params.get("url")
            if launch_url:
                if "baidu.com/s?" in launch_url or "google.com/search?" in launch_url or "bing.com/search?" in launch_url:
                    browser_type = "search"
                    import urllib.parse
                    for prefix in ("wd=", "q="):
                        idx = launch_url.find(prefix)
                        if idx != -1:
                            search_query = urllib.parse.unquote(launch_url[idx + len(prefix):].split("&")[0])
                            break
                    if not search_query:
                        search_query = request.command
                else:
                    browser_type = "open"
                    url = launch_url
            path = cmd.params.get("path", "")
            if "chrome" in path.lower():
                browser = "chrome"
            elif "msedge" in path.lower():
                browser = "edge"
            elif "firefox" in path.lower():
                browser = "firefox"
            break

    if not search_query and not url and browser_type == "open":
        action = parse_browser_intent(request.command)
        browser_type = action.type
        url = action.url
        search_query = action.search_query
        browser = action.browser
        new_window = action.new_window

    search_url = None
    if browser_type == "search" and search_query:
        action = BrowserAction(
            type="search", search_query=search_query,
            browser=browser, new_window=new_window,
            raw_command=request.command,
        )
        search_url = build_search_url(action)

    return BrowserIntentResponse(
        type=browser_type,
        url=url,
        search_query=search_query,
        browser=browser,
        new_window=new_window,
        raw_command=request.command,
        search_url=search_url,
    )


class BrowserExecuteRequest(BaseModel):
    """浏览器执行请求"""
    type: str = Field(..., description="操作类型：search/open/navigate")
    url: str | None = Field(default=None, description="目标URL")
    search_query: str | None = Field(default=None, description="搜索关键词")
    browser: str = Field(default="default", description="浏览器：edge/chrome/firefox/default")
    new_window: bool = Field(default=True, description="是否新窗口打开")
    raw_command: str = Field(default="", description="原始命令")


class BrowserExecuteResponse(BaseModel):
    """浏览器执行响应"""
    success: bool
    message: str
    browser: str
    url: str
    command: str | None = None
    fallback: bool = False
    error: str | None = None


@router.post("/execute", response_model=BrowserExecuteResponse)
async def execute_browser(request: BrowserExecuteRequest):
    """
    执行浏览器操作
    
    支持：
    - 搜索：打开浏览器并执行搜索
    - 打开URL：直接导航到指定URL
    - 打开新窗口：仅打开浏览器
    """
    # 验证搜索查询
    if request.type == "search" and not request.search_query:
        raise HTTPException(
            status_code=400,
            detail="SEARCH_QUERY_EMPTY: 搜索任务缺少关键词"
        )
    
    # 构建 Action
    action = BrowserAction(
        type=request.type,
        url=request.url,
        search_query=request.search_query,
        browser=request.browser,
        new_window=request.new_window,
        raw_command=request.raw_command,
    )
    
    # 执行
    result = execute_browser_action(action)
    
    return BrowserExecuteResponse(
        success=result.get("success", False),
        message=result.get("message", ""),
        browser=result.get("browser", request.browser),
        url=result.get("url", request.url or ""),
        command=result.get("command"),
        fallback=result.get("fallback", False),
        error=result.get("error"),
    )


class BrowserNLRequest(BaseModel):
    """自然语言浏览器控制请求"""
    command: str = Field(..., description="用户自然语言命令，如：'帮我搜索Python教程'")


class BrowserNLResponse(BaseModel):
    """自然语言浏览器控制响应"""
    intent: BrowserIntentResponse
    result: BrowserExecuteResponse


@router.post("/nlp", response_model=BrowserNLResponse)
async def nlp_browser_control(request: BrowserNLRequest):
    """
    自然语言浏览器控制（解析+执行一站式）

    统一走 agent 主链路完成解析和执行，
    消除与 parse_browser_intent + execute_browser_action 的重复逻辑。
    """
    intent_resp = await parse_intent(BrowserIntentRequest(command=request.command))

    action = BrowserAction(
        type=intent_resp.type,
        url=intent_resp.url,
        search_query=intent_resp.search_query,
        browser=intent_resp.browser,
        new_window=intent_resp.new_window,
        raw_command=request.command,
    )

    result = execute_browser_action(action)

    exec_response = BrowserExecuteResponse(
        success=result.get("success", False),
        message=result.get("message", ""),
        browser=result.get("browser", intent_resp.browser),
        url=result.get("url", intent_resp.url or ""),
        command=result.get("command"),
        fallback=result.get("fallback", False),
        error=result.get("error"),
    )

    return BrowserNLResponse(
        intent=intent_resp,
        result=exec_response,
    )


class BrowserPromptResponse(BaseModel):
    """浏览器控制 Prompt 模板响应"""
    template: str


@router.get("/prompt", response_model=BrowserPromptResponse)
async def get_browser_prompt():
    """
    获取浏览器控制的 Prompt 模板
    
    用于引导 LLM 输出结构化的浏览器控制指令
    """
    return BrowserPromptResponse(template=BROWSER_PROMPT_TEMPLATE)


# 便捷命令：快速搜索
class QuickSearchRequest(BaseModel):
    """快速搜索请求"""
    query: str = Field(..., description="搜索关键词")
    browser: str = Field(default="default", description="浏览器：edge/chrome/firefox/default")


class QuickSearchResponse(BaseModel):
    """快速搜索响应"""
    success: bool
    message: str
    search_url: str
    browser: str


@router.post("/search", response_model=QuickSearchResponse)
async def quick_search(request: QuickSearchRequest):
    """
    快速搜索接口
    
    最简单的搜索接口，只需提供搜索词
    """
    action = BrowserAction(
        type="search",
        search_query=request.query,
        browser=request.browser,
        new_window=True,
        raw_command=f"搜索 {request.query}",
    )
    
    result = execute_browser_action(action)
    search_url = build_search_url(action)
    
    return QuickSearchResponse(
        success=result.get("success", False),
        message=result.get("message", ""),
        search_url=search_url,
        browser=result.get("browser", request.browser),
    )