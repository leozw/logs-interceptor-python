from __future__ import annotations

import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

import logs_interceptor.utils as utils
from logs_interceptor.config import LogsInterceptorConfig, TransportConfig
from logs_interceptor.utils import (
    _env_levels,
    _merge_dataclass,
    calculate_compression_ratio,
    create_correlation_id,
    detect_sensitive_data,
    extract_error_metadata,
    format_bytes,
    hash_sensitive_data,
    internal_debug,
    internal_error,
    internal_warn,
    load_config_from_env,
    merge_configs,
    parse_bool,
    parse_float_range,
    parse_int_range,
    parse_labels,
    parse_stack_trace,
    safe_stringify,
    sanitize_data,
    should_sample,
    should_sample_advanced,
)


def test_parse_helpers() -> None:
    assert parse_bool("true", False) is True
    assert parse_bool("false", True) is False
    assert parse_bool("invalid", True) is True
    assert parse_int_range("10", 1, 0, 20) == 10
    assert parse_int_range("x", 1, 0, 20) == 1
    assert parse_int_range("30", 1, 0, 20) == 1
    assert parse_float_range("0.5", 1.0, 0.0, 1.0) == 0.5
    assert parse_float_range("bad", 0.7, 0.0, 1.0) == 0.7
    assert parse_float_range("1.7", 0.7, 0.0, 1.0) == 0.7


def test_parse_labels_and_hash() -> None:
    assert parse_labels("a=1,b=2") == {"a": "1", "b": "2"}
    assert parse_labels("") == {}
    assert parse_labels('{"service":"api","env":"prod"}') == {"service": "api", "env": "prod"}
    assert len(hash_sensitive_data("secret")) == 16


def test_safe_stringify_and_sanitize() -> None:
    circular = {}
    circular["self"] = circular
    text = safe_stringify(circular)
    assert "Circular" in text

    data = {"token": "secret", "safe": "ok"}
    redacted = sanitize_data(data, ["token"])
    assert redacted["token"] == "[REDACTED]"
    assert redacted["safe"] == "ok"


def test_safe_stringify_extended_types_and_depth() -> None:
    @dataclass
    class _Payload:
        value: str

    class _Object:
        def __init__(self) -> None:
            self.field = "ok"

    class _SlotsOnly:
        __slots__ = ()

        def __str__(self) -> str:
            return "slots"

    payload = {
        "err": ValueError("boom"),
        "dt": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "iterables": [{"a", "b"}, ("x", "y"), frozenset({"f"})],
        "data": _Payload("x"),
        "obj": _Object(),
        "slots": _SlotsOnly(),
        "nested": {"a": {"b": {"c": "d"}}},
    }

    parsed = json.loads(safe_stringify(payload, max_depth=2))
    assert parsed["err"]["name"] == "ValueError"
    assert parsed["dt"].startswith("2026-01-01T")
    assert parsed["data"]["value"] == "x"
    assert parsed["obj"] in ({"field": "ok"}, "[Circular Reference]")
    assert parsed["slots"] == "slots"
    assert parsed["nested"]["a"]["b"] == "[Max Depth Reached]"


def test_safe_stringify_uses_orjson_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeOrjson:
        @staticmethod
        def dumps(value: object) -> bytes:
            return b'{"backend":"orjson","ok":true}'

    monkeypatch.setattr(utils, "orjson", _FakeOrjson())
    assert safe_stringify({"any": "value"}) == '{"backend":"orjson","ok":true}'


def test_merge_configs_precedence() -> None:
    env_cfg = LogsInterceptorConfig(
        transport=TransportConfig(url="https://env", tenant_id="env"),
        app_name="env-app",
    )
    user_cfg = LogsInterceptorConfig(
        transport=TransportConfig(url="https://user", tenant_id="user"),
        app_name="user-app",
    )

    merged = merge_configs(user_cfg, env_cfg)
    assert merged.transport.url == "https://user"
    assert merged.transport.tenant_id == "user"
    assert merged.app_name == "user-app"


def test_misc_helpers() -> None:
    assert should_sample(1.0) is True
    assert should_sample(0.0) is False
    assert len(create_correlation_id()) == 32


def test_sampling_helpers_advanced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(utils.random, "random", lambda: 0.2)
    assert should_sample(0.5) is True

    deterministic = should_sample_advanced(0.5, strategy="deterministic", key="user:123")
    assert isinstance(deterministic, bool)

    monkeypatch.setattr(utils.os, "getloadavg", lambda: (10.0, 1.0, 1.0))
    monkeypatch.setattr(utils.os, "cpu_count", lambda: 10)
    assert should_sample_advanced(1.0, strategy="adaptive") is True
    assert should_sample_advanced(0.0, strategy="adaptive") is False
    assert should_sample_advanced(0.5, strategy="adaptive") is True

    def _raise() -> tuple[float, float, float]:
        raise OSError("not supported")

    monkeypatch.setattr(utils.os, "getloadavg", _raise)
    assert isinstance(should_sample_advanced(0.5, strategy="adaptive"), bool)


