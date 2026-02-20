from __future__ import annotations

from typing import Any

from ..domain.interfaces import ILogger


class CelerySignals:
    def __init__(self, logger: ILogger) -> None:
        self.logger = logger

    def register(self, app: Any) -> None:
        try:
            from celery import signals
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("celery extra is not installed") from exc

        @signals.task_prerun.connect
        def _task_prerun(task_id: str | None = None, task: Any = None, *args: Any, **kwargs: Any) -> None:
            self.logger.info(
                "Celery task started",
                {
                    "source": "celery",
                    "task_id": task_id,
                    "task_name": getattr(task, "name", None),
                },
            )

        @signals.task_postrun.connect
        def _task_postrun(task_id: str | None = None, task: Any = None, retval: Any = None, *args: Any, **kwargs: Any) -> None:
            self.logger.info(
                "Celery task completed",
                {
                    "source": "celery",
                    "task_id": task_id,
                    "task_name": getattr(task, "name", None),
                    "retval": str(retval),
                },
            )

        @signals.task_failure.connect
        def _task_failure(task_id: str | None = None, task: Any = None, exception: Exception | None = None, *args: Any, **kwargs: Any) -> None:
            self.logger.error(
                "Celery task failed",
                {
                    "source": "celery",
                    "task_id": task_id,
                    "task_name": getattr(task, "name", None),
                    "error": str(exception),
                },
            )

        app.log.get_default_logger()
