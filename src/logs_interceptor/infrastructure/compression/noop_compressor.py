from __future__ import annotations

from .base import Compressor


class NoOpCompressor(Compressor):
    def compress(self, data: bytes) -> bytes:
        return data

    def get_content_encoding(self) -> str:
        return ""

    def get_name(self) -> str:
        return "none"
