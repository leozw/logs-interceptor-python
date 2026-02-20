from __future__ import annotations

from typing import Any

from ..domain.interfaces import ILogger


class LoguruSink:
    def __init__(self, logger: ILogger) -> None:
        self.logger = logger

    def __call__(self, message: Any) -> None:
        record = getattr(message, "record", None)
        if record is None:
            self.logger.info(str(message), {"source": "loguru"})
            return

        level = str(record.get("level", {}).get("name", "INFO")).lower()
        if level == "warning":
            level = "warn"
        if level == "critical":
            level = "fatal"
        if level not in {"debug", "info", "warn", "error", "fatal"}:
            level = "info"

        self.logger.log(
            level,  # type: ignore[arg-type]
            str(record.get("message", "")),
            {
                "source": "loguru",
                "module": record.get("module"),
                "function": record.get("function"),
                "line": record.get("line"),
                "extra": record.get("extra"),
            },
        )
