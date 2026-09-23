"""
迁移脚本：将老版本内存信号迁移到磁盘 JSON 文件。

老版本 SelfGoverningMemoryStore 的 _signals 是内存 dict，
进程重启后信号全部丢失。新版本已改为磁盘持久化。

此脚本用于：
1. 从老版本 checkpoint 或内存快照中提取信号
2. 写入新版本的 {store_dir}/signals/signals.json

用法：
  python -m app.services.graph.migrate_signals --source <legacy_json_file> --target-dir <store_dir>

示例：
  python -m app.services.graph.migrate_signals --source ./legacy_signals_backup.json --target-dir ./memory_store
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Any

logger = logging.getLogger(__name__)


def migrate_signals(
    source_file: str,
    target_dir: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not os.path.exists(source_file):
        logger.error(f"源文件不存在: {source_file}")
        return {"status": "error", "reason": "source_not_found"}

    with open(source_file, "r", encoding="utf-8") as f:
        legacy_signals = json.load(f)

    if not isinstance(legacy_signals, dict):
        logger.error(f"源文件格式错误：期望dict，得到{type(legacy_signals).__name__}")
        return {"status": "error", "reason": "invalid_format"}

    signal_dir = os.path.join(target_dir, "signals")
    signal_file = os.path.join(signal_dir, "signals.json")

    existing_signals: dict[str, dict[str, Any]] = {}
    if os.path.exists(signal_file):
        with open(signal_file, "r", encoding="utf-8") as f:
            existing_signals = json.load(f)

    merged = dict(existing_signals)
    added = 0
    skipped = 0
    for sig_id, sig_data in legacy_signals.items():
        if sig_id in merged:
            skipped += 1
            logger.debug(f"跳过已存在信号: {sig_id}")
            continue
        if "signal_id" not in sig_data:
            sig_data["signal_id"] = sig_id
        if "status" not in sig_data:
            sig_data["status"] = "open"
        if "timestamp" not in sig_data:
            sig_data["timestamp"] = time.time()
        merged[sig_id] = sig_data
        added += 1

    if dry_run:
        logger.info(f"[DRY RUN] 将新增 {added} 条信号，跳过 {skipped} 条已存在信号")
        return {"status": "dry_run", "added": added, "skipped": skipped, "total": len(merged)}

    os.makedirs(signal_dir, exist_ok=True)
    with open(signal_file, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"迁移完成：新增 {added} 条，跳过 {skipped} 条，总计 {len(merged)} 条信号")
    return {"status": "ok", "added": added, "skipped": skipped, "total": len(merged), "output": signal_file}


def main():
    parser = argparse.ArgumentParser(description="迁移老版本内存信号到磁盘JSON文件")
    parser.add_argument("--source", required=True, help="老版本信号JSON文件路径")
    parser.add_argument("--target-dir", default="./memory_store", help="目标存储目录")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    result = migrate_signals(args.source, args.target_dir, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status") == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()