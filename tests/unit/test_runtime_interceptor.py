from __future__ import annotations

import logging

from logs_interceptor.infrastructure.interceptors.runtime_interceptor import RuntimeInterceptor
from logs_interceptor.infrastructure.internal_capture_guard import suppress_internal_log_capture


class _Logger:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict[str, object] | None]] = []

    def log(self, level, message, context=None):
        self.records.append((level, message, context))

    def info(self, message, context=None):
        self.records.append(("info", message, context))

    def fatal(self, message, context=None):
        self.records.append(("fatal", message, context))

    def flush(self):
        return None


def test_runtime_interceptor_restores_root_logger_level() -> None:
    root = logging.getLogger()
    original_level = root.level
    root.setLevel(logging.WARNING)

    interceptor = RuntimeInterceptor(_Logger())
    interceptor.enable()

    assert root.level == logging.DEBUG

    interceptor.restore()

    assert root.level == logging.WARNING
    root.setLevel(original_level)


def test_runtime_interceptor_ignores_known_noisy_logger_prefixes() -> None:
    logger = _Logger()
    interceptor = RuntimeInterceptor(logger)
    interceptor.enable()

    noisy_logger = logging.getLogger("elven_unified_observability.runtime")
    noisy_logger.warning("internal warning")
    noisy_otel_logger = logging.getLogger("opentelemetry.sdk.trace")
    noisy_otel_logger.info("trace noise")

    assert logger.records == []

    interceptor.restore()


def test_runtime_interceptor_ignores_records_during_internal_suppression() -> None:
    logger = _Logger()
    interceptor = RuntimeInterceptor(logger)
    interceptor.enable()

    with suppress_internal_log_capture():
        logging.getLogger("service.api").warning("internal transport noise")

    assert logger.records == []

    interceptor.restore()


def test_runtime_interceptor_captures_python_logging_extra() -> None:
    logger = _Logger()
    interceptor = RuntimeInterceptor(logger)
    interceptor.enable()

    try:
        logging.getLogger("service.fenix").info(
            "Payload construído com sucesso",
            extra={"payload": {"cpf": "12345678901", "id": 42}},
        )
    finally:
        interceptor.restore()

    assert len(logger.records) == 1
    level, message, context = logger.records[0]
    assert level == "info"
    assert message == "Payload construído com sucesso"
    assert context is not None
    assert context["extra"] == {"payload": {"cpf": "12345678901", "id": 42}}
