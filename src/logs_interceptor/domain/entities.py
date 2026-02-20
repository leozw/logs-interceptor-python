from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..types import LogEntry, LogLevel


@dataclass(slots=True)
class LogEntryEntity:
    id: str
    timestamp: str
    level: LogLevel
    message: str
    context: dict[str, Any] | None = None
    trace_id: str | None = None
    span_id: str | None = None
    request_id: str | None = None
    labels: dict[str, str] | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> LogEntry:
        payload: LogEntry = {
            "id": self.id,
            "timestamp": self.timestamp,
            "level": self.level,
            "message": self.message,
        }
        if self.context is not None:
            payload["context"] = self.context
        if self.trace_id:
            payload["trace_id"] = self.trace_id
        if self.span_id:
            payload["span_id"] = self.span_id
        if self.request_id:
            payload["request_id"] = self.request_id
        if self.labels:
            payload["labels"] = self.labels
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload
