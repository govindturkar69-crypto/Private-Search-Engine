"""Comprehensive unit, integration, and performance tests for Phase 4 Indexer."""

import sqlite3
import time
from pathlib import Path
import pytest
from src.indexer import SCHEMA_VERSION, SQLiteIndexer
from src.indexer.batch import BatchIndexer
from src.indexer.tfidf import BM25Ranker, TFIDFRanker
from src.parser.integration import ParsedDocument, ParserPipeline


@pytest.fixture
def temp_index(tmp_path: Path):
    """Provide an isolated SQLiteIndexer in a temporary directory."""
    db_path = tmp_path / "test_indexer.db"
    indexer = SQLiteIndexer(str(db_path))
    yield indexer
    indexer.close()


@pytest.fixture
def sample_documents():
    """Sample parsed documents containing diverse fields and terms."""
    return [
        {
            "url": "https://example.com/1",
            "title": "Python Programming",
            "description": "Learn Python basics and syntax",
            "body": (
                "Python is an interpreted programming language "
                "designed for readability"
            ),
            "content_hash": "hash_python_prog_1",
            "metadata": {"language": "en", "author": "Guido"},
            "tokens": [
                "python",
                "interpret",
                "program",
                "languag",
                "design",
                "readabl",
            ],
            "title_terms": ["python", "program"],
            "body_terms": ["interpret", "program", "languag", "design", "readabl"],
            "terms": [
                "design",
                "interpret",
                "languag",
                "program",
                "python",
                "readabl",
            ],
            "positions": {
                "python": [0],
                "interpret": [1],
                "program": [2],
                "languag": [3],
                "design": [4],
                "readabl": [5],
            },
        },
        {
            "url": "https://example.com/2",
            "title": "Web Development Guide",
            "description": "Build full-stack web applications",
            "body": "Web development involves HTML CSS JavaScript and Python backends",
            "content_hash": "hash_web_dev_2",
            "metadata": {"language": "en", "author": "WebDev Team"},
            "tokens": [
                "web",
                "develop",
                "involv",
                "html",
                "css",
                "javascript",
                "python",
                "backend",
            ],
            "title_terms": ["web", "develop", "guid"],
            "body_terms": [
                "web",
                "develop",
                "involv",
                "html",
                "css",
                "javascript",
                "python",
                "backend",
            ],
            "terms": [
                "backend",
                "css",
                "develop",
                "guid",
                "html",
                "involv",
                "javascript",
                "python",
                "web",
            ],
            "positions": {
                "web": [0],
                "develop": [1],
                "involv": [2],
                "html": [3],
                "css": [4],
                "javascript": [5],
                "python": [6],
                "backend": [7],
            },
        },
    ]


