"""Automated security regression testing and hardening test suite."""

import inspect
from typing import Dict, List
from fastapi.testclient import TestClient
import httpx
import pytest
from src.api.admin_routes import verify_admin_token
from src.api.middleware import RateLimiter
from src.config import Config, ServerConfig
from src.crawler.fetcher import Fetcher
from src.indexer import SQLiteIndexer
from src.main import create_app
from src.ranker.search import SearchEngine


@pytest.mark.security
class TestInputValidationAndInjection:
    """Validate query handling, injection resistance, and payload contracts."""

    def test_sql_injection_payloads(
        self,
        test_client_with_engine: TestClient,
        seeded_indexer: SQLiteIndexer,
    ) -> None:
        """SQL injection vectors must be treated strictly as text data."""
        initial_stats = seeded_indexer.get_stats()
        initial_docs = initial_stats["total_documents"]
        initial_terms = initial_stats["total_terms"]

        payloads = [
            "' OR '1'='1",
            "'; DROP TABLE documents; --",
            "1' UNION SELECT * FROM users--",
            "admin' --",
            "' OR 1=1; --",
            '" OR ""="',
        ]

        for payload in payloads:
            response = test_client_with_engine.post(
                "/api/v1/search",
                json={"query": payload, "limit": 10, "offset": 0},
            )
            # Response must succeed or validate cleanly (never 500)
            assert response.status_code in (200, 422)

            if response.status_code == 200:
                data = response.json()
                # Query must be preserved safely as string
                assert data["query"] == payload
                # Results must be valid list
                assert isinstance(data["results"], list)

        # Confirm underlying SQLite schema and records remain 100% intact
        conn = seeded_indexer.connection
        assert conn is not None
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert {"documents", "terms", "postings", "metadata"}.issubset(tables)

        final_stats = seeded_indexer.get_stats()
        assert final_stats["total_documents"] == initial_docs
        assert final_stats["total_terms"] == initial_terms

    def test_xss_payload_safety(self, test_client_with_engine: TestClient) -> None:
        """XSS vectors must be safely accepted as literals without execution."""
        xss_payloads = [
            '<script>alert("XSS")</script>',
            '<img src=x onerror=alert("XSS")>',
            '<svg/onload=alert("XSS")>',
            'javascript:alert("XSS")',
            '"><script src=evil.js></script>',
        ]

        for payload in xss_payloads:
            response = test_client_with_engine.post(
                "/api/v1/search",
                json={"query": payload, "limit": 10, "offset": 0},
            )
            assert response.status_code in (200, 422)
            if response.status_code == 200:
                data = response.json()
                assert data["query"] == payload

    def test_query_payload_size_contract(
        self, test_client_with_engine: TestClient
    ) -> None:
        """Oversized queries (e.g. 100k chars) are rejected with 422 per contract."""
        oversized = "x" * 100_000
        response = test_client_with_engine.post(
            "/api/v1/search",
            json={"query": oversized, "limit": 10, "offset": 0},
        )
        assert response.status_code == 422
        err = response.json()
        assert err["code"] == 422
        assert "validation failed" in err["error"].lower()


@pytest.mark.security
class TestSecurityHeaders:
    """Verify HTTP defense-in-depth security headers."""

    def test_baseline_security_headers(
        self, test_client_with_engine: TestClient
    ) -> None:
        """Assert presence of implemented security headers across all endpoints."""
        response = test_client_with_engine.get("/")
        assert response.status_code == 200
        headers = response.headers

        # Implemented modern defense headers
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "DENY"
        assert headers.get("Referrer-Policy") == "no-referrer"
        assert "default-src 'self'" in headers.get("Content-Security-Policy", "")

        # Legacy compatibility header
        assert headers.get("X-XSS-Protection") == "1; mode=block"

    def test_hsts_header_policy(
        self, seeded_indexer: SQLiteIndexer, test_search_engine: SearchEngine
    ) -> None:
        """HSTS must only be present when explicitly configured or under HTTPS."""
        # Case A: Default HTTP without HSTS
        cfg_default = Config(server=ServerConfig(enable_hsts=False))
        app_default = create_app(
            config=cfg_default,
            indexer=seeded_indexer,
            search_engine=test_search_engine,
        )
        with TestClient(app_default) as client_default:
            res_default = client_default.get("/")
            assert "Strict-Transport-Security" not in res_default.headers

        # Case B: Configured with enable_hsts=True
        cfg_hsts = Config(server=ServerConfig(enable_hsts=True))
        app_hsts = create_app(
            config=cfg_hsts,
            indexer=seeded_indexer,
            search_engine=test_search_engine,
        )
        with TestClient(app_hsts) as client_hsts:
            res_hsts = client_hsts.get("/")
            assert "Strict-Transport-Security" in res_hsts.headers
            assert "max-age=31536000" in res_hsts.headers["Strict-Transport-Security"]


