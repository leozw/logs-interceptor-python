from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..domain.interfaces import ILogger
from ..infrastructure.internal_capture_guard import is_internal_log_capture_suppressed
from ..infrastructure.log_noise_filter import (
    normalize_excluded_logger_prefixes,
    should_drop_log_record,
)


class LoguruSink:
    def __init__(self, logger: ILogger, exclude_prefixes: list[str] | None = None) -> None:
        self.logger = logger
        self._exclude_prefixes = normalize_excluded_logger_prefixes(exclude_prefixes)

    def __call__(self, message: Any) -> None:
        try:
            if is_internal_log_capture_suppressed():
                return
            record = getattr(message, "record", None)
            if not isinstance(record, Mapping):
                self.logger.info(str(message), {"source": "loguru"})
                return

            if self._should_ignore(record):
                return

            level = self._resolve_level(record)
            extra = record.get("extra")
            normalized_extra = dict(extra) if isinstance(extra, Mapping) else extra

            self.logger.log(
                level,  # type: ignore[arg-type]
                str(record.get("message", "")),
                {
                    "source": "loguru",
                    "logger_name": record.get("name"),
                    "module": record.get("module"),
                    "function": record.get("function"),
                    "line": record.get("line"),
                    "extra": normalized_extra,
                },
            )
        except Exception:
            return

    @staticmethod
    def _resolve_level(record: Mapping[str, Any]) -> str:
        raw_level = record.get("level")
        if isinstance(raw_level, Mapping):
            level = str(raw_level.get("name", "INFO")).lower()
            level_number = raw_level.get("no")
        else:
            level = str(getattr(raw_level, "name", "INFO")).lower()
            level_number = getattr(raw_level, "no", None)

        if level == "warning":
            return "warn"
        if level == "critical":
            return "fatal"
        if level not in {"debug", "info", "warn", "error", "fatal"}:
            if not level and isinstance(level_number, (int, float)):
                if level_number >= 50:
                    return "fatal"
                if level_number >= 40:
                    return "error"
                if level_number >= 30:
                    return "warn"
                if level_number >= 20:
                    return "info"
                return "debug"
            return "info"
        return level

    def _should_ignore(self, record: Mapping[str, Any]) -> bool:
        extra = record.get("extra")
        return should_drop_log_record(
            logger_name=str(record.get("name") or ""),
            module_name=str(record.get("module") or ""),
            extra=extra if isinstance(extra, Mapping) else None,
            exclude_prefixes=self._exclude_prefixes,
        )
