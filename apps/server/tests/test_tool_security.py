"""
工具调用安全管控测试 - 验证风险分级、高危确认、参数校验
可量化指标：高危工具确认覆盖率 100%，参数校验拦截率
"""
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parent.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.services.tool_registry import (
    ToolRegistry,
    ToolDefinition,
    ToolCategory,
    tool_registry,
)
from app.services.tools.schema import TOOLS_SCHEMA


class TestToolRiskClassification:
    """工具风险分级体系"""

    def test_dangerous_tools_require_confirmation(self):
        """高危工具必须要求人工确认"""
        dangerous_tools = [
            t for t in tool_registry._tools.values()
            if t.category == ToolCategory.DANGEROUS
        ]
        assert len(dangerous_tools) > 0, "应存在高危工具"

        for tool in dangerous_tools:
            assert tool.requires_confirmation is True, (
                f"高危工具 {tool.name} 必须设置 requires_confirmation=True"
            )
            assert tool.risk == "high", (
                f"高危工具 {tool.name} 风险等级应为 high"
            )

    def test_read_tools_are_safe(self):
        """读取类工具应为低风险"""
        read_tools = [
            t for t in tool_registry._tools.values()
            if t.command_type == "read"
        ]
        for tool in read_tools:
            assert tool.risk in ("low", "medium"), (
                f"读取工具 {tool.name} 风险等级应为 low/medium，实际为 {tool.risk}"
            )
            assert tool.requires_confirmation is False, (
                f"读取工具 {tool.name} 不应要求确认"
            )

    def test_destructive_tools_are_dangerous(self):
        """破坏性操作应标记为高危"""
        destructive_tools = [
            t for t in tool_registry._tools.values()
            if t.command_type == "destructive"
        ]
        for tool in destructive_tools:
            assert tool.category == ToolCategory.DANGEROUS, (
                f"破坏性工具 {tool.name} 应归类为 DANGEROUS"
            )
            assert tool.requires_confirmation is True

    def test_process_kill_is_dangerous(self):
        """进程终止应为高危操作"""
        kill_tool = tool_registry._tools.get("process:kill")
        assert kill_tool is not None
        assert kill_tool.category == ToolCategory.DANGEROUS
        assert kill_tool.requires_confirmation is True
        assert kill_tool.risk == "high"

    def test_disk_cleanup_is_dangerous(self):
        """磁盘清理应为高危操作"""
        cleanup_tool = tool_registry._tools.get("disk:cleanup")
        assert cleanup_tool is not None
        assert cleanup_tool.category == ToolCategory.DANGEROUS
        assert cleanup_tool.requires_confirmation is True

    def test_temp_cleanup_is_dangerous(self):
        """临时文件清理应为高危操作"""
        cleanup_tool = tool_registry._tools.get("temp:cleanup")
        assert cleanup_tool is not None
        assert cleanup_tool.category == ToolCategory.DANGEROUS
        assert cleanup_tool.requires_confirmation is True

    def test_system_info_is_safe(self):
        """系统信息查询应为安全操作"""
        info_tool = tool_registry._tools.get("system:info")
        assert info_tool is not None
        assert info_tool.risk == "low"
        assert info_tool.requires_confirmation is False

    def test_process_list_is_safe(self):
        """进程列表查询应为安全操作"""
        list_tool = tool_registry._tools.get("process:list")
        assert list_tool is not None
        assert list_tool.risk == "low"

    def test_process_top_is_safe(self):
        """高占用进程查询应为安全操作"""
        top_tool = tool_registry._tools.get("process:top")
        assert top_tool is not None
        assert top_tool.risk == "low"


