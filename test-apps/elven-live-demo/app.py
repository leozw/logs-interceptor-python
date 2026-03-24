from __future__ import annotations

import asyncio
import random
import time

from logs_interceptor import destroy, init, logger


def emit_startup_logs() -> None:
    logger.info("demo app started", {"component": "startup"})
    logger.track_event("demo_started", {"source": "local-run", "at": time.time()})


def emit_business_logs() -> None:
    for idx in range(10):
        logger.info(
            "processing item",
            {
                "idx": idx,
                "value": random.randint(100, 999),
                "duration_ms": round(random.uniform(5, 30), 2),
            },
        )

    logger.warn("slow dependency detected", {"dependency": "inventory-service", "latency_ms": 187})

    try:
        raise RuntimeError("simulated business exception")
    except RuntimeError as exc:
        logger.error(
            "handled domain error",
            {
                "error": str(exc),
                "kind": "business",
            },
        )


def emit_sync_context_logs() -> None:
    def _run() -> None:
        logger.info("sync request started", {"method": "GET", "path": "/products"})
        print("plain print still works and is intercepted")

    logger.with_context(
        {
            "request_id": "demo-sync-request-1",
            "trace_id": "demo-sync-trace-1",
            "span_id": "demo-sync-span-1",
        },
        _run,
    )


async def emit_async_context_logs() -> None:
    async def _run() -> None:
        logger.info("async job started", {"job": "catalog-refresh"})
        await asyncio.sleep(0.05)
        logger.track_event("catalog_refresh_finished", {"ok": True})

    await logger.with_context_async(
        {
            "request_id": "demo-async-request-1",
            "trace_id": "demo-async-trace-1",
            "span_id": "demo-async-span-1",
        },
        _run,
    )


def print_runtime_summary() -> None:
    metrics = logger.get_metrics()
    health = logger.get_health()
    print(
        {
            "processed": metrics.get("logs_processed"),
            "dropped": metrics.get("logs_dropped"),
            "flush_count": metrics.get("flush_count"),
            "error_count": metrics.get("error_count"),
        }
    )
    print({"health": health})


def main() -> None:
    init()
    emit_startup_logs()
    emit_business_logs()
    emit_sync_context_logs()
    asyncio.run(emit_async_context_logs())
    logger.flush()
    print_runtime_summary()
    destroy()


if __name__ == "__main__":
    main()
