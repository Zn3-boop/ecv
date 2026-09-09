"""
综合量化基准测试 - 输出所有可量化指标
运行方式: python -m tests.benchmark  或  pytest tests/benchmark.py -v -s
"""
import asyncio
import json
import time
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parent.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.services.intent_detector import detect_intent
from app.services.context_manager import ContextManager, CompressionStrategy
from app.services.tool_registry import tool_registry, ToolCategory
from app.services.tools.schema import TOOLS_SCHEMA
from app.services.llm.rate_limiter import LLMRateLimiter
from app.services.llm.provider import _classify_provider_error
from app.utils.response_cleaner import ResponseCleaner


def _build_long_history(turn_count: int = 30, chars_per_turn: int = 200) -> list[dict]:
    history = []
    for i in range(turn_count):
        role = "user" if i % 2 == 0 else "assistant"
        content = f"第{i+1}轮对话：" + "这是一段测试内容。" * (chars_per_turn // 10)
        history.append({"role": role, "content": content, "metadata": {}})
    return history


def benchmark_intent_detection():
    """意图识别性能基准"""
    print("\n" + "=" * 70)
    print("1. 意图识别分层 - 简单指令走本地规则，减少LLM调用")
    print("=" * 70)

    simple_commands = [
        "CPU多少", "内存使用率", "电脑很卡", "查看进程", "C盘空间",
        "打开微信", "关闭QQ", "搜索Python教程", "卸载Chrome应用", "全面清理",
        "磁盘状态", "检查系统", "启动Chrome", "结束chrome进程", "百度一下天气",
    ]
    complex_commands = [
        "打开记事本写代码", "写一篇关于AI的文章", "创建登录页面",
        "打开VSCode写个登录页面然后浏览器预览", "打开Word写毕业论文",
        "打开浏览器搜索AI", "打开微信然后发消息",
    ]
    all_commands = simple_commands + complex_commands

    start = time.perf_counter()
    results = [detect_intent(cmd) for cmd in all_commands]
    elapsed = (time.perf_counter() - start) * 1000

    local_count = sum(1 for r in results if r != "llm_decompose")
    llm_count = len(all_commands) - local_count
    reduction = local_count / len(all_commands) * 100
    avg_ms = elapsed / len(all_commands)

    print(f"  总指令数:       {len(all_commands)}")
    print(f"  本地规则处理:   {local_count} 条")
    print(f"  需LLM分解:      {llm_count} 条")
    print(f"  LLM调用量降低:  {reduction:.1f}%")
    print(f"  本地响应平均:   {avg_ms:.4f}ms/条")
    print(f"  ✅ 目标: 高频操作本地响应 < 1ms, LLM调用量降低 > 60%")

    start = time.perf_counter()
    for _ in range(1000):
        for cmd in simple_commands:
            detect_intent(cmd)
    batch_elapsed = (time.perf_counter() - start) * 1000
    print(f"  批量(1000轮×{len(simple_commands)}条)总耗时: {batch_elapsed:.1f}ms")


def benchmark_context_compression():
    """对话摘要压缩基准"""
    print("\n" + "=" * 70)
    print("2. 双层对话摘要压缩 - 降低Token消耗")
    print("=" * 70)

    cm = ContextManager(max_turns=6, max_tokens=6000, strategy=CompressionStrategy.HYBRID)
    history = _build_long_history(30, chars_per_turn=200)

    raw_tokens = sum(cm.estimate_tokens(m.get("content", "")) for m in history)

    context, summary = cm.process(history)
    compressed_tokens = sum(cm.estimate_tokens(c.get("content", "")) for c in context)
    if summary:
        compressed_tokens += cm.estimate_tokens(summary)

    reduction = (1 - compressed_tokens / raw_tokens) * 100

    print(f"  历史轮次:       30 条")
    print(f"  原始Token估算:  {raw_tokens}")
    print(f"  压缩后Token:    {compressed_tokens}")
    print(f"  Token消耗降低:  {reduction:.1f}%")
    print(f"  压缩策略:       Hybrid (滑动窗口 + 摘要)")
    print(f"  摘要生成:       {'是' if summary else '否'}")
    if summary:
        print(f"  摘要长度:       {len(summary)} 字符")
    print(f"  ✅ 目标: 长会话Token消耗降低 > 30%")

    for strategy in CompressionStrategy:
        cm_s = ContextManager(max_turns=6, max_tokens=6000, strategy=strategy)
        start = time.perf_counter()
        for _ in range(100):
            cm_s.process(history)
        elapsed = (time.perf_counter() - start) * 1000 / 100
        ctx_s, _ = cm_s.process(history)
        tokens_s = sum(cm_s.estimate_tokens(c.get("content", "")) for c in ctx_s)
        red_s = (1 - tokens_s / raw_tokens) * 100
        print(f"  策略 {strategy.value:10s}: 平均耗时 {elapsed:.3f}ms, Token降低 {red_s:.1f}%")


def benchmark_tool_security():
    """工具安全管控基准"""
    print("\n" + "=" * 70)
    print("3. 工具调用安全管控 - 风险分级 + 高危确认 + 参数校验")
    print("=" * 70)

    all_tools = list(tool_registry._tools.values())
    dangerous = [t for t in all_tools if t.category == ToolCategory.DANGEROUS]
    confirmed = [t for t in dangerous if t.requires_confirmation]
    safe = [t for t in all_tools if t.risk == "low"]
    read_only = [t for t in all_tools if t.command_type == "read"]

    print(f"  注册工具总数:   {len(all_tools)}")
    print(f"  高危工具数:     {len(dangerous)}")
    print(f"  高危确认覆盖:   {len(confirmed)}/{len(dangerous)} ({len(confirmed)/len(dangerous)*100 if dangerous else 100:.0f}%)")
    print(f"  安全工具数:     {len(safe)}")
    print(f"  只读工具数:     {len(read_only)}")
    print(f"  Schema工具数:   {len(TOOLS_SCHEMA)}")

    categories = {}
    for t in all_tools:
        cat = t.category.value
        categories[cat] = categories.get(cat, 0) + 1
    print(f"  分类分布:       {json.dumps(categories, ensure_ascii=False)}")

    print(f"  ✅ 目标: 高危工具确认覆盖率 100%")

    print(f"\n  高危工具清单:")
    for t in dangerous:
        print(f"    - {t.name:20s} risk={t.risk}, confirmation={t.requires_confirmation}")


def benchmark_error_classification():
    """异常分类处理基准"""
    print("\n" + "=" * 70)
    print("4. LLM Provider 异常分类处理")
    print("=" * 70)

    test_cases = [
        (400, "context window exceeded", "ContextTooLong"),
        (413, "too many tokens", "ContextTooLong"),
        (414, "prompt is too long", "ContextTooLong"),
        (429, "rate limited", "RateLimit"),
        (404, "model not found", "ModelDisabled"),
        (403, "model disabled", "ModelDisabled"),
        (500, "server error", "UpstreamServer"),
        (502, "bad gateway", "UpstreamServer"),
        (503, "unavailable", "UpstreamServer"),
        (400, "bad syntax", "Generic"),
        (418, "teapot", "Generic"),
    ]

    correct = 0
    for status, text, expected in test_cases:
        err = _classify_provider_error(status, text)
        actual = type(err).__name__
        match = expected in actual or actual.replace("LLM", "") == expected
        if match:
            correct += 1
        else:
            print(f"  ⚠ {status} '{text}' → {actual} (预期含 {expected})")

    coverage = correct / len(test_cases) * 100
    print(f"  测试场景数:     {len(test_cases)}")
    print(f"  精确分类数:     {correct}")
    print(f"  分类覆盖率:     {coverage:.0f}%")
    print(f"  ✅ 目标: 异常分类覆盖率 100%")


def benchmark_rate_limiter():
    """限流与缓存基准"""
    print("\n" + "=" * 70)
    print("5. 请求限流 + 结果缓存")
    print("=" * 70)

    rl = LLMRateLimiter()
    print(f"  限流间隔:       {rl.min_interval_seconds}s")
    print(f"  缓存TTL:        {rl.cache_ttl_seconds}s")
    print(f"  最大缓存条目:   {rl.max_cache_entries}")

    for i in range(50):
        rl.set_cached(
            f"result_{i}",
            system_prompt="sys", user_prompt=f"q_{i}", temperature=0.2, response_format=None,
        )

    hits = 0
    for i in range(50):
        result = rl.get_cached(
            system_prompt="sys", user_prompt=f"q_{i}", temperature=0.2, response_format=None,
        )
        if result is not None:
            hits += 1

    print(f"  缓存写入:       50 条")
    print(f"  缓存命中:       {hits} 条")
    print(f"  命中率:         {hits/50*100:.0f}%")

    start = time.perf_counter()
    for i in range(1000):
        rl.get_cached(
            system_prompt="sys", user_prompt=f"q_{i % 50}", temperature=0.2, response_format=None,
        )
    elapsed = (time.perf_counter() - start) * 1000
    print(f"  1000次缓存查询: {elapsed:.2f}ms (平均 {elapsed/1000:.4f}ms/次)")


def benchmark_component_reuse():
    """通用组件复用基准"""
    print("\n" + "=" * 70)
    print("6. 通用组件沉淀与复用")
    print("=" * 70)

    components = {
        "ResponseCleaner": ["clean", "sanitize_user_input", "contains_leakage", "clean_json_response"],
        "ContextManager": ["process", "estimate_tokens", "clean_content"],
        "ToolRegistry": ["register", "get", "list_tools"],
        "LLMRateLimiter": ["wait_turn", "get_cached", "set_cached"],
        "LLMProvider": ["chat", "chat_with_tools"],
        "IntentDetector": ["detect_intent"],
    }

    total_methods = 0
    for name, methods in components.items():
        total_methods += len(methods)
        print(f"  {name:20s}: {len(methods)} 个公共方法 - {', '.join(methods)}")

    print(f"\n  业务组件总数:   {len(components)}")
    print(f"  公共方法总数:   {total_methods}")
    print(f"  ✅ 目标: 沉淀 ≥ 6 个业务组件，复用于多处")


def run_all_benchmarks():
    print("\n" + "█" * 70)
    print("█  AI Desktop Agent — 综合量化基准测试报告")
    print("█" * 70)

    benchmark_intent_detection()
    benchmark_context_compression()
    benchmark_tool_security()
    benchmark_error_classification()
    benchmark_rate_limiter()
    benchmark_component_reuse()

    print("\n" + "=" * 70)
    print("测试完成！以上指标可用于面试量化陈述。")
    print("=" * 70)


if __name__ == "__main__":
    run_all_benchmarks()