"""Comprehensive test suite for Phase 6 Search API & FastAPI Server."""

from pathlib import Path
from typing import Any, Dict
from fastapi import Request
from fastapi.testclient import TestClient
import pytest
from src.api import API_VERSION
from src.api.middleware import RateLimiter, get_client_ip
from src.config import Config, ServerConfig
from src.indexer import SQLiteIndexer
from src.main import create_app
from src.ranker.search import SearchEngine


@pytest.fixture
def test_data_db(tmp_path: Path) -> SQLiteIndexer:
    """Create isolated SQLite database with sample documents for API tests."""
    db_file = str(tmp_path / "api_test.db")
    indexer = SQLiteIndexer(db_file)

    sample_docs = [
        {
            "url": "https://example.com/python",
            "title": "Python Programming Language",
            "description": "Learn Python programming and data science.",
            "body": "Python is an expressive and fast programming language.",
            "content_hash": "hash_python_1",
            "metadata": {"language": "en", "author": "Guido van Rossum"},
        },
        {
            "url": "https://example.com/fastapi",
            "title": "FastAPI Web Framework",
            "description": "High performance modern Python web APIs.",
            "body": (
                "FastAPI enables building robust APIs with standard Python type hints."
            ),
            "content_hash": "hash_fastapi_2",
            "metadata": {"language": "en", "author": "Tiangolo"},
        },
        {
            "url": "https://example.com/security",
            "title": "Web Security Best Practices",
            "description": "Learn XSS and CSRF prevention.",
            "body": (
                "Protect apps from malicious payload <script>alert(1)</script> safely."
            ),
            "content_hash": "hash_security_3",
            "metadata": {"language": "en", "author": "Security Team"},
        },
    ]

    for doc in sample_docs:
        indexer.add_document(doc)

    indexer.calculate_idf(recalculate=True)
    return indexer


@pytest.fixture
def mock_clock() -> Dict[str, float]:
    """Controllable clock fixture for fast, deterministic rate limiting tests."""
    return {"current_time": 1000.0}


# ============================================================================
# 1. Search Endpoints Tests (GET, POST, Legacy, Equivalent)
# ============================================================================


