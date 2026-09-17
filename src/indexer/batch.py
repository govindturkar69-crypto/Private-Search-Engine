"""Batch document indexing with atomic transactional flushes."""

import logging
from typing import Any, Dict, List
from src.indexer import SQLiteIndexer

logger = logging.getLogger(__name__)


class BatchIndexer:
    """Batch accumulator providing atomic all-or-nothing transaction flushes."""

    def __init__(self, indexer: SQLiteIndexer, batch_size: int = 100) -> None:
        self.indexer = indexer
        self.batch_size = batch_size
        self.batch: List[Any] = []
        self.indexed_count = 0
        self.failed_count = 0

    def add_to_batch(self, parsed_doc: Any) -> None:
        """Add document to batch, auto-flushing if threshold is reached."""
        self.batch.append(parsed_doc)
        if len(self.batch) >= self.batch_size:
            self.flush()

    def flush(self, recalculate_idf: bool = True) -> bool:
        """Flush accumulated batch to SQLite within a single atomic transaction.

        If any error occurs during database operations, the entire batch transaction
        is rolled back atomically.
        """
        if not self.batch:
            return True

        if self.indexer.connection is None:
            self.indexer._connect()
        assert self.indexer.connection is not None

        # Pre-validate and normalize documents prior to opening transaction
        normalized_docs = []
        validation_failures = 0
        for doc in self.batch:
            try:
                norm = self.indexer._normalize_document(doc)
                normalized_docs.append(norm)
            except Exception as e:
                logger.error(f"Batch item validation failed: {e}")
                validation_failures += 1

        if not normalized_docs and validation_failures > 0:
            self.failed_count += validation_failures
            self.batch = []
            return False

        try:
            # Single atomic transaction for entire batch
            newly_indexed = 0
            with self.indexer.connection:
                for norm in normalized_docs:
                    # Check URL duplicate
                    existing_url = self.indexer.connection.execute(
                        "SELECT doc_id FROM documents WHERE url = ?",
                        (norm["url"],),
                    ).fetchone()
                    if existing_url:
                        continue

                    # Check Content Hash duplicate
                    existing_hash = self.indexer.connection.execute(
                        "SELECT doc_id FROM documents WHERE content_hash = ?",
                        (norm["content_hash"],),
                    ).fetchone()
                    if existing_hash:
                        continue

                    self.indexer._index_document_internal(norm)
                    newly_indexed += 1

                if newly_indexed > 0:
                    self.indexer._bump_generation_internal()

            self.indexed_count += newly_indexed
            self.failed_count += validation_failures

            if recalculate_idf and newly_indexed > 0:
                self.indexer.calculate_idf(recalculate=True)

            logger.info(
                f"Batch flush succeeded: {len(self.batch)} processed "
                f"({newly_indexed} newly indexed, {validation_failures} failed)"
            )
            self.batch = []
            return True

        except Exception as e:
            logger.error(f"Batch transaction failed and was rolled back: {e}")
            self.failed_count += len(self.batch)
            self.batch = []
            return False

    def get_stats(self) -> Dict[str, int]:
        """Return batch processing statistics."""
        return {
            "batch_size": len(self.batch),
            "total_indexed": self.indexed_count,
            "total_failed": self.failed_count,
        }
