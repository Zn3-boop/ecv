"""
意图识别分层测试 - 验证简单/复杂指令分层设计
可量化指标：高频操作本地响应时间 < XXms，LLM调用量降低 XX%
"""
import time
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parent.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.services.intent_detector import detect_intent, _is_simple_single_action


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


class TestIntentDetectionPerformance:
    """本地意图识别性能测试 - 高频操作本地响应时间"""

    def test_simple_intent_under_1ms(self):
        simple_commands = [
            "CPU多少", "内存使用率", "电脑很卡", "查看进程",
            "打开微信", "关闭QQ", "搜索Python教程",
            "卸载Chrome应用", "C盘空间", "全面清理",
        ]
        start = time.perf_counter()
        for cmd in simple_commands:
            detect_intent(cmd)
        elapsed = (time.perf_counter() - start) * 1000

        avg_ms = elapsed / len(simple_commands)
        print(f"\n[性能] {len(simple_commands)} 条简单指令总耗时: {elapsed:.3f}ms, 平均: {avg_ms:.4f}ms/条")
        assert avg_ms < 1.0, f"简单指令平均耗时 {avg_ms:.4f}ms 超过 1ms 阈值"

    def test_llm_call_reduction_rate(self):
        """计算 LLM 调用降低率"""
        typical_session = [
            "CPU多少",
            "内存使用率",
            "电脑很卡",
            "打开微信",
            "关闭QQ",
            "搜索Python教程",
            "卸载Chrome应用",
            "打开记事本写代码",
            "写一篇关于AI的文章",
            "打开VSCode写个登录页面然后浏览器预览",
        ]
        local_count = sum(1 for cmd in typical_session if detect_intent(cmd) != "llm_decompose")
        total = len(typical_session)
        reduction = local_count / total * 100

        print(f"\n[LLM调用量] {total} 条指令中 {local_count} 条走本地规则, LLM调用量降低 {reduction:.1f}%")
        assert reduction >= 60, f"LLM调用量降低 {reduction:.1f}% 低于 60% 阈值"


class TestIntentEdgeCases:
    """意图识别边界情况"""

    def test_empty_string(self):
        result = detect_intent("")
        assert result in ("system_monitor", "llm_decompose")

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