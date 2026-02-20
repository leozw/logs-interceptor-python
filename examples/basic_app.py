from logs_interceptor import init

init(
    {
        "appName": "my-service",
        "interceptConsole": True,
        "transport": {
            "url": "http://localhost:3100/loki/api/v1/push",
            "tenantId": "my-tenant",
            "compression": "gzip",
            "enableConnectionPooling": True,
        },
        "deadLetterQueue": {"enabled": True, "type": "file"},
        "circuitBreaker": {"enabled": True},
    }
)

print("service started")
