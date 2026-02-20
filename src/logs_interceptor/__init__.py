from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

from .application import ConfigService
from .config import (
    BufferConfig,
    CircuitBreakerConfig,
    DeadLetterQueueConfig,
    FilterConfig,
    IntegrationsConfig,
    LogsInterceptorConfig,
    PerformanceConfig,
    TransportConfig,
)
from .domain.interfaces import ILogger
from .integrations import (
    CelerySignals,
    DjangoMiddleware,
    FastAPIMiddleware,
    FlaskExtension,
    LoggingHandler,
    LoguruSink,
    StructlogProcessor,
)
from .presentation import LogsInterceptorFactory
from .types import HealthStatus, LoggerMetrics, LogLevel
from .utils import internal_debug, internal_error, load_config_from_env, merge_configs, parse_bool

__all__ = [
    "init",
    "get_logger",
    "is_initialized",
    "destroy",
    "adestroy",
    "logger",
    "LogsInterceptorConfig",
    "TransportConfig",
    "BufferConfig",
    "FilterConfig",
    "CircuitBreakerConfig",
    "DeadLetterQueueConfig",
    "PerformanceConfig",
    "IntegrationsConfig",
    "LoggingHandler",
    "FastAPIMiddleware",
    "DjangoMiddleware",
    "FlaskExtension",
    "CelerySignals",
    "StructlogProcessor",
    "LoguruSink",
]


@dataclass(slots=True)
class _RuntimeState:
    logger: ILogger
    runtime_interceptor: Any | None = None


_global_runtime: _RuntimeState | None = None


def _pick(config: dict[str, Any], snake: str, camel: str, default: Any = None) -> Any:
    if snake in config:
        return config[snake]
    if camel in config:
        return config[camel]
    return default


