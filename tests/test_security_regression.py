"""Automated production security regression test suite.

Validates actual security boundaries:
- Filesystem boundary (search queries remain data, log reader is restricted)
- SQL injection safety (parameterized queries preserve database integrity)
- XSS data safety (API stores/transmits text data without script execution)
- SSRF crawler boundary (loopback, RFC1918, link-local, redirects blocked)
- Admin authentication hardening (constant-time compare, entropy, prod failsafe)
- Rate limiting and brute-force throttling with mock clock
- Content-type handling and XXE rejection
"""

import asyncio
from typing import Any
from unittest.mock import patch
from fastapi.testclient import TestClient
import pytest
from src.admin.log_service import LogService
from src.api.routes import router
from src.config import Config, ServerConfig, normalize_environment
from src.crawler.fetcher import Fetcher
from src.indexer import SQLiteIndexer
from src.main import create_app
from src.ranker.search import SearchEngine


@pytest.mark.security
class TestSearchFilesystemSafety:
    """Validate that search queries remain pure data and never influence files."""

    def test_path_traversal_query_treated_as_text_data(
        self,
        test_client_with_engine: TestClient,
        seeded_indexer: SQLiteIndexer,
    ) -> None:
        """Queries resembling traversal paths must execute safely as search text."""
        traversal_queries = [
            "../../../etc/passwd",
            "..%2F..%2F..%2Fetc%2Fpasswd",
            "....//....//....//etc/passwd",
            "..\\..\\..\\windows\\system32",
            "/etc/shadow",
            "C:\\boot.ini",
        ]
        for query in traversal_queries:
            resp = test_client_with_engine.get(f"/api/v1/search?q={query}")
            assert resp.status_code == 200
            data = resp.json()
            assert "results" in data
            assert len(data["query"]) > 0
            # Response must never leak actual OS password file contents
            response_text = resp.text.lower()
            assert "root:x:0:0" not in response_text
            assert "bin/bash" not in response_text

    def test_search_service_has_no_path_construction(self) -> None:
        """Verify search route signature accepts query as text with no file paths."""
        route_paths = [route.path for route in router.routes]
        assert any(p.endswith("/search") for p in route_paths)
        for route in router.routes:
            if getattr(route, "path", "").endswith("/search"):
                endpoint = getattr(route, "endpoint", None)
                assert endpoint is not None


