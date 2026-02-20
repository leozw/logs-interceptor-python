from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from typing import Any, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class WorkerMetrics:
    active_workers: int
    queue_length: int
    total_tasks: int
    completed_tasks: int
    failed_tasks: int


class WorkerPool:
    def __init__(self, max_workers: int | None = None) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = Lock()
        self._total_tasks = 0
        self._completed_tasks = 0
        self._failed_tasks = 0

    def execute(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> Future[T]:
        with self._lock:
            self._total_tasks += 1

        future = self._executor.submit(fn, *args, **kwargs)

        def _done_callback(done: Future[T]) -> None:
            with self._lock:
                if done.exception() is None:
                    self._completed_tasks += 1
                else:
                    self._failed_tasks += 1

        future.add_done_callback(_done_callback)
        return future

    def get_metrics(self) -> WorkerMetrics:
        with self._lock:
            queue_length = self._total_tasks - self._completed_tasks - self._failed_tasks
            return WorkerMetrics(
                active_workers=0,
                queue_length=max(0, queue_length),
                total_tasks=self._total_tasks,
                completed_tasks=self._completed_tasks,
                failed_tasks=self._failed_tasks,
            )

    def destroy(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)
