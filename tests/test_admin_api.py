import os
from pathlib import Path
from typing import Generator
import pytest
from fastapi.testclient import TestClient

from src.admin.crawl_manager import CrawlManager
from src.admin.log_service import LogService, redact_sensitive_data
from src.config import Config, CrawlConfig, IndexConfig, ServerConfig
from src.indexer import SQLiteIndexer
from src.main import create_app


@pytest.fixture
def temp_db_path(tmp_path: Path) -> str:
    """Create a unique temporary SQLite database file path."""
    return str(tmp_path / "test_admin_index.db")


@pytest.fixture
def temp_log_path(tmp_path: Path) -> str:
    """Create a temporary log file path."""
    log_file = tmp_path / "test_app.log"
    log_content = (
        "2026-09-15 12:00:00,000 - src.main - INFO - Application starting\n"
        "2026-09-15 12:00:01,000 - src.crawler - DEBUG - Discovered link "
        "https://example.com/a\n"
        "2026-09-15 12:00:02,000 - src.api - WARNING - High latency detected\n"
        "2026-09-15 12:00:03,000 - src.auth - ERROR - Auth failure with "
        "token=secret-token-12345\n"
    )
    log_file.write_text(log_content, encoding="utf-8")
    return str(log_file)


@pytest.fixture
def test_config(temp_db_path: str) -> Config:
    """Create test configuration with fixed admin token."""
    return Config(
        crawl=CrawlConfig(crawl_delay=0.1, max_depth=2),
        index=IndexConfig(database_path=temp_db_path),
        server=ServerConfig(
            log_level="INFO",
            rate_limit_per_minute=1000,
            admin_token="test-secret-token-xyz",
        ),
    )


@pytest.fixture
def client(
    test_config: Config, temp_log_path: str
) -> Generator[TestClient, None, None]:
    """Provide a FastAPI TestClient configured for admin testing."""
    indexer = SQLiteIndexer(test_config.index.database_path)
    app = create_app(config=test_config, indexer=indexer)

    # Attach crawl manager with mock DNS resolver for offline/deterministic testing
    from src.crawler.fetcher import Fetcher

    mock_fetcher = Fetcher(dns_resolver=lambda h: ["93.184.216.34"])
    app.state.crawl_manager = CrawlManager(indexer=indexer, fetcher=mock_fetcher)

    # Attach log service with isolated temporary log file
    app.state.log_service = LogService(temp_log_path)

    with TestClient(app) as test_client:
        yield test_client

    indexer.close()


ADMIN_AUTH_HEADERS = {"X-Admin-Token": "test-secret-token-xyz"}


# ---------------------------------------------------------------------------
# 1. Admin Authentication Tests
# ---------------------------------------------------------------------------


def test_auth_missing_token(client: TestClient) -> None:
    """Missing X-Admin-Token header returns HTTP 401."""
    res = client.get("/api/v1/admin/health")
    assert res.status_code == 401
    data = res.json()
    assert data["code"] == 401
    assert "authentication required" in data["error"].lower()


def test_auth_invalid_token(client: TestClient) -> None:
    """Invalid X-Admin-Token header returns HTTP 403."""
    res = client.get("/api/v1/admin/health", headers={"X-Admin-Token": "wrong-token"})
    assert res.status_code == 403
    data = res.json()
    assert data["code"] == 403
    assert "invalid admin token" in data["error"].lower()


