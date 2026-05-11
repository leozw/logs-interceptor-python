from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

DEFAULT_EXCLUDED_LOGGER_PREFIXES = (
    "httpcore",
    "httpx",
    "urllib3",
    "hpack",
    "h2",
    "h11",
    "opentelemetry",
    "logs_interceptor",
    "elven_unified_observability",
)


def normalize_excluded_logger_prefixes(prefixes: Iterable[str] | None = None) -> tuple[str, ...]:
    values = list(prefixes) if prefixes is not None else list(DEFAULT_EXCLUDED_LOGGER_PREFIXES)
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        value = str(item).strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return tuple(normalized)


def should_drop_log_record(
    *,
    logger_name: str | None = None,
    module_name: str | None = None,
    extra: Mapping[str, Any] | None = None,
    exclude_prefixes: Iterable[str] | None = None,
) -> bool:
    prefixes = normalize_excluded_logger_prefixes(exclude_prefixes)
    if not prefixes:
        return False

    normalized_logger_name = str(logger_name or "").strip().lower()
    normalized_module_name = str(module_name or "").strip().lower()
    normalized_extra_logger_name = ""
    if isinstance(extra, Mapping):
        normalized_extra_logger_name = str(extra.get("logger_name") or "").strip().lower()

    for prefix in prefixes:
        if (
            normalized_logger_name.startswith(prefix)
            or normalized_module_name.startswith(prefix)
            or normalized_extra_logger_name.startswith(prefix)
        ):
            return True
    return False
