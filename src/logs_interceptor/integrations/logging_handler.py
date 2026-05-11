from __future__ import annotations

import logging
import traceback as traceback_module
from typing import Any

from ..domain.interfaces import ILogger
from ..infrastructure.internal_capture_guard import is_internal_log_capture_suppressed
from ..infrastructure.log_noise_filter import (
    normalize_excluded_logger_prefixes,
    should_drop_log_record,
)
from ..infrastructure.log_record_extra import extract_log_record_extra
from ..types import LogLevel


class LoggingHandler(logging.Handler):
    def __init__(self, logger: ILogger, exclude_prefixes: list[str] | None = None) -> None:
        super().__init__()
        self._logger = logger
        self._exclude_prefixes = normalize_excluded_logger_prefixes(exclude_prefixes)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if is_internal_log_capture_suppressed():
                return
            if should_drop_log_record(
                logger_name=record.name,
                module_name=record.module,
                exclude_prefixes=self._exclude_prefixes,
            ):
                return
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
            extra = extract_log_record_extra(record)
            if extra is not None:
                context["extra"] = extra
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
