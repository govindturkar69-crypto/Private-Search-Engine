"""Main FastAPI application entrypoint with lifespan, security, and routing."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from pathlib import Path
import re
import time
from typing import Any, AsyncIterator, Callable, Optional
import uuid
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.admin import ConfigService, CrawlManager, LogService, MetricsCollector
from src.api import API_VERSION
from src.api.admin_models import CrawlStatus
from src.api.admin_routes import admin_router
from src.api.middleware import (
    RateLimiter,
    create_rate_limit_response,
    get_client_ip,
)
from src.api.models import ErrorResponse
from src.api.routes import router
from src.cache import LRUCache
from src.config import Config, load_config
from src.indexer import SQLiteIndexer
from src.logger import setup_logging
from src.monitoring import PerformanceMetricsCollector, PrometheusMetrics
from src.ranker.search import SearchEngine

logger = logging.getLogger(__name__)

RE_SAFE_REQUEST_ID = re.compile(r"^[a-zA-Z0-9\-_]{1,64}$")


def _get_request_id(request: Request) -> str:
    """Extract and validate client X-Request-ID or generate a new UUID."""
    client_req_id = request.headers.get("x-request-id")
    if client_req_id and RE_SAFE_REQUEST_ID.match(client_req_id):
        return client_req_id
    return str(uuid.uuid4())[:8]


def create_app(
    config: Optional[Config] = None,
    indexer: Optional[SQLiteIndexer] = None,
    search_engine: Optional[SearchEngine] = None,
    rate_limiter: Optional[RateLimiter] = None,
    rate_limit_time_func: Optional[Callable[[], float]] = None,
    search_cache: Optional[LRUCache] = None,
    performance_metrics: Optional[PerformanceMetricsCollector] = None,
    prometheus_metrics: Optional[PrometheusMetrics] = None,
) -> FastAPI:
    """Application factory for FastAPI server and automated test isolation."""
    app_config = config or load_config()
    setup_logging(log_level=app_config.server.log_level)

    limiter = rate_limiter or RateLimiter(
        requests_per_minute=app_config.server.rate_limit_per_minute,
        time_func=rate_limit_time_func,
    )

    is_custom_indexer = indexer is not None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Manage application lifecycle with clean startup and shutdown."""
        # 1. Production security secret validation
        if app_config.server.environment == "production":
            prod_token = app_config.server.admin_token
            if not prod_token:
                logger.error(
                    "Production startup failure: ADMIN_TOKEN must be configured."
                )
                raise RuntimeError(
                    "Production configuration error: ADMIN_TOKEN is required."
                )
            if (
                len(prod_token) < 32
                or prod_token == "dev-admin-secret-token"
                or len(set(prod_token)) < 4
            ):
                logger.error(
                    "Production startup failure: ADMIN_TOKEN has insufficient entropy."
                )
                raise RuntimeError(
                    "Production configuration error: ADMIN_TOKEN must be at least "
                    "32 characters with sufficient entropy. Generate via "
                    "secrets.token_urlsafe(32)."
                )

        # 2. Startup
        active_indexer = indexer
        active_engine = search_engine

        if active_indexer is None:
            try:
                active_indexer = SQLiteIndexer(app_config.index.database_path)
                active_engine = SearchEngine(active_indexer)
                db_str = app_config.index.database_path
                logger.info(f"Search engine initialized (database={db_str})")
            except Exception as e:
                logger.error(f"Failed to initialize SQLite indexer: {e}", exc_info=True)
                active_indexer = None
                active_engine = None

        app.state.indexer = active_indexer
        app.state.search_engine = active_engine
        app.state.config = app_config
        app.state.rate_limiter = limiter
        app.state.max_offset = app_config.server.max_offset
        app.state.trusted_proxies = app_config.server.trusted_proxies

        # Admin subsystem services
        if not getattr(app.state, "crawl_manager", None):
            app.state.crawl_manager = CrawlManager(active_indexer)
        if not getattr(app.state, "metrics_collector", None):
            app.state.metrics_collector = MetricsCollector(active_indexer)
        if not getattr(app.state, "config_service", None):
            app.state.config_service = ConfigService(app_config)
        if not getattr(app.state, "log_service", None):
            app.state.log_service = LogService("data/app.log")
        if not getattr(app.state, "search_cache", None):
            app.state.search_cache = search_cache or LRUCache(max_entries=1000)
        if not getattr(app.state, "performance_metrics", None):
            app.state.performance_metrics = (
                performance_metrics or PerformanceMetricsCollector()
            )
        if not getattr(app.state, "prometheus_metrics", None):
            app.state.prometheus_metrics = (
                prometheus_metrics or PrometheusMetrics()
            )

        crawl_mgr = app.state.crawl_manager

        yield

        # Shutdown
        if crawl_mgr.status in (CrawlStatus.RUNNING, CrawlStatus.PAUSED):
            try:
                await crawl_mgr.stop_crawl()
                logger.info("Admin crawler stopped gracefully during shutdown.")
            except Exception as e:
                logger.warning(f"Error stopping crawler during shutdown: {e}")

        if not is_custom_indexer and active_indexer is not None:
            try:
                active_indexer.close()
                logger.info("SQLite indexer connection closed successfully.")
            except Exception as e:
                logger.warning(f"Error closing indexer during shutdown: {e}")

    openapi_tags = [
        {"name": "Search", "description": "Full-text search execution endpoints"},
        {"name": "Suggestions", "description": "Autocomplete search suggestions"},
        {"name": "Index", "description": "Inverted index statistics and storage"},
        {"name": "Health", "description": "Service readiness and liveness health"},
        {
            "name": "Admin",
            "description": "Token-protected administration and telemetry",
        },
    ]

    app = FastAPI(
        title="Private Search Engine",
        description="Self-hosted, privacy-first full-text search engine",
        version=API_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=openapi_tags,
        lifespan=lifespan,
    )

    # Injected test dependencies prior to startup
    app.state.indexer = indexer
    app.state.search_engine = search_engine
    app.state.config = app_config
    app.state.rate_limiter = limiter
    app.state.max_offset = app_config.server.max_offset
    app.state.trusted_proxies = app_config.server.trusted_proxies
    app.state.crawl_manager = CrawlManager(indexer)
    app.state.metrics_collector = MetricsCollector(indexer)
    app.state.config_service = ConfigService(app_config)
    app.state.log_service = LogService("data/app.log")
    app.state.search_cache = search_cache or LRUCache(max_entries=1000)
    app.state.performance_metrics = (
        performance_metrics or PerformanceMetricsCollector()
    )
    app.state.prometheus_metrics = prometheus_metrics or PrometheusMetrics()

    # CORS Middleware
    allowed_origins = (
        app_config.server.cors_origins
        if app_config.server.cors_origins
        else ["http://localhost:8000"]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # -----------------------------------------------------------------------
    # Middlewares (Order: Request ID -> Rate Limiting -> Security Headers)
    # -----------------------------------------------------------------------

    @app.middleware("http")
    async def request_lifecycle_middleware(request: Request, call_next: Any) -> Any:
        """Coordinate request IDs, rate limits, logging, and security headers."""
        request_id = _get_request_id(request)
        request.state.request_id = request_id
        start_time = time.perf_counter()

        # 1. Rate Limiting Check (bypass health and docs endpoints)
        path = request.url.path
        is_api_route = path.startswith("/api/")
        is_health = path in ("/api/health", "/api/v1/health", "/health")

        if is_api_route and not is_health:
            client_ip = get_client_ip(request, app.state.trusted_proxies)
            if not limiter.is_allowed(client_ip):
                logger.warning(
                    f"[{request_id}] Rate limit exceeded for client {client_ip}"
                )
                response = create_rate_limit_response(limiter, client_ip, request_id)
                _apply_security_headers(
                    response, request, app_config.server.enable_hsts
                )
                return response

        # 2. Dispatch request
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(
                f"[{request_id}] Unhandled error during request execution: {exc}",
                exc_info=True,
            )
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            err_body = ErrorResponse(
                error="Internal server error",
                code=500,
                timestamp=now_iso,
                request_id=request_id,
            ).model_dump()
            response = JSONResponse(status_code=500, content=err_body)

        duration_ms = (time.perf_counter() - start_time) * 1000

        # 3. Privacy-conscious Structured Logging
        log_path = path
        if not app_config.server.log_queries and is_api_route:
            log_path = path.split("?")[0]

        logger.info(
            f"[{request_id}] {request.method} {log_path} "
            f"status={response.status_code} latency={duration_ms:.2f}ms"
        )

        # 4. Centralized Prometheus Metrics Recording
        route = request.scope.get("route")
        if (
            response.status_code == 404
            or not route
            or not hasattr(route, "path")
        ):
            handler_label = "unmatched"
        elif route.path == "/{full_path:path}":
            handler_label = "spa"
        else:
            handler_label = route.path

        prom_metrics = getattr(app.state, "prometheus_metrics", None)
        if prom_metrics is not None:
            prom_metrics.record_request(
                method=request.method,
                handler=handler_label,
                status=response.status_code,
                duration_sec=duration_ms / 1000.0,
            )

        # 5. Attach Headers
        response.headers["X-Request-ID"] = request_id
        _apply_security_headers(response, request, app_config.server.enable_hsts)
        return response

    # -----------------------------------------------------------------------
    # Exception Handlers
    # -----------------------------------------------------------------------

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        """Format standard HTTPExceptions using ErrorResponse schema."""
        req_id = getattr(request.state, "request_id", None) or _get_request_id(request)
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Support dictionary details or string details
        detail_msg = str(exc.detail) if not isinstance(exc.detail, dict) else "Error"
        extra_details = exc.detail if isinstance(exc.detail, dict) else None

        error_data = ErrorResponse(
            error=detail_msg,
            code=exc.status_code,
            timestamp=now_iso,
            request_id=req_id,
            details=extra_details,
        ).model_dump()

        response = JSONResponse(
            status_code=exc.status_code,
            content=error_data,
            headers=exc.headers or {},
        )
        response.headers["X-Request-ID"] = req_id
        _apply_security_headers(response, request, app_config.server.enable_hsts)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Format Pydantic/FastAPI validation errors consistently."""
        req_id = getattr(request.state, "request_id", None) or _get_request_id(request)
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        error_data = ErrorResponse(
            error="Request validation failed",
            code=422,
            timestamp=now_iso,
            request_id=req_id,
            details=jsonable_encoder(exc.errors()),
        ).model_dump()

        response = JSONResponse(status_code=422, content=error_data)
        response.headers["X-Request-ID"] = req_id
        _apply_security_headers(response, request, app_config.server.enable_hsts)
        return response

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: Any) -> JSONResponse:
        """Format 404 responses with structured ErrorResponse."""
        req_id = getattr(request.state, "request_id", None) or _get_request_id(request)
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        error_data = ErrorResponse(
            error="Endpoint not found",
            code=404,
            timestamp=now_iso,
            request_id=req_id,
        ).model_dump()

        response = JSONResponse(status_code=404, content=error_data)
        response.headers["X-Request-ID"] = req_id
        _apply_security_headers(response, request, app_config.server.enable_hsts)
        return response

    # -----------------------------------------------------------------------
    # Routes
    # -----------------------------------------------------------------------

    dist_path = Path("frontend/dist")

    @app.get(
        "/",
        tags=["Health"],
        summary="Service root information and documentation sitemap",
    )
    async def root(request: Request) -> Any:
        """Root endpoint returning SPA index.html for browsers or API metadata."""
        accept = request.headers.get("accept", "")
        index_html = dist_path / "index.html"
        if "text/html" in accept and dist_path.is_dir() and index_html.is_file():
            from fastapi.responses import FileResponse

            return FileResponse(index_html)
        return {
            "message": "Private Search Engine API",
            "version": API_VERSION,
            "docs": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
        }

    app.include_router(router)
    app.include_router(admin_router)

    # Static assets and SPA client-route fallback (mounted after all API routes)
    if dist_path.is_dir():
        from fastapi.responses import FileResponse

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str) -> Any:
            """Serve frontend static assets and SPA routes without shadowing API."""
            parts = [p for p in full_path.replace("\\", "/").split("/") if p]
            if ".." in parts:
                raise HTTPException(status_code=403, detail="Access denied")

            if (
                full_path.startswith("api/")
                or full_path == "api"
                or full_path.startswith("metrics")
                or full_path == "metrics"
                or full_path.startswith("health")
                or full_path == "health"
                or full_path.startswith("docs")
                or full_path.startswith("redoc")
                or full_path.startswith("openapi.json")
            ):
                raise HTTPException(status_code=404, detail="Endpoint not found")

            safe_rel = "/".join(parts)
            target_file = (dist_path / safe_rel).resolve()
            try:
                if not target_file.is_relative_to(dist_path.resolve()):
                    raise HTTPException(status_code=403, detail="Access denied")
            except Exception:
                raise HTTPException(status_code=404, detail="Not found")

            if target_file.is_file():
                return FileResponse(target_file)

            # If the requested path has a file extension, do not fall back to index.html
            if "." in parts[-1]:
                raise HTTPException(status_code=404, detail="File not found")

            index_html = dist_path / "index.html"
            if index_html.is_file():
                return FileResponse(index_html)
            raise HTTPException(status_code=404, detail="Not found")

    return app


def _apply_security_headers(
    response: Any, request: Request, enable_hsts: bool = False
) -> None:
    """Apply strict defense-in-depth HTTP security headers to all responses."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-XSS-Protection"] = "1; mode=block"  # Legacy compatibility
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:;"
    )

    # HSTS only enabled if configured or request arrived via HTTPS
    if enable_hsts or request.url.scheme == "https":
        response.headers[
            "Strict-Transport-Security"
        ] = "max-age=31536000; includeSubDomains"


# Global default application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    default_cfg = load_config()
    uvicorn.run(
        "src.main:app",
        host=default_cfg.server.host,
        port=default_cfg.server.port,
        reload=True,
    )
