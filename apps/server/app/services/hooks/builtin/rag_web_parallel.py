from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.services.hooks.types import HookEvent, HookLayer, HookMode
from app.services.hooks.registry import HookSpec
from app.services.hooks.plugins.base import (
    RetrievedDoc,
    DocSource,
    RewriteResult,
    FusionInput,
    ValidationResult,
)
from app.services.hooks.plugins.registry import get_plugin_registry, load_plugin_config

logger = logging.getLogger(__name__)


async def rag_web_parallel_hook(ctx: dict[str, Any]) -> dict[str, Any] | None:
    """
    RAG + Web 并行检索 Hook (插件化编排版)

    流程:
    1. 查询改写 → rag_query / web_query / retrieval_queries
    2. 并行检索 → 每个配置的retriever独立执行，超时隔离
    3. 去重过滤 → SimHash去重 + 规则过滤 + 时效性过滤
    4. 结果融合 → 加权/重排/拼接/来源优先
    5. 验证门 → Checker硬性检查 + Evaluator软性评估
    6. Prompt构造 → 区分来源、标注引用、压幻觉

    所有组件均可通过 YAML配置 / 环境变量 / register自定义实例 替换。
    """
    raw_query = ctx.get("raw_query", "")
    standalone_query = ctx.get("standalone_query", "")
    query = raw_query or standalone_query
    if not query:
        return None

    plugin_reg = get_plugin_registry()
    config = load_plugin_config()
    start_time = time.monotonic()

    try:
        rewrite_result = await _step_rewrite(query, ctx, plugin_reg, config)

        rag_docs, web_docs, all_docs = await _step_parallel_retrieve(
            rewrite_result, ctx, plugin_reg, config
        )

        if not all_docs and query != rewrite_result.rag_query:
            logger.warning("B10: 改写后检索为空，用原Query重试 (原Query召回保护)")
            from app.services.hooks.plugins.base import RewriteResult as _RR, RewriteType as _RT
            original_rewrite = _RR(
                standalone_query=query,
                rag_query=query,
                web_query=query,
                retrieval_queries=[query],
                rewrite_types=[_RT.NORMALIZE],
                confidence=1.0,
            )
            rag_docs, web_docs, all_docs = await _step_parallel_retrieve(
                original_rewrite, ctx, plugin_reg, config
            )

        all_docs = await _step_dedup_filter(all_docs, query, plugin_reg, config)

        fused_context = await _step_fuse(rag_docs, web_docs, query, plugin_reg, config)

        validation = await _step_validate(all_docs, query, plugin_reg, config)

        prompt_text = _step_build_prompt(fused_context, query, rag_docs, web_docs, plugin_reg, config)

        elapsed = time.monotonic() - start_time
        logger.info(
            f"RAG+Web并行检索完成: "
            f"rag={len(rag_docs)} web={len(web_docs)} "
            f"fusion={config['fusion']['type']} "
            f"valid={validation.passed} "
            f"elapsed={elapsed:.2f}s"
        )

        result: dict[str, Any] = {
            "rag_results": [d.to_dict() for d in rag_docs[:5]],
            "web_results": [d.to_dict() for d in web_docs[:5]],
            "fused_context": fused_context[: config.get("max_context_chars", 4000)],
            "fusion_strategy": config["fusion"]["type"],
            "rewrite_result": {
                "rag_query": rewrite_result.rag_query,
                "web_query": rewrite_result.web_query,
                "standalone_query": rewrite_result.standalone_query,
                "retrieval_queries": rewrite_result.retrieval_queries,
                "rewrite_types": [t.value for t in rewrite_result.rewrite_types],
                "confidence": rewrite_result.confidence,
            },
            "validation": {
                "passed": validation.passed,
                "reason": validation.reason,
                "metrics": validation.metrics,
            },
            "prompt_text": prompt_text,
            "retrieval_elapsed_s": round(elapsed, 3),
        }

        if not validation.passed:
            result["retrieval_warning"] = validation.reason

        return result

    except Exception as e:
        logger.warning(f"RAG+Web并行检索失败: {e}")
        return None


async def _step_rewrite(
    query: str,
    ctx: dict[str, Any],
    plugin_reg: Any,
    config: dict[str, Any],
) -> RewriteResult:
    rewriter_cfg = config.get("rewriter", {"type": "rule"})
    rewriter_type = rewriter_cfg.get("type", "rule")
    kwargs = {k: v for k, v in rewriter_cfg.items() if k != "type"}
    rewriter = plugin_reg.get_rewriter(rewriter_type, **kwargs)
    return await rewriter.rewrite(query, context=ctx)


