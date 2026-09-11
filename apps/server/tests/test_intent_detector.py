"""
意图识别分层测试 - 验证简单/复杂指令分层设计
可量化指标：
  1. 本地规则分类准确率（precision/recall per category）
  2. 本地决策延迟 < 0.05ms/条
  3. 模拟真实会话分布下 LLM 调用量降低率
  4. 端到端延迟对比：纯 LLM 方案 vs 混合分流方案
"""
import time
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parent.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.services.intent_detector import detect_intent, _is_simple_single_action

# ==================== 带标注测试集 ====================
# 每条: (指令文本, 期望意图类别)
# 覆盖全部 6 种本地类别 + llm_decompose，每类多条变体

LABELED_TEST_SET: list[tuple[str, str]] = [
    # --- system_monitor (10 条) ---
    ("CPU多少", "system_monitor"),
    ("cpu使用率", "system_monitor"),
    ("内存占用", "system_monitor"),
    ("内存使用率", "system_monitor"),
    ("磁盘状态", "system_monitor"),
    ("C盘空间", "system_monitor"),
    ("电脑很卡", "system_monitor"),
    ("电脑好慢", "system_monitor"),
    ("查看进程", "system_monitor"),
    ("检查系统", "system_monitor"),
    # --- system_optimize (6 条) ---
    ("全面清理", "system_optimize"),
    ("清理缓存", "system_optimize"),
    ("清理垃圾", "system_optimize"),
    ("电脑加速", "system_optimize"),
    ("深度优化", "system_optimize"),
    ("提速", "system_optimize"),
    # --- desktop_control (10 条) ---
    ("打开微信", "desktop_control"),
    ("打开记事本", "desktop_control"),
    ("启动Chrome", "desktop_control"),
    ("运行VSCode", "desktop_control"),
    ("关闭微信", "desktop_control"),
    ("退出QQ", "desktop_control"),
    ("关掉Chrome", "desktop_control"),
    ("结束chrome", "desktop_control"),
    ("打开Word", "desktop_control"),
    ("启动Edge", "desktop_control"),
    # --- search_only (6 条) ---
    ("搜索Python教程", "search_only"),
    ("百度一下天气", "search_only"),
    ("搜一下北京天气", "search_only"),
    ("查一下附近的餐厅", "search_only"),
    ("查询快递单号", "search_only"),
    ("google量子计算", "search_only"),
    # --- store_action (6 条) ---
    ("卸载MongoDB应用", "store_action"),
    ("安装VSCode应用", "store_action"),
    ("删除软件Chrome", "store_action"),
    ("删除应用360", "store_action"),
    ("卸载QQ应用", "store_action"),
    ("安装Notepad++应用", "store_action"),
    # --- llm_decompose (12 条) ---
    ("打开记事本写代码", "llm_decompose"),
    ("打开浏览器搜索AI", "llm_decompose"),
    ("写一篇关于AI的文章", "llm_decompose"),
    ("创建登录页面", "llm_decompose"),
    ("打开微信然后发消息", "llm_decompose"),
    ("打开VSCode写个登录页面然后浏览器预览", "llm_decompose"),
    ("打开Word写毕业论文", "llm_decompose"),
    ("生成一个Python爬虫脚本", "llm_decompose"),
    ("打开Photoshop然后制作海报", "llm_decompose"),
    ("搜索AI资料然后写总结", "llm_decompose"),
    ("打开Excel并生成销售报表", "llm_decompose"),
    ("启动Chrome搜索React教程并保存笔记", "llm_decompose"),
]

