from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import random
import time
from typing import Any

from app.services.graph.state import AgentState, validate_task_plan_items
from app.services.graph.metrics import NodeMetrics, inc_counter

logger = logging.getLogger(__name__)

LLM_MODE = os.getenv("LLM_MODE", "mock")

TASK_STEP_MAX_RETRY = int(os.getenv("TASK_STEP_MAX_RETRY", "2"))
TASK_STEP_TIMEOUT_S = int(os.getenv("TASK_STEP_TIMEOUT_S", "300"))
TASK_MIN_OUTPUT_LEN = int(os.getenv("TASK_MIN_OUTPUT_LEN", "50"))
MAX_REMEDY_STEPS = int(os.getenv("MAX_REMEDY_STEPS", "3"))


def _get_traced_execution():
    try:
        from app.services.observability.tracing import traced_execution
        return traced_execution
    except Exception:
        from contextlib import contextmanager

        @contextmanager
        def _mock_span(span_name: str, attributes: dict[str, Any]):
            class Dummy:
                def set_attribute(self, *a, **kw):
                    pass
            yield Dummy()

        return _mock_span


async def _detect_intent(raw_query: str) -> tuple[str, float]:
    if LLM_MODE == "real":
        try:
            from app.services.llm.client import detect_intent_llm
            return await detect_intent_llm(raw_query)
        except Exception as e:
            logger.warning(f"LLM调用失败降级mock: {e}")
    return await _mock_detect_intent(raw_query)


async def _extract_entities(raw_query: str, intent: str) -> dict[str, Any]:
    if LLM_MODE == "real":
        try:
            from app.services.llm.client import extract_entities_llm
            return await extract_entities_llm(raw_query, intent)
        except Exception as e:
            logger.warning(f"LLM调用失败降级mock: {e}")
    return await _mock_extract_entities(raw_query, intent)


async def _route_via_llm(raw_query: str) -> tuple[str, dict[str, Any], float]:
    if LLM_MODE == "real":
        try:
            from app.services.llm.client import route_via_llm_real
            return await route_via_llm_real(raw_query)
        except Exception as e:
            logger.warning(f"LLM调用失败降级mock: {e}")
    return await _mock_route_via_llm(raw_query)


async def _rewrite_query_pipeline(raw_query: str, entities: dict) -> tuple[str, list[str]]:
    if LLM_MODE == "real":
        try:
            from app.services.llm.client import rewrite_query_pipeline_real
            return await rewrite_query_pipeline_real(raw_query, entities)
        except Exception as e:
            logger.warning(f"LLM调用失败降级mock: {e}")
    return await _mock_rewrite_query(raw_query, entities)


async def _mock_detect_intent(raw_query: str) -> tuple[str, float]:
    q = raw_query.lower()
    if "启动" in q or "打开" in q:
        return "app_launch", 0.92
    elif "结束" in q or "杀掉" in q:
        return "app_kill", 0.90
    return "unknown", 0.4


async def _mock_extract_entities(raw_query: str, intent: str) -> dict[str, Any]:
    return {"raw": raw_query, "hint": "mock_entities"}


async def _mock_route_via_llm(raw_query: str) -> tuple[str, dict[str, Any], float]:
    q = raw_query.lower()
    if "启动" in q or "打开" in q:
        return "app_launch_agent_node", {"action": "launch", "path": "C:\\Windows\\notepad.exe"}, 0.91
    elif "结束" in q or "杀掉" in q:
        return "app_launch_agent_node", {"action": "kill", "name": "notepad.exe"}, 0.88
    elif "监控" in q or "cpu" in q or "内存" in q or "进程" in q:
        return "system_monitor_agent_node", {"action": "overview"}, 0.85
    elif "清理" in q or "优化" in q or "垃圾" in q:
        return "system_clean_agent_node", {"action": "scan"}, 0.85
    elif "搜代码" in q or "找代码" in q or "code search" in q or "代码搜索" in q:
        return "code_search_node", {"query": raw_query, "search_type": ""}, 0.85
    elif "撰写" in q or "简报" in q or "报告" in q or "方案" in q:
        return "planning_node", {"task": raw_query}, 0.90
    elif "搭建" in q or "规划" in q or "面试" in q or "论文" in q or "材料" in q or "包" in q and "面试" in q:
        return "planning_node", {"task": raw_query}, 0.90
    elif "并行" in q or "对比摘要" in q:
        return "planning_node", {"task": raw_query}, 0.90
    elif "查文档" in q or "检索" in q or "知识库" in q or "rag" in q:
        return "rag_retrieve_node", {"query": raw_query}, 0.85
    elif "搜索" in q or "查一下" in q or "百度" in q:
        return "browser_agent_node", {"action": "search", "query": raw_query}, 0.85
    elif "安装" in q or "卸载" in q or "应用商店" in q:
        return "store_agent_node", {"action": "search", "query": raw_query}, 0.85
    elif "生成" in q or "写" in q or "创建项目" in q or "写代码" in q:
        return "content_gen_agent_node", {"action": "generate", "task": raw_query}, 0.85
    return "clarification_node", {}, 0.35


async def _mock_build_clarification_message(raw_query: str, intent: str, conf: float) -> dict[str, str]:
    return {"message": f"我没有理解你的指令，请重新描述。输入:{raw_query}，置信度{conf:.2f}"}


async def _mock_rewrite_query(raw_query: str, entities: dict) -> tuple[str, list[str]]:
    standalone = raw_query
    retrieval = [raw_query]
    if "记事本" in raw_query:
        standalone = "启动记事本应用程序"
        retrieval.append("启动记事本 notepad.exe")
    return standalone, retrieval


async def detect_intent_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("detect_intent"):
        traced_execution = _get_traced_execution()
        raw_query = state.get("raw_query", "")
        fb_mode = state.get("fast_brain_mode", "")
        fb_result = state.get("fast_brain_result", "")
        fb_confidence = state.get("fast_brain_confidence", 0.0)
        fb_intent = state.get("fast_brain_intent", "")
        try:
            review_hint = ""
            if fb_mode == "review_by_slow" and fb_result:
                review_hint = (
                    f"\n[快脑复核] 快脑初步判断: {fb_result}, "
                    f"置信度={fb_confidence:.2f}, 意图={fb_intent}。"
                    f"请优先校验快脑结论是否正确，可采纳、修正或推翻。"
                )
            with traced_execution("chat", {"gen_ai.operation.name": "chat", "gen_ai.node": "detect_intent", "gen_ai.user.query": raw_query[:200]}):
                intent, confidence = await _detect_intent(raw_query + review_hint)
            updates: dict[str, Any] = {"intent": intent, "intent_confidence": confidence}
            if fb_mode == "review_by_slow":
                updates["fast_brain_mode"] = "review_done"
            return updates
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"detect_intent异常:{str(e)}", "error_type": "business"}


async def extract_entities_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("extract_entities"):
        traced_execution = _get_traced_execution()
        raw_query = state.get("raw_query", "")
        intent = state.get("intent", "")
        try:
            with traced_execution("chat", {"gen_ai.node": "extract_entities"}):
                entities = await _extract_entities(raw_query, intent)
                standalone_q, retrieval_q_list = await _rewrite_query_pipeline(raw_query, entities)
            return {"entities": entities, "standalone_query": standalone_q, "retrieval_queries": retrieval_q_list}
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"extract_entities异常:{str(e)}", "error_type": "business"}


async def route_llm_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("route_llm"):
        traced_execution = _get_traced_execution()
        raw_query = state.get("raw_query", "")
        try:
            with traced_execution("chat", {"gen_ai.node": "route_llm"}):
                agent_name, agent_args, route_confidence = await _route_via_llm(raw_query)
            tool_search_q = agent_name.replace("_node", "").replace("_agent", "")
            return {
                "route_target": agent_name,
                "route_confidence": route_confidence,
                "agent_input": agent_args,
                "tool_search_query": tool_search_q,
            }
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"route_llm异常:{str(e)}", "error_type": "business"}


async def clarification_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("clarification_node"):
        inc_counter("graph_clarification_trigger_total")
        raw_query = state.get("raw_query", "")
        intent = state.get("intent", "")
        conf = state.get("intent_confidence", 0.0)
        try:
            msg = await _mock_build_clarification_message(raw_query, intent, conf)
            return {
                "needs_clarification": True,
                "clarification_message": msg["message"],
                # B6: 纯文本降级路径也提供结构化外壳（原因码 + 空选项按钮）
                "clarification_reason_code": "UNABLE_TO_PARSE",
                "clarification_options": [],
                "standalone_query": raw_query,
                "task_plan_enabled": False,
                "correction_signal": {},
            }
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"clarification异常:{str(e)}", "error_type": "business"}


async def risk_check_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("risk_check_node"):
        from app.services.graph.checkers import risk_check_node as _risk
        try:
            return _risk(state)
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"risk_check异常:{str(e)}", "error_type": "business"}


async def rag_retrieve_node(state: AgentState) -> dict[str, Any]:
    """
    RAG在线检索节点:
    R6: 向量+BM25混搭
    R7: 原查询永不替换
    R8: 鉴权前置ACL过滤
    R9: RRF重排+交叉编码器精排
    R10: 证据回溯+压幻觉
    R12: 矛盾片段检测
    """
    with NodeMetrics("rag_retrieve_node"):
        try:
            from app.services.rag import get_rag_service
            rag = get_rag_service()
            query = state.get("rag_query", "") or state.get("standalone_query", "") or state.get("raw_query", "")
            rewrite_queries = state.get("rag_rewrite_queries", [])
            user_acl = state.get("rag_user_acl", []) or (["admin"] if state.get("user_id", "") == "admin" else ["public"])
            result = await rag.query(
                query=query,
                user_acl_tags=user_acl,
                rewrite_queries=rewrite_queries if rewrite_queries else None,
                top_k=5,
                rerank_top_k=3,
                enable_rerank=False,
            )
            context_data = result.get("context", {})
            contradiction = result.get("contradiction", {})
            return {
                "rag_query": query,
                "rag_results": result.get("retrieval", {}).get("results", []),
                "rag_context": context_data.get("context", ""),
                "rag_evidence_ids": context_data.get("evidence_ids", []),
                "rag_evidence_map": result.get("retrieval", {}).get("evidence_map", {}),
                "rag_contradiction": contradiction,
                "rag_should_refuse": context_data.get("should_refuse", False),
                "evidence": {
                    "rag_context": context_data.get("context", "")[:500],
                    "rag_evidence_count": len(context_data.get("evidence_ids", [])),
                    "rag_contradiction": contradiction.get("has_contradiction", False),
                },
            }
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"rag_retrieve异常:{str(e)}", "error_type": "business"}


