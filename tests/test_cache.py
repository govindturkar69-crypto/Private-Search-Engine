"""Unit and integration tests for service-layer LRUCache and generation keying."""

import concurrent.futures
from pathlib import Path
import pytest
from src.cache.cache_layer import LRUCache


class TestLRUCache:
    """Comprehensive test suite for LRUCache."""

    def test_cache_hit_and_miss(self) -> None:
        """Verify standard get/set operations and hit/miss accounting."""
        cache = LRUCache(max_entries=10, ttl_seconds=60.0)
        key = (1, "python search", 10, 0)

        # Initial lookup must miss
        assert cache.get(key) is None
        stats = cache.get_stats()
        assert stats["misses"] == 1
        assert stats["hits"] == 0

        # Set and hit
        payload = {"results": [1, 2, 3]}
        cache.set(key, payload)

        res = cache.get(key)
        assert res == payload
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1

    def test_ttl_expiry_with_controllable_clock(self) -> None:
        """Verify deterministic TTL expiry using an injected clock function."""
        current_time = 1000.0

        def mock_clock() -> float:
            return current_time

        cache = LRUCache(max_entries=10, ttl_seconds=10.0, clock=mock_clock)
        key = (1, "query", 10, 0)
        cache.set(key, "cached_data")

        # Within TTL
        current_time = 1005.0
        assert cache.get(key) == "cached_data"

        # At TTL boundary / expired
        current_time = 1010.1
        assert cache.get(key) is None
        # Entry should have been purged on lookup
        assert cache.get_stats()["size"] == 0

    def test_lru_eviction_bounded_capacity(self) -> None:
        """Verify capacity bound and least-recently used eviction policy."""
        cache = LRUCache(max_entries=3, ttl_seconds=300.0)

        cache.set((1, "k1", 10, 0), "v1")
        cache.set((1, "k2", 10, 0), "v2")
        cache.set((1, "k3", 10, 0), "v3")

        assert cache.get_stats()["size"] == 3
        assert cache.get_stats()["evictions"] == 0

        # Adding 4th item must evict least recently used (k1)
        cache.set((1, "k4", 10, 0), "v4")
        assert cache.get_stats()["size"] == 3
        assert cache.get_stats()["evictions"] == 1
        assert cache.get((1, "k1", 10, 0)) is None
        assert cache.get((1, "k2", 10, 0)) == "v2"

    def test_lru_move_to_end_on_hit(self) -> None:
        """Verify accessing an item marks it as MRU, preventing premature eviction."""
        cache = LRUCache(max_entries=3, ttl_seconds=300.0)

        cache.set((1, "k1", 10, 0), "v1")
        cache.set((1, "k2", 10, 0), "v2")
        cache.set((1, "k3", 10, 0), "v3")

        # Access k1 to make it most recently used
        assert cache.get((1, "k1", 10, 0)) == "v1"

        # Insert k4: k2 is now the oldest and should be evicted, NOT k1
        cache.set((1, "k4", 10, 0), "v4")

        assert cache.get((1, "k1", 10, 0)) == "v1"
        assert cache.get((1, "k2", 10, 0)) is None
        assert cache.get((1, "k3", 10, 0)) == "v3"
        assert cache.get((1, "k4", 10, 0)) == "v4"

    def test_cache_disabled_mode(self) -> None:
        """Verify cache behaves as a no-op when disabled."""
        cache = LRUCache(max_entries=10, enabled=False)
        key = (1, "query", 10, 0)

        cache.set(key, "data")
        assert cache.get(key) is None
        assert cache.get_stats()["size"] == 0

    def test_generation_key_isolation(self) -> None:
        """Verify that incrementing the index generation isolates cache keys."""
        cache = LRUCache(max_entries=100)

        gen1_key = (1, "search query", 10, 0)
        gen2_key = (2, "search query", 10, 0)

        cache.set(gen1_key, "gen1_results")

        # Query with gen2 should miss
        assert cache.get(gen2_key) is None
        assert cache.get(gen1_key) == "gen1_results"

    def test_invalidate_and_clear(self) -> None:
        """Verify explicit invalidation clears all cached entries."""
        cache = LRUCache(max_entries=10)
        cache.set((1, "q1", 10, 0), "val1")
        cache.set((1, "q2", 10, 0), "val2")
        assert cache.get_stats()["size"] == 2

        cache.invalidate()
        assert cache.get_stats()["size"] == 0
        assert cache.get((1, "q1", 10, 0)) is None

    def test_thread_safety_concurrent_access(self) -> None:
        """Verify thread safety under heavy concurrent read/write stress."""
        cache = LRUCache(max_entries=50, ttl_seconds=60.0)
        num_threads = 8
        ops_per_thread = 200

        def worker(thread_id: int) -> None:
            for i in range(ops_per_thread):
                key = (1, f"query_{i % 20}", 10, 0)
                if i % 2 == 0:
                    cache.set(key, f"val_{thread_id}_{i}")
                else:
                    cache.get(key)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, t) for t in range(num_threads)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        stats = cache.get_stats()
        assert stats["size"] <= 50
        assert stats["hits"] + stats["misses"] > 0


