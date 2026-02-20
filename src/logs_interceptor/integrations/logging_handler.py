from __future__ import annotations

import logging
import traceback as traceback_module
from typing import Any

from ..domain.interfaces import ILogger
from ..types import LogLevel


class LoggingHandler(logging.Handler):
    def __init__(self, logger: ILogger) -> None:
        super().__init__()
        self._logger = logger

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = self._map_level(record.levelno)
            message = record.getMessage()
            context: dict[str, Any] = {
                "source": "python-logging",
                "logger_name": record.name,
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            }
            if record.exc_info:
                context["exception"] = "".join(traceback_module.format_exception(*record.exc_info))
            self._logger.log(level, message, context)
        except Exception:
            return

    @staticmethod
    def _map_level(level_no: int) -> LogLevel:
        if level_no >= logging.CRITICAL:
            return "fatal"
        if level_no >= logging.ERROR:
            return "error"
        if level_no >= logging.WARNING:
            return "warn"
        if level_no >= logging.INFO:
            return "info"
        return "debug"
