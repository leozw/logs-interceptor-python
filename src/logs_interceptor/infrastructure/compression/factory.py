from __future__ import annotations

from .base import Compressor, CompressorConfig
from .brotli_compressor import BrotliCompressor
from .gzip_compressor import GzipCompressor
from .noop_compressor import NoOpCompressor


class CompressorFactory:
    @staticmethod
    def create(type_name: str | bool | None, config: CompressorConfig | None = None) -> Compressor:
        if type_name in (False, "none"):
            return NoOpCompressor()
        if type_name in (True, None, "gzip"):
            return GzipCompressor(config)
        if type_name == "brotli":
            return BrotliCompressor(config)
        return GzipCompressor(config)
