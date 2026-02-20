from __future__ import annotations

import hashlib
import json
import os
import random
import re
import secrets
import sys
from collections.abc import Iterable
from dataclasses import asdict, fields, is_dataclass
from datetime import datetime
from typing import Any, cast

from .config import (
    BufferConfig,
    CircuitBreakerConfig,
    CompressionType,
    DeadLetterQueueConfig,
    DLQType,
    FilterConfig,
    IntegrationsConfig,
    LogsInterceptorConfig,
    PerformanceConfig,
    TransportConfig,
)
from .domain.value_objects import LogLevelVO
from .types import LogLevel

try:
    import orjson  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - optional dependency
    orjson = None


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return default


def parse_int_range(value: str | None, default: int, min_value: int, max_value: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    if parsed < min_value or parsed > max_value:
        return default
    return parsed


def parse_float_range(value: str | None, default: float, min_value: float, max_value: float) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    if parsed < min_value or parsed > max_value:
        return default
    return parsed


def is_debug_enabled() -> bool:
    return parse_bool(os.getenv("LOGS_DEBUG"), False)


def is_silent_errors_enabled() -> bool:
    return parse_bool(os.getenv("LOGS_SILENT_ERRORS"), False)


def _internal_log(level: str, message: str, context: Any | None = None) -> None:
    if level == "debug" and not is_debug_enabled():
        return
    if level in {"warn", "error"} and is_silent_errors_enabled():
        return

    prefix = "[logs-interceptor]"
    payload = f"{prefix} {message}"
    if context is not None:
        payload = f"{payload} {safe_stringify(context)}"

    stream = sys.stderr if level in {"warn", "error"} else sys.stdout
    stream.write(payload + "\n")
    stream.flush()


def internal_debug(message: str, context: Any | None = None) -> None:
    _internal_log("debug", message, context)


def internal_warn(message: str, context: Any | None = None) -> None:
    _internal_log("warn", message, context)


def internal_error(message: str, context: Any | None = None) -> None:
    _internal_log("error", message, context)


def _safe_convert(value: Any, max_depth: int, depth: int, seen: set[int]) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if depth > max_depth:
        return "[Max Depth Reached]"

    if isinstance(value, Exception):
        return {
            "name": value.__class__.__name__,
            "message": str(value),
            "args": value.args,
        }

    if isinstance(value, datetime):
        return value.isoformat()

    obj_id = id(value)
    if obj_id in seen:
        return "[Circular Reference]"

    if isinstance(value, dict):
        seen.add(obj_id)
        return {
            str(k): _safe_convert(v, max_depth, depth + 1, seen)
            for k, v in value.items()
        }

    if isinstance(value, (list, tuple, set, frozenset)):
        seen.add(obj_id)
        return [_safe_convert(v, max_depth, depth + 1, seen) for v in value]

    if is_dataclass(value) and not isinstance(value, type):
        seen.add(obj_id)
        return _safe_convert(asdict(value), max_depth, depth + 1, seen)

    if hasattr(value, "__dict__"):
        seen.add(obj_id)
        return _safe_convert(value.__dict__, max_depth, depth + 1, seen)

    return str(value)


def safe_stringify(value: Any, max_depth: int = 10) -> str:
    try:
        converted = _safe_convert(value, max_depth=max_depth, depth=0, seen=set())
        if orjson is not None:
            return cast(bytes, orjson.dumps(converted)).decode("utf-8")
        return json.dumps(converted, separators=(",", ":"), ensure_ascii=False)
    except Exception as exc:  # pragma: no cover - hard-failure fallback
        return f"[Unserializable: {exc}]"


def detect_sensitive_data(text: str, patterns: Iterable[str]) -> bool:
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
    for pattern in compiled:
        if pattern.search(text):
            return True

    common_patterns = [
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"),
        re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/=]*", re.IGNORECASE),
        re.compile(r"Basic\s+[A-Za-z0-9+/=]*", re.IGNORECASE),
    ]
    return any(pattern.search(text) for pattern in common_patterns)


