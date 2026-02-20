from __future__ import annotations

import re

from ...config import ResolvedFilterConfig
from ...domain.entities import LogEntryEntity
from ...types import LogLevel
from ...utils import detect_sensitive_data, sanitize_data, should_sample


class LogFilter:
    def __init__(self, config: ResolvedFilterConfig) -> None:
        self._config = config
        self._patterns = [re.compile(pattern) for pattern in config.patterns]

    def should_process(self, entry: LogEntryEntity) -> bool:
        if not self.is_level_enabled(entry.level):
            return False

        if self._patterns:
            if not any(pattern.search(entry.message) for pattern in self._patterns):
                return False

        if not should_sample(self._config.sampling_rate):
            return False

        return True

    def filter(self, entry: LogEntryEntity) -> LogEntryEntity:
        message = entry.message
        if len(message) > self._config.max_message_length:
            message = message[: self._config.max_message_length] + "...[truncated]"

        context = entry.context
        if self._config.sanitize and context is not None:
            context = sanitize_data(context, self._config.sensitive_patterns)

        if self._config.sanitize and detect_sensitive_data(message, self._config.sensitive_patterns):
            message = "[REDACTED]"

        return LogEntryEntity(
            id=entry.id,
            timestamp=entry.timestamp,
            level=entry.level,
            message=message,
            context=context,
            trace_id=entry.trace_id,
            span_id=entry.span_id,
            request_id=entry.request_id,
            labels=entry.labels,
            metadata=entry.metadata,
        )

    def is_level_enabled(self, level: LogLevel) -> bool:
        return level in self._config.levels
