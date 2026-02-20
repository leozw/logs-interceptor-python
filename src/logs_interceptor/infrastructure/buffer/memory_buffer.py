from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime

from ...config import ResolvedBufferConfig
from ...domain.entities import LogEntryEntity
from ..memory.memory_tracker import MemoryTracker


class MemoryBuffer:
    def __init__(self, config: ResolvedBufferConfig) -> None:
        self._config = config
        self._entries: list[LogEntryEntity] = []
        self._last_flush_time = time.time()
        self._flush_timer: threading.Timer | None = None
        self._memory_tracker = MemoryTracker()
        self._flush_callback: Callable[[], None] | None = None
        self._dropped_entries = 0
        self._destroyed = False
        self._lock = threading.RLock()

        if self._config.auto_flush:
            self._schedule_flush()

    def set_flush_callback(self, callback: Callable[[], None]) -> None:
        self._flush_callback = callback

    def add(self, entry: LogEntryEntity) -> None:
        with self._lock:
            if self._destroyed:
                return

            self._entries.append(entry)
            self._memory_tracker.add_entry(entry)

            self._enforce_max_size()

            if self._memory_tracker.get_total_size_mb() > self._config.max_memory_mb:
                self._remove_old_entries()
                self._enforce_max_size()

            if self._config.auto_flush:
                self._schedule_flush()

            if len(self._entries) >= self._config.max_size and self._config.auto_flush:
                self._trigger_immediate_flush()

    def flush(self) -> list[LogEntryEntity]:
        with self._lock:
            if self._flush_timer:
                self._flush_timer.cancel()
                self._flush_timer = None

            flushed = list(self._entries)
            self._memory_tracker.remove_entries(flushed)
            self._entries.clear()
            self._last_flush_time = time.time()

            if self._config.auto_flush and not self._destroyed:
                self._schedule_flush()

            return flushed

    def peek(self) -> list[LogEntryEntity]:
        with self._lock:
            return list(self._entries)

    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    def is_full(self) -> bool:
        with self._lock:
            return len(self._entries) >= self._config.max_size

    def should_flush(self) -> bool:
        with self._lock:
            elapsed_ms = int((time.time() - self._last_flush_time) * 1000)
            return len(self._entries) >= self._config.max_size or (
                self._config.auto_flush and elapsed_ms >= self._config.flush_interval
            )

    def clear(self) -> None:
        with self._lock:
            self._memory_tracker.remove_entries(self._entries)
            self._entries.clear()
            if self._flush_timer:
                self._flush_timer.cancel()
                self._flush_timer = None

    def destroy(self) -> None:
        with self._lock:
            self._destroyed = True
            if self._flush_timer:
                self._flush_timer.cancel()
                self._flush_timer = None
            self.clear()
            self._memory_tracker.reset()
            self._flush_callback = None

    def get_metrics(self) -> dict[str, float | int | None]:
        with self._lock:
            oldest = self._entries[0].timestamp if self._entries else None
            newest = self._entries[-1].timestamp if self._entries else None
            oldest_ts = self._to_timestamp(oldest)
            newest_ts = self._to_timestamp(newest)
            return {
                "size": len(self._entries),
                "max_size": self._config.max_size,
                "oldest_entry": oldest_ts,
                "newest_entry": newest_ts,
                "memory_usage_mb": self._memory_tracker.get_total_size_mb(),
                "dropped_entries": self._dropped_entries,
            }

    def _enforce_max_size(self) -> None:
        if len(self._entries) <= self._config.max_size:
            return
        remove_count = len(self._entries) - self._config.max_size
        self._drop_oldest(remove_count)

    def _drop_oldest(self, count: int) -> None:
        if count <= 0 or not self._entries:
            return
        dropped = self._entries[:count]
        self._entries = self._entries[count:]
        self._memory_tracker.remove_entries(dropped)
        self._dropped_entries += len(dropped)

    def _trigger_immediate_flush(self) -> None:
        if self._destroyed or self._flush_callback is None:
            return
        callback = self._flush_callback
        timer = threading.Timer(0.001, callback)
        timer.daemon = True
        timer.start()

    def _remove_old_entries(self) -> None:
        now = time.time()
        max_age_s = self._config.max_age / 1000

        kept: list[LogEntryEntity] = []
        removed: list[LogEntryEntity] = []
        for entry in self._entries:
            ts = self._to_timestamp(entry.timestamp)
            if ts is None or (now - ts) < max_age_s:
                kept.append(entry)
            else:
                removed.append(entry)

        self._entries = kept
        if removed:
            self._memory_tracker.remove_entries(removed)
            self._dropped_entries += len(removed)

        if self._memory_tracker.get_total_size_mb() > self._config.max_memory_mb and self._entries:
            remove_count = max(1, len(self._entries) // 10)
            self._drop_oldest(remove_count)

    def _schedule_flush(self) -> None:
        if self._destroyed or self._flush_timer is not None:
            return

        def _on_timer() -> None:
            with self._lock:
                self._flush_timer = None
                if self._destroyed:
                    return
                if self._flush_callback and self._entries:
                    self._flush_callback()

        self._flush_timer = threading.Timer(self._config.flush_interval / 1000, _on_timer)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    @staticmethod
    def _to_timestamp(value: str | None) -> float | None:
        if value is None:
            return None
        try:
            normalized = value.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized).timestamp()
        except Exception:
            return None
