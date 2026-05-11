from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_SUPPRESSION_DEPTH: ContextVar[int] = ContextVar(
    "logs_interceptor_internal_capture_suppression_depth",
    default=0,
)


@contextmanager
def suppress_internal_log_capture() -> Iterator[None]:
    token = _SUPPRESSION_DEPTH.set(_SUPPRESSION_DEPTH.get() + 1)
    try:
        yield
    finally:
        _SUPPRESSION_DEPTH.reset(token)


def is_internal_log_capture_suppressed() -> bool:
    return _SUPPRESSION_DEPTH.get() > 0
