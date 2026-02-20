from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast

import httpx

from ...config import ResolvedTransportConfig
from ...domain.entities import LogEntryEntity
from ...types import TransportHealth, TransportMetrics
from ..compression import CompressorConfig, CompressorFactory

try:
    import orjson  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - optional dependency
    orjson = None


@dataclass(slots=True)
class RetryableTransportError(Exception):
    message: str
    status_code: int | None = None
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


class LokiJsonTransport:
    def __init__(
        self,
        config: ResolvedTransportConfig,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._config = config
        self._extra_headers = extra_headers or {}
        self._timeout = config.timeout / 1000
        self._compression_threshold = config.compression_threshold
        self._compressor = CompressorFactory.create(
            config.compression,
            CompressorConfig(level=config.compression_level, threshold=config.compression_threshold),
        )
        limits = httpx.Limits(max_keepalive_connections=config.max_sockets, max_connections=config.max_sockets)
        self._client: httpx.Client | None = None
        if config.enable_connection_pooling:
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
            payload = self._format_for_loki(entries)
            raw_bytes = self._dumps(payload)
            raw_size = len(raw_bytes)

            body = raw_bytes
            compression_time = 0.0
            was_compressed = False
            if self._compressor.get_name() != "none" and raw_size >= self._compression_threshold:
                compression_start = time.perf_counter()
                body = self._compressor.compress(raw_bytes)
                compression_time = (time.perf_counter() - compression_start) * 1000
                was_compressed = True

            headers: dict[str, str] = {
                "Content-Type": "application/json",
                "X-Scope-OrgID": self._config.tenant_id,
                "User-Agent": "logs-interceptor-python/0.1.1",
                **self._extra_headers,
            }
            if self._config.auth_token:
                headers["Authorization"] = f"Bearer {self._config.auth_token}"
            if was_compressed:
                encoding = self._compressor.get_content_encoding()
                if encoding:
                    headers["Content-Encoding"] = encoding

            response = self._request(headers, body)

            if response.status_code >= 300:
                raise RetryableTransportError(
                    message=f"Loki responded with {response.status_code}: {response.text}",
                    status_code=response.status_code,
                    retryable=response.status_code == 429 or response.status_code >= 500,
                )

            latency = (time.perf_counter() - start) * 1000
            self._record_success(latency)
            self._metrics["total_bytes_sent"] = self._metrics.get("total_bytes_sent", 0) + len(body)
            self._metrics["total_bytes_compressed"] = self._metrics.get("total_bytes_compressed", 0) + raw_size

            if was_compressed:
                self._update_compression_metrics(compression_time, raw_size, len(body))
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

    def _format_for_loki(self, entries: list[LogEntryEntity]) -> dict[str, Any]:
        streams: dict[str, dict[str, Any]] = {}
        values_map: dict[str, list[list[str]]] = defaultdict(list)

        for entry in entries:
            labels = entry.labels or {}
            key = json.dumps(labels, sort_keys=True)

            payload: dict[str, Any] = {
                "id": entry.id,
                "level": entry.level,
                "message": entry.message,
                "context": entry.context,
            }
            if entry.trace_id:
                payload["traceId"] = entry.trace_id
            if entry.span_id:
                payload["spanId"] = entry.span_id
            if entry.request_id:
                payload["requestId"] = entry.request_id
            if entry.metadata:
                payload["metadata"] = entry.metadata

            timestamp_ns = self._timestamp_to_ns(entry.timestamp)
            values_map[key].append([str(timestamp_ns), self._dumps(payload).decode("utf-8")])
            streams[key] = labels

        formatted_streams: list[dict[str, Any]] = []
        for key, stream_labels in streams.items():
            values = values_map[key]
            values.sort(key=lambda item: item[0])
            formatted_streams.append({"stream": stream_labels, "values": values})

        return {"streams": formatted_streams}

    @staticmethod
    def _timestamp_to_ns(iso_timestamp: str) -> int:
        try:
            normalized = iso_timestamp.replace("Z", "+00:00")
            dt_obj = datetime.fromisoformat(normalized)
            if dt_obj.tzinfo is None:
                dt_obj = dt_obj.replace(tzinfo=timezone.utc)
            seconds = int(dt_obj.timestamp())
            return (seconds * 1_000_000_000) + (dt_obj.microsecond * 1000)
        except Exception:
            return int(time.time() * 1_000_000_000)

    @staticmethod
    def _dumps(payload: Any) -> bytes:
        if orjson is not None:
            return cast(bytes, orjson.dumps(payload))
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