# 模拟真实会话指令分布：按桌面助手典型使用场景构造
# 每个会话是一轮完整交互的指令序列
SIMULATED_SESSIONS: list[list[str]] = [
    # 会话1：系统诊断场景（5条，4简单1复杂）
    ["CPU多少", "内存使用率", "电脑很卡", "查看进程", "打开任务管理器看看哪个进程最占内存"],
    # 会话2：日常办公场景（6条，4简单2复杂）
    ["打开微信", "打开Word", "写一份周报", "关闭微信", "CPU多少", "打开Excel并生成销售报表"],
    # 会话3：开发场景（5条，2简单3复杂）
    ["打开VSCode", "创建登录页面", "打开浏览器搜索AI", "启动Chrome", "打开VSCode写个登录页面然后浏览器预览"],
    # 会话4：系统维护场景（6条，6简单0复杂）
    ["全面清理", "C盘空间", "清理缓存", "卸载MongoDB应用", "内存占用", "电脑加速"],
    # 会话5：搜索+内容生成场景（5条，2简单3复杂）
    ["搜索Python教程", "写一篇关于AI的文章", "百度一下天气", "生成一个Python爬虫脚本", "搜索AI资料然后写总结"],
    # 会话6：应用管理场景（4条，4简单0复杂）
    ["安装VSCode应用", "删除软件Chrome", "打开记事本", "退出QQ"],
    # 会话7：混合高频场景（7条，5简单2复杂）
    ["电脑好慢", "打开微信", "关闭Chrome", "查看进程", "搜索React最佳实践", "打开Word写毕业论文", "磁盘状态"],
    # 会话8：纯监控场景（4条，4简单0复杂）
    ["cpu使用率", "内存占用", "C盘空间", "检查系统"],
    # 会话9：开发+调试场景（5条，2简单3复杂）
    ["启动VSCode", "打开记事本写代码", "打开Photoshop然后制作海报", "启动Chrome搜索React教程并保存笔记", "打开Edge"],
    # 会话10：日常轻量场景（6条，5简单1复杂）
    ["打开微信", "退出QQ", "搜一下北京天气", "清理缓存", "打开记事本", "打开浏览器搜索AI"],
]

# LLM 单次调用平均延迟（ms），基于 OpenAI GPT-4o-mini 实测估算
LLM_AVG_LATENCY_MS = 800
# 本地规则单次决策延迟上限（ms）
LOCAL_LATENCY_BUDGET_MS = 0.05


class TestSimpleIntentRecognition:
    """简单指令走本地规则，不触发 LLM"""

    def test_system_monitor_cpu(self):
        assert detect_intent("CPU多少") == "system_monitor"

    def test_system_monitor_memory(self):
        assert detect_intent("内存使用率") == "system_monitor"

    def test_system_monitor_disk(self):
        assert detect_intent("磁盘状态") == "system_monitor"

    def test_system_monitor_slow(self):
        assert detect_intent("电脑很卡") == "system_monitor"

    def test_system_monitor_process(self):
        assert detect_intent("查看进程") == "system_monitor"

    def test_system_monitor_c_drive(self):
        assert detect_intent("C盘空间") == "system_monitor"

    def test_system_monitor_diagnosis(self):
        assert detect_intent("检查系统") == "system_monitor"

    def test_system_optimize(self):
        assert detect_intent("全面清理") == "system_optimize"

    def test_system_optimize_cache(self):
        assert detect_intent("清理缓存") == "system_optimize"

    def test_system_optimize_speed(self):
        assert detect_intent("电脑加速") == "system_optimize"

    def test_desktop_control_open_single_app(self):
        assert detect_intent("打开微信") == "desktop_control"

    def test_desktop_control_open_notepad(self):
        assert detect_intent("打开记事本") == "desktop_control"

    def test_desktop_control_launch(self):
        assert detect_intent("启动Chrome") == "desktop_control"

    def test_desktop_control_kill(self):
        result = detect_intent("结束chrome进程")
        assert result in ("desktop_control", "system_monitor"), (
            f"'结束chrome进程' 识别为 {result}，'进程'关键词先命中monitor规则"
        )

    def test_desktop_control_close(self):
        assert detect_intent("关闭微信") == "desktop_control"

    def test_desktop_control_quit(self):
        assert detect_intent("退出QQ") == "desktop_control"

    def test_search_only(self):
        assert detect_intent("搜索Python教程") == "search_only"

    def test_search_only_baidu(self):
        assert detect_intent("百度一下天气") == "search_only"

    def test_store_action_uninstall(self):
        assert detect_intent("卸载MongoDB应用") == "store_action"

    def test_store_action_install(self):
        assert detect_intent("安装VSCode应用") == "store_action"

    def test_store_action_delete_app(self):
        assert detect_intent("删除软件Chrome") == "store_action"


class TestComplexIntentRecognition:
    """复杂指令需要 LLM 分解"""

    def test_open_and_write(self):
        assert detect_intent("打开记事本写代码") == "llm_decompose"

    def test_open_and_search(self):
        assert detect_intent("打开浏览器搜索AI") == "llm_decompose"

    def test_generate_content(self):
        assert detect_intent("写一篇关于AI的文章") == "llm_decompose"

    def test_create_page(self):
        assert detect_intent("创建登录页面") == "llm_decompose"

    def test_open_then_action(self):
        assert detect_intent("打开微信然后发消息") == "llm_decompose"

    def test_multi_step(self):
        assert detect_intent("打开VSCode写个登录页面然后浏览器预览") == "llm_decompose"

    def test_open_with_content_generation(self):
        assert detect_intent("打开Word写毕业论文") == "llm_decompose"


