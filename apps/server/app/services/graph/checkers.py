from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from typing import Any

import yaml

from app.services.graph.state import (
    AgentState,
    ERROR_TYPE_TRANSIENT,
    ERROR_TYPE_BUSINESS,
    ERROR_TYPE_SECURITY,
)
from app.services.graph.metrics import inc_counter

logger = logging.getLogger(__name__)

SHELL_METACHAR_PATTERN = re.compile(r'[|;&\$`\\!><\n\r\t]')
GARBAGE_CHAR_SET = set("┃┅▇◆◇▣☠💀�")
# H10 / 护栏类#2: 路径穿越 / 越界文件写入（写工具 output_path 等逃出工作区）
PATH_TRAVERSAL_PATTERNS = ["../", "..\\"]
# 判定为"路径型参数"的 key 特征（命中即按路径处理，避免误伤 URL/正文文本）
_PATH_KEY_HINTS = ("path", "file", "dir", "folder")


def _is_path_like_key(key: str) -> bool:
    k = (key or "").lower()
    return k in ("out", "src", "image", "script") or any(h in k for h in _PATH_KEY_HINTS)


def _find_path_traversal(value: str) -> list[str]:
    if ".." in value:
        return [t for t in PATH_TRAVERSAL_PATTERNS if t in value]
    return []


def _load_security_config() -> dict[str, Any]:
    cfg_path = os.getenv("SECURITY_CONFIG_PATH", "config/security.yaml")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"加载安全配置失败 {cfg_path}: {e}，使用默认值")
    return {}


_SEC_CFG = _load_security_config()
APPROVED_EXE_WHITELIST = set(_SEC_CFG.get("approved_exe_whitelist", ["notepad.exe", "calc.exe"]))
HIGH_RISK_EXTENSIONS = set(_SEC_CFG.get("high_risk_extensions", [".bat", ".cmd", ".ps1"]))
SYSTEM_DIRS = set(_SEC_CFG.get("system_dirs", ["windows", "system32"]))
GARBAGE_RATIO_THRESHOLD = float(_SEC_CFG.get("garbage_ratio_threshold", 0.3))


FAST_BRAIN_HIGH_THRESHOLD = float(os.getenv("FAST_BRAIN_HIGH_THRESHOLD", "0.92"))
FAST_BRAIN_MID_THRESHOLD = float(os.getenv("FAST_BRAIN_MID_THRESHOLD", "0.7"))


