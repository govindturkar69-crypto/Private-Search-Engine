"""Isolated performance and latency benchmark test suite.

Marked with @pytest.mark.performance to exclude from fast regression runs.
Reports statistical measures (median, p95) without machine-dependent failures.
"""

import os
from pathlib import Path
import statistics
import time
from typing import Any, Dict, List
import pytest
from src.indexer import SQLiteIndexer
from src.indexer.batch import BatchIndexer
from src.parser.integration import ParserPipeline
from src.ranker.search import SearchEngine


def _generate_benchmark_corpus(count: int = 100) -> List[Dict[str, Any]]:
    """Generate controlled deterministic documents for performance benchmarking."""
    topics = [
        "python",
        "algorithms",
        "databases",
        "networking",
        "distributed",
        "security",
    ]
    docs: List[Dict[str, Any]] = []

    for i in range(count):
        topic = topics[i % len(topics)]
        docs.append(
            {
                "url": f"https://benchmark.test/doc/{i}",
                "title": f"Document {i} on {topic.capitalize()} and Web Architecture",
                "description": (
                    f"Performance benchmark entry {i} covering {topic} systems."
                ),
                "body": (
                    f"Comprehensive architectural study of {topic} computing. "
                    f"In this paper number {i}, we explore indexing throughput, "
                    f"query latency, inverted index postings, and token processing. "
                    "Modern platforms require resilient retrieval and fast response."
                ),
                "content_hash": f"perf_hash_{i}_{topic}",
                "author": "Guido" if i % 2 == 0 else "BenchmarkTeam",
                "language": "en",
            }
        )
    return docs


@pytest.mark.performance
class TestIndexingThroughput:
    """Benchmark indexing throughput across parser, single insert, and batch."""

    def test_indexing_components_benchmark(self, tmp_path: Path) -> None:
        """Measure parser throughput, single SQLite insert, and batch indexing."""
        corpus = _generate_benchmark_corpus(100)
        parser = ParserPipeline()

        # 1. Measure Parser Throughput
        start_parse = time.perf_counter()
        parsed_docs = []
        for doc in corpus:
            raw_html = (
                f"<html><head><title>{doc['title']}</title></head>"
                f"<body><h1>{doc['title']}</h1><p>{doc['body']}</p></body></html>"
            )
            parsed = parser.process_document(html=raw_html, url=doc["url"])
            if parsed:
                parsed_docs.append(parsed)
        parse_duration = time.perf_counter() - start_parse
        parser_docs_per_sec = (
            len(parsed_docs) / parse_duration if parse_duration > 0 else 0
        )

        # 2. Measure Single-Document SQLite Indexing
        single_db_path = str(tmp_path / "single_perf.db")
        single_indexer = SQLiteIndexer(single_db_path)
        start_single = time.perf_counter()
        for p in parsed_docs:
            single_indexer.add_document(p)
        single_indexer.calculate_idf(recalculate=True)
        single_duration = time.perf_counter() - start_single
        single_docs_per_sec = (
            len(parsed_docs) / single_duration if single_duration > 0 else 0
        )
        single_indexer.close()

        # 3. Measure Batch Indexer Throughput
        batch_db_path = str(tmp_path / "batch_perf.db")
        batch_indexer = SQLiteIndexer(batch_db_path)
        batcher = BatchIndexer(batch_indexer, batch_size=50)
        start_batch = time.perf_counter()
        for p in parsed_docs:
            batcher.add_to_batch(p)
        batcher.flush()
        batch_indexer.calculate_idf(recalculate=True)
        batch_duration = time.perf_counter() - start_batch
        batch_docs_per_sec = (
            len(parsed_docs) / batch_duration if batch_duration > 0 else 0
        )
        batch_indexer.close()

        # Diagnostic benchmark output
        print(f"\n--- Indexing Benchmark (N={len(parsed_docs)}) ---")
        p_sec = f"{parser_docs_per_sec:.1f} docs/sec ({parse_duration:.3f}s)"
        print(f"Parser Throughput:       {p_sec}")
        s_sec = f"{single_docs_per_sec:.1f} docs/sec ({single_duration:.3f}s)"
        print(f"Single-Doc SQLite Write: {s_sec}")
        b_sec = f"{batch_docs_per_sec:.1f} docs/sec ({batch_duration:.3f}s)"
        print(f"Batch SQLite Write:      {b_sec}")

        # Sanity check: operations completed successfully
        assert len(parsed_docs) >= 90
        assert batch_docs_per_sec > 0


