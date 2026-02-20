from __future__ import annotations

import asyncio
import random
import time

from logs_interceptor import destroy, init, logger


def generate_sync_logs() -> None:
    logger.debug("smoke debug", {"feature": "smoke-test"})
    logger.info("smoke info", {"status": "starting"})
    logger.warn("smoke warning", {"hint": "this is expected in test"})
    logger.track_event("smoke_event", {"source": "manual-test", "batch": 1})

    try:
        _ = 10 / 0
    except Exception as exc:
        logger.error("captured exception during smoke", {"error": str(exc), "retryable": False})

    for idx in range(20):
        logger.info(
            "bulk log",
            {
                "idx": idx,
                "value": random.randint(1, 100),
                "ts": time.time(),
            },
        )


def generate_context_logs() -> None:
    def _sync_job() -> None:
        logger.info("inside sync context", {"path": "/sync"})
        print("console print intercepted from sync context")

    logger.with_context(
        {
            "request_id": "smoke-sync-req-1",
            "trace_id": "smoke-sync-trace-1",
            "span_id": "smoke-sync-span-1",
        },
        _sync_job,
    )


async def generate_async_context_logs() -> None:
    async def _async_job() -> None:
        logger.info("inside async context", {"path": "/async"})
        await asyncio.sleep(0.05)
        logger.info("async work completed", {"ok": True})

    await logger.with_context_async(
        {
            "request_id": "smoke-async-req-1",
            "trace_id": "smoke-async-trace-1",
            "span_id": "smoke-async-span-1",
        },
        _async_job,
    )


def main() -> None:
    init()
    print("logs-interceptor initialized via env")

    generate_sync_logs()
    generate_context_logs()
    asyncio.run(generate_async_context_logs())

    logger.flush()

    metrics = logger.get_metrics()
    health = logger.get_health()

    print(
        {
            "processed": metrics.get("logs_processed"),
            "dropped": metrics.get("logs_dropped"),
            "flush_count": metrics.get("flush_count"),
            "errors": metrics.get("error_count"),
        }
    )
    print({"health": health})

    destroy()


if __name__ == "__main__":
    main()