def fast_brain_node(state: AgentState) -> dict:
    """
    快脑前置节点：规则过滤 + Ollama结构化决策(3层路由)。

    第一层：纯规则拦截无效输入（空/乱码），零成本，直接reject。
    第二层：若 FAST_BRAIN_ENABLED=true，调用Ollama做结构化决策：
        - 高置信 (prob >= 0.92) → fast_answer: 快脑直接输出，不进慢脑
        - 中置信 (0.7 <= prob < 0.92) → review_by_slow: 快脑给初步判断，慢脑复核
        - 低置信 (prob < 0.7) → full_slow: 完整走慢脑规划+工具/RAG链路
    降级：Ollama不可用或超时时，退化为规则过滤，始终走full_slow。
    """
    raw_query = state.get("raw_query", "")

    if not raw_query:
        inc_counter("fast_brain_filter_total", labels={"reason": "empty_input"})
        return {
            "fast_brain_decision": "reject",
            "need_slow_brain": False,
            "fast_brain_mode": "reject",
            "fast_brain_msg": "输入内容不能为空，请描述你的操作需求。",
            "fast_brain_result": "",
            "fast_brain_confidence": 0.0,
            "fast_brain_intent": "",
        }

    if not raw_query.strip():
        inc_counter("fast_brain_filter_total", labels={"reason": "all_whitespace"})
        return {
            "fast_brain_decision": "reject",
            "need_slow_brain": False,
            "fast_brain_mode": "reject",
            "fast_brain_msg": "不能只输入空格，请描述你的操作需求。",
            "fast_brain_result": "",
            "fast_brain_confidence": 0.0,
            "fast_brain_intent": "",
        }

    garbage_count = sum(1 for c in raw_query if c in GARBAGE_CHAR_SET)
    if len(raw_query) > 0 and garbage_count / len(raw_query) > GARBAGE_RATIO_THRESHOLD:
        inc_counter("fast_brain_filter_total", labels={"reason": "garbage_chars"})
        return {
            "fast_brain_decision": "reject",
            "need_slow_brain": False,
            "fast_brain_mode": "reject",
            "fast_brain_msg": "检测到无效乱码，请输入正常的操作指令。",
            "fast_brain_result": "",
            "fast_brain_confidence": 0.0,
            "fast_brain_intent": "",
        }

    fb_enabled = os.getenv("FAST_BRAIN_ENABLED", "false").lower() in ("true", "1", "yes")
    if fb_enabled:
        try:
            import asyncio
            from app.services.fastbrain.fastbrain import OllamaFastBrainClient

            fb_model = os.getenv("FAST_BRAIN_MODEL", "qwen3:1.7b")
            fb_host = os.getenv("OLLAMA_HOST", os.getenv("OLLAMA_BASE_URL", None))
            fb_timeout = float(os.getenv("FAST_BRAIN_TIMEOUT", "30"))
            client = OllamaFastBrainClient(model=fb_model, host=fb_host, timeout=fb_timeout)

            questions = [
                {"id": "is_simple", "type": "boolean"},
                {"id": "intent_type", "type": "choice", "options": ["simple_action", "content_gen", "planning", "search"]},
            ]
            fb_state = {"user_query": raw_query}
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    decisions = pool.submit(asyncio.run, client.decide(fb_state, questions)).result(timeout=fb_timeout + 5)
            else:
                decisions = loop.run_until_complete(client.decide(fb_state, questions))

            if decisions is not None:
                is_simple = next((d for d in decisions if d.id == "is_simple"), None)
                intent = next((d for d in decisions if d.id == "intent_type"), None)
                prob = is_simple.probability if is_simple else 0.0
                intent_val = intent.value if intent else ""
                result_summary = f"简单动作:{intent_val}" if (is_simple and is_simple.value) else f"需要慢脑处理:{intent_val}"

                if prob >= FAST_BRAIN_HIGH_THRESHOLD and is_simple and is_simple.value:
                    inc_counter("fast_brain_filter_total", labels={"reason": "fast_answer"})
                    return {
                        "fast_brain_decision": "accept",
                        "need_slow_brain": False,
                        "fast_brain_mode": "fast_answer",
                        "fast_brain_msg": "",
                        "fast_brain_result": result_summary,
                        "fast_brain_confidence": prob,
                        "fast_brain_intent": intent_val or "simple_action",
                    }
                if prob >= FAST_BRAIN_MID_THRESHOLD:
                    inc_counter("fast_brain_filter_total", labels={"reason": "review_by_slow"})
                    return {
                        "fast_brain_decision": "accept",
                        "need_slow_brain": True,
                        "fast_brain_mode": "review_by_slow",
                        "fast_brain_msg": "",
                        "fast_brain_result": result_summary,
                        "fast_brain_confidence": prob,
                        "fast_brain_intent": intent_val,
                    }
                inc_counter("fast_brain_filter_total", labels={"reason": "full_slow"})
                return {
                    "fast_brain_decision": "accept",
                    "need_slow_brain": True,
                    "fast_brain_mode": "full_slow",
                    "fast_brain_msg": "",
                    "fast_brain_result": result_summary,
                    "fast_brain_confidence": prob,
                    "fast_brain_intent": intent_val,
                }
            logger.debug("FastBrain: Ollama decide returned None, fallback to full_slow")
        except Exception as e:
            logger.warning(f"FastBrain: Ollama调用失败, 降级到full_slow: {e}")

    inc_counter("fast_brain_filter_total", labels={"reason": "accept"})
    return {
        "fast_brain_decision": "accept",
        "need_slow_brain": True,
        "fast_brain_mode": "full_slow",
        "fast_brain_msg": "",
        "fast_brain_result": "",
        "fast_brain_confidence": 0.0,
        "fast_brain_intent": "",
    }


def risk_check_node(state: AgentState) -> dict:
    """
    Harness 风险分级 Checker 节点（独立非LLM硬编码）。
    返回新字典，不原地修改 state。
    """
    agent_input = state.get("agent_input", {})
    action = agent_input.get("action", "")
    path = agent_input.get("path", "")

    if action in ("launch", "launch_and_kill") and path:
        _, ext = os.path.splitext(path)
        ext_lower = ext.lower()
        basename = os.path.basename(path)
        dir_lower = os.path.dirname(path).lower()

        if ext_lower in HIGH_RISK_EXTENSIONS:
            return {
                "risk_level": "high",
                "risk_reason": f"脚本后缀 {ext_lower}，高风险变更",
                "approval_required": True,
                "approval_status": "pending",
            }

        if any(sd in dir_lower for sd in SYSTEM_DIRS):
            return {
                "risk_level": "high",
                "risk_reason": "路径位于系统目录，高风险变更",
                "approval_required": True,
                "approval_status": "pending",
            }

        if basename in APPROVED_EXE_WHITELIST:
            return {
                "risk_level": "medium",
                "risk_reason": "白名单桌面应用，中风险放行",
                "approval_required": False,
                "approval_status": "ok",
            }

        return {
            "risk_level": "medium",
            "risk_reason": "普通桌面应用，中风险放行",
            "approval_required": False,
            "approval_status": "ok",
        }

    if action == "kill":
        return {
            "risk_level": "medium",
            "risk_reason": "进程结束操作，中风险",
            "approval_required": False,
            "approval_status": "ok",
        }

    return {
        "risk_level": "low",
        "risk_reason": "",
        "approval_required": False,
        "approval_status": "ok",
    }


