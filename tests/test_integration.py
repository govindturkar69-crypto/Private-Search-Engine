"""Integration tests covering complete end-to-end workflows and subsystems."""

import asyncio
import concurrent.futures
from typing import Any, Dict, List
from fastapi.testclient import TestClient
import httpx
import pytest
from src.crawler.fetcher import Fetcher
from src.indexer import SQLiteIndexer
from src.main import create_app
from src.ranker.pipeline import EndToEndPipeline
from src.ranker.search import SearchEngine


@pytest.mark.integration
class TestFullWorkflow:
    """End-to-end integration workflow tests."""

    def test_search_workflow(self, test_client_with_engine: TestClient) -> None:
        """Test complete search lifecycle from health probe to suggestions."""
        # 1. Health check
        res_health = test_client_with_engine.get("/api/v1/health")
        assert res_health.status_code == 200
        health_data = res_health.json()
        assert health_data["status"] == "ok"
        assert health_data["index_ready"] is True

        # 2. Inverted index stats
        res_stats = test_client_with_engine.get("/api/v1/stats")
        assert res_stats.status_code == 200
        stats = res_stats.json()
        assert stats["total_documents"] == 10
        assert stats["total_terms"] > 0
        assert stats["total_postings"] > 0
        assert stats["index_size_mb"] >= 0

        # 3. Search POST query
        res_search = test_client_with_engine.post(
            "/api/v1/search",
            json={"query": "python", "limit": 10, "offset": 0},
        )
        assert res_search.status_code == 200
        search_data = res_search.json()
        assert search_data["query"] == "python"
        assert len(search_data["results"]) > 0
        assert search_data["count"] > 0
        assert search_data["total_available"] > 0
        assert "execution_time_ms" in search_data

        # 4. Search GET equivalent query
        res_get = test_client_with_engine.get("/api/v1/search?q=python&limit=10")
        assert res_get.status_code == 200
        get_data = res_get.json()
        assert get_data["count"] == search_data["count"]

        # 5. Autocomplete suggestions
        res_sug = test_client_with_engine.get("/api/v1/suggest?prefix=doc&limit=5")
        assert res_sug.status_code == 200
        sug_data = res_sug.json()
        assert sug_data["prefix"] == "doc"
        assert isinstance(sug_data["suggestions"], list)

    def test_pagination_workflow(self, test_client_with_engine: TestClient) -> None:
        """Verify disjoint result sets and consistent total counts across pages."""
        # Page 1
        res_p1 = test_client_with_engine.post(
            "/api/v1/search",
            json={"query": "document", "limit": 5, "offset": 0},
        )
        assert res_p1.status_code == 200
        page1 = res_p1.json()
        assert len(page1["results"]) <= 5

        # Page 2
        res_p2 = test_client_with_engine.post(
            "/api/v1/search",
            json={"query": "document", "limit": 5, "offset": 5},
        )
        assert res_p2.status_code == 200
        page2 = res_p2.json()

        page1_ids = {r["doc_id"] for r in page1["results"]}
        page2_ids = {r["doc_id"] for r in page2["results"]}

        if page1_ids and page2_ids:
            assert (
                len(page1_ids & page2_ids) == 0
            ), "Pagination should yield mutually disjoint result sets"


@pytest.mark.integration
class TestErrorHandling:
    """Test error handling and request validation contracts across workflows."""

    def test_invalid_query_types(self, test_client_with_engine: TestClient) -> None:
        """Test rejection of malformed or out-of-bounds search requests."""
        invalid_requests = [
            {"query": "", "limit": 10},  # Empty query
            {"query": "   ", "limit": 10},  # Whitespace query
            {"query": "x" * 600, "limit": 10},  # Exceeds max length (500)
            {"query": "test", "limit": 1000},  # Limit > 100
            {"query": "test", "limit": 0},  # Limit < 1
            {"query": "test", "offset": -1},  # Negative offset
        ]

        for req in invalid_requests:
            res = test_client_with_engine.post("/api/v1/search", json=req)
            assert res.status_code == 422, f"Expected 422 for invalid request: {req}"
            err_data = res.json()
            assert "error" in err_data
            assert "request_id" in err_data
            assert "timestamp" in err_data

    def test_api_error_format(self, test_client_with_engine: TestClient) -> None:
        """Test structured error response schema on bad routes and invalid inputs."""
        res_404 = test_client_with_engine.get("/api/v1/nonexistent-route")
        assert res_404.status_code == 404
        data = res_404.json()
        assert data["code"] == 404
        assert "error" in data
        assert "timestamp" in data
        assert "request_id" in data


