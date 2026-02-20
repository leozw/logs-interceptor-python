from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..application.log_service import LogService
from ..config import ResolvedLogsInterceptorConfig
from ..domain.interfaces import ILogger
from ..infrastructure.buffer import MemoryBuffer
from ..infrastructure.circuit_breaker import CircuitBreaker
from ..infrastructure.context import ContextVarProvider
from ..infrastructure.dlq import FileDeadLetterQueue, MemoryDeadLetterQueue
from ..infrastructure.filter import LogFilter
from ..infrastructure.interceptors import RuntimeInterceptor
from ..infrastructure.transport import TransportFactory

otel_trace: Any = None
try:
    from opentelemetry import trace as otel_trace
except Exception:  # pragma: no cover - optional dependency
    pass


@dataclass(slots=True)
class RuntimeBundle:
    logger: ILogger
    runtime_interceptor: RuntimeInterceptor | None = None


class LogsInterceptorFactory:
    @staticmethod
    def create(config: ResolvedLogsInterceptorConfig) -> RuntimeBundle:
        context_provider = ContextVarProvider()

        dynamic_labels: dict[str, Callable[[], str | int]] = {
            "request_id": lambda: str(context_provider.get("request_id", "")),
        }

        if otel_trace is not None:
            dynamic_labels["trace_id"] = lambda: LogsInterceptorFactory._trace_id()
            dynamic_labels["span_id"] = lambda: LogsInterceptorFactory._span_id()

        dynamic_labels.update(config.dynamic_labels)

        circuit_breaker = CircuitBreaker(config.circuit_breaker)

        dlq: FileDeadLetterQueue | MemoryDeadLetterQueue | None = None
        dlq_cfg = config.dead_letter_queue
        if dlq_cfg and dlq_cfg.enabled is not False:
            dlq_type = dlq_cfg.type or "memory"
            if dlq_type == "file":
                dlq = FileDeadLetterQueue(
                    base_path=dlq_cfg.base_path,
                    max_size=dlq_cfg.max_size or 1000,
                    max_retries=dlq_cfg.max_retries or 3,
                    max_file_size_mb=dlq_cfg.max_file_size_mb or 10,
                )
            else:
                dlq = MemoryDeadLetterQueue(dlq_cfg.max_size or 1000)

        transport = TransportFactory.create(config, circuit_breaker, dlq)
        buffer = MemoryBuffer(config.buffer)
        filter_service = LogFilter(config.filter)

        logger = LogService(
            filter_service,
            buffer,
            transport,
            context_provider,
            {
                "app_name": config.app_name,
                "version": config.version,
                "environment": config.environment,
                "labels": config.labels,
                "dynamic_labels": dynamic_labels,
                "enable_metrics": config.enable_metrics,
                "max_concurrent_flushes": config.performance.max_concurrent_flushes,
            },
        )

        runtime_interceptor = None
        if config.intercept_console:
            runtime_interceptor = RuntimeInterceptor(logger, config.preserve_original_console)
            runtime_interceptor.enable()

        original_destroy = logger.destroy

        def wrapped_destroy() -> None:
            if runtime_interceptor is not None:
                runtime_interceptor.restore()
            original_destroy()

        logger.destroy = wrapped_destroy  # type: ignore[method-assign]

        return RuntimeBundle(logger=logger, runtime_interceptor=runtime_interceptor)

    @staticmethod
    def _trace_id() -> str:
        if otel_trace is None:
            return ""
        try:
            span = otel_trace.get_current_span()
            if span is None:
                return ""
            ctx = span.get_span_context()
            trace_id = getattr(ctx, "trace_id", None)
            if isinstance(trace_id, int):
                return f"{trace_id:032x}"
            return str(trace_id or "")
        except Exception:
            return ""

    @staticmethod
    def _span_id() -> str:
        if otel_trace is None:
            return ""
        try:
            span = otel_trace.get_current_span()
            if span is None:
                return ""
            ctx = span.get_span_context()
            span_id = getattr(ctx, "span_id", None)
            if isinstance(span_id, int):
                return f"{span_id:016x}"
            return str(span_id or "")
        except Exception:
            return ""
