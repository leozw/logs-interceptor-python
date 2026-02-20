# logs-interceptor-python

High-performance, production-ready log interceptor for Python with Loki transport, batching, compression, circuit breaker, DLQ, and framework integrations.

## Installation

```bash
pip install logs-interceptor-python
```

With all extras:

```bash
pip install "logs-interceptor-python[all]"
```

## Quick Start

```python
from logs_interceptor import init, logger

init(
    {
        "appName": "billing-service",
        "interceptConsole": True,
        "transport": {
            "url": "https://loki.example.com/loki/api/v1/push",
            "tenantId": "tenant-a",
            "authToken": "token",
            "compression": "gzip",
        },
    }
)

logger.info("service started", {"port": 3000})
```

## Environment Variables

The package supports all `LOGS_*` variables from the JS v3 design.

Required:

- `LOGS_URL`
- `LOGS_TENANT`
- `LOGS_APP_NAME`

Core:

- `LOGS_TOKEN`
- `LOGS_APP_VERSION`
- `LOGS_ENVIRONMENT`

Transport:

- `LOGS_COMPRESSION` (`none|gzip|brotli|snappy`)
- `LOGS_COMPRESSION_LEVEL`
- `LOGS_COMPRESSION_THRESHOLD`
- `LOGS_USE_WORKERS`
- `LOGS_MAX_WORKERS`
- `LOGS_WORKER_TIMEOUT`
- `LOGS_CONNECTION_POOLING`
- `LOGS_MAX_SOCKETS`
- `LOGS_TIMEOUT`
- `LOGS_MAX_RETRIES`
- `LOGS_RETRY_DELAY`

Buffer:

- `LOGS_BUFFER_MAX_SIZE`
- `LOGS_BUFFER_FLUSH_INTERVAL`
- `LOGS_BUFFER_MAX_MEMORY_MB`
- `LOGS_BUFFER_MAX_AGE`
- `LOGS_BUFFER_AUTO_FLUSH`

Filter:

- `LOGS_FILTER_LEVELS`
- `LOGS_FILTER_SAMPLING_RATE`
- `LOGS_FILTER_SANITIZE`
- `LOGS_FILTER_MAX_MESSAGE_LENGTH`

Circuit Breaker:

- `LOGS_CIRCUIT_BREAKER_ENABLED`
- `LOGS_CIRCUIT_BREAKER_FAILURE_THRESHOLD`
- `LOGS_CIRCUIT_BREAKER_RESET_TIMEOUT`
- `LOGS_CIRCUIT_BREAKER_HALF_OPEN_REQUESTS`

DLQ:

- `LOGS_DLQ_ENABLED`
- `LOGS_DLQ_TYPE` (`memory|file`)
- `LOGS_DLQ_MAX_SIZE`
- `LOGS_DLQ_MAX_RETRIES`
- `LOGS_DLQ_BASE_PATH`

Runtime:

- `LOGS_MAX_CONCURRENT_FLUSHES`
- `LOGS_INTERCEPT_CONSOLE`
- `LOGS_PRESERVE_ORIGINAL_CONSOLE`
- `LOGS_ENABLE_METRICS`
- `LOGS_ENABLE_HEALTH_CHECK`
- `LOGS_DEBUG`
- `LOGS_SILENT_ERRORS`
- `LOGS_ENABLED`
- `LOGS_AUTO_INIT`
- `LOGS_ENABLE_EXPERIMENTAL_PROTOBUF` (optional, enables experimental snappy/protobuf transport path)

Labels:

- Prefix `LOGS_LABEL_*` (example: `LOGS_LABEL_SERVICE=billing`)

## Public API

- `init(config)`
- `get_logger()`
- `is_initialized()`
- `destroy()`
- `adestroy()`
- `logger` proxy with `debug/info/warn/error/fatal/log/track_event/flush/aflush/get_metrics/get_health/destroy/adestroy/with_context/with_context_async`

## Integrations

- Python `logging` (`LoggingHandler`)
- FastAPI / Starlette (`FastAPIMiddleware`)
- Django (`DjangoMiddleware`)
- Flask (`FlaskExtension`)
- Celery (`CelerySignals`)
- structlog (`StructlogProcessor`)
- loguru (`LoguruSink`)

## Auto Init

Set `LOGS_AUTO_INIT=true` and import the package.

Preload mode:

```bash
python -m logs_interceptor.preload
```

## Development

```bash
pip install -e ".[dev]"
ruff check .
mypy src
pytest
```

## Deploy / Publish

Local publish script:

```bash
./scripts/publish.sh --repository testpypi --dry-run
./scripts/publish.sh --repository testpypi
./scripts/publish.sh --repository pypi
```

Token environment variables used by default:

- `TEST_PYPI_API_TOKEN` for `--repository testpypi`
- `PYPI_API_TOKEN` for `--repository pypi`

Optional script flags:

- `--skip-checks` (skip lint/type/test)
- `--skip-build` (skip build/twine check)
- `--token-env CUSTOM_VAR` (custom token env var name)
- `--no-skip-existing` (upload fails if version already exists)

Makefile shortcuts:

```bash
make qa
make publish-dry-run
make publish-testpypi
make publish-pypi
```

GitHub Actions publish workflow:

- File: `.github/workflows/publish.yml`
- Trigger: manual (`workflow_dispatch`)
- Inputs: `repository = testpypi | pypi`
- Required secrets:
  - `TEST_PYPI_API_TOKEN`
  - `PYPI_API_TOKEN`

## License

MIT
