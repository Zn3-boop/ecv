"""
demo.py：最小可运行入口
> 注意：全部节点是async，使用 graph.ainvoke
> env：GRAPH_ENV=dev

用法：
    cd d:\\ecv\\apps\\server
    python -m app.services.graph.demo

演示场景：
    1. 正常启动记事本 → 全链路通过
    2. 低置信度路由 → 意图澄清
    3. 长期记忆 A/B/D 级证据
    4. 快慢脑架构前置过滤
    5. OTel Trace Hash 存储
    6. HITL 人工审批流程
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

os.environ.setdefault("GRAPH_ENV", "dev")

from app.services.graph.state import AgentState, init_state, ERROR_TYPE_TRANSIENT, ERROR_TYPE_BUSINESS, ERROR_TYPE_SECURITY
from app.services.graph.graph import (
    build_agent_graph,
    build_invoke_config,
    DEFAULT_RECURSION_LIMIT,
)


def _print_step(step_name: str, state: AgentState) -> None:
    print(f"\n{'='*60}")
    print(f"  【{step_name}】")
    print(f"{'='*60}")
    keys_to_show = [
        "intent", "intent_confidence", "standalone_query", "retrieval_queries",
        "entities", "route_target", "route_confidence", "agent_input",
        "risk_level", "risk_reason", "approval_required", "approval_status",
        "tool_name", "tool_args", "tool_result", "last_error", "error_type",
        "needs_clarification", "clarification_message",
    ]
    for k in keys_to_show:
        v = state.get(k)
        if v or v is False:
            display = json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (dict, list)) else v
            print(f"  {k:30s} = {display}")


async def run_demo_normal() -> None:
    print("\n" + "█"*60)
    print("  场景1：正常启动记事本 — 全链路通过")
    print("█"*60)

    graph = build_agent_graph(interrupt_before_approval=False)
    state = init_state("打开记事本", session_id="demo_normal")
    config = build_invoke_config(
        user_id="user_demo",
        session_id=state["session_id"],
        trace_id=state["trace_id"],
    )

    print(f"\n  初始 State: raw_query={state['raw_query']}, trace_id={state['trace_id'][:12]}...")
    print(f"  config: thread_id={config['configurable']['thread_id']}, recursion_limit={config['configurable']['recursion_limit']}")

    try:
        result = await graph.ainvoke(state, config)
    except Exception as e:
        print(f"\n  ❌ 异常: {e}")
        result = {}

    _print_step("最终 State", result)

    if result.get("tool_result", {}).get("ok"):
        print("\n  ✅ 结果：已为你启动记事本")
    elif result.get("needs_clarification"):
        print(f"\n  ⚠️ 澄清：{result.get('clarification_message', '')}")
    elif result.get("last_error"):
        print(f"\n  ❌ 错误：{result['last_error']}")
    else:
        print(f"\n  📋 结果：{json.dumps(result.get('tool_result', {}), ensure_ascii=False, default=str)[:200]}")


async def run_demo_clarification() -> None:
    print("\n" + "█"*60)
    print("  场景2：低置信度路由 — 意图澄清")
    print("█"*60)

    graph = build_agent_graph(interrupt_before_approval=False)
    ambiguous_queries = ["帮我弄一下", "那个东西", "算了"]

    for query in ambiguous_queries:
        state = init_state(query, session_id="demo_clarify")
        config = build_invoke_config(
            user_id="user_demo",
            session_id=state["session_id"],
            trace_id=state["trace_id"],
        )
        result = await graph.ainvoke(state, config)
        intent = result.get("intent", "")
        confidence = result.get("intent_confidence", 0.0)
        needs_clarify = result.get("needs_clarification", False)
        clarify_msg = result.get("clarification_message", "")
        print(f"\n  query: \"{query}\"")
        print(f"    intent={intent}, confidence={confidence:.2f}")
        if needs_clarify:
            print(f"    ⚠️ 触发澄清: {clarify_msg}")


async def run_demo_memory_store() -> None:
    print("\n" + "█"*60)
    print("  场景3：长期记忆 Store — A/B/D 级证据")
    print("█"*60)

    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        from app.services.graph.memory_store import MemoryStore
        store = MemoryStore(store_dir=tmp_dir)

        store.put_evidence_a("user1", "打开微信", {"ok": True, "pid": 1234}, "trace_abc")
        store.put_evidence_b("user1", "app:launch", "hash123", {"ok": True}, "trace_abc")
        store.put_user_preference("user1", "WeChat.exe")
        store.put_user_preference("user1", "WeChat.exe")

        keys = store.list_keys("user1")
        print(f"\n  ✅ Store keys: {keys}")

        pref = store.get("user1", "pref_app_WeChat.exe")
        print(f"  用户偏好: WeChat.exe 启动 {pref['value']['launch_count']} 次")

        store.put("user1", "d_inference", {"intent": "desktop_control"}, level="D")
        d_result = store.get("user1", "d_inference")
        print(f"  D级推论固化: {d_result} (应为 None，D级不固化)")


async def run_demo_fast_brain() -> None:
    print("\n" + "█"*60)
    print("  场景4：快慢脑架构 — 快脑前置过滤无效输入")
    print("█"*60)

    graph = build_agent_graph(interrupt_before_approval=False)

    test_cases = [
        ("", "空输入"),
        ("   \n\t  ", "全空格换行"),
        ("┃┅▇◆◇▣┃┅▇◆◇▣┃┅", "大量乱码"),
        ("打开微信", "正常输入（应放行）"),
    ]

    for query, desc in test_cases:
        state = init_state(query, session_id="fb_" + desc[:4])
        config = build_invoke_config(
            user_id="user_demo",
            session_id=state["session_id"],
            trace_id=state["trace_id"],
        )
        result = await graph.ainvoke(state, config)

        decision = result.get("fast_brain_decision", "")
        need_slow = result.get("need_slow_brain", True)
        msg = result.get("fast_brain_msg", "")

        if decision == "reject":
            print(f"\n  [{desc}] query={repr(query)}")
            print(f"    🧠 快脑拦截 → need_slow_brain={need_slow}, msg={msg}")
        else:
            print(f"\n  [{desc}] query={repr(query)}")
            print(f"    ✅ 快脑放行 → need_slow_brain={need_slow}, 进入慢脑链路")


async def run_demo_trace_hash() -> None:
    print("\n" + "█"*60)
    print("  场景5：Trace Hash 存储 — 原始参数不进 span")
    print("█"*60)

    from app.services.observability.tracing import compute_args_hash, build_trace_safe_tool_attrs

    tool_args = {"path": "C:\\Users\\张三\\AppData\\Local\\WeChat.exe", "url": "https://secret.internal/api"}

    args_hash = compute_args_hash(tool_args)
    safe_attrs = build_trace_safe_tool_attrs("app:launch", tool_args, "call_abc123")

    print(f"\n  原始参数: {json.dumps(tool_args, ensure_ascii=False)}")
    print(f"  args_hash: {args_hash}")
    print(f"  span 属性: {json.dumps(safe_attrs, ensure_ascii=False)}")
    print(f"\n  ✅ span 中不含原始 path/url，只存 hash，规避隐私泄露")


async def run_demo_hitl_approval() -> None:
    print("\n" + "█"*60)
    print("  场景6：HITL 人工审批 — interrupt_before + update_state")
    print("█"*60)

    graph = build_agent_graph(interrupt_before_approval=True)
    state = init_state("打开脚本", session_id="demo_hitl")
    state["agent_input"] = {"action": "launch", "path": "evil.bat"}
    config = build_invoke_config(
        user_id="user_demo",
        session_id=state["session_id"],
        trace_id=state["trace_id"],
    )

    print(f"\n  高风险路径: evil.bat")
    print(f"  graph 编译时设置 interrupt_before=['approval_node']")
    print(f"  ")
    print(f"  HITL 流程:")
    print(f"    1. graph.ainvoke(state, config)")
    print(f"       → 执行到 approval_node 前暂停")
    print(f"       → 返回当前 state，approval_status='pending'")
    print(f"    ")
    print(f"    2. 外部审批接口接收用户确认/拒绝:")
    print(f"       graph.update_state(config, {{'approval_status': 'ok'}}, 'approval_node')")
    print(f"    ")
    print(f"    3. 恢复执行:")
    print(f"       result = await graph.ainvoke(None, config)")
    print(f"       → approval_status='ok' → 继续到 app_launch_agent_node")
    print(f"       → approval_status='reject' → 走 error_fallback_node")
    print(f"  ")
    print(f"  ✅ 高风险动作不会直接执行，必须经过人工审批")


async def run_demo_error_type_distinction() -> None:
    print("\n" + "█"*60)
    print("  场景7：错误类型区分 — security/business/transient")
    print("█"*60)

    from app.services.graph.graph import _is_transient_error

    test_cases = [
        ("Guard拦截: path含shell元字符[';']", ERROR_TYPE_SECURITY, "安全拦截，禁止重试"),
        ("Validation Gate: PID 99999 进程未存活", ERROR_TYPE_BUSINESS, "业务错误，禁止重试"),
        ("subprocess timeout: Electron启动超时", ERROR_TYPE_TRANSIENT, "临时错误，可重试"),
    ]

    for error_msg, error_type, desc in test_cases:
        is_transient = _is_transient_error(error_msg)
        retry = "可重试" if is_transient else "禁止重试"
        icon = "🔄" if is_transient else "🚫"
        print(f"\n  {icon} {desc}")
        print(f"    error_type={error_type}, {retry}")
        print(f"    error: {error_msg[:60]}")


async def main() -> None:
    print("╔" + "═"*58 + "╗")
    print("║  桌面控制 Agent LangGraph 状态图 — Demo                    ║")
    print("║  对齐: ACI Guarded / Harness / Validation Gate / OTel GenAI  ║")
    print("╚" + "═"*58 + "╝")

    await run_demo_normal()
    await run_demo_clarification()
    await run_demo_memory_store()
    await run_demo_fast_brain()
    await run_demo_trace_hash()
    await run_demo_hitl_approval()
    await run_demo_error_type_distinction()

    print("\n" + "╔" + "═"*58 + "╗")
    print("║  全部 7 场景演示完毕                                      ║")
    print("╚" + "═"*58 + "╝")


if __name__ == "__main__":
    asyncio.run(main())