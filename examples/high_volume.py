from logs_interceptor import init, logger

init(
    {
        "appName": "high-volume-service",
        "interceptConsole": True,
        "transport": {
            "url": "http://localhost:3100/loki/api/v1/push",
            "tenantId": "production",
            "compression": "snappy",
            "maxSockets": 100,
            "timeout": 10000,
            "useWorkers": True,
            "maxWorkers": 4,
            "compressionThreshold": 4096,
            "compressionLevel": 6,
        },
        "buffer": {
            "maxSize": 2000,
            "flushInterval": 2000,
            "maxMemoryMB": 512,
        },
        "performance": {
            "maxConcurrentFlushes": 10,
        },
    }
)

for i in range(10000):
    logger.info("High volume event", {"index": i})