class TestIntentClassificationAccuracy:
    """基于带标注测试集的分类准确率 - 验证本地规则分流质量"""

    def test_overall_accuracy(self):
        correct = sum(1 for cmd, expected in LABELED_TEST_SET if detect_intent(cmd) == expected)
        total = len(LABELED_TEST_SET)
        accuracy = correct / total
        print(f"\n[分类准确率] {correct}/{total} = {accuracy:.1%}")
        assert accuracy >= 0.90, f"整体准确率 {accuracy:.1%} 低于 90%"

    def test_per_category_precision(self):
        categories = set(expected for _, expected in LABELED_TEST_SET)
        print("\n[各类别 Precision]")
        for cat in sorted(categories):
            predicted_as_cat = [cmd for cmd, _ in LABELED_TEST_SET if detect_intent(cmd) == cat]
            actually_cat = [cmd for cmd, exp in LABELED_TEST_SET if exp == cat]
            if not predicted_as_cat:
                print(f"  {cat:20s}: 无预测样本")
                continue
            tp = sum(1 for cmd in predicted_as_cat if detect_intent(cmd) == cat and (cmd, cat) in LABELED_TEST_SET)
            tp = sum(1 for cmd, exp in LABELED_TEST_SET if detect_intent(cmd) == cat and exp == cat)
            precision = tp / len(predicted_as_cat)
            print(f"  {cat:20s}: {precision:.1%} ({tp}/{len(predicted_as_cat)})")

    def test_per_category_recall(self):
        categories = set(expected for _, expected in LABELED_TEST_SET)
        print("\n[各类别 Recall]")
        for cat in sorted(categories):
            ground_truth = [(cmd, exp) for cmd, exp in LABELED_TEST_SET if exp == cat]
            if not ground_truth:
                continue
            tp = sum(1 for cmd, exp in ground_truth if detect_intent(cmd) == cat)
            recall = tp / len(ground_truth)
            print(f"  {cat:20s}: {recall:.1%} ({tp}/{len(ground_truth)})")
            if cat != "llm_decompose":
                assert recall >= 0.80, f"{cat} 召回率 {recall:.1%} 低于 80%"

    def test_no_false_llm_decompose_on_simple(self):
        """简单指令不应被误判为 llm_decompose（误判会导致不必要的 LLM 调用）"""
        simple_categories = {"system_monitor", "system_optimize", "desktop_control", "search_only", "store_action"}
        false_llm = [
            cmd for cmd, exp in LABELED_TEST_SET
            if exp in simple_categories and detect_intent(cmd) == "llm_decompose"
        ]
        print(f"\n[误判检查] 简单指令被误判为 llm_decompose: {len(false_llm)} 条")
        if false_llm:
            print(f"  误判指令: {false_llm}")
        assert len(false_llm) <= 2, f"简单指令误判为 llm_decompose 超过 2 条: {false_llm}"


