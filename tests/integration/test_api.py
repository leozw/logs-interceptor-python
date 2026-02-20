from __future__ import annotations

import httpx
import pytest

from logs_interceptor import destroy, get_logger, init, is_initialized


@pytest.fixture(autouse=True)
def cleanup_runtime() -> None:
    try:
        destroy()
    except Exception:
        pass
    yield
    try:
        destroy()
    except Exception:
        pass


def _valid_config() -> dict[str, object]:
    return {
        "transport": {
            "url": "https://loki.example.com/loki/api/v1/push",
            "tenantId": "tenant-a",
            "authToken": "token",
            "useWorkers": False,
            "enableConnectionPooling": False,
            "maxRetries": 0,
            "timeout": 100,
        },
        "appName": "test-app",
        "interceptConsole": False,
    }


def test_initialize_with_valid_config() -> None:
    logger_instance = init(_valid_config())
    assert logger_instance is get_logger()
    assert is_initialized() is True


def test_initialize_from_environment_only(monkeypatch) -> None:
    monkeypatch.setenv("LOGS_ENABLED", "true")
    monkeypatch.setenv("LOGS_URL", "https://loki.example.com/loki/api/v1/push")
    monkeypatch.setenv("LOGS_TENANT", "tenant-a")
    monkeypatch.setenv("LOGS_APP_NAME", "env-app")
    monkeypatch.setenv("LOGS_INTERCEPT_CONSOLE", "false")
    monkeypatch.setenv("LOGS_CONNECTION_POOLING", "false")
    monkeypatch.setenv("LOGS_MAX_RETRIES", "0")
    monkeypatch.setenv("LOGS_TIMEOUT", "100")

    logger_instance = init()
    assert logger_instance is get_logger()
    assert is_initialized() is True


def test_initialize_with_invalid_config_raises() -> None:
    with pytest.raises(ValueError):
        init(
            {
                "transport": {
                    "url": "",
                    "tenantId": "tenant-a",
                },
                "appName": "test-app",
            }
        )


def test_logging_and_metrics() -> None:
    instance = init(_valid_config())

    instance.debug("debug")
    instance.info("info")
    instance.warn("warn")
    instance.error("error")

    metrics = instance.get_metrics()
    assert metrics["logs_processed"] >= 4
    assert metrics["buffer_size"] >= 0


@pytest.mark.asyncio
async def test_context_api_async() -> None:
    instance = init(_valid_config())

    async def _fn() -> str:
        instance.info("inside async context")
        return "ok"

    result = await instance.with_context_async({"request_id": "req-123"}, _fn)
    assert result == "ok"


def test_flush_propagates_transport_errors() -> None:
    instance = init(_valid_config())
    instance.info("will flush")

    with pytest.raises(httpx.ConnectError):
        instance.flush()