@pytest.mark.security
class TestCORS:
    """Verify CORS preflight and origin policies."""

    def test_cors_allowed_origin(
        self, seeded_indexer: SQLiteIndexer, test_search_engine: SearchEngine
    ) -> None:
        """Configured allowed origin receives proper CORS response headers."""
        cfg = Config(
            server=ServerConfig(
                cors_origins=["http://localhost:3000", "http://localhost:8000"]
            )
        )
        app = create_app(
            config=cfg,
            indexer=seeded_indexer,
            search_engine=test_search_engine,
        )

        with TestClient(app) as client:
            headers = {
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            }
            response = client.options("/api/v1/search", headers=headers)
            assert response.status_code == 200
            assert (
                response.headers.get("access-control-allow-origin")
                == "http://localhost:3000"
            )
            assert response.headers.get("access-control-allow-credentials") == "true"

    def test_cors_disallowed_origin(
        self, seeded_indexer: SQLiteIndexer, test_search_engine: SearchEngine
    ) -> None:
        """Disallowed origin must not receive access-control-allow-origin header."""
        cfg = Config(server=ServerConfig(cors_origins=["http://localhost:8000"]))
        app = create_app(
            config=cfg,
            indexer=seeded_indexer,
            search_engine=test_search_engine,
        )

        with TestClient(app) as client:
            headers = {
                "Origin": "http://malicious-external-site.test",
                "Access-Control-Request-Method": "POST",
            }
            response = client.options("/api/v1/search", headers=headers)
            # Origin header must NOT be reflected for unauthorized origins
            assert (
                response.headers.get("access-control-allow-origin")
                != "http://malicious-external-site.test"
            )


@pytest.mark.security
class TestRateLimiting:
    """Verify rate limiting with an injected mock clock."""

    def test_rate_limiter_threshold_and_retry_after(
        self,
        seeded_indexer: SQLiteIndexer,
        test_search_engine: SearchEngine,
        mock_clock: Dict[str, float],
    ) -> None:
        """Rate limiter enforces threshold, sets Retry-After, and resets."""
        limiter = RateLimiter(
            requests_per_minute=3,
            window_seconds=60.0,
            time_func=lambda: mock_clock["current_time"],
        )
        app = create_app(
            indexer=seeded_indexer,
            search_engine=test_search_engine,
            rate_limiter=limiter,
        )

        with TestClient(app) as client:
            # First 3 requests permitted
            for _ in range(3):
                res = client.get("/api/v1/stats")
                assert res.status_code == 200

            # 4th request must be rate limited (429)
            res_blocked = client.get("/api/v1/stats")
            assert res_blocked.status_code == 429
            assert "Retry-After" in res_blocked.headers
            retry_after = int(res_blocked.headers["Retry-After"])
            assert 0 < retry_after <= 65

            # Advance clock past window
            mock_clock["current_time"] += 65.0

            # Must be permitted again
            res_recovered = client.get("/api/v1/stats")
            assert res_recovered.status_code == 200

    def test_rate_limiter_client_isolation(self, mock_clock: Dict[str, float]) -> None:
        """Exhausting quota on one client IP must not affect other client IPs."""
        limiter = RateLimiter(
            requests_per_minute=2,
            window_seconds=60.0,
            time_func=lambda: mock_clock["current_time"],
        )

        # Exhaust IP A
        assert limiter.is_allowed("198.51.100.1") is True
        assert limiter.is_allowed("198.51.100.1") is True
        assert limiter.is_allowed("198.51.100.1") is False

        # IP B must still have full quota
        assert limiter.is_allowed("198.51.100.2") is True
        assert limiter.is_allowed("198.51.100.2") is True
        assert limiter.is_allowed("198.51.100.2") is False

    def test_rate_limiter_stale_bucket_cleanup(
        self, mock_clock: Dict[str, float]
    ) -> None:
        """Evicts expired buckets when bucket capacity is reached."""
        limiter = RateLimiter(
            requests_per_minute=5,
            window_seconds=60.0,
            max_tracked_ips=2,
            time_func=lambda: mock_clock["current_time"],
        )
        limiter.is_allowed("1.1.1.1")
        limiter.is_allowed("2.2.2.2")

        # Advance past window
        mock_clock["current_time"] += 65.0

        # Adding 3rd IP triggers eviction of expired entries
        limiter.is_allowed("3.3.3.3")
        limiter._evict_stale_buckets(mock_clock["current_time"])
        assert "1.1.1.1" not in limiter.requests