def _coerce_config(user_config: LogsInterceptorConfig | dict[str, Any] | None) -> LogsInterceptorConfig:
    if user_config is None:
        return LogsInterceptorConfig()
    if isinstance(user_config, LogsInterceptorConfig):
        return user_config

    transport_raw = _pick(user_config, "transport", "transport", {}) or {}
    buffer_raw = _pick(user_config, "buffer", "buffer")
    filter_raw = _pick(user_config, "filter", "filter")
    cb_raw = _pick(user_config, "circuit_breaker", "circuitBreaker")
    perf_raw = _pick(user_config, "performance", "performance")
    dlq_raw = _pick(user_config, "dead_letter_queue", "deadLetterQueue")
    integrations_raw = _pick(user_config, "integrations", "integrations")

    return LogsInterceptorConfig(
        transport=TransportConfig(
            url=_pick(transport_raw, "url", "url", ""),
            tenant_id=_pick(transport_raw, "tenant_id", "tenantId", ""),
            auth_token=_pick(transport_raw, "auth_token", "authToken"),
            timeout=_pick(transport_raw, "timeout", "timeout"),
            max_retries=_pick(transport_raw, "max_retries", "maxRetries"),
            retry_delay=_pick(transport_raw, "retry_delay", "retryDelay"),
            compression=_pick(transport_raw, "compression", "compression"),
            compression_level=_pick(transport_raw, "compression_level", "compressionLevel"),
            compression_threshold=_pick(transport_raw, "compression_threshold", "compressionThreshold"),
            use_workers=_pick(transport_raw, "use_workers", "useWorkers"),
            max_workers=_pick(transport_raw, "max_workers", "maxWorkers"),
            worker_timeout=_pick(transport_raw, "worker_timeout", "workerTimeout"),
            enable_connection_pooling=_pick(
                transport_raw, "enable_connection_pooling", "enableConnectionPooling"
            ),
            max_sockets=_pick(transport_raw, "max_sockets", "maxSockets"),
        ),
        app_name=_pick(user_config, "app_name", "appName", ""),
        version=_pick(user_config, "version", "version"),
        environment=_pick(user_config, "environment", "environment"),
        labels=_pick(user_config, "labels", "labels"),
        dynamic_labels=_pick(user_config, "dynamic_labels", "dynamicLabels"),
        buffer=(
            BufferConfig(
                max_size=_pick(buffer_raw, "max_size", "maxSize") if buffer_raw else None,
                flush_interval=_pick(buffer_raw, "flush_interval", "flushInterval")
                if buffer_raw
                else None,
                max_age=_pick(buffer_raw, "max_age", "maxAge") if buffer_raw else None,
                auto_flush=_pick(buffer_raw, "auto_flush", "autoFlush") if buffer_raw else None,
                max_memory_mb=_pick(buffer_raw, "max_memory_mb", "maxMemoryMB")
                if buffer_raw
                else None,
            )
            if buffer_raw
            else None
        ),
        filter=(
            FilterConfig(
                levels=_pick(filter_raw, "levels", "levels"),
                patterns=_pick(filter_raw, "patterns", "patterns"),
                sampling_rate=_pick(filter_raw, "sampling_rate", "samplingRate"),
                max_message_length=_pick(filter_raw, "max_message_length", "maxMessageLength"),
                sanitize=_pick(filter_raw, "sanitize", "sanitize"),
                sensitive_patterns=_pick(filter_raw, "sensitive_patterns", "sensitivePatterns"),
            )
            if filter_raw
            else None
        ),
        circuit_breaker=(
            CircuitBreakerConfig(
                enabled=_pick(cb_raw, "enabled", "enabled"),
                failure_threshold=_pick(cb_raw, "failure_threshold", "failureThreshold"),
                reset_timeout=_pick(cb_raw, "reset_timeout", "resetTimeout"),
                half_open_requests=_pick(cb_raw, "half_open_requests", "halfOpenRequests"),
            )
            if cb_raw
            else None
        ),
        integrations=(IntegrationsConfig() if integrations_raw is not None else None),
        performance=(
            PerformanceConfig(
                use_workers=_pick(perf_raw, "use_workers", "useWorkers"),
                max_concurrent_flushes=_pick(perf_raw, "max_concurrent_flushes", "maxConcurrentFlushes"),
                compression_level=_pick(perf_raw, "compression_level", "compressionLevel"),
                max_workers=_pick(perf_raw, "max_workers", "maxWorkers"),
                worker_timeout=_pick(perf_raw, "worker_timeout", "workerTimeout"),
            )
            if perf_raw
            else None
        ),
        dead_letter_queue=(
            DeadLetterQueueConfig(
                enabled=_pick(dlq_raw, "enabled", "enabled"),
                type=_pick(dlq_raw, "type", "type"),
                max_size=_pick(dlq_raw, "max_size", "maxSize"),
                max_file_size_mb=_pick(dlq_raw, "max_file_size_mb", "maxFileSizeMB"),
                max_retries=_pick(dlq_raw, "max_retries", "maxRetries"),
                base_path=_pick(dlq_raw, "base_path", "basePath"),
            )
            if dlq_raw
            else None
        ),
        enable_metrics=_pick(user_config, "enable_metrics", "enableMetrics"),
        enable_health_check=_pick(user_config, "enable_health_check", "enableHealthCheck"),
        intercept_console=_pick(user_config, "intercept_console", "interceptConsole"),
        preserve_original_console=_pick(
            user_config,
            "preserve_original_console",
            "preserveOriginalConsole",
        ),
        debug=_pick(user_config, "debug", "debug"),
        silent_errors=_pick(user_config, "silent_errors", "silentErrors"),
    )


def init(user_config: LogsInterceptorConfig | dict[str, Any] | None = None) -> ILogger:
    global _global_runtime

    env_config = load_config_from_env()
    if user_config is None:
        merged_config = env_config
    else:
        coerced_user = _coerce_config(user_config)
        merged_config = merge_configs(coerced_user, env_config)

    errors = ConfigService.validate(merged_config)
    if errors:
        raise ValueError("Configuration errors:\n" + "\n".join(errors))

    resolved = ConfigService.resolve(merged_config)

    previous = _global_runtime
    if previous is not None:
        if previous.runtime_interceptor is not None:
            previous.runtime_interceptor.restore()
        try:
            previous.logger.destroy()
        except Exception:
            pass

    runtime = LogsInterceptorFactory.create(resolved)
    _global_runtime = _RuntimeState(
        logger=runtime.logger,
        runtime_interceptor=runtime.runtime_interceptor,
    )

    return runtime.logger