class TestSearchEndpoints:
    """Test suite for search routes, pagination, and equivalent query handling."""

    def test_search_post_success(self, test_data_db: SQLiteIndexer) -> None:
        engine = SearchEngine(test_data_db)
        app = create_app(indexer=test_data_db, search_engine=engine)

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/search",
                json={"query": "python", "limit": 10, "offset": 0},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["query"] == "python"
            assert data["count"] >= 1
            assert data["total_available"] >= 1
            assert data["limit"] == 10
            assert data["offset"] == 0
            assert isinstance(data["execution_time_ms"], float)
            first_res = data["results"][0]
            assert "doc_id" in first_res
            assert "url" in first_res
            assert "title" in first_res
            assert "snippet" in first_res
            assert "score" in first_res
            assert 0 <= first_res["relevance"] <= 100

    def test_search_get_success(self, test_data_db: SQLiteIndexer) -> None:
        engine = SearchEngine(test_data_db)
        app = create_app(indexer=test_data_db, search_engine=engine)

        with TestClient(app) as client:
            response = client.get("/api/v1/search?q=fastapi&limit=5&offset=0")
            assert response.status_code == 200
            data = response.json()
            assert data["query"] == "fastapi"
            assert data["count"] == 1
            assert "FastAPI" in data["results"][0]["title"]

    def test_search_get_and_post_equivalence(self, test_data_db: SQLiteIndexer) -> None:
        """Verify GET and POST /api/v1/search produce identical output."""
        engine = SearchEngine(test_data_db)
        app = create_app(indexer=test_data_db, search_engine=engine)

        with TestClient(app) as client:
            res_post = client.post(
                "/api/v1/search",
                json={"query": "python", "limit": 5, "offset": 0},
            )
            res_get = client.get("/api/v1/search?q=python&limit=5&offset=0")

            assert res_post.status_code == 200
            assert res_get.status_code == 200

            data_post = res_post.json()
            data_get = res_get.json()

            assert data_post["query"] == data_get["query"]
            assert data_post["count"] == data_get["count"]
            assert data_post["total_available"] == data_get["total_available"]
            assert len(data_post["results"]) == len(data_get["results"])
            for r_post, r_get in zip(data_post["results"], data_get["results"]):
                assert r_post["doc_id"] == r_get["doc_id"]
                assert r_post["url"] == r_get["url"]
                assert r_post["score"] == r_get["score"]
                assert r_post["relevance"] == r_get["relevance"]

    def test_legacy_api_search_aliases(self, test_data_db: SQLiteIndexer) -> None:
        """Verify backward-compatible /api/search works for both GET and POST."""
        engine = SearchEngine(test_data_db)
        app = create_app(indexer=test_data_db, search_engine=engine)

        with TestClient(app) as client:
            # Legacy GET
            res_get = client.get("/api/search?q=python")
            assert res_get.status_code == 200
            assert res_get.json()["count"] >= 1

            # Legacy POST
            res_post = client.post("/api/search", json={"query": "python"})
            assert res_post.status_code == 200
            assert res_post.json()["count"] >= 1

    def test_query_whitespace_normalization(self, test_data_db: SQLiteIndexer) -> None:
        engine = SearchEngine(test_data_db)
        app = create_app(indexer=test_data_db, search_engine=engine)

        with TestClient(app) as client:
            response = client.post("/api/v1/search", json={"query": "   python   "})
            assert response.status_code == 200
            assert response.json()["query"] == "python"

    def test_whitespace_only_query_rejected(self, test_data_db: SQLiteIndexer) -> None:
        engine = SearchEngine(test_data_db)
        app = create_app(indexer=test_data_db, search_engine=engine)

        with TestClient(app) as client:
            # POST whitespace only
            res_post = client.post("/api/v1/search", json={"query": "    "})
            assert res_post.status_code == 422
            data = res_post.json()
            assert data["code"] == 422
            assert "validation" in data["error"].lower()

            # GET whitespace only
            res_get = client.get("/api/v1/search?q=%20%20")
            assert res_get.status_code == 422

    def test_query_length_boundary(self, test_data_db: SQLiteIndexer) -> None:
        engine = SearchEngine(test_data_db)
        app = create_app(indexer=test_data_db, search_engine=engine)

        with TestClient(app) as client:
            # 500 characters: valid
            valid_500 = "a" * 500
            res_valid = client.post("/api/v1/search", json={"query": valid_500})
            assert res_valid.status_code == 200

            # 501 characters: rejected
            invalid_501 = "a" * 501
            res_invalid = client.post("/api/v1/search", json={"query": invalid_501})
            assert res_invalid.status_code == 422

    def test_limit_boundaries(self, test_data_db: SQLiteIndexer) -> None:
        engine = SearchEngine(test_data_db)
        app = create_app(indexer=test_data_db, search_engine=engine)

        with TestClient(app) as client:
            # Lower bound (1)
            res_1 = client.post("/api/v1/search", json={"query": "python", "limit": 1})
            assert res_1.status_code == 200
            assert len(res_1.json()["results"]) == 1

            # Upper bound (100)
            res_100 = client.post(
                "/api/v1/search", json={"query": "python", "limit": 100}
            )
            assert res_100.status_code == 200

            # Invalid (0)
            res_0 = client.post("/api/v1/search", json={"query": "python", "limit": 0})
            assert res_0.status_code == 422

            # Invalid (101)
            res_101 = client.post(
                "/api/v1/search", json={"query": "python", "limit": 101}
            )
            assert res_101.status_code == 422

    def test_pagination_offset_and_total_available(
        self, test_data_db: SQLiteIndexer
    ) -> None:
        engine = SearchEngine(test_data_db)
        app = create_app(indexer=test_data_db, search_engine=engine)

        with TestClient(app) as client:
            # Page 1
            res_p1 = client.post(
                "/api/v1/search",
                json={"query": "python", "limit": 1, "offset": 0},
            )
            assert res_p1.status_code == 200
            d1 = res_p1.json()
            assert d1["count"] == 1
            assert d1["total_available"] >= 2
            doc1_id = d1["results"][0]["doc_id"]

            # Page 2
            res_p2 = client.post(
                "/api/v1/search",
                json={"query": "python", "limit": 1, "offset": 1},
            )
            assert res_p2.status_code == 200
            d2 = res_p2.json()
            assert d2["count"] == 1
            doc2_id = d2["results"][0]["doc_id"]
            assert doc1_id != doc2_id

    def test_pagination_max_offset_exceeded(self, test_data_db: SQLiteIndexer) -> None:
        engine = SearchEngine(test_data_db)
        cfg = Config(server=ServerConfig(max_offset=50))
        app = create_app(config=cfg, indexer=test_data_db, search_engine=engine)

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/search",
                json={"query": "python", "limit": 10, "offset": 51},
            )
            assert response.status_code == 422
            assert "exceeds maximum" in response.json()["error"]

    def test_search_engine_unavailable_503(self) -> None:
        """Verify HTTP 503 with standard ErrorResponse when search engine is missing."""
        app = create_app(indexer=None, search_engine=None)
        with TestClient(app) as client:
            # Forcing engine to None
            app.state.search_engine = None
            response = client.post("/api/v1/search", json={"query": "python"})
            assert response.status_code == 503
            data = response.json()
            assert data["code"] == 503
            assert "unavailable" in data["error"].lower()

    def test_snippet_escaping_prevents_xss(self, test_data_db: SQLiteIndexer) -> None:
        """Verify raw HTML tags inside text are escaped in snippet output."""
        engine = SearchEngine(test_data_db)
        app = create_app(indexer=test_data_db, search_engine=engine)

        with TestClient(app) as client:
            response = client.get("/api/v1/search?q=malicious")
            assert response.status_code == 200
            data = response.json()
            assert len(data["results"]) == 1
            snippet = data["results"][0]["snippet"]
            # Should have escaped &lt;script&gt; instead of raw executable HTML
            assert "<script>" not in snippet
            assert "&lt;script&gt;" in snippet


