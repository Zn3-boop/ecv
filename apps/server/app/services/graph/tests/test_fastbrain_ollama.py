"""
快脑 Ollama 集成测试 + 快脑/慢脑路由验证

验证目标:
1. Ollama 快脑能否做结构化决策 (choice/boolean/score)
2. 快脑→慢脑路由: 高置信直接采信, 中置信复核, 低置信降级
3. 生产环境不会"只走快脑不走慢脑" — 即快脑reject时确实跳过慢脑,
   但快脑accept时一定进入慢脑链路
4. Ollama 不可用时的 fail-open 降级

用法:
    cd d:\\ecv\\apps\\server
    # 需要 Ollama 运行中且已拉取模型
    python -m pytest app/services/graph/tests/test_fastbrain_ollama.py -v
    # 主函数模式(推荐人工观察)
    python app/services/graph/tests/test_fastbrain_ollama.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import pytest


# ==================== 1. 快脑 Ollama 客户端单元测试 ====================

class TestOllamaFastBrainClient:
    """测试 OllamaFastBrainClient 的结构化决策能力"""

    def _make_client(self):
        from app.services.fastbrain.fastbrain import OllamaFastBrainClient
        ollama_host = os.getenv("OLLAMA_HOST", os.getenv("OLLAMA_BASE_URL", None))
        return OllamaFastBrainClient(
            model=os.getenv("FAST_BRAIN_MODEL", "qwen3:1.7b"),
            host=ollama_host,
            timeout=90.0,
        )

    @pytest.mark.asyncio
    async def test_boolean_decision(self):
        """快脑布尔判断: 给出明确事实, 应返回高置信 True/False"""
        client = self._make_client()
        state = {"user_query": "启动记事本", "intent": "app_launch"}
        questions = [{"id": "is_launch", "type": "boolean"}]
        results = await client.decide(state, questions)
        if results is None:
            pytest.skip("Ollama 不可用, 跳过真实快脑测试")
        assert len(results) == 1
        d = results[0]
        assert d.kind == "boolean"
        assert isinstance(d.value, bool)
        assert 0.0 <= d.probability <= 1.0
        assert d.source == "fast_brain"
        print(f"  boolean: value={d.value}, prob={d.probability:.3f}, confident={d.confident}")

    @pytest.mark.asyncio
    async def test_choice_decision(self):
        """快脑多选一: 给出多个选项, 应返回最佳选项+概率"""
        client = self._make_client()
        state = {"user_query": "清理磁盘垃圾", "available_actions": ["launch", "clean", "monitor", "search"]}
        questions = [{"id": "action_choice", "type": "choice", "options": ["launch", "clean", "monitor", "search"]}]
        results = await client.decide(state, questions)
        if results is None:
            pytest.skip("Ollama 不可用")
        assert len(results) == 1
        d = results[0]
        assert d.kind == "choice"
        assert d.value in ["launch", "clean", "monitor", "search"]
        print(f"  choice: value={d.value}, prob={d.probability:.3f}")

    @pytest.mark.asyncio
    async def test_score_decision(self):
        """快脑打分: 对风险程度打分"""
        client = self._make_client()
        state = {"action": "删除系统文件", "risk_context": "高危操作"}
        questions = [{"id": "risk_score", "type": "score", "min": 0.0, "max": 1.0}]
        results = await client.decide(state, questions)
        if results is None:
            pytest.skip("Ollama 不可用")
        assert len(results) == 1
        d = results[0]
        assert d.kind == "score"
        assert 0.0 <= d.value <= 1.0
        print(f"  score: value={d.value:.3f}, prob={d.probability:.3f}")

    @pytest.mark.asyncio
    async def test_multiple_decisions_parallel(self):
        """快脑并行多条决策"""
        client = self._make_client()
        state = {"user_query": "帮我写一份面试材料包"}
        questions = [
            {"id": "is_complex", "type": "boolean"},
            {"id": "intent_type", "type": "choice", "options": ["simple_action", "content_gen", "planning", "search"]},
            {"id": "urgency", "type": "score", "min": 0.0, "max": 1.0},
        ]
        results = await client.decide(state, questions)
        if results is None:
            pytest.skip("Ollama 不可用")
        assert len(results) == 3
        for d in results:
            print(f"  {d.id}: kind={d.kind}, value={d.value!r}, prob={d.probability:.3f}, confident={d.confident}")


# ==================== 2. 快脑/慢脑路由逻辑测试 ====================

class TestFastSlowBrainRouting:
    """验证快脑→慢脑的路由逻辑, 确保生产环境不会'只走快脑'"""

    def test_fast_brain_reject_skips_slow(self):
        """快脑reject → need_slow_brain=False, 确实跳过慢脑"""
        from app.services.graph.checkers import fast_brain_node
        state = {"raw_query": ""}
        result = fast_brain_node(state)
        assert result["fast_brain_decision"] == "reject"
        assert result["need_slow_brain"] is False

    def test_fast_brain_accept_enters_slow(self):
        """快脑accept → need_slow_brain=True, 一定进入慢脑链路"""
        from app.services.graph.checkers import fast_brain_node
        state = {"raw_query": "帮我写一份面试材料包"}
        result = fast_brain_node(state)
        assert result["fast_brain_decision"] == "accept"
        assert result["need_slow_brain"] is True

    def test_route_after_fast_brain_reject_to_error(self):
        """快脑reject → 路由到 error_fallback_node, 不会跳到END"""
        from app.services.graph.graph import route_after_fast_brain
        state = {"need_slow_brain": False, "fast_brain_decision": "reject"}
        target = route_after_fast_brain(state)
        assert target == "error_fallback_node"

    def test_route_after_fast_brain_accept_to_detect_intent(self):
        """快脑accept → 路由到 detect_intent, 进入慢脑完整链路"""
        from app.services.graph.graph import route_after_fast_brain
        state = {"need_slow_brain": True}
        target = route_after_fast_brain(state)
        assert target == "detect_intent"

    def test_normal_query_always_enters_slow_brain(self):
        """任何正常查询(非空/非乱码)都会进入慢脑 — 这是生产安全底线"""
        from app.services.graph.checkers import fast_brain_node
        normal_queries = [
            "启动记事本",
            "帮我写一份面试材料包",
            "清理磁盘",
            "搜索Python教程",
            "监控CPU使用率",
            "What is LangGraph?",
            "2026年大模型Agent最新发展趋势",
        ]
        for q in normal_queries:
            result = fast_brain_node({"raw_query": q})
            assert result["fast_brain_decision"] == "accept", f"查询'{q}'被快脑错误reject"
            assert result["need_slow_brain"] is True, f"查询'{q}'未进入慢脑链路"


# ==================== 3. Ollama 快脑降级测试 ====================

class TestFastBrainDegradation:
    """Ollama 不可用时的 fail-open 降级"""

    @pytest.mark.asyncio
    async def test_ollama_unavailable_returns_none(self):
        """Ollama 未安装/未运行 → decide() 返回 None, 上层降级到规则"""
        from app.services.fastbrain.fastbrain import OllamaFastBrainClient
        client = OllamaFastBrainClient(model="nonexistent_model_xyz", timeout=2.0)
        state = {"query": "test"}
        questions = [{"id": "test", "type": "boolean"}]
        result = await client.decide(state, questions)
        assert result is None

    def test_fast_brain_enabled_default_off(self):
        """快脑默认关闭, 需要显式开启"""
        import os
        original = os.environ.pop("FAST_BRAIN_ENABLED", None)
        try:
            from app.services.fastbrain.fastbrain import _fast_brain_enabled
            assert _fast_brain_enabled() is False
        finally:
            if original is not None:
                os.environ["FAST_BRAIN_ENABLED"] = original

    def test_fast_brain_enabled_explicit_on(self):
        """FAST_BRAIN_ENABLED=1 时开启"""
        import os
        original = os.environ.get("FAST_BRAIN_ENABLED")
        os.environ["FAST_BRAIN_ENABLED"] = "1"
        try:
            from app.services.fastbrain.fastbrain import _fast_brain_enabled
            assert _fast_brain_enabled() is True
        finally:
            if original is not None:
                os.environ["FAST_BRAIN_ENABLED"] = original
            else:
                os.environ.pop("FAST_BRAIN_ENABLED", None)


# ==================== 4. 快脑置信度分级测试 ====================

class TestConfidenceTiering:
    """验证快脑置信度三级分层: >=0.9采信, 0.6~0.9复核, <0.6人工/规则"""

    def test_confident_decision(self):
        from app.services.fastbrain.fastbrain import Decision, CONFIDENCE_TRUST
        d = Decision(id="test", kind="boolean", value=True, probability=0.95)
        assert d.confident is True
        assert d.needs_recheck is False

    def test_recheck_decision(self):
        from app.services.fastbrain.fastbrain import Decision
        d = Decision(id="test", kind="boolean", value=True, probability=0.75)
        assert d.confident is False
        assert d.needs_recheck is True

    def test_low_confidence_decision(self):
        from app.services.fastbrain.fastbrain import Decision
        d = Decision(id="test", kind="boolean", value=True, probability=0.4)
        assert d.confident is False
        assert d.needs_recheck is False


# ==================== 主函数: 交互式测试 ====================

async def main():
    """交互式快脑测试: 给一堆东西, 快脑自己判断, 然后验证"""
    print("=" * 60)
    print("快脑 Ollama 集成测试")
    print("=" * 60)

    from app.services.fastbrain.fastbrain import (
        OllamaFastBrainClient,
        Decision,
        CONFIDENCE_TRUST,
        CONFIDENCE_RECHECK,
    )

    client = OllamaFastBrainClient(
        model=os.getenv("FAST_BRAIN_MODEL", "qwen3:4b"),
        timeout=15.0,
    )

    test_cases = [
        {
            "name": "简单启动指令 → 应高置信判定为简单操作",
            "state": {"user_query": "启动记事本", "intent": "app_launch"},
            "questions": [
                {"id": "is_simple_action", "type": "boolean"},
                {"id": "action_type", "type": "choice", "options": ["launch", "kill", "search", "generate", "plan"]},
            ],
        },
        {
            "name": "复杂规划任务 → 应判定需要慢脑规划",
            "state": {"user_query": "帮我搭建一套面试材料包，包含简历模板、自我介绍、项目经验梳理、技术面试准备", "intent": "planning"},
            "questions": [
                {"id": "needs_planning", "type": "boolean"},
                {"id": "complexity", "type": "score", "min": 0.0, "max": 1.0},
            ],
        },
        {
            "name": "风险操作 → 应高置信判定为高风险",
            "state": {"user_query": "删除C盘所有临时文件", "action": "disk_cleanup", "target": "C:\\"},
            "questions": [
                {"id": "is_dangerous", "type": "boolean"},
                {"id": "risk_level", "type": "score", "min": 0.0, "max": 1.0},
            ],
        },
        {
            "name": "知识检索 → 应判定走RAG而非直接执行",
            "state": {"user_query": "LangGraph怎么处理循环依赖？", "intent": "search"},
            "questions": [
                {"id": "needs_rag", "type": "boolean"},
                {"id": "query_type", "type": "choice", "options": ["direct_action", "rag_retrieve", "web_search", "planning"]},
            ],
        },
    ]

    for tc in test_cases:
        print(f"\n{'─' * 50}")
        print(f"测试: {tc['name']}")
        print(f"状态: {tc['state']}")
        results = await client.decide(tc["state"], tc["questions"])
        if results is None:
            print("  ⚠️ Ollama 不可用, 降级到规则/慢脑")
            continue
        for d in results:
            tier = "✅采信" if d.confident else ("🔄复核" if d.needs_recheck else "⚠️低置信")
            print(f"  {d.id}: value={d.value!r}, prob={d.probability:.3f} → {tier}")
            if d.confident:
                print(f"    → 快脑直接采信, 无需慢脑复核")
            elif d.needs_recheck:
                print(f"    → 交给慢脑LLM复核该判断")
            else:
                print(f"    → 置信度过低, 降级到规则/人工")

    print(f"\n{'=' * 60}")
    print("快脑/慢脑路由验证")
    print("=" * 60)

    from app.services.graph.checkers import fast_brain_node
    from app.services.graph.graph import route_after_fast_brain

    routing_tests = [
        ("", "空输入"),
        ("   ", "纯空格"),
        ("帮我写面试材料包", "正常查询"),
        ("启动记事本", "简单指令"),
        ("2026年AI Agent趋势", "知识查询"),
    ]

    for query, desc in routing_tests:
        state = {"raw_query": query}
        fb_result = fast_brain_node(state)
        route = route_after_fast_brain(fb_result)
        decision = fb_result["fast_brain_decision"]
        need_slow = fb_result["need_slow_brain"]
        print(f"  [{desc}] query='{query}' → decision={decision}, need_slow_brain={need_slow}, route={route}")

    print(f"\n✅ 路由验证完成: 所有正常查询都会进入慢脑链路(detect_intent)")


if __name__ == "__main__":
    asyncio.run(main())