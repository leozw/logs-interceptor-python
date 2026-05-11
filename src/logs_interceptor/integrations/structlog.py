from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..domain.interfaces import ILogger
from ..infrastructure.internal_capture_guard import is_internal_log_capture_suppressed
from ..infrastructure.log_noise_filter import (
    normalize_excluded_logger_prefixes,
    should_drop_log_record,
)


class StructlogProcessor:
    def __init__(self, logger: ILogger, exclude_prefixes: list[str] | None = None) -> None:
        self.logger = logger
        self._exclude_prefixes = normalize_excluded_logger_prefixes(exclude_prefixes)

    def __call__(self, _logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        if is_internal_log_capture_suppressed():
            return event_dict
        if should_drop_log_record(
            logger_name=event_dict.get("logger_name"),
            module_name=event_dict.get("module"),
            extra=event_dict.get("extra") if isinstance(event_dict.get("extra"), Mapping) else None,
            exclude_prefixes=self._exclude_prefixes,
        ):
            return event_dict

        message = str(event_dict.get("event", method_name))
        level = method_name.lower()
        if level not in {"debug", "info", "warn", "error", "fatal"}:
            level = "info"

        context = dict(event_dict)
        context.pop("event", None)
        self.logger.log(level, message, {"source": "structlog", **context})  # type: ignore[arg-type]
        return event_dict