async def _step_parallel_retrieve(
    rewrite_result: RewriteResult,
    ctx: dict[str, Any],
    plugin_reg: Any,
    config: dict[str, Any],
) -> tuple[list[RetrievedDoc], list[RetrievedDoc], list[RetrievedDoc]]:
    retriever_configs = config.get("retrievers", [])
    timeouts = config.get("timeouts", {"rag": 5.0, "web": 8.0})

    tasks: list[asyncio.Task[list[RetrievedDoc]]] = []
    task_sources: list[str] = []

    for rcfg in retriever_configs:
        rtype = rcfg.get("type", "rag")
        rkwargs = {k: v for k, v in rcfg.items() if k != "type"}

        try:
            retriever = plugin_reg.get_retriever(rtype, **rkwargs)
        except ValueError as e:
            logger.warning(f"跳过未知检索器 {rtype}: {e}")
            continue

        query_for_retriever = (
            rewrite_result.rag_query
            if retriever.source == DocSource.RAG
            else rewrite_result.web_query
        )

        timeout_key = "rag" if retriever.source == DocSource.RAG else "web"
        timeout_s = float(timeouts.get(timeout_key, 8.0))

        extra_kwargs: dict[str, Any] = {}
        if retriever.source == DocSource.RAG:
            extra_kwargs["rewrite_queries"] = rewrite_result.retrieval_queries
            extra_kwargs["user_acl"] = ctx.get("rag_user_acl", ["public"])

        async def _safe_retrieve(
            ret: Any = retriever,
            q: str = query_for_retriever,
            kw: dict[str, Any] = extra_kwargs,
        ) -> list[RetrievedDoc]:
            return await ret.retrieve(q, top_k=rcfg.get("top_k", 5), **kw)

        tasks.append(asyncio.create_task(asyncio.wait_for(_safe_retrieve(), timeout=timeout_s)))
        task_sources.append(rtype)

    if not tasks:
        return [], [], []

    results = await asyncio.gather(*tasks, return_exceptions=True)

    rag_docs: list[RetrievedDoc] = []
    web_docs: list[RetrievedDoc] = []
    all_docs: list[RetrievedDoc] = []

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning(f"检索器 {task_sources[i]} 超时或失败: {result}")
            continue
        for doc in result:
            all_docs.append(doc)
            if doc.source == DocSource.RAG:
                rag_docs.append(doc)
            else:
                web_docs.append(doc)

    return rag_docs, web_docs, all_docs


async def _step_dedup_filter(
    docs: list[RetrievedDoc],
    query: str,
    plugin_reg: Any,
    config: dict[str, Any],
) -> list[RetrievedDoc]:
    dedup_configs = config.get("dedup_filters", [])
    if not dedup_configs:
        return docs

    filters = []
    for dcfg in dedup_configs:
        dtype = dcfg.get("type", "simhash")
        dkwargs = {k: v for k, v in dcfg.items() if k != "type"}
        try:
            filters.append(plugin_reg.get_dedup(dtype, **dkwargs))
        except ValueError as e:
            logger.warning(f"跳过未知去重过滤器 {dtype}: {e}")

    if not filters:
        return docs

    from app.services.hooks.plugins.dedup import CompositeDedupFilter

    composite = CompositeDedupFilter(filters)
    return await composite.dedup_filter(docs, query)


async def _step_fuse(
    rag_docs: list[RetrievedDoc],
    web_docs: list[RetrievedDoc],
    query: str,
    plugin_reg: Any,
    config: dict[str, Any],
) -> str:
    fusion_cfg = config.get("fusion", {"type": "weighted"})
    fusion_type = fusion_cfg.get("type", "weighted")
    fkwargs = {k: v for k, v in fusion_cfg.items() if k not in ("type",)}

    _FUSION_CTOR_PARAMS = {"max_content_len", "max_total_docs", "max_per_source"}
    ctor_kwargs = {k: v for k, v in fkwargs.items() if k in _FUSION_CTOR_PARAMS}
    fusion = plugin_reg.get_fusion(fusion_type, **ctor_kwargs)
    fusion_input = FusionInput(
        rag_docs=rag_docs,
        web_docs=web_docs,
        query=query,
        rag_weight=float(fusion_cfg.get("rag_weight", 0.7)),
        web_weight=float(fusion_cfg.get("web_weight", 0.3)),
    )
    return await fusion.fuse(fusion_input)


async def _step_validate(
    docs: list[RetrievedDoc],
    query: str,
    plugin_reg: Any,
    config: dict[str, Any],
) -> ValidationResult:
    validator_configs = config.get("validators", [])
    if not validator_configs:
        return ValidationResult(passed=True, filtered_docs=docs)

    validators = []
    for vcfg in validator_configs:
        vtype = vcfg.get("type", "min_result")
        vkwargs = {k: v for k, v in vcfg.items() if k != "type"}
        try:
            validators.append(plugin_reg.get_validator(vtype, **vkwargs))
        except ValueError as e:
            logger.warning(f"跳过未知验证器 {vtype}: {e}")

    if not validators:
        return ValidationResult(passed=True, filtered_docs=docs)

    from app.services.hooks.plugins.validation import CompositeValidator

    composite = CompositeValidator(validators)
    return await composite.validate(docs, query)


def _step_build_prompt(
    fused_context: str,
    query: str,
    rag_docs: list[RetrievedDoc],
    web_docs: list[RetrievedDoc],
    plugin_reg: Any,
    config: dict[str, Any],
) -> str:
    pb_cfg = config.get("prompt_builder", {"type": "default"})
    pb_type = pb_cfg.get("type", "default")
    pkwargs = {k: v for k, v in pb_cfg.items() if k != "type"}

    builder = plugin_reg.get_prompt_builder(pb_type, **pkwargs)

    metadata: dict[str, Any] = {
        "rag_content": "\n".join(d.content[:300] for d in rag_docs[:3]),
        "web_content": "\n".join(d.content[:300] for d in web_docs[:3]),
        "evidence_ids": [d.chunk_id for d in rag_docs if d.chunk_id],
    }

    return builder.build(fused_context, query, metadata)


def create_rag_web_parallel_hook() -> HookSpec:
    return HookSpec(
        name="rag_web_parallel",
        event=HookEvent.BEFORE_AGENT_START,
        callback=rag_web_parallel_hook,
        mode=HookMode.MODIFY,
        layer=HookLayer.AGENT,
        priority=10,
    )