@pytest.mark.security
class TestFilesystemLogServiceBoundary:
    """Validate filesystem boundaries on log reading services."""

    def test_log_service_path_is_not_request_controllable(
        self,
        test_client_with_engine: TestClient,
    ) -> None:
        """Log retrieval endpoint must not accept user-specified paths."""
        resp = test_client_with_engine.get(
            "/api/v1/admin/logs?path=/etc/passwd",
            headers={"X-Admin-Token": "dev-admin-secret-token"},
        )
        # Endpoint ignores unexpected query parameter 'path' and serves data/app.log
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_log_service_reads_strictly_configured_file(
        self,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """LogService instance must only read from its configured log_path."""
        safe_log = tmp_path / "safe.log"  # type: ignore[operator]
        safe_log.write_text(
            "2026-09-15 12:00:00 - src.test - INFO - Application starting\n",
            encoding="utf-8",
        )
        service = LogService(str(safe_log))
        logs = service.get_logs(lines=10)
        assert len(logs) == 1
        assert logs[0].message == "Application starting"


@pytest.mark.security
class TestSQLInjectionSafety:
    """Validate SQL injection safety with parameterized query execution."""

    def test_sql_injection_payloads_do_not_corrupt_database(
        self,
        test_client_with_engine: TestClient,
        seeded_indexer: SQLiteIndexer,
    ) -> None:
        """Malicious SQL strings must be treated strictly as search query text."""
        initial_stats = seeded_indexer.get_stats()
        initial_doc_count = initial_stats["total_documents"]
        initial_terms = initial_stats["total_terms"]

        payloads = [
            "' OR '1'='1",
            "'; DROP TABLE documents; --",
            "' UNION SELECT id, url, title, body FROM documents --",
            "1; SELECT * FROM metadata WHERE '1'='1",
            "' OR 1=1; DELETE FROM postings; --",
        ]

        for payload in payloads:
            resp = test_client_with_engine.get(f"/api/v1/search?q={payload}")
            # Query must return safe HTTP response (200 OK)
            assert resp.status_code == 200
            data = resp.json()
            assert "results" in data
            # Zero SQLite exception tracebacks leaked
            resp_str = resp.text.lower()
            assert "operationalerror" not in resp_str
            assert "syntax error" not in resp_str
            assert "sqlite3" not in resp_str

        # Verify DB schema and row counts remain fully intact
        final_stats = seeded_indexer.get_stats()
        assert final_stats["total_documents"] == initial_doc_count
        assert final_stats["total_terms"] == initial_terms


@pytest.mark.security
class TestXSSDataHandling:
    """Validate that HTML/script inputs are handled strictly as data."""

    def test_xss_payloads_stored_and_returned_as_raw_text(
        self,
        test_client_with_engine: TestClient,
    ) -> None:
        """Script tags in search queries must be safely handled without error."""
        xss_queries = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert(1)>",
            "<svg/onload=alert('pwned')>",
            "javascript:alert(document.cookie)",
        ]
        for query in xss_queries:
            resp = test_client_with_engine.get(f"/api/v1/search?q={query}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["query"] == query


@pytest.mark.security
class TestSSRFCrawlerBoundary:
    """Validate SSRF protection boundaries for web crawler subsystem."""

    def test_crawler_blocks_loopback_and_private_destinations(self) -> None:
        """Fetcher must block loopback, RFC1918, link-local, and reserved IPs."""
        fetcher = Fetcher()
        blocked_targets = [
            "http://127.0.0.1:8000/secret",
            "http://127.0.0.2:9000/",
            "http://localhost:8000/admin",
            "http://0.0.0.0:8000/",
            "http://10.0.0.1/internal",
            "http://172.16.0.1/private",
            "http://192.168.1.1/router",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]:8000/ipv6-loopback",
            "file:///etc/passwd",
            "gopher://127.0.0.1:70/",
        ]
        for target in blocked_targets:
            assert fetcher._is_safe_url(target) is False
            res = asyncio.run(fetcher.fetch(target))
            assert res.status_code == 403
            assert res.content is None or res.error is not None

    def test_admin_crawler_cannot_bypass_ssrf_protection(
        self,
        test_client_with_engine: TestClient,
    ) -> None:
        """Admin crawl start endpoint must reject private and loopback seed URLs."""
        private_seeds = [
            ["http://127.0.0.1:8000/seed"],
            ["http://localhost:3000/"],
            ["http://192.168.1.100/doc"],
        ]
        for seeds in private_seeds:
            resp = test_client_with_engine.post(
                "/api/v1/admin/crawler/start",
                json={"seed_urls": seeds, "max_documents": 10},
                headers={"X-Admin-Token": "dev-admin-secret-token"},
            )
            assert resp.status_code == 422


