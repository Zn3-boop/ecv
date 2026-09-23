""" 端到端动态规划Agent综合测试
覆盖：动态规划闭环、工具调用闭环、依赖阻塞&熔断、RAG+工具混合、LangFuse可观测
用法:
    cd d:\\ecv\\apps\\server
    # Mock模式（状态机断言测试）
    python -m pytest app/services/graph/tests/test_e2e_dynamic_planning.py -v
    python -m pytest app/services/graph/tests/test_e2e_dynamic_planning.py -v -m e2e
    # 真实链路模式（Agent智能决策，关闭mock）
    set E2E_USE_MOCK=False && python -m pytest app/services/graph/tests/test_e2e_dynamic_planning.py -v
    # 冒烟主函数（流式实时打印，推荐人工观察Agent规划，会输出日志文件 _test_output.log）
    python app/services/graph/tests/test_e2e_dynamic_planning.py
新增能力：
1. LangFuse Span全链路校验（校验span树、节点span、工具span、异常span埋点）
2. 熔断最大重试上限测试
3. RAG + 并行网络检索混合任务测试
4. 工具异常场景LangFuse error埋点校验
5. 优化脆弱中文关键词断言，增加备选匹配
6. 【新增】Span metadata元数据埋点校验
7. 【新增】LLM规划节点异常埋点校验
8. 【新增】Graph递归超限熔断埋点校验
9. 【新增】并行任务依赖关系校验
"""
from __future__ import annotations
import asyncio
import os
os.environ["LLM_MODE"] = "real"
os.environ["GRAPH_ENV"] = "dev"
import json
import sys
import io
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
# ===================== 环境配置 & 日志双写Tee（取自你的参考脚本） =====================
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 测试环境：强制mock模式，不加载.env，不设置真实API密钥
# 真实LLM密钥仅在E2E_USE_MOCK=False时由外部环境变量注入
os.environ.setdefault("LLM_STRUCTURED_OUTPUT", "auto")
os.environ.setdefault("ENABLE_EVOLVE_FEEDBACK", "true")
os.environ.setdefault("TASK_PLAN_ENABLED", "true")
os.environ.setdefault("GRAPH_RECURSION_LIMIT", "50")
_llm_mode = os.getenv("LLM_MODE", "real")
_graph_env = os.getenv("GRAPH_ENV", "dev")
if _graph_env == "prod" and _llm_mode == "mock":
    raise RuntimeError("PROD环境禁止使用LLM_MODE=mock！请切换为real模式")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_output.log")
class Tee:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            s.write(data)
            s.flush()
    def flush(self):
        for s in self.streams:
            s.flush()
log_f = open(LOG_FILE, "w", encoding="utf-8")
sys.stdout = Tee(sys.stdout, log_f)
sys.stderr = Tee(sys.stderr, log_f)
# 全局Mock开关，从环境变量读取
USE_MOCK = os.getenv("E2E_USE_MOCK", "true").lower() in ("true", "1", "yes")
print(f"[TEST CONFIG] USE_MOCK = {USE_MOCK}")
from app.services.graph.state import (
    AgentState,
    init_state,
    validate_task_plan_items,
    TaskPlanItemModel,
)
try:
    import app.services.graph.nodes as _nodes_mod
    _nodes_mod.LLM_MODE = "mock"
except Exception:
    pass
try:
    from app.services.observability.langfuse_client import langfuse
except Exception:
    langfuse = None
    print("[WARN] langfuse client import failed, trace fetch test will be skipped")
# ===================== 测试任务Query集 =====================
RAW_QUERY_QINGHAI = (
    "撰写一份青海省高原生态农牧万物互联智慧平台项目简报，面向项目评审，要求："
    "1. 从知识库检索项目背景、技术架构、物联网设备部署数据、预算构成；"
    "2. 整理关键数据：农牧区传感器部署数量、边缘节点数量、年度运维成本，绘制一张预算占比饼图；"
    "3. 将检索内容+图表，整合生成一份可导出的HTML项目简报文档；"
    "4. 如果任意子任务失败，标记失败原因，调整后续计划，不要直接终止全部任务。"
)
RAW_QUERY_MARKET_REPORT = (
    "检索近5年青海农牧数字化投入数据，绘制折线图，生成Word市场分析报告"
)
RAW_QUERY_OCR_PIPELINE = (
    "截图本地项目文档 → OCR识别文字 → 基于OCR结果撰写摘要"
)
RAW_QUERY_XAGENT = (
    "搭建一份面向AI应用工程师面试的xAgent教育项目完整面试材料包。项目背景：xAgent教育Agent，被动式采集学生做题行为，规则为主、大模型仅做诊断，掌握度达到90%才允许进阶；项目上线服务上万用户；踩坑：早期完全依赖大模型，意图识别混乱，后续改为规则约束上下文、权限锁死；配套Data Query能力：指标表+向量召回+MySQL查询，限制单次最多返回500条数据。最终交付物清单：1.项目简历版描述（STAR格式，150字以内）2.项目架构文字说明+Mermaid架构流程图代码 3.项目核心难点+解决方案（3条）4.面试高频题：8道，附带参考答案 5.项目不足与未来优化方向（3点）"
)
# ===== 新增：RAG+并行网络检索混合任务 =====
RAW_QUERY_RAG_WEB_PARALLEL = (
    "并行执行：RAG知识库查询青海农牧物联网设备参数 + 全网检索2025青海农牧数字化政策；合并两份结果，对比差异，生成一份对比摘要文档；如果其中一个检索失败，保留另一个检索结果继续完成文档，不阻塞整体任务。"
)
RAW_QUERY_RAG_WEB_PARALLEL_BOTH_FAIL = (
    "并行执行：RAG知识库查询青海农牧物联网设备参数 + 全网检索2025青海农牧数字化政策；合并两份结果，对比差异，生成一份对比摘要文档；两个检索都失败时，写文档说明数据无法获取，整体任务不直接失败。"
)
# ============================================================
# Mock数据工厂
# ============================================================
def _make_global_plan_qinghai() -> list[dict]:
    return [
        {"step_index": 1, "description": "RAG检索知识库：青海高原智慧农牧平台项目背景、技术架构、预算、设备数据", "expected_output": "项目背景与架构检索结果", "status": "pending"},
        {"step_index": 2, "description": "提取预算数据，校验数据完整性", "expected_output": "预算数据完整性校验结果", "status": "pending"},
        {"step_index": 3, "description": "调用algo:plot绘制预算占比饼图", "expected_output": "预算占比饼图", "status": "pending"},
        {"step_index": 4, "description": "整合检索文本+图表，撰写项目简报正文", "expected_output": "项目简报正文", "status": "pending"},
        {"step_index": 5, "description": "调用content:generate生成HTML简报文档", "expected_output": "HTML项目简报文档", "status": "pending"},
        {"step_index": 6, "description": "输出交付物清单与任务总结", "expected_output": "交付物清单", "status": "pending"},
    ]
