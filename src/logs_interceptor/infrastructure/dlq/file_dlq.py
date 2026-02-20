from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from ...domain.entities import LogEntryEntity
from ...utils import internal_warn


@dataclass(slots=True)
class _DLQEntry:
    entry: LogEntryEntity
    reason: str
    timestamp: float
    retry_count: int


class FileDeadLetterQueue:
    def __init__(
        self,
        base_path: str | None = None,
        max_size: int = 1000,
        max_file_size_mb: int = 10,
        max_retries: int = 3,
    ) -> None:
        path = Path(base_path or os.getcwd())
        self._dlq_dir = path / ".logs-interceptor-dlq"
        self._dlq_dir.mkdir(parents=True, exist_ok=True)

        self._file_path = self._dlq_dir / "dlq-current.jsonl"
        self._max_size = max_size
        self._max_file_size_mb = max_file_size_mb
        self._max_retries = max_retries
        self._dropped_entries = 0
        self._queue: list[_DLQEntry] = []
        self._lock = threading.RLock()

        self.load_from_disk()

    def add(self, entry: LogEntryEntity, reason: str) -> dict[str, int]:
        return self.add_batch([entry], reason)

    def add_batch(self, entries: list[LogEntryEntity], reason: str) -> dict[str, int]:
        if not entries:
            return {"added": 0, "dropped": 0}

        with self._lock:
            dropped = 0
            ts = time.time()
            for entry in entries:
                if len(self._queue) >= self._max_size:
                    self._queue.pop(0)
                    self._dropped_entries += 1
                    dropped += 1
                self._queue.append(_DLQEntry(entry=entry, reason=reason, timestamp=ts, retry_count=0))

            self._persist_queue_to_disk()
            return {"added": len(entries), "dropped": dropped}

    def flush(self) -> int:
        return 0

    def size(self) -> int:
        with self._lock:
            return len(self._queue)

    def clear(self) -> None:
        with self._lock:
            self._queue.clear()
            try:
                if self._file_path.exists():
                    self._file_path.unlink()
            except OSError as exc:
                internal_warn("[FileDLQ] Failed to clear file", exc)

    def get_entries(self, limit: int = 100) -> list[dict[str, object]]:
        with self._lock:
            return [
                {
                    "entry": item.entry,
                    "reason": item.reason,
                    "timestamp": item.timestamp,
                }
                for item in self._queue[:limit]
            ]

    def get_stats(self) -> dict[str, int]:
        with self._lock:
            return {"size": len(self._queue), "dropped_entries": self._dropped_entries}

    def load_from_disk(self) -> int:
        if not self._file_path.exists():
            return 0

        with self._lock:
            try:
                lines = self._file_path.read_text(encoding="utf-8").splitlines()
                loaded: list[_DLQEntry] = []
                for line in lines:
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                        retry_count = int(item.get("retry_count", 0))
                        if retry_count > self._max_retries:
                            continue
                        entry_payload = item.get("entry", {})
                        if not isinstance(entry_payload, dict):
                            continue
                        loaded.append(
                            _DLQEntry(
                                entry=LogEntryEntity(
                                    id=str(entry_payload.get("id", "")),
                                    timestamp=str(entry_payload.get("timestamp", "")),
                                    level=str(entry_payload.get("level", "info")),  # type: ignore[arg-type]
                                    message=str(entry_payload.get("message", "")),
                                    context=entry_payload.get("context"),
                                    trace_id=entry_payload.get("trace_id"),
                                    span_id=entry_payload.get("span_id"),
                                    request_id=entry_payload.get("request_id"),
                                    labels=entry_payload.get("labels"),
                                    metadata=entry_payload.get("metadata"),
                                ),
                                reason=str(item.get("reason", "unknown")),
                                timestamp=float(item.get("timestamp", time.time())),
                                retry_count=retry_count,
                            )
                        )
                    except Exception:
                        continue

                if len(loaded) > self._max_size:
                    self._dropped_entries += len(loaded) - self._max_size
                self._queue = loaded[-self._max_size :]
                return len(self._queue)
            except OSError as exc:
                internal_warn("[FileDLQ] Failed to load from disk", exc)
                return 0

    def _persist_queue_to_disk(self) -> None:
        lines = [
            json.dumps(
                {
                    "entry": item.entry.to_dict(),
                    "reason": item.reason,
                    "timestamp": item.timestamp,
                    "retry_count": item.retry_count,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            for item in self._queue
        ]
        content = "\n".join(lines)
        if content:
            content += "\n"

        max_bytes = self._max_file_size_mb * 1024 * 1024
        if len(content.encode("utf-8")) > max_bytes and self._queue:
            half = max(1, len(self._queue) // 2)
            dropped = len(self._queue) - half
            self._queue = self._queue[-half:]
            self._dropped_entries += dropped
            return self._persist_queue_to_disk()

        self._file_path.write_text(content, encoding="utf-8")