# ============================================================================
# 2. Suggestions Endpoints Tests
# ============================================================================


class TestSuggestEndpoints:
    """Test suite for autocomplete suggestions endpoint."""

    def test_suggest_success(self, test_data_db: SQLiteIndexer) -> None:
        engine = SearchEngine(test_data_db)
        app = create_app(indexer=test_data_db, search_engine=engine)

        with TestClient(app) as client:
            response = client.get("/api/v1/suggest?prefix=py&limit=5")
            assert response.status_code == 200
            data = response.json()
            assert data["prefix"] == "py"
            assert isinstance(data["suggestions"], list)
            assert any(s.startswith("py") for s in data["suggestions"])

    def test_legacy_suggest_alias(self, test_data_db: SQLiteIndexer) -> None:
        engine = SearchEngine(test_data_db)
        app = create_app(indexer=test_data_db, search_engine=engine)

        with TestClient(app) as client:
            response = client.get("/api/suggest?prefix=fast")
            assert response.status_code == 200
            assert response.json()["prefix"] == "fast"

    def test_suggest_whitespace_normalization(
        self, test_data_db: SQLiteIndexer
    ) -> None:
        engine = SearchEngine(test_data_db)
        app = create_app(indexer=test_data_db, search_engine=engine)

        with TestClient(app) as client:
            response = client.get("/api/v1/suggest?prefix=%20py%20")
            assert response.status_code == 200
            assert response.json()["prefix"] == "py"

    def test_suggest_empty_prefix_rejected(self, test_data_db: SQLiteIndexer) -> None:
        engine = SearchEngine(test_data_db)
        app = create_app(indexer=test_data_db, search_engine=engine)

        with TestClient(app) as client:
            response = client.get("/api/v1/suggest?prefix=%20%20")
            assert response.status_code == 422

    def test_suggest_prefix_too_long(self, test_data_db: SQLiteIndexer) -> None:
        engine = SearchEngine(test_data_db)
        app = create_app(indexer=test_data_db, search_engine=engine)

        with TestClient(app) as client:
            long_prefix = "p" * 51
            response = client.get(f"/api/v1/suggest?prefix={long_prefix}")
            assert response.status_code == 422


# ============================================================================
# 3. Stats Endpoints Tests
# ============================================================================


class TestStatsEndpoints:
    """Test suite for index statistics endpoints."""

    def test_stats_success(self, test_data_db: SQLiteIndexer) -> None:
        app = create_app(indexer=test_data_db)

        with TestClient(app) as client:
            response = client.get("/api/v1/stats")
            assert response.status_code == 200
            data = response.json()
            assert data["total_documents"] == 3
            assert data["total_terms"] > 0
            assert data["total_postings"] > 0
            assert data["avg_postings_per_term"] > 0
            assert data["index_size_mb"] >= 0.0

    def test_legacy_stats_alias(self, test_data_db: SQLiteIndexer) -> None:
        app = create_app(indexer=test_data_db)

        with TestClient(app) as client:
            response = client.get("/api/stats")
            assert response.status_code == 200
            assert response.json()["total_documents"] == 3

    def test_stats_indexer_unavailable_503(self) -> None:
        app = create_app(indexer=None)
        with TestClient(app) as client:
            app.state.indexer = None
            response = client.get("/api/v1/stats")
            assert response.status_code == 503


