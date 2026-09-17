"""Production smoke test utility for deployed Private Search Engine instances.

Validates:
- Liveness probe: GET /health
- Readiness probe: GET /api/v1/health
- Search API functional path: POST /api/v1/search
- Prometheus exposition: GET /metrics
- Optional rate limiting verification: --test-rate-limit
"""

import argparse
import json
import logging
import sys
import urllib.error
import urllib.request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("smoke_test")


def test_liveness(base_url: str) -> bool:
    """Test top-level liveness probe."""
    url = f"{base_url.rstrip('/')}/health"
    logger.info(f"Probing liveness: {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SmokeTest/1.0"})
        with urllib.request.urlopen(req, timeout=5) as res:
            status = res.getcode()
            body = res.read().decode("utf-8")
            if status == 200 and "ok" in body:
                logger.info("  PASS: /health returned 200 OK")
                return True
            logger.error(f"  FAIL: /health returned status={status}, body={body}")
            return False
    except Exception as exc:
        logger.error(f"  FAIL: /health request error: {exc}")
        return False


def test_readiness(base_url: str) -> bool:
    """Test API component readiness probe."""
    url = f"{base_url.rstrip('/')}/api/v1/health"
    logger.info(f"Probing readiness: {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SmokeTest/1.0"})
        with urllib.request.urlopen(req, timeout=5) as res:
            status = res.getcode()
            body = res.read().decode("utf-8")
            if status == 200:
                logger.info(f"  PASS: /api/v1/health returned 200 OK ({body.strip()})")
                return True
            logger.error(f"  FAIL: /api/v1/health status={status}, body={body}")
            return False
    except Exception as exc:
        logger.error(f"  FAIL: /api/v1/health request error: {exc}")
        return False


def test_search_endpoint(base_url: str) -> bool:
    """Test search endpoint with a read-only query."""
    url = f"{base_url.rstrip('/')}/api/v1/search"
    payload = json.dumps({"query": "python", "page": 1, "page_size": 5}).encode("utf-8")
    logger.info(f"Testing search API: {url}")
    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "SmokeTest/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as res:
            status = res.getcode()
            data = json.loads(res.read().decode("utf-8"))
            if status == 200 and "results" in data and "total_available" in data:
                logger.info(
                    f"  PASS: /api/v1/search returned 200 OK "
                    f"(results={len(data['results'])}, "
                    f"total_available={data['total_available']})"
                )
                return True
            logger.error(f"  FAIL: /api/v1/search returned invalid payload: {data}")
            return False
    except Exception as exc:
        logger.error(f"  FAIL: /api/v1/search request error: {exc}")
        return False


def test_metrics_endpoint(base_url: str) -> bool:
    """Test Prometheus metrics exposition format."""
    url = f"{base_url.rstrip('/')}/metrics"
    logger.info(f"Probing metrics endpoint: {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SmokeTest/1.0"})
        with urllib.request.urlopen(req, timeout=5) as res:
            status = res.getcode()
            content = res.read().decode("utf-8")
            if status == 200 and "http_requests_total" in content:
                logger.info("  PASS: /metrics returned 200 with Prometheus text")
                return True
            logger.error("  FAIL: /metrics missing expected counters")
            return False
    except Exception as exc:
        logger.error(f"  FAIL: /metrics request error: {exc}")
        return False


def test_rate_limiting(base_url: str) -> bool:
    """Optionally test rate limiting trigger."""
    url = f"{base_url.rstrip('/')}/api/v1/health"
    logger.info(f"Testing rate limiting enforcement against: {url}")
    hit_429 = False
    for i in range(120):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "RateLimitTest/1.0"}
            )
            with urllib.request.urlopen(req, timeout=2) as res:
                if res.getcode() == 429:
                    hit_429 = True
                    break
        except urllib.error.HTTPError as err:
            if err.code == 429:
                hit_429 = True
                break
        except Exception:
            pass

    if hit_429:
        logger.info("  PASS: Rate limiter correctly enforced HTTP 429")
        return True
    logger.warning("  WARNING: Did not trigger HTTP 429 within 120 requests")
    return False


def main() -> None:
    """Run production smoke test suite."""
    parser = argparse.ArgumentParser(description="Production Deployment Smoke Tests")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of search engine instance (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--test-rate-limit",
        action="store_true",
        help="Execute rate limit burst verification",
    )
    args = parser.parse_args()

    logger.info(f"Starting production smoke tests against: {args.base_url}")
    results = [
        ("Liveness (/health)", test_liveness(args.base_url)),
        ("Readiness (/api/v1/health)", test_readiness(args.base_url)),
        ("Search (/api/v1/search)", test_search_endpoint(args.base_url)),
        ("Metrics (/metrics)", test_metrics_endpoint(args.base_url)),
    ]

    if args.test_rate_limit:
        results.append(("Rate Limiting", test_rate_limiting(args.base_url)))

    failed = [name for name, success in results if not success]

    print("\n" + "=" * 60)
    print("SMOKE TEST SUMMARY")
    print("=" * 60)
    for name, success in results:
        status_str = "PASS" if success else "FAIL"
        print(f"  [{status_str}] {name}")
    print("=" * 60)

    if failed:
        logger.error(f"Smoke test suite FAILED: {', '.join(failed)}")
        sys.exit(1)

    logger.info("All smoke test checks PASSED successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()
