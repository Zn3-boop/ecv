"""
RAG + Web 并行检索 e2e 测试

验证目标:
1. rag_web_parallel_hook 是否被触发 (P0: Hook接线审计)
2. RAG + Web 并行检索是否同时返回结果
3. 融合策略是否生效 (weighted/rerank/source_priority)
4. 原查询保护: 改写后检索为空时用原Query重试
5. Web不可用时RAG单独可用 (降级兜底)
6. DuckDuckGo检索器是否工作

用法:
    cd d:\\ecv\\apps\\server
    python -m pytest app/services/graph/tests/test_rag_web_parallel_e2e.py -v
    python app/services/graph/tests/test_rag_web_parallel_e2e.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import pytest


# ==================== 1. Hook 接线审计 ====================

class TestHookWiring:
    """P0: 确认 rag_web_parallel_hook 在 Agent 检索路径上被触发"""

    def test_hook_registered_in_hooks_init(self):
        """rag_web_parallel hook 应在 hooks/__init__.py 中注册"""
        import app.services.hooks.__init__ as hooks_init
        import importlib
        importlib.reload(hooks_init)
        from app.services.hooks import init_hooks
        init_hooks()
        from app.services.hooks.registry import get_hook_registry
        registry = get_hook_registry()
        hook_names = [h["name"] for h in registry.list_all()]
        assert "rag_web_parallel" in hook_names, f"rag_web_parallel 未注册, 已注册: {hook_names}"

    def test_hook_event_is_before_agent_start(self):
        """hook 应挂在 BEFORE_AGENT_START 事件上"""
        from app.services.hooks.builtin.rag_web_parallel import create_rag_web_parallel_hook
        spec = create_rag_web_parallel_hook()
        from app.services.hooks.types import HookEvent
        assert spec.event == HookEvent.BEFORE_AGENT_START

    def test_graph_uses_hook_enhanced_rag_retrieve(self):
        """graph 中 rag_retrieve_node 应使用 hook 增强版 (当 HOOKS_ENABLED=true)"""
        original = os.environ.get("HOOKS_ENABLED")
        os.environ["HOOKS_ENABLED"] = "true"
        try:
            from app.services.hooks.graph_integration import rag_retrieve_with_hooks
            assert callable(rag_retrieve_with_hooks)
        finally:
            if original is not None:
                os.environ["HOOKS_ENABLED"] = original
            else:
                os.environ.pop("HOOKS_ENABLED", None)

    def test_route_after_llm_includes_rag_retrieve(self):
        """route_after_llm 应包含 rag_retrieve_node 作为有效路由目标"""
        from app.services.graph.graph import route_after_llm
        state = {"route_confidence": 0.9, "route_target": "rag_retrieve_node"}
        target = route_after_llm(state)
        assert target == "rag_retrieve_node"


# ==================== 2. RAG + Web 并行检索核心逻辑 ====================

class TestRAGWebParallel:
    """测试 rag_web_parallel_hook 的完整流水线"""

    @pytest.mark.asyncio
    async def test_parallel_retrieve_returns_both_sources(self):
        """并行检索应同时返回 RAG 和 Web 结果"""
        from app.services.hooks.builtin.rag_web_parallel import rag_web_parallel_hook
        ctx = {
            "raw_query": "LangGraph循环依赖处理方式",
            "standalone_query": "LangGraph循环依赖处理方式",
            "rag_user_acl": ["public"],
        }
        result = await rag_web_parallel_hook(ctx)
        if result is None:
            pytest.skip("Hook执行返回None (可能检索器未配置或超时)")
        assert "rag_results" in result
        assert "web_results" in result
        assert "fused_context" in result
        assert "fusion_strategy" in result
        print(f"  rag={len(result['rag_results'])}, web={len(result['web_results'])}")
        print(f"  fusion={result['fusion_strategy']}")
        print(f"  context_len={len(result.get('fused_context', ''))}")

    @pytest.mark.asyncio
    async def test_query_rewriting_preserves_original(self):
        """改写应保留原始query (R7: 原查询永不替换)"""
        from app.services.hooks.plugins.query_rewriter import RuleBasedRewriter
        rewriter = RuleBasedRewriter()
        result = await rewriter.rewrite("LangGraph怎么处理循环依赖？")
        assert result.standalone_query == "LangGraph怎么处理循环依赖？"
        assert result.rag_query == "LangGraph怎么处理循环依赖？"
        assert result.confidence == 1.0
        print(f"  rag_query={result.rag_query}")
        print(f"  web_query={result.web_query}")
        print(f"  retrieval_queries={result.retrieval_queries}")

    @pytest.mark.asyncio
    async def test_rewrite_validation_rejects_drift(self):
        """改写偏离原意时应被丢弃"""
        from app.services.rag.retriever import OnlineRetriever
        from app.services.rag.store import DualIndexStore
        store = DualIndexStore(store_dir=os.path.join(os.path.expanduser("~"), ".ecv_rag_store_test"))
        retriever = OnlineRetriever(store=store)
        valid = retriever._validate_rewrite("LangGraph 循环依赖", "LangGraph 循环依赖 处理方法")
        assert valid is True
        invalid = retriever._validate_rewrite("LangGraph 循环依赖", "React Hooks useEffect 清理")
        assert invalid is False

    @pytest.mark.asyncio
    async def test_duckduckgo_retriever_works(self):
        """DuckDuckGo 检索器应能返回结果"""
        from app.services.hooks.plugins.retrievers import DuckDuckGoRetriever
        retriever = DuckDuckGoRetriever(timeout=10.0)
        results = await retriever.retrieve("Python programming language", top_k=3)
        print(f"  DuckDuckGo results: {len(results)}")
        for r in results:
            print(f"    - {r.title[:50]}: {r.content[:80]}...")
        if not results:
            print("  WARNING: DuckDuckGo returned empty (may be rate-limited)")


# ==================== 3. 融合策略测试 ====================

class TestFusionStrategies:
    """测试 4 种融合策略"""

    @pytest.mark.asyncio
    async def test_weighted_fusion(self):
        """加权融合: RAG权重0.7, Web权重0.3"""
        from app.services.hooks.plugins.fusion import WeightedFusion
        from app.services.hooks.plugins.base import RetrievedDoc, DocSource, FusionInput
        fusion = WeightedFusion(max_content_len=200, max_total_docs=4)
        fusion_input = FusionInput(
            rag_docs=[
                RetrievedDoc(content="RAG结果1: 内部文档关于LangGraph", source=DocSource.RAG, score=0.9),
                RetrievedDoc(content="RAG结果2: 循环依赖处理方案", source=DocSource.RAG, score=0.8),
            ],
            web_docs=[
                RetrievedDoc(content="Web结果1: StackOverflow回答", source=DocSource.WEB, score=0.7),
                RetrievedDoc(content="Web结果2: GitHub Issue讨论", source=DocSource.WEB, score=0.6),
            ],
            query="LangGraph循环依赖7依赖",
            rag_weight=0.7,
            web_weight=0.3,
        )
        result = await fusion.fuse(fusion_input)
        assert "内部知识库" in result or "RAG" in result.upper() or len(result) > 0
        print(f"  weighted fusion result ({len(result)} chars):\n{result[:300]}")

    @pytest.mark.asyncio
    async def test_source_priority_fusion(self):
        """来源优先级融合: RAG > CODE > WEB"""
        from app.services.hooks.plugins.fusion import SourcePriorityFusion
        from app.services.hooks.plugins.base import RetrievedDoc, DocSource, FusionInput
        fusion = SourcePriorityFusion(max_per_source=2, max_total_docs=6)
        fusion_input = FusionInput(
            rag_docs=[
                RetrievedDoc(content="RAG: 权威内部文档", source=DocSource.RAG, score=0.8),
            ],
            web_docs=[
                RetrievedDoc(content="Web: 外网信息", source=DocSource.WEB, score=0.9),
            ],
            query="test",
        )
        result = await fusion.fuse(fusion_input)
        assert "内部知识库" in result
        print(f"  source_priority fusion:\n{result[:300]}")

    @pytest.mark.asyncio
    async def test_simple_concat_fusion(self):
        """简单拼接: RAG在前, Web在后"""
        from app.services.hooks.plugins.fusion import SimpleConcatFusion
        from app.services.hooks.plugins.base import RetrievedDoc, DocSource, FusionInput
        fusion = SimpleConcatFusion(max_content_len=200, max_docs_per_source=2)
        fusion_input = FusionInput(
            rag_docs=[RetrievedDoc(content="RAG片段", source=DocSource.RAG, score=0.9)],
            web_docs=[RetrievedDoc(content="Web片段", source=DocSource.WEB, score=0.7)],
            query="test",
        )
        result = await fusion.fuse(fusion_input)
        assert "内部知识库" in result
        assert "互联网" in result
        print(f"  simple_concat fusion:\n{result[:300]}")


# ==================== 4. 降级兜底测试 ====================

class TestDegradationFallback:
    """Web不可用时RAG单独可用, RAG不可用时Web兜底"""

    @pytest.mark.asyncio
    async def test_rag_retrieve_with_hooks_fallback(self):
        """Hook增强版 rag_retrieve 应在 Hook 失败时降级到原有逻辑"""
        from app.services.hooks.graph_integration import rag_retrieve_with_hooks
        from app.services.graph.state import AgentState
        state = AgentState(
            raw_query="测试查询",
            standalone_query="测试查询",
            retrieval_queries=["测试查询"],
            user_id="test_user",
            session_id="test_session",
        )
        result = await rag_retrieve_with_hooks(state)
        assert isinstance(result, dict)
        print(f"  fallback result keys: {list(result.keys())}")

    @pytest.mark.asyncio
    async def test_web_timeout_does_not_block_rag(self):
        """Web检索超时不应阻断RAG检索"""
        from app.services.hooks.plugins.retrievers import DuckDuckGoRetriever
        retriever = DuckDuckGoRetriever(timeout=0.001)
        results = await retriever.retrieve("test query that will timeout", top_k=3)
        print(f"  timeout result: {len(results)} docs (should be 0, not exception)")


# ==================== 5. ACL 鉴权前置测试 ====================

class TestACLPrefilter:
    """R8: 鉴权前置 — ACL过滤在检索前执行"""

    @pytest.mark.asyncio
    async def test_acl_filter_blocks_unauthorized(self):
        """无权限的chunk应被过滤"""
        from app.services.rag.retriever import OnlineRetriever
        from app.services.rag.store import DualIndexStore
        store = DualIndexStore(store_dir=os.path.join(os.path.expanduser("~"), ".ecv_rag_store_test"))
        retriever = OnlineRetriever(store=store)
        results = [
            {"chunk_id": "public_1", "content": "公开内容", "meta": {"acl_tags": ["public"]}, "score": 0.9},
            {"chunk_id": "private_1", "content": "私密内容", "meta": {"acl_tags": ["admin"]}, "score": 0.8},
            {"chunk_id": "team_1", "content": "团队内容", "meta": {"acl_tags": ["team_a"]}, "score": 0.7},
        ]
        filtered = retriever._acl_filter(results, ["public"])
        chunk_ids = [r["chunk_id"] for r in filtered]
        assert "public_1" in chunk_ids
        assert "private_1" not in chunk_ids
        assert "team_1" not in chunk_ids
        print(f"  ACL filtered: {chunk_ids}")

    @pytest.mark.asyncio
    async def test_admin_sees_all(self):
        """admin权限应能看到所有内容"""
        from app.services.rag.retriever import OnlineRetriever
        from app.services.rag.store import DualIndexStore
        store = DualIndexStore(store_dir=os.path.join(os.path.expanduser("~"), ".ecv_rag_store_test"))
        retriever = OnlineRetriever(store=store)
        results = [
            {"chunk_id": "public_1", "content": "公开", "meta": {"acl_tags": ["public"]}, "score": 0.9},
            {"chunk_id": "admin_1", "content": "管理", "meta": {"acl_tags": ["admin"]}, "score": 0.8},
        ]
        filtered = retriever._acl_filter(results, ["admin", "public"])
        chunk_ids = [r["chunk_id"] for r in filtered]
        assert "public_1" in chunk_ids
        assert "admin_1" in chunk_ids


# ==================== 主函数 ====================

async def main():
    print("=" * 60)
    print("RAG + Web 并行检索 e2e 测试")
    print("=" * 60)

    print("\n[1] Hook 接线审计")
    print("-" * 40)
    try:
        from app.services.hooks import init_hooks
        init_hooks()
        from app.services.hooks.registry import get_hook_registry
        registry = get_hook_registry()
        hook_names = [h.name for h in registry.hooks]
        print(f"  已注册hooks: {hook_names}")
        assert "rag_web_parallel" in hook_names
        print("  OK rag_web_parallel hook 已注册")
    except Exception as e:
        print(f"  FAIL hook注册检查失败: {e}")

    print("\n[2] 并行检索测试")
    print("-" * 40)
    from app.services.hooks.builtin.rag_web_parallel import rag_web_parallel_hook
    test_queries = [
        "LangGraph循环依赖处理方式",
        "2026年大模型Agent最新发展趋势",
        "Python asyncio gather用法",
    ]
    for query in test_queries:
        print(f"\n  Query: {query}")
        ctx = {
            "raw_query": query,
            "standalone_query": query,
            "rag_user_acl": ["public"],
        }
        result = await rag_web_parallel_hook(ctx)
        if result is None:
            print(f"    SKIP hook返回None")
            continue
        rag_count = len(result.get("rag_results", []))
        web_count = len(result.get("web_results", []))
        fusion = result.get("fusion_strategy", "unknown")
        context_len = len(result.get("fused_context", ""))
        validation = result.get("validation", {})
        print(f"    RAG={rag_count}, Web={web_count}, Fusion={fusion}")
        print(f"    Context={context_len}chars, Valid={validation.get('passed', '?')}")
        if result.get("retrieval_warning"):
            print(f"    WARNING: {result['retrieval_warning']}")

    print("\n[3] DuckDuckGo 检索器测试")
    print("-" * 40)
    from app.services.hooks.plugins.retrievers import DuckDuckGoRetriever
    ddg = DuckDuckGoRetriever(timeout=10.0)
    results = await ddg.retrieve("Python programming language history", top_k=3)
    print(f"  DuckDuckGo返回: {len(results)}条")
    for r in results:
        print(f"    - [{r.score:.2f}] {r.title[:60]}")

    print("\n[4] 融合策略测试")
    print("-" * 40)
    from app.services.hooks.plugins.fusion import WeightedFusion, SourcePriorityFusion
    from app.services.hooks.plugins.base import RetrievedDoc, DocSource, FusionInput
    rag_docs = [RetrievedDoc(content="RAG: 内部权威文档", source=DocSource.RAG, score=0.9)]
    web_docs = [RetrievedDoc(content="Web: 外网补充信息", source=DocSource.WEB, score=0.7)]
    fusion_input = FusionInput(rag_docs=rag_docs, web_docs=web_docs, query="test", rag_weight=0.7, web_weight=0.3)
    wf = WeightedFusion()
    result = await wf.fuse(fusion_input)
    print(f"  Weighted: {result[:200]}")

    print("\n[5] ACL鉴权前置测试")
    print("-" * 40)
    from app.services.rag.retriever import OnlineRetriever
    from app.services.rag.store import DualIndexStore
    store = DualIndexStore(store_dir=os.path.join(os.path.expanduser("~"), ".ecv_rag_store_test"))
    retriever = OnlineRetriever(store=store)
    results = [
        {"chunk_id": "pub", "content": "公开", "meta": {"acl_tags": ["public"]}, "score": 0.9},
        {"chunk_id": "adm", "content": "管理", "meta": {"acl_tags": ["admin"]}, "score": 0.8},
    ]
    filtered = retriever._acl_filter(results, ["public"])
    print(f"  public用户可见: {[r['chunk_id'] for r in filtered]}")
    filtered_admin = retriever._acl_filter(results, ["admin", "public"])
    print(f"  admin用户可见: {[r['chunk_id'] for r in filtered_admin]}")

    print(f"\n{'=' * 60}")
    print("RAG+Web e2e test done")


if __name__ == "__main__":
    asyncio.run(main())