class TestToolSchemaValidation:
    """工具 Schema 参数校验"""

    def test_all_schema_tools_have_names(self):
        """所有 Schema 工具必须有名称"""
        for tool_def in TOOLS_SCHEMA:
            func = tool_def.get("function", {})
            assert "name" in func, f"工具缺少 name 字段: {tool_def}"
            assert func["name"], f"工具 name 不能为空"

    def test_all_schema_tools_have_descriptions(self):
        """所有 Schema 工具必须有描述"""
        for tool_def in TOOLS_SCHEMA:
            func = tool_def.get("function", {})
            assert "description" in func, f"工具 {func.get('name')} 缺少 description"
            assert len(func["description"]) > 5

    def test_all_schema_tools_have_parameters(self):
        """所有 Schema 工具必须有参数定义"""
        for tool_def in TOOLS_SCHEMA:
            func = tool_def.get("function", {})
            assert "parameters" in func, f"工具 {func.get('name')} 缺少 parameters"

    def test_required_params_have_types(self):
        """必要参数必须有类型定义"""
        for tool_def in TOOLS_SCHEMA:
            func = tool_def.get("function", {})
            params = func.get("parameters", {})
            required = params.get("required", [])
            properties = params.get("properties", {})
            for req_param in required:
                assert req_param in properties, (
                    f"工具 {func.get('name')} 的必要参数 {req_param} 未在 properties 中定义"
                )
                assert "type" in properties[req_param], (
                    f"工具 {func.get('name')} 参数 {req_param} 缺少 type 定义"
                )

    def test_dangerous_schema_tools_have_enum_restriction(self):
        """高危 Schema 工具的 action 参数应有 enum 限制"""
        system_control = None
        for tool_def in TOOLS_SCHEMA:
            if tool_def.get("function", {}).get("name") == "systemControl":
                system_control = tool_def
                break

        if system_control:
            action_prop = (
                system_control["function"]["parameters"]
                .get("properties", {})
                .get("action", {})
            )
            assert "enum" in action_prop, "systemControl action 应有 enum 限制"
            assert "shutdown" in action_prop["enum"]
            assert "sleep" in action_prop["enum"]

    def test_process_kill_schema_has_pid_or_name(self):
        """进程终止 Schema 应支持 pid 或 name 参数"""
        kill_schema = None
        for tool_def in TOOLS_SCHEMA:
            if tool_def.get("function", {}).get("name") == "process:kill":
                kill_schema = tool_def
                break

        if kill_schema:
            props = kill_schema["function"]["parameters"].get("properties", {})
            assert "pid" in props or "name" in props, "process:kill 应支持 pid 或 name 参数"


class TestToolRegistryCoverage:
    """工具注册覆盖率"""

    def test_registry_has_minimum_tools(self):
        """注册工具数量应达到最低要求"""
        assert len(tool_registry._tools) >= 10, (
            f"注册工具仅 {len(tool_registry._tools)} 个，应至少 10 个"
        )

    def test_all_categories_covered(self):
        """应覆盖所有工具分类"""
        categories = {t.category for t in tool_registry._tools.values()}
        assert ToolCategory.SYSTEM in categories
        assert ToolCategory.FILE in categories
        assert ToolCategory.PROCESS in categories
        assert ToolCategory.DANGEROUS in categories

    def test_dangerous_confirmation_coverage(self):
        """高危工具确认覆盖率应为 100%"""
        dangerous = [
            t for t in tool_registry._tools.values()
            if t.category == ToolCategory.DANGEROUS
        ]
        confirmed = [t for t in dangerous if t.requires_confirmation]
        coverage = len(confirmed) / len(dangerous) * 100 if dangerous else 100

        print(f"\n[安全管控] 高危工具 {len(dangerous)} 个, 确认覆盖 {len(confirmed)} 个, 覆盖率 {coverage:.0f}%")
        assert coverage == 100, f"高危工具确认覆盖率 {coverage:.0f}% 未达 100%"

    def test_tool_examples_exist(self):
        """推荐工具应有使用示例"""
        recommended = [
            t for t in tool_registry._tools.values()
            if t.recommended
        ]
        for tool in recommended:
            assert len(tool.examples) > 0, f"推荐工具 {tool.name} 应有使用示例"


class TestToolCategoryConsistency:
    """工具分类一致性"""

    def test_network_tools_category(self):
        network_tools = [
            t for t in tool_registry._tools.values()
            if t.category == ToolCategory.NETWORK
        ]
        for tool in network_tools:
            assert tool.name.startswith(("network:", "browser:")), (
                f"网络工具 {tool.name} 命名应以 network: 或 browser: 开头"
            )

    def test_process_tools_category(self):
        process_tools = [
            t for t in tool_registry._tools.values()
            if t.category == ToolCategory.PROCESS
        ]
        for tool in process_tools:
            assert tool.name.startswith("process:"), (
                f"进程工具 {tool.name} 命名应以 process: 开头"
            )

    def test_file_tools_category(self):
        file_tools = [
            t for t in tool_registry._tools.values()
            if t.category == ToolCategory.FILE
        ]
        for tool in file_tools:
            assert tool.name.startswith(("file:", "temp:")), (
                f"文件工具 {tool.name} 命名应以 file: 或 temp: 开头"
            )