def test_misc_math_helpers() -> None:
    assert format_bytes(0) == "0 Bytes"
    assert format_bytes(2048) == "2.00 KB"
    assert calculate_compression_ratio(100, 25) == 75.0
    assert calculate_compression_ratio(0, 0) == 0.0


def test_sanitize_data_recursive_and_sensitive_detection() -> None:
    nested = {
        "user": "safe",
        "auth_token": "abc",
        "children": [
            "safe",
            "user@example.com",
            {"password": "123", "x": "ok"},
        ],
    }
    nested["self"] = nested

    redacted = sanitize_data(nested, [r"token", r"password"])
    assert redacted["auth_token"] == "[REDACTED]"
    assert redacted["children"][1] == "[REDACTED]"
    assert redacted["children"][2]["password"] == "[REDACTED]"
    assert redacted["self"] == {"_circular": "[REDACTED]"}
    assert detect_sensitive_data("Bearer my-secret-token", [r"token"]) is True


def test_merge_dataclass_helper() -> None:
    env_transport = TransportConfig(url="https://env", tenant_id="tenant", timeout=10)
    user_transport = TransportConfig(url="", tenant_id="", timeout=None)

    merged_transport = _merge_dataclass(env_transport, user_transport)
    assert isinstance(merged_transport, TransportConfig)
    assert merged_transport.timeout == 10

    assert _merge_dataclass(None, user_transport) is user_transport
    assert _merge_dataclass(env_transport, None) is env_transport
    assert _merge_dataclass(None, None) is None
    assert _merge_dataclass({"env": 1}, {"user": 2}) == {"user": 2}


def test_env_levels_and_env_loader_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _env_levels("debug,invalid,error") == ["debug", "error"]

    monkeypatch.setenv("LOGS_ENABLED", "false")
    disabled_cfg = load_config_from_env()
    assert disabled_cfg.filter is not None
    assert disabled_cfg.filter.levels == []

    monkeypatch.setenv("LOGS_ENABLED", "true")
    monkeypatch.setenv("LOGS_URL", "https://loki.example.com/loki/api/v1/push")
    monkeypatch.setenv("LOGS_TENANT", "tenant")
    monkeypatch.setenv("LOGS_APP_NAME", "app")
    monkeypatch.setenv("LOGS_COMPRESSION", "invalid")
    monkeypatch.setenv("LOGS_DLQ_TYPE", "invalid")

    cfg = load_config_from_env()
    assert cfg.transport.compression == "gzip"
    assert cfg.dead_letter_queue is not None
    assert cfg.dead_letter_queue.type == "memory"


def test_parse_labels_invalid_json_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, object | None]] = []

    def _warn(message: str, context: object | None = None) -> None:
        calls.append((message, context))

    monkeypatch.setattr(utils, "internal_warn", _warn)
    assert parse_labels("{bad-json}") == {}
    assert calls


def test_internal_log_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    monkeypatch.setattr(utils.sys, "stdout", stdout)
    monkeypatch.setattr(utils.sys, "stderr", stderr)

    monkeypatch.setenv("LOGS_DEBUG", "true")
    monkeypatch.setenv("LOGS_SILENT_ERRORS", "false")
    internal_debug("debug message", {"a": 1})
    internal_warn("warn message")
    internal_error("error message")
    assert "debug message" in stdout.getvalue()
    assert "warn message" in stderr.getvalue()
    assert "error message" in stderr.getvalue()

    # Silent mode suppresses warn/error output.
    stderr.truncate(0)
    stderr.seek(0)
    monkeypatch.setenv("LOGS_SILENT_ERRORS", "true")
    internal_warn("should-not-print")
    internal_error("should-not-print")
    assert stderr.getvalue() == ""


def test_extract_error_metadata_and_parse_stack_trace() -> None:
    class _CustomError(RuntimeError):
        def __init__(self) -> None:
            super().__init__("boom")
            self.code = "E_BROKEN"
            self.status_code = 503
            self.errno = 12
            self.path = "/tmp/file"
            self.address = "127.0.0.1"
            self.port = 5432

    metadata = extract_error_metadata(_CustomError())
    assert metadata["name"] == "_CustomError"
    assert metadata["status_code"] == 503
    assert metadata["port"] == 5432

    stack_lines = [
        f'  File "/tmp/a{i}.py", line {i}, in fn{i}'
        for i in range(1, 13)
    ]
    parsed = parse_stack_trace("\n".join(["Traceback...", *stack_lines]))
    assert len(parsed) == 10
    assert parsed[0]["file"] == "/tmp/a1.py"
