"""
Context Builder 测试 - 验证系统上下文摘要、语音上下文摘要
"""
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parent.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.services.llm.context_builder import (
    summarize_system_context,
    summarize_voice_context,
)


class TestSystemContextSummary:
    """系统上下文摘要"""

    def test_none_context(self):
        result = summarize_system_context(None)
        assert "未提供" in result

    def test_empty_context(self):
        result = summarize_system_context({})
        assert isinstance(result, str)

    def test_full_context(self):
        ctx = {
            "cpu": {"usagePercent": 45, "cores": 8},
            "memory": {"usagePercent": 60, "usedLabel": "9.6 GB", "totalLabel": "16 GB"},
            "disk": {"disks": [{"fs": "C:", "usePercent": 70, "availableLabel": "50 GB"}]},
            "network": {"defaultInterface": "Ethernet"},
            "processes": {"topProcesses": [
                {"name": "chrome.exe", "cpu": 25, "memoryLabel": "1.2 GB"},
                {"name": "node.exe", "cpu": 15, "memoryLabel": "800 MB"},
            ]},
            "alerts": [],
        }
        result = summarize_system_context(ctx)
        assert "45" in result
        assert "8" in result
        assert "60" in result
        assert "chrome.exe" in result
        assert "normal" in result

    def test_critical_risk_level(self):
        ctx = {
            "cpu": {"usagePercent": 95},
            "memory": {"usagePercent": 50},
            "disk": {"disks": []},
            "network": {},
            "alerts": [],
        }
        result = summarize_system_context(ctx)
        assert "critical" in result

    def test_warning_risk_level(self):
        ctx = {
            "cpu": {"usagePercent": 80},
            "memory": {"usagePercent": 50},
            "disk": {"disks": []},
            "network": {},
            "alerts": [],
        }
        result = summarize_system_context(ctx)
        assert "warning" in result

    def test_alerts_included(self):
        ctx = {
            "cpu": {"usagePercent": 50},
            "memory": {"usagePercent": 50},
            "disk": {"disks": []},
            "network": {},
            "alerts": [
                {"level": "warning", "type": "cpu", "message": "CPU过高"},
            ],
        }
        result = summarize_system_context(ctx)
        assert "CPU过高" in result

    def test_top_processes_limited(self):
        ctx = {
            "cpu": {"usagePercent": 50},
            "memory": {"usagePercent": 50},
            "disk": {"disks": []},
            "network": {},
            "processes": {"topProcesses": [
                {"name": f"p{i}.exe", "cpu": i, "memoryLabel": f"{i}MB"}
                for i in range(10)
            ]},
            "alerts": [],
        }
        result = summarize_system_context(ctx)
        assert "p0.exe" in result
        assert "p2.exe" in result


class TestVoiceContextSummary:
    """语音上下文摘要"""

    def test_none_context(self):
        result = summarize_voice_context(None)
        assert "未提供" in result

    def test_empty_context(self):
        result = summarize_voice_context({})
        assert isinstance(result, str)

    def test_full_context(self):
        ctx = {
            "locale": "zh-CN",
            "source": "microphone",
            "device": "desktop",
        }
        result = summarize_voice_context(ctx)
        assert "microphone" in result
        assert "zh-CN" in result
        assert "desktop" in result