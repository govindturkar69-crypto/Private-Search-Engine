"""Controlled database maintenance utility for Private Search Engine.

Usage:
    python scripts/optimize_database.py --stats
    python scripts/optimize_database.py --optimize
    python scripts/optimize_database.py --analyze
    python scripts/optimize_database.py --vacuum --force
    python scripts/optimize_database.py --reindex --force
"""

import argparse
import logging
from pathlib import Path
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_config  # noqa: E402
from src.db.optimizer import DatabaseOptimizer  # noqa: E402
from src.indexer import SQLiteIndexer  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("db-optimizer")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for database optimization."""
    parser = argparse.ArgumentParser(
        description="Controlled SQLite database maintenance utility."
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path to SQLite database (defaults to path in config.yaml)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Display database storage statistics and PRAGMA settings",
    )
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Run PRAGMA optimize; to update query planner heuristics",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run ANALYZE; to rebuild index statistics tables",
    )
    parser.add_argument(
        "--vacuum",
        action="store_true",
        help="Run VACUUM; to defragment and reclaim free space (requires lock)",
    )
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Run REINDEX; to rebuild all inverted index b-trees",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass interactive confirmation for heavy operations (VACUUM/REINDEX)",
    )
    return parser.parse_args()


def confirm_heavy_operation(operation: str, force: bool) -> bool:
    """Display safety warning and prompt operator unless --force is specified."""
    if force:
        return True

    print("\n" + "=" * 70)
    print(f" CAUTION: Heavy Database Maintenance Operation [{operation.upper()}]")
    print("=" * 70)
    print(
        " WARNING: This operation acquires an exclusive database write lock.\n"
        " For VACUUM, available free disk space equal to the full database file size\n"
        " is strictly required. Ensure recent verified backups exist before proceeding."
    )
    print("=" * 70)

    try:
        response = (
            input(f"Proceed with {operation.upper()}? (yes/no): ").strip().lower()
        )
        return response in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def main() -> int:
    """Execute requested database maintenance operations."""
    args = parse_args()
    config = load_config()
    db_path = args.db_path or config.index.database_path

    if not Path(db_path).exists():
        logger.error(f"Target database file not found at: {db_path}")
        return 1

    logger.info(f"Opening database for maintenance: {db_path}")
    indexer = SQLiteIndexer(db_path)
    optimizer = DatabaseOptimizer(indexer)

    try:
        if args.stats or not any(
            [args.optimize, args.analyze, args.vacuum, args.reindex]
        ):
            stats = optimizer.get_database_stats()
            pragmas = optimizer.inspect_pragmas()
            print("\n--- SQLite Database Storage Statistics ---")
            for k, v in stats.items():
                print(f"  {k:22}: {v}")
            print("\n--- SQLite PRAGMA Configuration ---")
            for k, v in pragmas.items():
                print(f"  {k:22}: {v}")

        if args.optimize:
            logger.info("Executing PRAGMA optimize...")
            res = optimizer.run_maintenance("optimize")
            print(f"Optimize Result: {res['status']}")

        if args.analyze:
            logger.info("Executing ANALYZE...")
            res = optimizer.run_maintenance("analyze")
            print(f"Analyze Result: {res['status']}")

        if args.reindex:
            if confirm_heavy_operation("reindex", args.force):
                logger.info("Executing REINDEX...")
                res = optimizer.run_maintenance("reindex")
                print(f"Reindex Result: {res['status']}")
            else:
                logger.warning("REINDEX cancelled by operator.")

        if args.vacuum:
            if confirm_heavy_operation("vacuum", args.force):
                logger.info("Executing VACUUM...")
                res = optimizer.run_maintenance("vacuum")
                print(f"Vacuum Result: {res['status']}")
            else:
                logger.warning("VACUUM cancelled by operator.")

        return 0
    finally:
        indexer.close()


if __name__ == "__main__":
    sys.exit(main())
