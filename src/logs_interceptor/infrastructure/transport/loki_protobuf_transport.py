from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, cast

import httpx

from ...config import ResolvedTransportConfig
from ...domain.entities import LogEntryEntity
from ...types import TransportHealth, TransportMetrics

try:
    import snappy  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - optional dependency
    snappy = None

@dataclass(slots=True)
class RetryableTransportError(Exception):
    message: str
    status_code: int | None = None
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


class LokiProtobufTransport:
    """
    Protobuf/Snappy transport with graceful fallback semantics.

    The runtime payload is encoded as JSON bytes and then Snappy-compressed
    when protobuf schemas are unavailable in environment.
    """

    def __init__(
        self,
        config: ResolvedTransportConfig,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        # This transport requires a real protobuf payload implementation.
        # Keep it explicitly opt-in to avoid silent breakage in production
        # when users install `python-snappy` but don't expect experimental behavior.
        experimental_enabled = (os.getenv("LOGS_ENABLE_EXPERIMENTAL_PROTOBUF") or "").strip().lower()
        if experimental_enabled not in {"1", "true", "yes", "on"}:
            raise RuntimeError("Set LOGS_ENABLE_EXPERIMENTAL_PROTOBUF=true to enable LokiProtobufTransport")

        if snappy is None:
            raise RuntimeError("python-snappy is required for compression='snappy'")

        self._config = config
        self._extra_headers = extra_headers or {}
        self._timeout = config.timeout / 1000
        self._client: httpx.Client | None = None
        if config.enable_connection_pooling:
            limits = httpx.Limits(max_keepalive_connections=config.max_sockets, max_connections=config.max_sockets)
            self._client = httpx.Client(timeout=self._timeout, limits=limits)

        self._health: TransportHealth = {
            "healthy": True,
            "consecutive_failures": 0,
        }
        self._metrics: TransportMetrics = {
            "total_sends": 0,
            "successful_sends": 0,
            "failed_sends": 0,
            "avg_latency": 0.0,
            "avg_compression_time": 0.0,
            "avg_compression_ratio": 0.0,
            "total_bytes_sent": 0,
            "total_bytes_compressed": 0,
        }

    def send(self, entries: list[LogEntryEntity]) -> None:
        if not entries:
            return

        start = time.perf_counter()
        self._metrics["total_sends"] = self._metrics.get("total_sends", 0) + 1

        try:
            payload = self._format_payload(entries)
            raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            raw_size = len(raw)

            compression_start = time.perf_counter()
            compressed = cast(bytes, snappy.compress(raw))
            compression_time = (time.perf_counter() - compression_start) * 1000
            compressed_size = len(compressed)

            headers = {
                "Content-Type": "application/x-protobuf",
                "Content-Encoding": "snappy",
                "X-Scope-OrgID": self._config.tenant_id,
                "User-Agent": "logs-interceptor-python/0.1.1",
                **self._extra_headers,
            }
            if self._config.auth_token:
                headers["Authorization"] = f"Bearer {self._config.auth_token}"

            response = self._request(headers, compressed)
            if response.status_code >= 300:
                raise RetryableTransportError(
                    message=f"Loki responded with {response.status_code}: {response.text}",
                    status_code=response.status_code,
                    retryable=response.status_code == 429 or response.status_code >= 500,
                )

            latency = (time.perf_counter() - start) * 1000
            self._record_success(latency)
            self._update_compression_metrics(compression_time, raw_size, compressed_size)
            self._metrics["total_bytes_sent"] = self._metrics.get("total_bytes_sent", 0) + compressed_size
            self._metrics["total_bytes_compressed"] = self._metrics.get("total_bytes_compressed", 0) + raw_size
        except Exception as exc:
            self._record_failure(exc)
            raise

    def _request(self, headers: dict[str, str], body: bytes) -> httpx.Response:
        if self._client is not None:
            return self._client.post(self._config.url, headers=headers, content=body)
        with httpx.Client(timeout=self._timeout) as client:
            return client.post(self._config.url, headers=headers, content=body)

    def is_available(self) -> bool:
        return bool(self._health.get("healthy", False))

    def get_health(self) -> TransportHealth:
        return cast(TransportHealth, dict(self._health))

    def get_metrics(self) -> TransportMetrics:
        return cast(TransportMetrics, dict(self._metrics))

    def destroy(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _record_success(self, duration_ms: float) -> None:
        self._health = {
            "healthy": True,
            "consecutive_failures": 0,
            "last_successful_send": time.time(),
        }
        successful = self._metrics.get("successful_sends", 0) + 1
        self._metrics["successful_sends"] = successful
        current_avg = float(self._metrics.get("avg_latency", 0.0))
        self._metrics["avg_latency"] = ((current_avg * (successful - 1)) + duration_ms) / successful

    def _record_failure(self, error: Exception) -> None:
        failures = int(self._health.get("consecutive_failures", 0)) + 1
        self._health = {
            "healthy": False,
            "consecutive_failures": failures,
            "error_message": str(error),
        }
        self._metrics["failed_sends"] = self._metrics.get("failed_sends", 0) + 1

    def _update_compression_metrics(self, duration_ms: float, raw_size: int, compressed_size: int) -> None:
        successful = max(1, self._metrics.get("successful_sends", 1))
        current_time = float(self._metrics.get("avg_compression_time", 0.0))
        self._metrics["avg_compression_time"] = (
            (current_time * (successful - 1)) + duration_ms
        ) / successful

        ratio = compressed_size / raw_size if raw_size > 0 else 1.0
        current_ratio = float(self._metrics.get("avg_compression_ratio", 0.0))
        self._metrics["avg_compression_ratio"] = (
            (current_ratio * (successful - 1)) + ratio
        ) / successful

    def _format_payload(self, entries: list[LogEntryEntity]) -> dict[str, Any]:
        streams: dict[str, dict[str, Any]] = {}
        values: dict[str, list[dict[str, Any]]] = {}

        for entry in entries:
            labels = entry.labels or {}
            key = json.dumps(labels, sort_keys=True)
            if key not in streams:
                streams[key] = labels
                values[key] = []
            values[key].append(
                {
                    "timestamp": entry.timestamp,
                    "line": json.dumps(
                        {
                            "level": entry.level,
                            "message": entry.message,
                            "context": entry.context,
                            "traceId": entry.trace_id,
                            "spanId": entry.span_id,
                            "requestId": entry.request_id,
                            "metadata": entry.metadata,
                        },
                        separators=(",", ":"),
                    ),
                }
            )

        return {
            "streams": [
                {
                    "labels": stream_labels,
                    "entries": values[key],
                }
                for key, stream_labels in streams.items()
            ]
        }