class TestAPICacheIntegration:
    """Integration test suite for service-layer search caching and X-Cache headers."""

    @pytest.fixture
    def api_client(self, tmp_path: Path):
        """Create isolated TestClient with indexed test corpus."""
        from fastapi.testclient import TestClient
        from src.indexer import SQLiteIndexer
        from src.main import create_app
        from src.ranker.search import SearchEngine

        db_file = str(tmp_path / "cache_api_test.db")
        indexer = SQLiteIndexer(db_file)
        indexer.add_document(
            {
                "url": "https://example.com/python",
                "title": "Python Language Guide",
                "description": "Comprehensive overview of Python programming.",
                "body": "Python is dynamic, powerful, and easy to learn.",
                "content_hash": "hash_py_1",
            }
        )
        indexer.add_document(
            {
                "url": "https://example.com/fastapi",
                "title": "FastAPI Web Framework",
                "description": "High performance Python web framework.",
                "body": "FastAPI is built on Starlette and Pydantic.",
                "content_hash": "hash_fa_2",
            }
        )
        engine = SearchEngine(indexer)
        cache = LRUCache(max_entries=100)
        app = create_app(indexer=indexer, search_engine=engine, search_cache=cache)
        client = TestClient(app)
        return client, indexer

    def test_search_cache_miss_then_hit(self, api_client) -> None:
        """First request is MISS, second request is HIT with identical results."""
        client, indexer = api_client

        # 1. Cold search: MISS
        r1 = client.get("/api/v1/search?q=python")
        assert r1.status_code == 200
        assert r1.headers.get("X-Cache") == "MISS"
        data1 = r1.json()
        assert data1["count"] > 0

        # 2. Warm search: HIT
        r2 = client.get("/api/v1/search?q=python")
        assert r2.status_code == 200
        assert r2.headers.get("X-Cache") == "HIT"
        data2 = r2.json()

        # Result equivalence check
        assert data1["count"] == data2["count"]
        assert data1["total_available"] == data2["total_available"]
        assert [d["doc_id"] for d in data1["results"]] == [
            d["doc_id"] for d in data2["results"]
        ]
        assert [d["score"] for d in data1["results"]] == [
            d["score"] for d in data2["results"]
        ]

    def test_post_search_shares_cache_semantics(self, api_client) -> None:
        """POST /api/v1/search must also participate in caching."""
        client, _ = api_client

        payload = {"query": "fastapi", "limit": 10, "offset": 0}
        r1 = client.post("/api/v1/search", json=payload)
        assert r1.status_code == 200
        assert r1.headers.get("X-Cache") == "MISS"

        r2 = client.post("/api/v1/search", json=payload)
        assert r2.status_code == 200
        assert r2.headers.get("X-Cache") == "HIT"

    def test_invalidation_upon_document_addition(self, api_client) -> None:
        """Adding a document advances generation and invalidates cached queries."""
        client, indexer = api_client

        # Populate cache
        r1 = client.get("/api/v1/search?q=python")
        assert r1.headers.get("X-Cache") == "MISS"
        r2 = client.get("/api/v1/search?q=python")
        assert r2.headers.get("X-Cache") == "HIT"

        # Mutate index (advances persistent generation)
        indexer.add_document(
            {
                "url": "https://example.com/python-new",
                "title": "New Python Document",
                "description": "Freshly added Python content.",
                "body": "Python continues to evolve rapidly.",
                "content_hash": "hash_py_new_3",
            }
        )

        # Stale cache entry is logically unreachable: query must be MISS
        r3 = client.get("/api/v1/search?q=python")
        assert r3.status_code == 200
        assert r3.headers.get("X-Cache") == "MISS"

        # Subsequent query on new generation is HIT
        r4 = client.get("/api/v1/search?q=python")
        assert r4.status_code == 200
        assert r4.headers.get("X-Cache") == "HIT"

    def test_errors_are_never_cached(self, api_client) -> None:
        """Invalid requests (422/400) must never be stored in cache."""
        client, _ = api_client

        r1 = client.get("/api/v1/search?q=   ")
        assert r1.status_code == 422
        assert "X-Cache" not in r1.headers

        r2 = client.get("/api/v1/search?q=   ")
        assert r2.status_code == 422
        assert "X-Cache" not in r2.headers
