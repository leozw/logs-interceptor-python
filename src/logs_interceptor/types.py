from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict

LogLevel = Literal["debug", "info", "warn", "error", "fatal"]
CircuitBreakerState = Literal["closed", "open", "half-open"]


class LogEntry(TypedDict, total=False):
    id: str
    timestamp: str
    level: LogLevel
    message: str
    context: dict[str, Any]
    trace_id: str
    span_id: str
    request_id: str
    labels: dict[str, str]
    metadata: dict[str, Any]


class TransportHealth(TypedDict, total=False):
    healthy: bool
    last_successful_send: float
    consecutive_failures: int
    error_message: str


class TransportMetrics(TypedDict, total=False):
    total_sends: int
    successful_sends: int
    failed_sends: int
    avg_latency: float
    avg_compression_time: float
    avg_compression_ratio: float
    total_bytes_sent: int
    total_bytes_compressed: int
    retry_attempts: int
    retried_requests: int
    dlq_dropped_entries: int


class LatencyMetrics(TypedDict):
    p50: float
    p95: float
    p99: float
    avg: float


class CompressionMetrics(TypedDict):
    avg_ratio: float
    avg_time: float
    total_saved_bytes: int


class LoggerMetrics(TypedDict, total=False):
    logs_processed: int
    logs_dropped: int
    logs_sanitized: int
    flush_count: int
    error_count: int
    buffer_size: int
    avg_flush_time: float
    last_flush_time: float
    memory_usage: float
    cpu_usage: float
    circuit_breaker_trips: int
    dropped_by_backpressure: int
    dropped_by_dlq: int
    latency: LatencyMetrics
    compression: CompressionMetrics
    throughput: float


class HealthStatus(TypedDict, total=False):
    healthy: bool
    last_successful_flush: float
    consecutive_errors: int
    buffer_utilization: float
    uptime: float
    memory_usage_mb: float
    circuit_breaker_state: CircuitBreakerState
    last_error: str


@dataclass(frozen=True)
class RuntimeState:
    initialized: bool
