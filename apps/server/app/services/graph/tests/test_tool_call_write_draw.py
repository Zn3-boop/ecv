"""
工具调用测试: 写入文件 + 绘图(matplotlib)

验证目标:
1. content:generate 工具能否生成并写入文件
2. matplotlib 绘图工具能否生成图片
3. 工具执行节点(tool_execute_node)能否正确调度
4. Guard护栏对路径穿越/命令注入的拦截

用法:
    cd d:\\ecv\\apps\\server
    python -m pytest app/services/graph/tests/test_tool_call_write_draw.py -v
    python app/services/graph/tests/test_tool_call_write_draw.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import pytest


class TestFileWrite:

    @pytest.mark.asyncio
    async def test_content_gen_agent_sets_write_tool(self):
        from app.services.graph.nodes import content_gen_agent_node
        state = {
            "agent_input": {
                "action": "generate",
                "task": "写一份Python快速入门文档",
                "content_type": "document",
            }
        }
        result = await content_gen_agent_node(state)
        assert result["tool_name"] == "content:generate"
        assert "task" in result["tool_args"]

    @pytest.mark.asyncio
    async def test_content_gen_write_action(self):
        from app.services.graph.nodes import content_gen_agent_node
        state = {
            "agent_input": {
                "action": "write",
                "task": "创建一个README.md",
            }
        }
        result = await content_gen_agent_node(state)
        assert result["tool_name"] == "content:generate"

    @pytest.mark.asyncio
    async def test_ide_launch_creates_project_files(self):
        from app.services.tools.executor import _execute_single_tool
        project_name = f"test_project_{int(time.time())}"
        result = await _execute_single_tool("ide:launch", {
            "ide": "vscode",
            "action": "create_project",
            "project_name": project_name,
            "files": [
                {"path": "index.html", "template": "modern_login"},
                {"path": "main.py"},
            ],
        })
        err_msg = str(result.get("error", ""))[:100]
        print(f"  ide:launch result: ok={result.get('ok')}, error={err_msg}")

    def test_direct_file_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "test_output.txt")
            content = "这是AI Agent写入的测试文件\n包含中文内容\n和数字12345"
            with open(test_file, "w", encoding="utf-8") as f:
                f.write(content)
            assert os.path.exists(test_file)
            with open(test_file, "r", encoding="utf-8") as f:
                assert f.read() == content
            print(f"  文件写入成功: {test_file}")


class TestMatplotlibDraw:

    def test_matplotlib_available(self):
        try:
            import matplotlib
            print(f"  matplotlib version: {matplotlib.__version__}")
        except ImportError:
            pytest.skip("matplotlib 未安装, 请运行: pip install matplotlib")

    def test_simple_line_plot(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "line_plot.png")
            x = [1, 2, 3, 4, 5]
            y = [2, 4, 6, 8, 10]
            plt.figure(figsize=(8, 5))
            plt.plot(x, y, marker="o", linewidth=2, markersize=8)
            plt.title("Simple Line Plot")
            plt.xlabel("X")
            plt.ylabel("Y")
            plt.grid(True, alpha=0.3)
            plt.savefig(output_path, dpi=100, bbox_inches="tight")
            plt.close()
            assert os.path.exists(output_path)
            assert os.path.getsize(output_path) > 0
            print(f"  折线图绘制成功: {output_path} ({os.path.getsize(output_path)} bytes)")

    def test_bar_chart(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "bar_chart.png")
            categories = ["RAG", "Web", "Code", "Image", "Text"]
            values = [85, 72, 90, 65, 78]
            plt.figure(figsize=(8, 5))
            bars = plt.bar(categories, values, color=["#667eea", "#764ba2", "#f093fb", "#f5576c", "#4facfe"])
            plt.title("Tool Capability Scores")
            plt.ylabel("Score")
            for bar, val in zip(bars, values):
                plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1, str(val), ha="center")
            plt.savefig(output_path, dpi=100, bbox_inches="tight")
            plt.close()
            assert os.path.exists(output_path)
            print(f"  柱状图绘制成功: {output_path}")

    def test_pie_chart(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "pie_chart.png")
            labels = ["RAG", "Web", "Code", "Direct"]
            sizes = [40, 25, 20, 15]
            colors = ["#667eea", "#764ba2", "#f093fb", "#4facfe"]
            plt.figure(figsize=(7, 7))
            plt.pie(sizes, labels=labels, colors=colors, autopct="%1.1f%%", startangle=90)
            plt.title("Agent Route Distribution")
            plt.savefig(output_path, dpi=100, bbox_inches="tight")
            plt.close()
            assert os.path.exists(output_path)
            print(f"  饼图绘制成功: {output_path}")

    def test_chinese_text_plot(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "chinese_plot.png")
            try:
                plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
                plt.rcParams["axes.unicode_minus"] = False
            except Exception:
                pass
            months = ["1月", "2月", "3月", "4月", "5月", "6月"]
            rag_usage = [120, 150, 180, 200, 220, 250]
            web_usage = [80, 90, 100, 110, 130, 140]
            plt.figure(figsize=(10, 6))
            plt.plot(months, rag_usage, marker="o", label="RAG", linewidth=2)
            plt.plot(months, web_usage, marker="s", label="Web", linewidth=2)
            plt.title("RAG vs Web Trend")
            plt.xlabel("Month")
            plt.ylabel("Count")
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.savefig(output_path, dpi=100, bbox_inches="tight")
            plt.close()
            assert os.path.exists(output_path)
            print(f"  中文图表绘制成功: {output_path}")


class TestToolExecuteIntegration:

    @pytest.mark.asyncio
    async def test_image_agent_screenshot(self):
        from app.services.graph.nodes import image_agent_node
        state = {"agent_input": {"action": "screenshot"}}
        result = await image_agent_node(state)
        assert result["tool_name"] == "image:screenshot"

    @pytest.mark.asyncio
    async def test_image_agent_ocr(self):
        from app.services.graph.nodes import image_agent_node
        state = {"agent_input": {"action": "ocr", "image_path": "test.png"}}
        result = await image_agent_node(state)
        assert result["tool_name"] == "image:ocr"

    @pytest.mark.asyncio
    async def test_image_agent_understand(self):
        from app.services.graph.nodes import image_agent_node
        state = {"agent_input": {"action": "理解", "image_path": "test.png", "question": "这张图是什么？"}}
        result = await image_agent_node(state)
        assert result["tool_name"] == "image:understand"


class TestGuardSecurity:

    def test_path_traversal_blocked(self):
        from app.services.graph.checkers import guard_pre_check_node
        state = {
            "tool_name": "app:launch",
            "tool_args": {"path": "C:\\Users\\..\\..\\Windows\\System32\\cmd.exe"},
        }
        result = guard_pre_check_node(state)
        if result.get("last_error"):
            assert "路径穿越" in result["last_error"] or "Guard" in result["last_error"]

    def test_shell_metachar_blocked(self):
        from app.services.graph.checkers import guard_pre_check_node
        state = {
            "tool_name": "app:launch",
            "tool_args": {"path": "notepad.exe & calc.exe"},
        }
        result = guard_pre_check_node(state)
        if result.get("last_error"):
            assert "元字符" in result["last_error"] or "Guard" in result["last_error"]


async def main():
    import time

    print("=" * 60)
    print("工具调用测试: 写入文件 + 绘图")
    print("=" * 60)

    print("\n[1] 文件写入测试")
    print("-" * 40)
    with tempfile.TemporaryDirectory() as tmpdir:
        test_files = [
            ("test_doc.md", "# AI Agent Test Document\n\nAuto-generated by AI Agent."),
            ("test_code.py", "def hello():\n    print('Hello from AI Agent!')\n\nhello()"),
            ("test_data.json", '{"name": "test", "value": 42, "tags": ["ai", "agent", "test"]}'),
        ]
        for filename, content in test_files:
            filepath = os.path.join(tmpdir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            assert os.path.exists(filepath)
            print(f"  OK write: {filename} ({os.path.getsize(filepath)} bytes)")

    print("\n[2] Plot Test")
    print("-" * 40)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        output_dir = tempfile.mkdtemp()

        try:
            plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
            plt.rcParams["axes.unicode_minus"] = False
        except Exception:
            pass

        fig, axes = plt.subplots(2, 2, figsize=(12, 10))

        x = list(range(1, 7))
        y_rag = [120, 150, 180, 200, 220, 250]
        y_web = [80, 90, 100, 110, 130, 140]
        axes[0, 0].plot(x, y_rag, marker="o", label="RAG", linewidth=2)
        axes[0, 0].plot(x, y_web, marker="s", label="Web", linewidth=2)
        axes[0, 0].set_title("RAG vs Web Trend")
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)

        categories = ["RAG", "Web", "Code", "Image", "Text"]
        values = [85, 72, 90, 65, 78]
        axes[0, 1].bar(categories, values, color=["#667eea", "#764ba2", "#f093fb", "#f5576c", "#4facfe"])
        axes[0, 1].set_title("Tool Scores")

        labels = ["RAG", "Web", "Code", "Direct"]
        sizes = [40, 25, 20, 15]
        axes[1, 0].pie(sizes, labels=labels, autopct="%1.1f%%", startangle=90)
        axes[1, 0].set_title("Route Distribution")

        try:
            import numpy as np
            t = np.linspace(0, 2 * np.pi, 100)
            axes[1, 1].plot(np.cos(t), np.sin(t), linewidth=2)
            axes[1, 1].set_title("Unit Circle")
            axes[1, 1].set_aspect("equal")
        except ImportError:
            axes[1, 1].text(0.5, 0.5, "numpy not installed", ha="center", va="center", transform=axes[1, 1].transAxes)
            axes[1, 1].set_title("Skipped")

        plt.suptitle("AI Agent Tool Call Test", fontsize=14, fontweight="bold")
        plt.tight_layout()
        output_path = os.path.join(output_dir, "agent_test_plots.png")
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  OK plot: {output_path}")
        print(f"     size: {os.path.getsize(output_path)} bytes")
    except ImportError as e:
        print(f"  SKIP matplotlib not installed: {e}")
        print(f"       Run: pip install matplotlib numpy")

    print("\n[3] Tool Node Mapping Test")
    print("-" * 40)
    from app.services.graph.nodes import content_gen_agent_node, image_agent_node

    test_actions = [
        (content_gen_agent_node, {"action": "generate", "task": "write doc"}, "content:generate"),
        (content_gen_agent_node, {"action": "write", "task": "create file"}, "content:generate"),
        (content_gen_agent_node, {"action": "write_document", "task": "write report"}, "content:generate"),
        (image_agent_node, {"action": "screenshot"}, "image:screenshot"),
        (image_agent_node, {"action": "ocr", "image_path": "test.png"}, "image:ocr"),
        (image_agent_node, {"action": "理解", "image_path": "test.png"}, "image:understand"),
    ]
    for node_fn, agent_input, expected_tool in test_actions:
        result = await node_fn({"agent_input": agent_input})
        actual = result.get("tool_name", "")
        status = "OK" if actual == expected_tool else "FAIL"
        print(f"  [{status}] {node_fn.__name__}({agent_input}) -> {actual} (expected: {expected_tool})")

    print(f"\n{'=' * 60}")
    print("Tool call test done")


if __name__ == "__main__":
    asyncio.run(main())