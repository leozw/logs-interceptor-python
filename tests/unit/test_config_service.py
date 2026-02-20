from __future__ import annotations

from logs_interceptor.application.config_service import ConfigService
from logs_interceptor.config import (
    BufferConfig,
    CircuitBreakerConfig,
    FilterConfig,
    LogsInterceptorConfig,
    PerformanceConfig,
    TransportConfig,
)


def test_validate_requires_fields() -> None:
    errors = ConfigService.validate(LogsInterceptorConfig())
    assert "Transport URL is required" in errors
    assert "Tenant ID is required" in errors
    assert "App name is required" in errors


def test_validate_url_and_ranges() -> None:
    config = LogsInterceptorConfig(
        transport=TransportConfig(
            url="invalid-url",
            tenant_id="tenant",
            timeout=-1,
            max_retries=-1,
            retry_delay=-1,
        ),
        app_name="app",
    )

    errors = ConfigService.validate(config)
    assert "Transport URL must be a valid URL" in errors
    assert "Transport timeout must be greater than or equal to 0" in errors
    assert "Transport max retries must be greater than or equal to 0" in errors
    assert "Transport retry delay must be greater than or equal to 0" in errors


def test_resolve_applies_defaults() -> None:
    resolved = ConfigService.resolve(
        LogsInterceptorConfig(
            transport=TransportConfig(url="https://loki.example.com/loki/api/v1/push", tenant_id="tenant"),
            app_name="app",
        )
    )

    assert resolved.transport.timeout == 10_000
    assert resolved.transport.max_retries == 3
    assert resolved.buffer.max_size == 100
    assert resolved.filter.sampling_rate == 1.0
    assert resolved.circuit_breaker.failure_threshold == 50
    assert resolved.performance.max_concurrent_flushes == 3


def test_validate_extended_ranges() -> None:
    config = LogsInterceptorConfig(
        transport=TransportConfig(
            url="https://loki.example.com/loki/api/v1/push",
            tenant_id="tenant",
            compression_level=-1,
        ),
        app_name="app",
        buffer=BufferConfig(max_size=0, flush_interval=0, max_memory_mb=0),
        filter=FilterConfig(sampling_rate=2.0),
        circuit_breaker=CircuitBreakerConfig(
            failure_threshold=0,
            reset_timeout=0,
            half_open_requests=0,
        ),
        performance=PerformanceConfig(max_concurrent_flushes=0),
    )

    errors = ConfigService.validate(config)
    assert "Buffer max size must be greater than 0" in errors
    assert "Flush interval must be greater than 0" in errors
    assert "Buffer max memory must be greater than 0" in errors
    assert "Sampling rate must be between 0 and 1" in errors
    assert "Circuit breaker failure threshold must be greater than 0" in errors
    assert "Circuit breaker reset timeout must be greater than 0" in errors
    assert "Circuit breaker half-open requests must be greater than 0" in errors
    assert "Max concurrent flushes must be greater than 0" in errors
    assert "Compression level must be greater than or equal to 0" in errors


def test_resolve_transport_compression_variants() -> None:
    base = {
        "url": "https://loki.example.com/loki/api/v1/push",
        "tenant_id": "tenant",
    }

    none_cfg = ConfigService.resolve(
        LogsInterceptorConfig(
            transport=TransportConfig(**base, compression=False),
            app_name="app",
        )
    )
    assert none_cfg.transport.compression == "none"

    brotli_cfg = ConfigService.resolve(
        LogsInterceptorConfig(
            transport=TransportConfig(**base, compression="brotli"),
            app_name="app",
        )
    )
    assert brotli_cfg.transport.compression == "brotli"

    snappy_cfg = ConfigService.resolve(
        LogsInterceptorConfig(
            transport=TransportConfig(**base, compression="snappy"),
            app_name="app",
        )
    )
    assert snappy_cfg.transport.compression == "snappy"