@pytest.mark.performance
class TestQueryLatencyBenchmark:
    """Benchmark query latency across terms, phrases, and filtered search."""

    @pytest.fixture(autouse=True)
    def setup_seeded_engine(self, tmp_path: Path) -> Any:
        """Seed a benchmark index with 150 documents for realistic retrieval pools."""
        self.db_path = str(tmp_path / "query_perf.db")
        self.indexer = SQLiteIndexer(self.db_path)
        batcher = BatchIndexer(self.indexer, batch_size=50)

        corpus = _generate_benchmark_corpus(150)
        parser = ParserPipeline()
        for doc in corpus:
            raw_html = (
                f"<html><head><title>{doc['title']}</title></head>"
                f"<body><article><h1>{doc['title']}</h1>"
                f"<p>{doc['body']}</p></article></body></html>"
            )
            parsed = parser.process_document(html=raw_html, url=doc["url"])
            if parsed:
                batcher.add_to_batch(parsed)
        batcher.flush()
        self.indexer.calculate_idf(recalculate=True)
        self.engine = SearchEngine(self.indexer)
        yield
        self.indexer.close()

    def test_search_latencies_across_query_types(self) -> None:
        """Benchmark query latencies with warmup, reporting median and p95 latency."""
        # Warmup query
        self.engine.search_with_total("python", limit=10)

        queries = {
            "single_term": "python",
            "multi_term": "python indexing latency",
            "exact_phrase": '"query latency"',
            "field_filtered": "author:Guido python",
        }

        iterations = 50
        results_summary: Dict[str, Dict[str, float]] = {}

        for query_type, q_str in queries.items():
            timings: List[float] = []
            for _ in range(iterations):
                start = time.perf_counter()
                results, total, err = self.engine.search_with_total(q_str, limit=10)
                elapsed_ms = (time.perf_counter() - start) * 1000
                timings.append(elapsed_ms)
                assert err is None

            timings.sort()
            median_ms = statistics.median(timings)
            p95_ms = timings[int(len(timings) * 0.95)]
            results_summary[query_type] = {
                "median_ms": round(median_ms, 2),
                "p95_ms": round(p95_ms, 2),
                "min_ms": round(min(timings), 2),
                "max_ms": round(max(timings), 2),
            }

        print("\n--- Search Query Latency Benchmarks (50 iterations each) ---")
        for q_type, stats in results_summary.items():
            print(
                f"{q_type:<16}: median={stats['median_ms']:>6.2f}ms  "
                f"p95={stats['p95_ms']:>6.2f}ms  "
                f"[min={stats['min_ms']:.2f}ms, max={stats['max_ms']:.2f}ms]"
            )

        # Sanity check: all queries executed successfully
        assert len(results_summary) == 4

    def test_autocomplete_latency_benchmark(self) -> None:
        """Benchmark autocomplete suggestion retrieval latency."""
        # Warmup
        self.engine.get_suggestions("py", limit=5)

        prefixes = ["py", "doc", "alg", "net"]
        timings: List[float] = []

        for pfx in prefixes * 25:
            start = time.perf_counter()
            suggestions = self.engine.get_suggestions(pfx, limit=5)
            elapsed_ms = (time.perf_counter() - start) * 1000
            timings.append(elapsed_ms)
            assert isinstance(suggestions, list)

        median_ms = statistics.median(timings)
        p95_ms = sorted(timings)[int(len(timings) * 0.95)]

        print("\n--- Autocomplete Suggestion Latency (100 iterations) ---")
        print(f"Median Latency: {median_ms:.2f}ms")
        print(f"P95 Latency:    {p95_ms:.2f}ms")
        assert len(timings) == 100


@pytest.mark.performance
class TestDatabaseOverhead:
    """Benchmark SQLite index storage overhead relative to raw text corpus."""

    def test_sqlite_storage_overhead_ratio(self, tmp_path: Path) -> None:
        """Measure sqlite_file_size / raw_corpus_bytes as an informational metric."""
        db_path = str(tmp_path / "storage_overhead.db")
        indexer = SQLiteIndexer(db_path)
        batcher = BatchIndexer(indexer, batch_size=50)

        corpus = _generate_benchmark_corpus(100)
        raw_corpus_bytes = 0
        parser = ParserPipeline()

        for doc in corpus:
            raw_corpus_bytes += len(doc["title"].encode("utf-8"))
            raw_corpus_bytes += len(doc["body"].encode("utf-8"))
            raw_html = (
                f"<html><head><title>{doc['title']}</title></head>"
                f"<body><p>{doc['body']}</p></body></html>"
            )
            parsed = parser.process_document(html=raw_html, url=doc["url"])
            if parsed:
                batcher.add_to_batch(parsed)

        batcher.flush()
        indexer.calculate_idf(recalculate=True)
        indexer.close()

        sqlite_size_bytes = os.path.getsize(db_path)
        overhead_ratio = (
            sqlite_size_bytes / raw_corpus_bytes if raw_corpus_bytes > 0 else 0
        )

        print("\n--- SQLite Database Storage Overhead ---")
        raw_kb = raw_corpus_bytes / 1024
        print(f"Raw Text Corpus:       {raw_corpus_bytes:,} bytes ({raw_kb:.1f} KB)")
        sqlite_kb = sqlite_size_bytes / 1024
        print(
            f"SQLite Index DB File:  {sqlite_size_bytes:,} bytes ({sqlite_kb:.1f} KB)"
        )
        print(f"Index Overhead Ratio:  {overhead_ratio:.2f}x")

        assert sqlite_size_bytes > 0
        assert overhead_ratio > 0
