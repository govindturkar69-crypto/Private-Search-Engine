"""Prometheus metrics exporter for operational monitoring.

Uses an application-owned CollectorRegistry to ensure complete test isolation.
Centralizes HTTP request metrics, cache counters, and index gauges with bounded
cardinality and zero sensitive query or URL text in labels.
"""

from typing import Optional
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)


class PrometheusMetrics:
    """Manages Prometheus metrics with an isolated CollectorRegistry."""

    def __init__(self, registry: Optional[CollectorRegistry] = None) -> None:
        self.registry = registry or CollectorRegistry(auto_describe=True)

        self.http_requests_total = Counter(
            "http_requests_total",
            "Total count of HTTP requests processed by method, route, and status.",
            ["method", "handler", "status"],
            registry=self.registry,
        )

        self.http_request_duration_seconds = Histogram(
            "http_request_duration_seconds",
            "Histogram of HTTP request processing durations in seconds.",
            ["method", "handler"],
            buckets=[
                0.001,
                0.005,
                0.01,
                0.025,
                0.05,
                0.1,
                0.25,
                0.5,
                1.0,
                2.5,
                5.0,
                10.0,
            ],
            registry=self.registry,
        )

        self.cache_hits_total = Counter(
            "search_engine_cache_hits_total",
            "Total number of query cache hits.",
            registry=self.registry,
        )

        self.cache_misses_total = Counter(
            "search_engine_cache_misses_total",
            "Total number of query cache misses.",
            registry=self.registry,
        )

        self.indexed_documents = Gauge(
            "search_engine_indexed_documents",
            "Current number of indexed documents in the search index.",
            registry=self.registry,
        )

        self.unique_terms = Gauge(
            "search_engine_unique_terms",
            "Current number of unique vocabulary terms in the search index.",
            registry=self.registry,
        )

        self.index_generation = Gauge(
            "search_engine_index_generation",
            "Current transactional index generation counter.",
            registry=self.registry,
        )

    def record_request(
        self, method: str, handler: str, status: int, duration_sec: float
    ) -> None:
        """Record HTTP request metrics with bounded labels."""
        status_str = str(status)
        self.http_requests_total.labels(
            method=method, handler=handler, status=status_str
        ).inc()
        self.http_request_duration_seconds.labels(
            method=method, handler=handler
        ).observe(max(0.0, float(duration_sec)))

    def record_cache_hit(self) -> None:
        """Increment authoritative cache hit counter."""
        self.cache_hits_total.inc()

    def record_cache_miss(self) -> None:
        """Increment authoritative cache miss counter."""
        self.cache_misses_total.inc()

    def update_index_gauges(
        self, doc_count: int, term_count: int, generation: int
    ) -> None:
        """Update gauges from O(1) metadata without scanning SQLite."""
        self.indexed_documents.set(max(0, doc_count))
        self.unique_terms.set(max(0, term_count))
        self.index_generation.set(max(1, generation))

    def generate_exposition(self) -> bytes:
        """Generate Prometheus exposition plaintext format."""
        return generate_latest(self.registry)


__all__ = ["PrometheusMetrics", "CONTENT_TYPE_LATEST"]

