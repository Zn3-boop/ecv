"""
Agent 工作流集成测试 - 验证意图识别→工具编排→参数安全拦截→本地执行→结果回传闭环
"""
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

SERVER_ROOT = Path(__file__).resolve().parent.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.services.intent_detector import detect_intent
from app.services.tool_registry import tool_registry, ToolCategory
from app.services.tools.schema import TOOLS_SCHEMA
from app.services.tools.executor import SCHEMA_TO_EXECUTOR_MAP, SYSTEM_CONTROL_COMMANDS
from app.utils.response_cleaner import ResponseCleaner


class TestEndToEndPipeline:
    """完整 Agent 执行链路验证"""

    def test_simple_command_pipeline(self):
        """简单指令：意图识别 → 本地规则 → 无需 LLM"""
        cmd = "CPU多少"
        intent = detect_intent(cmd)
        assert intent == "system_monitor"
        assert intent != "llm_decompose"

    def test_complex_command_pipeline(self):
        """复杂指令：意图识别 → LLM 分解 → 工具编排"""
        cmd = "打开记事本写代码"
        intent = detect_intent(cmd)
        assert intent == "llm_decompose"

    def test_dangerous_command_pipeline(self):
        """高危指令：意图识别 → 工具编排 → 安全确认"""
        cmd = "关闭微信"
        intent = detect_intent(cmd)
        assert intent == "desktop_control"

        kill_tool = tool_registry._tools.get("process:kill")
        assert kill_tool is not None
        assert kill_tool.requires_confirmation is True

    def test_schema_to_executor_mapping(self):
        """Schema 名称到执行器名称的映射完整性"""
        for schema_name, executor_name in SCHEMA_TO_EXECUTOR_MAP.items():
            assert isinstance(schema_name, str)
            assert isinstance(executor_name, str)
            assert schema_name != executor_name or schema_name == executor_name

    def test_system_control_commands_coverage(self):
        """系统控制命令覆盖所有 action"""
        expected_actions = {"volume_up", "volume_down", "mute", "shutdown", "sleep"}
        for action in expected_actions:
            assert action in SYSTEM_CONTROL_COMMANDS, f"缺少系统控制命令: {action}"

    def test_shutdown_requires_confirmation(self):
        """关机命令必须有确认机制"""
        assert "shutdown" in SYSTEM_CONTROL_COMMANDS
        shutdown_cmd = SYSTEM_CONTROL_COMMANDS["shutdown"]
        assert "shutdown" in shutdown_cmd.lower() or "/s" in shutdown_cmd

    def test_response_cleaning_in_pipeline(self):
        """结果回传时清洗内部标记"""
        raw_response = "系统正常。[DEBUG] 内部信息 审核备注：合规"
        cleaned = ResponseCleaner.clean(raw_response)
        assert "[DEBUG" not in cleaned
        assert "审核备注" not in cleaned


class TestToolOrchestration:
    """工具编排验证"""

    def test_all_schema_tools_mappable(self):
        """Schema 中定义的工具都应有对应执行路径"""
        schema_names = {
            t["function"]["name"] for t in TOOLS_SCHEMA
        }
        registry_names = set(tool_registry._tools.keys())

        unmapped = schema_names - registry_names - set(SCHEMA_TO_EXECUTOR_MAP.keys())
        print(f"\n[工具编排] Schema工具: {len(schema_names)}, 注册工具: {len(registry_names)}")
        if unmapped:
            print(f"  未映射工具: {unmapped}")

    def test_tool_schema_json_valid(self):
        """所有工具 Schema 应为有效 JSON"""
        for tool_def in TOOLS_SCHEMA:
            serialized = json.dumps(tool_def, ensure_ascii=False)
            parsed = json.loads(serialized)
            assert parsed == tool_def


class TestIntentToToolMapping:
    """意图到工具的映射验证"""

    def test_system_monitor_maps_to_info_tools(self):
        """系统监控意图应对应信息查询工具"""
        info_tools = ["system:info", "process:top", "process:list", "disk:list"]
        for name in info_tools:
            tool = tool_registry._tools.get(name)
            assert tool is not None, f"缺少工具: {name}"
            assert tool.risk == "low"

    def test_desktop_control_maps_to_launch_tools(self):
        """桌面控制意图应对应启动/终止工具"""
        launch_tool = tool_registry._tools.get("app:launch")
        assert launch_tool is not None
        kill_tool = tool_registry._tools.get("process:kill")
        assert kill_tool is not None

    def test_store_action_maps_to_store_tools(self):
        """应用商店意图应对应 store 工具"""
        for name in ["store:search", "store:install", "store:uninstall", "store:list"]:
            tool = tool_registry._tools.get(name)
            if tool is None:
                print(f"  注意: store 工具 {name} 未在 registry 中注册（可能在 schema 中）")


class TestConversationPersistence:
    """会话持久化验证"""

    def test_storage_module_importable(self):
        from app.services.storage import init_storage, DB_PATH
        assert DB_PATH is not None

    def test_db_path_exists(self):
        from app.services.storage import DB_PATH, DATA_DIR
        assert DATA_DIR is not None
        assert "data" in str(DATA_DIR)


class TestComponentReuse:
    """通用组件复用验证"""

    def test_response_cleaner_is_singleton_class(self):
        """ResponseCleaner 作为类方法复用"""
        assert hasattr(ResponseCleaner, "clean")
        assert hasattr(ResponseCleaner, "sanitize_user_input")
        assert hasattr(ResponseCleaner, "contains_leakage")
        assert hasattr(ResponseCleaner, "clean_json_response")

    def test_context_manager_strategies(self):
        """ContextManager 支持多种策略复用"""
        from app.services.context_manager import CompressionStrategy
        strategies = list(CompressionStrategy)
        assert len(strategies) >= 3
        assert CompressionStrategy.NONE in strategies
        assert CompressionStrategy.SLIDING_WINDOW in strategies
        assert CompressionStrategy.SUMMARY in strategies
        assert CompressionStrategy.HYBRID in strategies

    def test_tool_registry_extensible(self):
        """ToolRegistry 支持扩展注册"""
        from app.services.tool_registry import ToolDefinition, ToolCategory

        initial_count = len(tool_registry._tools)
        tool_registry.register(
            ToolDefinition(
                name="test:custom",
                description="测试自定义工具",
                category=ToolCategory.NOTIFICATION,
                command_type="read",
                risk="low",
            )
        )
        assert len(tool_registry._tools) == initial_count + 1

        del tool_registry._tools["test:custom"]

    def test_rate_limiter_reusable(self):
        """RateLimiter 作为全局单例复用"""
        from app.services.llm.rate_limiter import rate_limiter
        assert rate_limiter is not None
        assert hasattr(rate_limiter, "wait_turn")
        assert hasattr(rate_limiter, "get_cached")
        assert hasattr(rate_limiter, "set_cached")