from logs_interceptor import init, logger

init(
    {
        "appName": "analytics-service",
        "transport": {
            "url": "http://localhost:3100/loki/api/v1/push",
            "tenantId": "analytics",
        },
    }
)

logger.track_event("user_signup", {"user_id": "u_123", "plan": "pro"})
logger.track_event("api_request", {"endpoint": "/users", "status_code": 200})
