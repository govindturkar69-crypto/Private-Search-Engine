"""Unit tests for database optimization, generation persistence, and batch prefetch."""

from pathlib import Path
from typing import Any, Dict
import pytest
from src.db.optimizer import DatabaseOptimizer
from src.db.query_optimizer import QueryOptimizer
from src.indexer import SQLiteIndexer
from src.indexer.batch import BatchIndexer


@pytest.fixture
def temp_db(tmp_path: Path) -> str:
    """Provide a fresh SQLite database path in a temporary directory."""
    return str(tmp_path / "test_perf.db")


@pytest.fixture
def sample_doc() -> Dict[str, Any]:
    """Sample parsed document payload."""
    return {
        "url": "https://example.com/python-guide",
        "title": "Python Performance Guide",
        "description": "Comprehensive guide to optimizing Python code and SQLite.",
        "body": "Python performance optimization requires measurement and batching.",
        "content_hash": "hash_sample_001",
        "tokens": ["python", "performance", "guide", "optimizing", "sqlite"],
        "terms": ["python", "performance", "guide", "optimizing", "sqlite"],
        "title_terms": ["python", "performance", "guide"],
        "body_terms": ["python", "performance", "optimizing", "sqlite"],
        "positions": {"python": [0, 4]},
    }


class TestIndexGeneration:
    """Test persistent index generation tracking across operations and restarts."""

    def test_persistent_generation_across_indexer_restarts(
        self, temp_db: str, sample_doc: Dict[str, Any]
    ) -> None:
        """Generation must persist to disk across connection lifecycles."""
        with SQLiteIndexer(temp_db) as indexer:
            initial_gen = indexer.get_generation()
            assert initial_gen == 1

            # Add document: generation advances
            doc_id = indexer.add_document(sample_doc)
            assert doc_id is not None
            assert indexer.get_generation() == 2

        # Open fresh indexer instance pointing to same file
        with SQLiteIndexer(temp_db) as indexer2:
            assert indexer2.get_generation() == 2

    def test_no_op_non_advancement(
        self, temp_db: str, sample_doc: Dict[str, Any]
    ) -> None:
        """Skipped duplicates (URL/hash match) must not advance generation."""
        with SQLiteIndexer(temp_db) as indexer:
            indexer.add_document(sample_doc)
            gen_after_first = indexer.get_generation()
            assert gen_after_first == 2

            # Duplicate URL insertion
            dup_id = indexer.add_document(sample_doc)
            assert dup_id is not None
            assert indexer.get_generation() == gen_after_first

            # Duplicate content hash insertion with different URL
            sample_doc2 = dict(sample_doc)
            sample_doc2["url"] = "https://example.com/other-url"
            dup_hash_id = indexer.add_document(sample_doc2)
            assert dup_hash_id is not None
            assert indexer.get_generation() == gen_after_first

    def test_batch_flush_single_generation_increment(
        self, temp_db: str, sample_doc: Dict[str, Any]
    ) -> None:
        """Batch flush of new documents must advance generation exactly once."""
        with SQLiteIndexer(temp_db) as indexer:
            batch_indexer = BatchIndexer(indexer, batch_size=10)
            initial_gen = indexer.get_generation()

            for i in range(5):
                doc = dict(sample_doc)
                doc["url"] = f"https://example.com/doc_{i}"
                doc["content_hash"] = f"hash_{i}"
                batch_indexer.add_to_batch(doc)

            batch_indexer.flush()
            # Must increment by 1 for the whole batch commit
            assert indexer.get_generation() == initial_gen + 1