def guard_pre_check_node(state: AgentState) -> dict:
    """
    ACI-Guarded 前置护栏节点：执行前拦截非法参数。
    返回新字典，不原地修改 state。
    """
    tool_name = state.get("tool_name", "")
    tool_args = state.get("tool_args", {})

    if tool_name == "app:launch":
        path = tool_args.get("path", "")
        if path:
            traversal = _find_path_traversal(path)
            if traversal:
                return {
                    "last_error": f"Guard拦截: path含路径穿越{traversal}，越界写入风险",
                    "error_type": ERROR_TYPE_SECURITY,
                }
            found = SHELL_METACHAR_PATTERN.findall(path)
            if found:
                return {
                    "last_error": f"Guard拦截: path含shell元字符{found}，命令注入风险",
                    "error_type": ERROR_TYPE_SECURITY,
                }
            basename = os.path.basename(path)
            if basename not in APPROVED_EXE_WHITELIST:
                _, ext = os.path.splitext(path)
                if ext.lower() in HIGH_RISK_EXTENSIONS:
                    return {
                        "last_error": f"Guard拦截: 脚本后缀{ext.lower()}不在白名单",
                        "error_type": ERROR_TYPE_SECURITY,
                    }

    if tool_name == "process:kill":
        kill_name = tool_args.get("name", "")
        if kill_name:
            found = SHELL_METACHAR_PATTERN.findall(kill_name)
            if found:
                return {
                    "last_error": f"Guard拦截: kill_name含shell元字符{found}",
                    "error_type": ERROR_TYPE_SECURITY,
                }

    for arg_key, arg_val in tool_args.items():
        if isinstance(arg_val, str) and arg_val:
            # H10 类#2: 路径型参数禁止 `..` 逃逸（防止写工具越界写文件）
            if _is_path_like_key(arg_key):
                traversal = _find_path_traversal(arg_val)
                if traversal:
                    return {
                        "last_error": f"Guard拦截: {arg_key}含路径穿越{traversal}，越界写入风险",
                        "error_type": ERROR_TYPE_SECURITY,
                    }
            found = SHELL_METACHAR_PATTERN.findall(arg_val)
            if found and tool_name not in ("app:launch", "process:kill"):
                return {
                    "last_error": f"Guard拦截: {arg_key}含shell元字符{found}",
                    "error_type": ERROR_TYPE_SECURITY,
                }

    return {}


_FILE_PRODUCING_TOOLS = ("content:generate", "image:screenshot", "algo:plot", "ide:launch")
_TEXT_PRODUCING_TOOLS = ("image:ocr", "image:understand", "algo:calculate")