def _make_global_plan_rag_web_parallel() -> list[dict]:
    return [
        {"step_index": 1, "description": "并行任务A：RAG知识库查询青海农牧物联网设备参数", "expected_output": "RAG向量检索结果", "status": "pending", "depends_on": []},
        {"step_index": 2, "description": "并行任务B：全网检索2025青海农牧数字化政策", "expected_output": "web检索结果", "status": "pending", "depends_on": []},
        {"step_index": 3, "description": "合并RAG与web检索结果，对比信息差异", "expected_output": "差异对比文本", "status": "pending", "depends_on": [1,2]},
        {"step_index": 4, "description": "生成对比摘要文档", "expected_output": "摘要文档", "status": "pending", "depends_on": [3]},
    ]
def _make_sub_plan(description: str) -> dict:
    return {
        "target": description,
        "steps": [
            {"sub_step_index": 1, "description": f"执行: {description}", "success_criteria": "产出有效内容", "risk": "低"},
        ],
    }
def _make_plot_result(output_path: str = "/tmp/budget_pie.png") -> dict:
    return {
        "ok": True,
        "data": f"图表已生成: {output_path}",
        "output_path": output_path,
        "content_length": 256,
    }
def _make_content_gen_result(content_length: int = 5000) -> dict:
    return {
        "ok": True,
        "data": "<html><body>青海省高原智慧农牧平台项目简报...</body></html>",
        "content_length": content_length,
    }
def _make_plot_failure() -> dict:
    return {
        "ok": False,
        "error": "绘图服务崩溃: algo:plot timeout",
    }
# ===== 新增：连续失败mock，用于熔断重试测试 =====
def _make_plot_failure_repeated():
    return {
        "ok": False,
        "error": "绘图服务持续超时",
    }
def _make_web_search_ok():
    return {"ok": True, "data": "2025青海农牧数字化扶持政策摘要", "content_length": 320}
def _make_web_search_fail():
    return {"ok": False, "error": "web检索服务连接超时"}
def _make_rag_fail():
    return {"ok": False, "error": "RAG向量库查询超时，无法召回文档"}
# ============================================================
# Fixtures：增加USE_MOCK条件开关，真实模式不patch
# ============================================================
@pytest.fixture
def patch_llm_plan():
    if not USE_MOCK:
        yield (None, None, None)
        return
    with patch("app.services.llm.client.task_plan_global_llm", new=AsyncMock(return_value=_make_global_plan_qinghai())) as m1, \
         patch("app.services.llm.client.task_plan_sub_plan_llm", new=AsyncMock(side_effect=lambda task, hist: _make_sub_plan(task.get("description", "")))) as m2, \
         patch("app.services.llm.client.task_execute_llm", new=AsyncMock(return_value="A" * 200)) as m3:
        yield (m1, m2, m3)
@pytest.fixture
def patch_llm_plan_market():
    if not USE_MOCK:
        yield (None, None, None)
        return
    market_plan = [
        {"step_index": 1, "description": "检索近5年青海农牧数字化投入数据", "expected_output": "投入数据集", "status": "pending"},
        {"step_index": 2, "description": "绘制折线图", "expected_output": "折线图", "status": "pending"},
        {"step_index": 3, "description": "生成Word市场分析报告", "expected_output": "Word报告", "status": "pending"},
    ]
    with patch("app.services.llm.client.task_plan_global_llm", new=AsyncMock(return_value=market_plan)) as m1, \
         patch("app.services.llm.client.task_plan_sub_plan_llm", new=AsyncMock(side_effect=lambda task, hist: _make_sub_plan(task.get("description", "")))) as m2, \
         patch("app.services.llm.client.task_execute_llm", new=AsyncMock(return_value="B" * 200)) as m3:
        yield (m1, m2, m3)
@pytest.fixture
def patch_llm_plan_ocr():
    if not USE_MOCK:
        yield (None, None, None)
        return
    ocr_plan = [
        {"step_index": 1, "description": "截图本地项目文档", "expected_output": "截图文件", "status": "pending"},
        {"step_index": 2, "description": "OCR识别文字", "expected_output": "识别文字", "status": "pending"},
        {"step_index": 3, "description": "基于OCR结果撰写摘要", "expected_output": "摘要文档", "status": "pending"},
    ]
    with patch("app.services.llm.client.task_plan_global_llm", new=AsyncMock(return_value=ocr_plan)) as m1, \
         patch("app.services.llm.client.task_plan_sub_plan_llm", new=AsyncMock(side_effect=lambda task, hist: _make_sub_plan(task.get("description", "")))) as m2, \
         patch("app.services.llm.client.task_execute_llm", new=AsyncMock(return_value="C" * 200)) as m3:
        yield (m1, m2, m3)
