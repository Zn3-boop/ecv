"""
日志配置：RotatingFileHandler + 控制台输出 + JSON结构化格式（prod）。

环境变量：
  LOG_LEVEL         - 日志级别（默认 INFO）
  LOG_DIR           - 日志目录（默认 ./logs）
  LOG_MAX_BYTES     - 单文件最大字节数（默认 10MB）
  LOG_BACKUP_COUNT  - 保留轮转文件数（默认 5）
  LOG_FORMAT        - 输出格式 text | json（默认 text）
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_DIR = os.getenv("LOG_DIR", "./logs")
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))
LOG_FORMAT = os.getenv("LOG_FORMAT", "text")


def setup_logging() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    if root_logger.handlers:
        for h in root_logger.handlers[:]:
            root_logger.removeHandler(h)

    formatter: logging.Formatter
    if LOG_FORMAT == "json":
        formatter = _JsonFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        filename=os.path.join(LOG_DIR, "app.log"),
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    graph_handler = RotatingFileHandler(
        filename=os.path.join(LOG_DIR, "graph.log"),
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    graph_handler.setFormatter(formatter)
    graph_logger = logging.getLogger("app.services.graph")
    graph_logger.addHandler(graph_handler)

    llm_handler = RotatingFileHandler(
        filename=os.path.join(LOG_DIR, "llm.log"),
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    llm_handler.setFormatter(formatter)
    llm_logger = logging.getLogger("app.services.llm")
    llm_logger.addHandler(llm_handler)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        import json as _json
        from datetime import datetime

        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])
        return _json.dumps(log_entry, ensure_ascii=False)