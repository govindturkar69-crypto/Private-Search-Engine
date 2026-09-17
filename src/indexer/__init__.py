"""SQLite-based inverted index engine with BM25 TF/IDF support."""

import json
import logging
import math
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "4.0"


class SQLiteIndexer:
    """SQLite-based inverted index engine tracking term and field frequencies."""

    def __init__(self, db_path: str = "data/index.db") -> None:
        self.db_path = db_path
        self._index_generation = 1
        self._ensure_db_exists()
        self.connection: Optional[sqlite3.Connection] = None
        self._connect()

    def _ensure_db_exists(self) -> None:
        """Ensure database and schema exist with proper versioning."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        schema_path = Path(__file__).parent / "schema.sql"

        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found at {schema_path}")

        with open(schema_path, "r", encoding="utf-8") as f:
            schema = f.read()

        conn = sqlite3.connect(self.db_path)
        try:
            # Check for existing schema version or legacy tables
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='metadata'"
            )
            has_metadata = cursor.fetchone() is not None

            should_initialize = True
            if has_metadata:
                cursor.execute("SELECT value FROM metadata WHERE key='schema_version'")
                row = cursor.fetchone()
                if row and row[0] == SCHEMA_VERSION:
                    should_initialize = False
                else:
                    # Incompatible legacy schema: drop legacy tables to migrate cleanly
                    logger.warning(
                        "Incompatible or legacy schema detected. Upgrading to 4.0..."
                    )
                    conn.executescript(
                        """
                        DROP TABLE IF EXISTS postings;
                        DROP TABLE IF EXISTS terms;
                        DROP TABLE IF EXISTS documents;
                        DROP TABLE IF EXISTS metadata;
                        """
                    )
            else:
                # Check if old documents table without metadata exists
                cursor.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='documents'"
                )
                if cursor.fetchone() is not None:
                    logger.warning("Legacy unversioned schema found. Upgrading...")
                    conn.executescript(
                        """
                        DROP TABLE IF EXISTS postings;
                        DROP TABLE IF EXISTS terms;
                        DROP TABLE IF EXISTS documents;
                        """
                    )

            if should_initialize:
                conn.executescript(schema)
                conn.commit()
                logger.info(
                    f"Database schema initialized (v{SCHEMA_VERSION}): {self.db_path}"
                )
        finally:
            conn.close()

    def _connect(self) -> None:
        """Create connection to SQLite database with robust PRAGMAs."""
        self.connection = sqlite3.connect(
            self.db_path, timeout=5.0, check_same_thread=False
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON;")
        self.connection.execute("PRAGMA journal_mode = WAL;")
        self.connection.execute("PRAGMA busy_timeout = 5000;")
        self.connection.execute("PRAGMA synchronous = NORMAL;")

        # Ensure index_generation row exists in metadata
        try:
            self.connection.execute(
                "INSERT OR IGNORE INTO metadata (key, value) "
                "VALUES ('index_generation', '1');"
            )
            self.connection.commit()
            self._load_generation()
        except Exception as e:
            logger.debug(f"Could not initialize index_generation metadata: {e}")

    def _load_generation(self) -> int:
        """Load index generation from metadata table into memory."""
        if self.connection is None:
            return getattr(self, "_index_generation", 1)
        try:
            row = self.connection.execute(
                "SELECT value FROM metadata WHERE key = 'index_generation'"
            ).fetchone()
            if row and row[0] is not None:
                self._index_generation = int(row[0])
                return self._index_generation
        except Exception:
            pass
        return getattr(self, "_index_generation", 1)

    def get_generation(self) -> int:
        """Return the current persistent index generation."""
        return self._load_generation()

    def _bump_generation_internal(self) -> int:
        """Advance index generation within an active transaction.

        Must be called within an active transaction (`with self.connection:`).
        """
        assert self.connection is not None
        now_iso = datetime.utcnow().isoformat()
        self.connection.execute(
            """UPDATE metadata
               SET value = CAST(CAST(COALESCE(value, '1') AS INTEGER) + 1 AS TEXT),
                   updated_at = ?
               WHERE key = 'index_generation'""",
            (now_iso,),
        )
        row = self.connection.execute(
            "SELECT value FROM metadata WHERE key = 'index_generation'"
        ).fetchone()
        gen = (
            int(row[0]) if row and row[0] is not None else (self._index_generation + 1)
        )
        self._index_generation = gen
        return gen

    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            try:
                self.connection.close()
            except Exception:
                pass
            self.connection = None

    def __enter__(self) -> "SQLiteIndexer":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()

    def _normalize_document(self, parsed_doc: Any) -> Dict[str, Any]:
        """Normalize ParsedDocument or dictionary into standardized indexing payload."""
        if parsed_doc is None:
            raise ValueError("Document cannot be None")

        if isinstance(parsed_doc, dict):
            url = str(parsed_doc.get("url", "")).strip()
            title = str(parsed_doc.get("title", "")).strip()
            description = str(parsed_doc.get("description", "")).strip()
            body = str(parsed_doc.get("body", "")).strip()
            content_hash = str(parsed_doc.get("content_hash", "")).strip()
            metadata = parsed_doc.get("metadata", {})
            tokens = parsed_doc.get("tokens", [])
            terms = parsed_doc.get("terms") or parsed_doc.get("all_terms")
            title_terms = parsed_doc.get("title_terms")
            body_terms = parsed_doc.get("body_terms")
            positions_input = parsed_doc.get("positions")
        else:
            url = str(getattr(parsed_doc, "url", "")).strip()
            title = str(getattr(parsed_doc, "title", "")).strip()
            description = str(getattr(parsed_doc, "description", "")).strip()
            body = str(getattr(parsed_doc, "body", "")).strip()
            content_hash = str(getattr(parsed_doc, "content_hash", "")).strip()
            metadata = getattr(parsed_doc, "metadata", {})
            tokens = getattr(parsed_doc, "tokens", [])
            terms = getattr(parsed_doc, "terms", None)
            title_terms = getattr(parsed_doc, "title_terms", None)
            body_terms = getattr(parsed_doc, "body_terms", None)
            positions_input = getattr(parsed_doc, "positions", None)

        if not url:
            raise ValueError("Document must contain a non-empty 'url'")
        if not content_hash:
            raise ValueError("Document must contain a non-empty 'content_hash'")

        if not isinstance(metadata, dict):
            metadata = {}

        language = (
            getattr(parsed_doc, "language", None) or metadata.get("language") or "en"
        )
        author = getattr(parsed_doc, "author", None) or metadata.get("author")
        publish_date = (
            getattr(parsed_doc, "published_at", None)
            or getattr(parsed_doc, "publish_date", None)
            or metadata.get("publish_date")
            or metadata.get("published_at")
        )

        # Derive tokens and term positions
        if not tokens and body:
            # Basic whitespace fallback if preprocessed tokens absent
            tokens = [t.lower() for t in body.split()]

        # Token count is the true BM25 document length
        doc_length = len(tokens)

        # Title and body terms
        if title_terms is None:
            title_terms = [t for t in tokens if t in title.lower()]
        if body_terms is None:
            body_terms = tokens

        # Term set
        if terms is None:
            terms = sorted(set(tokens) | set(title_terms))

        # Calculate or adopt positions
        term_positions: Dict[str, List[int]] = {}
        if isinstance(positions_input, dict):
            term_positions = positions_input
        else:
            for idx, token in enumerate(tokens):
                term_positions.setdefault(token, []).append(idx)

        return {
            "url": url,
            "title": title,
            "description": description,
            "body": body,
            "content_hash": content_hash,
            "language": language,
            "author": author,
            "publish_date": publish_date,
            "document_length": doc_length,
            "tokens": tokens,
            "terms": terms,
            "title_terms": title_terms,
            "body_terms": body_terms,
            "positions": term_positions,
        }

    def add_document(self, parsed_doc: Any) -> Optional[int]:
        """Index a single parsed document atomically.

        Returns doc_id on success, existing doc_id if duplicate, or None on error.
        """
        if self.connection is None:
            self._connect()
        assert self.connection is not None

        try:
            norm = self._normalize_document(parsed_doc)
        except Exception as e:
            logger.error(f"Document validation failed: {e}")
            return None

        # 1. URL Duplication: return existing document without re-indexing
        existing_url = self.connection.execute(
            "SELECT doc_id FROM documents WHERE url = ?", (norm["url"],)
        ).fetchone()
        if existing_url:
            logger.debug(
                f"Document URL already indexed: {norm['url']} "
                f"(doc_id={existing_url[0]})"
            )
            return int(existing_url[0])

        # 2. Content Hash Duplication: return canonical doc_id without re-indexing
        existing_hash = self.connection.execute(
            "SELECT doc_id FROM documents WHERE content_hash = ?",
            (norm["content_hash"],),
        ).fetchone()
        if existing_hash:
            logger.debug(
                f"Content hash already indexed: {norm['content_hash'][:12]} "
                f"(canonical doc_id={existing_hash[0]})"
            )
            return int(existing_hash[0])

        # 3. Atomic insertion
        try:
            with self.connection:
                doc_id = self._index_document_internal(norm)
                self._bump_generation_internal()
            logger.info(f"Document indexed: {norm['url']} (doc_id={doc_id})")
            return doc_id
        except Exception as e:
            logger.error(f"Failed to index document atomically: {e}")
            return None

    def _index_document_internal(self, norm: Dict[str, Any]) -> int:
        """Internal helper to insert document, terms, and postings in transaction."""
        assert self.connection is not None
        cursor = self.connection.execute(
            """INSERT INTO documents
               (url, title, description, body, content_hash, language,
                author, publish_date, document_length)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                norm["url"],
                norm["title"],
                norm["description"],
                norm["body"],
                norm["content_hash"],
                norm["language"],
                norm["author"],
                norm["publish_date"],
                norm["document_length"],
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("Failed to obtain lastrowid for inserted document")
        doc_id = int(cursor.lastrowid)

        # Calculate term frequencies
        title_counts: Dict[str, int] = {}
        for t in norm["title_terms"]:
            title_counts[t] = title_counts.get(t, 0) + 1

        body_counts: Dict[str, int] = {}
        for t in norm["body_terms"]:
            body_counts[t] = body_counts.get(t, 0) + 1

        raw_counts: Dict[str, int] = {}
        for t in norm["tokens"]:
            raw_counts[t] = raw_counts.get(t, 0) + 1

        all_unique_terms = set(norm["terms"]) | set(title_counts) | set(body_counts)

        # Index terms and postings
        for term in all_unique_terms:
            raw_tf = raw_counts.get(term, 0)
            title_tf = title_counts.get(term, 0)
            body_tf = body_counts.get(term, 0)
            if raw_tf == 0:
                raw_tf = max(title_tf + body_tf, 1)

            positions_list = norm["positions"].get(term, [])
            positions_json = json.dumps(positions_list) if positions_list else None

            # Get or create term
            term_row = self.connection.execute(
                "SELECT term_id FROM terms WHERE term = ?", (term,)
            ).fetchone()

            if term_row:
                term_id = term_row[0]
                self.connection.execute(
                    """UPDATE terms
                       SET collection_frequency = collection_frequency + ?,
                           document_frequency = document_frequency + 1
                       WHERE term_id = ?""",
                    (raw_tf, term_id),
                )
            else:
                term_cur = self.connection.execute(
                    """INSERT INTO terms
                       (term, document_frequency, collection_frequency)
                       VALUES (?, 1, ?)""",
                    (term, raw_tf),
                )
                if term_cur.lastrowid is None:
                    raise RuntimeError("Failed to obtain lastrowid for inserted term")
                term_id = int(term_cur.lastrowid)

            # Insert posting
            self.connection.execute(
                """INSERT INTO postings
                   (term_id, doc_id, term_frequency, title_frequency,
                    body_frequency, positions)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (term_id, doc_id, raw_tf, title_tf, body_tf, positions_json),
            )

        # Update metadata transactionally
        self._update_metadata_internal(added_length=norm["document_length"])
        return doc_id

    def _update_metadata_internal(self, added_length: int = 0) -> None:
        """Update metadata counters within an active transaction."""
        assert self.connection is not None
        cur = self.connection.cursor()

        # Read current document count and total length
        cur.execute("SELECT COUNT(*), COALESCE(SUM(document_length), 0) FROM documents")
        row = cur.fetchone()
        doc_count = int(row[0]) if row else 0
        total_length = int(row[1]) if row else 0
        avg_length = (total_length / doc_count) if doc_count > 0 else 0.0

        cur.execute("SELECT COUNT(*) FROM terms")
        term_count = int(cur.fetchone()[0])

        now_iso = datetime.utcnow().isoformat()
        cur.execute(
            "UPDATE metadata SET value = ?, updated_at = ? "
            "WHERE key = 'total_documents'",
            (str(doc_count), now_iso),
        )
        cur.execute(
            "UPDATE metadata SET value = ?, updated_at = ? "
            "WHERE key = 'total_document_length'",
            (str(total_length), now_iso),
        )
        cur.execute(
            "UPDATE metadata SET value = ?, updated_at = ? "
            "WHERE key = 'avg_document_length'",
            (str(round(avg_length, 4)), now_iso),
        )
        cur.execute(
            "UPDATE metadata SET value = ?, updated_at = ? WHERE key = 'total_terms'",
            (str(term_count), now_iso),
        )
        cur.execute(
            "UPDATE metadata SET value = ?, updated_at = ? WHERE key = 'last_indexed'",
            (now_iso, now_iso),
        )

    def get_document(self, doc_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve document by doc_id."""
        if self.connection is None:
            self._connect()
        assert self.connection is not None

        row = self.connection.execute(
            "SELECT * FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_document_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Retrieve document by canonical URL."""
        if self.connection is None:
            self._connect()
        assert self.connection is not None

        row = self.connection.execute(
            "SELECT * FROM documents WHERE url = ?", (url,)
        ).fetchone()
        return dict(row) if row else None

    def get_documents_by_ids(
        self, doc_ids: List[int], batch_size: int = 500
    ) -> Dict[int, Dict[str, Any]]:
        """Retrieve multiple documents by ID in parameterized batches.

        Eliminates N+1 single-row lookup bottlenecks in BM25 ranking and search
        filtering while respecting SQLite parameter limits.

        Args:
            doc_ids: List of integer document IDs to retrieve.
            batch_size: Maximum parameter count per SQL query (default 500).

        Returns:
            Dictionary mapping doc_id to document dictionary.
        """
        if not doc_ids:
            return {}

        if self.connection is None:
            self._connect()
        assert self.connection is not None

        unique_ids = list(dict.fromkeys(doc_ids))
        results: Dict[int, Dict[str, Any]] = {}

        for i in range(0, len(unique_ids), batch_size):
            chunk = unique_ids[i : i + batch_size]
            placeholders = ",".join("?" for _ in chunk)
            query = f"SELECT * FROM documents WHERE doc_id IN ({placeholders})"
            cursor = self.connection.execute(query, chunk)
            for row in cursor.fetchall():
                doc_dict = dict(row)
                results[int(doc_dict["doc_id"])] = doc_dict

        return results

    def calculate_idf(self, recalculate: bool = False) -> None:
        """Calculate and update BM25 IDF for terms.

        Uses Robertson-Spärck Jones BM25 formula:
        idf = log(1.0 + (N - df + 0.5) / (df + 0.5))
        which remains strictly positive for all document frequencies.
        """
        if self.connection is None:
            self._connect()
        assert self.connection is not None

        total_docs_row = self.connection.execute(
            "SELECT COUNT(*) FROM documents"
        ).fetchone()
        total_docs = int(total_docs_row[0]) if total_docs_row else 0

        if total_docs == 0:
            logger.warning("No documents indexed, skipping IDF calculation")
            return

        query = (
            "SELECT term_id, document_frequency FROM terms"
            if recalculate
            else "SELECT term_id, document_frequency FROM terms WHERE idf = 0.0"
        )
        cursor = self.connection.execute(query)
        updates = []

        for term_id, doc_freq in cursor.fetchall():
            # Standard BM25 Robertson-Spärck Jones IDF
            numerator = total_docs - doc_freq + 0.5
            denominator = doc_freq + 0.5
            idf = math.log(1.0 + max(0.0, numerator / denominator))
            updates.append((idf, term_id))

        if updates:
            with self.connection:
                self.connection.executemany(
                    "UPDATE terms SET idf = ? WHERE term_id = ?", updates
                )
            logger.info(f"Updated BM25 IDF for {len(updates)} terms (N={total_docs})")

    def get_all_terms(self) -> Dict[str, Dict[str, Any]]:
        """Get all indexed terms with statistics."""
        if self.connection is None:
            self._connect()
        assert self.connection is not None

        cursor = self.connection.execute(
            "SELECT term, idf, document_frequency, collection_frequency FROM terms"
        )
        terms: Dict[str, Dict[str, Any]] = {}
        for term, idf, doc_freq, coll_freq in cursor.fetchall():
            terms[term] = {
                "idf": idf,
                "doc_frequency": doc_freq,
                "collection_frequency": coll_freq,
            }
        return terms

    def get_stats(self) -> Dict[str, Any]:
        """Get indexing statistics from metadata table."""
        if self.connection is None:
            self._connect()
        assert self.connection is not None

        cur = self.connection.execute("SELECT key, value FROM metadata")
        meta = {row[0]: row[1] for row in cur.fetchall()}

        doc_count = int(meta.get("total_documents", 0))
        term_count = int(meta.get("total_terms", 0))
        total_doc_len = int(meta.get("total_document_length", 0))
        avg_doc_len = float(meta.get("avg_document_length", 0.0))

        postings_row = self.connection.execute(
            "SELECT COUNT(*) FROM postings"
        ).fetchone()
        posting_count = int(postings_row[0]) if postings_row else 0

        return {
            "total_documents": doc_count,
            "total_terms": term_count,
            "total_postings": posting_count,
            "total_document_length": total_doc_len,
            "avg_document_length": avg_doc_len,
            "avg_postings_per_term": posting_count / max(term_count, 1),
            "schema_version": meta.get("schema_version", SCHEMA_VERSION),
        }

    def search_postings(self, term: str) -> List[Tuple[int, int]]:
        """Get posting list for a term as (doc_id, term_frequency) tuples."""
        if self.connection is None:
            self._connect()
        assert self.connection is not None

        cursor = self.connection.execute(
            """SELECT doc_id, term_frequency FROM postings
               WHERE term_id = (SELECT term_id FROM terms WHERE term = ?)""",
            (term,),
        )
        return [(int(row[0]), int(row[1])) for row in cursor.fetchall()]

    def search_detailed_postings(self, term: str) -> List[Dict[str, Any]]:
        """Get detailed postings including field frequencies and positions."""
        if self.connection is None:
            self._connect()
        assert self.connection is not None

        cursor = self.connection.execute(
            """SELECT doc_id, term_frequency, title_frequency, body_frequency, positions
               FROM postings
               WHERE term_id = (SELECT term_id FROM terms WHERE term = ?)""",
            (term,),
        )
        results = []
        for row in cursor.fetchall():
            pos_str = row[4]
            positions = json.loads(pos_str) if pos_str else []
            results.append(
                {
                    "doc_id": int(row[0]),
                    "term_frequency": int(row[1]),
                    "title_frequency": int(row[2]),
                    "body_frequency": int(row[3]),
                    "positions": positions,
                }
            )
        return results

    def delete_document(self, doc_id: int) -> bool:
        """Delete a document and consistently update statistics and metadata."""
        if self.connection is None:
            self._connect()
        assert self.connection is not None

        try:
            with self.connection:
                # 1. Fetch document length
                doc_row = self.connection.execute(
                    "SELECT document_length FROM documents WHERE doc_id = ?",
                    (doc_id,),
                ).fetchone()
                if not doc_row:
                    logger.warning(f"Document doc_id={doc_id} not found for deletion")
                    return False

                # 2. Fetch all postings for this document
                postings = self.connection.execute(
                    "SELECT term_id, term_frequency FROM postings WHERE doc_id = ?",
                    (doc_id,),
                ).fetchall()

                # 3. Decrement document and collection frequencies
                for term_id, tf in postings:
                    self.connection.execute(
                        """UPDATE terms
                           SET document_frequency = document_frequency - 1,
                               collection_frequency = collection_frequency - ?
                           WHERE term_id = ?""",
                        (tf, term_id),
                    )

                # 4. Remove orphaned terms whose document frequency dropped to 0
                self.connection.execute(
                    "DELETE FROM terms WHERE document_frequency <= 0"
                )

                # 5. Delete postings and document
                self.connection.execute(
                    "DELETE FROM postings WHERE doc_id = ?", (doc_id,)
                )
                self.connection.execute(
                    "DELETE FROM documents WHERE doc_id = ?", (doc_id,)
                )

                # 6. Update metadata
                self._update_metadata_internal()
                self._bump_generation_internal()

            logger.info(f"Document doc_id={doc_id} deleted successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to delete document doc_id={doc_id}: {e}")
            return False

    def clear_index(self) -> bool:
        """Clear the entire inverted index and reset metadata counters."""
        if self.connection is None:
            self._connect()
        assert self.connection is not None

        try:
            with self.connection:
                self.connection.execute("DELETE FROM postings")
                self.connection.execute("DELETE FROM terms")
                self.connection.execute("DELETE FROM documents")
                self._update_metadata_internal()
                self._bump_generation_internal()

            logger.warning("Inverted index cleared")
            return True
        except Exception as e:
            logger.error(f"Failed to clear index: {e}")
            return False