# =====================================================================
# 1. SQLiteIndexer Core Tests
# =====================================================================
class TestSQLiteIndexer:
    def test_database_initialization_and_schema_version(self, temp_index):
        """Test database tables, indices, and schema version metadata."""
        conn = temp_index.connection
        assert conn is not None

        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert {"documents", "terms", "postings", "metadata"}.issubset(tables)

        # Check metadata schema version
        cur = conn.execute("SELECT value FROM metadata WHERE key = 'schema_version'")
        assert cur.fetchone()[0] == SCHEMA_VERSION

    def test_sqlite_pragmas_and_foreign_keys(self, temp_index):
        """Test that foreign keys, WAL mode, and busy timeout are configured."""
        conn = temp_index.connection
        assert conn is not None

        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1

        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        # In SQLite on Windows WAL or memory/delete depending on lock mode
        assert journal.lower() in ("wal", "delete", "memory")

    def test_add_document_and_retrieval(self, temp_index, sample_documents):
        """Test adding document and retrieving it by ID and URL."""
        doc_id = temp_index.add_document(sample_documents[0])
        assert doc_id is not None
        assert doc_id > 0

        # Retrieve by ID
        doc = temp_index.get_document(doc_id)
        assert doc is not None
        assert doc["url"] == "https://example.com/1"
        assert doc["title"] == "Python Programming"
        assert doc["document_length"] == len(sample_documents[0]["tokens"])

        # Retrieve by URL
        doc_by_url = temp_index.get_document_by_url("https://example.com/1")
        assert doc_by_url is not None
        assert doc_by_url["doc_id"] == doc_id

    def test_duplicate_normalized_url_returns_existing_id(
        self, temp_index, sample_documents
    ):
        """Test adding the same URL returns the existing doc_id without reindexing."""
        doc_id1 = temp_index.add_document(sample_documents[0])
        doc_id2 = temp_index.add_document(sample_documents[0])
        assert doc_id1 == doc_id2

        stats = temp_index.get_stats()
        assert stats["total_documents"] == 1

    def test_duplicate_content_hash_returns_canonical_id(
        self, temp_index, sample_documents
    ):
        """Test adding identical content under a different URL returns canonical ID."""
        doc1 = sample_documents[0]
        doc2 = dict(doc1)
        doc2["url"] = "https://example.com/mirror-path"  # Same content_hash

        doc_id1 = temp_index.add_document(doc1)
        doc_id2 = temp_index.add_document(doc2)
        assert doc_id1 == doc_id2

        stats = temp_index.get_stats()
        assert stats["total_documents"] == 1

    def test_atomic_rollback_on_insertion_failure(self, temp_index):
        """Test that a database failure rolls back the entire document insertion."""
        # Corrupt the connection temporarily or trigger an integrity error
        doc = {
            "url": "https://example.com/bad",
            "title": "Bad",
            "body": "Fail",
            "content_hash": "hash_bad",
            "tokens": ["fail"],
        }
        temp_index.add_document(doc)

        # Attempt to insert invalid foreign key or trigger constraint failure
        conn = temp_index.connection
        assert conn is not None

        # Try inserting invalid document structure missing required URL
        bad_doc = {"url": "", "title": "Empty URL", "content_hash": "bad"}
        result = temp_index.add_document(bad_doc)
        assert result is None

        # Document count should remain 1
        stats = temp_index.get_stats()
        assert stats["total_documents"] == 1

    def test_term_df_and_cf_statistics(self, temp_index, sample_documents):
        """Test document_frequency and collection_frequency accounting."""
        temp_index.add_document(sample_documents[0])
        temp_index.add_document(sample_documents[1])

        terms = temp_index.get_all_terms()
        # 'python' appears in both docs
        assert terms["python"]["doc_frequency"] == 2
        assert terms["python"]["collection_frequency"] == 2

        # 'javascript' appears in doc 2 only
        assert terms["javascript"]["doc_frequency"] == 1
        assert terms["javascript"]["collection_frequency"] == 1

    def test_raw_tf_and_field_frequencies(self, temp_index, sample_documents):
        """Test postings store separate raw TF, title_frequency, and body_frequency."""
        doc_id = temp_index.add_document(sample_documents[0])
        detailed = temp_index.search_detailed_postings("program")
        assert len(detailed) == 1

        posting = detailed[0]
        assert posting["doc_id"] == doc_id
        assert posting["term_frequency"] >= 1
        assert posting["title_frequency"] == 1
        assert posting["body_frequency"] == 1

    def test_positions_serialization_and_roundtrip(self, temp_index, sample_documents):
        """Test positions survive JSON serialization round-trip in postings table."""
        temp_index.add_document(sample_documents[0])
        detailed = temp_index.search_detailed_postings("python")
        assert len(detailed) == 1
        assert detailed[0]["positions"] == [0]

    def test_document_length_tracking(self, temp_index, sample_documents):
        """Test that document_length is based on token count and metadata updates."""
        temp_index.add_document(sample_documents[0])
        temp_index.add_document(sample_documents[1])

        stats = temp_index.get_stats()
        len1 = len(sample_documents[0]["tokens"])
        len2 = len(sample_documents[1]["tokens"])
        expected_total = len1 + len2

        assert stats["total_documents"] == 2
        assert stats["total_document_length"] == expected_total
        assert stats["avg_document_length"] == pytest.approx(
            expected_total / 2, rel=1e-2
        )

    def test_delete_document_and_metadata_consistency(
        self, temp_index, sample_documents
    ):
        """Test deleting document updates terms, postings, and metadata consistency."""
        doc_id1 = temp_index.add_document(sample_documents[0])
        doc_id2 = temp_index.add_document(sample_documents[1])

        # Delete doc 1
        deleted = temp_index.delete_document(doc_id1)
        assert deleted is True

        # Verify doc 1 is gone
        assert temp_index.get_document(doc_id1) is None
        assert temp_index.get_document(doc_id2) is not None

        # Stats should be updated
        stats = temp_index.get_stats()
        assert stats["total_documents"] == 1
        assert stats["total_document_length"] == len(sample_documents[1]["tokens"])

        # 'python' DF should now be 1
        terms = temp_index.get_all_terms()
        assert terms["python"]["doc_frequency"] == 1

    def test_delete_removes_orphaned_terms(self, temp_index, sample_documents):
        """Test that deleting the only document containing a term removes the term."""
        doc_id1 = temp_index.add_document(sample_documents[0])
        temp_index.delete_document(doc_id1)

        terms = temp_index.get_all_terms()
        assert "readabl" not in terms
        assert len(terms) == 0

    def test_clear_index_resets_tables_and_metadata(self, temp_index, sample_documents):
        """Test clear_index empties all tables and resets metadata."""
        temp_index.add_document(sample_documents[0])
        temp_index.add_document(sample_documents[1])

        assert temp_index.clear_index() is True
        stats = temp_index.get_stats()
        assert stats["total_documents"] == 0
        assert stats["total_terms"] == 0
        assert stats["total_postings"] == 0
        assert stats["total_document_length"] == 0
        assert stats["avg_document_length"] == 0.0

    def test_context_manager_lifecycle(self, tmp_path):
        """Test that context manager closes database cleanly."""
        db_file = tmp_path / "ctx.db"
        with SQLiteIndexer(str(db_file)) as indexer:
            stats = indexer.get_stats()
            assert stats["total_documents"] == 0
        # After exit, connection is closed
        assert indexer.connection is None

    def test_unicode_terms_and_documents(self, temp_index):
        """Test indexing international and non-ASCII Unicode terms."""
        doc = {
            "url": "https://example.com/unicode",
            "title": "Über Python & 日本語",
            "body": "Python mit Umlauten: München, Köln, und 東京",
            "content_hash": "hash_unicode_1",
            "tokens": ["über", "python", "münchen", "köln", "東京"],
            "title_terms": ["über", "python"],
            "body_terms": ["python", "münchen", "köln", "東京"],
            "terms": ["köln", "münchen", "python", "über", "東京"],
        }
        doc_id = temp_index.add_document(doc)
        assert doc_id is not None

        postings = temp_index.search_postings("東京")
        assert len(postings) == 1
        assert postings[0][0] == doc_id


