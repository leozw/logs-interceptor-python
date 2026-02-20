# Elven Observability Smoke App

Small test app to validate real log delivery using `logs-interceptor-python` with env-based config.

## Run

```bash
cd /Users/leonardozwirtes/Documents/Projects/logs-interceptor-python
cp test-apps/elven-observability-smoke/.env.example test-apps/elven-observability-smoke/.env
chmod +x test-apps/elven-observability-smoke/run.sh
./test-apps/elven-observability-smoke/run.sh
```

## Notes

- Config is loaded from `test-apps/elven-observability-smoke/.env`.
- `LOGS_TOKEN` in `.env.example` is a placeholder. Use a real token only in local `.env`.
- App name/environment were adjusted for smoke testing:
  - `LOGS_APP_NAME=busca-smoke`
  - `LOGS_ENVIRONMENT=hml`
  - `LOGS_LABEL_SERVICE=busca-smoke`
  - `LOGS_LABEL_ENVIRONMENT=hml`

Snappy/protobuf note:

- By default, snappy/protobuf transport is kept behind `LOGS_ENABLE_EXPERIMENTAL_PROTOBUF=true`.
- If not enabled, the library safely falls back to JSON transport.
