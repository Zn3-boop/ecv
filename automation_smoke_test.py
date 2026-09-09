import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SERVER_APP_DIR = os.path.join(ROOT, "apps", "server")
if SERVER_APP_DIR not in sys.path:
    sys.path.insert(0, SERVER_APP_DIR)

from app.api.automation import parse_commands_from_suggestion, parse_user_command  # noqa: E402


def summarize_commands(commands) -> list[str]:
    return [
        f"{item.tool}|confirm={item.require_confirmation}|risk={item.risk}|params={item.params}"
        for item in commands
    ]


def assert_no_kill_for_investigation() -> None:
    system_context = {
        "memory": {"usagePercent": 95},
        "processes": {
            "topProcesses": [
                {"pid": 3210, "name": "chrome.exe", "cpu": 42, "memory": 2048},
                {"pid": 6543, "name": "Code.exe", "cpu": 18, "memory": 1024},
            ]
        },
        "disk": {"disks": [{"usePercent": 91}]},
        "temp_path": "D:\\ecv",
    }
    suggestion = (
        "结论：当前内存使用率约 95%，需要先定位高占用进程，而不是只做提示。\n"
        "建议动作：已自动补充进程排查步骤，优先检查 chrome.exe(42% CPU)、Code.exe(18% CPU)。\n"
        "下一步：先查看进程列表，再由你确认是否结束异常进程。"
    )

    commands = parse_commands_from_suggestion("memory", suggestion, system_context)
    kill_commands = [item for item in commands if item.tool == "process:kill"]

    print("\n[CASE 1] 排查进程不应产生 kill")
    print("commands:", *summarize_commands(commands), sep="\n - ")

    assert not kill_commands, f"Expected no process:kill commands, got: {kill_commands}"


def assert_confirmation_flow_for_explicit_close_command() -> None:
    analysis, commands, reply_text = parse_user_command("结束 python.exe 进程")
    kill_commands = [item for item in commands if item.tool == "process:kill"]

    print("\n[CASE 2] 明确结束某进程时，不应直接自动 kill，而应先走确认链路")
    print("analysis:", analysis)
    print("reply_text:", reply_text)
    print("commands:", *summarize_commands(commands), sep="\n - ")

    assert not kill_commands, f"Direct command parsing should not auto-emit process:kill before confirmation: {kill_commands}"
    assert any(item.tool == "process:list" for item in commands), f"Expected process:list pre-check command, got: {commands}"


def assert_single_confirmed_kill_for_explicit_suggestion() -> None:
    system_context = {
        "cpu": {"usagePercent": 98},
        "processes": {
            "topProcesses": [
                {"pid": 4321, "name": "python.exe", "cpu": 88, "memory": 512},
                {"pid": 5678, "name": "node.exe", "cpu": 72, "memory": 768},
                {"pid": 4321, "name": "python.exe", "cpu": 88, "memory": 512},
            ]
        },
    }
    suggestion = (
        "结论：当前 CPU 使用率约 98%，需要先收集高占用进程信息。\n"
        "建议动作：优先分析 python.exe(88% CPU)、node.exe(72% CPU)。\n"
        "下一步：请结束 python.exe，其他进程先保留观察。"
    )

    commands = parse_commands_from_suggestion("cpu", suggestion, system_context)
    kill_commands = [item for item in commands if item.tool == "process:kill"]

    print("\n[CASE 3] 明确建议结束某进程时，最多一个 kill 且必须确认")
    print("commands:", *summarize_commands(commands), sep="\n - ")

    assert len(kill_commands) == 1, f"Expected exactly 1 process:kill command, got: {kill_commands}"
    kill_command = kill_commands[0]
    assert kill_command.params.get("pid") == 4321, f"Expected PID 4321, got: {kill_command.params}"
    assert kill_command.require_confirmation is True, f"Kill command must require confirmation: {kill_command}"


if __name__ == "__main__":
    assert_no_kill_for_investigation()
    assert_confirmation_flow_for_explicit_close_command()
    assert_single_confirmed_kill_for_explicit_suggestion()
    print("\nAll automation smoke tests passed.")