from __future__ import annotations

import logging

from logs_interceptor.infrastructure.internal_capture_guard import suppress_internal_log_capture
from logs_interceptor.integrations.logging_handler import LoggingHandler
from logs_interceptor.integrations.structlog import StructlogProcessor


class _Logger:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []

    def log(self, level, message, context=None):
        self.calls.append((level, message, context))


def test_logging_handler_ignores_records_during_internal_suppression() -> None:
    logger = _Logger()
    handler = LoggingHandler(logger)
    record = logging.LogRecord(
        name="service.api",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="hello",
        args=(),
        exc_info=None,
    )

    with suppress_internal_log_capture():
        handler.emit(record)

    assert logger.calls == []


def test_structlog_processor_ignores_records_during_internal_suppression() -> None:
    logger = _Logger()
    processor = StructlogProcessor(logger)

    with suppress_internal_log_capture():
        result = processor(None, "info", {"event": "hello", "request_id": "req-1"})

    assert result == {"event": "hello", "request_id": "req-1"}
    assert logger.calls == []


def test_logging_handler_ignores_configured_noisy_prefixes() -> None:
    logger = _Logger()
    handler = LoggingHandler(logger, exclude_prefixes=["botocore"])

    noisy_record = logging.LogRecord(
        name="botocore.endpoint",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="noise",
        args=(),
        exc_info=None,
    )
    app_record = logging.LogRecord(
        name="service.api",
        level=logging.INFO,
        pathname=__file__,
        lineno=20,
        msg="hello",
        args=(),
        exc_info=None,
    )

    handler.emit(noisy_record)
    handler.emit(app_record)

    assert logger.calls == [
        (
            "info",
            "hello",
            {
                "source": "python-logging",
                "logger_name": "service.api",
                "module": "test_integration_filters",
                "function": None,
                "line": 20,
            },
        )
    ]


def test_logging_handler_captures_python_logging_extra() -> None:
    logger = _Logger()
    handler = LoggingHandler(logger)
    record = logging.getLogger("service.fenix").makeRecord(
        name="service.fenix",
        level=logging.INFO,
        fn=__file__,
        lno=158,
        msg="Payload construído com sucesso",
        args=(),
        exc_info=None,
        func="create_kit",
        extra={"payload": {"cpf": "12345678901", "id": 42}},
    )

    handler.emit(record)

    assert logger.calls == [
        (
            "info",
            "Payload construído com sucesso",
            {
                "source": "python-logging",
                "logger_name": "service.fenix",
                "module": "test_integration_filters",
                "function": "create_kit",
                "line": 158,
                "extra": {"payload": {"cpf": "12345678901", "id": 42}},
            },
        )
    ]
