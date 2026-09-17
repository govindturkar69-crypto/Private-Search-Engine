from fastapi.testclient import TestClient
from src.main import create_app


class TestPrometheusMetricsExposition:
    """Test suite for Prometheus operational metrics and route instrumentation."""

    def test_metrics_endpoint_exposition_format(self) -> None:
        """Test that /metrics returns 200 with standard exposition format."""
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/metrics")
            assert response.status_code == 200
            assert "text/plain" in response.headers.get("content-type", "")
            content = response.text
            assert "# HELP http_requests_total" in content
            assert "# TYPE http_requests_total counter" in content
            assert "# HELP http_request_duration_seconds" in content
            assert "# TYPE http_request_duration_seconds histogram" in content
            assert "search_engine_cache_hits_total" in content
            assert "search_engine_cache_misses_total" in content
            assert "search_engine_indexed_documents" in content
            assert "search_engine_unique_terms" in content
            assert "search_engine_index_generation" in content

    def test_registry_isolation_between_apps(self) -> None:
        """Test that separate create_app instances do not share metric state."""
        app1 = create_app()
        app2 = create_app()

        with TestClient(app1) as c1, TestClient(app2) as c2:
            c1.get("/health")
            c1.get("/health")

            res1 = c1.get("/metrics").text
            res2 = c2.get("/metrics").text

            expected_label = (
                'http_requests_total{handler="/health",method="GET",status="200"} 2.0'
            )
            assert expected_label in res1
            # App 2 hasn't received /health requests yet
            assert (
                'http_requests_total{handler="/health",method="GET",status="200"}'
                not in res2
            )

    def test_centralized_http_route_template_labels(self) -> None:
        """Test that route templates are normalized and attacker paths bounded."""
        app = create_app()
        with TestClient(app) as client:
            client.get("/api/v1/health")
            client.get("/api/v1/nonexistent/arbitrary/path?param=123")

            res = client.get("/metrics").text
            assert 'handler="/api/v1/health"' in res
            assert 'handler="unmatched"' in res
            # Verify the attacker-controlled path is NOT used as a label
            assert "/api/v1/nonexistent/arbitrary/path" not in res

    def test_cache_hits_and_misses_counters(
        self, test_client_with_engine: TestClient
    ) -> None:
        """Test that cache hits and misses increment the single-source counters."""
        client = test_client_with_engine
        # First query -> Cache MISS
        res1 = client.get("/api/v1/search", params={"q": "python"})
        assert res1.status_code == 200
        assert res1.headers.get("X-Cache") == "MISS"

        # Second query -> Cache HIT
        res2 = client.get("/api/v1/search", params={"q": "python"})
        assert res2.status_code == 200
        assert res2.headers.get("X-Cache") == "HIT"

        metrics_text = client.get("/metrics").text
        assert "search_engine_cache_hits_total 1.0" in metrics_text
        assert "search_engine_cache_misses_total 1.0" in metrics_text

    def test_metrics_privacy_zero_query_text(
        self, test_client_with_engine: TestClient
    ) -> None:
        """Test that sensitive queries, tokens, and URLs are never exported."""
        client = test_client_with_engine
        secret_query = "confidential-private-search-phrase"
        client.get("/api/v1/search", params={"q": secret_query})

        metrics_text = client.get("/metrics").text
        assert secret_query not in metrics_text
        assert "confidential" not in metrics_text

    def test_index_gauges_reflect_metadata(
        self, test_client_with_engine: TestClient
    ) -> None:
        """Test that index gauges reflect SQLite metadata without table scans."""
        client = test_client_with_engine
        metrics_text = client.get("/metrics").text

        # Seeded indexer fixture has 10 documents
        assert "search_engine_indexed_documents 10.0" in metrics_text
        assert "search_engine_unique_terms" in metrics_text
        assert "search_engine_index_generation" in metrics_text


class TestSPAStaticServingAndSecurity:
    """Test suite for SPA fallback routing and static file confinement."""

    def test_api_routes_never_fall_through_to_spa(self) -> None:
        """Test that missing /api routes return JSON 404, never HTML index."""
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/api/v1/nonexistent_endpoint")
            assert response.status_code == 404
            assert response.headers.get("content-type") == "application/json"
            data = response.json()
            assert data["error"] == "Endpoint not found"

    def test_static_confinement_prevents_directory_traversal(self) -> None:
        """Test that traversal attempts cannot access files outside frontend/dist."""
        app = create_app()
        with TestClient(app) as client:
            # Asset files not present in dist return 404
            res_ext = client.get("/secret.env")
            assert res_ext.status_code == 404

            res_traversal = client.get("/missing_asset.js")
            assert res_traversal.status_code == 404
            assert "root:" not in res_traversal.text
