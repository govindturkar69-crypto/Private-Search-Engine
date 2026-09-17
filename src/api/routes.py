"""FastAPI route definitions for Search Engine API."""

from datetime import datetime, timezone
import html
import logging
from pathlib import Path
import time
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from src.api import API_VERSION
from src.api.models import (
    ErrorResponse,
    HealthResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    StatsResponse,
    SuggestResponse,
)
from src.cache import LRUCache
from src.indexer import SQLiteIndexer
from src.monitoring.prometheus_exporter import CONTENT_TYPE_LATEST, PrometheusMetrics
from src.ranker.search import SearchEngine

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency Injection via app.state
# ---------------------------------------------------------------------------


def get_indexer(request: Request) -> SQLiteIndexer:
    """Retrieve SQLiteIndexer from application state."""
    indexer = getattr(request.app.state, "indexer", None)
    if indexer is None or not isinstance(indexer, SQLiteIndexer):
        raise HTTPException(
            status_code=503,
            detail="Index service is currently unavailable",
        )
    return indexer


def get_search_engine(request: Request) -> SearchEngine:
    """Retrieve SearchEngine from application state."""
    engine = getattr(request.app.state, "search_engine", None)
    if engine is None or not isinstance(engine, SearchEngine):
        raise HTTPException(
            status_code=503,
            detail="Search engine is currently unavailable",
        )
    return engine


# ---------------------------------------------------------------------------
# Core Unified Search Execution
# ---------------------------------------------------------------------------


async def _execute_search_service(
    query: str,
    limit: int,
    offset: int,
    engine: SearchEngine,
    max_offset: int = 1000,
    request: Optional[Request] = None,
    response: Optional[Response] = None,
) -> SearchResponse:
    """Unified search implementation shared by GET and POST routes.

    Integrates thread-safe LRU caching with persistent generation invalidation
    and bounded query latency telemetry.
    """
    clean_query = query.strip()
    if not clean_query:
        raise HTTPException(
            status_code=422,
            detail="Query cannot be empty or whitespace-only",
        )

    if offset > max_offset:
        raise HTTPException(
            status_code=422,
            detail=f"Pagination offset {offset} exceeds maximum allowed ({max_offset})",
        )

    start_time = time.perf_counter()
    cache: Optional[LRUCache] = None
    perf_metrics = None
    if request is not None and hasattr(request, "app"):
        cache = getattr(request.app.state, "search_cache", None)
        perf_metrics = getattr(request.app.state, "performance_metrics", None)

    # Resolve persistent index generation from indexer
    generation = 1
    if (
        hasattr(engine, "indexer")
        and engine.indexer is not None
        and hasattr(engine.indexer, "get_generation")
    ):
        try:
            generation = engine.indexer.get_generation()
        except Exception:
            generation = 1

    cache_key = (generation, clean_query.lower(), limit, offset)

    if cache is not None:
        cached_resp: Optional[SearchResponse] = cache.get(cache_key)
        if cached_resp is not None:
            if response is not None:
                response.headers["X-Cache"] = "HIT"
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            if perf_metrics is not None:
                perf_metrics.record_query(duration_ms=duration_ms, cache_hit=True)
            prom_metrics: Optional[PrometheusMetrics] = (
                getattr(request.app.state, "prometheus_metrics", None)
                if request is not None
                else None
            )
            if prom_metrics is not None:
                prom_metrics.record_cache_hit()

            # Return fresh copy with current execution time
            # without mutating cached object
            return SearchResponse(
                query=cached_resp.query,
                results=list(cached_resp.results),
                count=cached_resp.count,
                total_available=cached_resp.total_available,
                limit=cached_resp.limit,
                offset=cached_resp.offset,
                execution_time_ms=duration_ms,
            )

    if response is not None:
        response.headers["X-Cache"] = "MISS"
    prom_metrics = (
        getattr(request.app.state, "prometheus_metrics", None)
        if request is not None
        else None
    )
    if prom_metrics is not None:
        prom_metrics.record_cache_miss()

    try:
        results, total_available, error = engine.search_with_total(
            clean_query, limit=limit, offset=offset
        )
    except Exception as e:
        logger.error(f"Search execution error: {e}")
        if perf_metrics is not None:
            perf_metrics.record_error()
        raise HTTPException(status_code=500, detail="Internal server error")

    if error:
        if perf_metrics is not None:
            perf_metrics.record_error()
        raise HTTPException(status_code=400, detail=error)

    # Safe snippet sanitization preventing executable HTML injection
    items: List[SearchResultItem] = []
    for r in results:
        safe_snippet = html.escape(r.snippet, quote=False)
        items.append(
            SearchResultItem(
                doc_id=r.doc_id,
                url=r.url,
                title=r.title,
                description=r.description,
                snippet=safe_snippet,
                score=r.score,
                relevance=r.relevance_score,
                metadata=r.metadata,
            )
        )

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    if perf_metrics is not None:
        perf_metrics.record_query(duration_ms=duration_ms, cache_hit=False)

    search_response = SearchResponse(
        query=clean_query,
        results=items,
        count=len(items),
        total_available=total_available,
        limit=limit,
        offset=offset,
        execution_time_ms=duration_ms,
    )

    if cache is not None:
        cache.set(cache_key, search_response)

    return search_response


