from __future__ import annotations

from statistics import mean
from time import time


class MetricsCollector:
    def __init__(self, max_samples: int = 10_000) -> None:
        self._latencies: list[float] = []
        self._compression_ratios: list[float] = []
        self._compression_times: list[float] = []
        self._operation_timestamps: list[float] = []
        self._total_original_bytes = 0
        self._total_compressed_bytes = 0
        self._max_samples = max_samples

    def record_latency(self, ms: float) -> None:
        self._latencies.append(ms)
        self._operation_timestamps.append(time())

        if len(self._latencies) > self._max_samples:
            self._latencies.pop(0)
        if len(self._operation_timestamps) > self._max_samples:
            self._operation_timestamps.pop(0)

    def record_compression(self, original_size: int, compressed_size: int, time_ms: float) -> None:
        self._total_original_bytes += original_size
        self._total_compressed_bytes += compressed_size

        if original_size > 0:
            ratio = (1 - compressed_size / original_size) * 100
            self._compression_ratios.append(ratio)
            if len(self._compression_ratios) > self._max_samples:
                self._compression_ratios.pop(0)

        self._compression_times.append(time_ms)
        if len(self._compression_times) > self._max_samples:
            self._compression_times.pop(0)

    def get_latency_metrics(self) -> dict[str, float]:
        if not self._latencies:
            return {
                "p50": 0.0,
                "p95": 0.0,
                "p99": 0.0,
                "p999": 0.0,
                "min": 0.0,
                "max": 0.0,
                "avg": 0.0,
                "count": 0.0,
            }

        sorted_values = sorted(self._latencies)
        count = len(sorted_values)

        return {
            "p50": self._get_percentile(sorted_values, 50),
            "p95": self._get_percentile(sorted_values, 95),
            "p99": self._get_percentile(sorted_values, 99),
            "p999": self._get_percentile(sorted_values, 99.9),
            "min": sorted_values[0],
            "max": sorted_values[-1],
            "avg": mean(sorted_values),
            "count": float(count),
        }

    def get_compression_metrics(self) -> dict[str, float | int]:
        avg_ratio = mean(self._compression_ratios) if self._compression_ratios else 0.0
        avg_time = mean(self._compression_times) if self._compression_times else 0.0

        return {
            "avg_ratio": avg_ratio,
            "avg_time": avg_time,
            "total_original_bytes": self._total_original_bytes,
            "total_compressed_bytes": self._total_compressed_bytes,
            "total_saved_bytes": self._total_original_bytes - self._total_compressed_bytes,
            "count": len(self._compression_ratios),
        }

    def get_throughput(self, window_seconds: int = 60) -> float:
        if window_seconds <= 0:
            return 0.0
        if not self._operation_timestamps:
            return 0.0

        now = time()
        window_start = now - window_seconds
        in_window = len([ts for ts in self._operation_timestamps if ts >= window_start])
        return in_window / window_seconds

    def reset(self) -> None:
        self._latencies.clear()
        self._compression_ratios.clear()
        self._compression_times.clear()
        self._operation_timestamps.clear()
        self._total_original_bytes = 0
        self._total_compressed_bytes = 0

    def _get_percentile(self, sorted_values: list[float], percentile: float) -> float:
        if not sorted_values:
            return 0.0
        index = int((percentile / 100) * len(sorted_values))
        bounded = min(max(index, 1), len(sorted_values)) - 1
        return sorted_values[bounded]
