from __future__ import annotations

import pytest

import logs_interceptor.infrastructure.transport.resilient_transport as resilient_module
from logs_interceptor.domain.entities import LogEntryEntity
from logs_interceptor.infrastructure.transport.resilient_transport import (
    ResilientTransport,
    ResilientTransportConfig,
)


class _FakeTransport:
    def __init__(self, fail_times: int = 0) -> None:
        self.fail_times = fail_times
        self.calls = 0

    def send(self, entries: list[LogEntryEntity]) -> None:
        self.calls += 1
        if self.calls <= self.fail_times:
            error = RuntimeError("timeout")
            error.retryable = True  # type: ignore[attr-defined]
            raise error

    def is_available(self) -> bool:
        return True

    def get_health(self) -> dict[str, object]:
        return {"healthy": True, "consecutive_failures": 0}

    def get_metrics(self) -> dict[str, int]:
        return {"total_sends": self.calls, "successful_sends": max(0, self.calls - self.fail_times)}

    def destroy(self) -> None:
        return None


class _NoMetricsTransport(_FakeTransport):
    def get_metrics(self):
        return None


class _FakeCircuitBreaker:
    def __init__(self, state: str = "closed") -> None:
        self.state = state

    def execute(self, operation):
        return operation()

    def record_success(self) -> None:
        return None

    def record_failure(self, error=None) -> None:
        return None

    def get_state(self) -> dict[str, object]:
        return {"state": self.state, "failures": 1, "last_error": "boom"}

    def reset(self) -> None:
        self.state = "closed"


class _FakeDlq:
    def __init__(self) -> None:
        self.added = 0

    def add(self, entry, reason: str):
        return {"added": 1, "dropped": 0}

    def add_batch(self, entries, reason: str):
        self.added += len(entries)
        return {"added": len(entries), "dropped": 1}

    def flush(self):
        return 0

    def size(self):
        return self.added

    def clear(self):
        return None

    def get_entries(self, limit: int = 100):
        return []

    def get_stats(self):
        return {"size": self.added, "dropped_entries": 0}


class _FailingDlq(_FakeDlq):
    def add_batch(self, entries, reason: str):
        raise RuntimeError("dlq unavailable")


def _entry() -> list[LogEntryEntity]:
    return [LogEntryEntity("1", "2026-01-01T00:00:00+00:00", "info", "msg")]


def test_resilient_transport_retries_and_succeeds() -> None:
    base = _FakeTransport(fail_times=1)
    transport = ResilientTransport(base, ResilientTransportConfig(max_retries=2, retry_delay=1))

    transport.send(_entry())
    metrics = transport.get_metrics()
    assert metrics is not None
    assert metrics["retry_attempts"] >= 1
    assert base.calls == 2


def test_resilient_transport_enqueues_dlq_on_failure() -> None:
    base = _FakeTransport(fail_times=10)
    dlq = _FakeDlq()
    transport = ResilientTransport(
        base,
        ResilientTransportConfig(max_retries=0, retry_delay=1),
        _FakeCircuitBreaker(),
        dlq,
    )

    with pytest.raises(RuntimeError):
        transport.send(_entry())

    metrics = transport.get_metrics()
    assert metrics is not None
    assert metrics["dlq_dropped_entries"] >= 1
    assert dlq.added == 1


def test_resilient_transport_health_from_circuit_breaker() -> None:
    base = _FakeTransport()
    transport = ResilientTransport(
        base,
        ResilientTransportConfig(),
        _FakeCircuitBreaker(state="open"),
        None,
    )

    health = transport.get_health()
    assert health["healthy"] is False
    assert "OPEN" in str(health["error_message"])


def test_resilient_transport_ignores_empty_batch() -> None:
    base = _FakeTransport()
    transport = ResilientTransport(base, ResilientTransportConfig())
    transport.send([])
    assert base.calls == 0


def test_resilient_transport_is_available_and_fallback_health() -> None:
    base = _FakeTransport()
    transport = ResilientTransport(base, ResilientTransportConfig())
    assert transport.is_available() is True
    assert transport.get_health()["healthy"] is True


def test_resilient_transport_half_open_health() -> None:
    base = _FakeTransport()
    transport = ResilientTransport(
        base,
        ResilientTransportConfig(),
        _FakeCircuitBreaker(state="half-open"),
        None,
    )
    health = transport.get_health()
    assert health["healthy"] is True
    assert "HALF_OPEN" in str(health["error_message"])


def test_resilient_transport_metrics_when_base_has_none() -> None:
    base = _NoMetricsTransport()
    transport = ResilientTransport(base, ResilientTransportConfig())
    metrics = transport.get_metrics()
    assert metrics is not None
    assert "retry_attempts" in metrics


def test_resilient_transport_dlq_enqueue_failure_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    base = _FakeTransport(fail_times=1)
    dlq = _FailingDlq()
    transport = ResilientTransport(
        base,
        ResilientTransportConfig(max_retries=0, retry_delay=1),
        None,
        dlq,
    )

    warnings: list[str] = []
    monkeypatch.setattr(resilient_module, "internal_warn", lambda msg, ctx=None: warnings.append(msg))

    with pytest.raises(RuntimeError):
        transport.send(_entry())

    assert warnings


def test_retryable_error_classification_variants() -> None:
    retryable = RuntimeError("whatever")
    retryable.retryable = True  # type: ignore[attr-defined]
    assert ResilientTransport._is_retryable_error(retryable) is True

    by_status = RuntimeError("http error")
    by_status.status_code = 503  # type: ignore[attr-defined]
    assert ResilientTransport._is_retryable_error(by_status) is True

    not_retryable = RuntimeError("bad request")
    not_retryable.status_code = 400  # type: ignore[attr-defined]
    assert ResilientTransport._is_retryable_error(not_retryable) is False

    by_message = RuntimeError("socket timeout on connect")
    assert ResilientTransport._is_retryable_error(by_message) is True
