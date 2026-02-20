from __future__ import annotations

from urllib.parse import urlparse

from ..config import (
    BufferConfig,
    CircuitBreakerConfig,
    FilterConfig,
    IntegrationsConfig,
    LogsInterceptorConfig,
    PerformanceConfig,
    ResolvedBufferConfig,
    ResolvedCircuitBreakerConfig,
    ResolvedFilterConfig,
    ResolvedLogsInterceptorConfig,
    ResolvedPerformanceConfig,
    ResolvedTransportConfig,
    TransportConfig,
)
from ..types import LogLevel

DEFAULT_LEVELS: list[LogLevel] = ["debug", "info", "warn", "error", "fatal"]
DEFAULT_SENSITIVE_PATTERNS = [
    r"password",
    r"token",
    r"secret",
    r"api[_-]?key",
    r"authorization",
    r"credit[_-]?card",
    r"ssn",
    r"cpf",
]


class ConfigService:
    @staticmethod
    def validate(config: LogsInterceptorConfig) -> list[str]:
        errors: list[str] = []

        if not config.transport.url:
            errors.append("Transport URL is required")
        if not config.transport.tenant_id:
            errors.append("Tenant ID is required")
        if not config.app_name:
            errors.append("App name is required")

        if config.transport.url:
            parsed = urlparse(config.transport.url)
            if not parsed.scheme or not parsed.netloc:
                errors.append("Transport URL must be a valid URL")

        ConfigService._validate_non_negative(errors, "Transport timeout", config.transport.timeout)
        ConfigService._validate_non_negative(errors, "Transport max retries", config.transport.max_retries)
        ConfigService._validate_non_negative(errors, "Transport retry delay", config.transport.retry_delay)

        if config.buffer:
            ConfigService._validate_positive(errors, "Buffer max size", config.buffer.max_size)
            ConfigService._validate_positive(errors, "Flush interval", config.buffer.flush_interval)
            ConfigService._validate_positive(errors, "Buffer max memory", config.buffer.max_memory_mb)

        if config.filter and config.filter.sampling_rate is not None:
            if config.filter.sampling_rate < 0 or config.filter.sampling_rate > 1:
                errors.append("Sampling rate must be between 0 and 1")

        if config.circuit_breaker:
            ConfigService._validate_positive(
                errors,
                "Circuit breaker failure threshold",
                config.circuit_breaker.failure_threshold,
            )
            ConfigService._validate_positive(
                errors,
                "Circuit breaker reset timeout",
                config.circuit_breaker.reset_timeout,
            )
            ConfigService._validate_positive(
                errors,
                "Circuit breaker half-open requests",
                config.circuit_breaker.half_open_requests,
            )

        if config.performance:
            ConfigService._validate_positive(
                errors,
                "Max concurrent flushes",
                config.performance.max_concurrent_flushes,
            )

        if config.transport.compression_level is not None and config.transport.compression_level < 0:
            errors.append("Compression level must be greater than or equal to 0")

        return errors

    @staticmethod
    def resolve(config: LogsInterceptorConfig) -> ResolvedLogsInterceptorConfig:
        transport = ConfigService._resolve_transport(config.transport, config.performance)
        return ResolvedLogsInterceptorConfig(
            transport=transport,
            app_name=config.app_name,
            version=config.version or "1.0.0",
            environment=config.environment or "production",
            labels=config.labels or {},
            dynamic_labels=config.dynamic_labels or {},
            buffer=ConfigService._resolve_buffer(config.buffer),
            filter=ConfigService._resolve_filter(config.filter),
            circuit_breaker=ConfigService._resolve_circuit_breaker(config.circuit_breaker),
            integrations=config.integrations or IntegrationsConfig(),
            performance=ConfigService._resolve_performance(config.performance),
            dead_letter_queue=config.dead_letter_queue,
            enable_metrics=True if config.enable_metrics is None else config.enable_metrics,
            enable_health_check=True
            if config.enable_health_check is None
            else config.enable_health_check,
            intercept_console=False if config.intercept_console is None else config.intercept_console,
            preserve_original_console=True
            if config.preserve_original_console is None
            else config.preserve_original_console,
            debug=False if config.debug is None else config.debug,
            silent_errors=False if config.silent_errors is None else config.silent_errors,
        )

    @staticmethod
    def _resolve_transport(
        transport: TransportConfig,
        performance: PerformanceConfig | None,
    ) -> ResolvedTransportConfig:
        compression = "gzip"
        if transport.compression in (False, "none"):
            compression = "none"
        elif transport.compression == "brotli":
            compression = "brotli"
        elif transport.compression == "snappy":
            compression = "snappy"
        elif transport.compression in (True, "gzip", None):
            compression = "gzip"

        return ResolvedTransportConfig(
            url=transport.url,
            tenant_id=transport.tenant_id,
            auth_token=transport.auth_token or "",
            timeout=transport.timeout if transport.timeout is not None else 10_000,
            max_retries=transport.max_retries if transport.max_retries is not None else 3,
            retry_delay=transport.retry_delay if transport.retry_delay is not None else 1_000,
            compression=compression,  # type: ignore[arg-type]
            compression_level=(
                transport.compression_level
                if transport.compression_level is not None
                else (performance.compression_level if performance and performance.compression_level is not None else 6)
            ),
            compression_threshold=(
                transport.compression_threshold if transport.compression_threshold is not None else 1024
            ),
            use_workers=(
                transport.use_workers
                if transport.use_workers is not None
                else (performance.use_workers if performance and performance.use_workers is not None else True)
            ),
            max_workers=(
                transport.max_workers
                if transport.max_workers is not None
                else (performance.max_workers if performance else None)
            ),
            worker_timeout=(
                transport.worker_timeout
                if transport.worker_timeout is not None
                else (performance.worker_timeout if performance and performance.worker_timeout is not None else 30_000)
            ),
            enable_connection_pooling=(
                True if transport.enable_connection_pooling is None else transport.enable_connection_pooling
            ),
            max_sockets=transport.max_sockets if transport.max_sockets is not None else 50,
        )

    @staticmethod
    def _resolve_buffer(buffer: BufferConfig | None) -> ResolvedBufferConfig:
        source = buffer or BufferConfig()
        return ResolvedBufferConfig(
            max_size=100 if source.max_size is None else source.max_size,
            flush_interval=5000 if source.flush_interval is None else source.flush_interval,
            max_age=30_000 if source.max_age is None else source.max_age,
            auto_flush=True if source.auto_flush is None else source.auto_flush,
            max_memory_mb=50 if source.max_memory_mb is None else source.max_memory_mb,
        )

    @staticmethod
    def _resolve_filter(filter_cfg: FilterConfig | None) -> ResolvedFilterConfig:
        source = filter_cfg or FilterConfig()
        return ResolvedFilterConfig(
            levels=source.levels or DEFAULT_LEVELS,
            patterns=source.patterns or [],
            sampling_rate=1.0 if source.sampling_rate is None else source.sampling_rate,
            max_message_length=8192
            if source.max_message_length is None
            else source.max_message_length,
            sanitize=True if source.sanitize is None else source.sanitize,
            sensitive_patterns=source.sensitive_patterns or DEFAULT_SENSITIVE_PATTERNS,
        )

    @staticmethod
    def _resolve_circuit_breaker(
        circuit_breaker: CircuitBreakerConfig | None,
    ) -> ResolvedCircuitBreakerConfig:
        source = circuit_breaker or CircuitBreakerConfig()
        return ResolvedCircuitBreakerConfig(
            enabled=True if source.enabled is None else source.enabled,
            failure_threshold=50 if source.failure_threshold is None else source.failure_threshold,
            reset_timeout=30_000 if source.reset_timeout is None else source.reset_timeout,
            half_open_requests=3 if source.half_open_requests is None else source.half_open_requests,
        )

    @staticmethod
    def _resolve_performance(performance: PerformanceConfig | None) -> ResolvedPerformanceConfig:
        source = performance or PerformanceConfig()
        return ResolvedPerformanceConfig(
            use_workers=True if source.use_workers is None else source.use_workers,
            max_concurrent_flushes=3
            if source.max_concurrent_flushes is None
            else source.max_concurrent_flushes,
            compression_level=6 if source.compression_level is None else source.compression_level,
            max_workers=source.max_workers,
            worker_timeout=30_000 if source.worker_timeout is None else source.worker_timeout,
        )

    @staticmethod
    def _validate_non_negative(errors: list[str], field: str, value: int | None) -> None:
        if value is not None and value < 0:
            errors.append(f"{field} must be greater than or equal to 0")

    @staticmethod
    def _validate_positive(errors: list[str], field: str, value: int | None) -> None:
        if value is not None and value <= 0:
            errors.append(f"{field} must be greater than 0")
