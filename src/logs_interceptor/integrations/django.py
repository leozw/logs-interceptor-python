from __future__ import annotations

import time
from typing import Any

from ..domain.interfaces import ILogger


class DjangoMiddleware:
    def __init__(self, get_response: Any, logger: ILogger) -> None:
        self.get_response = get_response
        self.logger = logger

    def __call__(self, request: Any) -> Any:
        start = time.time()
        request_id = request.headers.get("X-Request-Id") if hasattr(request, "headers") else None
        if not request_id:
            request_id = f"req-{int(start * 1000)}"

        def _run() -> Any:
            return self.get_response(request)

        response = self.logger.with_context({"request_id": request_id}, _run)

        duration_ms = int((time.time() - start) * 1000)
        status_code = int(getattr(response, "status_code", 200))
        level = "info"
        if status_code >= 500:
            level = "error"
        elif status_code >= 400:
            level = "warn"

        self.logger.log(
            level,  # type: ignore[arg-type]
            f"{request.method} {request.path}",
            {
                "type": "http_request",
                "source": "django",
                "status_code": status_code,
                "duration_ms": duration_ms,
            },
        )

        return response