async def evolve_feedback_node(state: AgentState) -> dict[str, Any]:
    """
    自进化Agent节点:
    E1: 经验驱动 — 从任务反馈学习
    E2: 四类演化闭环
    E4: 评估/回滚/权限/供应链
    """
    with NodeMetrics("evolve_feedback_node"):
        try:
            from app.services.evolve import get_evolve_engine, EvolveLevel
            engine = get_evolve_engine()
            tool_result = state.get("tool_result", {})
            raw_query = state.get("raw_query", "")
            level = EvolveLevel(state.get("evolve_level", 1))
            record = engine.evolve_from_feedback(
                task_id=state.get("session_id", ""),
                task_result=tool_result,
                user_correction="",
                evaluation_score=1.0 if tool_result.get("ok") else 0.3,
                level=level,
            )
            context = engine.get_context_for_task(raw_query)
            return {
                "evolve_record_id": record.record_id,
                "evolve_level": int(record.level),
                "evolve_context": context,
                "evidence": {
                    "evolve_record_id": record.record_id,
                    "evolve_level": record.level.name,
                    "eval_passed": record.evaluation_passed,
                    "eval_score": record.evaluation_score,
                },
            }
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"evolve_feedback异常:{str(e)}", "error_type": "business"}


async def code_search_node(state: AgentState) -> dict[str, Any]:
    """
    智能代码搜索节点:
    S1: 搜索策略路由
    S2: 三类引擎(Glob/Grep/Semantic)
    S3: 权限检查+实时索引
    S7: 聚合输出
    """
    with NodeMetrics("code_search_node"):
        try:
            from app.services.code_search import get_code_search_service
            svc = get_code_search_service()
            query = state.get("raw_query", "")
            tool_args = state.get("tool_args", {})
            root_dir = tool_args.get("root_dir", ".")
            search_type = tool_args.get("search_type", "")
            file_glob = tool_args.get("file_glob", "")
            user_acl = ["admin"] if state.get("user_id", "") == "admin" else ["public"]
            result = await svc.search(
                query=query,
                root_dir=root_dir,
                search_type=search_type,
                file_glob=file_glob,
                max_results=20,
                user_acl=user_acl,
            )
            return {
                "code_search_type": result["search_type"],
                "code_search_results": result["results"],
                "code_search_stats": result["stats"],
                "evidence": {
                    "search_type": result["search_type"],
                    "result_count": len(result["results"]),
                    "stats": result["stats"],
                },
            }
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"code_search异常:{str(e)}", "error_type": "business"}


async def planning_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("planning_node"):
        raw_query = state.get("raw_query", "")
        intent = state.get("intent", "")
        route_target = state.get("route_target", "")
        try:
            if LLM_MODE == "real":
                from app.services.llm.client import plan_steps_llm
                is_multi, steps = await plan_steps_llm(raw_query, intent, route_target)
            else:
                is_multi, steps = _mock_plan_steps(raw_query, intent, route_target)
            if is_multi and steps:
                inc_counter("plan_multi_step_total")
                return {"is_multi_step": True, "plan_steps": steps, "current_step_index": 0, "step_results": []}
            return {"is_multi_step": False, "plan_steps": [], "current_step_index": 0}
        except Exception as e:
            logger.exception(e)
            return {"is_multi_step": False, "plan_steps": [], "current_step_index": 0}


def _mock_plan_steps(raw_query: str, intent: str, route_target: str) -> tuple[bool, list[dict[str, Any]]]:
    """ONLY FOR LOCAL DEBUG, REMOVE IN PROD
    Mock生成初始计划，全部清空agent/action字段，避免旧路由泄露到step_loop_node
    注意：撰写/简报/报告/方案/搭建/面试类query交由task_planner_node的task_plan_global_llm生成计划，
    此处返回空plan_steps，避免plan_steps覆盖task_plan_global_llm的mock返回值。
    """
    q = raw_query.lower()
    if any(k in q for k in ("撰写", "简报", "报告", "方案", "搭建", "面试", "材料包", "规划", "并行", "对比摘要")):
        return False, []
    if "写" in q or "生成" in q or "创建项目" in q:
        steps = [
            {"step_index": 0, "agent": "", "action": "", "description": f"搜索相关资料：{raw_query}", "depends_on": []},
            {"step_index": 1, "agent": "", "action": "", "description": f"根据资料生成内容：{raw_query}", "depends_on": [0]},
        ]
        return True, steps
    if ("查" in q or "搜索" in q) and ("装" in q or "安装" in q):
        steps = [
            {"step_index": 0, "agent": "", "action": "", "description": f"搜索相关信息：{raw_query}", "depends_on": []},
            {"step_index": 1, "agent": "", "action": "", "description": f"安装所需工具：{raw_query}", "depends_on": [0]},
        ]
        return True, steps
    if ("清理" in q or "优化" in q) and ("监控" in q or "查看" in q or "状态" in q):
        steps = [
            {"step_index": 0, "agent": "", "action": "", "description": "先查看系统状态", "depends_on": []},
            {"step_index": 1, "agent": "", "action": "", "description": "根据状态执行清理", "depends_on": [0]},
        ]
        return True, steps
    return False, []


async def step_loop_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("step_loop_node"):
        plan_steps = state.get("plan_steps", [])
        current_idx = state.get("current_step_index", 0)
        step_results = list(state.get("step_results", []))
        if current_idx >= len(plan_steps):
            return {"route_target": "memory_persist_node"}
        step = plan_steps[current_idx]
        agent = step.get("agent", "clarification_node")
        action = step.get("action", "")
        description = step.get("description", "")
        agent_input: dict[str, Any] = {"action": action, "_step_description": description}
        if current_idx > 0 and step_results:
            prev_result = step_results[-1]
            agent_input["_prev_step_result"] = prev_result
        if agent == "browser_agent_node":
            raw_query = state.get("raw_query", "")
            agent_input["query"] = raw_query
        elif agent == "rag_retrieve_node":
            raw_query = state.get("raw_query", "")
            agent_input["query"] = raw_query
        elif agent == "code_search_node":
            raw_query = state.get("raw_query", "")
            agent_input["query"] = raw_query
        elif agent == "content_gen_agent_node":
            raw_query = state.get("raw_query", "")
            agent_input["task"] = raw_query
            if current_idx > 0 and step_results:
                prev = step_results[-1]
                if isinstance(prev, dict) and "tool_result" in prev:
                    agent_input["_reference"] = str(prev["tool_result"])[:2000]
        elif agent == "store_agent_node":
            raw_query = state.get("raw_query", "")
            agent_input["query"] = raw_query
        inc_counter("step_loop_advance_total")
        return {
            "route_target": agent,
            "agent_input": agent_input,
            "tool_search_query": agent.replace("_agent_node", "").replace("_node", ""),
        }


def route_after_planning(state: AgentState) -> str:
    if state.get("task_plan_enabled", True):
        return "task_planner_node"
    if state.get("is_multi_step", False):
        return "step_loop_node"
    return "guard_pre_check"


def route_after_step_execute(state: AgentState) -> str:
    plan_steps = state.get("plan_steps", [])
    current_idx = state.get("current_step_index", 0)
    if state.get("last_error"):
        return "error_fallback_node"
    if current_idx >= len(plan_steps):
        return "memory_persist_node"
    return "step_loop_node"


async def app_launch_agent_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("app_launch_agent_node"):
        agent_input = dict(state.get("agent_input", {}))
        raw_query = state.get("raw_query", "")
        try:
            action = agent_input.get("action", "")
            if not action:
                q = raw_query.lower()
                if "结束" in q or "杀掉" in q or "关闭" in q or "关掉" in q:
                    action = "kill"
                else:
                    action = "launch"
            if action == "launch":
                tool_name = "app:launch"
                path = agent_input.get("path", "")
                if not path:
                    app_name = agent_input.get("app_name", agent_input.get("name", ""))
                    if app_name:
                        APP_EXE_MAP = {
                            "微信": "WeChat.exe", "记事本": "notepad.exe", "计算器": "calc.exe",
                            "画图": "mspaint.exe", "word": "WINWORD.EXE", "excel": "EXCEL.EXE",
                            "chrome": "chrome.exe", "edge": "msedge.exe", "vscode": "Code.exe",
                            "cursor": "Cursor.exe", "qq": "QQ.exe", "飞书": "Feishu.exe",
                            "钉钉": "DingTalk.exe", "wps": "wps.exe", "notepad": "notepad.exe",
                            "浏览器": "msedge.exe", "ppt": "POWERPNT.EXE", "powerpoint": "POWERPNT.EXE",
                        }
                        path = APP_EXE_MAP.get(app_name.lower(), app_name)
                tool_args = {"path": path}
            elif action == "kill":
                tool_name = "process:kill"
                name = agent_input.get("name", agent_input.get("app_name", ""))
                tool_args = {"name": name}
            else:
                logger.warning(f"app_launch_agent降级: 未知action={action}, 降级为launch")
                tool_name = "app:launch"
                tool_args = {"path": agent_input.get("path", agent_input.get("app_name", ""))}
            return {"tool_name": tool_name, "tool_args": tool_args}
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"app_launch_agent异常:{str(e)}", "error_type": "business"}


