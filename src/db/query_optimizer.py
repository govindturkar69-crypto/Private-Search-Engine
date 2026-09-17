"""Query plan inspection and batch document retrieval helpers."""

import logging
from typing import Any, Dict, List
from src.indexer import SQLiteIndexer

logger = logging.getLogger(__name__)


class QueryOptimizer:
    """Helper for SQLite query plan inspection and batch document prefetching."""

    def __init__(self, indexer: SQLiteIndexer) -> None:
        self.indexer = indexer

    def explain_query(self, sql: str, params: tuple = ()) -> List[str]:
        """Execute EXPLAIN QUERY PLAN safely using parameterized bindings.

        Args:
            sql: SQL statement to explain.
            params: Parameter values bound to placeholders.

        Returns:
            List of plan detail strings returned by SQLite optimizer.
        """
        if self.indexer.connection is None:
            self.indexer._connect()
        assert self.indexer.connection is not None

        explain_sql = f"EXPLAIN QUERY PLAN {sql}"
        cursor = self.indexer.connection.execute(explain_sql, params)
        plan_lines: List[str] = []
        for row in cursor.fetchall():
            # SQLite EXPLAIN QUERY PLAN returns (id, parent, notused, detail)
            detail = row[3] if len(row) > 3 else str(row)
            plan_lines.append(str(detail))
        return plan_lines

    def get_term_postings(self, term_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve postings with term and field frequencies for a term ID.

        Accurately reports raw term_frequency without conflating it with BM25 rank.
        """
        if self.indexer.connection is None:
            self.indexer._connect()
        assert self.indexer.connection is not None

        cursor = self.indexer.connection.execute(
            """
            SELECT doc_id, term_frequency, title_frequency, body_frequency
            FROM postings
            WHERE term_id = ?
            LIMIT ?
            """,
            (term_id, limit),
        )
        return [
            {
                "doc_id": int(row[0]),
                "term_frequency": int(row[1]),
                "title_frequency": int(row[2]),
                "body_frequency": int(row[3]),
            }
            for row in cursor.fetchall()
        ]

    def prefetch_documents(
        self, doc_ids: List[int], batch_size: int = 500
    ) -> Dict[int, Dict[str, Any]]:
        """Delegate batch retrieval directly to the indexer's batched prefetch.

        Eliminates N+1 single-row document queries during ranking and filtering.
        """
        return self.indexer.get_documents_by_ids(doc_ids, batch_size=batch_size)
