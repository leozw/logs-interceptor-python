from logs_interceptor import init

init(
    {
        "appName": "my-service-name",
        "version": "1.2.0",
        "environment": "production",
        "interceptConsole": True,
        "preserveOriginalConsole": True,
        "silentErrors": False,
        "debug": False,
        "labels": {"region": "us-east-1", "tier": "gold"},
        "dynamicLabels": {
            "pod_id": lambda: "unknown",
        },
        "transport": {
            "url": "http://localhost:3100/loki/api/v1/push",
            "tenantId": "my-tenant-id",
            "timeout": 10000,
            "maxRetries": 3,
            "retryDelay": 1000,
            "enableConnectionPooling": True,
            "maxSockets": 50,
            "compression": "snappy",
            "compressionLevel": 6,
            "compressionThreshold": 1024,
            "useWorkers": True,
            "maxWorkers": 2,
            "workerTimeout": 30000,
        },
        "buffer": {
            "maxSize": 1000,
            "flushInterval": 5000,
            "maxMemoryMB": 50,
            "maxAge": 30000,
            "autoFlush": True,
        },
        "filter": {
            "levels": ["info", "warn", "error", "fatal"],
            "patterns": ["health/check"],
            "samplingRate": 1.0,
            "sanitize": True,
            "sensitivePatterns": ["password", "token", "secret"],
            "maxMessageLength": 8192,
        },
        "circuitBreaker": {
            "enabled": True,
            "failureThreshold": 20,
            "resetTimeout": 30000,
            "halfOpenRequests": 3,
        },
        "deadLetterQueue": {
            "enabled": True,
            "type": "file",
            "basePath": "./.logs-dlq",
            "maxSize": 1000,
            "maxRetries": 10,
        },
        "performance": {
            "useWorkers": True,
            "maxConcurrentFlushes": 5,
            "workerTimeout": 30000,
        },
        "enableMetrics": True,
        "enableHealthCheck": True,
    }
)
