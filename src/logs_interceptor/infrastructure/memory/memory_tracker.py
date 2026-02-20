from __future__ import annotations

from dataclasses import dataclass

from ...domain.entities import LogEntryEntity


@dataclass(slots=True)
class MemoryStats:
    total_bytes: int
    total_mb: float
    entry_count: int
    avg_entry_size: float


class MemoryTracker:
    def __init__(self) -> None:
        self._total_size = 0
        self._entry_sizes: dict[int, int] = {}
        self._entry_count = 0

    def add_entry(self, entry: LogEntryEntity) -> None:
        size = self._estimate_size(entry)
        self._entry_sizes[id(entry)] = size
        self._total_size += size
        self._entry_count += 1

    def remove_entry(self, entry: LogEntryEntity) -> None:
        key = id(entry)
        size = self._entry_sizes.pop(key, None)
        if size is None:
            return
        self._total_size -= size
        self._entry_count -= 1

    def remove_entries(self, entries: list[LogEntryEntity]) -> None:
        for entry in entries:
            self.remove_entry(entry)

    def get_total_size(self) -> int:
        return self._total_size

    def get_total_size_mb(self) -> float:
        return self._total_size / 1024 / 1024

    def get_entry_count(self) -> int:
        return self._entry_count

    def get_avg_entry_size(self) -> float:
        if self._entry_count <= 0:
            return 0.0
        return self._total_size / self._entry_count

    def get_stats(self) -> MemoryStats:
        return MemoryStats(
            total_bytes=self._total_size,
            total_mb=self.get_total_size_mb(),
            entry_count=self._entry_count,
            avg_entry_size=self.get_avg_entry_size(),
        )

    def reset(self) -> None:
        self._total_size = 0
        self._entry_sizes.clear()
        self._entry_count = 0

    def _estimate_size(self, entry: LogEntryEntity) -> int:
        size = 0
        size += len(entry.id) * 2
        size += len(entry.timestamp) * 2
        size += len(entry.level) * 2
        size += len(entry.message) * 2

        if entry.trace_id:
            size += len(entry.trace_id) * 2
        if entry.span_id:
            size += len(entry.span_id) * 2
        if entry.request_id:
            size += len(entry.request_id) * 2

        if entry.context:
            keys = list(entry.context.keys())
            size += len(keys) * 20
            size += len(keys) * 50

        if entry.labels:
            for key, value in entry.labels.items():
                size += len(key) * 2
                size += len(value) * 2

        if entry.metadata:
            size += 50

        size += 200
        return size