async def system_monitor_agent_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("system_monitor_agent_node"):
        agent_input = dict(state.get("agent_input", {}))
        try:
            action = agent_input.get("action", "overview")
            tool_name = "system:info"
            tool_args: dict[str, Any] = {"action": action}
            if action == "top_processes":
                tool_name = "process:top"
                tool_args = {"max": agent_input.get("max_processes", 10)}
            elif action == "disk_info":
                tool_name = "disk:list"
                tool_args = {}
            elif action == "overview":
                tool_name = "system:info"
                tool_args = {}
            return {"tool_name": tool_name, "tool_args": tool_args}
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"system_monitor_agent异常:{str(e)}", "error_type": "business"}


async def system_clean_agent_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("system_clean_agent_node"):
        agent_input = dict(state.get("agent_input", {}))
        try:
            action = agent_input.get("action", "scan")
            max_items = agent_input.get("max_items", 50)
            if action in ("cleanup", "scan_and_cleanup"):
                tool_name = "disk:cleanup"
                tool_args = {"max": max_items}
            else:
                tool_name = "temp:scan"
                tool_args = {"max": max_items}
            return {"tool_name": tool_name, "tool_args": tool_args}
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"system_clean_agent异常:{str(e)}", "error_type": "business"}


async def browser_agent_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("browser_agent_node"):
        agent_input = dict(state.get("agent_input", {}))
        try:
            action = agent_input.get("action", "search")
            if action in ("search", "query", "find", "lookup", "search_web", "web_search", "browse"):
                tool_name = "browser:search"
                tool_args = {"query": agent_input.get("query", "")}
            elif action in ("request", "http", "fetch"):
                tool_name = "network:request"
                tool_args = {"url": agent_input.get("url", ""), "method": agent_input.get("method", "GET")}
            else:
                logger.warning(f"browser_agent降级: 未知action={action}, 降级为search")
                tool_name = "browser:search"
                tool_args = {"query": agent_input.get("query", agent_input.get("task", ""))}
            return {"tool_name": tool_name, "tool_args": tool_args}
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"browser_agent异常:{str(e)}", "error_type": "business"}


async def store_agent_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("store_agent_node"):
        agent_input = dict(state.get("agent_input", {}))
        try:
            action = agent_input.get("action", "list")
            if action == "search":
                tool_name = "store:search"
                tool_args = {"query": agent_input.get("query", "")}
            elif action == "install":
                tool_name = "store:install"
                tool_args = {"package_id": agent_input.get("package_id", "")}
                if agent_input.get("app_name"):
                    tool_args["app_name"] = agent_input["app_name"]
            elif action == "uninstall":
                tool_name = "store:uninstall"
                tool_args = {"package_id": agent_input.get("package_id", "")}
            elif action == "list":
                tool_name = "store:list"
                tool_args = {}
            else:
                logger.warning(f"store_agent降级: 未知action={action}, 降级为search")
                tool_name = "store:search"
                tool_args = {"query": agent_input.get("query", agent_input.get("task", ""))}
            return {"tool_name": tool_name, "tool_args": tool_args}
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"store_agent异常:{str(e)}", "error_type": "business"}


async def content_gen_agent_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("content_gen_agent_node"):
        agent_input = dict(state.get("agent_input", {}))
        try:
            action = agent_input.get("action", "generate")
            if action in ("generate", "generate_and_open", "generate_code", "generate_document", "write", "create", "write_document", "write_paper", "compose", "draft"):
                tool_name = "content:generate"
                tool_args = {
                    "task": agent_input.get("task", ""),
                    "content_type": agent_input.get("content_type", "document"),
                    "auto_open": action == "generate_and_open",
                }
                for key in ("theme", "style", "length", "output_path"):
                    if agent_input.get(key):
                        tool_args[key] = agent_input[key]
            elif action == "ide_create":
                tool_name = "ide:launch"
                tool_args = {
                    "ide": agent_input.get("ide", "vscode"),
                    "action": "create_project",
                    "project_name": agent_input.get("project_name", "untitled"),
                }
            else:
                logger.warning(f"content_gen_agent降级: 未知action={action}, 降级为generate")
                tool_name = "content:generate"
                tool_args = {
                    "task": agent_input.get("task", ""),
                    "content_type": agent_input.get("content_type", "document"),
                    "auto_open": False,
                }
            return {"tool_name": tool_name, "tool_args": tool_args}
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"content_gen_agent异常:{str(e)}", "error_type": "business"}


async def image_agent_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("image_agent_node"):
        agent_input = dict(state.get("agent_input", {}))
        try:
            action = agent_input.get("action", "screenshot")
            if action in ("screenshot", "capture", "截图"):
                tool_name = "image:screenshot"
                tool_args = {
                    "region": agent_input.get("region", ""),
                    "output_path": agent_input.get("output_path", ""),
                }
            elif action in ("ocr", "recognize", "识别", "文字识别"):
                tool_name = "image:ocr"
                tool_args = {
                    "image_path": agent_input.get("image_path", ""),
                    "lang": agent_input.get("lang", "chi_sim+eng"),
                }
            elif action in ("understand", "理解", "语义", "图片理解", "描述图片", "看图"):
                tool_name = "image:understand"
                tool_args = {
                    "image_path": agent_input.get("image_path", ""),
                    "question": agent_input.get("question", agent_input.get("task", "")),
                }
            elif action in ("resize", "缩放", "调整大小"):
                tool_name = "image:resize"
                tool_args = {
                    "image_path": agent_input.get("image_path", ""),
                    "width": agent_input.get("width", 0),
                    "height": agent_input.get("height", 0),
                    "output_path": agent_input.get("output_path", ""),
                }
            elif action in ("crop", "裁剪"):
                tool_name = "image:crop"
                tool_args = {
                    "image_path": agent_input.get("image_path", ""),
                    "box": agent_input.get("box", ""),
                    "output_path": agent_input.get("output_path", ""),
                }
            elif action in ("convert", "转换", "格式转换"):
                tool_name = "image:convert"
                tool_args = {
                    "image_path": agent_input.get("image_path", ""),
                    "target_format": agent_input.get("target_format", "png"),
                    "output_path": agent_input.get("output_path", ""),
                }
            elif action in ("filter", "滤镜", "处理"):
                tool_name = "image:filter"
                tool_args = {
                    "image_path": agent_input.get("image_path", ""),
                    "filter_type": agent_input.get("filter_type", "grayscale"),
                    "output_path": agent_input.get("output_path", ""),
                }
            elif action in ("analyze", "分析", "图像分析"):
                tool_name = "image:analyze"
                tool_args = {
                    "image_path": agent_input.get("image_path", ""),
                    "analyze_type": agent_input.get("analyze_type", "histogram"),
                }
            elif action in ("read_qr", "二维码", "扫码"):
                tool_name = "image:read_qr"
                tool_args = {
                    "image_path": agent_input.get("image_path", ""),
                }
            elif action in ("compare", "对比", "比较"):
                tool_name = "image:compare"
                tool_args = {
                    "image_path_a": agent_input.get("image_path_a", ""),
                    "image_path_b": agent_input.get("image_path_b", ""),
                }
            else:
                logger.warning(f"image_agent降级: 未知action={action}, 降级为screenshot")
                tool_name = "image:screenshot"
                tool_args = {"region": agent_input.get("region", ""), "output_path": agent_input.get("output_path", "")}
            return {"tool_name": tool_name, "tool_args": tool_args}
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"image_agent异常:{str(e)}", "error_type": "business"}


async def algorithm_agent_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("algorithm_agent_node"):
        agent_input = dict(state.get("agent_input", {}))
        try:
            action = agent_input.get("action", "calculate")
            if action in ("calculate", "计算", "求值"):
                tool_name = "algo:calculate"
                tool_args = {
                    "expression": agent_input.get("expression", ""),
                }
            elif action in ("encrypt", "加密"):
                tool_name = "algo:encrypt"
                tool_args = {
                    "text": agent_input.get("text", ""),
                    "method": agent_input.get("method", "aes"),
                    "key": agent_input.get("key", ""),
                }
            elif action in ("decrypt", "解密"):
                tool_name = "algo:decrypt"
                tool_args = {
                    "text": agent_input.get("text", ""),
                    "method": agent_input.get("method", "aes"),
                    "key": agent_input.get("key", ""),
                }
            elif action in ("compress", "压缩"):
                tool_name = "algo:compress"
                tool_args = {
                    "source_path": agent_input.get("source_path", ""),
                    "output_path": agent_input.get("output_path", ""),
                    "format": agent_input.get("format", "zip"),
                }
            elif action in ("decompress", "解压", "解压缩"):
                tool_name = "algo:decompress"
                tool_args = {
                    "archive_path": agent_input.get("archive_path", ""),
                    "output_path": agent_input.get("output_path", ""),
                }
            elif action in ("convert_data", "数据转换", "格式转换"):
                tool_name = "algo:convert_data"
                tool_args = {
                    "input_path": agent_input.get("input_path", ""),
                    "input_format": agent_input.get("input_format", ""),
                    "output_format": agent_input.get("output_format", ""),
                    "output_path": agent_input.get("output_path", ""),
                }
            elif action in ("generate", "生成", "随机"):
                tool_name = "algo:generate"
                tool_args = {
                    "gen_type": agent_input.get("gen_type", "uuid"),
                    "count": agent_input.get("count", 1),
                }
            elif action in ("hash", "哈希", "摘要"):
                tool_name = "algo:hash"
                tool_args = {
                    "text": agent_input.get("text", ""),
                    "algorithm": agent_input.get("algorithm", "sha256"),
                }
            elif action in ("plot", "画图", "可视化", "绘图", "visualize", "chart", "graph"):
                tool_name = "algo:plot"
                tool_args = {
                    "data_path": agent_input.get("data_path", ""),
                    "chart_type": agent_input.get("chart_type", "bar"),
                    "title": agent_input.get("title", ""),
                    "output_path": agent_input.get("output_path", ""),
                }
            else:
                logger.warning(f"algorithm_agent降级: 未知action={action}, 降级为calculate")
                tool_name = "algo:calculate"
                tool_args = {"expression": agent_input.get("expression", agent_input.get("task", ""))}
            return {"tool_name": tool_name, "tool_args": tool_args}
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"algorithm_agent异常:{str(e)}", "error_type": "business"}


