"""Tests for automated, live-consistent SQLite database backup and recovery.

Validates:
- Atomic snapshot creation via Python sqlite3 backup API.
- SHA-256 integrity digest generation and verification.
- PRAGMA integrity_check validation on live and restored databases.
- Non-destructive restore testing into isolated temporary environments.
- Safe backup retention and expiration purging.
- Concurrency safety during active write transactions.
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import threading
import time

import pytest

from scripts.backup_database import (
    compute_file_sha256,
    create_backup,
    purge_expired_backups,
    verify_database_integrity,
    verify_restore,
)
from src.indexer import SQLiteIndexer


@pytest.fixture
def populated_db_path(tmp_path: Path) -> Path:
    """Fixture providing an initialized, populated SQLite database."""
    db_path = tmp_path / "source.db"
    indexer = SQLiteIndexer(str(db_path))

    docs = [
        {
            "url": "http://example.com/python",
            "title": "Python Search Engine",
            "description": "Python search engine with sqlite",
            "body": "Building a fast python private search engine with sqlite",
            "content_hash": "hash_python_backup_1",
        },
        {
            "url": "http://example.com/fastapi",
            "title": "FastAPI Integration",
            "description": "FastAPI web framework",
            "body": "FastAPI web framework with async support and rest api",
            "content_hash": "hash_fastapi_backup_2",
        },
    ]
    for doc in docs:
        indexer.add_document(doc)

    indexer.calculate_idf(recalculate=True)
    indexer.close()
    return db_path


class TestSQLiteBackupSubsystem:
    """Test suite for SQLite backup, restore verification, and retention."""

    def test_create_backup_success_and_checksum(
        self, populated_db_path: Path, tmp_path: Path
    ) -> None:
        """Verify successful backup creation, sha256 checksum file, and integrity."""
        backup_dir = tmp_path / "backups"
        backup_file = create_backup(populated_db_path, backup_dir)

        assert backup_file.is_file()
        assert backup_file.stat().st_size > 0

        # Verify sha256 checksum file
        checksum_file = backup_file.with_suffix(".db.sha256")
        assert checksum_file.is_file()

        content = checksum_file.read_text().strip()
        expected_digest = compute_file_sha256(backup_file)
        assert content.startswith(expected_digest)
        assert backup_file.name in content

        # Verify integrity
        is_valid, msg = verify_database_integrity(backup_file)
        assert is_valid is True
        assert msg == "ok"

    def test_backup_nonexistent_source_raises(self, tmp_path: Path) -> None:
        """Verify FileNotFoundError is raised when source database does not exist."""
        nonexistent_db = tmp_path / "does_not_exist.db"
        backup_dir = tmp_path / "backups"

        with pytest.raises(FileNotFoundError):
            create_backup(nonexistent_db, backup_dir)

    def test_verify_database_integrity_corrupted_file(
        self, tmp_path: Path
    ) -> None:
        """Verify PRAGMA integrity check detects corrupted or non-database files."""
        corrupted_db = tmp_path / "corrupted.db"
        corrupted_db.write_bytes(b"NOT A VALID SQLITE DATABASE HEADER DATA")

        is_valid, msg = verify_database_integrity(corrupted_db)
        assert is_valid is False
        err_msg = msg.lower()
        assert "not a database" in err_msg or "file is not a database" in err_msg

    def test_verify_restore_success(
        self, populated_db_path: Path, tmp_path: Path
    ) -> None:
        """Verify non-destructive restore verification into temp environment."""
        backup_dir = tmp_path / "backups"
        backup_file = create_backup(populated_db_path, backup_dir)

        result = verify_restore(backup_file)
        assert result is True

    def test_verify_restore_nonexistent_file(self, tmp_path: Path) -> None:
        """Verify restore verification fails safely if file does not exist."""
        nonexistent = tmp_path / "ghost.db"
        assert verify_restore(nonexistent) is False

    def test_live_concurrent_writes_during_backup(
        self, populated_db_path: Path, tmp_path: Path
    ) -> None:
        """Verify backup integrity during concurrent writes in WAL mode."""
        backup_dir = tmp_path / "backups"
        stop_event = threading.Event()
        write_errors: list[Exception] = []

        def background_writer() -> None:
            try:
                conn = sqlite3.connect(str(populated_db_path))
                conn.execute("PRAGMA journal_mode=WAL;")
                cursor = conn.cursor()
                counter = 0
                while not stop_event.is_set():
                    cursor.execute(
                        "INSERT INTO documents "
                        "(url, title, body, content_hash) "
                        "VALUES (?, ?, ?, ?)",
                        (
                            f"http://example.com/concurrent_{counter}",
                            f"Concurrent Title {counter}",
                            f"Concurrent Body {counter}",
                            f"hash_concurrent_{counter}",
                        ),
                    )
                    conn.commit()
                    counter += 1
                    time.sleep(0.01)
                conn.close()
            except Exception as exc:
                write_errors.append(exc)

        writer_thread = threading.Thread(target=background_writer, daemon=True)
        writer_thread.start()

        # Let writer begin
        time.sleep(0.05)

        try:
            # Perform backup while writes are actively occurring
            backup_file = create_backup(populated_db_path, backup_dir)
        finally:
            stop_event.set()
            writer_thread.join(timeout=3.0)

        assert len(write_errors) == 0, f"Writer thread failed: {write_errors}"
        assert backup_file.is_file()

        # Check integrity of backup taken during active writes
        is_valid, msg = verify_database_integrity(backup_file)
        assert is_valid is True, f"Integrity check failed: {msg}"

        # Check restore verification
        assert verify_restore(backup_file) is True

    def test_purge_expired_backups(self, tmp_path: Path) -> None:
        """Verify retention purge removes aged backups and respects dry_run."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        old_db = backup_dir / "index_backup_20200101_000000.db"
        old_sha = backup_dir / "index_backup_20200101_000000.db.sha256"
        old_db.write_text("old database content")
        old_sha.write_text("old sha256")

        recent_db = backup_dir / "index_backup_20990101_000000.db"
        recent_sha = backup_dir / "index_backup_20990101_000000.db.sha256"
        recent_db.write_text("recent database content")
        recent_sha.write_text("recent sha256")

        # Set mtime on old files to 60 days ago
        past_time = datetime.now(timezone.utc).timestamp() - (60 * 86400)
        os.utime(old_db, (past_time, past_time))
        os.utime(old_sha, (past_time, past_time))

        # Test dry-run
        purged = purge_expired_backups(backup_dir, retention_days=30, dry_run=True)
        assert purged == 1
        assert old_db.is_file()
        assert old_sha.is_file()

        # Test live purge
        purged = purge_expired_backups(backup_dir, retention_days=30, dry_run=False)
        assert purged == 1
        assert not old_db.exists()
        assert not old_sha.exists()
        assert recent_db.is_file()
        assert recent_sha.is_file()