def task_completion_verifier(state: AgentState) -> dict[str, Any]:
    """
    M15 / H5扩展 / H13: 任务完成独立验证器。
    工具返回 ok ≠ 任务完成。做文件级 / 结果级实证校验，产出证据包。
    返回 {"completion_evidence": {...}, "task_verified": bool}。
    """
    tool_name = state.get("tool_name", "")
    tool_args = state.get("tool_args", {})
    tool_result = state.get("tool_result", {})
    if not isinstance(tool_result, dict):
        tool_result = {}

    checks: dict[str, Any] = {}
    verified = True

    # 1) 文件产出类工具：验证输出文件真实存在且非空
    if tool_name in _FILE_PRODUCING_TOOLS:
        output_path = str(tool_args.get("output_path", "") or tool_args.get("path", "")).strip()
        res_path = ""
        data = tool_result.get("data", {}) or {}
        if isinstance(data, dict):
            res_path = str(data.get("path", "") or "").strip()
        if not output_path and res_path:
            output_path = res_path
        if output_path:
            exists = os.path.exists(output_path)
            size = os.path.getsize(output_path) if exists else 0
            checks["output_file_exists"] = bool(exists)
            checks["output_file_size"] = size
            if not exists or size <= 0:
                verified = False
        else:
            checks["output_file_exists"] = None
            checks["unverifiable"] = "无输出路径可验证"

    # 2) 文本产出类工具：验证返回文本非空
    if tool_name in _TEXT_PRODUCING_TOOLS:
        text = tool_result.get("text") or (tool_result.get("data", {}) or {}).get("text", "") or tool_result.get("summary", "")
        checks["output_text_nonempty"] = bool(text and str(text).strip())
        if not checks["output_text_nonempty"]:
            verified = False

    # 3) 分级：验证通过且产生实证 → user(A级)证据；否则 unverified 不固化
    if verified and checks:
        evidence_level = "user"
        source = "user"
    else:
        evidence_level = ""
        source = "unverified"

    completion_evidence = {
        "tool_name": tool_name,
        "status": tool_result.get("status", "ok" if tool_result.get("ok") else "error"),
        "task_verified": verified,
        "evidence_level": evidence_level,
        "source": source,
        "checks": checks,
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return {"completion_evidence": completion_evidence, "task_verified": verified}


def post_validate_gate(state: AgentState) -> dict:
    """
    Validation Gate 验收闸门：工具返回ok ≠ 任务完成。
    独立 Checker 校验进程真实存活。
    返回新字典，不原地修改 state。
    """
    if state.get("last_error"):
        err = state["last_error"]
        if isinstance(err, dict):
            err = err.get("suggestion", "") or err.get("type", "未知错误")
        err = str(err) if err else "未知错误"
        return {
            "last_error": err,
            "error_type": state.get("error_type", ERROR_TYPE_BUSINESS),
        }

    tool_name = state.get("tool_name", "")
    tool_args = state.get("tool_args", {})
    tool_result = state.get("tool_result", {})

    if not tool_result.get("ok", False):
        if tool_result.get("status") == "success":
            pass
        else:
            error_msg = tool_result.get("error", {})
            if isinstance(error_msg, dict):
                error_msg = error_msg.get("suggestion", "") or tool_result.get("summary", "工具执行失败")
            elif not isinstance(error_msg, str):
                error_msg = tool_result.get("summary", "工具执行失败")
            return {
                "last_error": error_msg,
                "error_type": ERROR_TYPE_BUSINESS,
                "correction_signal_status": "open",
            }

    if tool_name == "app:launch":
        path = tool_args.get("path", "")
        basename = os.path.basename(path) if path else ""
        if basename:
            try:
                check = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {basename}"],
                    capture_output=True, text=True, timeout=5,
                )
                if basename.lower() not in check.stdout.lower():
                    return {
                        "last_error": f"Validation Gate: 应用 {basename} 启动后未检测到存活进程",
                        "error_type": ERROR_TYPE_BUSINESS,
                    }
            except Exception:
                pass
        pid = tool_result.get("pid")
        if pid:
            try:
                check = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    capture_output=True, text=True, timeout=5,
                )
                if str(pid) not in check.stdout:
                    return {
                        "last_error": f"Validation Gate: PID {pid} 进程未存活",
                        "error_type": ERROR_TYPE_BUSINESS,
                    }
            except Exception:
                pass

    if tool_name == "process:kill":
        kill_name = tool_args.get("name", "")
        kill_pid = tool_args.get("pid")
        try:
            if kill_pid:
                check = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {kill_pid}"],
                    capture_output=True, text=True, timeout=5,
                )
                if str(kill_pid) in check.stdout:
                    return {
                        "last_error": f"Validation Gate: 进程 {kill_pid} 仍在运行",
                        "error_type": ERROR_TYPE_BUSINESS,
                    }
            elif kill_name:
                check = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {kill_name}"],
                    capture_output=True, text=True, timeout=5,
                )
                if kill_name.lower() in check.stdout.lower():
                    return {
                        "last_error": f"Validation Gate: 进程 {kill_name} 仍在运行",
                        "error_type": ERROR_TYPE_BUSINESS,
                    }
        except Exception:
            pass

    # M15/H5/H13: 任务完成实证验证（文件级/结果级），产出证据包
    vr = task_completion_verifier(state)
    # H13 第7步铁律：工具ok ≠ 任务完成。实证校验失败 → 上升为业务错误，
    # 进入校正循环(rewrite_agent_input_node)并在重试耗尽后降级 error_fallback，
    # 防止"验证失败仍被当作任务完成"。
    if vr["task_verified"] is False:
        failed_checks = [k for k, v in vr["completion_evidence"].get("checks", {}).items() if v is False]
        err_detail = "、".join(failed_checks) if failed_checks else "产出物校验未通过"
        return {
            "last_error": f"Validation Gate: 任务完成校验未通过 [{err_detail}]",
            "error_type": ERROR_TYPE_BUSINESS,
            "correction_signal_status": "open",
            "completion_evidence": vr["completion_evidence"],
            "task_verified": False,
        }
    return vr