from __future__ import annotations

import builtins
import logging
import sys
import traceback as traceback_module
from types import TracebackType
from typing import Any

from ...domain.interfaces import ILogger
from ...types import LogLevel
from ...utils import safe_stringify


class _BridgeLoggingHandler(logging.Handler):
    def __init__(self, logger: ILogger) -> None:
        super().__init__()
        self._logger = logger

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = self._map_level(record.levelno)
            msg = record.getMessage()
            context = {
                "source": "logging",
                "logger_name": record.name,
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            }
            if record.exc_info:
                context["exc_info"] = "".join(traceback_module.format_exception(*record.exc_info))
            self._logger.log(level, msg, context)
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


class RuntimeInterceptor:
    def __init__(self, logger: ILogger, preserve_original: bool = True) -> None:
        self._logger = logger
        self._preserve_original = preserve_original
        self._enabled = False

        self._original_print = builtins.print
        self._original_excepthook = sys.excepthook
        self._root_logger = logging.getLogger()
        self._bridge_handler = _BridgeLoggingHandler(logger)
        self._original_handlers: list[logging.Handler] = []

    def enable(self) -> None:
        if self._enabled:
            return
        self._enabled = True

        self._patch_print()
        self._patch_excepthook()
        self._patch_logging()

    def restore(self) -> None:
        if not self._enabled:
            return

        builtins.print = self._original_print
        sys.excepthook = self._original_excepthook

        try:
            self._root_logger.removeHandler(self._bridge_handler)
        except ValueError:
            pass

        if not self._preserve_original:
            self._root_logger.handlers = self._original_handlers

        self._enabled = False

    def is_enabled(self) -> bool:
        return self._enabled

    def _patch_print(self) -> None:
        def intercepted_print(*args: Any, **kwargs: Any) -> None:
            try:
                message = " ".join(
                    [arg if isinstance(arg, str) else safe_stringify(arg) for arg in args]
                )
                self._logger.info(message, {"source": "print"})
            except Exception:
                pass

            if self._preserve_original:
                self._original_print(*args, **kwargs)

        builtins.print = intercepted_print

    def _patch_excepthook(self) -> None:
        def intercepted_excepthook(
            exc_type: type[BaseException],
            exc_value: BaseException,
            traceback: TracebackType | None,
        ) -> None:
            try:
                self._logger.fatal(
                    f"Uncaught exception: {exc_value}",
                    {
                        "source": "sys.excepthook",
                        "exception_type": exc_type.__name__,
                        "traceback": "".join(traceback_module.format_tb(traceback))
                        if traceback
                        else None,
                    },
                )
                self._logger.flush()
            except Exception:
                pass

            if self._preserve_original and self._original_excepthook is not None:
                self._original_excepthook(exc_type, exc_value, traceback)

        sys.excepthook = intercepted_excepthook

    def _patch_logging(self) -> None:
        if not self._preserve_original:
            self._original_handlers = list(self._root_logger.handlers)
            self._root_logger.handlers = []

        self._bridge_handler.setLevel(logging.DEBUG)
        self._root_logger.addHandler(self._bridge_handler)
        self._root_logger.setLevel(min(self._root_logger.level, logging.DEBUG) or logging.DEBUG)