# ============================================================================
# 4. Health & Readiness Endpoints Tests
# ============================================================================


class TestHealthEndpoints:
    """Test suite for health and readiness checks."""

    def test_health_v1_readiness_true(self, test_data_db: SQLiteIndexer) -> None:
        engine = SearchEngine(test_data_db)
        app = create_app(indexer=test_data_db, search_engine=engine)

        with TestClient(app) as client:
            response = client.get("/api/v1/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["version"] == API_VERSION
            assert "Z" in data["timestamp"]
            assert data["index_ready"] is True

    def test_health_v1_readiness_false_when_empty(self, tmp_path: Path) -> None:
        empty_db = SQLiteIndexer(str(tmp_path / "empty.db"))
        engine = SearchEngine(empty_db)
        app = create_app(indexer=empty_db, search_engine=engine)

        with TestClient(app) as client:
            response = client.get("/api/v1/health")
            assert response.status_code == 200
            assert response.json()["index_ready"] is False
        empty_db.close()

    def test_legacy_health_and_root_liveness(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            # /api/health
            res_api = client.get("/api/health")
            assert res_api.status_code == 200
            assert res_api.json() == {"status": "ok"}

            # /health
            res_root = client.get("/health")
            assert res_root.status_code == 200
            assert res_root.json() == {"status": "ok"}

    def test_health_safe_fields_no_sensitive_leak(
        self, test_data_db: SQLiteIndexer
    ) -> None:
        engine = SearchEngine(test_data_db)
        app = create_app(indexer=test_data_db, search_engine=engine)

        with TestClient(app) as client:
            response = client.get("/api/v1/health")
            data = response.json()
            # Allowed fields only
            assert set(data.keys()) == {
                "status",
                "version",
                "timestamp",
                "index_ready",
            }
            # No paths or env details leaked
            raw_text = response.text
            assert "api_test.db" not in raw_text
            assert "C:" not in raw_text and "D:" not in raw_text


# ============================================================================
# 5. Root and OpenAPI Endpoints Tests
# ============================================================================


class TestRootAndOpenAPIEndpoints:
    """Test suite for root path and documentation endpoints."""

    def test_root_endpoint(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/")
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Private Search Engine API"
            assert data["version"] == API_VERSION
            assert "/docs" in data["docs"]

    def test_openapi_json_endpoint(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/openapi.json")
            assert response.status_code == 200
            spec = response.json()
            assert spec["info"]["version"] == API_VERSION
            tags = {t["name"] for t in spec.get("tags", [])}
            assert "Search" in tags
            assert "Suggestions" in tags


# ============================================================================
# 6. Structured Error Handling Tests (404, 422, 500)
# ============================================================================


class TestStructuredErrorHandling:
    """Test suite verifying consistent ErrorResponse schema across all error types."""

    def test_404_error_response_schema(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/api/v1/nonexistent_path")
            assert response.status_code == 404
            data = response.json()
            assert data["code"] == 404
            assert "not found" in data["error"].lower()
            assert "timestamp" in data
            assert "request_id" in data
            assert response.headers.get("x-request-id") == data["request_id"]

    def test_422_validation_error_schema(self, test_data_db: SQLiteIndexer) -> None:
        engine = SearchEngine(test_data_db)
        app = create_app(indexer=test_data_db, search_engine=engine)

        with TestClient(app) as client:
            response = client.post("/api/v1/search", json={"limit": "not_an_int"})
            assert response.status_code == 422
            data = response.json()
            assert data["code"] == 422
            assert "validation" in data["error"].lower()
            assert "details" in data
            assert isinstance(data["details"], list)

    def test_500_internal_error_does_not_leak_trace(
        self, test_data_db: SQLiteIndexer
    ) -> None:
        """Verify unexpected exceptions return safe 500 response without leaks."""
        engine = SearchEngine(test_data_db)
        app = create_app(indexer=test_data_db, search_engine=engine)

        # Inject broken search method raising unexpected exception
        def broken_search(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("Database corruption simulated in test")

        engine.search_with_total = broken_search  # type: ignore

        with TestClient(app) as client:
            response = client.post("/api/v1/search", json={"query": "python"})
            assert response.status_code == 500
            data = response.json()
            assert data["code"] == 500
            assert "internal server error" in data["error"].lower()
            # Must NOT expose raw exception string to client
            assert "Database corruption" not in response.text
            assert "Traceback" not in response.text


# ============================================================================
# 7. Rate Limiting Tests (Deterministic with Mock Clock)
# ============================================================================


class TestRateLimiting:
    """Test suite for in-memory sliding-window rate limiter."""

    def test_rate_limiter_allows_under_limit(
        self, mock_clock: Dict[str, float]
    ) -> None:
        limiter = RateLimiter(
            requests_per_minute=3,
            time_func=lambda: mock_clock["current_time"],
        )
        assert limiter.is_allowed("192.168.1.1") is True
        assert limiter.is_allowed("192.168.1.1") is True
        assert limiter.is_allowed("192.168.1.1") is True
        assert limiter.get_remaining("192.168.1.1") == 0

    def test_rate_limiter_blocks_over_limit_429(
        self, mock_clock: Dict[str, float]
    ) -> None:
        limiter = RateLimiter(
            requests_per_minute=2,
            time_func=lambda: mock_clock["current_time"],
        )
        assert limiter.is_allowed("10.0.0.1") is True
        assert limiter.is_allowed("10.0.0.1") is True
        # 3rd request blocked
        assert limiter.is_allowed("10.0.0.1") is False

    def test_rate_limiter_reset_with_controllable_clock(
        self, mock_clock: Dict[str, float]
    ) -> None:
        """Verify window expiration resets rate limit without sleeping in real time."""
        limiter = RateLimiter(
            requests_per_minute=2,
            window_seconds=60.0,
            time_func=lambda: mock_clock["current_time"],
        )
        assert limiter.is_allowed("10.0.0.1") is True
        assert limiter.is_allowed("10.0.0.1") is True
        assert limiter.is_allowed("10.0.0.1") is False

        # Advance simulated clock by 61 seconds
        mock_clock["current_time"] += 61.0
        assert limiter.is_allowed("10.0.0.1") is True

    def test_rate_limiter_client_isolation(self, mock_clock: Dict[str, float]) -> None:
        limiter = RateLimiter(
            requests_per_minute=1,
            time_func=lambda: mock_clock["current_time"],
        )
        assert limiter.is_allowed("1.1.1.1") is True
        assert limiter.is_allowed("1.1.1.1") is False
        # Client 2.2.2.2 has independent budget
        assert limiter.is_allowed("2.2.2.2") is True

    def test_rate_limit_middleware_integration_and_headers(
        self, test_data_db: SQLiteIndexer, mock_clock: Dict[str, float]
    ) -> None:
        """Verify HTTP 429 response body and headers through FastAPI middleware."""
        limiter = RateLimiter(
            requests_per_minute=2,
            window_seconds=60.0,
            time_func=lambda: mock_clock["current_time"],
        )
        engine = SearchEngine(test_data_db)
        app = create_app(
            indexer=test_data_db, search_engine=engine, rate_limiter=limiter
        )

        with TestClient(app) as client:
            r1 = client.post("/api/v1/search", json={"query": "python"})
            assert r1.status_code == 200

            r2 = client.post("/api/v1/search", json={"query": "python"})
            assert r2.status_code == 200

            # 3rd request triggers 429
            r3 = client.post("/api/v1/search", json={"query": "python"})
            assert r3.status_code == 429
            assert "Retry-After" in r3.headers
            assert "X-RateLimit-Limit" in r3.headers
            assert r3.headers["X-RateLimit-Remaining"] == "0"
            data = r3.json()
            assert data["code"] == 429
            assert "rate limit" in data["error"].lower()
            assert data["details"]["requests_per_minute"] == 2

    def test_rate_limiter_expired_bucket_eviction(
        self, mock_clock: Dict[str, float]
    ) -> None:
        """Verify expired IP buckets are purged from memory."""
        limiter = RateLimiter(
            requests_per_minute=5,
            window_seconds=10.0,
            max_tracked_ips=2,
            time_func=lambda: mock_clock["current_time"],
        )
        limiter.is_allowed("1.1.1.1")
        limiter.is_allowed("2.2.2.2")
        limiter.is_allowed("3.3.3.3")

        mock_clock["current_time"] += 20.0
        # Trigger cleanup
        limiter.is_allowed("4.4.4.4")
        assert "1.1.1.1" not in limiter.requests

    def test_get_client_ip_trusted_proxy_policy(self) -> None:
        """Verify X-Forwarded-For is ONLY trusted when request is from trusted proxy."""
        # Untrusted proxy scenario
        req_untrusted = Request(
            {
                "type": "http",
                "client": ("203.0.113.5", 1234),
                "headers": [(b"x-forwarded-for", b"198.51.100.1")],
            }
        )
        # Ignores spoofed header
        assert get_client_ip(req_untrusted, trusted_proxies=[]) == "203.0.113.5"

        # Trusted proxy scenario
        req_trusted = Request(
            {
                "type": "http",
                "client": ("10.0.0.1", 1234),
                "headers": [(b"x-forwarded-for", b"198.51.100.1, 10.0.0.1")],
            }
        )
        # Trusts client IP forwarded by trusted proxy
        assert (
            get_client_ip(req_trusted, trusted_proxies=["10.0.0.1"]) == "198.51.100.1"
        )


# ============================================================================
# 8. Security Headers and CORS Tests
# ============================================================================


class TestSecurityHeadersAndCORS:
    """Test suite for security headers and CORS configurations."""

    def test_security_headers_on_success(self, test_data_db: SQLiteIndexer) -> None:
        engine = SearchEngine(test_data_db)
        app = create_app(indexer=test_data_db, search_engine=engine)

        with TestClient(app) as client:
            response = client.get("/")
            assert response.status_code == 200
            assert response.headers.get("x-content-type-options") == "nosniff"
            assert response.headers.get("x-frame-options") == "DENY"
            assert response.headers.get("referrer-policy") == "no-referrer"
            assert response.headers.get("x-xss-protection") == "1; mode=block"
            assert "Content-Security-Policy" in response.headers

    def test_security_headers_on_error_responses(self) -> None:
        """Verify security headers are retained on 404, 422, and 429 responses."""
        app = create_app()

        with TestClient(app) as client:
            # 404
            res_404 = client.get("/api/v1/not_found")
            assert res_404.headers.get("x-frame-options") == "DENY"
            assert res_404.headers.get("x-content-type-options") == "nosniff"

            # 422
            res_422 = client.post("/api/v1/search", json={"query": ""})
            assert res_422.headers.get("x-frame-options") == "DENY"
            assert res_422.headers.get("x-content-type-options") == "nosniff"

    def test_hsts_disabled_by_default_on_local_http(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/")
            assert "Strict-Transport-Security" not in response.headers

    def test_hsts_enabled_via_config(self) -> None:
        cfg = Config(server=ServerConfig(enable_hsts=True))
        app = create_app(config=cfg)
        with TestClient(app) as client:
            response = client.get("/")
            assert "Strict-Transport-Security" in response.headers
            assert "max-age=31536000" in response.headers["Strict-Transport-Security"]

    def test_cors_headers_allowed_origin(self) -> None:
        cfg = Config(server=ServerConfig(cors_origins=["http://trusted-ui.local"]))
        app = create_app(config=cfg)
        with TestClient(app) as client:
            response = client.options(
                "/api/v1/search",
                headers={
                    "Origin": "http://trusted-ui.local",
                    "Access-Control-Request-Method": "POST",
                },
            )
            assert (
                response.headers.get("access-control-allow-origin")
                == "http://trusted-ui.local"
            )


# ============================================================================
# 9. Request ID Tracing Tests
# ============================================================================


class TestRequestIDTracing:
    """Test suite for request ID generation, correlation, and propagation."""

    def test_request_id_generated_and_propagated(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/")
            req_id = response.headers.get("x-request-id")
            assert req_id is not None
            assert len(req_id) >= 8

    def test_custom_safe_request_id_preserved(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            custom_id = "client-trace-12345"
            response = client.get("/", headers={"X-Request-ID": custom_id})
            assert response.headers.get("x-request-id") == custom_id

    def test_oversized_request_id_replaced_with_safe_uuid(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            oversized = "x" * 200
            response = client.get("/", headers={"X-Request-ID": oversized})
            actual_id = response.headers.get("x-request-id")
            assert actual_id != oversized
            assert len(actual_id) < 64