# ---------------------------------------------------------------------------
# Search Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/api/v1/search",
    response_model=SearchResponse,
    tags=["Search"],
    summary="Execute search query (POST JSON payload)",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid query syntax"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        503: {"model": ErrorResponse, "description": "Search service unavailable"},
    },
)
async def search_post(
    body: SearchRequest,
    request: Request,
    response: Response,
    engine: SearchEngine = Depends(get_search_engine),
) -> SearchResponse:
    """Execute search query with structured JSON payload."""
    max_offset = getattr(request.app.state, "max_offset", 1000)
    return await _execute_search_service(
        query=body.query,
        limit=body.limit,
        offset=body.offset,
        engine=engine,
        max_offset=max_offset,
        request=request,
        response=response,
    )


@router.get(
    "/api/v1/search",
    response_model=SearchResponse,
    tags=["Search"],
    summary="Execute search query (GET query parameters)",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid query syntax"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        503: {"model": ErrorResponse, "description": "Search service unavailable"},
    },
)
async def search_get(
    request: Request,
    response: Response,
    q: str = Query(
        ...,
        min_length=1,
        max_length=500,
        description="Search query string with operators (+, -, quotes)",
    ),
    limit: int = Query(
        10, ge=1, le=100, description="Maximum number of results to return"
    ),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    engine: SearchEngine = Depends(get_search_engine),
) -> SearchResponse:
    """Execute search query with URL query parameters."""
    max_offset = getattr(request.app.state, "max_offset", 1000)
    return await _execute_search_service(
        query=q,
        limit=limit,
        offset=offset,
        engine=engine,
        max_offset=max_offset,
        request=request,
        response=response,
    )


# Legacy frontend route aliases
@router.get(
    "/api/search",
    response_model=SearchResponse,
    tags=["Search"],
    include_in_schema=False,
)
async def legacy_search_get(
    request: Request,
    response: Response,
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    engine: SearchEngine = Depends(get_search_engine),
) -> SearchResponse:
    """Legacy alias supporting GET /api/search for frontend compatibility."""
    max_offset = getattr(request.app.state, "max_offset", 1000)
    return await _execute_search_service(
        query=q,
        limit=limit,
        offset=offset,
        engine=engine,
        max_offset=max_offset,
        request=request,
        response=response,
    )


@router.post(
    "/api/search",
    response_model=SearchResponse,
    tags=["Search"],
    include_in_schema=False,
)
async def legacy_search_post(
    body: SearchRequest,
    request: Request,
    response: Response,
    engine: SearchEngine = Depends(get_search_engine),
) -> SearchResponse:
    """Legacy alias supporting POST /api/search."""
    max_offset = getattr(request.app.state, "max_offset", 1000)
    return await _execute_search_service(
        query=body.query,
        limit=body.limit,
        offset=body.offset,
        engine=engine,
        max_offset=max_offset,
        request=request,
        response=response,
    )


# ---------------------------------------------------------------------------
# Suggestions Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/api/v1/suggest",
    response_model=SuggestResponse,
    tags=["Suggestions"],
    summary="Get autocomplete suggestions matching term prefix",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        503: {"model": ErrorResponse, "description": "Search service unavailable"},
    },
)
async def suggest(
    prefix: str = Query(
        ..., min_length=1, max_length=50, description="Term prefix to autocomplete"
    ),
    limit: int = Query(5, ge=1, le=20, description="Maximum suggestions to return"),
    engine: SearchEngine = Depends(get_search_engine),
) -> SuggestResponse:
    """Retrieve autocomplete suggestions from the inverted index vocabulary."""
    clean_prefix = prefix.strip()
    if not clean_prefix:
        raise HTTPException(
            status_code=422,
            detail="Prefix cannot be empty or whitespace-only",
        )

    try:
        suggestions = engine.get_suggestions(clean_prefix, limit=limit)
        return SuggestResponse(prefix=clean_prefix, suggestions=suggestions)
    except Exception as e:
        logger.error(f"Suggestion retrieval error: {e}")
        raise HTTPException(status_code=500, detail="Suggestions failed")


