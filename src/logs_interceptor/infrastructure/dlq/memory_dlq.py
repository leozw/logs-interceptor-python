from __future__ import annotations

import time
from dataclasses import dataclass

from ...domain.entities import LogEntryEntity


@dataclass(slots=True)
class _DLQEntry:
    entry: LogEntryEntity
    reason: str
    timestamp: float
    retry_count: int


class MemoryDeadLetterQueue:
    def __init__(self, max_size: int = 1000) -> None:
        self._queue: list[_DLQEntry] = []
        self._max_size = max_size
        self._dropped_entries = 0

    def add(self, entry: LogEntryEntity, reason: str) -> dict[str, int]:
        return self.add_batch([entry], reason)

    def add_batch(self, entries: list[LogEntryEntity], reason: str) -> dict[str, int]:
        dropped = 0
        timestamp = time.time()
        for entry in entries:
            if len(self._queue) >= self._max_size:
                self._queue.pop(0)
                self._dropped_entries += 1
                dropped += 1
            self._queue.append(_DLQEntry(entry=entry, reason=reason, timestamp=timestamp, retry_count=0))
        return {"added": len(entries), "dropped": dropped}

    def flush(self) -> int:
        count = len(self._queue)
        self._queue.clear()
        return count

    def size(self) -> int:
        return len(self._queue)

    def clear(self) -> None:
        self._queue.clear()

    def get_entries(self, limit: int = 100) -> list[dict[str, object]]:
        return [
            {
                "entry": item.entry,
                "reason": item.reason,
                "timestamp": item.timestamp,
            }
            for item in self._queue[:limit]
        ]

    def get_stats(self) -> dict[str, int]:
        return {"size": len(self._queue), "dropped_entries": self._dropped_entries}
