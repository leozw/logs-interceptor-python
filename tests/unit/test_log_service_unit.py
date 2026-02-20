from __future__ import annotations

import asyncio

import logs_interceptor.application.log_service as log_service_module
from logs_interceptor.application.log_service import LogService
from logs_interceptor.domain.entities import LogEntryEntity


class _Filter:
    def __init__(self, enabled: bool = True, process: bool = True) -> None:
        self.enabled = enabled
        self.process = process

    def is_level_enabled(self, level):
        return self.enabled

    def should_process(self, entry):
        return self.process

    def filter(self, entry):
        return entry


class _Buffer:
    def __init__(self) -> None:
        self.entries: list[LogEntryEntity] = []
        self.callback = None

    def set_flush_callback(self, callback):
        self.callback = callback

    def add(self, entry):
        self.entries.append(entry)

    def flush(self):
        items = list(self.entries)
        self.entries.clear()
        return items

    def peek(self):
        return list(self.entries)

    def size(self):
        return len(self.entries)

    def is_full(self):
        return False

    def should_flush(self):
        return False

    def clear(self):
        self.entries.clear()

    def destroy(self):
        self.entries.clear()

    def get_metrics(self):
        return {
            "size": len(self.entries),
            "max_size": 100,
            "oldest_entry": None,
            "newest_entry": None,
            "memory_usage_mb": 0,
            "dropped_entries": 0,
        }


class _Transport:
    def __init__(self, fail: bool = False, half_open: bool = False) -> None:
        self.fail = fail
        self.sent = 0
        self.half_open = half_open
        self.destroyed = False

    def send(self, entries):
        if self.fail:
            raise RuntimeError("send failed")
        self.sent += len(entries)

    def is_available(self):
        return True

    def get_health(self):
        if self.half_open:
            return {
                "healthy": True,
                "consecutive_failures": 0,
                "error_message": "CircuitBreaker is HALF_OPEN",
            }
        return {"healthy": not self.fail, "consecutive_failures": 0}

    def get_metrics(self):
        return {"dlq_dropped_entries": 0}

    def destroy(self):
        self.destroyed = True
        return None


class _Context:
    def __init__(self) -> None:
        self.store = {}

    def get_context(self):
        return dict(self.store)

    def run_with_context(self, context, fn):
        previous = dict(self.store)
        self.store.update(context)
        try:
            return fn()
        finally:
            self.store = previous

    async def run_with_context_async(self, context, fn):
        previous = dict(self.store)
        self.store.update(context)
        try:
            result = fn()
            if hasattr(result, "__await__"):
                return await result
            return result
        finally:
            self.store = previous

    def set(self, key, value):
        self.store[key] = value

    def get(self, key, default=None):
        return self.store.get(key, default)

    def clear(self):
        self.store = {}


def _service(
    fail: bool = False,
    enabled: bool = True,
    process: bool = True,
    half_open: bool = False,
) -> LogService:
    return LogService(
        _Filter(enabled=enabled, process=process),
        _Buffer(),
        _Transport(fail=fail, half_open=half_open),
        _Context(),
        {
            "app_name": "app",
            "version": "1.0.0",
            "environment": "test",
            "labels": {},
            "dynamic_labels": {},
            "enable_metrics": True,
            "max_concurrent_flushes": 2,
        },
    )


class _BadSetCallbackBuffer(_Buffer):
    def set_flush_callback(self, callback):
        raise RuntimeError("cannot bind callback")


class _MutatingFilter(_Filter):
    def filter(self, entry):
        return LogEntryEntity(
            id=entry.id,
            timestamp=entry.timestamp,
            level=entry.level,
            message=f"{entry.message}-mutated",
            context={"mutated": True},
            trace_id=entry.trace_id,
            span_id=entry.span_id,
            request_id=entry.request_id,
            labels=entry.labels,
            metadata=entry.metadata,
        )


class _BadDestroyBuffer(_Buffer):
    def destroy(self):
        raise RuntimeError("buffer destroy failed")


class _BadDestroyTransport(_Transport):
    def destroy(self):
        raise RuntimeError("transport destroy failed")


def test_log_service_processes_and_flushes() -> None:
    service = _service()
    service.info("hello", {"k": "v"})
    assert service.get_metrics()["logs_processed"] == 1

    service.flush()
    assert service.get_metrics()["flush_count"] >= 1


def test_log_service_drops_when_filter_blocks() -> None:
    service = _service(enabled=False)
    service.info("hello")
    assert service.get_metrics()["logs_processed"] == 0


def test_log_service_health_on_transport_failure() -> None:
    service = _service(fail=True)
    service.info("hello")
    try:
        service.flush()
    except RuntimeError:
        pass

    health = service.get_health()
    assert health["healthy"] is False