class TestBatchPrefetch:
    """Test parameterized batch document prefetching."""

    def test_batch_prefetch_documents(
        self, temp_db: str, sample_doc: Dict[str, Any]
    ) -> None:
        """Verify prefetch handles empty, deduplicated, and multiple IDs correctly."""
        with SQLiteIndexer(temp_db) as indexer:
            # 1. Empty list
            assert indexer.get_documents_by_ids([]) == {}

            # Add documents
            doc_ids = []
            for i in range(3):
                doc = dict(sample_doc)
                doc["url"] = f"https://example.com/batch_{i}"
                doc["content_hash"] = f"hash_b_{i}"
                did = indexer.add_document(doc)
                assert did is not None
                doc_ids.append(did)

            # 2. Valid multi-lookup
            docs_map = indexer.get_documents_by_ids(doc_ids)
            assert len(docs_map) == 3
            for did in doc_ids:
                assert did in docs_map
                assert docs_map[did]["doc_id"] == did

            # 3. Duplicate IDs in query
            dup_query = doc_ids + doc_ids
            docs_map_dup = indexer.get_documents_by_ids(dup_query)
            assert len(docs_map_dup) == 3

            # 4. Partial nonexistent ID
            mixed_ids = doc_ids + [99999]
            docs_map_mixed = indexer.get_documents_by_ids(mixed_ids)
            assert len(docs_map_mixed) == 3
            assert 99999 not in docs_map_mixed

    def test_query_optimizer_delegation(
        self, temp_db: str, sample_doc: Dict[str, Any]
    ) -> None:
        """QueryOptimizer.prefetch_documents must delegate to indexer."""
        with SQLiteIndexer(temp_db) as indexer:
            did = indexer.add_document(sample_doc)
            assert did is not None
            optimizer = QueryOptimizer(indexer)
            res = optimizer.prefetch_documents([did])
            assert did in res
            assert res[did]["title"] == "Python Performance Guide"


class TestQueryPlanAndMaintenance:
    """Test EXPLAIN QUERY PLAN analysis and controlled maintenance helpers."""

    def test_explain_query_plan(self, temp_db: str, sample_doc: Dict[str, Any]) -> None:
        """Explain query plan must inspect SQLite plan details."""
        with SQLiteIndexer(temp_db) as indexer:
            indexer.add_document(sample_doc)
            optimizer = QueryOptimizer(indexer)

            plan = optimizer.explain_query(
                "SELECT idf FROM terms WHERE term = ?", ("python",)
            )
            assert len(plan) > 0
            plan_str = " ".join(plan)
            assert "SEARCH terms USING INDEX" in plan_str

    def test_inspect_pragmas_and_stats(
        self, temp_db: str, sample_doc: Dict[str, Any]
    ) -> None:
        """DatabaseOptimizer must inspect PRAGMAs and database allocation."""
        with SQLiteIndexer(temp_db) as indexer:
            indexer.add_document(sample_doc)
            db_opt = DatabaseOptimizer(indexer)

            stats = db_opt.get_database_stats()
            assert stats["page_count"] > 0
            assert stats["page_size_bytes"] == 4096
            assert stats["disk_size_bytes"] > 0

            pragmas = db_opt.inspect_pragmas()
            assert pragmas["journal_mode"].lower() == "wal"
            assert pragmas["foreign_keys"] == 1

    def test_run_maintenance_operations(
        self, temp_db: str, sample_doc: Dict[str, Any]
    ) -> None:
        """DatabaseOptimizer must execute maintenance operations safely."""
        with SQLiteIndexer(temp_db) as indexer:
            indexer.add_document(sample_doc)
            db_opt = DatabaseOptimizer(indexer)

            opt_res = db_opt.run_maintenance("optimize")
            assert opt_res["status"] == "success"

            analyze_res = db_opt.run_maintenance("analyze")
            assert analyze_res["status"] == "success"

            reindex_res = db_opt.run_maintenance("reindex")
            assert reindex_res["status"] == "success"

            vacuum_res = db_opt.run_maintenance("vacuum")
            assert vacuum_res["status"] == "success"

            with pytest.raises(ValueError, match="Unsupported maintenance operation"):
                db_opt.run_maintenance("drop_all_tables")
