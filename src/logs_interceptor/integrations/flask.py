from __future__ import annotations

import time
from typing import Any

from ..domain.interfaces import ILogger


class FlaskExtension:
    def __init__(self, logger: ILogger) -> None:
        self.logger = logger

    def init_app(self, app: Any) -> None:
        @app.before_request
        def _before_request() -> None:
            from flask import g, request

            g._logs_interceptor_start_time = time.time()
            request_id = request.headers.get("X-Request-Id") or f"req-{int(time.time() * 1000)}"
            g._logs_interceptor_request_id = request_id

        @app.after_request
        def _after_request(response: Any) -> Any:
            from flask import g, request

            start = getattr(g, "_logs_interceptor_start_time", time.time())
            request_id = getattr(g, "_logs_interceptor_request_id", "")
            duration_ms = int((time.time() - start) * 1000)
            status_code = int(getattr(response, "status_code", 200))

            level = "info"
            if status_code >= 500:
                level = "error"
            elif status_code >= 400:
                level = "warn"

            self.logger.with_context(
                {"request_id": request_id},
                lambda: self.logger.log(
                    level,  # type: ignore[arg-type]
                    f"{request.method} {request.path}",
                    {
                        "source": "flask",
                        "type": "http_request",
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                    },
                ),
            )
            return response
