from __future__ import annotations

from contextvars import ContextVar
from typing import Any


class ContextVarProvider:
    def __init__(self) -> None:
        self._context: ContextVar[dict[str, Any] | None] = ContextVar(
            "logs_interceptor_context", default=None
        )

    def get_context(self) -> dict[str, Any]:
        return dict(self._context.get() or {})

    def run_with_context(self, context: dict[str, Any], fn: Any) -> Any:
        merged = {**(self._context.get() or {}), **context}
        token = self._context.set(merged)
        try:
            return fn()
        finally:
            self._context.reset(token)

    async def run_with_context_async(self, context: dict[str, Any], fn: Any) -> Any:
        merged = {**(self._context.get() or {}), **context}
        token = self._context.set(merged)
        try:
            result = fn()
            if hasattr(result, "__await__"):
                return await result
            return result
        finally:
            self._context.reset(token)

    def set(self, key: str, value: Any) -> None:
        merged = self.get_context()
        merged[key] = value
        self._context.set(merged)

    def get(self, key: str, default: Any = None) -> Any:
        return (self._context.get() or {}).get(key, default)

    def clear(self) -> None:
        self._context.set({})