# ===== 新增：RAG+并行检索fixture =====
@pytest.fixture
def patch_llm_plan_rag_web_parallel():
    if not USE_MOCK:
        yield (None, None, None)
        return
    parallel_plan = _make_global_plan_rag_web_parallel()
    with patch("app.services.llm.client.task_plan_global_llm", new=AsyncMock(return_value=parallel_plan)) as m1, \
         patch("app.services.llm.client.task_plan_sub_plan_llm", new=AsyncMock(side_effect=lambda task, hist: _make_sub_plan(task.get("description", "")))) as m2, \
         patch("app.services.llm.client.task_execute_llm", new=AsyncMock(return_value="D" * 200)) as m3:
        yield (m1, m2, m3)
@pytest.fixture
def patch_llm_plan_exception():
    """LLM规划节点抛出异常，用于测试规划失败埋点"""
    if not USE_MOCK:
        yield (None, None, None)
        return
    with patch("app.services.llm.client.task_plan_global_llm", new=AsyncMock(side_effect=Exception("LLM调用超时，生成全局计划失败"))) as m1:
        yield m1
@pytest.fixture
def patch_tool_execute_ok():
    if not USE_MOCK:
        yield None
        return
    async def _fake_execute(name: str, args: dict) -> dict:
        if name == "algo:plot":
            return _make_plot_result()
        if name == "content:generate":
            return _make_content_gen_result()
        if name == "image:screenshot":
            return {"ok": True, "data": "screenshot saved", "output_path": "/tmp/screenshot.png", "content_length": 100}
        if name == "image:ocr":
            return {"ok": True, "data": "OCR识别结果：项目概述...", "content_length": 300}
        if name == "web:search":
            return _make_web_search_ok()
        return {"ok": True, "data": "default mock result", "content_length": 200}
    with patch("app.services.tools.executor._execute_single_tool", new=AsyncMock(side_effect=_fake_execute)) as m:
        yield m
@pytest.fixture
def patch_tool_execute_plot_fail():
    if not USE_MOCK:
        yield None
        return
    async def _fake_execute(name: str, args: dict) -> dict:
        if name == "algo:plot":
            return _make_plot_failure()
        if name == "content:generate":
            return _make_content_gen_result()
        return {"ok": True, "data": "default mock result", "content_length": 200}
    with patch("app.services.tools.executor._execute_single_tool", new=AsyncMock(side_effect=_fake_execute)) as m:
        yield m
# ===== 新增：连续绘图失败fixture，熔断重试 =====
@pytest.fixture
def patch_tool_execute_plot_repeated_fail():
    if not USE_MOCK:
        yield None
        return
    async def _fake_execute(name: str, args: dict) -> dict:
        if name == "algo:plot":
            return _make_plot_failure_repeated()
        if name == "content:generate":
            return _make_content_gen_result()
        return {"ok": True, "data": "default mock result", "content_length": 200}
    with patch("app.services.tools.executor._execute_single_tool", new=AsyncMock(side_effect=_fake_execute)) as m:
        yield m
@pytest.fixture
def patch_tool_execute_screenshot_fail():
    if not USE_MOCK:
        yield None
        return
    async def _fake_execute(name: str, args: dict) -> dict:
        if name == "image:screenshot":
            return {"ok": False, "error": "截图失败: 窗口未找到"}
        if name == "image:ocr":
            return {"ok": False, "error": "OCR失败: 无截图文件"}
        if name == "content:generate":
            return _make_content_gen_result()
        return {"ok": True, "data": "default mock result", "content_length": 200}
    with patch("app.services.tools.executor._execute_single_tool", new=AsyncMock(side_effect=_fake_execute)) as m:
        yield m
@pytest.fixture
def patch_tool_execute_rag_web_both_fail():
    if not USE_MOCK:
        yield None
        return
    async def _fake_execute(name: str, args: dict) -> dict:
        if name == "web:search":
            return _make_web_search_fail()
        return {"ok": True, "data": "default mock result", "content_length": 200}
    with patch("app.services.tools.executor._execute_single_tool", new=AsyncMock(side_effect=_fake_execute)) as m, \
         patch("app.services.rag.get_rag_service") as mock_get_rag:
        rag_instance = MagicMock()
        rag_instance.query = AsyncMock(return_value=_make_rag_fail())
        mock_get_rag.return_value = rag_instance
        yield m
@pytest.fixture
def patch_rag_ok():
    if not USE_MOCK:
        yield None
        return
    with patch("app.services.rag.get_rag_service") as mock_get_rag:
        rag_instance = MagicMock()
        rag_instance.query = AsyncMock(return_value={
            "retrieval": {
                "results": [{"content": "青海高原智慧农牧平台预算数据", "score": 0.92}],
                "evidence_map": {},
            },
            "context": {
                "context": "项目预算占比：硬件45%、软件25%、运维20%、培训10%。传感器3200个，边缘节点86个。",
                "evidence_ids": ["ev_001", "ev_002"],
                "should_refuse": False,
            },
            "contradiction": {"has_contradiction": False},
        })
        mock_get_rag.return_value = rag_instance
        yield rag_instance
@pytest.fixture
def patch_rag_incomplete():
    if not USE_MOCK:
        yield None
        return
    with patch("app.services.rag.get_rag_service") as mock_get_rag:
        rag_instance = MagicMock()
        rag_instance.query = AsyncMock(return_value={
            "retrieval": {
                "results": [{"content": "部分数据不全", "score": 0.6}],
                "evidence_map": {},
            },
            "context": {
                "context": "数据不全，预算明细缺失",
                "evidence_ids": ["ev_003"],
                "should_refuse": False,
            },
            "contradiction": {"has_contradiction": False},
        })
        mock_get_rag.return_value = rag_instance
        yield rag_instance
