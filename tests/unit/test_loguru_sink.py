from __future__ import annotations

from logs_interceptor.infrastructure.internal_capture_guard import suppress_internal_log_capture
from logs_interceptor.integrations.loguru import LoguruSink


class _Logger:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []

    def info(self, message, context=None):
        self.calls.append(("info", message, context))

    def log(self, level, message, context=None):
        self.calls.append((level, message, context))


class _Message:
    def __init__(self, record):
        self.record = record


class _Level:
    def __init__(self, name: str, no: int) -> None:
        self.name = name
        self.no = no


def test_loguru_sink_records_logger_name_and_metadata() -> None:
    logger = _Logger()
    sink = LoguruSink(logger)

    sink(
        _Message(
            {
                "name": "service.api",
                "module": "app",
                "function": "handler",
                "line": 42,
                "message": "hello",
                "level": {"name": "INFO"},
                "extra": {"request_id": "req-1"},
            }
        )
    )

    assert logger.calls == [
        (
            "info",
            "hello",
            {
                "source": "loguru",
                "logger_name": "service.api",
                "module": "app",
                "function": "handler",
                "line": 42,
                "extra": {"request_id": "req-1"},
            },
        )
    ]


def test_loguru_sink_excludes_configured_prefixes() -> None:
    logger = _Logger()
    sink = LoguruSink(logger, exclude_prefixes=["httpx", "httpcore"])

    sink(
        _Message(
            {
                "name": "httpx",
                "module": "client",
                "function": "send",
                "line": 1,
                "message": "request",
                "level": {"name": "DEBUG"},
                "extra": {},
            }
        )
    )

    assert logger.calls == []


def test_loguru_sink_supports_loguru_record_level_objects() -> None:
    logger = _Logger()
    sink = LoguruSink(logger)

    sink(
        _Message(
            {
                "name": "service.api",
                "module": "app",
                "function": "handler",
                "line": 42,
                "message": "hello",
                "level": _Level("WARNING", 30),
                "extra": {"request_id": "req-1"},
            }
        )
    )

    assert logger.calls == [
        (
            "warn",
            "hello",
            {
                "source": "loguru",
                "logger_name": "service.api",
                "module": "app",
                "function": "handler",
                "line": 42,
                "extra": {"request_id": "req-1"},
            },
        )
    ]


def test_loguru_sink_ignores_records_during_internal_suppression() -> None:
    logger = _Logger()
    sink = LoguruSink(logger)

    with suppress_internal_log_capture():
        sink(
            _Message(
                {
                    "name": "service.api",
                    "module": "app",
                    "function": "handler",
                    "line": 42,
                    "message": "hello",
                    "level": {"name": "INFO"},
                    "extra": {"request_id": "req-1"},
                }
            )
        )

    assert logger.calls == []
