from __future__ import annotations

import time

from logs_interceptor.config import ResolvedCircuitBreakerConfig
from logs_interceptor.infrastructure.circuit_breaker import CircuitBreaker


def test_circuit_breaker_half_open_to_closed() -> None:
    breaker = CircuitBreaker(
        ResolvedCircuitBreakerConfig(
            enabled=True,
            failure_threshold=1,
            reset_timeout=20,
            half_open_requests=1,
        )
    )

    try:
        breaker.execute(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    except RuntimeError:
        pass

    assert breaker.get_state()["state"] == "open"

    time.sleep(0.03)
    assert breaker.execute(lambda: "ok") == "ok"
    assert breaker.get_state()["state"] == "closed"


def test_circuit_breaker_reset() -> None:
    breaker = CircuitBreaker(
        ResolvedCircuitBreakerConfig(
            enabled=True,
            failure_threshold=1,
            reset_timeout=1000,
            half_open_requests=1,
        )
    )

    try:
        breaker.execute(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    except RuntimeError:
        pass

    assert breaker.get_state()["state"] == "open"
    breaker.reset()
    assert breaker.get_state()["state"] == "closed"
