from __future__ import annotations

import gzip

from .base import Compressor, CompressorConfig


class GzipCompressor(Compressor):
    def __init__(self, config: CompressorConfig | None = None) -> None:
        self._config = config or CompressorConfig()
        self._level = 6 if self._config.level is None else self._config.level

    def compress(self, data: bytes) -> bytes:
        return gzip.compress(data, compresslevel=self._level)

    def get_content_encoding(self) -> str:
        return "gzip"

    def get_name(self) -> str:
        return "gzip"
