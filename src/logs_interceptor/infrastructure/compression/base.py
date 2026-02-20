from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CompressorConfig:
    level: int | None = None
    threshold: int | None = None


class Compressor:
    def compress(self, data: bytes) -> bytes:
        raise NotImplementedError

    def get_content_encoding(self) -> str:
        raise NotImplementedError

    def get_name(self) -> str:
        raise NotImplementedError
