from __future__ import annotations

from logs_interceptor.utils import load_config_from_env


def test_load_required_logs_fields(monkeypatch) -> None:
    monkeypatch.setenv("LOGS_URL", "https://loki.example.com/loki/api/v1/push")
    monkeypatch.setenv("LOGS_TENANT", "tenant-a")
    monkeypatch.setenv("LOGS_APP_NAME", "app-a")

    config = load_config_from_env()

    assert config.transport.url == "https://loki.example.com/loki/api/v1/push"
    assert config.transport.tenant_id == "tenant-a"
    assert config.app_name == "app-a"


def test_preserve_explicit_zero_values(monkeypatch) -> None:
    monkeypatch.setenv("LOGS_URL", "https://loki.example.com/loki/api/v1/push")
    monkeypatch.setenv("LOGS_TENANT", "tenant-a")
    monkeypatch.setenv("LOGS_APP_NAME", "app-a")
    monkeypatch.setenv("LOGS_TIMEOUT", "0")
    monkeypatch.setenv("LOGS_MAX_RETRIES", "0")
    monkeypatch.setenv("LOGS_RETRY_DELAY", "0")
    monkeypatch.setenv("LOGS_FILTER_SAMPLING_RATE", "0.0")
    monkeypatch.setenv("LOGS_COMPRESSION_LEVEL", "0")

    config = load_config_from_env()

    assert config.transport.timeout == 0
    assert config.transport.max_retries == 0
    assert config.transport.retry_delay == 0
    assert config.filter is not None
    assert config.filter.sampling_rate == 0.0
    assert config.transport.compression_level == 0


def test_load_labels_from_prefix(monkeypatch) -> None:
    monkeypatch.setenv("LOGS_URL", "https://loki.example.com/loki/api/v1/push")
    monkeypatch.setenv("LOGS_TENANT", "tenant-a")
    monkeypatch.setenv("LOGS_APP_NAME", "app-a")
    monkeypatch.setenv("LOGS_LABEL_SERVICE", "busca-prd")
    monkeypatch.setenv("LOGS_LABEL_ENVIRONMENT", "prd")

    config = load_config_from_env()

    assert config.labels == {"service": "busca-prd", "environment": "prd"}


def test_load_excluded_logger_prefixes_from_env(monkeypatch) -> None:
    monkeypatch.setenv("LOGS_URL", "https://loki.example.com/loki/api/v1/push")
    monkeypatch.setenv("LOGS_TENANT", "tenant-a")
    monkeypatch.setenv("LOGS_APP_NAME", "app-a")
    monkeypatch.setenv("LOGS_FILTER_EXCLUDE_LOGGER_PREFIXES", "httpx, httpcore ,custom_stack")

    config = load_config_from_env()

    assert config.filter is not None
    assert config.filter.exclude_logger_prefixes == ["httpx", "httpcore", "custom_stack"]
