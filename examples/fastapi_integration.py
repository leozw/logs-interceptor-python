from fastapi import FastAPI

from logs_interceptor import init, logger
from logs_interceptor.integrations import FastAPIMiddleware

init(
    {
        "transport": {
            "url": "http://localhost:3100/loki/api/v1/push",
            "tenantId": "my-tenant",
            "compression": "brotli",
        },
        "appName": "my-api",
        "interceptConsole": True,
        "deadLetterQueue": {"enabled": True, "type": "file"},
    }
)

app = FastAPI()
app.add_middleware(FastAPIMiddleware, logger=logger)


@app.get("/ping")
def ping() -> dict[str, str]:
    logger.info("ping called")
    return {"message": "pong"}