@pytest.mark.integration
class TestConcurrency:
    """Test concurrent operations against the application without race conditions."""

    def test_concurrent_searches(self, test_client_with_engine: TestClient) -> None:
        """Execute multiple concurrent searches across multiple threads safely."""

        def _do_search(term: str) -> int:
            response = test_client_with_engine.post(
                "/api/v1/search",
                json={"query": term, "limit": 5, "offset": 0},
            )
            return response.status_code

        query_batch = ["document", "python", "search", "database", "guide"] * 4

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            status_codes = list(executor.map(_do_search, query_batch))

        assert len(status_codes) == len(query_batch)
        assert all(code == 200 for code in status_codes)


@pytest.mark.integration
class TestDataIntegrity:
    """Test data integrity, deduplication, and search idempotency."""

    def test_duplicate_document_handling(self, seeded_indexer: SQLiteIndexer) -> None:
        """Verify duplicate ingestion updates or deduplicates without corruption."""
        initial_stats = seeded_indexer.get_stats()
        initial_doc_count = initial_stats["total_documents"]

        dup_doc = {
            "url": "https://example.com/unique-dup-test",
            "title": "Duplicate Ingestion Test",
            "description": "Deduplication testing",
            "body": "Content body for testing duplicate handling in indexer",
            "content_hash": "hash_dup_unique_val",
            "metadata": {"language": "en"},
        }

        # Add first time
        doc_id1 = seeded_indexer.add_document(dup_doc)
        assert doc_id1 is not None

        # Add second time
        doc_id2 = seeded_indexer.add_document(dup_doc)
        # Should return existing ID or update gracefully
        assert doc_id2 == doc_id1

        post_count = seeded_indexer.get_stats()["total_documents"]
        assert post_count == initial_doc_count + 1

    def test_search_consistency(self, test_client_with_engine: TestClient) -> None:
        """Repeated identical queries must return completely deterministic results."""
        queries = ["python", "document"]

        for q in queries:
            results: List[Dict[str, Any]] = []
            for _ in range(3):
                res = test_client_with_engine.post(
                    "/api/v1/search",
                    json={"query": q, "limit": 10, "offset": 0},
                )
                assert res.status_code == 200
                results.append(res.json())

            first = results[0]
            for subsequent in results[1:]:
                assert first["count"] == subsequent["count"]
                assert first["total_available"] == subsequent["total_available"]
                assert [r["doc_id"] for r in first["results"]] == [
                    r["doc_id"] for r in subsequent["results"]
                ]


@pytest.mark.integration
class TestEndToEndPipelineWorkflow:
    """Req 41: URL/HTML -> Mock fetch -> Parse -> Dedup -> Index -> Search -> API."""

    def test_full_pipeline_mock_fetch_to_search_api(self, tmp_path: Any) -> None:
        """Full end-to-end integration flow using controlled local mock transport."""
        db_path = str(tmp_path / "pipeline_e2e.db")
        indexer = SQLiteIndexer(db_path)

        # Mock HTML responses for controlled crawl
        mock_html_1 = """<!DOCTYPE html>
        <html lang="en">
        <head><title>Quantum Computing Fundamentals</title></head>
        <body>
            <article>
                <h1>Quantum Supremacy and Qubits</h1>
                <p>Quantum computing utilizes qubits for faster calculation.</p>
                <a href="https://example.test/doc2">Next Article</a>
            </article>
        </body>
        </html>"""

        mock_html_2 = """<!DOCTYPE html>
        <html lang="en">
        <head><title>Quantum Cryptography Protocols</title></head>
        <body>
            <article>
                <h1>Post-Quantum Security</h1>
                <p>Cryptography ensures secure communication against adversaries.</p>
            </article>
        </body>
        </html>"""

        def mock_handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if "robots.txt" in url_str:
                return httpx.Response(
                    200, text="User-agent: *\nAllow: /\n", request=request
                )
            if "doc2" in url_str:
                return httpx.Response(200, text=mock_html_2, request=request)
            return httpx.Response(200, text=mock_html_1, request=request)

        mock_transport = httpx.MockTransport(mock_handler)
        fetcher = Fetcher(
            transport=mock_transport,
            dns_resolver=lambda h: ["93.184.216.34"],
        )

        pipeline = EndToEndPipeline(indexer=indexer, fetcher=fetcher)

        # Execute crawl and index pipeline
        pipeline.add_seed_urls(["https://example.test/doc1"])
        indexed_count = asyncio.run(
            pipeline.crawl_and_index(max_documents=5, timeout=10.0)
        )

        assert indexed_count >= 1

        # Wire up search engine and FastAPI app
        search_engine = SearchEngine(indexer)
        app = create_app(indexer=indexer, search_engine=search_engine)

        with TestClient(app) as client:
            # Query the newly indexed documents
            response = client.post(
                "/api/v1/search",
                json={"query": "quantum cryptography", "limit": 10, "offset": 0},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["count"] >= 1
            assert "Quantum" in data["results"][0]["title"]
            assert data["results"][0]["snippet"] != ""

        indexer.close()
