from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from logs_interceptor.config import ResolvedTransportConfig
from logs_interceptor.domain.entities import LogEntryEntity
from logs_interceptor.infrastructure.transport.loki_json_transport import LokiJsonTransport, RetryableTransportError


@dataclass
class _Response:
    status_code: int
    text: str = ""


def _config(compression: str = "gzip") -> ResolvedTransportConfig:
    return ResolvedTransportConfig(
        url="https://loki.example.com/loki/api/v1/push",
        tenant_id="tenant",
        auth_token="",
        timeout=100,
        max_retries=0,
        retry_delay=0,
        compression=compression,  # type: ignore[arg-type]
        compression_level=6,
        compression_threshold=1,
        use_workers=False,
        max_workers=None,
        worker_timeout=100,
        enable_connection_pooling=False,
        max_sockets=10,
    )


def _entries() -> list[LogEntryEntity]:
    return [
        LogEntryEntity(
            id="1",
            timestamp="2026-01-01T00:00:00.000000+00:00",
            level="info",
            message="hello",
            labels={"service": "billing"},
            context={"a": 1},
        )
    ]


def test_loki_json_transport_send_success(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = LokiJsonTransport(_config())

    monkeypatch.setattr(transport, "_request", lambda headers, body: _Response(status_code=204))

    transport.send(_entries())
    metrics = transport.get_metrics()
    assert metrics["successful_sends"] == 1
    assert metrics["failed_sends"] == 0


def test_loki_json_transport_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = LokiJsonTransport(_config())

    monkeypatch.setattr(transport, "_request", lambda headers, body: _Response(status_code=500, text="err"))

    with pytest.raises(RetryableTransportError):
        transport.send(_entries())

    assert transport.get_health()["healthy"] is False


def test_timestamp_to_ns_uses_timezone_correctly() -> None:
    iso = "2026-02-20T19:39:14.123456+00:00"
    expected = int(datetime(2026, 2, 20, 19, 39, 14, 123456, tzinfo=timezone.utc).timestamp() * 1_000_000_000)
    assert LokiJsonTransport._timestamp_to_ns(iso) == expected


def test_timestamp_to_ns_fallback_for_invalid_input() -> None:
    result = LokiJsonTransport._timestamp_to_ns("not-a-timestamp")
    assert isinstance(result, int)
    assert result > 0