AGENT_NODE_MAP = {
    "app_launch_agent_node": "app_launch_agent_node",
    "system_monitor_agent_node": "system_monitor_agent_node",
    "system_clean_agent_node": "system_clean_agent_node",
    "browser_agent_node": "browser_agent_node",
    "store_agent_node": "store_agent_node",
    "content_gen_agent_node": "content_gen_agent_node",
    "image_agent_node": "image_agent_node",
    "algorithm_agent_node": "algorithm_agent_node",
    "rag_retrieve_node": "rag_retrieve_node",
    "code_search_node": "code_search_node",
}


async def agent_dispatch_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("agent_dispatch_node"):
        route_target = state.get("route_target", "")
        if route_target in AGENT_NODE_MAP:
            return {"route_target": route_target}
        intent = state.get("intent", "")
        q = state.get("raw_query", "").lower()
        if any(k in q for k in ("搜代码", "找代码", "code search", "代码搜索")):
            return {"route_target": "code_search_node"}
        if any(k in q for k in ("查文档", "检索", "知识库", "rag")):
            return {"route_target": "rag_retrieve_node"}
        if any(k in q for k in ("写", "生成", "创建", "论文", "文档")):
            return {"route_target": "content_gen_agent_node"}
        if any(k in q for k in ("搜索", "查", "资料")):
            return {"route_target": "browser_agent_node"}
        logger.warning(f"agent_dispatch: 未知route_target={route_target}，降级到content_gen")
        return {"route_target": "content_gen_agent_node"}


def route_after_dispatch(state: AgentState) -> str:
    return state.get("route_target", "app_launch_agent_node")


async def tool_execute_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("tool_execute_node"):
        traced_execution = _get_traced_execution()

        tool_name = state.get("tool_name", "")
        tool_args = state.get("tool_args", {})
        args_hash = hashlib.sha256(str(tool_args).encode()).hexdigest()[:16]
        try:
            with traced_execution("execute_tool", {"gen_ai.tool.name": tool_name, "gen_ai.tool.args_hash": args_hash}) as span:
                from app.services.tools.executor import _execute_single_tool
                result = await _execute_single_tool(tool_name, tool_args)
                span.set_attribute("gen_ai.tool.ok", str(result.get("ok")))
            updates = {"tool_result": result}
            if not result.get("ok"):
                updates["last_error"] = result.get("error", "unknown error")
            return updates
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"tool_execute异常:{str(e)}", "error_type": "business"}


async def step_collect_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("step_collect_node"):
        is_multi = state.get("is_multi_step", False)
        if not is_multi:
            return {}
        current_idx = state.get("current_step_index", 0)
        step_results = list(state.get("step_results", []))
        tool_result = state.get("tool_result", {})
        tool_name = state.get("tool_name", "")
        step_results.append({
            "step_index": current_idx,
            "tool_name": tool_name,
            "tool_result": tool_result,
        })
        next_idx = current_idx + 1
        return {"step_results": step_results, "current_step_index": next_idx}


def route_after_tool_exec_or_step(state: AgentState) -> str:
    is_multi = state.get("is_multi_step", False)
    if is_multi:
        task_plan_status = state.get("task_plan_status", "")
        if task_plan_status in ("executing", "planning", "blocked"):
            return "task_plan_collect_node"
        return "step_collect_node"
    err = state.get("last_error")
    auto_diag = state.get("enable_auto_diagnose", False)
    if err and auto_diag:
        return "supervisor_diagnose_node"
    return "post_validate_gate"


async def post_validate_gate_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("post_validate_gate_node"):
        from app.services.graph.checkers import post_validate_gate
        try:
            return post_validate_gate(state)
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"validate_gate异常:{str(e)}", "error_type": "business"}


async def error_fallback_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("error_fallback_node"):
        inc_counter("fallback_triggered_total")
        err = state.get("last_error", "未知错误")
        return {"tool_result": {
            "status": "error",
            "summary": f"任务降级: {err}",
            "data": {"ok": False, "error": err, "fallback": True},
            "meta": {"hit_count": 0, "missing_info": [], "confidence": 0.0},
            "error": {"type": state.get("error_type", "execution"), "suggestion": "任务执行失败，已降级处理"},
            "fallback": True,
        }}


async def memory_persist_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("memory_persist_node"):
        from app.services.graph.memory_store import (
            EVIDENCE_LEVEL_A,
            EVIDENCE_LEVEL_B,
            EVIDENCE_LEVEL_C,
            EVIDENCE_LEVEL_D,
            get_memory_store,
        )

        store = get_memory_store()
        raw_query = state.get("raw_query", "")
        standalone_query = state.get("standalone_query", "")
        retrieval_queries = state.get("retrieval_queries", [])
        trace_id = state.get("trace_id", "")
        tool_name = state.get("tool_name", "")
        tool_args = state.get("tool_args", {})
        tool_result = state.get("tool_result", {})
        user_id = state.get("user_id") or state.get("session_id", "default")

        try:
            store.put_evidence_a(user_id, raw_query, tool_result, trace_id)
            args_hash = hashlib.sha256(str(tool_args).encode()).hexdigest()[:16]
            store.put_evidence_b(user_id, tool_name, args_hash, tool_result, trace_id)

            ts = int(time.time() * 1000)
            store.put(
                user_id,
                key=f"user_utterance_C_{ts}",
                value={"raw_query": raw_query, "trace_id": trace_id},
                level=EVIDENCE_LEVEL_C,
                owner="user",
            )

            model_inference = {
                k: state.get(k)
                for k in ("intent", "intent_confidence", "standalone_query",
                          "retrieval_queries", "route_target", "route_confidence")
                if state.get(k) not in (None, "", [])
            }
            if model_inference:
                store.put(
                    user_id,
                    key=f"model_inference_D_{ts}",
                    value=model_inference,
                    level=EVIDENCE_LEVEL_D,
                    owner="llm",
                )

            # M15/H13 执行闭环：把独立验证结果(completion_evidence/task_verified)作为
            # C级"系统实证"证据落盘，后续任务可读取，避免世界模型只存"以为的结果"。
            completion_evidence = state.get("completion_evidence", {}) or {}
            task_verified = bool(state.get("task_verified", False))
            if completion_evidence:
                store.put(
                    user_id,
                    key=f"task_verification_C_{ts}",
                    value={
                        "tool_name": tool_name,
                        "task_verified": task_verified,
                        "evidence_level": completion_evidence.get("evidence_level", ""),
                        "source": completion_evidence.get("source", ""),
                        "checks": completion_evidence.get("checks", {}),
                        "trace_id": trace_id,
                    },
                    level=EVIDENCE_LEVEL_C,
                    owner="system",
                )
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"memory_persist异常:{str(e)}", "error_type": "business"}

        evidence = {
            "raw_query": raw_query,
            "standalone_query": standalone_query,
            "retrieval_queries": retrieval_queries,
            "intent": state.get("intent"),
            "tool_name": tool_name,
            "tool_result_ok": tool_result.get("ok", False),
            "task_verified": bool(state.get("task_verified", False)),
            "completion_evidence": state.get("completion_evidence", {}) or {},
            "timestamp": time.time(),
        }

        return {"evidence": evidence}


async def tool_search_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("tool_search_node"):
        from app.services.graph.tool_search import tool_search_instance

        q = state.get("tool_search_query", "")
        retrieval_queries = state.get("retrieval_queries", [])
        search_terms = [q] if q and q.strip() else []
        for rq in retrieval_queries:
            if rq and rq.strip() and rq not in search_terms:
                search_terms.append(rq)

        if not search_terms:
            return {"tool_search_hit_list": [], "tool_loaded_schema": tool_search_instance.get_current_loaded_schema()}

        seen_names: set[str] = set()
        hit_names: list[str] = []
        for term in search_terms:
            hits = tool_search_instance.search_tool(term, top_k=3)
            for h in hits:
                if h.name not in seen_names:
                    seen_names.add(h.name)
                    hit_names.append(h.name)
                    tool_search_instance.load_tool_schema(h.name)

        loaded_schema = tool_search_instance.get_current_loaded_schema()
        inc_counter("tool_search_invoked_total")
        if len(hit_names) == 0:
            inc_counter("tool_search_zero_hit_total")

        return {"tool_search_hit_list": hit_names, "tool_loaded_schema": loaded_schema, "tool_search_query": ""}


