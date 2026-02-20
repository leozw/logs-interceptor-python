from __future__ import annotations

from typing import Any

from ..domain.interfaces import ILogger


class StructlogProcessor:
    def __init__(self, logger: ILogger) -> None:
        self.logger = logger

    def __call__(self, _logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        message = str(event_dict.get("event", method_name))
        level = method_name.lower()
        if level not in {"debug", "info", "warn", "error", "fatal"}:
            level = "info"

        context = dict(event_dict)
        context.pop("event", None)
        self.logger.log(level, message, {"source": "structlog", **context})  # type: ignore[arg-type]
        return event_dict