def test_log_service_context_apis() -> None:
    service = _service()

    def _fn() -> str:
        service.info("inside")
        return "ok"

    result = service.with_context({"request_id": "r1"}, _fn)
    assert result == "ok"


def test_log_service_all_levels_and_process_drop() -> None:
    service = _service(process=False)
    service.debug("d")
    service.warn("w")
    service.error("e")
    service.fatal("f")
    metrics = service.get_metrics()
    assert metrics["logs_processed"] == 0
    assert metrics["logs_dropped"] >= 1


def test_log_service_half_open_health() -> None:
    service = _service(half_open=True)
    service.info("hello")
    health = service.get_health()
    assert health["circuit_breaker_state"] == "half-open"


def test_log_service_destroy_and_async_wrappers() -> None:
    service = _service()
    service.info("hello")

    asyncio.run(service.aflush())
    asyncio.run(service.adestroy())

    # second destroy is idempotent and should not fail
    service.destroy()


def test_log_service_init_ignores_set_callback_failure() -> None:
    service = LogService(
        _Filter(),
        _BadSetCallbackBuffer(),
        _Transport(),
        _Context(),
        {
            "app_name": "app",
            "version": "1.0.0",
            "environment": "test",
            "labels": {},
            "dynamic_labels": {},
            "enable_metrics": True,
            "max_concurrent_flushes": 1,
        },
    )
    service.info("hello")
    assert service.get_metrics()["logs_processed"] == 1


def test_log_service_fatal_swallows_flush_error() -> None:
    service = _service(fail=True)
    service.fatal("boom")
    assert service.get_metrics()["logs_processed"] == 1


def test_log_service_track_event_and_sanitized_metric() -> None:
    service = LogService(
        _MutatingFilter(),
        _Buffer(),
        _Transport(),
        _Context(),
        {
            "app_name": "app",
            "version": "1.0.0",
            "environment": "test",
            "labels": {},
            "dynamic_labels": {},
            "enable_metrics": True,
            "max_concurrent_flushes": 1,
        },
    )
    service.track_event("purchase", {"amount": 10})
    metrics = service.get_metrics()
    assert metrics["logs_processed"] == 1
    assert metrics["logs_sanitized"] == 1


def test_log_service_dynamic_labels_and_otel_fallback(monkeypatch) -> None:
    service = _service()
    service._config["dynamic_labels"] = {
        "trace_id": lambda: "trace-123",
        "span_id": lambda: "span-123",
        "request_id": lambda: "req-123",
        "bad_provider": lambda: (_ for _ in ()).throw(RuntimeError("bad")),
    }

    class _BadOtel:
        @staticmethod
        def get_current_span():
            raise RuntimeError("otel down")

    monkeypatch.setattr(log_service_module, "otel_trace", _BadOtel())
    entry = service._create_log_entry("info", "hello", None)
    assert entry.trace_id == "trace-123"
    assert entry.span_id == "span-123"
    assert entry.request_id == "req-123"


def test_log_service_destroyed_log_and_flush_noop() -> None:
    service = _service()
    service.destroy()
    before = service.get_metrics()["logs_dropped"]
    service.info("after-destroy")
    service.flush()
    assert service.get_metrics()["logs_dropped"] >= before + 1


def test_log_service_destroy_warns_when_components_fail(monkeypatch) -> None:
    warnings: list[str] = []
    monkeypatch.setattr(log_service_module, "internal_warn", lambda message, context=None: warnings.append(message))
    service = LogService(
        _Filter(),
        _BadDestroyBuffer(),
        _BadDestroyTransport(),
        _Context(),
        {
            "app_name": "app",
            "version": "1.0.0",
            "environment": "test",
            "labels": {},
            "dynamic_labels": {},
            "enable_metrics": True,
            "max_concurrent_flushes": 1,
        },
    )
    service.destroy()
    assert any("buffer" in message.lower() for message in warnings)
    assert any("transport" in message.lower() for message in warnings)


def test_log_service_metrics_disabled_and_resource_fallback(monkeypatch) -> None:
    service = _service()
    service._config["enable_metrics"] = False
    service.info("hello")
    no_metrics = service.get_metrics()
    assert no_metrics["logs_processed"] == 1

    class _BadResource:
        RUSAGE_SELF = 0

        @staticmethod
        def getrusage(scope: int):
            raise RuntimeError("resource not available")

    service._config["enable_metrics"] = True
    monkeypatch.setattr(log_service_module, "resource", _BadResource())
    service._update_metrics(force=True)
    assert service.get_metrics()["memory_usage"] == 0.0
