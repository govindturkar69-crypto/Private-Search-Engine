"""Seed a controlled temporary SQLite database for Playwright E2E browser tests."""

import os
from pathlib import Path
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.indexer import SQLiteIndexer  # noqa: E402
from src.indexer.batch import BatchIndexer  # noqa: E402
from src.parser.integration import ParserPipeline  # noqa: E402


def seed_database(db_path: str = "data/e2e_test.db") -> None:
    """Seed database with controlled documents for E2E search and admin testing."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)

    indexer = SQLiteIndexer(db_path)
    batcher = BatchIndexer(indexer, batch_size=20)
    parser = ParserPipeline()

    docs = [
        {
            "url": "https://example.com/python-guide",
            "title": "Python Programming Language Guide",
            "description": "Learn modern Python web and data architecture.",
            "body": (
                "Python is an interpreted programming language designed for "
                "readability and rapid development."
            ),
        },
        {
            "url": "https://example.com/fastapi-tutorial",
            "title": "FastAPI Web Framework Overview",
            "description": "Building high performance APIs with Python.",
            "body": (
                "FastAPI enables building robust asynchronous search APIs "
                "with standard type hints."
            ),
        },
        {
            "url": "https://example.com/search-algorithms",
            "title": "Search Engine Retrieval Algorithms",
            "description": "Exploring BM25 ranking and inverted index structures.",
            "body": (
                "Okapi BM25 scoring balances term frequency and document length "
                "normalization for relevant results."
            ),
        },
        {
            "url": "https://example.com/web-security",
            "title": "Web Application Security Practices",
            "description": "SSRF, XSS, and SQL injection defense mechanisms.",
            "body": (
                "Security hardening requires defense-in-depth headers, "
                "constant-time token comparison, and rate limiting."
            ),
        },
    ]

    # Add 12 additional numbered documents for pagination testing
    for i in range(1, 13):
        docs.append(
            {
                "url": f"https://example.com/doc/{i}",
                "title": f"Document {i} Search Engineering Fundamentals",
                "description": f"Pageable document {i} discussing systems.",
                "body": (
                    f"Detailed content of document {i} exploring search engines, "
                    "database queries, and indexing."
                ),
            }
        )

    for d in docs:
        raw_html = (
            f"<html><head><title>{d['title']}</title>"
            f"<meta name='description' content='{d['description']}'></head>"
            f"<body><article><h1>{d['title']}</h1><p>{d['body']}</p>"
            "</article></body></html>"
        )
        parsed = parser.process_document(html=raw_html, url=d["url"])
        if parsed:
            batcher.add_to_batch(parsed)

    batcher.flush()
    indexer.calculate_idf(recalculate=True)
    indexer.close()
    print(f"Successfully seeded {len(docs)} documents into {db_path}")


if __name__ == "__main__":
    seed_database()