def sanitize_data(
    data: dict[str, Any],
    sensitive_patterns: Iterable[str],
    seen: set[int] | None = None,
) -> dict[str, Any]:
    if seen is None:
        seen = set()

    obj_id = id(data)
    if obj_id in seen:
        return {"_circular": "[REDACTED]"}
    seen.add(obj_id)

    compiled = [re.compile(p, re.IGNORECASE) for p in sensitive_patterns]
    sanitized: dict[str, Any] = {}

    for key, value in data.items():
        key_sensitive = any(pattern.search(key) for pattern in compiled)
        if key_sensitive:
            sanitized[key] = "[REDACTED]"
            continue

        if isinstance(value, str):
            sanitized[key] = "[REDACTED]" if detect_sensitive_data(value, sensitive_patterns) else value
            continue

        if isinstance(value, list):
            transformed: list[Any] = []
            for item in value:
                if isinstance(item, str):
                    transformed.append(
                        "[REDACTED]" if detect_sensitive_data(item, sensitive_patterns) else item
                    )
                elif isinstance(item, dict):
                    transformed.append(sanitize_data(item, sensitive_patterns, seen))
                else:
                    transformed.append(item)
            sanitized[key] = transformed
            continue

        if isinstance(value, dict):
            sanitized[key] = sanitize_data(value, sensitive_patterns, seen)
            continue

        sanitized[key] = value

    return sanitized


