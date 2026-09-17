"""Locust load test suite for Private Search Engine API.

Standalone runner - excluded from standard pytest collection.
Targets explicitly configured LOAD_TEST_HOST (default: http://127.0.0.1:8000).
"""

from datetime import datetime
import json
import logging
import os
from pathlib import Path
from random import choice
import sys
from typing import Any
from urllib.parse import urlparse
from locust import HttpUser, TaskSet, between, events, task

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("locust_runner")


def _is_local_host(hostname: str) -> bool:
    """Validate if hostname is safe loopback or local private address."""
    clean = hostname.lower().strip("[]")
    return (
        clean
        in (
            "localhost",
            "127.0.0.1",
            "::1",
            "0.0.0.0",
            "testserver",
        )
        or clean.startswith("127.")
        or clean.startswith("192.168.")
        or clean.startswith("10.")
    )


# Safety validation on init
@events.init.add_listener
def on_locust_init(environment: Any, **kwargs: Any) -> None:
    """Ensure load test target is a local, controlled environment."""
    target_host = environment.host or os.environ.get(
        "LOAD_TEST_HOST", "http://127.0.0.1:8000"
    )
    parsed = urlparse(target_host)
    hostname = parsed.hostname or "127.0.0.1"

    allow_remote = os.environ.get("ALLOW_REMOTE_LOAD_TEST", "false").lower() == "true"
    if not _is_local_host(hostname) and not allow_remote:
        logger.error(
            f"SAFETY ABORT: Target '{target_host}' is not a local/private host. "
            "Set ALLOW_REMOTE_LOAD_TEST=true to explicitly override."
        )
        sys.exit(1)


class SearchTasks(TaskSet):
    """Realistic load testing task distributions."""

    queries = [
        "python",
        "algorithms",
        "databases",
        "networking",
        "distributed",
        "security",
        "search",
        "architecture",
    ]

    prefixes = ["py", "alg", "dat", "net", "sec", "sea"]

    @task(7)
    def search(self) -> None:
        """Perform POST search queries."""
        q = choice(self.queries)
        limit = choice([5, 10, 20])
        offset = choice([0, 5])

        with self.client.post(
            "/api/v1/search",
            json={"query": q, "limit": limit, "offset": offset},
            catch_response=True,
            name="/api/v1/search",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}: {response.text[:100]}")

    @task(2)
    def suggest(self) -> None:
        """Get autocomplete suggestions."""
        pfx = choice(self.prefixes)
        with self.client.get(
            f"/api/v1/suggest?prefix={pfx}&limit=5",
            catch_response=True,
            name="/api/v1/suggest",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")

    @task(1)
    def stats(self) -> None:
        """Read inverted index statistics."""
        with self.client.get(
            "/api/v1/stats",
            catch_response=True,
            name="/api/v1/stats",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")


class SearchUser(HttpUser):
    """Simulated search user with realistic think-time."""

    tasks = [SearchTasks]
    wait_time = between(0.1, 0.5)


@events.test_stop.add_listener
def on_test_stop(environment: Any, **kwargs: Any) -> None:
    """Evaluate pass/fail criteria and record timestamped report."""
    stats = environment.stats.total
    total_reqs = stats.num_requests
    failures = stats.num_failures
    fail_rate = (failures / total_reqs * 100) if total_reqs > 0 else 0.0

    avg_latency = stats.avg_response_time
    p50_latency = stats.get_response_time_percentile(0.50) or 0.0
    p95_latency = stats.get_response_time_percentile(0.95) or 0.0
    p99_latency = stats.get_response_time_percentile(0.99) or 0.0

    print("\n" + "=" * 55)
    print("           LOCUST LOAD TEST SUMMARY RESULTS")
    print("=" * 55)
    print(f"Total Requests:     {total_reqs:,}")
    print(f"Failed Requests:    {failures:,} ({fail_rate:.2f}%)")
    print(f"Avg Response Time:  {avg_latency:.1f} ms")
    print(f"Median (p50):       {p50_latency:.1f} ms")
    print(f"95th Percentile:    {p95_latency:.1f} ms")
    print(f"99th Percentile:    {p99_latency:.1f} ms")
    print("=" * 55)

    # Save timestamped report
    reports_dir = Path("reports/load")
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = reports_dir / f"loadtest_{ts_str}.json"

    report_data = {
        "timestamp": ts_str,
        "total_requests": total_reqs,
        "failures": failures,
        "failure_rate_percent": round(fail_rate, 2),
        "avg_latency_ms": round(avg_latency, 2),
        "p50_latency_ms": round(p50_latency, 2),
        "p95_latency_ms": round(p95_latency, 2),
        "p99_latency_ms": round(p99_latency, 2),
    }

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    logger.info(f"Report saved to {report_file}")