async def governor_scan_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("governor_scan_node"):
        from app.services.graph.memory_store import get_governing_store, SIGNAL_STATUS_OPEN, SIGNAL_STATUS_PROCESSING, SIGNAL_STATUS_RESOLVED

        mem_store = get_governing_store()
        trigger = state.get("governor_trigger", "")
        user_id = state.get("session_id", "default")
        scan_res = None
        try:
            open_signals = mem_store.get_open_signals(user_id)
            if open_signals:
                logger.info(f"Governor: 发现 {len(open_signals)} 个待处理校正信号")
                for sig in open_signals[:3]:
                    sig_id = sig.get("signal_id", "")
                    mem_store.update_signal_status(sig_id, SIGNAL_STATUS_PROCESSING, owner="governor", comment="自动认领处理")
                    sig_type = sig.get("signal_type", "")
                    if sig_type == "pollution":
                        related = sig.get("related_keys", [])
                        for rk in related:
                            mem_store.delete(user_id, rk)
                        mem_store.update_signal_status(sig_id, SIGNAL_STATUS_RESOLVED, owner="governor", comment="污染记忆已清除")
                        logger.info(f"Governor: 处理污染信号 {sig_id}, 清除 {len(related)} 条记忆")
                    elif sig_type == "conflict":
                        mem_store.update_signal_status(sig_id, SIGNAL_STATUS_RESOLVED, owner="governor", comment="冲突信号已标记")
                        logger.info(f"Governor: 处理冲突信号 {sig_id}")
                    else:
                        mem_store.update_signal_status(sig_id, SIGNAL_STATUS_RESOLVED, owner="governor", comment="未知信号类型，直接关闭")

            if trigger == "full":
                scan_res = mem_store.full_scan(user_id=user_id)
                inc_counter("governor_full_scan_total")
            elif trigger == "light":
                scan_res = mem_store.put_memory(user_id, "governor_light_scan", {"trigger": "light"}, evidence_level="C", source="governor_light_scan")
                inc_counter("governor_light_scan_total")
            if scan_res and (len(scan_res.get("conflict", [])) > 0 or len(scan_res.get("expired", [])) > 0):
                inc_counter("governor_signal_generated_total")
                inc_counter("signal_status_open_total")
            return {"governor_scan_result": scan_res or {}, "governor_trigger": ""}
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"governor_scan异常:{str(e)}", "error_type": "business"}


async def supervisor_diagnose_node(state: AgentState) -> dict[str, Any]:
    with NodeMetrics("supervisor_diagnose_node"):
        from app.services.graph.memory_store import get_governing_store

        mem_store = get_governing_store()
        trace_id = state.get("diagnose_trace_id", "")
        user_id = state.get("session_id", "default")
        enable_auto = state.get("enable_auto_diagnose", False)
        last_error = state.get("last_error", "")
        sig_id = ""
        try:
            if enable_auto and trace_id and last_error:
                elow = last_error.lower()
                if any(k in elow for k in ("intent", "route", "confidence")):
                    sig_id = mem_store.generate_correction_signal(user_id, "pollution", [], f"Supervisor诊断 trace_id={trace_id},err={last_error}")
                    inc_counter("supervisor_diagnose_signal_total")
            return {"correction_signal_id": sig_id, "correction_signal_status": "open" if sig_id else "", "diagnose_trigger": False}
        except Exception as e:
            logger.exception(e)
            return {"last_error": f"supervisor_diagnose异常:{str(e)}", "error_type": "business"}


async def rewrite_agent_input_node(state: AgentState) -> dict[str, Any]:
    """
    自校正循环节点：拿到上一轮error信息，让LLM重写agent_input
    埋点：触发、成功、超时；失败自动生成pollution类型correction_signal
    """
    with NodeMetrics("rewrite_agent_input_node"):
        import asyncio as _asyncio

        from app.services.graph.memory_store import get_governing_store

        mem_store = get_governing_store()
        traced_execution = _get_traced_execution()
        raw_query = state.get("raw_query", "")
        old_agent_input = state.get("agent_input", {})
        last_err = state.get("last_error", "")
        user_id = state.get("user_id") or state.get("session_id", "default")
        loop_cnt = state.get("correction_loop_count", 0)
        new_loop = loop_cnt + 1

        correction_start = state.get("correction_start_time", 0)
        if correction_start == 0:
            correction_start = time.time()
        correction_timeout_s = float(os.getenv("CORRECTION_LOOP_TIMEOUT_S", "30"))
        if time.time() - correction_start > correction_timeout_s:
            NodeMetrics.count_correction_timeout()
            return {
                "correction_loop_count": new_loop,
                "correction_reason": f"correction loop total timeout ({correction_timeout_s}s)",
                "last_error": f"自校正超时({correction_timeout_s}s)，停止循环",
                "error_type": "business",
            }

        NodeMetrics.count_correction_trigger()

        import yaml
        cfg_path = os.getenv("SECURITY_CONFIG_PATH", "config/security.yaml")
        rewrite_timeout = 10.0
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    sec_cfg = yaml.safe_load(f)
                    rewrite_timeout = float(sec_cfg.get("llm_rewrite_timeout", 10.0))
            except Exception:
                pass

        try:
            with traced_execution("chat", {"gen_ai.node": "rewrite_agent_input"}):
                if LLM_MODE == "real":
                    from app.services.llm.client import rewrite_agent_input_llm
                    new_agent_input = await rewrite_agent_input_llm(
                        raw_query, old_agent_input, last_err,
                        rewrite_timeout=rewrite_timeout,
                    )
                else:
                    new_agent_input = old_agent_input

            NodeMetrics.count_correction_success()
            return {
                "agent_input": new_agent_input,
                "correction_loop_count": new_loop,
                "correction_reason": last_err,
                "correction_start_time": correction_start,
                "last_error": None,
                "error_type": "",
            }

        except _asyncio.TimeoutError:
            NodeMetrics.count_correction_timeout()
            sig_id = mem_store.generate_correction_signal(
                user_id=user_id,
                signal_type="pollution",
                related_keys=[],
                detail=f"自校正LLM重写超时，loop={loop_cnt}, raw_query={raw_query}, error={last_err}",
            )
            return {
                "correction_loop_count": new_loop,
                "correction_reason": f"rewrite timeout: {last_err}",
                "correction_signal_id": sig_id,
                "correction_signal_status": "open",
                "last_error": "rewrite_agent_input: llm rewrite timeout",
                "error_type": "business",
            }

        except Exception as e:
            logger.exception(f"rewrite_agent_input_node exception {e}")
            sig_id = mem_store.generate_correction_signal(
                user_id=user_id,
                signal_type="pollution",
                related_keys=[],
                detail=f"自校正重写异常，loop={loop_cnt}, raw_query={raw_query}, exc={str(e)}",
            )
            return {
                "correction_loop_count": new_loop,
                "correction_reason": last_err,
                "correction_signal_id": sig_id,
                "correction_signal_status": "open",
                "last_error": f"rewrite_agent_input异常:{str(e)}",
                "error_type": "business",
            }


def _render_task_plan_md(items: list[dict[str, Any]]) -> str:
    lines = ["## 📋 任务规划清单"]
    for item in items:
        idx = item.get("step_index", 0)
        status = item.get("status", "pending")
        priority = item.get("priority", "P1")
        desc = item.get("description", "")
        depends = item.get("depends_on", [])
        deliverable = item.get("deliverable", "")
        dep_str = str(depends) if depends else "无"
        if status == "done":
            mark = "[x]"
        elif status == "blocked":
            mark = "[-]"
        else:
            mark = "[ ]"
        line = f"- {mark} ({priority}) 任务{idx}: {desc} | 依赖：{dep_str} | 交付物：{deliverable}"
        if status == "blocked" and item.get("blocked_reason"):
            line += f" 【阻塞：{item['blocked_reason']}】"
        lines.append(line)
    return "\n".join(lines)


def _find_next_executable(items: list[dict[str, Any]]) -> int | None:
    done_indices = {it["step_index"] for it in items if it.get("status") == "done"}
    pending = [it for it in items if it.get("status") == "pending"]
    if not pending:
        return None
    pending.sort(key=lambda x: (0 if x.get("priority") == "P0" else 1 if x.get("priority") == "P1" else 2, x.get("step_index", 0)))
    for it in pending:
        deps = it.get("depends_on", [])
        if all(d in done_indices for d in deps):
            return it["step_index"]
    return None