def hash_sensitive_data(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


def parse_labels(labels_string: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    if not labels_string:
        return labels

    try:
        if labels_string.startswith("{"):
            parsed = json.loads(labels_string)
            if isinstance(parsed, dict):
                return {str(k): str(v) for k, v in parsed.items()}
            return labels

        pairs = labels_string.split(",")
        for pair in pairs:
            key, *value_parts = pair.split("=")
            if key and value_parts:
                labels[key.strip()] = "=".join(value_parts).strip()
    except Exception as exc:
        internal_warn("Failed to parse labels from environment", exc)

    return labels


def should_sample(rate: float) -> bool:
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    return random.random() < rate


def should_sample_advanced(
    rate: float,
    strategy: str = "random",
    key: str | None = None,
) -> bool:
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False

    if strategy == "deterministic" and key:
        digest = hashlib.md5(key.encode("utf-8")).digest()  # noqa: S324 - deterministic sampling
        value = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
        return value < rate

    if strategy == "adaptive":
        try:
            load = os.getloadavg()[0]
            cpu_count = max(1, os.cpu_count() or 1)
            factor = min(1.0, load / cpu_count)
            adjusted = rate * (1 - factor * 0.5)
            return random.random() < adjusted
        except OSError:
            return random.random() < rate

    return random.random() < rate


def format_bytes(size: int) -> str:
    units = ["Bytes", "KB", "MB", "GB"]
    if size == 0:
        return "0 Bytes"
    index = 0
    value = float(size)
    while value >= 1024 and index < len(units) - 1:
        value /= 1024
        index += 1
    return f"{value:.2f} {units[index]}"


def calculate_compression_ratio(original: int, compressed: int) -> float:
    if original <= 0:
        return 0.0
    return round((1 - (compressed / original)) * 100, 2)


def _env_levels(value: str | None) -> list[LogLevel]:
    raw = value or "debug,info,warn,error,fatal"
    levels: list[LogLevel] = []
    for item in raw.split(","):
        normalized = item.strip().lower()
        if LogLevelVO.is_valid(normalized):
            levels.append(normalized)  # type: ignore[arg-type]
    return levels


def _merge_dataclass(env_obj: Any | None, user_obj: Any | None) -> Any | None:
    if env_obj is None and user_obj is None:
        return None
    if env_obj is None:
        return user_obj
    if user_obj is None:
        return env_obj

    if not (is_dataclass(env_obj) and is_dataclass(user_obj)):
        return user_obj

    merged_values: dict[str, Any] = {}
    for field_info in fields(env_obj):
        env_value = getattr(env_obj, field_info.name)
        user_value = getattr(user_obj, field_info.name)
        merged_values[field_info.name] = user_value if user_value is not None else env_value

    return cast(Any, env_obj.__class__)(**merged_values)


def load_config_from_env() -> LogsInterceptorConfig:
    if not parse_bool(os.getenv("LOGS_ENABLED"), True):
        return LogsInterceptorConfig(filter=FilterConfig(levels=[]))

    env = os.environ
    labels: dict[str, str] = {}
    for key, value in env.items():
        if key.startswith("LOGS_LABEL_") and value:
            labels[key[len("LOGS_LABEL_") :].lower()] = value

    compression_value_raw = (env.get("LOGS_COMPRESSION") or "gzip").lower()
    compression_value = compression_value_raw
    if compression_value not in {"none", "gzip", "brotli", "snappy"}:
        compression_value = "gzip"

    dlq_type_raw = (env.get("LOGS_DLQ_TYPE") or "memory").lower()
    dlq_type = dlq_type_raw
    if dlq_type not in {"memory", "file"}:
        dlq_type = "memory"

    cfg = LogsInterceptorConfig(
        transport=TransportConfig(
            url=env.get("LOGS_URL", ""),
            tenant_id=env.get("LOGS_TENANT", ""),
            auth_token=env.get("LOGS_TOKEN"),
            timeout=parse_int_range(env.get("LOGS_TIMEOUT"), 10_000, 0, 600_000),
            max_retries=parse_int_range(env.get("LOGS_MAX_RETRIES"), 3, 0, 20),
            retry_delay=parse_int_range(env.get("LOGS_RETRY_DELAY"), 1_000, 0, 120_000),
            compression=cast(CompressionType, compression_value),
            compression_level=parse_int_range(env.get("LOGS_COMPRESSION_LEVEL"), 6, 0, 11),
            compression_threshold=parse_int_range(
                env.get("LOGS_COMPRESSION_THRESHOLD"), 1024, 0, 2**31 - 1
            ),
            use_workers=parse_bool(env.get("LOGS_USE_WORKERS"), True),
            max_workers=parse_int_range(env.get("LOGS_MAX_WORKERS"), 2, 1, 64),
            enable_connection_pooling=parse_bool(env.get("LOGS_CONNECTION_POOLING"), True),
            max_sockets=parse_int_range(env.get("LOGS_MAX_SOCKETS"), 50, 1, 1024),
            worker_timeout=parse_int_range(env.get("LOGS_WORKER_TIMEOUT"), 30_000, 1000, 300_000),
        ),
        app_name=env.get("LOGS_APP_NAME", ""),
        version=env.get("LOGS_APP_VERSION", "1.0.0"),
        environment=env.get("LOGS_ENVIRONMENT") or env.get("ENVIRONMENT") or "production",
        labels=labels,
        buffer=BufferConfig(
            max_size=parse_int_range(env.get("LOGS_BUFFER_MAX_SIZE"), 100, 1, 1_000_000),
            flush_interval=parse_int_range(
                env.get("LOGS_BUFFER_FLUSH_INTERVAL"), 5000, 1, 300_000
            ),
            max_memory_mb=parse_int_range(env.get("LOGS_BUFFER_MAX_MEMORY_MB"), 50, 1, 32_768),
            max_age=parse_int_range(env.get("LOGS_BUFFER_MAX_AGE"), 30_000, 100, 86_400_000),
            auto_flush=parse_bool(env.get("LOGS_BUFFER_AUTO_FLUSH"), True),
        ),
        filter=FilterConfig(
            levels=_env_levels(env.get("LOGS_FILTER_LEVELS")),
            sampling_rate=parse_float_range(env.get("LOGS_FILTER_SAMPLING_RATE"), 1.0, 0.0, 1.0),
            sanitize=parse_bool(env.get("LOGS_FILTER_SANITIZE"), True),
            max_message_length=parse_int_range(
                env.get("LOGS_FILTER_MAX_MESSAGE_LENGTH"), 8192, 64, 1_000_000
            ),
        ),
        circuit_breaker=CircuitBreakerConfig(
            enabled=parse_bool(env.get("LOGS_CIRCUIT_BREAKER_ENABLED"), True),
            failure_threshold=parse_int_range(
                env.get("LOGS_CIRCUIT_BREAKER_FAILURE_THRESHOLD"), 50, 1, 100_000
            ),
            reset_timeout=parse_int_range(
                env.get("LOGS_CIRCUIT_BREAKER_RESET_TIMEOUT"), 30_000, 1000, 3_600_000
            ),
            half_open_requests=parse_int_range(
                env.get("LOGS_CIRCUIT_BREAKER_HALF_OPEN_REQUESTS"), 3, 1, 100
            ),
        ),
        dead_letter_queue=DeadLetterQueueConfig(
            enabled=parse_bool(env.get("LOGS_DLQ_ENABLED"), True),
            type=cast(DLQType, dlq_type),
            max_size=parse_int_range(env.get("LOGS_DLQ_MAX_SIZE"), 1000, 1, 1_000_000),
            max_retries=parse_int_range(env.get("LOGS_DLQ_MAX_RETRIES"), 3, 0, 100),
            base_path=env.get("LOGS_DLQ_BASE_PATH") or os.getcwd(),
            max_file_size_mb=10,
        ),
        performance=PerformanceConfig(
            use_workers=parse_bool(env.get("LOGS_USE_WORKERS"), True),
            max_concurrent_flushes=parse_int_range(
                env.get("LOGS_MAX_CONCURRENT_FLUSHES"), 3, 1, 256
            ),
            max_workers=parse_int_range(env.get("LOGS_MAX_WORKERS"), 2, 1, 64),
            compression_level=parse_int_range(env.get("LOGS_COMPRESSION_LEVEL"), 6, 0, 11),
            worker_timeout=parse_int_range(env.get("LOGS_WORKER_TIMEOUT"), 30_000, 1000, 300_000),
        ),
        integrations=IntegrationsConfig(),
        intercept_console=parse_bool(env.get("LOGS_INTERCEPT_CONSOLE"), False),
        preserve_original_console=parse_bool(env.get("LOGS_PRESERVE_ORIGINAL_CONSOLE"), True),
        enable_metrics=parse_bool(env.get("LOGS_ENABLE_METRICS"), True),
        enable_health_check=parse_bool(env.get("LOGS_ENABLE_HEALTH_CHECK"), True),
        debug=parse_bool(env.get("LOGS_DEBUG"), False),
        silent_errors=parse_bool(env.get("LOGS_SILENT_ERRORS"), False),
    )

    if not cfg.transport.url and not cfg.transport.tenant_id and not cfg.app_name:
        return LogsInterceptorConfig()

    return cfg


def merge_configs(user_config: LogsInterceptorConfig, env_config: LogsInterceptorConfig) -> LogsInterceptorConfig:
    return LogsInterceptorConfig(
        transport=_merge_dataclass(env_config.transport, user_config.transport)
        or TransportConfig(),
        app_name=user_config.app_name or env_config.app_name,
        version=user_config.version or env_config.version,
        environment=user_config.environment or env_config.environment,
        labels={**(env_config.labels or {}), **(user_config.labels or {})} or None,
        dynamic_labels={**(env_config.dynamic_labels or {}), **(user_config.dynamic_labels or {})}
        or None,
        buffer=_merge_dataclass(env_config.buffer, user_config.buffer),
        filter=_merge_dataclass(env_config.filter, user_config.filter),
        circuit_breaker=_merge_dataclass(env_config.circuit_breaker, user_config.circuit_breaker),
        integrations=_merge_dataclass(env_config.integrations, user_config.integrations),
        performance=_merge_dataclass(env_config.performance, user_config.performance),
        dead_letter_queue=_merge_dataclass(env_config.dead_letter_queue, user_config.dead_letter_queue),
        enable_metrics=user_config.enable_metrics
        if user_config.enable_metrics is not None
        else env_config.enable_metrics,
        enable_health_check=user_config.enable_health_check
        if user_config.enable_health_check is not None
        else env_config.enable_health_check,
        intercept_console=user_config.intercept_console
        if user_config.intercept_console is not None
        else env_config.intercept_console,
        preserve_original_console=user_config.preserve_original_console
        if user_config.preserve_original_console is not None
        else env_config.preserve_original_console,
        debug=user_config.debug if user_config.debug is not None else env_config.debug,
        silent_errors=user_config.silent_errors
        if user_config.silent_errors is not None
        else env_config.silent_errors,
    )


def create_correlation_id() -> str:
    return secrets.token_hex(16)


def extract_error_metadata(error: BaseException) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": error.__class__.__name__,
        "message": str(error),
    }
    for attr in ["code", "status_code", "errno", "path", "address", "port"]:
        if hasattr(error, attr):
            payload[attr] = getattr(error, attr)
    return payload


def parse_stack_trace(stack: str) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    pattern = re.compile(r"File \"(?P<file>.+?)\", line (?P<line>\d+), in (?P<func>.+)")
    for line in stack.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        frames.append(
            {
                "function": match.group("func"),
                "file": match.group("file"),
                "line": int(match.group("line")),
            }
        )
    return frames[:10]
