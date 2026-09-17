"""Database maintenance and PRAGMA inspection helpers.

All operations in this module are administrative tools designed for dedicated
offline or operator maintenance scripts. They are strictly non-request-path.
"""

import logging
from pathlib import Path
from typing import Any, Dict
from src.indexer import SQLiteIndexer

logger = logging.getLogger(__name__)


class DatabaseOptimizer:
    """Provides PRAGMA inspection and controlled database maintenance operations."""

    def __init__(self, indexer: SQLiteIndexer) -> None:
        self.indexer = indexer

    def get_database_stats(self) -> Dict[str, Any]:
        """Inspect low-level SQLite database page allocation and file metrics."""
        if self.indexer.connection is None:
            self.indexer._connect()
        assert self.indexer.connection is not None

        cur = self.indexer.connection.cursor()
        cur.execute("PRAGMA page_count;")
        page_count = int(cur.fetchone()[0])

        cur.execute("PRAGMA page_size;")
        page_size = int(cur.fetchone()[0])

        cur.execute("PRAGMA freelist_count;")
        freelist_count = int(cur.fetchone()[0])

        file_path = Path(self.indexer.db_path)
        disk_size_bytes = file_path.stat().st_size if file_path.exists() else 0

        return {
            "page_count": page_count,
            "page_size_bytes": page_size,
            "freelist_pages": freelist_count,
            "allocated_size_bytes": page_count * page_size,
            "disk_size_bytes": disk_size_bytes,
            "disk_size_mb": round(disk_size_bytes / (1024 * 1024), 2),
            "free_space_bytes": freelist_count * page_size,
        }

    def inspect_pragmas(self) -> Dict[str, Any]:
        """Report current runtime SQLite PRAGMA configuration settings."""
        if self.indexer.connection is None:
            self.indexer._connect()
        assert self.indexer.connection is not None

        pragma_queries = {
            "journal_mode": "PRAGMA journal_mode;",
            "cache_size": "PRAGMA cache_size;",
            "temp_store": "PRAGMA temp_store;",
            "synchronous": "PRAGMA synchronous;",
            "busy_timeout": "PRAGMA busy_timeout;",
            "foreign_keys": "PRAGMA foreign_keys;",
            "auto_vacuum": "PRAGMA auto_vacuum;",
        }
        results: Dict[str, Any] = {}
        for p, query in pragma_queries.items():
            cur = self.indexer.connection.execute(query)
            row = cur.fetchone()
            results[p] = row[0] if row else None
        return results

    def run_maintenance(self, operation: str) -> Dict[str, Any]:
        """Execute a controlled database maintenance operation.

        Allowed operations: 'optimize', 'analyze', 'vacuum', 'reindex'.
        CRITICAL: Never invoke during active search request serving.
        """
        valid_ops = {
            "optimize": "PRAGMA optimize;",
            "analyze": "ANALYZE;",
            "vacuum": "VACUUM;",
            "reindex": "REINDEX;",
        }

        op_lower = operation.strip().lower()
        if op_lower not in valid_ops:
            raise ValueError(
                f"Unsupported maintenance operation: '{operation}'. "
                f"Valid operations are: {list(valid_ops.keys())}"
            )

        if self.indexer.connection is None:
            self.indexer._connect()
        assert self.indexer.connection is not None

        sql = valid_ops[op_lower]
        logger.info(f"Starting database maintenance: {op_lower} ({sql})")

        try:
            # PRAGMA optimize, ANALYZE, VACUUM, REINDEX
            # SQLite requires autocommit mode for VACUUM
            self.indexer.connection.isolation_level = None
            self.indexer.connection.execute(sql)
            self.indexer.connection.isolation_level = ""  # restore default
            logger.info(f"Database maintenance completed successfully: {op_lower}")
            return {
                "operation": op_lower,
                "status": "success",
                "sql": sql,
            }
        except Exception as e:
            logger.error(f"Database maintenance failed for {op_lower}: {e}")
            return {
                "operation": op_lower,
                "status": "failed",
                "error": str(e),
                "sql": sql,
            }