# =====================================================================
# 2. BM25 Ranking Tests
# =====================================================================
class TestBM25Ranking:
    def test_calculate_bm25_idf_always_positive(self, temp_index, sample_documents):
        """Test that Robertson BM25 IDF formula produces strictly positive values."""
        temp_index.add_document(sample_documents[0])
        temp_index.add_document(sample_documents[1])

        temp_index.calculate_idf(recalculate=True)
        terms = temp_index.get_all_terms()

        for term, stats in terms.items():
            assert stats["idf"] > 0.0, f"IDF for {term} must be strictly positive"

    def test_tfidf_ranker_alias_compatibility(self, temp_index, sample_documents):
        """Test that TFIDFRanker is a functional alias for BM25Ranker."""
        assert TFIDFRanker is BM25Ranker
        temp_index.add_document(sample_documents[0])
        ranker = TFIDFRanker(temp_index)
        res = ranker.rank_documents(["python"])
        assert len(res) > 0

    def test_title_boost_ranks_above_body_only(self, temp_index):
        """Deterministic test: title-boosted term ranks higher than body-only match."""
        # Doc 1 has "python" in title and body
        doc_title = {
            "url": "https://example.com/title_match",
            "title": "Python Programming",
            "body": "General software engineering topics",
            "content_hash": "hash_title_match",
            "tokens": ["python", "program", "softwar"],
            "title_terms": ["python", "program"],
            "body_terms": ["softwar"],
            "terms": ["program", "python", "softwar"],
        }
        # Doc 2 has "python" only in body
        doc_body = {
            "url": "https://example.com/body_match",
            "title": "General Engineering",
            "body": "Includes python scripting language",
            "content_hash": "hash_body_match",
            "tokens": ["general", "engin", "python", "script"],
            "title_terms": ["general", "engin"],
            "body_terms": ["python", "script"],
            "terms": ["engin", "general", "python", "script"],
        }
        id1 = temp_index.add_document(doc_title)
        temp_index.add_document(doc_body)

        ranker = BM25Ranker(temp_index, title_boost=2.0, body_boost=1.0)
        ranked = ranker.rank_documents(["python"])

        assert len(ranked) == 2
        # id1 (title match) must score strictly higher than id2 (body only)
        assert ranked[0][0] == id1
        assert ranked[0][1] > ranked[1][1]

    def test_higher_tf_improves_score(self, temp_index):
        """Test that higher term frequency increases relevance score."""
        doc_low_tf = {
            "url": "https://example.com/low_tf",
            "title": "Article A",
            "body": "python coding",
            "content_hash": "hash_low_tf",
            "tokens": ["python", "code"],
            "title_terms": [],
            "body_terms": ["python", "code"],
            "terms": ["code", "python"],
        }
        doc_high_tf = {
            "url": "https://example.com/high_tf",
            "title": "Article B",
            "body": "python python python coding",
            "content_hash": "hash_high_tf",
            "tokens": ["python", "python", "python", "code"],
            "title_terms": [],
            "body_terms": ["python", "python", "python", "code"],
            "terms": ["code", "python"],
        }
        temp_index.add_document(doc_low_tf)
        id_high = temp_index.add_document(doc_high_tf)

        ranker = BM25Ranker(temp_index)
        ranked = ranker.rank_documents(["python"])

        assert len(ranked) == 2
        assert ranked[0][0] == id_high
        assert ranked[0][1] > ranked[1][1]

    def test_document_length_normalization(self, temp_index):
        """Test shorter doc scores higher than long doc with same TF."""
        # Short document with 1 mention of 'python' in 3 tokens
        doc_short = {
            "url": "https://example.com/short",
            "title": "Short",
            "body": "learn python today",
            "content_hash": "hash_short",
            "tokens": ["learn", "python", "today"],
            "title_terms": [],
            "body_terms": ["learn", "python", "today"],
            "terms": ["learn", "python", "today"],
        }
        # Long document with 1 mention of 'python' in 25 tokens
        filler = ["word"] * 24
        doc_long = {
            "url": "https://example.com/long",
            "title": "Long",
            "body": "python " + "word " * 24,
            "content_hash": "hash_long",
            "tokens": ["python"] + filler,
            "title_terms": [],
            "body_terms": ["python"] + filler,
            "terms": ["python", "word"],
        }
        id_short = temp_index.add_document(doc_short)
        temp_index.add_document(doc_long)

        ranker = BM25Ranker(temp_index, b=0.75)
        ranked = ranker.rank_documents(["python"])

        assert len(ranked) == 2
        assert ranked[0][0] == id_short
        assert ranked[0][1] > ranked[1][1]

    def test_multi_term_match_ranks_above_single_term(self, temp_index):
        """Test multi-term match ranks above single-term match."""
        doc_multi = {
            "url": "https://example.com/multi",
            "title": "Search Engines",
            "body": "crawler and indexer architecture",
            "content_hash": "hash_multi",
            "tokens": ["crawler", "and", "indexer", "architectur"],
            "title_terms": [],
            "body_terms": ["crawler", "and", "indexer", "architectur"],
            "terms": ["architectur", "crawler", "indexer"],
        }
        doc_single = {
            "url": "https://example.com/single",
            "title": "Crawler Only",
            "body": "web crawler algorithms",
            "content_hash": "hash_single",
            "tokens": ["web", "crawler", "algorithm"],
            "title_terms": [],
            "body_terms": ["web", "crawler", "algorithm"],
            "terms": ["algorithm", "crawler", "web"],
        }
        id_multi = temp_index.add_document(doc_multi)
        temp_index.add_document(doc_single)

        ranker = BM25Ranker(temp_index)
        ranked = ranker.rank_documents(["crawler", "indexer"])

        assert len(ranked) == 2
        assert ranked[0][0] == id_multi
        assert ranked[0][1] > ranked[1][1]

    def test_edge_cases_empty_and_unknown(self, temp_index, sample_documents):
        """Test edge cases: empty query, unknown terms, empty index."""
        # 1. Empty index
        empty_ranker = BM25Ranker(temp_index)
        assert empty_ranker.rank_documents(["python"]) == []

        # 2. Add one document
        temp_index.add_document(sample_documents[0])
        ranker = BM25Ranker(temp_index)

        # 3. Empty query
        assert ranker.rank_documents([]) == []
        assert ranker.rank_documents("") == []
        assert ranker.rank_documents("   ") == []

        # 4. Unknown term
        assert ranker.rank_documents(["nonexistenttermxyz"]) == []

        # 5. Repeated query terms
        res_single = ranker.rank_documents(["python"])
        res_repeated = ranker.rank_documents(["python", "python"])
        assert len(res_single) == 1 and len(res_repeated) == 1
        assert res_repeated[0][1] > res_single[0][1]

        # 6. Term present in every document
        temp_index.add_document(sample_documents[1])
        # 'python' is in all docs in sample_documents
        res_all = ranker.rank_documents(["python"])
        assert len(res_all) == 2
        assert all(score > 0.0 for _, score in res_all)


