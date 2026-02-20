from __future__ import annotations

from logs_interceptor.config import (
    ResolvedBufferConfig,
    ResolvedCircuitBreakerConfig,
    ResolvedFilterConfig,
)
from logs_interceptor.domain.entities import LogEntryEntity
from logs_interceptor.infrastructure.buffer import MemoryBuffer
from logs_interceptor.infrastructure.circuit_breaker import CircuitBreaker
from logs_interceptor.infrastructure.filter import LogFilter


def test_memory_buffer_drop_oldest_when_full() -> None:
    buffer = MemoryBuffer(
        ResolvedBufferConfig(
            max_size=2,
            flush_interval=1000,
            max_age=10000,
            auto_flush=False,
            max_memory_mb=10,
        )
    )

    buffer.add(LogEntryEntity("1", "2026-01-01T00:00:00+00:00", "info", "a"))
    buffer.add(LogEntryEntity("2", "2026-01-01T00:00:01+00:00", "info", "b"))
    buffer.add(LogEntryEntity("3", "2026-01-01T00:00:02+00:00", "info", "c"))

    assert buffer.size() == 2
    ids = [entry.id for entry in buffer.peek()]
    assert ids == ["2", "3"]


def test_log_filter_sanitizes_sensitive_values() -> None:
    filter_service = LogFilter(
        ResolvedFilterConfig(
            levels=["info", "error"],
            patterns=[],
            sampling_rate=1.0,
            max_message_length=1024,
            sanitize=True,
            sensitive_patterns=[r"token", r"password"],
        )
    )

    entry = LogEntryEntity(
        id="1",
        timestamp="2026-01-01T00:00:00+00:00",
        level="info",
        message="user logged in",
        context={"token": "secret-token", "safe": "ok"},
    )

    result = filter_service.filter(entry)
    assert result.context is not None
    assert result.context["token"] == "[REDACTED]"
    assert result.context["safe"] == "ok"


def test_circuit_breaker_opens_after_threshold() -> None:
    breaker = CircuitBreaker(
        ResolvedCircuitBreakerConfig(
            enabled=True,
            failure_threshold=2,
            reset_timeout=1000,
            half_open_requests=1,
        )
    )

    for _ in range(2):
        try:
            breaker.execute(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        except RuntimeError:
            pass

    state = breaker.get_state()
    assert state["state"] == "open"
