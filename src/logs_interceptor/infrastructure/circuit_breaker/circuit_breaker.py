from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TypeVar

from ...config import ResolvedCircuitBreakerConfig

T = TypeVar("T")


class CircuitBreaker:
    def __init__(self, config: ResolvedCircuitBreakerConfig) -> None:
        self._config = config
        self._state: str = "closed"
        self._failures = 0
        self._success_count = 0
        self._half_open_in_flight = 0
        self._last_failure: float | None = None
        self._next_attempt: float | None = None
        self._last_error: str | None = None
        self._lock = threading.Lock()

    def execute(self, operation: Callable[[], T]) -> T:
        if not self._config.enabled:
            return operation()

        with self._lock:
            if self._is_open_locked():
                raise RuntimeError("Circuit breaker is open")
            counted_as_probe = self._state == "half-open"
            if counted_as_probe and self._half_open_in_flight >= self._config.half_open_requests:
                raise RuntimeError("Circuit breaker half-open probe limit reached")
            if counted_as_probe:
                self._half_open_in_flight += 1

        try:
            result = operation()
            self.record_success()
            return result
        except Exception as exc:
            self.record_failure(exc)
            raise
        finally:
            if self._state == "half-open":
                with self._lock:
                    self._half_open_in_flight = max(0, self._half_open_in_flight - 1)

    def record_success(self) -> None:
        with self._lock:
            if self._state == "half-open":
                self._success_count += 1
                if self._success_count >= self._config.half_open_requests:
                    self._state = "closed"
                    self._failures = 0
                    self._success_count = 0
                    self._half_open_in_flight = 0
                    self._last_error = None
                return

            if self._state == "closed":
                self._failures = 0
                self._last_error = None

    def record_failure(self, error: Exception | None = None) -> None:
        with self._lock:
            self._failures += 1
            self._last_failure = time.time()
            if error is not None:
                self._last_error = str(error)

            if self._failures >= self._config.failure_threshold or self._state == "half-open":
                self._state = "open"
                self._success_count = 0
                self._half_open_in_flight = 0
                self._next_attempt = time.time() + (self._config.reset_timeout / 1000)

    def get_state(self) -> dict[str, float | int | str | None]:
        with self._lock:
            return {
                "state": self._state,
                "failures": self._failures,
                "success_count": self._success_count,
                "half_open_in_flight": self._half_open_in_flight,
                "last_failure": self._last_failure,
                "next_attempt": self._next_attempt,
                "last_error": self._last_error,
            }

    def reset(self) -> None:
        with self._lock:
            self._state = "closed"
            self._failures = 0
            self._success_count = 0
            self._half_open_in_flight = 0
            self._last_failure = None
            self._next_attempt = None
            self._last_error = None

    def _is_open_locked(self) -> bool:
        if self._state != "open":
            return False
        now = time.time()
        if self._next_attempt and now >= self._next_attempt:
            self._state = "half-open"
            self._success_count = 0
            self._half_open_in_flight = 0
            return False
        return True