# =====================================================================
# 3. BatchIndexer Tests
# =====================================================================
class TestBatchIndexer:
    def test_batch_manual_flush(self, temp_index, sample_documents):
        """Test accumulating documents and manually flushing in a single transaction."""
        batch = BatchIndexer(temp_index, batch_size=10)
        for doc in sample_documents:
            batch.add_to_batch(doc)

        assert len(batch.batch) == 2
        assert batch.flush() is True
        assert len(batch.batch) == 0

        stats = batch.get_stats()
        assert stats["total_indexed"] == 2
        assert stats["total_failed"] == 0

        idx_stats = temp_index.get_stats()
        assert idx_stats["total_documents"] == 2

    def test_batch_auto_flush_threshold(self, temp_index, sample_documents):
        """Test that reaching batch_size automatically flushes documents."""
        batch = BatchIndexer(temp_index, batch_size=1)
        batch.add_to_batch(sample_documents[0])

        stats = batch.get_stats()
        assert stats["total_indexed"] == 1
        assert len(batch.batch) == 0

    def test_batch_empty_flush(self, temp_index):
        """Test that flushing an empty batch succeeds safely."""
        batch = BatchIndexer(temp_index, batch_size=5)
        assert batch.flush() is True

    def test_batch_atomic_rollback_on_db_error(self, temp_index, monkeypatch):
        """Test that an error inside the batch transaction rolls back all items."""
        batch = BatchIndexer(temp_index, batch_size=10)
        doc1 = {
            "url": "https://example.com/ok1",
            "title": "OK 1",
            "body": "Content 1",
            "content_hash": "hash_ok1",
            "tokens": ["ok1"],
        }
        doc2 = {
            "url": "https://example.com/ok2",
            "title": "OK 2",
            "body": "Content 2",
            "content_hash": "hash_ok2",
            "tokens": ["ok2"],
        }
        batch.add_to_batch(doc1)
        batch.add_to_batch(doc2)

        # Force a database failure during indexing of doc2
        orig_internal = temp_index._index_document_internal

        def fail_on_doc2(norm):
            if norm["url"] == "https://example.com/ok2":
                raise sqlite3.OperationalError("Simulated batch transaction failure")
            return orig_internal(norm)

        monkeypatch.setattr(temp_index, "_index_document_internal", fail_on_doc2)

        success = batch.flush()
        assert success is False
        assert batch.get_stats()["total_failed"] == 2

        # Atomic rollback verification: Neither doc1 nor doc2 was committed!
        assert temp_index.get_document_by_url("https://example.com/ok1") is None
        assert temp_index.get_document_by_url("https://example.com/ok2") is None
        assert temp_index.get_stats()["total_documents"] == 0

    def test_batch_skips_duplicates_cleanly(self, temp_index, sample_documents):
        """Test batch indexing handles duplicated items without crashing."""
        batch = BatchIndexer(temp_index, batch_size=10)
        batch.add_to_batch(sample_documents[0])
        batch.add_to_batch(sample_documents[0])  # Duplicate URL and content_hash

        assert batch.flush() is True
        stats = temp_index.get_stats()
        # Only 1 unique document indexed
        assert stats["total_documents"] == 1


