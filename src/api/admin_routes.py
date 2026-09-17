"""Admin subsystem routes providing token-protected management and telemetry."""

from datetime import datetime, timezone
import logging
import os
import secrets
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from src.admin.config_service import ConfigService
from src.admin.crawl_manager import CrawlManager
from src.admin.log_service import LogService
from src.admin.metrics import MetricsCollector
from src.api.admin_models import (
    AdminHealthResponse,
    ConfigUpdateRequest,
    CrawlRequest,
    CrawlResponse,
    IndexMetrics,
    LogEntry,
    RuntimeConfigResponse,
    SystemMetrics,
)
from src.indexer import SQLiteIndexer

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


def verify_admin_token(
    request: Request,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> str:
    """Verify admin authentication via constant-time token comparison."""
    # 1. Resolve provided token from header
    provided_token = x_admin_token
    if not provided_token and authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            provided_token = parts[1]

    if not provided_token:
        raise HTTPException(
            status_code=401,
            detail=(
                "Admin authentication required. Please provide X-Admin-Token header."
            ),
        )

    # 2. Resolve expected server token
    expected_token: Optional[str] = None
    if (
        hasattr(request.app.state, "config")
        and request.app.state.config
        and request.app.state.config.server.admin_token
    ):
        expected_token = request.app.state.config.server.admin_token
    elif "ADMIN_TOKEN" in os.environ:
        expected_token = os.environ["ADMIN_TOKEN"]

    from src.config import normalize_environment

    env_dict = dict(os.environ)
    if (
        hasattr(request.app.state, "config")
        and request.app.state.config
        and hasattr(request.app.state.config.server, "environment")
    ):
        if request.app.state.config.server.environment == "production":
            env_dict["ENVIRONMENT"] = "production"

    env = normalize_environment(env_dict)

    if not expected_token:
        if env == "production":
            raise HTTPException(
                status_code=500,
                detail="Admin token is not configured on production server.",
            )
        # Permitted default for development and test environments
        expected_token = "dev-admin-secret-token"

    if env == "production":
        if len(expected_token) < 32 or expected_token == "dev-admin-secret-token":
            raise HTTPException(
                status_code=500,
                detail="Admin token is insufficiently secure on production server.",
            )

    if not secrets.compare_digest(provided_token, expected_token):
        raise HTTPException(
            status_code=403,
            detail="Invalid admin token.",
        )

    return provided_token


# Service Dependency Resolvers
def get_crawl_manager(request: Request) -> CrawlManager:
    """Resolve CrawlManager from app.state."""
    if (
        not hasattr(request.app.state, "crawl_manager")
        or not request.app.state.crawl_manager
    ):
        # Lazy fallback
        indexer = getattr(request.app.state, "indexer", None)
        request.app.state.crawl_manager = CrawlManager(indexer)
    mgr: CrawlManager = request.app.state.crawl_manager
    return mgr


def get_metrics_collector(request: Request) -> MetricsCollector:
    """Resolve MetricsCollector from app.state."""
    if (
        not hasattr(request.app.state, "metrics_collector")
        or not request.app.state.metrics_collector
    ):
        indexer = getattr(request.app.state, "indexer", None)
        request.app.state.metrics_collector = MetricsCollector(indexer)
    collector: MetricsCollector = request.app.state.metrics_collector
    return collector


def get_config_service(request: Request) -> ConfigService:
    """Resolve ConfigService from app.state."""
    if (
        not hasattr(request.app.state, "config_service")
        or not request.app.state.config_service
    ):
        config = request.app.state.config
        request.app.state.config_service = ConfigService(config)
    service: ConfigService = request.app.state.config_service
    return service


def get_log_service(request: Request) -> LogService:
    """Resolve LogService from app.state."""
    if (
        not hasattr(request.app.state, "log_service")
        or not request.app.state.log_service
    ):
        request.app.state.log_service = LogService("data/app.log")
    service: LogService = request.app.state.log_service
    return service


# ---------------------------------------------------------------------------
# Admin Endpoints
# ---------------------------------------------------------------------------


@admin_router.get(
    "/health",
    response_model=AdminHealthResponse,
    summary="Admin subsystem health and readiness",
)
async def admin_health(
    request: Request,
    _token: str = Depends(verify_admin_token),
) -> AdminHealthResponse:
    """Probe status of the admin subsystem, crawler, and inverted index."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    indexer_ready = getattr(request.app.state, "indexer", None) is not None
    crawler_ready = hasattr(request.app.state, "crawl_manager")

    return AdminHealthResponse(
        status="ok",
        admin_ready=True,
        crawler_ready=crawler_ready,
        index_ready=indexer_ready,
        timestamp=now_iso,
    )


@admin_router.post(
    "/crawler/start",
    response_model=CrawlResponse,
    summary="Start background web crawl job",
)
async def start_crawler(
    payload: CrawlRequest,
    manager: CrawlManager = Depends(get_crawl_manager),
    _token: str = Depends(verify_admin_token),
) -> CrawlResponse:
    """Initiate a background crawling job with seed URLs and bounds."""
    try:
        return await manager.start_crawl(payload)
    except ValueError as e:
        err_msg = str(e)
        if "already in progress" in err_msg:
            raise HTTPException(status_code=409, detail=err_msg)
        if "SSRF" in err_msg or "Seed URL" in err_msg:
            raise HTTPException(status_code=422, detail=err_msg)
        raise HTTPException(status_code=400, detail=err_msg)


@admin_router.post(
    "/crawler/pause",
    response_model=CrawlResponse,
    summary="Pause active crawler job",
)
async def pause_crawler(
    manager: CrawlManager = Depends(get_crawl_manager),
    _token: str = Depends(verify_admin_token),
) -> CrawlResponse:
    """Pause an active crawler job."""
    try:
        return await manager.pause_crawl()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@admin_router.post(
    "/crawler/resume",
    response_model=CrawlResponse,
    summary="Resume paused crawler job",
)
async def resume_crawler(
    manager: CrawlManager = Depends(get_crawl_manager),
    _token: str = Depends(verify_admin_token),
) -> CrawlResponse:
    """Resume a paused crawler job."""
    try:
        return await manager.resume_crawl()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@admin_router.post(
    "/crawler/stop",
    response_model=CrawlResponse,
    summary="Stop active crawler job",
)
async def stop_crawler(
    manager: CrawlManager = Depends(get_crawl_manager),
    _token: str = Depends(verify_admin_token),
) -> CrawlResponse:
    """Stop an active or paused crawler job."""
    try:
        return await manager.stop_crawl()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@admin_router.get(
    "/crawler/status",
    response_model=CrawlResponse,
    summary="Get current crawler status and metrics",
)
async def get_crawler_status(
    manager: CrawlManager = Depends(get_crawl_manager),
    _token: str = Depends(verify_admin_token),
) -> CrawlResponse:
    """Return the current crawler lifecycle state and progress metrics."""
    return manager.get_status()


@admin_router.get(
    "/metrics/index",
    response_model=IndexMetrics,
    summary="Get SQLite inverted index metrics",
)
async def get_index_metrics(
    collector: MetricsCollector = Depends(get_metrics_collector),
    _token: str = Depends(verify_admin_token),
) -> IndexMetrics:
    """Retrieve document, term, posting counts and index file size."""
    return collector.get_index_metrics()


@admin_router.get(
    "/metrics/system",
    response_model=SystemMetrics,
    summary="Get host system performance metrics",
)
async def get_system_metrics(
    collector: MetricsCollector = Depends(get_metrics_collector),
    _token: str = Depends(verify_admin_token),
) -> SystemMetrics:
    """Sample host CPU, memory, and disk resource metrics strictly via psutil."""
    return collector.get_system_metrics()


@admin_router.post(
    "/index/clear",
    summary="Clear all documents from the inverted index",
)
async def clear_index(
    request: Request,
    collector: MetricsCollector = Depends(get_metrics_collector),
    _token: str = Depends(verify_admin_token),
) -> Dict[str, str]:
    """Clear all indexed documents and postings from the SQLite database."""
    indexer: Optional[SQLiteIndexer] = getattr(request.app.state, "indexer", None)
    if not indexer:
        raise HTTPException(status_code=503, detail="Index database is not available")

    success = indexer.clear_index()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to clear inverted index")

    return {"message": "Inverted index cleared successfully."}


@admin_router.get(
    "/logs",
    response_model=List[LogEntry],
    summary="Retrieve bounded application logs with token redaction",
)
async def get_logs(
    lines: int = Query(
        100, ge=1, le=500, description="Number of tail lines (1 to 500)"
    ),
    level: Optional[str] = Query(
        None, description="Optional log level filter (DEBUG, INFO, etc.)"
    ),
    log_service: LogService = Depends(get_log_service),
    _token: str = Depends(verify_admin_token),
) -> List[LogEntry]:
    """Return bounded tail of application logs with sensitive data redacted."""
    return log_service.get_logs(lines=lines, level=level)


@admin_router.get(
    "/config",
    response_model=RuntimeConfigResponse,
    summary="Get allowlisted runtime configuration",
)
async def get_runtime_config(
    config_service: ConfigService = Depends(get_config_service),
    _token: str = Depends(verify_admin_token),
) -> RuntimeConfigResponse:
    """Retrieve the current allowlisted runtime-only configuration settings."""
    return config_service.get_runtime_config()


@admin_router.post(
    "/config",
    response_model=RuntimeConfigResponse,
    summary="Update allowlisted runtime configuration in-memory",
)
async def update_runtime_config(
    update: ConfigUpdateRequest,
    config_service: ConfigService = Depends(get_config_service),
    _token: str = Depends(verify_admin_token),
) -> RuntimeConfigResponse:
    """Update an allowlisted configuration value in-memory without disk persistence."""
    try:
        return config_service.update_setting(update)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
