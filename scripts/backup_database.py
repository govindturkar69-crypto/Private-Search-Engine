"""Automated, live-consistent SQLite database backup and verification utility.

Uses Python's sqlite3 backup API to capture atomic database snapshots while the
search engine is running, computes SHA-256 integrity digests, verifies logical
database correctness via PRAGMA integrity_check, and provides non-destructive
restore testing into isolated temporary environments.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import sqlite3
import sys
import tempfile
from typing import Tuple

from src.config import load_config
from src.indexer import SQLiteIndexer
from src.ranker.search import SearchEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("backup")


def compute_file_sha256(file_path: Path) -> str:
    """Compute SHA-256 cryptographic digest of a file in 64KB chunks."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_database_integrity(db_path: Path) -> Tuple[bool, str]:
    """Execute PRAGMA integrity_check on SQLite database."""
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        row = cursor.fetchone()
        conn.close()
        if row and row[0] == "ok":
            return True, "ok"
        return False, str(row[0]) if row else "Empty integrity check result"
    except Exception as exc:
        return False, str(exc)


def create_backup(
    source_db_path: Path,
    backup_dir: Path,
) -> Path:
    """Perform live, transactionally consistent SQLite backup using backup API."""
    if not source_db_path.is_file():
        raise FileNotFoundError(f"Source database file not found: {source_db_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target_backup_path = backup_dir / f"index_backup_{timestamp}.db"

    logger.info(
        f"Starting live SQLite backup from {source_db_path} to " f"{target_backup_path}"
    )

    # Use SQLite Online Backup API
    source_conn = sqlite3.connect(str(source_db_path))
    target_conn = sqlite3.connect(str(target_backup_path))

    try:
        with target_conn:
            source_conn.backup(target_conn, pages=100)
    finally:
        target_conn.close()
        source_conn.close()

    # 1. Compute and persist SHA-256 checksum
    digest = compute_file_sha256(target_backup_path)
    checksum_file = target_backup_path.with_suffix(".db.sha256")
    checksum_file.write_text(f"{digest}  {target_backup_path.name}\n")
    logger.info(f"Backup created successfully. SHA-256: {digest}")

    # 2. Logical integrity check
    is_valid, msg = verify_database_integrity(target_backup_path)
    if not is_valid:
        logger.error(f"Backup failed logical integrity check: {msg}")
        raise RuntimeError(f"Corrupted backup created: {msg}")
    logger.info("Logical integrity check: PASS (PRAGMA integrity_check = ok)")

    return target_backup_path


def verify_restore(backup_path: Path) -> bool:
    """Non-destructive restore verification into isolated temporary workspace."""
    logger.info(f"Initiating restore verification for: {backup_path}")
    if not backup_path.is_file():
        logger.error(f"Backup file does not exist: {backup_path}")
        return False

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_db = Path(tmp_dir) / "restored_test.db"

        # Copy backup to isolated temp path to keep original immutable
        source_conn = sqlite3.connect(str(backup_path))
        dest_conn = sqlite3.connect(str(tmp_db))
        try:
            with dest_conn:
                source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
            source_conn.close()

        # Step 1: Logical integrity check on restored file
        is_valid, msg = verify_database_integrity(tmp_db)
        if not is_valid:
            logger.error(f"Restored database integrity check failed: {msg}")
            return False

        # Step 2: Open with SQLiteIndexer and inspect metadata
        try:
            indexer = SQLiteIndexer(str(tmp_db))
            stats = indexer.get_stats()
            doc_count = stats.get("total_documents", 0)
            term_count = stats.get("unique_terms", 0)
            gen = indexer.get_generation()
            logger.info(
                f"Restored index verified: docs={doc_count}, terms={term_count}, "
                f"gen={gen}"
            )

            # Step 3: Run safe test search smoke query
            engine = SearchEngine(indexer)
            results, total, err = engine.search_with_total("python", limit=5)
            logger.info(
                f"Smoke search executed on restored index: total_available={total}, "
                f"error={err}"
            )
            indexer.close()
        except Exception as exc:
            logger.error(f"Failed to query restored database: {exc}", exc_info=True)
            return False

    logger.info("Restore verification SUCCESSFUL (non-destructive)")
    return True


def purge_expired_backups(
    backup_dir: Path, retention_days: int, dry_run: bool = False
) -> int:
    """Purge backups older than retention_days matching strict pattern."""
    if retention_days <= 0:
        return 0

    now = datetime.now(timezone.utc).timestamp()
    cutoff_sec = now - (retention_days * 86400)
    purged_count = 0

    for item in backup_dir.glob("index_backup_*.db"):
        if item.is_file() and item.stat().st_mtime < cutoff_sec:
            purged_count += 1
            checksum_item = item.with_suffix(".db.sha256")
            if dry_run:
                logger.info(f"[DRY-RUN] Would delete expired backup: {item.name}")
            else:
                item.unlink(missing_ok=True)
                checksum_item.unlink(missing_ok=True)
                logger.info(f"Purged expired backup: {item.name}")

    return purged_count


def main() -> None:
    """CLI entrypoint for database backup, restore testing, and retention."""
    cfg = load_config()
    default_db = Path(cfg.index.database_path)
    default_backup_dir = default_db.parent / "backups"

    parser = argparse.ArgumentParser(
        description="SQLite Database Backup & Disaster Recovery Utility"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=default_db,
        help=f"Path to SQLite database (default: {default_db})",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=default_backup_dir,
        help=f"Target backup directory (default: {default_backup_dir})",
    )
    parser.add_argument(
        "--verify-restore",
        action="store_true",
        help="Perform non-destructive restore verification in temp environment",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=30,
        help="Days of backups to retain (default: 30, 0 to disable purge)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Display purge actions without deleting files",
    )

    args = parser.parse_args()

    try:
        backup_file = create_backup(args.db_path, args.backup_dir)
        if args.verify_restore:
            success = verify_restore(backup_file)
            if not success:
                logger.error("Restore verification failed.")
                sys.exit(1)

        if args.retention_days > 0:
            purge_expired_backups(
                args.backup_dir, args.retention_days, dry_run=args.dry_run
            )

        logger.info("Backup operation completed successfully.")
    except Exception as exc:
        logger.error(f"Backup operation failed: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
