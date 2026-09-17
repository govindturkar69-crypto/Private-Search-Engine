"""Bounded performance telemetry and query latency monitoring.

Preserves privacy by never storing or logging raw query text.
"""

from collections import deque
from dataclasses import dataclass
import logging
import math
import threading
import time
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class PerformanceMetricsCollector:
    """Bounded, thread-safe metrics collector for search latency and cache efficacy.

    Uses a fixed-size collections.deque to maintain a sliding window of recent
    query latencies without unbounded memory growth.
    """

    def __init__(self, max_samples: int = 1000) -> None:
        self.max_samples = max(1, max_samples)
        self._latencies: deque = deque(maxlen=self.max_samples)
        self._total_queries = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._errors = 0
        self._start_time = time.monotonic()
        self._lock = threading.Lock()

    def record_query(self, duration_ms: float, cache_hit: bool = False) -> None:
        """Record query latency and cache hit/miss status.

        Crucially, zero raw query text is stored to uphold privacy guarantees.
        """
        with self._lock:
            self._latencies.append(max(0.0, float(duration_ms)))
            self._total_queries += 1
            if cache_hit:
                self._cache_hits += 1
            else:
                self._cache_misses += 1

    def record_error(self) -> None:
        """Record an API or execution error."""
        with self._lock:
            self._errors += 1

    def get_percentiles(self) -> Dict[str, float]:
        """Compute p50, p95, and p99 query latency percentiles from sample window."""
        with self._lock:
            samples = list(self._latencies)

        if not samples:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}

        sorted_samples = sorted(samples)
        n = len(sorted_samples)

        if n == 1:
            val = round(sorted_samples[0], 2)
            return {"p50": val, "p95": val, "p99": val}

        def _calc_p(p: float) -> float:
            k = (n - 1) * p
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return float(sorted_samples[int(k)])
            d0 = sorted_samples[int(f)] * (c - k)
            d1 = sorted_samples[int(c)] * (k - f)
            return float(d0 + d1)

        return {
            "p50": round(_calc_p(0.50), 2),
            "p95": round(_calc_p(0.95), 2),
            "p99": round(_calc_p(0.99), 2),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Return comprehensive query performance and telemetry statistics."""
        with self._lock:
            uptime = round(time.monotonic() - self._start_time, 1)
            total = self._total_queries
            hits = self._cache_hits
            misses = self._cache_misses
            errors = self._errors
            sample_count = len(self._latencies)

        cache_total = hits + misses
        hit_rate = round((hits / cache_total) * 100, 2) if cache_total > 0 else 0.0
        error_rate = round((errors / total) * 100, 2) if total > 0 else 0.0
        percentiles = self.get_percentiles()

        return {
            "total_queries": total,
            "cache_hits": hits,
            "cache_misses": misses,
            "cache_hit_rate_pct": hit_rate,
            "error_count": errors,
            "error_rate_pct": error_rate,
            "sample_window_size": sample_count,
            "max_sample_window": self.max_samples,
            "latency_percentiles_ms": percentiles,
            "uptime_seconds": uptime,
        }

    def reset(self) -> None:
        """Reset all metrics and flush sample window."""
        with self._lock:
            self._latencies.clear()
            self._total_queries = 0
            self._cache_hits = 0
            self._cache_misses = 0
            self._errors = 0
            self._start_time = time.monotonic()


@dataclass
class PerformanceAlert:
    """Configurable informational alert checker for service performance degradation."""

    max_p95_latency_ms: float = 500.0
    max_error_rate_pct: float = 5.0
    min_cache_hit_rate_pct: float = 50.0

    def check_alerts(self, stats: Dict[str, Any]) -> List[str]:
        """Check performance stats against thresholds and return warning notices."""
        alerts: List[str] = []
        p95 = stats.get("latency_percentiles_ms", {}).get("p95", 0.0)
        if p95 > self.max_p95_latency_ms:
            alerts.append(
                f"High p95 query latency: {p95}ms exceeds threshold of "
                f"{self.max_p95_latency_ms}ms"
            )

        err_rate = stats.get("error_rate_pct", 0.0)
        if stats.get("total_queries", 0) >= 20 and err_rate > self.max_error_rate_pct:
            alerts.append(
                f"Elevated error rate: {err_rate}% exceeds threshold of "
                f"{self.max_error_rate_pct}%"
            )

        total_cached_queries = stats.get("cache_hits", 0) + stats.get("cache_misses", 0)
        hit_rate = stats.get("cache_hit_rate_pct", 0.0)
        if total_cached_queries >= 50 and hit_rate < self.min_cache_hit_rate_pct:
            alerts.append(
                f"Low cache hit rate: {hit_rate}% is below threshold of "
                f"{self.min_cache_hit_rate_pct}%"
            )

        return alerts