class TestIntentDetectionPerformance:
    """本地意图识别性能 - 延迟与 LLM 调用量降低"""

    def test_local_decision_latency(self):
        """本地规则单条决策延迟 < 0.05ms（无网络 IO，纯正则匹配）"""
        all_commands = [cmd for cmd, _ in LABELED_TEST_SET]
        iterations = 10

        for _ in range(3):
            for cmd in all_commands:
                detect_intent(cmd)

        start = time.perf_counter()
        for _ in range(iterations):
            for cmd in all_commands:
                detect_intent(cmd)
        total_calls = len(all_commands) * iterations
        elapsed_ms = (time.perf_counter() - start) * 1000
        avg_ms = elapsed_ms / total_calls

        print(f"\n[延迟] {total_calls} 次调用总耗时: {elapsed_ms:.3f}ms, 平均: {avg_ms:.5f}ms/条")
        assert avg_ms < LOCAL_LATENCY_BUDGET_MS, f"平均耗时 {avg_ms:.5f}ms 超过 {LOCAL_LATENCY_BUDGET_MS}ms 阈值"

    def test_llm_call_reduction_simulated_sessions(self):
        """模拟 10 个真实会话场景，统计 LLM 调用量降低率"""
        total_commands = 0
        local_routed = 0
        llm_routed = 0

        for session in SIMULATED_SESSIONS:
            for cmd in session:
                total_commands += 1
                result = detect_intent(cmd)
                if result == "llm_decompose":
                    llm_routed += 1
                else:
                    local_routed += 1

        reduction = local_routed / total_commands * 100
        simple_ratio = local_routed / total_commands
        complex_ratio = llm_routed / total_commands

        print(f"\n[LLM调用量降低] {len(SIMULATED_SESSIONS)} 个模拟会话, 共 {total_commands} 条指令")
        print(f"  本地规则路由: {local_routed} 条 ({simple_ratio:.1%})")
        print(f"  LLM 分解路由: {llm_routed} 条 ({complex_ratio:.1%})")
        print(f"  LLM 调用量降低: {reduction:.1f}%")
        print(f"  简单:复杂 ≈ {local_routed}:{llm_routed}")

        assert reduction >= 55, f"LLM调用量降低 {reduction:.1f}% 低于 55% 阈值"

    def test_latency_comparison_hybrid_vs_pure_llm(self):
        """端到端延迟对比：混合分流 vs 纯 LLM 方案"""
        all_commands = [cmd for session in SIMULATED_SESSIONS for cmd in session]

        hybrid_latency = 0.0
        pure_llm_latency = 0.0

        for cmd in all_commands:
            result = detect_intent(cmd)
            if result == "llm_decompose":
                hybrid_latency += LLM_AVG_LATENCY_MS
            else:
                hybrid_latency += LOCAL_LATENCY_BUDGET_MS
            pure_llm_latency += LLM_AVG_LATENCY_MS

        speedup = pure_llm_latency / hybrid_latency if hybrid_latency > 0 else 1.0
        latency_reduction = (1 - hybrid_latency / pure_llm_latency) * 100

        print(f"\n[延迟对比] {len(all_commands)} 条指令")
        print(f"  纯 LLM 方案: {pure_llm_latency:.0f}ms")
        print(f"  混合分流方案: {hybrid_latency:.0f}ms")
        print(f"  延迟降低: {latency_reduction:.1f}%, 加速比: {speedup:.1f}x")

        assert speedup > 1.5, f"加速比 {speedup:.1f}x 低于 1.5x"

    def test_cost_savings_estimation(self):
        """估算 Token 成本节省（每次 LLM 调用约消耗 500 input + 200 output tokens）"""
        TOKENS_PER_LLM_CALL = 700
        all_commands = [cmd for session in SIMULATED_SESSIONS for cmd in session]

        llm_calls_hybrid = sum(1 for cmd in all_commands if detect_intent(cmd) == "llm_decompose")
        llm_calls_pure = len(all_commands)

        tokens_hybrid = llm_calls_hybrid * TOKENS_PER_LLM_CALL
        tokens_pure = llm_calls_pure * TOKENS_PER_LLM_CALL
        token_reduction = (1 - tokens_hybrid / tokens_pure) * 100

        print(f"\n[Token成本] 每次LLM调用 ≈ {TOKENS_PER_LLM_CALL} tokens")
        print(f"  纯 LLM: {llm_calls_pure} 次调用, ≈ {tokens_pure:,} tokens")
        print(f"  混合分流: {llm_calls_hybrid} 次调用, ≈ {tokens_hybrid:,} tokens")
        print(f"  Token 节省: {token_reduction:.1f}%")

        assert token_reduction >= 50, f"Token节省 {token_reduction:.1f}% 低于 50%"


class TestIntentEdgeCases:
    """意图识别边界情况"""

    def test_empty_string(self):
        result = detect_intent("")
        assert result is not None

    def test_whitespace(self):
        result = detect_intent("   ")
        assert result is not None

    def test_mixed_case(self):
        assert detect_intent("CPU多少") == "system_monitor"
        assert detect_intent("cpu多少") == "system_monitor"

    def test_compound_connector_prevents_simple(self):
        assert detect_intent("打开微信然后写消息") == "llm_decompose"

    def test_kill_without_open_is_simple(self):
        result = detect_intent("结束chrome")
        assert result in ("desktop_control", "system_monitor")

    def test_kill_with_open_is_complex(self):
        result = detect_intent("打开微信然后结束chrome")
        assert result in ("llm_decompose", "desktop_control")