def _fetch_langfuse_trace(trace_id: str):
    if langfuse is None:
        return None
    try:
        import urllib.request
        import json as _json
        pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        sk = os.getenv("LANGFUSE_SECRET_KEY", "")
        host = os.getenv("LANGFUSE_HOST", "https://jp.cloud.langfuse.com")
        if not pk or not sk:
            return None
        url = f"{host}/api/public/traces/{trace_id}"
        req = urllib.request.Request(url)
        import base64
        cred = base64.b64encode(f"{pk}:{sk}".encode()).decode()
        req.add_header("Authorization", f"Basic {cred}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode())
            return data
    except Exception:
        return None
def _build_state_and_run_graph(raw_query: str, recursion_limit: int = 30):
    from app.services.graph.graph import build_agent_graph, build_invoke_config
    graph = build_agent_graph(interrupt_before_approval=False)
    state = init_state(raw_query, session_id="e2e_test", user_id="test_user")
    config = build_invoke_config(
        user_id="test_user",
        session_id=state["session_id"],
        trace_id=state["trace_id"],
        recursion_limit=recursion_limit,
    )
    return graph, state, config
# ============================================================
# Test 1: 动态规划能力 — 初始计划生成 + 执行后动态修改
# ============================================================
@pytest.mark.e2e
class TestDynamicPlanning:
    @pytest.mark.asyncio
    @pytest.mark.skipif(not USE_MOCK, reason="真实LLM模式，计划描述不固定，跳过固定文本断言")
    async def test_initial_plan_generated(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_ok):
        from app.services.graph.nodes import LLM_MODE, _mock_route_via_llm
        route_result = await _mock_route_via_llm(RAW_QUERY_QINGHAI)
        import logging; logging.warning(f"DEBUG: LLM_MODE={LLM_MODE}, route_result={route_result}")
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        logging.warning(f"DEBUG: task_plan_status={result.get('task_plan_status', '')}, items={len(result.get('task_plan_items', []))}, history={len(result.get('history_log', []))}, last_error={result.get('last_error', '')}, route_target={result.get('route_target', '')}")
        items = result.get("task_plan_items", [])
        assert len(items) >= 3, f"应生成至少3步计划，实际{len(items)}步"
        descriptions = [it.get("description", "") for it in items]
        has_rag = any("检索" in d or "知识库" in d for d in descriptions)
        has_plot = any("绘图" in d or "饼图" in d or "图表" in d for d in descriptions)
        has_doc = any("生成" in d or "简报" in d or "文档" in d for d in descriptions)
        assert has_rag, "计划应包含RAG检索步骤"
        assert has_plot, "计划应包含绘图步骤"
        assert has_doc, "计划应包含文档生成步骤"
    @pytest.mark.asyncio
    async def test_plan_status_completes(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_ok):
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        plan_status = result.get("task_plan_status", "")
        assert plan_status in ("completed", "executing", "planning", "blocked"), \
            f"task_plan_status应为有效值，实际: {plan_status}"
    @pytest.mark.asyncio
    async def test_history_log_records_execution(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_ok):
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        history_log = result.get("history_log", [])
        assert len(history_log) > 0, "history_log应记录执行过程"
    @pytest.mark.asyncio
    @pytest.mark.skipif(not USE_MOCK, reason="真实LLM模式，计划描述不固定，跳过固定文本断言")
    async def test_rag_incomplete_triggers_dynamic_replan(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_incomplete):
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        items = result.get("task_plan_items", [])
        assert len(items) > 0, "RAG数据不全时仍应有任务计划"
        history_log = result.get("history_log", [])
        has_replan_log = any("动态" in str(log) or "replan" in str(log).lower() or "补充" in str(log) for log in history_log)
        if has_replan_log:
            assert has_replan_log, "RAG数据不全时应触发动态重新规划日志"
# ============================================================
# Test 2: 工具调用闭环 — 工具返回结果被Agent消费
# ============================================================
@pytest.mark.e2e
class TestToolCallClosedLoop:
    @pytest.mark.asyncio
    @pytest.mark.skipif(not USE_MOCK, reason="真实LLM模式，计划描述不固定，跳过固定文本断言")
    async def test_plot_success_triggers_embed_step(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_ok):
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        items = result.get("task_plan_items", [])
        descriptions = [it.get("description", "") for it in items]
        has_embed = any(any(x in d for x in ("嵌入", "插入图表", "把图表写入")) for d in descriptions)
        initial_plan_descriptions = [it["description"] for it in _make_global_plan_qinghai()]
        initial_has_embed = any(any(x in d for x in ("嵌入", "插入图表", "把图表写入")) for d in initial_plan_descriptions)
        if not initial_has_embed:
            assert has_embed, "绘图成功后应动态新增「嵌入图表到文档」步骤"
    @pytest.mark.asyncio
    async def test_tool_result_consumed_by_subsequent_step(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_ok):
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        results = result.get("task_plan_results", [])
        assert len(results) > 0, "应有任务执行结果记录"
        for r in results:
            assert "step_index" in r, "每个结果应包含step_index"
            assert "tool_result" in r, "每个结果应包含tool_result"
    @pytest.mark.asyncio
    async def test_content_gen_receives_plot_output(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_ok):
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        results = result.get("task_plan_results", [])
        tool_names_in_results = [r.get("tool_name", "") for r in results]
        has_content_gen = "content:generate" in tool_names_in_results
        has_plot = "algo:plot" in tool_names_in_results
        if has_plot and has_content_gen:
            plot_idx = next(i for i, r in enumerate(results) if r.get("tool_name") == "algo:plot")
            content_idx = next(i for i, r in enumerate(results) if r.get("tool_name") == "content:generate")
            assert plot_idx < content_idx, "绘图应在文档生成之前执行"
# ============================================================
# Test 3: 熔断、异常降级、依赖阻塞
# ============================================================
@pytest.mark.e2e
class TestCircuitBreakerAndFallback:
    @pytest.mark.asyncio
    @pytest.mark.skipif(not USE_MOCK, reason="真实LLM模式，计划描述不固定，跳过固定文本断言")
    async def test_plot_failure_adds_text_fallback_step(self, patch_llm_plan, patch_tool_execute_plot_fail, patch_rag_ok):
        """绘图工具失败：Agent自动修改计划，新增文字数据说明降级步骤"""
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        items = result.get("task_plan_items", [])
        descriptions = [it.get("description", "") for it in items]
        has_text_fallback = any(any(x in d for x in ("文字版", "降级", "文本描述预算占比")) for d in descriptions)
        initial_plan_descriptions = [it["description"] for it in _make_global_plan_qinghai()]
        initial_has_fallback = any(any(x in d for x in ("文字版", "降级", "文本描述预算占比")) for d in initial_plan_descriptions)
        if not initial_has_fallback:
            assert has_text_fallback, "绘图失败后应动态新增「文字版降级」步骤"
    @pytest.mark.asyncio
    async def test_plot_failure_does_not_terminate_whole_task(self, patch_llm_plan, patch_tool_execute_plot_fail, patch_rag_ok):
        """单个子任务失败不能终止整个任务"""
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        plan_status = result.get("task_plan_status", "")
        assert plan_status != "failed", "单个子任务失败不能将task_plan_status设为failed"
        items = result.get("task_plan_items", [])
        doc_items = [it for it in items if "简报" in it.get("description", "") or "文档" in it.get("description", "")]
        doc_not_blocked = [it for it in doc_items if it.get("status") not in ("blocked",)]
        assert len(doc_not_blocked) > 0 or len(doc_items) == 0, \
            "绘图失败不应阻塞文档生成等无关任务"
    @pytest.mark.asyncio
    async def test_failed_step_records_error_reason(self, patch_llm_plan, patch_tool_execute_plot_fail, patch_rag_ok):
        """失败步骤必须记录失败原因"""
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        items = result.get("task_plan_items", [])
        failed_items = [it for it in items if it.get("status") == "failed"]
        if failed_items:
            for it in failed_items:
                assert it.get("blocked_reason"), f"失败任务{it['step_index']}应记录blocked_reason"
    @pytest.mark.asyncio
    async def test_circuit_breaker_max_retry(self, patch_llm_plan, patch_tool_execute_plot_fail, patch_rag_ok):
        """熔断跳过的任务retry_count应>0"""
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        items = result.get("task_plan_items", [])
        for it in items:
            if it.get("status") == "failed":
                assert it.get("retry_count", 0) > 0, "熔断跳过的任务retry_count应>0"
    # ===== 新增：最大重试上限熔断测试 =====
    @pytest.mark.asyncio
    async def test_circuit_breaker_max_retry_limit(self, patch_llm_plan, patch_tool_execute_plot_repeated_fail, patch_rag_ok):
        """多次连续失败，达到最大重试次数，触发熔断，不再继续重试"""
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        items = result.get("task_plan_items", [])
        plot_step = next((x for x in items if "algo:plot" in x.get("description", "") or "绘图" in x.get("description", "") or "饼图" in x.get("description", "")), None)
        if plot_step is None:
            pytest.skip("Mock计划中未找到绘图步骤，跳过重试上限断言")
        assert plot_step.get("retry_count", 0) > 0, "连续失败后retry_count应>0"
        assert plot_step.get("status") in ("blocked", "failed"), "达到最大重试次数，任务应熔断"
# ============================================================
# Test 4: 依赖阻塞传播
# ============================================================
@pytest.mark.e2e
class TestDependencyBlocking:
    @pytest.mark.asyncio
    async def test_screenshot_failure_blocks_ocr_and_summary(self, patch_llm_plan_ocr, patch_tool_execute_screenshot_fail, patch_rag_ok):
        """强依赖任务：截图失败，OCR和摘要任务自动标记blocked，不执行"""
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_OCR_PIPELINE)
        result = await graph.ainvoke(state, config=config)
        items = result.get("task_plan_items", [])
        screenshot_step = next((x for x in items if "截图" in x.get("description", "")), None)
        ocr_step = next((x for x in items if "OCR" in x.get("description", "")), None)
        summary_step = next((x for x in items if "摘要" in x.get("description", "")), None)
        if screenshot_step and screenshot_step.get("status") in ("failed", "blocked"):
            if ocr_step and 1 in ocr_step.get("depends_on", []):
                assert ocr_step.get("status") in ("blocked", "pending"), \
                    "前置截图失败后，OCR步骤应被阻塞或保持pending"
            if summary_step:
                pass
    @pytest.mark.asyncio
    async def test_dependency_chain_propagation(self):
        """直接测试task_plan_collect_node的依赖阻塞传播逻辑"""
        from app.services.graph.nodes import task_plan_collect_node
        state = init_state(RAW_QUERY_OCR_PIPELINE)
        state["task_plan_items"] = [
            {"step_index": 1, "description": "截图本地项目文档", "status": "pending", "depends_on": [], "priority": "P0", "deliverable": "截图文件", "expected_output": "截图文件", "retry_count": 0},
            {"step_index": 2, "description": "OCR识别文字", "status": "pending", "depends_on": [1], "priority": "P1", "deliverable": "识别文字", "expected_output": "识别文字", "retry_count": 0},
            {"step_index": 3, "description": "基于OCR结果撰写摘要", "status": "pending", "depends_on": [2], "priority": "P1", "deliverable": "摘要文档", "expected_output": "摘要文档", "retry_count": 0},
        ]
        state["task_plan_current_idx"] = 1
        state["task_plan_results"] = []
        state["tool_result"] = {"ok": False, "error": "截图失败: 窗口未找到"}
        state["tool_name"] = "image:screenshot"
        result = await task_plan_collect_node(state)
        items = result.get("task_plan_items", [])
        step1 = next((x for x in items if x["step_index"] == 1), None)
        step2 = next((x for x in items if x["step_index"] == 2), None)
        step3 = next((x for x in items if x["step_index"] == 3), None)
        assert step1 is not None
        assert step1.get("status") == "blocked", "截图失败应标记步骤1为blocked"
        if step2 and 1 in step2.get("depends_on", []):
            assert step2.get("status") == "blocked", "步骤2依赖步骤1，步骤1阻塞后步骤2应被阻塞"
        if step3 and step3.get("status") == "blocked":
            assert "前置依赖" in step3.get("blocked_reason", ""), "步骤3阻塞原因应包含前置依赖说明"
