"""Telemetry metrics collector for index statistics and system resource utilization."""

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Optional
import psutil

from src.api.admin_models import IndexMetrics, SystemMetrics
from src.indexer import SQLiteIndexer

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects strictly measured index metrics and psutil system utilization."""

    def __init__(self, indexer: Optional[SQLiteIndexer] = None) -> None:
        self.indexer = indexer

    def set_indexer(self, indexer: SQLiteIndexer) -> None:
        """Update indexer reference."""
        self.indexer = indexer

    def get_index_metrics(self) -> IndexMetrics:
        """Retrieve real index stats and database file size."""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        if not self.indexer:
            return IndexMetrics(
                total_documents=0,
                total_terms=0,
                total_postings=0,
                avg_postings_per_term=0.0,
                index_size_mb=0.0,
                last_updated=now_iso,
                health_status="uninitialized",
            )

        try:
            stats = self.indexer.get_stats()
            db_file = Path(self.indexer.db_path)
            size_mb = (
                round(db_file.stat().st_size / (1024 * 1024), 2)
                if db_file.exists()
                else 0.0
            )

            # Query last indexed document timestamp if available
            last_updated = now_iso
            try:
                if self.indexer.connection:
                    row = self.indexer.connection.execute(
                        "SELECT MAX(indexed_at) FROM documents"
                    ).fetchone()
                    if row and row[0]:
                        last_updated = str(row[0])
            except Exception:
                pass

            total_docs = stats.get("total_documents", 0)
            health = "healthy" if total_docs > 0 else "empty"

            return IndexMetrics(
                total_documents=total_docs,
                total_terms=stats.get("total_terms", 0),
                total_postings=stats.get("total_postings", 0),
                avg_postings_per_term=round(
                    float(stats.get("avg_postings_per_term", 0.0)), 2
                ),
                index_size_mb=size_mb,
                last_updated=last_updated,
                health_status=health,
            )
        except Exception as e:
            logger.error(f"Failed to query index metrics: {e}")
            return IndexMetrics(
                total_documents=0,
                total_terms=0,
                total_postings=0,
                avg_postings_per_term=0.0,
                index_size_mb=0.0,
                last_updated=now_iso,
                health_status="error",
            )

    def get_system_metrics(self) -> SystemMetrics:
        """Sample host performance measurements strictly via non-blocking psutil."""
        try:
            # cpu_percent with interval=None is strictly non-blocking
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage(".")

            return SystemMetrics(
                cpu_percent=round(cpu, 1),
                memory_percent=round(mem.percent, 1),
                disk_percent=round(disk.percent, 1),
                memory_used_mb=round(mem.used / (1024 * 1024), 1),
                memory_total_mb=round(mem.total / (1024 * 1024), 1),
                disk_used_gb=round(disk.used / (1024 * 1024 * 1024), 2),
                disk_total_gb=round(disk.total / (1024 * 1024 * 1024), 2),
            )
        except Exception as e:
            logger.error(f"Failed to sample system metrics: {e}")
            return SystemMetrics(
                cpu_percent=0.0,
                memory_percent=0.0,
                disk_percent=0.0,
                memory_used_mb=0.0,
                memory_total_mb=0.0,
                disk_used_gb=0.0,
                disk_total_gb=0.0,
            )