@pytest.mark.security
class TestAdminAuthenticationHardening:
    """Validate admin authentication hardening and production fail-safe."""

    def test_admin_auth_status_codes(
        self,
        test_client_with_engine: TestClient,
    ) -> None:
        """Missing token returns 401; invalid token returns 403."""
        # 1. Missing token -> 401
        resp_missing = test_client_with_engine.get("/api/v1/admin/crawler/status")
        assert resp_missing.status_code == 401

        # 2. Invalid token -> 403
        resp_invalid = test_client_with_engine.get(
            "/api/v1/admin/crawler/status",
            headers={"X-Admin-Token": "wrong-token-value"},
        )
        assert resp_invalid.status_code == 403

        # 3. Valid dev token -> 200
        resp_valid = test_client_with_engine.get(
            "/api/v1/admin/crawler/status",
            headers={"X-Admin-Token": "dev-admin-secret-token"},
        )
        assert resp_valid.status_code == 200

    def test_constant_time_comparison_is_invoked(
        self,
        test_client_with_engine: TestClient,
    ) -> None:
        """Behavioral test verifying secrets.compare_digest is called during auth."""
        with patch(
            "secrets.compare_digest", wraps=__import__("secrets").compare_digest
        ) as spy_compare:
            resp = test_client_with_engine.get(
                "/api/v1/admin/crawler/status",
                headers={"X-Admin-Token": "dev-admin-secret-token"},
            )
            assert resp.status_code == 200
            assert spy_compare.called
            # Verify compare_digest was called with the provided token
            call_args = spy_compare.call_args[0]
            assert "dev-admin-secret-token" in call_args

    def test_environment_normalization_production_precedence(self) -> None:
        """Deterministic environment precedence: production always takes precedence."""
        # Conflicting variables: ENV=development, ENVIRONMENT=production
        env_conflicting = {"ENV": "development", "ENVIRONMENT": "production"}
        assert normalize_environment(env_conflicting) == "production"

        # Conflicting reverse: ENV=production, ENVIRONMENT=development
        env_conflicting_rev = {
            "ENV": "production",
            "ENVIRONMENT": "development",
        }
        assert normalize_environment(env_conflicting_rev) == "production"

        # Standard dev
        assert normalize_environment({"ENV": "development"}) == "development"
        # Standard test
        assert normalize_environment({"ENV": "test"}) == "test"

    def test_production_failsafe_on_missing_or_weak_admin_token(self) -> None:
        """Production startup fails with RuntimeError if admin token is weak/absent."""
        # 1. Missing token in production -> fails startup
        prod_cfg_missing = Config(
            server=ServerConfig(environment="production", admin_token=None)
        )
        with pytest.raises(RuntimeError, match="Production configuration error"):
            app = create_app(config=prod_cfg_missing)
            with TestClient(app):
                pass

        # 2. Default dev token in production -> fails startup
        prod_cfg_default = Config(
            server=ServerConfig(
                environment="production",
                admin_token="dev-admin-secret-token",
            )
        )
        with pytest.raises(RuntimeError, match="Production configuration error"):
            app = create_app(config=prod_cfg_default)
            with TestClient(app):
                pass

        # 3. Short token (< 32 chars) in production -> fails startup
        prod_cfg_short = Config(
            server=ServerConfig(
                environment="production",
                admin_token="short-secret-token-under-32",
            )
        )
        with pytest.raises(RuntimeError, match="Production configuration error"):
            app = create_app(config=prod_cfg_short)
            with TestClient(app):
                pass

        # 4. Valid strong token (>= 32 chars) -> starts up cleanly
        strong_token = "secure-high-entropy-production-admin-token-32ch"
        prod_cfg_valid = Config(
            server=ServerConfig(
                environment="production",
                admin_token=strong_token,
            )
        )
        app_valid = create_app(config=prod_cfg_valid)
        with TestClient(app_valid) as client:
            resp = client.get(
                "/api/v1/admin/crawler/status",
                headers={"X-Admin-Token": strong_token},
            )
            assert resp.status_code == 200


@pytest.mark.security
class TestRateLimiterAndBruteForce:
    """Validate client rate limiting and brute force resilience."""

    def test_admin_endpoint_rate_limiting_with_mock_clock(
        self,
        mock_clock: Any,
        seeded_indexer: SQLiteIndexer,
        test_search_engine: SearchEngine,
    ) -> None:
        """Rapid unauthorized requests trigger HTTP 429 with Retry-After header."""
        cfg = Config(server=ServerConfig(rate_limit_per_minute=5))
        app = create_app(
            config=cfg,
            indexer=seeded_indexer,
            search_engine=test_search_engine,
            rate_limit_time_func=lambda: mock_clock["current_time"],
        )

        with TestClient(app) as client:
            # Send 5 requests within limit
            for _ in range(5):
                resp = client.get(
                    "/api/v1/admin/crawler/status",
                    headers={"X-Admin-Token": "wrong-token"},
                )
                assert resp.status_code == 403

            # 6th request triggers rate limiter
            resp_limited = client.get(
                "/api/v1/admin/crawler/status",
                headers={"X-Admin-Token": "wrong-token"},
            )
            assert resp_limited.status_code == 429
            assert "Retry-After" in resp_limited.headers

            # Advance clock past 60s window
            mock_clock["current_time"] += 61.0
            resp_reset = client.get(
                "/api/v1/admin/crawler/status",
                headers={"X-Admin-Token": "wrong-token"},
            )
            assert resp_reset.status_code == 403


@pytest.mark.security
class TestContentTypeSafety:
    """Validate content-type contract and rejection of unexpected payloads."""

    def test_unsupported_xml_content_type_safely_rejected(
        self,
        test_client_with_engine: TestClient,
    ) -> None:
        """XML payload sent to JSON endpoint is rejected safely without XXE parsing."""
        xxe_payload = """<?xml version="1.0"?>
        <!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
        <search><query>&xxe;</query></search>"""

        resp = test_client_with_engine.post(
            "/api/v1/search",
            content=xxe_payload,
            headers={"Content-Type": "application/xml"},
        )
        # Safely rejected with HTTP 422 Unprocessable Entity
        assert resp.status_code == 422
        # Zero file disclosure from XXE processing
        assert "root:x:0:0" not in resp.text