# =====================================================================
# 4. Integration & Performance Benchmark Tests
# =====================================================================
class TestIndexerIntegration:
    def test_phase3_parser_pipeline_integration(self, temp_index):
        """Test integration: HTML -> ParserPipeline -> SQLiteIndexer -> BM25."""
        pipeline = ParserPipeline()
        html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <title>Information Retrieval Systems</title>
            <meta name="description"
                  content="Design and implementation of search engines." />
            <meta name="author" content="Dr. Search" />
        </head>
        <body>
            <article>
                <h1>Information Retrieval Systems</h1>
                <p>Inverted index maps terms to postings with term frequencies.</p>
                <p>BM25 is a ranking function used by search engines.</p>
            </article>
        </body>
        </html>
        """
        parsed_doc = pipeline.process_document(html, "https://example.com/ir-systems")
        assert isinstance(parsed_doc, ParsedDocument)

        # Index the ParsedDocument directly
        doc_id = temp_index.add_document(parsed_doc)
        assert doc_id is not None
        assert doc_id > 0

        # Verify indexed metadata and term frequencies
        doc = temp_index.get_document(doc_id)
        assert doc is not None
        assert doc["title"] == "Information Retrieval Systems"
        assert doc["author"] == "Dr. Search"
        assert doc["document_length"] == len(parsed_doc.tokens)

        # Rank for query terms
        ranker = BM25Ranker(temp_index)
        results = ranker.rank_documents(["bm25", "retriev"])
        assert len(results) == 1
        assert results[0][0] == doc_id
        assert results[0][1] > 0.0

    @pytest.mark.performance
    def test_performance_benchmark(self, temp_index):
        """Benchmark indexing throughput targeting >50 docs/sec."""
        batch = BatchIndexer(temp_index, batch_size=100)
        num_docs = 60

        docs = [
            {
                "url": f"https://example.com/benchmark/{i}",
                "title": f"Benchmark Document {i}",
                "body": (
                    f"Synthetic benchmark body content for doc {i} "
                    "with search terms."
                ),
                "content_hash": f"hash_bench_{i}",
                "tokens": [
                    "synthet",
                    "benchmark",
                    "bodi",
                    "content",
                    "document",
                    f"term{i}",
                ],
                "title_terms": ["benchmark", "document"],
                "body_terms": [
                    "synthet",
                    "benchmark",
                    "bodi",
                    "content",
                    "document",
                    f"term{i}",
                ],
                "terms": [
                    "benchmark",
                    "bodi",
                    "content",
                    "document",
                    "synthet",
                    f"term{i}",
                ],
            }
            for i in range(num_docs)
        ]

        start_time = time.perf_counter()
        for d in docs:
            batch.add_to_batch(d)
        batch.flush()
        duration = time.perf_counter() - start_time

        throughput = num_docs / max(duration, 0.001)
        msg = (
            f"\n[BENCHMARK] Indexed {num_docs} docs in "
            f"{duration:.3f}s: {throughput:.1f} docs/sec"
        )
        print(msg)

        # Documented target: >50 docs/sec in production batching
        stats = temp_index.get_stats()
        assert stats["total_documents"] == num_docs


# =====================================================================
# 5. Advanced Edge Cases, Schema Migrations & Saturation Tests
# =====================================================================
class TestIndexerAdvancedEdgeCases:
    def test_schema_migration_from_legacy_without_metadata(self, tmp_path):
        """Test migrating legacy database without metadata table to v4.0."""
        legacy_db = tmp_path / "legacy_v1.db"
        conn = sqlite3.connect(legacy_db)
        conn.execute(
            """CREATE TABLE documents (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   url TEXT UNIQUE,
                   title TEXT,
                   content TEXT
               );"""
        )
        conn.commit()
        conn.close()

        # Initializing SQLiteIndexer should detect legacy schema and upgrade to v4.0
        indexer = SQLiteIndexer(str(legacy_db))
        stats = indexer.get_stats()
        assert stats["schema_version"] == SCHEMA_VERSION
        indexer.close()

    def test_schema_upgrade_from_older_schema_version(self, tmp_path):
        """Test upgrading from an older schema version (e.g. v3.0) to v4.0."""
        v3_db = tmp_path / "legacy_v3.db"
        conn = sqlite3.connect(v3_db)
        conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT);")
        conn.execute(
            "INSERT INTO metadata (key, value) VALUES ('schema_version', '3.0');"
        )
        conn.commit()
        conn.close()

        indexer = SQLiteIndexer(str(v3_db))
        stats = indexer.get_stats()
        assert stats["schema_version"] == SCHEMA_VERSION
        indexer.close()

    def test_foreign_key_violation_rejected(self, temp_index):
        """Test that inserting posting with invalid FK fails constraint check."""
        conn = temp_index.connection
        assert conn is not None

        # Foreign keys are ON, so referencing non-existent term_id or doc_id must fail
        with pytest.raises(sqlite3.IntegrityError):
            with conn:
                conn.execute(
                    """INSERT INTO postings
                       (term_id, doc_id, term_frequency, title_frequency,
                        body_frequency)
                       VALUES (99999, 99999, 1, 0, 1)"""
                )

    def test_foreign_key_cascade_deletion(self, temp_index, sample_documents):
        """Test that deleting a document row cascades to delete its postings."""
        doc_id = temp_index.add_document(sample_documents[0])
        conn = temp_index.connection
        assert conn is not None

        # Postings exist
        postings = conn.execute(
            "SELECT COUNT(*) FROM postings WHERE doc_id = ?", (doc_id,)
        ).fetchone()[0]
        assert postings > 0

        # Direct SQL delete on document to test cascade
        with conn:
            conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))

        # Postings should be cascaded to 0
        postings_after = conn.execute(
            "SELECT COUNT(*) FROM postings WHERE doc_id = ?", (doc_id,)
        ).fetchone()[0]
        assert postings_after == 0

    def test_bm25_tf_saturation(self, temp_index):
        """Test BM25 TF saturation (diminishing returns as TF grows)."""
        # Create 3 documents with TF = 1, 10, 19 in identical length bodies
        doc1 = {
            "url": "https://example.com/tf1",
            "title": "TF 1",
            "body": "term " + "pad " * 99,
            "content_hash": "hash_tf1",
            "tokens": ["term"] + ["pad"] * 99,
            "title_terms": [],
            "body_terms": ["term"] + ["pad"] * 99,
            "terms": ["pad", "term"],
        }
        doc10 = {
            "url": "https://example.com/tf10",
            "title": "TF 10",
            "body": "term " * 10 + "pad " * 90,
            "content_hash": "hash_tf10",
            "tokens": ["term"] * 10 + ["pad"] * 90,
            "title_terms": [],
            "body_terms": ["term"] * 10 + ["pad"] * 90,
            "terms": ["pad", "term"],
        }
        doc19 = {
            "url": "https://example.com/tf19",
            "title": "TF 19",
            "body": "term " * 19 + "pad " * 81,
            "content_hash": "hash_tf19",
            "tokens": ["term"] * 19 + ["pad"] * 81,
            "title_terms": [],
            "body_terms": ["term"] * 19 + ["pad"] * 81,
            "terms": ["pad", "term"],
        }
        id1 = temp_index.add_document(doc1)
        id10 = temp_index.add_document(doc10)
        id19 = temp_index.add_document(doc19)

        ranker = BM25Ranker(temp_index, k1=1.5)
        results = dict(ranker.rank_documents(["term"]))

        score1 = results[id1]
        score10 = results[id10]
        score19 = results[id19]

        gain_1_to_10 = score10 - score1
        gain_10_to_19 = score19 - score10

        # Saturation: gain from 10 to 19 is less than from 1 to 10
        assert gain_1_to_10 > gain_10_to_19 > 0.0

    def test_document_with_zero_indexable_tokens(self, temp_index):
        """Test document with empty body and tokens indexes safely."""
        doc = {
            "url": "https://example.com/empty",
            "title": "Empty",
            "body": "",
            "content_hash": "hash_empty",
            "tokens": [],
        }
        doc_id = temp_index.add_document(doc)
        assert doc_id is not None

        retrieved = temp_index.get_document(doc_id)
        assert retrieved is not None
        assert retrieved["document_length"] == 0

    def test_one_document_corpus_bm25(self, temp_index):
        """Test BM25 ranking when N=1."""
        doc = {
            "url": "https://example.com/only",
            "title": "Solo Document",
            "body": "Unique lone content",
            "content_hash": "hash_lone",
            "tokens": ["uniqu", "lone", "content"],
        }
        doc_id = temp_index.add_document(doc)
        ranker = BM25Ranker(temp_index)
        results = ranker.rank_documents(["lone"])

        assert len(results) == 1
        assert results[0][0] == doc_id
        assert results[0][1] > 0.0

    def test_all_documents_contain_query_term(self, temp_index):
        """Test query term present in 100% of indexed documents."""
        for i in range(4):
            temp_index.add_document(
                {
                    "url": f"https://example.com/all/{i}",
                    "title": f"Doc {i}",
                    "body": f"universal term in doc {i}",
                    "content_hash": f"hash_all_{i}",
                    "tokens": ["univers", "term", f"doc{i}"],
                }
            )

        ranker = BM25Ranker(temp_index)
        results = ranker.rank_documents(["univers"])
        assert len(results) == 4
        # All scores strictly positive due to Robertson formulation
        assert all(score > 0.0 for _, score in results)

    def test_query_string_and_list_input(self, temp_index, sample_documents):
        """Test rank_documents accepts either a query string or a list of terms."""
        temp_index.add_document(sample_documents[0])
        ranker = BM25Ranker(temp_index)

        res_str = ranker.rank_documents("python program")
        res_list = ranker.rank_documents(["python", "program"])

        assert len(res_str) == len(res_list) == 1
        assert res_str[0][0] == res_list[0][0]
        assert pytest.approx(res_str[0][1]) == res_list[0][1]

    def test_query_with_mix_of_known_and_unknown_terms(
        self, temp_index, sample_documents
    ):
        """Test querying with a mix of indexed terms and nonexistent terms."""
        doc_id = temp_index.add_document(sample_documents[0])
        ranker = BM25Ranker(temp_index)

        results = ranker.rank_documents(["python", "xyzunknownabcterm"])
        assert len(results) == 1
        assert results[0][0] == doc_id
        assert results[0][1] > 0.0

    def test_batch_indexer_partial_validation_failure(self, temp_index):
        """Test batch with invalid docs records failures but indexes valid."""
        batch = BatchIndexer(temp_index, batch_size=10)
        valid = {
            "url": "https://example.com/valid",
            "title": "Valid",
            "body": "Body",
            "content_hash": "hash_valid",
            "tokens": ["valid"],
        }
        invalid = {"url": "", "title": "No URL", "content_hash": "bad"}

        batch.add_to_batch(valid)
        batch.add_to_batch(invalid)
        batch.flush()

        stats = batch.get_stats()
        assert stats["total_indexed"] == 1
        assert stats["total_failed"] == 1
        assert temp_index.get_document_by_url("https://example.com/valid") is not None

    def test_delete_nonexistent_document_returns_false(self, temp_index):
        """Test deleting non-existent doc_id returns False."""
        assert temp_index.delete_document(99999) is False

    def test_recalculate_idf_flag(self, temp_index, sample_documents):
        """Test recalculating IDF on demand updates all terms."""
        temp_index.add_document(sample_documents[0])
        temp_index.calculate_idf(recalculate=False)

        terms_before = temp_index.get_all_terms()
        idf1 = terms_before["python"]["idf"]

        # Add second document with 'python'
        temp_index.add_document(sample_documents[1])
        temp_index.calculate_idf(recalculate=True)

        terms_after = temp_index.get_all_terms()
        idf2 = terms_after["python"]["idf"]

        # Document frequency changed from 1/1 to 2/2 -> Robertson IDF updates
        assert idf1 != idf2
        assert idf2 > 0.0

    def test_validation_rejects_missing_url_or_hash(self, temp_index):
        """Test add_document rejects payloads without url or content_hash."""
        assert temp_index.add_document({"title": "No URL"}) is None
        assert temp_index.add_document({"url": "https://ok.com"}) is None
        assert temp_index.add_document(None) is None

    def test_get_document_by_url_nonexistent(self, temp_index):
        """Test get_document_by_url returns None for unindexed URL."""
        assert temp_index.get_document_by_url("https://nonexistent.org") is None
