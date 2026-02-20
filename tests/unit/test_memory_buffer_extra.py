from __future__ import annotations

import threading
import time

from logs_interceptor.config import ResolvedBufferConfig
from logs_interceptor.domain.entities import LogEntryEntity
from logs_interceptor.infrastructure.buffer import MemoryBuffer


def _entry(entry_id: str, ts: str) -> LogEntryEntity:
    return LogEntryEntity(entry_id, ts, "info", f"message-{entry_id}")


def _buffer(
    *,
    max_size: int = 10,
    flush_interval: int = 1000,
    max_age: int = 10_000,
    auto_flush: bool = False,
    max_memory_mb: int = 10,
) -> MemoryBuffer:
    return MemoryBuffer(
        ResolvedBufferConfig(
            max_size=max_size,
            flush_interval=flush_interval,
            max_age=max_age,
            auto_flush=auto_flush,
            max_memory_mb=max_memory_mb,
        )
    )


def test_buffer_flush_callback_on_size_limit() -> None:
    event = threading.Event()
    buffer = _buffer(max_size=1, auto_flush=True)
    buffer.set_flush_callback(event.set)

    buffer.add(_entry("1", "2026-01-01T00:00:00+00:00"))
    assert event.wait(timeout=1)


def test_buffer_should_flush_by_time() -> None:
    buffer = _buffer(max_size=100, flush_interval=5, auto_flush=True)
    buffer.add(_entry("1", "2026-01-01T00:00:00+00:00"))
    time.sleep(0.01)
    assert buffer.should_flush() is True


def test_buffer_destroy_clears_resources() -> None:
    buffer = _buffer()
    buffer.add(_entry("1", "2026-01-01T00:00:00+00:00"))
    assert buffer.size() == 1
    buffer.destroy()
    assert buffer.size() == 0


def test_buffer_add_ignored_after_destroy() -> None:
    buffer = _buffer()
    buffer.destroy()
    buffer.add(_entry("1", "2026-01-01T00:00:00+00:00"))
    assert buffer.size() == 0


def test_buffer_memory_pressure_and_timestamp_branches() -> None:
    # max_memory_mb=0 forces memory-pressure handling path.
    buffer = _buffer(max_age=1, max_memory_mb=0)

    # Old entry is removed by age.
    buffer.add(_entry("old", "2000-01-01T00:00:00+00:00"))

    # Invalid timestamp is treated as unknown age and may be dropped by pressure.
    buffer.add(_entry("bad-ts", "invalid-ts"))

    metrics = buffer.get_metrics()
    assert metrics["dropped_entries"] >= 1
    assert buffer.size() >= 0
    assert MemoryBuffer._to_timestamp(None) is None
    assert MemoryBuffer._to_timestamp("invalid") is None


def test_buffer_private_guard_paths() -> None:
    buffer = _buffer()
    buffer._drop_oldest(0)
    buffer._trigger_immediate_flush()  # no callback set
    buffer.destroy()
    buffer._trigger_immediate_flush()  # destroyed branch
    assert buffer.size() == 0


def test_buffer_is_full_and_clear_cancels_timer() -> None:
    buffer = _buffer(max_size=1, flush_interval=200, auto_flush=True)
    buffer.add(_entry("1", "2026-01-01T00:00:00+00:00"))
    assert buffer.is_full() is True
    assert buffer._flush_timer is not None
    buffer.clear()
    assert buffer._flush_timer is None


def test_schedule_flush_callback_runs_with_entries() -> None:
    event = threading.Event()
    buffer = _buffer(flush_interval=5, auto_flush=True)
    buffer.set_flush_callback(event.set)
    buffer.add(_entry("1", "2026-01-01T00:00:00+00:00"))
    assert event.wait(timeout=1)
    buffer.destroy()


def test_schedule_flush_destroyed_guard_inside_timer() -> None:
    event = threading.Event()
    buffer = _buffer(flush_interval=40, auto_flush=False)
    buffer.set_flush_callback(event.set)
    buffer.add(_entry("1", "2026-01-01T00:00:00+00:00"))
    buffer._schedule_flush()
    buffer._destroyed = True
    time.sleep(0.06)
    assert event.is_set() is False
    buffer.clear()
