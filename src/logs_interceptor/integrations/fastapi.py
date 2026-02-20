from __future__ import annotations

import time
from typing import Any

from ..domain.interfaces import ILogger


class FastAPIMiddleware:
    def __init__(self, app: Any, logger: ILogger) -> None:
        self.app = app
        self.logger = logger

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        start = time.time()
        headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope.get("headers", [])}
        request_id = headers.get("x-request-id") or f"req-{int(start * 1000)}"

        status_code_holder = {"status": 200}

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                status_code_holder["status"] = int(message.get("status", 200))
            await send(message)

        async def run_request() -> None:
            await self.app(scope, receive, send_wrapper)

        await self.logger.with_context_async({"request_id": request_id}, run_request)

        duration_ms = int((time.time() - start) * 1000)
        level = "info"
        if status_code_holder["status"] >= 500:
            level = "error"
        elif status_code_holder["status"] >= 400:
            level = "warn"

        self.logger.log(
            level,  # type: ignore[arg-type]
            f"{scope.get('method', 'GET')} {scope.get('path', '/')}",
            {
                "type": "http_request",
                "path": scope.get("path"),
                "method": scope.get("method"),
                "status_code": status_code_holder["status"],
                "duration_ms": duration_ms,
                "source": "fastapi",
            },
        )
