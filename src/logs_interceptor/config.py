from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from .types import LogLevel

CompressionType = Literal["none", "gzip", "brotli", "snappy"]
DLQType = Literal["memory", "file"]


@dataclass(slots=True)
class TransportConfig:
    url: str = ""
    tenant_id: str = ""
    auth_token: str | None = None
    timeout: int | None = None
    max_retries: int | None = None
    retry_delay: int | None = None
    compression: CompressionType | bool | None = None
    compression_level: int | None = None
    compression_threshold: int | None = None
    use_workers: bool | None = None
    max_workers: int | None = None
    worker_timeout: int | None = None
    enable_connection_pooling: bool | None = None
    max_sockets: int | None = None


@dataclass(slots=True)
class BufferConfig:
    max_size: int | None = None
    flush_interval: int | None = None
    max_age: int | None = None
    auto_flush: bool | None = None
    max_memory_mb: int | None = None


@dataclass(slots=True)
class FilterConfig:
    levels: list[LogLevel] | None = None
    patterns: list[str] | None = None
    sampling_rate: float | None = None
    max_message_length: int | None = None
    sanitize: bool | None = None
    sensitive_patterns: list[str] | None = None


@dataclass(slots=True)
class CircuitBreakerConfig:
    enabled: bool | None = None
    failure_threshold: int | None = None
    reset_timeout: int | None = None
    half_open_requests: int | None = None


@dataclass(slots=True)
class PerformanceConfig:
    use_workers: bool | None = None
    max_concurrent_flushes: int | None = None
    compression_level: int | None = None
    max_workers: int | None = None
    worker_timeout: int | None = None


@dataclass(slots=True)
class DeadLetterQueueConfig:
    enabled: bool | None = None
    type: DLQType | None = None
    max_size: int | None = None
    max_file_size_mb: int | None = None
    max_retries: int | None = None
    base_path: str | None = None


@dataclass(slots=True)
class WinstonIntegrationConfig:
    enabled: bool = True
    levels: dict[str, LogLevel] | None = None


@dataclass(slots=True)
class MorganIntegrationConfig:
    enabled: bool = True
    format: str | None = None


@dataclass(slots=True)
class IntegrationsConfig:
    winston: bool | WinstonIntegrationConfig | None = None
    morgan: bool | MorganIntegrationConfig | None = None


@dataclass(slots=True)
class LogsInterceptorConfig:
    transport: TransportConfig = field(default_factory=TransportConfig)
    app_name: str = ""
    version: str | None = None
    environment: str | None = None
    labels: dict[str, str] | None = None
    dynamic_labels: dict[str, Callable[[], str | int]] | None = None
    buffer: BufferConfig | None = None
    filter: FilterConfig | None = None
    circuit_breaker: CircuitBreakerConfig | None = None
    integrations: IntegrationsConfig | None = None
    performance: PerformanceConfig | None = None
    dead_letter_queue: DeadLetterQueueConfig | None = None
    enable_metrics: bool | None = None
    enable_health_check: bool | None = None
    intercept_console: bool | None = None
    preserve_original_console: bool | None = None
    debug: bool | None = None
    silent_errors: bool | None = None


@dataclass(slots=True)
class ResolvedTransportConfig:
    url: str
    tenant_id: str
    auth_token: str
    timeout: int
    max_retries: int
    retry_delay: int
    compression: CompressionType
    compression_level: int
    compression_threshold: int
    use_workers: bool
    max_workers: int | None
    worker_timeout: int
    enable_connection_pooling: bool
    max_sockets: int


@dataclass(slots=True)
class ResolvedBufferConfig:
    max_size: int
    flush_interval: int
    max_age: int
    auto_flush: bool
    max_memory_mb: int


@dataclass(slots=True)
class ResolvedFilterConfig:
    levels: list[LogLevel]
    patterns: list[str]
    sampling_rate: float
    max_message_length: int
    sanitize: bool
    sensitive_patterns: list[str]


@dataclass(slots=True)
class ResolvedCircuitBreakerConfig:
    enabled: bool
    failure_threshold: int
    reset_timeout: int
    half_open_requests: int


@dataclass(slots=True)
class ResolvedPerformanceConfig:
    use_workers: bool
    max_concurrent_flushes: int
    compression_level: int
    max_workers: int | None
    worker_timeout: int


@dataclass(slots=True)
class ResolvedLogsInterceptorConfig:
    transport: ResolvedTransportConfig
    app_name: str
    version: str
    environment: str
    labels: dict[str, str]
    dynamic_labels: dict[str, Callable[[], str | int]]
    buffer: ResolvedBufferConfig
    filter: ResolvedFilterConfig
    circuit_breaker: ResolvedCircuitBreakerConfig
    integrations: IntegrationsConfig
    performance: ResolvedPerformanceConfig
    dead_letter_queue: DeadLetterQueueConfig | None
    enable_metrics: bool
    enable_health_check: bool
    intercept_console: bool
    preserve_original_console: bool
    debug: bool
    silent_errors: bool
