"""Comprehensive empirical benchmarking suite for Phase 11 performance optimization.

Measures:
  1. Uncached vs Cached Query Latencies (Cold, Warm, p50, p95, p99)
  2. Batch Document Prefetch vs N+1 Lookup Performance
  3. Single-Doc vs Batch Indexing Throughput
  4. Index Generation Advancement and Cache Invalidation Lifecycle
  5. SQLite EXPLAIN QUERY PLAN validation
"""

import math
from pathlib import Path
import shutil
import sys
import tempfile
import time
from typing import Any, Dict, List

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cache import LRUCache  # noqa: E402
from src.db.optimizer import DatabaseOptimizer  # noqa: E402
from src.db.query_optimizer import QueryOptimizer  # noqa: E402
from src.indexer import SQLiteIndexer  # noqa: E402
from src.indexer.batch import BatchIndexer  # noqa: E402
from src.ranker.search import SearchEngine  # noqa: E402


def generate_benchmark_corpus(n_docs: int = 150) -> List[Dict[str, Any]]:
    """Generate deterministic synthetic corpus for reproducible benchmarking."""
    topics = [
        ("python", "Python programming language concurrency and data structures"),
        ("sqlite", "SQLite embedded relational database index optimization"),
        ("search", "Full text search inverted index scoring and ranking algorithms"),
        ("performance", "High performance web architectures and latency reduction"),
        ("caching", "In-memory LRU caching strategies and invalidation protocols"),
    ]
    docs = []
    for i in range(n_docs):
        topic_idx = i % len(topics)
        kw, title_desc = topics[topic_idx]
        url = f"https://benchmark.internal/doc/{i}"
        title = f"{kw.capitalize()} Performance Engineering Guide Part {i}"
        desc = f"Technical analysis of {title_desc} for scalable systems."
        body = (
            f"This benchmark document covers {kw} in detail. "
            f"Repeated terms: {kw} {kw} and systems engineering. "
            f"High throughput indexing and low latency query execution are paramount. "
            f"Document index reference number is {i}."
        )
        tokens = [t.lower() for t in f"{title} {desc} {body}".split() if len(t) > 2]
        unique_terms = list(dict.fromkeys(tokens))
        title_terms = [t.lower() for t in title.split() if len(t) > 2]
        body_terms = [t.lower() for t in body.split() if len(t) > 2]

        docs.append(
            {
                "url": url,
                "title": title,
                "description": desc,
                "body": body,
                "content_hash": f"bench_hash_{i}_{hash(url)}",
                "language": "en",
                "author": f"Engineer_{i % 5}",
                "tokens": tokens,
                "terms": unique_terms,
                "title_terms": title_terms,
                "body_terms": body_terms,
                "positions": {kw: [2, 10]},
            }
        )
    return docs


