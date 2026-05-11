from __future__ import annotations

from importlib import import_module
from typing import Any, cast

from .base import Compressor, CompressorConfig

try:
    brotli = cast(Any, import_module("brotli"))
except Exception:  # pragma: no cover - optional dependency
    brotli = None


class BrotliCompressor(Compressor):
    def __init__(self, config: CompressorConfig | None = None) -> None:
        self._config = config or CompressorConfig()
        self._level = 4 if self._config.level is None else self._config.level

    def compress(self, data: bytes) -> bytes:
        if brotli is None:
            raise RuntimeError("brotli extra is not installed")
        return cast(bytes, brotli.compress(data, quality=self._level))

    def get_content_encoding(self) -> str:
        return "br"

    def get_name(self) -> str:
        return "brotli"
