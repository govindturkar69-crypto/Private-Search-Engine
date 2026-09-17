import logging
from pathlib import Path
from typing import Any, Dict, Generator
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.config import Config, load_config
from src.indexer import SQLiteIndexer
from src.logger import setup_logging
from src.main import app, create_app
from src.ranker.search import SearchEngine


@pytest.fixture(scope="session")
def config() -> Config:
    return load_config()


@pytest.fixture(scope="session")
def logger() -> logging.Logger:
    return setup_logging("DEBUG")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def test_db(tmp_path: Path) -> str:
    """Provide an isolated temporary database path."""
    db_file = tmp_path / "integration_test.db"
    return str(db_file)


@pytest.fixture
def seeded_indexer(test_db: str) -> Generator[SQLiteIndexer, None, None]:
    """Create isolated SQLiteIndexer with controlled, diverse sample documents."""
    indexer = SQLiteIndexer(test_db)

    sample_docs = [
        {
            "url": f"https://example.com/doc/{i}",
            "title": f"Document {i} Python Guide",
            "description": f"Overview of document {i} for web search systems.",
            "body": (
                f"Content for document {i} discussing python programming, "
                "search engines, databases, and api development."
            ),
            "content_hash": f"hash_sample_doc_{i}",
            "metadata": {
                "author": "Guido" if i % 2 == 0 else "Community",
                "language": "en",
                "index": i,
            },
            "tokens": [
                "document",
                "python",
                "guid",
                "program",
                "search",
                "engin",
                "databas",
                "develop",
            ],
            "title_terms": ["document", "python", "guid"],
            "body_terms": ["content", "discuss", "search", "engin", "databas"],
            "terms": [
                "content",
                "databas",
                "develop",
                "discuss",
                "document",
                "engin",
                "guid",
                "program",
                "python",
                "search",
            ],
            "positions": {
                "document": [0],
                "python": [1],
                "guid": [2],
                "program": [3],
                "search": [4],
                "engin": [5],
                "databas": [6],
                "develop": [7],
            },
        }
        for i in range(10)
    ]

    for doc in sample_docs:
        indexer.add_document(doc)

    indexer.calculate_idf(recalculate=True)
    yield indexer
    indexer.close()


@pytest.fixture
def test_search_engine(seeded_indexer: SQLiteIndexer) -> SearchEngine:
    """Provide a SearchEngine instance backed by the seeded indexer."""
    return SearchEngine(seeded_indexer)


@pytest.fixture
def test_app_with_engine(
    seeded_indexer: SQLiteIndexer, test_search_engine: SearchEngine
) -> FastAPI:
    """Create isolated FastAPI app injecting test indexer and engine via create_app."""
    return create_app(indexer=seeded_indexer, search_engine=test_search_engine)


@pytest.fixture
def test_client_with_engine(
    test_app_with_engine: FastAPI,
) -> Generator[TestClient, None, None]:
    """Provide a TestClient connected to the isolated test application."""
    with TestClient(test_app_with_engine) as test_client:
        yield test_client


@pytest.fixture
def mock_clock() -> Dict[str, float]:
    """Provide a controllable clock for deterministic rate limit testing."""
    return {"current_time": 1000.0}


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: Any, call: Any) -> Generator[None, None, None]:
    """Capture test execution outcome on the test item for artifact generation."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)
