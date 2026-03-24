# Elven Live Demo

Local Python app to exercise `elven-logs-interceptor-python` against the Elven Loki endpoint.

## Run

```bash
cd /Users/leonardozwirtes/Documents/Projects/logs-interceptor-python
chmod +x test-apps/elven-live-demo/run.sh
./test-apps/elven-live-demo/run.sh
```

## Notes

- The tracked config template is `.env.example`.
- The real token lives only in local `.env`, which is ignored by Git.
- The package import remains `logs_interceptor`.