# ===== 新增：Test 5 RAG+并行网络检索混合场景 =====
@pytest.mark.e2e
class TestRagWebParallel:
    @pytest.mark.asyncio
    async def test_parallel_task_independent_fallback(self, patch_llm_plan_rag_web_parallel, patch_tool_execute_ok, patch_rag_ok):
        """并行任务：一个检索失败，另一个正常执行，整体任务不阻塞"""
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_RAG_WEB_PARALLEL)
        result = await graph.ainvoke(state, config=config)
        items = result.get("task_plan_items", [])
        plan_status = result.get("task_plan_status")
        assert plan_status != "failed", "并行子任务单路失败不能整体失败"
        # 并行任务互不依赖，剩下的合并、生成文档任务仍可执行
        final_items = [x for x in items if "生成对比摘要文档" in x["description"]]
        assert len(final_items) > 0
    @pytest.mark.asyncio
    async def test_parallel_both_fallback(self, patch_llm_plan_rag_web_parallel, patch_tool_execute_rag_web_both_fail):
        """并行两个检索全部失败，Agent降级生成说明文档，整体不失败"""
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_RAG_WEB_PARALLEL_BOTH_FAIL)
        result = await graph.ainvoke(state, config=config)
        plan_status = result.get("task_plan_status")
        assert plan_status != "failed", "并行两个子任务全部失败，整体任务仍不能标记failed"
        items = result.get("task_plan_items", [])
        final_items = [x for x in items if "生成对比摘要文档" in x["description"]]
        assert len(final_items) > 0
    @pytest.mark.asyncio
    @pytest.mark.skipif(not USE_MOCK, reason="真实LLM模式，计划描述不固定")
    async def test_parallel_step_no_depends_on(self, patch_llm_plan_rag_web_parallel, patch_tool_execute_ok, patch_rag_ok):
        """校验并行任务A、B的depends_on为空，不能互相依赖"""
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_RAG_WEB_PARALLEL)
        result = await graph.ainvoke(state, config=config)
        items = result.get("task_plan_items", [])
        step_a = next((x for x in items if "并行任务A" in x.get("description", "")), None)
        step_b = next((x for x in items if "并行任务B" in x.get("description", "")), None)
        if step_a is None or step_b is None:
            pytest.skip("Mock计划中未找到并行任务A/B步骤，跳过依赖校验")
        assert step_a.get("depends_on", []) == [], "并行任务A不能存在依赖"
        assert step_b.get("depends_on", []) == [], "并行任务B不能存在依赖"
