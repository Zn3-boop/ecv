from __future__ import annotations

from typing import Any


def _top_processes(system_context: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    processes = system_context.get("processes", {}) if isinstance(system_context, dict) else {}
    top_items = processes.get("topProcesses", []) if isinstance(processes, dict) else []
    return top_items[:limit] if isinstance(top_items, list) else []


def summarize_system_context(system_context: dict[str, Any] | None) -> str:
    if not system_context:
        return "当前未提供实时系统监控上下文。"

    cpu = system_context.get("cpu", {})
    memory = system_context.get("memory", {})
    disk = system_context.get("disk", {})
    network = system_context.get("network", {})
    alerts = system_context.get("alerts", [])

    top_processes = _top_processes(system_context)
    process_summary = "、".join(
        f"{item.get('name', 'unknown')}({item.get('cpu', 0)}% CPU, {item.get('memoryLabel', '0 B')})"
        for item in top_processes
    ) or "暂无"

    disk_items = disk.get("disks", []) if isinstance(disk, dict) else []
    hottest_disk = disk_items[0] if disk_items else {}
    hottest_disk_text = (
        f"{hottest_disk.get('fs', 'unknown')} 已用 {hottest_disk.get('usePercent', 0)}%，剩余 {hottest_disk.get('availableLabel', 'unknown')}"
        if hottest_disk
        else "暂无磁盘数据"
    )

    alert_summary = "；".join(
        f"{item.get('level', 'info')} / {item.get('type', 'unknown')} / {item.get('message', '')}"
        for item in alerts[:5]
    ) or "当前无阈值告警"

    cpu_usage = float(cpu.get('usagePercent', 0) or 0)
    memory_usage = float(memory.get('usagePercent', 0) or 0)
    risk_level = 'critical' if cpu_usage >= 90 or memory_usage >= 90 or len(alerts) >= 2 else 'warning' if cpu_usage >= 75 or memory_usage >= 80 or alerts else 'normal'

    return (
        f"系统风险等级：{risk_level}；"
        f"CPU 使用率 {cpu.get('usagePercent', 'unknown')}%，{cpu.get('cores', 'unknown')} 核；"
        f"内存使用率 {memory.get('usagePercent', 'unknown')}%，已用 {memory.get('usedLabel', 'unknown')} / {memory.get('totalLabel', 'unknown')}；"
        f"磁盘概览：{hottest_disk_text}；"
        f"网络默认接口 {network.get('defaultInterface', 'unknown')}；"
        f"Top 进程：{process_summary}；"
        f"告警：{alert_summary}。"
    )


def summarize_voice_context(voice_context: dict[str, Any] | None) -> str:
    if not voice_context:
        return "当前未提供额外语音上下文。"

    locale = voice_context.get("locale", "zh-CN")
    source = voice_context.get("source", "text-simulated")
    device = voice_context.get("device", "desktop")
    return f"语音来源：{source}；语言：{locale}；设备：{device}。"
