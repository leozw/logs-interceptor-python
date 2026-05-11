from __future__ import annotations

import logging
from typing import Any

_STANDARD_LOG_RECORD_ATTRIBUTES = frozenset(logging.makeLogRecord({}).__dict__) | {
    "asctime",
    "message",
}


def extract_log_record_extra(record: logging.LogRecord) -> dict[str, Any] | None:
    extras = {
        key: value
        for key, value in record.__dict__.items()
        if key not in _STANDARD_LOG_RECORD_ATTRIBUTES and not key.startswith("_")
    }
    return extras or None