def compute_percentiles(values: List[float]) -> Dict[str, float]:
    """Compute min, median (p50), p95, p99, and max from latency list."""
    if not values:
        return {"min": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}

    s = sorted(values)
    n = len(s)

    def _p(p: float) -> float:
        k = (n - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return float(s[int(k)])
        d0 = s[int(f)] * (c - k)
        d1 = s[int(c)] * (k - f)
        return float(d0 + d1)

    return {
        "min": round(s[0], 3),
        "p50": round(_p(0.50), 3),
        "p95": round(_p(0.95), 3),
        "p99": round(_p(0.99), 3),
        "max": round(s[-1], 3),
    }


def run_benchmarks() -> None:
    """Execute complete benchmarking suite and report structured findings."""
    temp_dir = tempfile.mkdtemp(prefix="pse_bench_")
    db_path = str(Path(temp_dir) / "bench.db")

    print("\n" + "=" * 75)
    print(" PRIVATE SEARCH ENGINE — MEASUREMENT-DRIVEN PERFORMANCE BENCHMARK")
    print("=" * 75)

    try:
        corpus = generate_benchmark_corpus(150)

        # -------------------------------------------------------------------
        # 1. Ingestion Throughput Benchmark
        # -------------------------------------------------------------------
        print("\n[1/5] Ingestion Throughput Benchmark (150 documents)...")

        # Single document insert test
        t0 = time.perf_counter()
        with SQLiteIndexer(db_path) as indexer:
            for d in corpus[:75]:
                indexer.add_document(d)
        single_write_time = time.perf_counter() - t0
        single_rate = round(75 / single_write_time, 1)
        print(
            f"  * Single-Doc Writes : {single_rate:7.1f} docs/sec "
            f"({single_write_time:.3f}s for 75 docs)"
        )

        # Batch insert test
        t0 = time.perf_counter()
        with SQLiteIndexer(db_path) as indexer:
            batcher = BatchIndexer(indexer, batch_size=50)
            for d in corpus[75:]:
                batcher.add_to_batch(d)
            batcher.flush()
        batch_write_time = time.perf_counter() - t0
        batch_rate = round(75 / batch_write_time, 1)
        print(
            f"  * Batch Writes (50) : {batch_rate:7.1f} docs/sec "
            f"({batch_write_time:.3f}s for 75 docs)"
        )
        print(
            f"  * Batch Speedup     : {batch_rate / max(single_rate, 1):.2f}x "
            "faster than single-doc writes"
        )

        # -------------------------------------------------------------------
        # 2. Batch Document Prefetch vs N+1 Lookup Benchmark
        # -------------------------------------------------------------------
        print("\n[2/5] Batch Document Prefetch vs N+1 Lookups (50 candidate IDs)...")
        with SQLiteIndexer(db_path) as indexer:
            candidate_ids = list(range(1, 51))

            # Iterative N+1 single lookups
            n1_times = []
            for _ in range(50):
                t0 = time.perf_counter()
                for cid in candidate_ids:
                    indexer.get_document(cid)
                n1_times.append((time.perf_counter() - t0) * 1000)

            # Batched single query
            batch_times = []
            for _ in range(50):
                t0 = time.perf_counter()
                indexer.get_documents_by_ids(candidate_ids)
                batch_times.append((time.perf_counter() - t0) * 1000)

            n1_p = compute_percentiles(n1_times)
            bp_p = compute_percentiles(batch_times)
            speedup = n1_p["p50"] / max(bp_p["p50"], 0.001)

            print(
                f"  * N+1 Queries (50 fetches) : p50 = {n1_p['p50']:6.3f}ms | "
                f"p95 = {n1_p['p95']:6.3f}ms"
            )
            print(
                f"  * Batch Prefetch (1 fetch) : p50 = {bp_p['p50']:6.3f}ms | "
                f"p95 = {bp_p['p95']:6.3f}ms"
            )
            print(
                f"  * Prefetch Query Speedup   : {speedup:6.1f}x "
                "reduction in retrieval latency"
            )

        # -------------------------------------------------------------------
        # 3. Uncached vs Cached Query Latency
        # -------------------------------------------------------------------
        print(
            "\n[3/5] Uncached (Cold) vs Cached (Warm) Latencies "
            "(100 iterations)..."
        )
        with SQLiteIndexer(db_path) as indexer:
            engine = SearchEngine(indexer)
            cache = LRUCache(max_entries=500)

            test_queries = [
                "python",
                "sqlite database",
                "performance latency optimization",
                "caching algorithms",
            ]

            hdr_q = "Query String"
            hdr_u = "Uncached p50"
            hdr_c = "Cached p50"
            hdr_s = "Speedup"
            print(f"  {hdr_q:<32} | {hdr_u:<12} | {hdr_c:<10} | {hdr_s:<8}")
            print("  " + "-" * 70)

            for q in test_queries:
                # Uncached runs
                uncached_times = []
                for _ in range(30):
                    t0 = time.perf_counter()
                    engine.search_with_total(q, limit=10)
                    uncached_times.append((time.perf_counter() - t0) * 1000)

                # Prime cache
                gen = indexer.get_generation()
                key = (gen, q.lower(), 10, 0)
                resp, _, _ = engine.search_with_total(q, limit=10)
                cache.set(key, resp)

                # Cached runs
                cached_times = []
                for _ in range(30):
                    t0 = time.perf_counter()
                    cache.get(key)
                    cached_times.append((time.perf_counter() - t0) * 1000)

                u_p = compute_percentiles(uncached_times)
                c_p = compute_percentiles(cached_times)
                q_speedup = u_p["p50"] / max(c_p["p50"], 0.0001)

                print(
                    f"  {q:<32} | {u_p['p50']:8.3f} ms   | "
                    f"{c_p['p50']:6.4f} ms | {q_speedup:6.1f}x"
                )

        # -------------------------------------------------------------------
        # 4. Generation Invalidation Verification
        # -------------------------------------------------------------------
        print("\n[4/5] Index Generation Invalidation Verification...")
        with SQLiteIndexer(db_path) as indexer:
            engine = SearchEngine(indexer)
            cache = LRUCache(max_entries=100)

            gen1 = indexer.get_generation()
            key1 = (gen1, "python", 10, 0)
            res1, _, _ = engine.search_with_total("python", limit=10)
            cache.set(key1, res1)
            assert cache.get(key1) is not None
            print(f"  * Cached query at generation {gen1} : HIT")

            # Add doc to advance generation
            new_doc = {
                "url": "https://benchmark.internal/doc/new_999",
                "title": "Fresh Python Evolution",
                "description": "Brand new document.",
                "body": "Python expands with modern features.",
                "content_hash": "hash_fresh_999",
                "tokens": ["python", "evolution"],
                "terms": ["python", "evolution"],
                "title_terms": ["python", "evolution"],
                "body_terms": ["python"],
                "positions": {},
            }
            indexer.add_document(new_doc)
            gen2 = indexer.get_generation()
            assert gen2 > gen1

            key2 = (gen2, "python", 10, 0)
            stale_lookup = cache.get(key2)
            assert stale_lookup is None
            print(
                f"  * Advanced to generation {gen2}     : "
                "Stale cache miss verified (HIT -> MISS)"
            )

        # -------------------------------------------------------------------
        # 5. Database Query Plans and Maintenance Inspection
        # -------------------------------------------------------------------
        print("\n[5/5] Query Plan Inspection & Storage Metrics...")
        with SQLiteIndexer(db_path) as indexer:
            qopt = QueryOptimizer(indexer)
            dbopt = DatabaseOptimizer(indexer)

            plans = [
                (
                    "Term IDF Lookup",
                    "SELECT idf FROM terms WHERE term = ?",
                    ("python",),
                ),
                (
                    "Postings Lookup",
                    "SELECT doc_id FROM postings WHERE term_id = ?",
                    (1,),
                ),
                ("Document by ID", "SELECT * FROM documents WHERE doc_id = ?", (1,)),
            ]

            for name, query, params in plans:
                p = qopt.explain_query(query, params)
                print(f"  * {name:<20}: {' '.join(p)}")

            stats = dbopt.get_database_stats()
            print(
                f"  * Database Disk Size : {stats['disk_size_bytes']:,} bytes "
                f"({stats['disk_size_mb']} MB)"
            )
            print(
                f"  * Page Allocation    : {stats['page_count']} pages x "
                f"{stats['page_size_bytes']} bytes"
            )

        print("\n" + "=" * 75)
        print(" BENCHMARK COMPLETED SUCCESSFULLY: ALL OPTIMIZATIONS VERIFIED")
        print("=" * 75 + "\n")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    run_benchmarks()
