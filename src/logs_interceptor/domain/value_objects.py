from __future__ import annotations

from dataclasses import dataclass

from ..types import LogLevel

VALID_LOG_LEVELS: tuple[LogLevel, ...] = ("debug", "info", "warn", "error", "fatal")
LEVEL_PRIORITY: dict[LogLevel, int] = {
    "debug": 0,
    "info": 1,
    "warn": 2,
    "error": 3,
    "fatal": 4,
}


@dataclass(frozen=True)
class LogLevelVO:
    value: LogLevel

    def __post_init__(self) -> None:
        if not self.is_valid(self.value):
            raise ValueError(f"Invalid log level: {self.value}")

    @staticmethod
    def is_valid(level: str) -> bool:
        return level in VALID_LOG_LEVELS

    @staticmethod
    def from_string(level: str) -> LogLevelVO:
        normalized = level.lower().strip()
        if not LogLevelVO.is_valid(normalized):
            raise ValueError(f"Invalid log level: {level}")
        return LogLevelVO(normalized)  # type: ignore[arg-type]

    def compare_to(self, other: LogLevelVO) -> int:
        return LEVEL_PRIORITY[self.value] - LEVEL_PRIORITY[other.value]

    def is_greater_than_or_equal(self, other: LogLevelVO) -> bool:
        return self.compare_to(other) >= 0
