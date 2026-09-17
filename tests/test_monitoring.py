"""Unit tests for bounded performance telemetry, percentiles, and alerts."""

import concurrent.futures
import inspect
from src.monitoring.metrics import PerformanceAlert, PerformanceMetricsCollector


class TestPerformanceMetricsCollector:
    """Test suite for PerformanceMetricsCollector."""

    def test_bounded_sample_window(self) -> None:
        """Collector must strictly limit stored samples to max_samples."""
        collector = PerformanceMetricsCollector(max_samples=50)

        for i in range(150):
            collector.record_query(duration_ms=float(i), cache_hit=(i % 2 == 0))

        stats = collector.get_stats()
        assert stats["total_queries"] == 150
        assert stats["sample_window_size"] == 50
        assert stats["cache_hits"] == 75
        assert stats["cache_misses"] == 75
        assert stats["cache_hit_rate_pct"] == 50.0

    def test_percentiles_calculation_empty_and_single(self) -> None:
        """Percentile calculations must handle 0 and 1 sample boundary conditions."""
        collector = PerformanceMetricsCollector(max_samples=100)

        # 0 samples
        p_empty = collector.get_percentiles()
        assert p_empty == {"p50": 0.0, "p95": 0.0, "p99": 0.0}

        # 1 sample
        collector.record_query(duration_ms=42.5)
        p_single = collector.get_percentiles()
        assert p_single == {"p50": 42.5, "p95": 42.5, "p99": 42.5}

    def test_percentiles_calculation_uniform(self) -> None:
        """Verify standard quantile calculation with 100 uniform samples."""
        collector = PerformanceMetricsCollector(max_samples=100)
        for i in range(1, 101):
            collector.record_query(duration_ms=float(i))

        p = collector.get_percentiles()
        assert 49.0 <= p["p50"] <= 52.0
        assert 94.0 <= p["p95"] <= 96.0
        assert 98.0 <= p["p99"] <= 100.0

    def test_privacy_zero_query_text(self) -> None:
        """Verify API accepts no query text and collector maintains no query logs."""
        sig = inspect.signature(PerformanceMetricsCollector.record_query)
        params = list(sig.parameters.keys())
        assert "query" not in params
        assert "query_text" not in params

        collector = PerformanceMetricsCollector()
        collector.record_query(duration_ms=12.3, cache_hit=True)
        stats = collector.get_stats()
        # Verify no string containing query text appears in dictionary
        stats_str = str(stats)
        assert "query_text" not in stats_str

    def test_thread_safety_monitoring(self) -> None:
        """Verify concurrent multi-threaded recording without race conditions."""
        collector = PerformanceMetricsCollector(max_samples=200)
        num_threads = 6
        queries_per_thread = 100

        def worker(t_id: int) -> None:
            for i in range(queries_per_thread):
                collector.record_query(duration_ms=float(i), cache_hit=(i % 3 == 0))
                if i % 10 == 0:
                    collector.record_error()

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, t) for t in range(num_threads)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        stats = collector.get_stats()
        assert stats["total_queries"] == num_threads * queries_per_thread
        assert stats["sample_window_size"] == 200
        assert stats["error_count"] == num_threads * 10

    def test_performance_alerts(self) -> None:
        """Verify threshold evaluation for performance alerts."""
        alert_checker = PerformanceAlert(
            max_p95_latency_ms=100.0,
            max_error_rate_pct=5.0,
            min_cache_hit_rate_pct=50.0,
        )

        healthy_stats = {
            "total_queries": 100,
            "cache_hits": 60,
            "cache_misses": 40,
            "cache_hit_rate_pct": 60.0,
            "error_count": 1,
            "error_rate_pct": 1.0,
            "latency_percentiles_ms": {"p50": 10.0, "p95": 45.0, "p99": 80.0},
        }
        assert alert_checker.check_alerts(healthy_stats) == []

        degraded_stats = {
            "total_queries": 100,
            "cache_hits": 20,
            "cache_misses": 80,
            "cache_hit_rate_pct": 20.0,
            "error_count": 15,
            "error_rate_pct": 15.0,
            "latency_percentiles_ms": {"p50": 80.0, "p95": 250.0, "p99": 400.0},
        }
        alerts = alert_checker.check_alerts(degraded_stats)
        assert len(alerts) == 3
        assert any("latency" in a for a in alerts)
        assert any("error rate" in a for a in alerts)
        assert any("cache hit rate" in a for a in alerts)