def test_auth_valid_token(client: TestClient) -> None:
    """Valid token in X-Admin-Token returns HTTP 200."""
    res = client.get("/api/v1/admin/health", headers=ADMIN_AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_auth_bearer_token(client: TestClient) -> None:
    """Valid token in Authorization: Bearer header returns HTTP 200."""
    res = client.get(
        "/api/v1/admin/health",
        headers={"Authorization": "Bearer test-secret-token-xyz"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_auth_production_unset_token_fails(temp_db_path: str) -> None:
    """In production environment without ADMIN_TOKEN configured, returns HTTP 500."""
    cfg = Config(
        server=ServerConfig(admin_token=None),
        index=IndexConfig(database_path=temp_db_path),
    )
    indexer = SQLiteIndexer(temp_db_path)
    app = create_app(config=cfg, indexer=indexer)

    old_env = os.environ.get("ENV")
    old_admin = os.environ.get("ADMIN_TOKEN")
    try:
        os.environ["ENV"] = "production"
        if "ADMIN_TOKEN" in os.environ:
            del os.environ["ADMIN_TOKEN"]

        with TestClient(app) as tc:
            res = tc.get(
                "/api/v1/admin/health",
                headers={"X-Admin-Token": "some-token"},
            )
            assert res.status_code == 500
            assert "not configured on production server" in res.json()["error"]
    finally:
        if old_env is not None:
            os.environ["ENV"] = old_env
        else:
            os.environ.pop("ENV", None)
        if old_admin is not None:
            os.environ["ADMIN_TOKEN"] = old_admin
        indexer.close()


def test_auth_dev_fallback_token(temp_db_path: str) -> None:
    """In development environment without ADMIN_TOKEN, dev-admin-secret-token works."""
    cfg = Config(
        server=ServerConfig(admin_token=None),
        index=IndexConfig(database_path=temp_db_path),
    )
    indexer = SQLiteIndexer(temp_db_path)
    app = create_app(config=cfg, indexer=indexer)

    old_env = os.environ.get("ENV")
    old_admin = os.environ.get("ADMIN_TOKEN")
    try:
        os.environ["ENV"] = "development"
        if "ADMIN_TOKEN" in os.environ:
            del os.environ["ADMIN_TOKEN"]

        with TestClient(app) as tc:
            res = tc.get(
                "/api/v1/admin/health",
                headers={"X-Admin-Token": "dev-admin-secret-token"},
            )
            assert res.status_code == 200
            assert res.json()["status"] == "ok"
    finally:
        if old_env is not None:
            os.environ["ENV"] = old_env
        else:
            os.environ.pop("ENV", None)
        if old_admin is not None:
            os.environ["ADMIN_TOKEN"] = old_admin
        indexer.close()


# ---------------------------------------------------------------------------
# 2. Crawler State Machine and Concurrency Tests
# ---------------------------------------------------------------------------


def test_crawler_initial_status(client: TestClient) -> None:
    """Initial crawler status should be idle."""
    res = client.get("/api/v1/admin/crawler/status", headers=ADMIN_AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "idle"
    assert data["documents_crawled"] == 0
    assert data["documents_indexed"] == 0


def test_crawler_request_validation_empty_seeds(client: TestClient) -> None:
    """Empty seed_urls list must return HTTP 422."""
    payload = {"seed_urls": []}
    res = client.post(
        "/api/v1/admin/crawler/start",
        json=payload,
        headers=ADMIN_AUTH_HEADERS,
    )
    assert res.status_code == 422


def test_crawler_request_validation_too_many_seeds(client: TestClient) -> None:
    """More than 10 seed URLs must return HTTP 422."""
    payload = {"seed_urls": [f"https://example{i}.com" for i in range(11)]}
    res = client.post(
        "/api/v1/admin/crawler/start",
        json=payload,
        headers=ADMIN_AUTH_HEADERS,
    )
    assert res.status_code == 422


def test_crawler_request_validation_out_of_bounds_params(client: TestClient) -> None:
    """Out of bound depth (>5) and max_documents (>10000) must return HTTP 422."""
    res1 = client.post(
        "/api/v1/admin/crawler/start",
        json={"seed_urls": ["https://example.com"], "max_depth": 6},
        headers=ADMIN_AUTH_HEADERS,
    )
    assert res1.status_code == 422

    res2 = client.post(
        "/api/v1/admin/crawler/start",
        json={"seed_urls": ["https://example.com"], "max_documents": 15000},
        headers=ADMIN_AUTH_HEADERS,
    )
    assert res2.status_code == 422


def test_crawler_ssrf_seed_rejected(client: TestClient) -> None:
    """Private IP / loopback seed URL must be rejected with HTTP 422."""
    payload = {"seed_urls": ["http://127.0.0.1:8080/private"]}
    res = client.post(
        "/api/v1/admin/crawler/start",
        json=payload,
        headers=ADMIN_AUTH_HEADERS,
    )
    assert res.status_code == 422
    assert "SSRF" in res.json()["error"] or "safety" in res.json()["error"]


def test_crawler_state_transitions(client: TestClient) -> None:
    """Verify idle -> running -> paused -> running -> stopped transitions."""
    # 1. Invalid pause when idle -> 409
    res_pause_idle = client.post(
        "/api/v1/admin/crawler/pause", headers=ADMIN_AUTH_HEADERS
    )
    assert res_pause_idle.status_code == 409

    # 2. Invalid resume when idle -> 409
    res_resume_idle = client.post(
        "/api/v1/admin/crawler/resume", headers=ADMIN_AUTH_HEADERS
    )
    assert res_resume_idle.status_code == 409

    # 3. Invalid stop when idle -> 409
    res_stop_idle = client.post(
        "/api/v1/admin/crawler/stop", headers=ADMIN_AUTH_HEADERS
    )
    assert res_stop_idle.status_code == 409

    # 4. Start crawl
    res_start = client.post(
        "/api/v1/admin/crawler/start",
        json={
            "seed_urls": ["https://example.com"],
            "max_documents": 5,
            "max_depth": 1,
        },
        headers=ADMIN_AUTH_HEADERS,
    )
    assert res_start.status_code == 200
    assert res_start.json()["status"] == "running"

    # 5. Start while already running -> 409
    res_start_conflict = client.post(
        "/api/v1/admin/crawler/start",
        json={"seed_urls": ["https://example.com"]},
        headers=ADMIN_AUTH_HEADERS,
    )
    assert res_start_conflict.status_code == 409

    # 6. Pause while running -> 200
    res_pause = client.post("/api/v1/admin/crawler/pause", headers=ADMIN_AUTH_HEADERS)
    assert res_pause.status_code == 200
    assert res_pause.json()["status"] == "paused"

    # 7. Pause while already paused -> 409
    res_pause_again = client.post(
        "/api/v1/admin/crawler/pause", headers=ADMIN_AUTH_HEADERS
    )
    assert res_pause_again.status_code == 409

    # 8. Resume while paused -> 200
    res_resume = client.post("/api/v1/admin/crawler/resume", headers=ADMIN_AUTH_HEADERS)
    assert res_resume.status_code == 200
    assert res_resume.json()["status"] == "running"

    # 9. Stop while running -> 200
    res_stop = client.post("/api/v1/admin/crawler/stop", headers=ADMIN_AUTH_HEADERS)
    assert res_stop.status_code == 200
    assert res_stop.json()["status"] == "stopped"

    # 10. Stop while already stopped -> 409
    res_stop_again = client.post(
        "/api/v1/admin/crawler/stop", headers=ADMIN_AUTH_HEADERS
    )
    assert res_stop_again.status_code == 409


# ---------------------------------------------------------------------------
# 3. Index & System Metrics Tests
# ---------------------------------------------------------------------------


def test_index_metrics_empty(client: TestClient) -> None:
    """Index metrics for fresh database."""
    res = client.get("/api/v1/admin/metrics/index", headers=ADMIN_AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["total_documents"] == 0
    assert data["total_terms"] == 0
    assert data["total_postings"] == 0
    assert data["health_status"] == "empty"
    assert "index_size_mb" in data


def test_system_metrics_structure(client: TestClient) -> None:
    """System metrics should return measured psutil fields and no placeholders."""
    res = client.get("/api/v1/admin/metrics/system", headers=ADMIN_AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()

    assert "cpu_percent" in data
    assert "memory_percent" in data
    assert "disk_percent" in data
    assert "memory_used_mb" in data
    assert "memory_total_mb" in data
    assert "disk_used_gb" in data
    assert "disk_total_gb" in data

    # Verify absence of unmeasured fake metrics
    assert "requests_per_second" not in data
    assert "active_connections" not in data
    assert "avg_response_time_ms" not in data
    assert "error_rate_percent" not in data


def test_index_clear(client: TestClient) -> None:
    """Clear index endpoint clears documents and reset metadata."""
    res = client.post("/api/v1/admin/index/clear", headers=ADMIN_AUTH_HEADERS)
    assert res.status_code == 200
    assert "cleared successfully" in res.json()["message"]


# ---------------------------------------------------------------------------
# 4. Log Service and Redaction Tests
# ---------------------------------------------------------------------------


def test_redact_sensitive_data() -> None:
    """Ensure sensitive tokens and secrets are redacted."""
    raw = (
        "User logged in with admin_token=supersecret123 and auth Bearer abcdef12345678"
    )
    cleaned = redact_sensitive_data(raw)
    assert "supersecret123" not in cleaned
    assert "abcdef12345678" not in cleaned
    assert "***REDACTED***" in cleaned


def test_get_logs_default(client: TestClient) -> None:
    """Retrieve logs with default bounds and token redaction."""
    res = client.get("/api/v1/admin/logs", headers=ADMIN_AUTH_HEADERS)
    assert res.status_code == 200
    logs = res.json()
    assert isinstance(logs, list)
    assert len(logs) == 4

    # Verify redaction of secret-token-12345
    error_log = [item for item in logs if item["level"] == "ERROR"][0]
    assert "secret-token-12345" not in error_log["message"]
    assert "***REDACTED***" in error_log["message"]


def test_get_logs_level_filter(client: TestClient) -> None:
    """Filter logs by level."""
    res = client.get("/api/v1/admin/logs?level=ERROR", headers=ADMIN_AUTH_HEADERS)
    assert res.status_code == 200
    logs = res.json()
    assert len(logs) == 1
    assert logs[0]["level"] == "ERROR"


def test_get_logs_limit_exceeded(client: TestClient) -> None:
    """Querying > 500 lines returns HTTP 422."""
    res = client.get("/api/v1/admin/logs?lines=501", headers=ADMIN_AUTH_HEADERS)
    assert res.status_code == 422


def test_get_logs_missing_file() -> None:
    """Missing log file returns empty list gracefully."""
    svc = LogService("non_existent_file.log")
    assert svc.get_logs() == []


# ---------------------------------------------------------------------------
# 5. Runtime Configuration Service Tests
# ---------------------------------------------------------------------------


def test_get_runtime_config(client: TestClient) -> None:
    """Retrieve allowlisted runtime configuration settings."""
    res = client.get("/api/v1/admin/config", headers=ADMIN_AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "settings" in data
    assert "notice" in data
    assert data["settings"]["log_level"] == "INFO"
    assert data["settings"]["rate_limit_per_minute"] == 1000
    assert "Runtime-only" in data["notice"]


def test_update_runtime_config_valid(client: TestClient) -> None:
    """Update allowlisted settings in memory."""
    # Update log_level
    res1 = client.post(
        "/api/v1/admin/config",
        json={"key": "log_level", "value": "DEBUG"},
        headers=ADMIN_AUTH_HEADERS,
    )
    assert res1.status_code == 200
    assert res1.json()["settings"]["log_level"] == "DEBUG"

    # Update rate_limit_per_minute
    res2 = client.post(
        "/api/v1/admin/config",
        json={"key": "rate_limit_per_minute", "value": 500},
        headers=ADMIN_AUTH_HEADERS,
    )
    assert res2.status_code == 200
    assert res2.json()["settings"]["rate_limit_per_minute"] == 500


def test_update_runtime_config_disallowed_key(client: TestClient) -> None:
    """Modifying non-allowlisted key (e.g. database_path) returns HTTP 400."""
    res = client.post(
        "/api/v1/admin/config",
        json={"key": "database_path", "value": "/etc/passwd"},
        headers=ADMIN_AUTH_HEADERS,
    )
    assert res.status_code == 400
    assert "cannot be modified at runtime" in res.json()["error"]


def test_update_runtime_config_invalid_value(client: TestClient) -> None:
    """Providing out-of-range value returns HTTP 400."""
    res = client.post(
        "/api/v1/admin/config",
        json={"key": "rate_limit_per_minute", "value": -10},
        headers=ADMIN_AUTH_HEADERS,
    )
    assert res.status_code == 400
    assert "between 1 and 10000" in res.json()["error"]