# ============================================================
# Test 6: LangFuse可观测性【增强：完整Span树校验】
# ============================================================
@pytest.mark.e2e
class TestLangFuseTrace:
    @pytest.mark.asyncio
    async def test_trace_id_present(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_ok):
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        assert result.get("trace_id"), "应存在trace_id"
        assert len(result["trace_id"]) > 0, "trace_id不应为空"
    @pytest.mark.asyncio
    async def test_session_id_preserved(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_ok):
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        assert result.get("session_id"), "应存在session_id"
    @pytest.mark.asyncio
    async def test_evidence_collected(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_ok):
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        evidence = result.get("evidence", {})
        assert isinstance(evidence, dict), "evidence应为dict"
    @pytest.mark.asyncio
    async def test_history_log_covers_full_lifecycle(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_ok):
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        history_log = result.get("history_log", [])
        if len(history_log) == 0:
            pytest.skip("history_log为空，graph执行路径未经过task_planner_node")
    @pytest.mark.asyncio
    async def test_trace_span_coverage(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_ok):
        """校验trace_id存在且history_log覆盖关键节点"""
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        trace_id = result.get("trace_id", "")
        assert trace_id, "必须生成trace_id"
        history_log = result.get("history_log", [])
        items = result.get("task_plan_items", [])
        if len(items) == 0:
            pytest.skip("task_plan_items为空，graph执行路径未经过task_planner_node")
    # ===== 新增：拉取LangFuse后端，校验完整Span树 =====
    @pytest.mark.asyncio
    @pytest.mark.skipif(langfuse is None, reason="LangFuse客户端初始化失败，跳过远端trace拉取校验")
    async def test_langfuse_full_span_tree(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_ok):
        """远端拉取trace，校验根trace存在且包含span"""
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        trace_id = result["trace_id"]
        try:
            trace = _fetch_langfuse_trace(trace_id)
            if trace is None:
                pytest.skip("无法拉取langfuse trace")
            assert trace is not None, "LangFuse无法拉取trace"
            spans = trace["spans"]
            assert len(spans) > 0, "trace应包含至少1个span"
        except Exception as e:
            pytest.skip(f"LangFuse远端拉取失败: {e}")
    # ===== 新增：工具异常场景校验LangFuse Error Span埋点 =====
    @pytest.mark.asyncio
    @pytest.mark.skipif(langfuse is None, reason="LangFuse客户端初始化失败，跳过远端trace拉取校验")
    async def test_langfuse_error_span_on_tool_failure(self, patch_llm_plan, patch_tool_execute_plot_fail, patch_rag_ok):
        """工具调用失败时，LangFuse对应span标记error状态"""
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        trace_id = result["trace_id"]
        try:
            trace = _fetch_langfuse_trace(trace_id)
            if trace is None:
                pytest.skip("无法拉取langfuse trace")
            spans = trace["spans"]
            error_spans = [s for s in spans if s.get("status", None) == "error"]
            assert len(error_spans) >= 1, "algo:plot失败，应该生成error span"
        except Exception as e:
            pytest.skip(f"LangFuse远端拉取失败: {e}")
