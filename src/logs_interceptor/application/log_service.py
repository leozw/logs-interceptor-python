from __future__ import annotations

import asyncio
import os
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast

from ..domain.entities import LogEntryEntity
from ..domain.interfaces import IContextProvider, ILogBuffer, ILogFilter, ILogger, ILogTransport
from ..infrastructure.metrics.metrics_collector import MetricsCollector
from ..types import CircuitBreakerState, HealthStatus, LoggerMetrics, LogLevel
from ..utils import internal_warn

resource: Any = None
try:
    import resource
except Exception:  # pragma: no cover
    pass

otel_trace: Any = None
try:
    from opentelemetry import trace as otel_trace
except Exception:  # pragma: no cover - optional dependency
    pass


@dataclass(slots=True)
class _FlushTask:
    entries: list[LogEntryEntity]
    event: threading.Event
    error: Exception | None = None


class LogService(ILogger):
    def __init__(
        self,
        filter_service: ILogFilter,
        buffer: ILogBuffer,
        transport: ILogTransport,
        context_provider: IContextProvider,
        config: dict[str, Any],
    ) -> None:
        self._filter = filter_service
        self._buffer = buffer
        self._transport = transport
        self._context_provider = context_provider
        self._config = config

        self._start_time = time.time()
        self._hostname = socket.gethostname()
        self._pid = str(os.getpid())
        self._max_concurrent_flushes = max(1, int(config.get("max_concurrent_flushes", 1)))

        self._metrics: dict[str, Any] = {
            "logs_processed": 0,
            "logs_dropped": 0,
            "logs_sanitized": 0,
            "flush_count": 0,
            "error_count": 0,
            "buffer_size": 0,
            "avg_flush_time": 0.0,
            "last_flush_time": 0.0,
            "memory_usage": 0.0,
            "cpu_usage": 0.0,
            "circuit_breaker_trips": 0,
            "dropped_by_backpressure": 0,
            "dropped_by_dlq": 0,
        }

        self._destroyed = False
        self._log_sequence = 0
        self._last_resource_sample_at = 0.0
        self._resource_sample_interval = 1.0

        self._flush_queue: list[_FlushTask] = []
        self._in_flight_flushes = 0
        self._queue_lock = threading.RLock()
        self._queue_cond = threading.Condition(self._queue_lock)

        self._metrics_collector = MetricsCollector()

        if hasattr(self._buffer, "set_flush_callback"):
            try:
                self._buffer.set_flush_callback(lambda: self.flush())
            except Exception:
                pass

    def debug(self, message: str, context: dict[str, Any] | None = None) -> None:
        self.log("debug", message, context)

    def info(self, message: str, context: dict[str, Any] | None = None) -> None:
        self.log("info", message, context)

    def warn(self, message: str, context: dict[str, Any] | None = None) -> None:
        self.log("warn", message, context)

    def error(self, message: str, context: dict[str, Any] | None = None) -> None:
        self.log("error", message, context)

    def fatal(self, message: str, context: dict[str, Any] | None = None) -> None:
        self.log("fatal", message, context)
        try:
            self.flush()
        except Exception:
            pass

    def with_context(self, context: dict[str, Any], fn: Callable[[], Any]) -> Any:
        return self._context_provider.run_with_context(context, fn)

    async def with_context_async(self, context: dict[str, Any], fn: Callable[[], Any]) -> Any:
        return await self._context_provider.run_with_context_async(context, fn)

    def log(self, level: LogLevel, message: str, context: dict[str, Any] | None = None) -> None:
        if self._destroyed:
            self._metrics["logs_dropped"] += 1
            return

        if not self._filter.is_level_enabled(level):
            return

        entry = self._create_log_entry(level, message, context)

        if not self._filter.should_process(entry):
            self._metrics["logs_dropped"] += 1
            return

        filtered = self._filter.filter(entry)
        if filtered.message != entry.message or filtered.context != entry.context:
            self._metrics["logs_sanitized"] += 1

        self._buffer.add(filtered)
        self._metrics["logs_processed"] += 1
        self._update_metrics()

    def track_event(self, event_name: str, properties: dict[str, Any] | None = None) -> None:
        self.info(f"[EVENT] {event_name}", properties)

    def _create_log_entry(
        self,
        level: LogLevel,
        message: str,
        context: dict[str, Any] | None,
    ) -> LogEntryEntity:
        async_context = self._context_provider.get_context()
        log_id = f"{int(time.time() * 1000):x}-{self._log_sequence:x}"
        self._log_sequence += 1

        dynamic_labels: dict[str, str] = {}
        providers = self._config.get("dynamic_labels", {})
        for key, provider in providers.items():
            try:
                value = str(provider())
                if value and value != "undefined":
                    dynamic_labels[key] = value
            except Exception:
                continue

        trace_id: str | None = None
        span_id: str | None = None
        if otel_trace is not None:
            try:
                span = otel_trace.get_current_span()
                if span is not None:
                    ctx = span.get_span_context()
                    if ctx is not None:
                        trace_id = getattr(ctx, "trace_id", None)
                        span_id = getattr(ctx, "span_id", None)
                        if isinstance(trace_id, int):
                            trace_id = f"{trace_id:032x}"
                        if isinstance(span_id, int):
                            span_id = f"{span_id:016x}"
            except Exception:
                pass

        if not trace_id:
            trace_id = dynamic_labels.get("trace_id")
        if not span_id:
            span_id = dynamic_labels.get("span_id")

        return LogEntryEntity(
            id=log_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            level=level,
            message=message,
            context={**async_context, **(context or {})} or None,
            trace_id=trace_id,
            span_id=span_id,
            request_id=dynamic_labels.get("request_id"),
            labels={
                "app": self._config["app_name"],
                "version": self._config["version"],
                "environment": self._config["environment"],
                "level": level,
                "hostname": self._hostname,
                "pid": self._pid,
                **self._config.get("labels", {}),
                **dynamic_labels,
            },
            metadata={
                "memory_usage": self._metrics.get("memory_usage", 0.0),
                "cpu_usage": self._metrics.get("cpu_usage", 0.0),
            },
        )

    def flush(self) -> None:
        if self._destroyed:
            return

        if self._buffer.size() > 0:
            entries = self._buffer.flush()
            if entries:
                self._enqueue_flush(entries)

        self._wait_for_queue_idle()

    async def aflush(self) -> None:
        await asyncio.to_thread(self.flush)

    def _enqueue_flush(self, entries: list[LogEntryEntity]) -> None:
        task = _FlushTask(entries=entries, event=threading.Event())

        with self._queue_cond:
            self._flush_queue.append(task)
            self._process_flush_queue_locked()

        task.event.wait()
        if task.error is not None:
            raise task.error

    def _process_flush_queue_locked(self) -> None:
        while (
            self._in_flight_flushes < self._max_concurrent_flushes
            and len(self._flush_queue) > 0
        ):
            task = self._flush_queue.pop(0)
            self._in_flight_flushes += 1
            thread = threading.Thread(target=self._send_flush_batch, args=(task,), daemon=True)
            thread.start()

    def _send_flush_batch(self, task: _FlushTask) -> None:
        start = time.perf_counter()
        error: Exception | None = None

        try:
            self._transport.send(task.entries)
            flush_time = (time.perf_counter() - start) * 1000

            self._metrics_collector.record_latency(flush_time)
            self._metrics["flush_count"] += 1
            self._metrics["last_flush_time"] = time.time()

            count = self._metrics["flush_count"]
            current_avg = self._metrics.get("avg_flush_time", 0.0)
            self._metrics["avg_flush_time"] = ((current_avg * (count - 1)) + flush_time) / count
            self._update_metrics()
        except Exception as exc:
            self._metrics["error_count"] += 1
            error = exc
        finally:
            task.error = error
            task.event.set()
            with self._queue_cond:
                self._in_flight_flushes = max(0, self._in_flight_flushes - 1)
                self._process_flush_queue_locked()
                self._queue_cond.notify_all()

    def _wait_for_queue_idle(self) -> None:
        with self._queue_cond:
            while self._in_flight_flushes > 0 or self._flush_queue:
                self._queue_cond.wait(timeout=1)

    def get_metrics(self) -> LoggerMetrics:
        self._update_metrics(force=True)
        latency_metrics = self._metrics_collector.get_latency_metrics()
        compression_metrics = self._metrics_collector.get_compression_metrics()

        metrics: dict[str, Any] = {
            **self._metrics,
            "buffer_size": self._buffer.size(),
            "latency": {
                "p50": latency_metrics["p50"],
                "p95": latency_metrics["p95"],
                "p99": latency_metrics["p99"],
                "avg": latency_metrics["avg"],
            },
            "compression": {
                "avg_ratio": float(compression_metrics["avg_ratio"]),
                "avg_time": float(compression_metrics["avg_time"]),
                "total_saved_bytes": int(compression_metrics["total_saved_bytes"]),
            },
            "throughput": self._metrics_collector.get_throughput(60),
        }
        return cast(LoggerMetrics, metrics)

    def get_health(self) -> HealthStatus:
        buffer_metrics = self._buffer.get_metrics()
        transport_health = self._transport.get_health()

        circuit_state: CircuitBreakerState = "closed"
        if not transport_health.get("healthy", False):
            circuit_state = "open"
        elif "HALF_OPEN" in str(transport_health.get("error_message", "")):
            circuit_state = "half-open"

        health: dict[str, Any] = {
            "healthy": self._metrics["error_count"] < 10 and bool(transport_health.get("healthy", False)),
            "last_successful_flush": self._metrics["last_flush_time"],
            "consecutive_errors": self._metrics["error_count"],
            "buffer_utilization": (
                (buffer_metrics["size"] / buffer_metrics["max_size"]) if buffer_metrics["max_size"] else 0
            ),
            "uptime": time.time() - self._start_time,
            "memory_usage_mb": self._metrics["memory_usage"],
            "circuit_breaker_state": circuit_state,
        }
        last_error = transport_health.get("error_message")
        if isinstance(last_error, str):
            health["last_error"] = last_error
        return cast(HealthStatus, health)

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True

        flush_error: Exception | None = None
        try:
            if self._buffer.size() > 0:
                entries = self._buffer.flush()
                if entries:
                    self._enqueue_flush(entries)
            self._wait_for_queue_idle()
        except Exception as exc:
            flush_error = exc
        finally:
            try:
                self._buffer.destroy()
            except Exception as exc:
                internal_warn("Failed to destroy buffer", exc)
            try:
                self._transport.destroy()
            except Exception as exc:
                internal_warn("Failed to destroy transport", exc)

        if flush_error is not None:
            raise flush_error

    async def adestroy(self) -> None:
        await asyncio.to_thread(self.destroy)

    def _update_metrics(self, force: bool = False) -> None:
        if not bool(self._config.get("enable_metrics", True)):
            return

        now = time.time()
        if not force and (now - self._last_resource_sample_at) < self._resource_sample_interval:
            self._metrics["buffer_size"] = self._buffer.size()
            return

        self._last_resource_sample_at = now

        mem_usage = 0.0
        if resource is not None:
            try:
                mem_usage_raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                mem_usage = float(mem_usage_raw) / 1024
            except Exception:
                mem_usage = 0.0

        self._metrics["memory_usage"] = mem_usage
        self._metrics["cpu_usage"] = time.process_time()

        buffer_metrics = self._buffer.get_metrics()
        self._metrics["buffer_size"] = buffer_metrics["size"]
        self._metrics["dropped_by_backpressure"] = int(buffer_metrics.get("dropped_entries", 0))

        transport_metrics = self._transport.get_metrics() or {}
        self._metrics["dropped_by_dlq"] = int(transport_metrics.get("dlq_dropped_entries", 0))