def get_logger() -> ILogger:
    if _global_runtime is None:
        raise RuntimeError("LogsInterceptor not initialized. Call init() first.")
    return _global_runtime.logger


def is_initialized() -> bool:
    return _global_runtime is not None


def destroy() -> None:
    global _global_runtime

    if _global_runtime is None:
        return

    runtime = _global_runtime
    _global_runtime = None

    if runtime.runtime_interceptor is not None:
        runtime.runtime_interceptor.restore()

    runtime.logger.destroy()


async def adestroy() -> None:
    await asyncio.to_thread(destroy)


class _GlobalLoggerProxy:
    def debug(self, message: str, context: dict[str, Any] | None = None) -> None:
        if _global_runtime is not None:
            _global_runtime.logger.debug(message, context)

    def info(self, message: str, context: dict[str, Any] | None = None) -> None:
        if _global_runtime is not None:
            _global_runtime.logger.info(message, context)

    def warn(self, message: str, context: dict[str, Any] | None = None) -> None:
        if _global_runtime is not None:
            _global_runtime.logger.warn(message, context)

    def error(self, message: str, context: dict[str, Any] | None = None) -> None:
        if _global_runtime is not None:
            _global_runtime.logger.error(message, context)

    def fatal(self, message: str, context: dict[str, Any] | None = None) -> None:
        if _global_runtime is not None:
            _global_runtime.logger.fatal(message, context)

    def log(self, level: LogLevel, message: str, context: dict[str, Any] | None = None) -> None:
        if _global_runtime is not None:
            _global_runtime.logger.log(level, message, context)

    def track_event(self, event_name: str, properties: dict[str, Any] | None = None) -> None:
        if _global_runtime is not None:
            _global_runtime.logger.track_event(event_name, properties)

    def with_context(self, context: dict[str, Any], fn: Any) -> Any:
        if _global_runtime is None:
            raise RuntimeError("LogsInterceptor not initialized")
        return _global_runtime.logger.with_context(context, fn)

    async def with_context_async(self, context: dict[str, Any], fn: Any) -> Any:
        if _global_runtime is None:
            raise RuntimeError("LogsInterceptor not initialized")
        return await _global_runtime.logger.with_context_async(context, fn)

    def flush(self) -> None:
        if _global_runtime is not None:
            _global_runtime.logger.flush()

    async def aflush(self) -> None:
        if _global_runtime is not None:
            await _global_runtime.logger.aflush()

    def get_metrics(self) -> LoggerMetrics:
        if _global_runtime is None:
            raise RuntimeError("LogsInterceptor not initialized")
        return _global_runtime.logger.get_metrics()

    def get_health(self) -> HealthStatus:
        if _global_runtime is None:
            raise RuntimeError("LogsInterceptor not initialized")
        return _global_runtime.logger.get_health()

    def destroy(self) -> None:
        destroy()

    async def adestroy(self) -> None:
        await adestroy()


logger = _GlobalLoggerProxy()


def _auto_init_if_enabled() -> None:
    if not parse_bool(os.getenv("LOGS_AUTO_INIT"), False):
        return

    env_config = load_config_from_env()
    if not env_config.transport.url or not env_config.transport.tenant_id or not env_config.app_name:
        internal_debug("Auto-init skipped due to missing required LOGS_* variables")
        return

    try:
        init(env_config)
        internal_debug("Auto-initialized from LOGS_* environment variables")
    except Exception as exc:
        internal_error("Auto-initialization failed", exc)


_auto_init_if_enabled()