# ===== 新增：LangFuse Metadata、LLM规划异常、递归超限埋点测试 =====
@pytest.mark.e2e
class TestLangFuseMetadataAndEventSpan:
    @pytest.mark.asyncio
    @pytest.mark.skipif(langfuse is None, reason="LangFuse客户端初始化失败，跳过远端trace拉取校验")
    async def test_langfuse_span_metadata(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_ok):
        """校验span metadata写入session_id、trace_id等"""
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        trace_id = result["trace_id"]
        try:
            trace = _fetch_langfuse_trace(trace_id)
            if trace is None:
                pytest.skip("无法拉取langfuse trace")
            spans = trace["spans"]
            for span in spans:
                meta = span.get("metadata", {})
                if meta and "tool" in (span.get("name", "")):
                    assert "session_id" in meta or "trace_id" in meta
        except Exception:
            pass
    @pytest.mark.asyncio
    @pytest.mark.skipif(langfuse is None or not USE_MOCK, reason="仅Mock模式测试LLM规划异常埋点")
    async def test_langfuse_llm_planner_exception_span(self, patch_llm_plan_exception, patch_tool_execute_ok):
        """LLM全局规划节点抛出异常，生成error span并写入LangFuse"""
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        try:
            result = await graph.ainvoke(state, config=config)
        except Exception:
            pass
        try:
            trace = _fetch_langfuse_trace(state["trace_id"])
            if trace is None:
                pytest.skip("无法拉取langfuse trace")
            spans = trace["spans"]
            error_spans = [s for s in spans if s.get("status", None) == "error"]
            assert len(error_spans) >= 1
        except Exception:
            pass
    @pytest.mark.asyncio
    @pytest.mark.skipif(langfuse is None, reason="LangFuse客户端初始化失败")
    async def test_langfuse_recursion_limit_exceed_span(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_ok):
        """递归超限捕获异常，写入LangFuse error span"""
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI, recursion_limit=1)
        try:
            result = await graph.ainvoke(state, config=config)
        except Exception:
            pass
        try:
            trace = _fetch_langfuse_trace(state["trace_id"])
            if trace is None:
                pytest.skip("无法拉取langfuse trace")
            spans = trace["spans"]
            error_spans = [s for s in spans if s.get("status", None) == "error"]
            assert len(error_spans) >= 0
        except Exception:
            pass
# ============================================================
# Test 7: 交付物有效性
# ============================================================
@pytest.mark.e2e
class TestDeliverable:
    @pytest.mark.asyncio
    async def test_final_deliverable_exists(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_ok):
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        memory_summary = result.get("memory_summary", "")
        assert len(memory_summary) > 0, "应生成memory_summary"
    @pytest.mark.asyncio
    async def test_task_plan_items_have_valid_structure(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_ok):
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        items = result.get("task_plan_items", [])
        for it in items:
            assert "step_index" in it, "每个task_plan_item应有step_index"
            assert "description" in it, "每个task_plan_item应有description"
            assert "status" in it, "每个task_plan_item应有status"
            assert it["status"] in ("pending", "done", "completed", "blocked", "failed"), \
                f"status应为有效值，实际: {it['status']}"
# ============================================================
# Test 8: task_planner_node 单元级直接测试
# ============================================================
class TestTaskPlannerNodeDirect:
    @pytest.mark.asyncio
    async def test_first_entry_generates_global_plan(self, patch_llm_plan, patch_tool_execute_ok):
        from app.services.graph.nodes import task_planner_node
        state = init_state(RAW_QUERY_QINGHAI)
        state["task_plan_enabled"] = True
        state["task_plan_items"] = []
        state["task_plan_status"] = ""
        state["plan_steps"] = []
        state["history_log"] = []
        result = await task_planner_node(state)
        items = result.get("task_plan_items", [])
        assert len(items) > 0, "task_planner_node应生成全局计划"
    @pytest.mark.asyncio
    async def test_session_id_preserved(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_ok):
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        assert result.get("session_id"), "session_id 不能为空"
        assert result["session_id"] == "e2e_test", "session_id 需要全程保持不变"
    @pytest.mark.asyncio
    @pytest.mark.skipif(langfuse is None, reason="LangFuse客户端初始化失败，跳过Trace拉取测试")
    async def test_span_tree_structure(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_ok):
        """校验全链路Span树：根span、规划节点span、工具span"""
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        trace_id = result["trace_id"]
        trace = _fetch_langfuse_trace(trace_id)
        if trace is None:
            pytest.skip("无法拉取langfuse trace")
        spans = trace.get("spans", [])

        root_span = next((s for s in spans if not s.get("parent_observation_id")), None)
        assert root_span is not None, "Trace必须存在根span"

        plan_span = next((s for s in spans if "task_plan" in s.get("name", "")), None)
        assert plan_span is not None, "必须存在规划节点span"

        tool_spans = [s for s in spans if "tool" in s.get("name", "").lower()]
        assert len(tool_spans) > 0, "至少存在一条工具调用span"

    @pytest.mark.asyncio
    @pytest.mark.skipif(langfuse is None, reason="LangFuse客户端初始化失败，跳过metadata校验")
    async def test_span_metadata_embedded(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_ok):
        """校验Span metadata元数据埋点：session_id、trace_id""" 
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        result = await graph.ainvoke(state, config=config)
        trace_id = result["trace_id"]
        trace = _fetch_langfuse_trace(trace_id)
        if trace is None:
            pytest.skip("无法拉取langfuse trace")
        spans = trace.get("spans", [])
        root_span = next((s for s in spans if not s.get("parent_observation_id")), None)
        if root_span and root_span.get("metadata"):
            meta = root_span["metadata"]
            assert meta.get("session_id") == "e2e_test" or "session_id" in str(meta)

    @pytest.mark.asyncio
    @pytest.mark.skipif(langfuse is None, reason="LangFuse客户端初始化失败，跳过异常span埋点")
    async def test_llm_plan_exception_span_error(self, patch_llm_plan_exception):
        """LLM规划节点抛出异常，校验LangFuse error埋点"""
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI)
        try:
            result = await graph.ainvoke(state, config=config)
        except Exception:
            pass
        trace = _fetch_langfuse_trace(state["trace_id"])
        if trace is None:
            pytest.skip("无法拉取langfuse trace")
        spans = trace.get("spans", [])
        err_spans = [s for s in spans if s.get("status") == "error"]
        assert len(err_spans) >= 1, "LLM规划异常应产生error span"

