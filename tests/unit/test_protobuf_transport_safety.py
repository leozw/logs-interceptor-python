from __future__ import annotations

import pytest

from logs_interceptor.config import (
    IntegrationsConfig,
    ResolvedBufferConfig,
    ResolvedCircuitBreakerConfig,
    ResolvedFilterConfig,
    ResolvedLogsInterceptorConfig,
    ResolvedPerformanceConfig,
    ResolvedTransportConfig,
)
from logs_interceptor.domain.entities import LogEntryEntity
from logs_interceptor.infrastructure.internal_capture_guard import (
    is_internal_log_capture_suppressed,
)
from logs_interceptor.infrastructure.transport.loki_protobuf_transport import LokiProtobufTransport
from logs_interceptor.infrastructure.transport.resilient_transport import ResilientTransport
from logs_interceptor.infrastructure.transport.transport_factory import TransportFactory


def _config() -> ResolvedLogsInterceptorConfig:
    return ResolvedLogsInterceptorConfig(
        transport=ResolvedTransportConfig(
            url="https://loki.example.com/loki/api/v1/push",
            tenant_id="tenant",
            auth_token="",
            timeout=100,
            max_retries=0,
            retry_delay=0,
            compression="snappy",
            compression_level=4,
            compression_threshold=1,
            use_workers=False,
            max_workers=None,
            worker_timeout=100,
            enable_connection_pooling=False,
            max_sockets=10,
        ),
        app_name="app",
        version="1.0.0",
        environment="test",
        labels={},
        dynamic_labels={},
        buffer=ResolvedBufferConfig(
            max_size=10,
            flush_interval=1000,
            max_age=1000,
            auto_flush=False,
            max_memory_mb=10,
        ),
        filter=ResolvedFilterConfig(
            levels=["info"],
            patterns=[],
            sampling_rate=1.0,
            max_message_length=1000,
            sanitize=False,
            sensitive_patterns=[],
        ),
        circuit_breaker=ResolvedCircuitBreakerConfig(
            enabled=False,
            failure_threshold=1,
            reset_timeout=1000,
            half_open_requests=1,
        ),
        integrations=IntegrationsConfig(),
        performance=ResolvedPerformanceConfig(
            use_workers=False,
            max_concurrent_flushes=1,
            compression_level=1,
            max_workers=None,
            worker_timeout=1000,
        ),
        dead_letter_queue=None,
        enable_metrics=True,
        enable_health_check=True,
        intercept_console=False,
        preserve_original_console=True,
        debug=False,
        silent_errors=False,
    )


def test_protobuf_transport_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config()
    monkeypatch.delenv("LOGS_ENABLE_EXPERIMENTAL_PROTOBUF", raising=False)
    with pytest.raises(RuntimeError):
        LokiProtobufTransport(config.transport)


def test_transport_factory_falls_back_to_json_for_snappy_without_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config()
    monkeypatch.delenv("LOGS_ENABLE_EXPERIMENTAL_PROTOBUF", raising=False)
    transport = TransportFactory.create(config)
    assert isinstance(transport, ResilientTransport)
    assert transport._transport.__class__.__name__ == "LokiJsonTransport"  # noqa: SLF001


def test_protobuf_transport_suppresses_internal_capture_during_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Snappy:
        @staticmethod
        def compress(raw: bytes) -> bytes:
            return raw[::-1]

    class _Response:
        status_code = 204
        text = ""

    monkeypatch.setenv("LOGS_ENABLE_EXPERIMENTAL_PROTOBUF", "true")
    monkeypatch.setattr(
        "logs_interceptor.infrastructure.transport.loki_protobuf_transport.snappy",
        _Snappy(),
    )

    transport = LokiProtobufTransport(_config().transport)
    observed: list[bool] = []

    def fake_request(headers, body):
        del headers, body
        observed.append(is_internal_log_capture_suppressed())
        return _Response()

    monkeypatch.setattr(transport, "_request", fake_request)

    transport.send(
        [
            LogEntryEntity(
                id="1",
                timestamp="2026-01-01T00:00:00.000000+00:00",
                level="info",
                message="hello",
                labels={"service": "billing"},
                context={"a": 1},
            )
        ]
    )

    assert observed == [True]
