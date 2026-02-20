from __future__ import annotations

import logs_interceptor.infrastructure.filter.log_filter as filter_module
from logs_interceptor.config import ResolvedFilterConfig
from logs_interceptor.domain.entities import LogEntryEntity
from logs_interceptor.infrastructure.filter import LogFilter


def _entry(message: str = "hello", level: str = "info") -> LogEntryEntity:
    return LogEntryEntity(
        id="1",
        timestamp="2026-01-01T00:00:00+00:00",
        level=level,  # type: ignore[arg-type]
        message=message,
        context={"token": "abc"},
    )


def test_log_filter_should_process_blocks_by_level_and_pattern_and_sampling(monkeypatch) -> None:
    service = LogFilter(
        ResolvedFilterConfig(
            levels=["error"],
            patterns=[r"^ok$"],
            sampling_rate=1.0,
            max_message_length=50,
            sanitize=False,
            sensitive_patterns=[],
        )
    )

    # Disabled level
    assert service.should_process(_entry(level="info")) is False

    # Enabled level, but pattern mismatch
    assert service.should_process(_entry(message="not-match", level="error")) is False

    # Pattern matches, but sampling blocks
    monkeypatch.setattr(filter_module, "should_sample", lambda rate: False)
    assert service.should_process(_entry(message="ok", level="error")) is False


def test_log_filter_truncate_and_redact_message() -> None:
    truncating = LogFilter(
        ResolvedFilterConfig(
            levels=["info"],
            patterns=[],
            sampling_rate=1.0,
            max_message_length=4,
            sanitize=True,
            sensitive_patterns=[r"token"],
        )
    )

    truncated = truncating.filter(_entry(message="abcdef"))
    assert truncated.message.endswith("...[truncated]")

    redacting = LogFilter(
        ResolvedFilterConfig(
            levels=["info"],
            patterns=[],
            sampling_rate=1.0,
            max_message_length=500,
            sanitize=True,
            sensitive_patterns=[r"token"],
        )
    )
    redacted = redacting.filter(_entry(message="token=123"))
    assert redacted.message == "[REDACTED]"