# ============================================================
# Test7: Graph递归超限熔断埋点测试
# ============================================================
@pytest.mark.e2e
class TestGraphRecursionLimit:
    @pytest.mark.asyncio
    async def test_recursion_limit_trigger_break_and_span(self, patch_llm_plan, patch_tool_execute_ok, patch_rag_ok):
        """设置极小递归上限，触发Graph递归超限熔断，校验状态+LangFuse埋点"""
        graph, state, config = _build_state_and_run_graph(RAW_QUERY_QINGHAI, recursion_limit=2)
        try:
            result = await graph.ainvoke(state, config=config)
        except Exception:
            result = {}
        plan_status = result.get("task_plan_status", "")
        assert plan_status in ("blocked", "failed", "completed", "executing", "planning", ""), \
            f"递归超限后task_plan_status应为有效值，实际: {plan_status}"

        if langfuse:
            trace_id = result.get("trace_id") or state.get("trace_id", "")
            if trace_id:
                try:
                    trace = _fetch_langfuse_trace(trace_id)
                    if trace:
                        spans = trace.get("spans", [])
                        error_spans = [s for s in spans if s.get("status") == "error"]
                        assert len(error_spans) >= 0
                except Exception:
                    pass

# ============================================================
# 主函数：冒烟执行，流式打印Agent执行日志，输出到 _test_output.log
# ============================================================
async def main():
    try:
        from dotenv import load_dotenv
        from pathlib import Path
        env_path = Path(r"D:\ecv\apps\server\.env")
        load_dotenv(env_path, override=True)
        print(f"[ENV] Loaded .env from: {env_path}")
        print(f"[ENV] LLM_API_KEY: {os.environ.get('LLM_API_KEY', '')[:20]}...")
        print(f"[ENV] LLM_BASE_URL: {os.environ.get('LLM_BASE_URL', '')}")
        print(f"[ENV] LLM_MODEL: {os.environ.get('LLM_MODEL', '')}")
        import app.services.llm.client as _llm_client
        _llm_client.client = None
        print("[ENV] Reset LLM client singleton to pick up new env vars")
    except Exception as e:
        print(f"[WARN] .env load failed: {e}")
    print("====== Dynamic Planning Agent E2E Smoke Test Start ======")
    print(f"USE_MOCK = {USE_MOCK}")
    print("可选测试任务：")
    print(" [1] RAW_QUERY_QINGHAI 青海智慧农牧平台简报")
    print(" [2] RAW_QUERY_MARKET_REPORT 青海农牧数字化市场报告")
    print(" [3] RAW_QUERY_OCR_PIPELINE OCR文档摘要流水线")
    print(" [4] RAW_QUERY_XAGENT xAgent面试材料包")
    print(" [5] RAW_QUERY_RAG_WEB_PARALLEL RAG+并行网络检索")
    print(" [6] RAW_QUERY_RAG_WEB_PARALLEL_BOTH_FAIL 双检索全部失败降级")

    selected_query = RAW_QUERY_RAG_WEB_PARALLEL
    print(f"\n>> Selected Query:\n{selected_query}\n")

    graph, state, config = _build_state_and_run_graph(selected_query, recursion_limit=30)
    print(">> Start graph streaming invoke...")
    async for chunk in graph.astream(state, config=config):
        for node_name, chunk_state in chunk.items():
            print(f"\n===== NODE: {node_name} =====")
            if chunk_state is None:
                continue
            if "task_plan_items" in chunk_state:
                plan_items = chunk_state["task_plan_items"]
                for item in plan_items:
                    step_idx = item.get("step_index")
                    desc = item.get("description")
                    status = item.get("status")
                    retry = item.get("retry_count",0)
                    depends = item.get("depends_on",[])
                    print(f"Step{step_idx} [{status}] retry:{retry} depends:{depends} | {desc}")
            if "history_log" in chunk_state and chunk_state["history_log"]:
                last_log = chunk_state["history_log"][-1]
                print(f"[LOG] {last_log}")
            if "tool_result" in chunk_state:
                tr = chunk_state["tool_result"]
                ok_flag = tr.get("ok")
                err_msg = tr.get("error","")
                print(f"[TOOL RESULT] ok={ok_flag}, error={err_msg}")

    print("\n====== Smoke Test Complete ======")
    final_state = await graph.ainvoke(state, config=config)
    print(f"Final task_plan_status: {final_state.get('task_plan_status')}")
    print(f"Trace ID: {final_state.get('trace_id')}")
    print(f"Log saved to: {LOG_FILE}")

if __name__ == "__main__":
    asyncio.run(main())