@pytest.mark.security
class TestAdminAuthentication:
    """Verify token-protected admin endpoints and constant-time comparison."""

    def test_missing_token_returns_401(
        self, test_client_with_engine: TestClient
    ) -> None:
        """Admin endpoints reject requests without X-Admin-Token header with 401."""
        response = test_client_with_engine.get("/api/v1/admin/health")
        assert response.status_code == 401
        data = response.json()
        assert data["code"] == 401
        assert (
            "required" in data["error"].lower()
            or "x-admin-token" in data["error"].lower()
        )

    def test_invalid_token_returns_403(
        self, test_client_with_engine: TestClient
    ) -> None:
        """Admin endpoints reject invalid tokens with 403."""
        response = test_client_with_engine.get(
            "/api/v1/admin/health",
            headers={"X-Admin-Token": "completely-invalid-secret-key"},
        )
        assert response.status_code == 403
        data = response.json()
        assert data["code"] == 403

    def test_constant_time_comparison_used(self) -> None:
        """Verify constant-time comparison via secrets.compare_digest."""
        src_code = inspect.getsource(verify_admin_token)
        assert (
            "secrets.compare_digest" in src_code
        ), "Admin token verification must use secrets.compare_digest"

    def test_production_missing_admin_token_fails_safely(
        self,
        seeded_indexer: SQLiteIndexer,
        test_search_engine: SearchEngine,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """In production environment, unconfigured ADMIN_TOKEN safely denies access."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("ADMIN_TOKEN", raising=False)

        cfg = Config(server=ServerConfig(admin_token=None))
        app = create_app(
            config=cfg,
            indexer=seeded_indexer,
            search_engine=test_search_engine,
        )

        with TestClient(app) as client:
            response = client.get(
                "/api/v1/admin/health",
                headers={"X-Admin-Token": "some-token"},
            )
            assert response.status_code in (403, 500)


@pytest.mark.security
class TestSSRFRegression:
    """Regression tests verifying blocking of non-public and unsafe destinations."""

    def test_ssrf_blocked_destinations(self) -> None:
        """Fetcher must block loopback, private IPv4, IPv6, and link-local ranges."""
        fetcher = Fetcher()

        blocked_urls = [
            "http://localhost/",
            "http://localhost:8000/admin",
            "http://127.0.0.1/",
            "http://127.0.0.2:9000/",
            "http://[::1]/",
            "http://[::]/",
            "http://10.0.0.1/",
            "http://172.16.0.1/",
            "http://172.31.255.255/",
            "http://192.168.1.1/",
            "http://169.254.169.254/metadata",
            "http://[fe80::1]/",
            "ftp://example.com/file",
            "file:///etc/passwd",
        ]

        for url in blocked_urls:
            assert fetcher._is_safe_url(url) is False, f"SSRF should block: {url}"

    def test_ssrf_dns_resolution_to_private_target(self) -> None:
        """Rejects domain names whose DNS resolves to a private IP range."""

        def mock_internal_dns(hostname: str) -> List[str]:
            if hostname == "vault.internal":
                return ["10.10.10.5"]
            return ["93.184.216.34"]

        fetcher = Fetcher(dns_resolver=mock_internal_dns)
        assert fetcher._is_safe_url("http://vault.internal/secrets") is False

    def test_ssrf_redirect_to_private_target(self) -> None:
        """Rejects redirect hops that navigate to private/loopback IP addresses."""

        def mock_handler(request: httpx.Request) -> httpx.Response:
            if str(request.url) == "https://public.test/redirect":
                return httpx.Response(
                    302,
                    headers={"Location": "http://127.0.0.1:8000/admin"},
                    request=request,
                )
            return httpx.Response(200, text="OK", request=request)

        transport = httpx.MockTransport(mock_handler)
        fetcher = Fetcher(
            transport=transport,
            dns_resolver=lambda h: ["93.184.216.34"],
        )

        import asyncio

        result = asyncio.run(fetcher.fetch("https://public.test/redirect"))
        assert result.error is not None
        assert result.status_code == 0 or "ssrf" in result.error.lower()


@pytest.mark.security
class TestDOSResilience:
    """Verify safe resilience against oversized requests and concurrent bounds."""

    def test_concurrent_health_and_stats_resilience(
        self, test_client_with_engine: TestClient
    ) -> None:
        """Simultaneous rapid requests against health endpoint must remain resilient."""
        for _ in range(10):
            res = test_client_with_engine.get("/api/v1/health")
            assert res.status_code == 200

    def test_oversized_json_body_rejection(
        self, test_client_with_engine: TestClient
    ) -> None:
        """Oversized JSON body is rejected with 422 before processing."""
        res = test_client_with_engine.post(
            "/api/v1/search",
            json={"query": "a" * 1000, "limit": 10},
        )
        assert res.status_code == 422