@router.get(
    "/api/suggest",
    response_model=SuggestResponse,
    tags=["Suggestions"],
    include_in_schema=False,
)
async def legacy_suggest(
    prefix: str = Query(..., min_length=1, max_length=50),
    limit: int = Query(5, ge=1, le=20),
    engine: SearchEngine = Depends(get_search_engine),
) -> SuggestResponse:
    """Legacy alias supporting GET /api/suggest."""
    return await suggest(prefix=prefix, limit=limit, engine=engine)


# ---------------------------------------------------------------------------
# Statistics Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/api/v1/stats",
    response_model=StatsResponse,
    tags=["Index"],
    summary="Retrieve inverted index statistics and database size",
    responses={
        503: {"model": ErrorResponse, "description": "Index service unavailable"}
    },
)
async def stats(
    indexer: SQLiteIndexer = Depends(get_indexer),
) -> StatsResponse:
    """Retrieve document, term, and storage statistics from SQLite metadata."""
    try:
        stats_data = indexer.get_stats()
    except Exception as e:
        logger.error(f"Failed to fetch index stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve index stats")

    # Safely compute file size on disk without blocking table scans
    index_size_mb = 0.0
    try:
        db_path = getattr(indexer, "db_path", None)
        if db_path and str(db_path) != ":memory:":
            p = Path(db_path)
            if p.exists():
                size_bytes = p.stat().st_size
                wal_path = Path(str(db_path) + "-wal")
                if wal_path.exists():
                    size_bytes += wal_path.stat().st_size
                index_size_mb = round(size_bytes / (1024 * 1024), 2)
    except Exception as e:
        logger.debug(f"Could not read index file size on disk: {e}")
        index_size_mb = 0.0

    return StatsResponse(
        total_documents=stats_data.get("total_documents", 0),
        total_terms=stats_data.get("total_terms", 0),
        total_postings=stats_data.get("total_postings", 0),
        avg_postings_per_term=stats_data.get("avg_postings_per_term", 0.0),
        index_size_mb=index_size_mb,
    )


@router.get(
    "/api/stats",
    response_model=StatsResponse,
    tags=["Index"],
    include_in_schema=False,
)
async def legacy_stats(
    indexer: SQLiteIndexer = Depends(get_indexer),
) -> StatsResponse:
    """Legacy alias supporting GET /api/stats."""
    return await stats(indexer=indexer)


# ---------------------------------------------------------------------------
# Health & Readiness Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/api/v1/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Readiness health check inspecting index initialization state",
)
async def health_v1(request: Request) -> HealthResponse:
    """Readiness endpoint verifying search engine readiness."""
    indexer = getattr(request.app.state, "indexer", None)
    search_engine = getattr(request.app.state, "search_engine", None)
    index_ready = False

    if indexer is not None and search_engine is not None:
        try:
            stats_data = indexer.get_stats()
            index_ready = stats_data.get("total_documents", 0) > 0
        except Exception:
            index_ready = False

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return HealthResponse(
        status="ok",
        version=API_VERSION,
        timestamp=now_iso,
        index_ready=index_ready,
    )


@router.get(
    "/api/health",
    tags=["Health"],
    summary="Lightweight container liveness check",
)
async def health_legacy() -> Dict[str, str]:
    """Lightweight liveness check for container orchestrators."""
    return {"status": "ok"}


@router.get(
    "/health",
    tags=["Health"],
    summary="Root liveness check",
    include_in_schema=False,
)
async def health_root() -> Dict[str, str]:
    """Root liveness check alias."""
    return {"status": "ok"}


@router.get(
    "/metrics",
    tags=["Health"],
    summary="Prometheus metrics exposition endpoint",
    include_in_schema=False,
)
async def metrics_endpoint(request: Request) -> Response:
    """Expose Prometheus metrics in official plaintext exposition format."""
    prom_metrics: Optional[PrometheusMetrics] = getattr(
        request.app.state, "prometheus_metrics", None
    )
    indexer = getattr(request.app.state, "indexer", None)

    if prom_metrics is not None and indexer is not None:
        try:
            stats_data = indexer.get_stats()
            doc_count = stats_data.get("total_documents", 0)
            term_count = stats_data.get("unique_terms", 0)
            generation = indexer.get_generation()
            prom_metrics.update_index_gauges(doc_count, term_count, generation)
        except Exception as exc:
            logger.debug(f"Error updating index gauges for /metrics: {exc}")

    if prom_metrics is None:
        return Response(content=b"", media_type="text/plain; version=0.0.4")

    exposition = prom_metrics.generate_exposition()
    return Response(content=exposition, media_type=CONTENT_TYPE_LATEST)
