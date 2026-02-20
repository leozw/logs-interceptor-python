from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from ...domain.entities import LogEntryEntity
from ...domain.interfaces import ICircuitBreaker, IDeadLetterQueue, ILogTransport
from ...types import TransportHealth, TransportMetrics
from ...utils import internal_warn


@dataclass(slots=True)
class ResilientTransportConfig:
    max_retries: int = 3
    retry_delay: int = 1000


class ResilientTransport:
    def __init__(
        self,
        transport: ILogTransport,
        config: ResilientTransportConfig,
        circuit_breaker: ICircuitBreaker | None = None,
        dlq: IDeadLetterQueue | None = None,
    ) -> None:
        self._transport = transport
        self._config = config
        self._circuit_breaker = circuit_breaker
        self._dlq = dlq
        self._metrics: TransportMetrics = {
            "total_sends": 0,
            "successful_sends": 0,
            "failed_sends": 0,
            "avg_latency": 0.0,
            "retry_attempts": 0,
            "retried_requests": 0,
            "dlq_dropped_entries": 0,
        }
        self._last_dlq_warning = 0.0

    def send(self, entries: list[LogEntryEntity]) -> None:
        if not entries:
            return

        self._metrics["total_sends"] = self._metrics.get("total_sends", 0) + 1

        def operation() -> None:
            self._retry_operation(lambda: self._transport.send(entries))

        try:
            if self._circuit_breaker is not None:
                self._circuit_breaker.execute(operation)
            else:
                operation()
            self._metrics["successful_sends"] = self._metrics.get("successful_sends", 0) + 1
        except Exception as exc:
            self._metrics["failed_sends"] = self._metrics.get("failed_sends", 0) + 1
            self._enqueue_dlq(entries, exc)
            raise

    def _enqueue_dlq(self, entries: list[LogEntryEntity], error: Exception) -> None:
        if self._dlq is None:
            return
        try:
            result = self._dlq.add_batch(entries, str(error))
            self._metrics["dlq_dropped_entries"] = self._metrics.get("dlq_dropped_entries", 0) + result.get(
                "dropped", 0
            )
        except Exception as dlq_error:
            now = time.time()
            if now - self._last_dlq_warning > 10:
                self._last_dlq_warning = now
                internal_warn("Failed to enqueue logs to DLQ", dlq_error)

    def _retry_operation(self, operation: Callable[[], None]) -> None:
        max_retries = self._config.max_retries
        delay = self._config.retry_delay
        total_attempts = max_retries + 1
        request_retried = False

        for attempt in range(total_attempts):
            try:
                operation()
                return
            except Exception as exc:
                should_retry = attempt < total_attempts - 1 and self._is_retryable_error(exc)
                if not should_retry:
                    raise

                if not request_retried:
                    request_retried = True
                    self._metrics["retried_requests"] = self._metrics.get("retried_requests", 0) + 1
                self._metrics["retry_attempts"] = self._metrics.get("retry_attempts", 0) + 1

                base_delay = delay * (2**attempt)
                jitter = random.randint(0, 250)
                time.sleep((base_delay + jitter) / 1000)

    @staticmethod
    def _is_retryable_error(error: Exception) -> bool:
        retryable = getattr(error, "retryable", None)
        if isinstance(retryable, bool):
            return retryable

        status_code = getattr(error, "status_code", None)
        if isinstance(status_code, int):
            return status_code == 429 or status_code >= 500

        message = str(error).lower()
        markers = [
            "timeout",
            "socket",
            "connect",
            "network",
            "429",
            "502",
            "503",
            "504",
        ]
        return any(marker in message for marker in markers)

    def is_available(self) -> bool:
        return self._transport.is_available()

    def get_health(self) -> TransportHealth:
        if self._circuit_breaker is not None:
            state = self._circuit_breaker.get_state()
            state_name = state.get("state")
            if state_name == "open":
                return {
                    "healthy": False,
                    "consecutive_failures": int(state.get("failures", 0)),
                    "error_message": f"CircuitBreaker is OPEN. Last error: {state.get('last_error')}",
                }
            if state_name == "half-open":
                return {
                    "healthy": True,
                    "consecutive_failures": int(state.get("failures", 0)),
                    "error_message": "CircuitBreaker is HALF_OPEN",
                }

        return self._transport.get_health()

    def get_metrics(self) -> TransportMetrics | None:
        base = self._transport.get_metrics()
        if base is None:
            return cast(TransportMetrics, dict(self._metrics))

        merged = dict(base)
        merged["retry_attempts"] = base.get("retry_attempts", 0) + self._metrics.get("retry_attempts", 0)
        merged["retried_requests"] = base.get("retried_requests", 0) + self._metrics.get("retried_requests", 0)
        merged["dlq_dropped_entries"] = base.get("dlq_dropped_entries", 0) + self._metrics.get(
            "dlq_dropped_entries", 0
        )
        return cast(TransportMetrics, merged)

    def destroy(self) -> None:
        self._transport.destroy()