async def task_planner_node(state: AgentState) -> dict[str, Any]:
    """
    Task-Planner 规划-分步执行-迭代交付节点（LLM驱动版）
    - 首次进入: 调用LLM生成全局总计划(task_plan_global_llm)
    - 后续进入: 找到第一个pending任务 → 调用LLM生成本轮子计划(task_plan_sub_plan_llm)
               → 调用LLM执行子计划产出内容(task_execute_llm) → 标记完成
    - 全部完成: 标记completed, 汇总交付物
    """
    with NodeMetrics("task_planner_node"):
        state["route_target"] = ""
        plan_enabled = state.get("task_plan_enabled", True)
        if not plan_enabled:
            return {"route_target": ""}

        items = validate_task_plan_items(list(state.get("task_plan_items", [])))
        plan_status = state.get("task_plan_status", "")
        plan_steps = state.get("plan_steps", [])
        history_log = list(state.get("history_log", []))
        raw_query = state.get("raw_query", "")

        # ========== 首次进入：生成全局总计划 ==========
        if not items and plan_steps:
            items = []
            for step in plan_steps:
                items.append({
                    "step_index": step.get("step_index", 0),
                    "agent": "",
                    "action": "",
                    "description": step.get("description", ""),
                    "depends_on": step.get("depends_on", []),
                    "priority": step.get("priority", "P1"),
                    "deliverable": step.get("deliverable", ""),
                    "status": "pending",
                    "retry_count": 0,
                })
            items = validate_task_plan_items(items)
            md = _render_task_plan_md(items)
            logger.info(f"Task-Planner: 从plan_steps生成规划清单\n{md}")
            inc_counter("task_plan_created_total")
            history_log.append("plan_global: 从plan_steps创建全局任务计划")
            return {
                "task_plan_items": items,
                "task_plan_status": "planning",
                "task_plan_current_idx": 0,
                "task_plan_results": [],
                "history_log": history_log,
                "memory_summary": md,
                "route_target": "",
            }

        if not items and not plan_steps:
            try:
                from app.services.llm.client import task_plan_global_llm
                global_items = await asyncio.wait_for(
                    task_plan_global_llm(raw_query),
                    timeout=TASK_STEP_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                logger.warning(f"task_plan_global_llm超时({TASK_STEP_TIMEOUT_S}s), 降级到单步执行")
                global_items = []
            except Exception as e:
                logger.warning(f"task_plan_global_llm失败, 降级到plan_steps: {e}")
                global_items = []
            if global_items:
                items = []
                for idx, gi in enumerate(global_items):
                    items.append({
                        "step_index": gi.get("step_index", idx + 1),
                        "agent": "",
                        "action": "",
                        "description": gi.get("description", ""),
                        "depends_on": [],
                        "priority": "P1",
                        "deliverable": gi.get("expected_output", ""),
                        "expected_output": gi.get("expected_output", ""),
                        "status": "pending",
                        "retry_count": 0,
                    })
                items = validate_task_plan_items(items)
                md = _render_task_plan_md(items)
                logger.info(f"Task-Planner: LLM生成全局计划\n{md}")
                inc_counter("task_plan_created_total")
                history_log.append("plan_global: LLM创建全局任务计划")
                return {
                    "task_plan_items": items,
                    "task_plan_status": "planning",
                    "task_plan_current_idx": 0,
                    "task_plan_results": [],
                    "history_log": history_log,
                    "memory_summary": md,
                    "route_target": "",
                }
            logger.warning("Task-Planner: 全局计划生成失败, 降级到单步执行")
            return {
                "task_plan_status": "completed",
                "all_finished": True,
                "route_target": "",
            }

        if plan_status == "completed":
            return {"route_target": ""}

        # ========== 找到第一个pending任务 ==========
        pending_items = [it for it in items if it.get("status") == "pending"]
        if not pending_items:
            all_done = all(it.get("status") in ("done", "completed", "failed") for it in items)
            if all_done:
                results = list(state.get("task_plan_results", []))
                md = _render_task_plan_md(items)
                summary = f"✅ 全部任务执行完毕\n\n{md}\n\n交付物汇总：\n"
                for it in items:
                    if it.get("deliverable") or it.get("expected_output"):
                        summary += f"  - 任务{it['step_index']}: {it.get('deliverable') or it.get('expected_output')}\n"
                failed_items = [it for it in items if it.get("status") == "failed"]
                if failed_items:
                    summary += f"\n⚠️ 失败任务：\n"
                    for it in failed_items:
                        summary += f"  - 任务{it['step_index']}: {it.get('blocked_reason', 'unknown')}\n"
                logger.info(summary)
                inc_counter("task_plan_completed_total")
                history_log.append("plan_global: 全部任务完成")
                return {
                    "task_plan_status": "completed",
                    "all_finished": True,
                    "history_log": history_log,
                    "memory_summary": summary,
                    "route_target": "",
                }
            blocked_items = [it for it in items if it.get("status") == "blocked"]
            if blocked_items:
                md = _render_task_plan_md(items)
                return {
                    "task_plan_items": items,
                    "task_plan_status": "blocked",
                    "history_log": history_log,
                    "memory_summary": md,
                    "route_target": "",
                }
            return {"task_plan_status": "completed", "all_finished": True, "route_target": ""}

        target_item = pending_items[0]
        next_idx = target_item["step_index"]
        description = target_item.get("description", "")
        expected_output = target_item.get("expected_output", target_item.get("deliverable", ""))
        step_retry = target_item.get("retry_count", 0)

             # ========== 生成本轮子执行计划（带重试熔断） ==========
        sub_plan = {"target": description, "steps": []}
        sub_plan_ok = False
        for attempt in range(TASK_STEP_MAX_RETRY + 1):
            try:
                from app.services.llm.client import task_plan_sub_plan_llm
                sub_plan = await asyncio.wait_for(
                    task_plan_sub_plan_llm(
                        {"step_index": next_idx, "description": description, "expected_output": expected_output},
                        history_log,
                    ),
                    timeout=TASK_STEP_TIMEOUT_S,
                )
                sub_plan_ok = True
                break
            except asyncio.TimeoutError:
                logger.warning(f"task_plan_sub_plan_llm超时 attempt={attempt+1}/{TASK_STEP_MAX_RETRY+1} step={next_idx}")
                inc_counter("task_plan_step_timeout_total")
            except Exception as e:
                logger.warning(f"task_plan_sub_plan_llm失败 attempt={attempt+1}/{TASK_STEP_MAX_RETRY+1} step={next_idx}: {e}")
            if attempt < TASK_STEP_MAX_RETRY:
                await asyncio.sleep(2 * (attempt + 1) + random.uniform(0, 1))
        if not sub_plan_ok:
            sub_plan = {"target": description, "steps": []}
            logger.warning(f"Task-Planner: 子计划生成全部重试失败 step={next_idx}, 降级为空子计划继续执行")
        history_log.append(f"plan_step: 生成子计划，目标={sub_plan.get('target', description)}")
        # ========== 执行子计划（带重试熔断） ==========
        results = list(state.get("task_plan_results", []))
        agent_result = ""
        exec_ok = False
        for attempt in range(TASK_STEP_MAX_RETRY + 1):
            try:
                from app.services.llm.client import task_execute_llm
                agent_result = await asyncio.wait_for(
                    task_execute_llm(description, sub_plan, expected_output, results),
                    timeout=TASK_STEP_TIMEOUT_S,
                )
                if len(agent_result) >= TASK_MIN_OUTPUT_LEN:
                    exec_ok = True
                    break
                logger.warning(f"task_execute_llm产出过短({len(agent_result)}<{TASK_MIN_OUTPUT_LEN}), attempt={attempt+1}")
            except asyncio.TimeoutError:
                logger.warning(f"task_execute_llm超时 attempt={attempt+1}/{TASK_STEP_MAX_RETRY+1} step={next_idx}")
                inc_counter("task_plan_step_timeout_total")
            except Exception as e:
                logger.warning(f"task_execute_llm失败 attempt={attempt+1}/{TASK_STEP_MAX_RETRY+1} step={next_idx}: {e}")
            if attempt < TASK_STEP_MAX_RETRY:
                await asyncio.sleep(2 * (attempt + 1) + random.uniform(0, 1))
        # ========== 更新任务状态：成功/失败熔断 ==========
        for it in items:
            if it["step_index"] == next_idx:
                if exec_ok:
                    it["status"] = "completed"
                    it["retry_count"] = 0
                else:
                    it["retry_count"] = step_retry + 1
                    if it["retry_count"] > TASK_STEP_MAX_RETRY:
                        it["status"] = "failed"
                        it["blocked_reason"] = f"执行重试{it['retry_count']}次仍失败, 熔断跳过"
                        logger.warning(f"Task-Planner: 任务{next_idx}熔断跳过, retry_count={it['retry_count']}")
                        inc_counter("task_plan_step_max_retry_total")
                    else:
                        it["status"] = "pending"
                        logger.warning(f"Task-Planner: 任务{next_idx}执行失败, retry_count={it['retry_count']}, 下轮重试")
                break

        results.append({
            "step_index": next_idx,
            "tool_name": "llm:execute",
            "tool_result": {"ok": exec_ok, "content_length": len(agent_result), "data": agent_result[:500] if exec_ok else ""},
        })

        history_log.append(f"execute_step: {'成功' if exec_ok else '失败'} 产出长度{len(agent_result)}")

        # ========== 工具调用触发：根据任务描述/预期输出判断是否需要调用工具 ==========
        tool_call_result = None
        if exec_ok:
            desc_lower = description.lower()
            output_lower = expected_output.lower()
            need_file_gen = any(k in desc_lower or k in output_lower for k in (
                "生成文档", "生成文件", "word", "ppt", "html", "文档", "材料包", "面试材料",
                "简历", "架构图", "mermaid", "流程图",
            ))
            need_plot = any(k in desc_lower or k in output_lower for k in (
                "绘图", "画图", "可视化", "图表", "柱状图", "折线图", "饼图", "chart", "plot",
            ))
            need_image = any(k in desc_lower or k in output_lower for k in (
                "截图", "截屏", "screenshot",
            ))
            if need_file_gen:
                tool_name_triggered = "content:generate"
                content_type = "word" if "word" in output_lower else "ppt" if "ppt" in output_lower else "html" if "html" in output_lower else "document"
                tool_args_triggered = {"task": description, "content_type": content_type}
                tool_call_result = {"tool_name": tool_name_triggered, "tool_args": tool_args_triggered}
                history_log.append(f"tool_trigger: 任务{next_idx}触发content:generate, content_type={content_type}")
            elif need_plot:
                tool_name_triggered = "algo:plot"
                chart_type = "bar"
                if "折线" in desc_lower or "折线" in output_lower or "line" in desc_lower:
                    chart_type = "line"
                elif "饼" in desc_lower or "饼" in output_lower or "pie" in desc_lower:
                    chart_type = "pie"
                tool_args_triggered = {"chart_type": chart_type, "title": description[:100]}
                tool_call_result = {"tool_name": tool_name_triggered, "tool_args": tool_args_triggered}
                history_log.append(f"tool_trigger: 任务{next_idx}触发algo:plot, chart_type={chart_type}")
            elif need_image:
                tool_name_triggered = "image:screenshot"
                tool_args_triggered = {"region": "", "output_path": ""}
                tool_call_result = {"tool_name": tool_name_triggered, "tool_args": tool_args_triggered}
                history_log.append(f"tool_trigger: 任务{next_idx}触发image:screenshot")

        if tool_call_result and exec_ok:
            try:
                from app.services.tools.executor import _execute_single_tool
                _tr = await _execute_single_tool(
                    tool_call_result["tool_name"], tool_call_result["tool_args"]
                )
                tool_call_result["tool_result"] = _tr
                history_log.append(f"tool_exec: {tool_call_result['tool_name']} ok={_tr.get('ok')}")
            except Exception as _te:
                tool_call_result["tool_result"] = {"ok": False, "error": str(_te)}
                history_log.append(f"tool_exec: {tool_call_result['tool_name']} error={str(_te)[:200]}")

        remaining = [it for it in items if it.get("status") == "pending"]
        all_done = len(remaining) == 0

        md = _render_task_plan_md(items)
        if all_done:
            summary = f"✅ 全部任务执行完毕\n\n{md}\n\n交付物汇总：\n"
            for it in items:
                if it.get("deliverable") or it.get("expected_output"):
                    summary += f"  - 任务{it['step_index']}: {it.get('deliverable') or it.get('expected_output')}\n"
            failed_items = [it for it in items if it.get("status") == "failed"]
            if failed_items:
                summary += f"\n⚠️ 失败任务：\n"
                for it in failed_items:
                    summary += f"  - 任务{it['step_index']}: {it.get('blocked_reason', 'unknown')}\n"
            logger.info(summary)
            inc_counter("task_plan_completed_total")
            history_log.append("plan_global: 全部任务完成")
            return {
                "task_plan_items": items,
                "task_plan_current_idx": next_idx,
                "task_plan_results": results,
                "task_plan_status": "completed",
                "all_finished": True,
                "agent_result": agent_result,
                "current_sub_plan": sub_plan,
                "history_log": history_log,
                "memory_summary": summary,
                "tool_name": tool_call_result["tool_name"] if tool_call_result else "",
                "tool_args": tool_call_result["tool_args"] if tool_call_result else {},
                "tool_result": tool_call_result.get("tool_result", {}) if tool_call_result else {},
                "route_target": "",
            }

        logger.info(f"🔁 Task-Planner: 任务{next_idx}{'完成' if exec_ok else '失败'}, 还有{len(remaining)}项待执行\n{md}")
        inc_counter("task_plan_step_exec_total")
        return {
            "task_plan_items": items,
            "task_plan_current_idx": next_idx,
            "task_plan_results": results,
            "task_plan_status": "executing",
            "agent_result": agent_result,
            "current_sub_plan": sub_plan,
            "history_log": history_log,
            "memory_summary": md,
            "tool_name": tool_call_result["tool_name"] if tool_call_result else "",
            "tool_args": tool_call_result["tool_args"] if tool_call_result else {},
            "tool_result": tool_call_result.get("tool_result", {}) if tool_call_result else {},
            "route_target": "",
        }


async def task_plan_collect_node(state: AgentState) -> dict[str, Any]:
    """
    Task-Planner 步骤收集: 执行完一步后校验交付物有效性, 标记done/blocked, 回到task_planner_node继续
    校验规则:
      1. tool_result.ok=False → blocked
      2. tool_result.degraded=True → blocked(降级检测)
      3. 交付物有效性: content_length<200 → blocked(疑似占位输出)
      4. 前置依赖交付物无效 → 后续任务blocked
    """
    with NodeMetrics("task_plan_collect_node"):
        items = list(state.get("task_plan_items", []))
        current_idx = state.get("task_plan_current_idx", 0)
        results = list(state.get("task_plan_results", []))
        tool_result = state.get("tool_result", {})
        tool_name = state.get("tool_name", "")

        results.append({
            "step_index": current_idx,
            "tool_name": tool_name,
            "tool_result": tool_result,
        })

        for it in items:
            if it["step_index"] == current_idx:
                if it.get("status") == "failed":
                    logger.info(f"Task-Planner: 任务{current_idx}已是failed状态, 跳过collect处理")
                    break
                is_ok = tool_result.get("ok", False)
                is_degraded = tool_result.get("degraded", False)
                degradation_type = tool_result.get("degradation_type", "")
                content_length = tool_result.get("content_length", 0)
                warning = tool_result.get("warning", "")

                if not is_ok:
                    err = tool_result.get("error", "unknown")
                    it["retry_count"] = it.get("retry_count", 0) + 1
                    if it["retry_count"] > TASK_STEP_MAX_RETRY:
                        it["status"] = "failed"
                        it["blocked_reason"] = f"执行失败(重试{it['retry_count']}次): {err}"
                        logger.warning(f"Task-Planner: 任务{current_idx}重试耗尽, 标记failed, retry_count={it['retry_count']}")
                    else:
                        it["status"] = "blocked"
                        it["blocked_reason"] = f"执行失败: {err}"
                        logger.warning(f"Task-Planner: 任务{current_idx}执行失败: {err}, retry_count={it['retry_count']}")
                    remedy_count = sum(1 for x in items if "解决任务" in x.get("description", "") or "修复任务" in x.get("description", ""))
                    if remedy_count < MAX_REMEDY_STEPS:
                        new_idx = max(x["step_index"] for x in items) + 1 if items else 0
                        items.append({
                            "step_index": new_idx,
                            "agent": "clarification_node",
                            "action": "clarify",
                            "description": f"解决任务{current_idx}执行失败: {err}",
                            "depends_on": [],
                            "priority": "P0",
                            "deliverable": f"修复任务{current_idx}",
                            "status": "pending",
                        })
                    else:
                        logger.warning(f"Task-Planner: 补救步骤已达上限({MAX_REMEDY_STEPS}), 不再追加, 任务{current_idx}标记failed")
                        it["status"] = "failed"
                        it["blocked_reason"] = f"执行失败且补救上限耗尽: {err}"
                    inc_counter("task_plan_blocked_total")
                elif is_degraded:
                    it["status"] = "blocked"
                    it["blocked_reason"] = f"工具降级: {degradation_type or warning or 'unknown degradation'}"
                    logger.warning(f"Task-Planner: 任务{current_idx}工具降级阻塞: {degradation_type}")
                    remedy_count = sum(1 for x in items if "解决任务" in x.get("description", "") or "修复任务" in x.get("description", ""))
                    if remedy_count < MAX_REMEDY_STEPS:
                        new_idx = max(x["step_index"] for x in items) + 1 if items else 0
                        items.append({
                            "step_index": new_idx,
                            "agent": "clarification_node",
                            "action": "clarify",
                            "description": f"修复任务{current_idx}工具降级: {degradation_type}",
                            "depends_on": [],
                            "priority": "P0",
                            "deliverable": f"解除任务{current_idx}降级({degradation_type})",
                            "status": "pending",
                        })
                    else:
                        logger.warning(f"Task-Planner: 补救步骤已达上限({MAX_REMEDY_STEPS}), 不再追加降级补救")
                        it["status"] = "failed"
                        it["blocked_reason"] = f"工具降级且补救上限耗尽: {degradation_type}"
                    inc_counter("task_plan_degraded_total")
                elif content_length > 0 and content_length < 200:
                    it["status"] = "blocked"
                    it["blocked_reason"] = f"交付物过短({content_length}chars), 疑似占位输出"
                    logger.warning(f"Task-Planner: 任务{current_idx}交付物过短({content_length}chars), 标记阻塞")
                    inc_counter("task_plan_deliverable_invalid_total")
                else:
                    it["status"] = "done"
                    if content_length > 0:
                        it["deliverable_size"] = content_length
                break

        # ========== 动态重新规划：根据工具返回结果调整后续任务 ==========
        dynamic_added = []
        if tool_result.get("ok", False):
            tool_output_data = tool_result.get("data", "")
            tool_output_path = tool_result.get("output_path", "")
            remaining_after = [it for it in items if it.get("status") == "pending"]
            has_embed_step = any("嵌入" in it.get("description", "") or "插入图表" in it.get("description", "") for it in remaining_after)
            has_text_fallback = any("文字版" in it.get("description", "") or "降级" in it.get("description", "") for it in remaining_after)

            if tool_name == "algo:plot" and tool_output_path and not has_embed_step:
                new_idx = max(x["step_index"] for x in items) + 1 if items else 0
                embed_step = {
                    "step_index": new_idx,
                    "description": f"将图表({tool_output_path})嵌入到项目简报文档中",
                    "depends_on": [current_idx],
                    "priority": "P1",
                    "deliverable": "含图表的简报文档",
                    "expected_output": "HTML简报文档(含嵌入图表)",
                    "status": "pending",
                    "retry_count": 0,
                }
                items.append(embed_step)
                dynamic_added.append(embed_step)
                logger.info(f"Task-Planner: 动态重新规划 - 绘图成功, 新增步骤{new_idx}: 嵌入图表到文档")

            if tool_name == "rag_retrieve_node" and tool_output_data:
                output_lower = str(tool_output_data).lower()
                data_incomplete = any(k in output_lower for k in ("数据不全", "缺失", "未找到", "no result", "empty"))
                if data_incomplete and not has_text_fallback:
                    new_idx = max(x["step_index"] for x in items) + 1 if items else 0
                    supplement_step = {
                        "step_index": new_idx,
                        "description": "补充检索缺失的项目数据(预算明细/设备部署数据)",
                        "depends_on": [],
                        "priority": "P0",
                        "deliverable": "补充数据",
                        "expected_output": "完整项目数据",
                        "status": "pending",
                        "retry_count": 0,
                    }
                    items.append(supplement_step)
                    dynamic_added.append(supplement_step)
                    logger.info(f"Task-Planner: 动态重新规划 - RAG数据不全, 新增步骤{new_idx}: 补充检索")
        else:
            remaining_after = [it for it in items if it.get("status") == "pending"]
            has_text_fallback = any("文字版" in it.get("description", "") or "降级" in it.get("description", "") for it in remaining_after)
            if tool_name == "algo:plot" and not has_text_fallback:
                new_idx = max(x["step_index"] for x in items) + 1 if items else 0
                fallback_step = {
                    "step_index": new_idx,
                    "description": "绘图工具失败降级: 在文档中插入文字版数据说明替代图表",
                    "depends_on": [],
                    "priority": "P1",
                    "deliverable": "文字版数据说明",
                    "expected_output": "文字版预算占比说明",
                    "status": "pending",
                    "retry_count": 0,
                }
                items.append(fallback_step)
                dynamic_added.append(fallback_step)
                logger.info(f"Task-Planner: 动态重新规划 - 绘图失败, 新增步骤{new_idx}: 文字版降级")

        for it in items:
            if it.get("status") != "pending":
                continue
            deps = it.get("depends_on", [])
            if not deps:
                continue
            for dep_idx in deps:
                dep_item = next((x for x in items if x["step_index"] == dep_idx), None)
                if dep_item and dep_item.get("status") in ("blocked",):
                    it["status"] = "blocked"
                    it["blocked_reason"] = f"前置依赖任务{dep_idx}阻塞"
                    logger.warning(f"Task-Planner: 任务{it['step_index']}因前置依赖{dep_idx}阻塞而阻塞")
                    inc_counter("task_plan_dep_blocked_total")
                    break

        remaining = [it for it in items if it.get("status") == "pending"]
        all_done = all(it.get("status") == "done" for it in items if it.get("status") != "blocked")

        if remaining or not all_done:
            md = _render_task_plan_md(items)
            logger.info(f"🔁 Task-Planner: 任务{current_idx}完成, 还有{len(remaining)}项待执行\n{md}")
            blocked_items = [it for it in items if it.get("status") == "blocked"]
            update: dict[str, Any] = {
                "task_plan_items": items,
                "task_plan_results": results,
                "task_plan_status": "executing",
                "memory_summary": md,
                "tool_name": "",
                "tool_result": {},
            }
            if blocked_items:
                worst = blocked_items[0]
                update["correction_signal"] = {
                    "signal_type": "pollution",
                    "reason": worst.get("blocked_reason", "unknown block"),
                    "error_type": "business",
                    "step_index": worst["step_index"],
                }
                update["correction_loops"] = state.get("correction_loops", 0) + 1
                inc_counter("graph_correction_exhaust_total")
                try:
                    from app.services.audit.signal_audit import write_signal_audit, SignalAuditRecord
                    write_signal_audit(SignalAuditRecord(
                        session_id=state.get("session_id", "unknown"),
                        user_id=state.get("user_id", "unknown"),
                        trace_id=state.get("trace_id"),
                        signal_type="pollution",
                        signal_reason=worst.get("blocked_reason", "unknown block"),
                        correction_loops=update["correction_loops"],
                    ))
                except Exception as audit_err:
                    logger.warning(f"审计日志写入失败(非致命): {audit_err}")
            return update

        md = _render_task_plan_md(items)
        summary = f"✅ 全部任务执行完毕\n\n{md}\n\n交付物汇总：\n"
        for it in items:
            if it.get("deliverable"):
                size_info = f" ({it.get('deliverable_size', '?')}chars)" if it.get("deliverable_size") else ""
                summary += f"  - 任务{it['step_index']}: {it['deliverable']}{size_info}\n"
        logger.info(summary)
        inc_counter("task_plan_completed_total")
        return {
            "task_plan_items": items,
            "task_plan_results": results,
            "task_plan_status": "completed",
            "memory_summary": summary,
            "correction_signal": {},
            "tool_name": "",
            "tool_result": {},
        }


_TASK_PLAN_ALLOWED_TARGETS = frozenset({
    "app_launch_agent_node", "system_monitor_agent_node", "system_clean_agent_node",
    "browser_agent_node", "store_agent_node", "content_gen_agent_node",
    "image_agent_node", "algorithm_agent_node", "rag_retrieve_node",
    "code_search_node", "memory_persist_node", "clarification_node",
})


def route_after_task_plan(state: AgentState) -> str:
    plan_status = state.get("task_plan_status", "")
    tool_name = state.get("tool_name", "")
    if plan_status == "completed":
        if tool_name:
            return "task_plan_collect_node"
        if state.get("last_error"):
            return "post_validate_gate"
        return "memory_persist_node"
    if plan_status in ("executing", "planning"):
        if tool_name:
            return "task_plan_collect_node"
        route_target = state.get("route_target", "")
        if route_target and route_target in _TASK_PLAN_ALLOWED_TARGETS:
            return route_target
        if route_target:
            logger.warning(f"route_after_task_plan: route_target={route_target}不在白名单, 降级到task_planner_node")
        return "task_planner_node"
    if plan_status == "blocked":
        return "task_planner_node"
    return "memory_persist_node"


def route_after_task_plan_exec(state: AgentState) -> str:
    plan_status = state.get("task_plan_status", "")
    if plan_status == "completed":
        if state.get("last_error"):
            return "post_validate_gate"
        return "memory_persist_node"
    return "task_planner_node"


_GOVERNOR_MAX_CORRECTION_LOOPS = int(os.getenv("GOVERNOR_MAX_CORRECTION_LOOPS", "3"))
_GOVERNOR_HITL_SIGNAL_TYPES = frozenset({"pollution"})


async def governor_node(state: AgentState) -> dict[str, Any]:
    """
    Governor治理节点:
    1. 读取correction_signal, 判断信号类型
    2. 校正循环次数保护, 超过MAX_CORRECTION_LOOPS直接终止
    3. pollution信号触发HITL人工等待, 暂停图执行
    4. 更新metrics, 更新state内信号状态
    """
    with NodeMetrics("governor_node"):
        correction_signal = state.get("correction_signal", {})
        correction_loops = state.get("correction_loops", 0)
        task_plan_enabled = state.get("task_plan_enabled", False)

        if not correction_signal:
            return {
                "correction_signal": {},
                "needs_hitl": False,
                "task_plan_enabled": task_plan_enabled,
            }

        signal_type = correction_signal.get("signal_type", "unknown")
        inc_counter(f"graph_correction_signal_{signal_type}_total")

        if correction_loops >= _GOVERNOR_MAX_CORRECTION_LOOPS:
            logger.warning(f"Governor: 校正循环达到上限({_GOVERNOR_MAX_CORRECTION_LOOPS}), 任务强制终止")
            inc_counter("graph_correction_exhaust_total")
            try:
                from app.services.audit.signal_audit import write_signal_audit, SignalAuditRecord
                write_signal_audit(SignalAuditRecord(
                    session_id=state.get("session_id", "unknown"),
                    user_id=state.get("user_id", "unknown"),
                    trace_id=state.get("trace_id"),
                    signal_type="terminated",
                    signal_reason=f"校正循环次数超过最大阈值({_GOVERNOR_MAX_CORRECTION_LOOPS}), 任务终止",
                    correction_loops=correction_loops,
                ))
            except Exception as audit_err:
                logger.warning(f"审计日志写入失败(非致命): {audit_err}")
            return {
                "correction_signal": {
                    **correction_signal,
                    "signal_type": "terminated",
                    "reason": f"校正循环次数超过最大阈值({_GOVERNOR_MAX_CORRECTION_LOOPS}), 任务终止",
                },
                "needs_hitl": False,
                "task_plan_enabled": False,
                "needs_clarification": True,
                "clarification_message": f"校正尝试{correction_loops}次仍然失败, 任务终止, 请人工排查问题",
            }

        if signal_type in _GOVERNOR_HITL_SIGNAL_TYPES:
            logger.info(f"Governor: 收到{signal_type}信号, 进入HITL人工等待, signal={correction_signal}")
            return {
                "correction_signal": correction_signal,
                "needs_hitl": True,
                "task_plan_enabled": task_plan_enabled,
                "needs_clarification": True,
                "clarification_message": f"任务阻塞, 生成{signal_type}信号, 等待人工ack/resolve处理",
            }

        return {
            "correction_signal": correction_signal,
            "needs_hitl": False,
            "task_plan_enabled": task_plan_enabled,
        }


async def hitl_approval_node(state: AgentState) -> dict[str, Any]:
    """
    HITL人工审批节点
    图会在进入此节点前interrupt_before, 暂停等待外部API写入hitl_decision
    approve: 清空信号, 继续任务循环
    reject: 关闭任务, 停止规划循环, 标记任务终止
    """
    with NodeMetrics("hitl_approval_node"):
        hitl_decision = state.get("hitl_decision", "")
        hitl_comment = state.get("hitl_comment", "")
        correction_signal = state.get("correction_signal", {})

        if not hitl_decision:
            return {}

        if hitl_decision == "approve":
            return {
                "correction_signal": {},
                "needs_hitl": False,
                "hitl_decision": "",
                "hitl_comment": hitl_comment,
                "needs_clarification": False,
            }
        elif hitl_decision == "reject":
            logger.warning(f"HITL人工拒绝任务, signal: {correction_signal}, comment={hitl_comment}")
            inc_counter("graph_hitl_reject_total")
            return {
                "task_plan_enabled": False,
                "needs_hitl": False,
                "hitl_decision": "",
                "hitl_comment": hitl_comment,
                "correction_signal": {
                    **correction_signal,
                    "signal_type": "rejected",
                    "reason": f"人工拒绝任务, 备注: {hitl_comment}",
                },
                "needs_clarification": True,
                "clarification_message": "人工审批拒绝, 任务终止。",
            }
        else:
            logger.error(f"非法HITL decision: {hitl_decision}")
            return {}


def route_after_governor(state: AgentState) -> str:
    needs_hitl = state.get("needs_hitl", False)
    task_plan_enabled = state.get("task_plan_enabled", False)
    if needs_hitl:
        return "hitl_approval_node"
    if task_plan_enabled:
        return "task_planner_node"
    return "memory_persist_node"


def route_after_hitl(state: AgentState) -> str:
    hitl_decision = state.get("hitl_decision", "")
    task_plan_enabled = state.get("task_plan_enabled", False)
    if hitl_decision == "approve":
        return "task_planner_node"
    if hitl_decision == "reject" or not task_plan_enabled:
        return "memory_persist_node"
    return "hitl_approval_node"