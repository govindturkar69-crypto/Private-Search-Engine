"""Pydantic v2 schemas and models for the Admin subsystem."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CrawlStatus(str, Enum):
    """Lifecycle status states for crawl jobs."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class CrawlPriority(str, Enum):
    """Crawl queue priority level."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class CrawlRequest(BaseModel):
    """Request payload to initiate a new crawl."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "seed_urls": ["https://example.com"],
                "max_documents": 500,
                "max_depth": 3,
                "priority": "normal",
            }
        }
    )

    seed_urls: List[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="List of initial seed URLs (1 to 10 URLs)",
    )
    max_documents: int = Field(
        1000,
        ge=1,
        le=10000,
        description="Maximum documents to crawl and index (1 to 10,000)",
    )
    max_depth: int = Field(
        3,
        ge=1,
        le=5,
        description="Maximum crawl link depth (1 to 5)",
    )
    priority: CrawlPriority = Field(
        CrawlPriority.NORMAL,
        description="Queue priority (low, normal, high)",
    )

    @field_validator("seed_urls")
    @classmethod
    def validate_seed_urls(cls, urls: List[str]) -> List[str]:
        """Ensure seed URLs are valid, non-empty, and do not exceed length limits."""
        cleaned_urls: List[str] = []
        for url in urls:
            if not isinstance(url, str):
                raise ValueError("Each seed URL must be a string")
            cleaned = url.strip()
            if not cleaned:
                raise ValueError("Seed URL cannot be empty or whitespace-only")
            if len(cleaned) > 2048:
                raise ValueError("Seed URL exceeds maximum length of 2048 characters")
            cleaned_urls.append(cleaned)
        return cleaned_urls


class CrawlResponse(BaseModel):
    """Crawl lifecycle and progress status response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "crawl_id": "crawl-1726400000",
                "status": "running",
                "start_time": "2026-09-15T12:00:00Z",
                "documents_crawled": 45,
                "documents_indexed": 42,
                "errors": 1,
                "urls_queued": 120,
                "current_url": "https://example.com/page",
                "progress_percent": 4,
            }
        }
    )

    crawl_id: str
    status: CrawlStatus
    start_time: Optional[str] = None
    documents_crawled: int = 0
    documents_indexed: int = 0
    errors: int = 0
    urls_queued: int = 0
    current_url: Optional[str] = None
    progress_percent: int = 0


class IndexMetrics(BaseModel):
    """Health and metric totals of the SQLite inverted index."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_documents": 1250,
                "total_terms": 18450,
                "total_postings": 154200,
                "avg_postings_per_term": 8.35,
                "index_size_mb": 4.5,
                "last_updated": "2026-09-15T12:00:00Z",
                "health_status": "healthy",
            }
        }
    )

    total_documents: int
    total_terms: int
    total_postings: int
    avg_postings_per_term: float
    index_size_mb: float
    last_updated: str
    health_status: str


class SystemMetrics(BaseModel):
    """Host/Container performance measurements genuinely sampled via psutil."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "cpu_percent": 14.2,
                "memory_percent": 48.5,
                "disk_percent": 62.1,
                "memory_used_mb": 3950.0,
                "memory_total_mb": 8192.0,
                "disk_used_gb": 124.5,
                "disk_total_gb": 256.0,
            }
        }
    )

    cpu_percent: float
    memory_percent: float
    disk_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_used_gb: float
    disk_total_gb: float


class LogEntry(BaseModel):
    """Single parsed log entry from the application log."""

    timestamp: str
    level: str
    module: str
    message: str


class ConfigUpdateRequest(BaseModel):
    """Typed request for runtime-only configuration updates."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "key": "rate_limit_per_minute",
                "value": 120,
            }
        }
    )

    key: str
    value: Any
    description: Optional[str] = None


class RuntimeConfigResponse(BaseModel):
    """Current runtime configuration settings and persistence notice."""

    settings: Dict[str, Any]
    notice: str = "Runtime-only settings. Changes reset when the server restarts."


class AdminHealthResponse(BaseModel):
    """Readiness probe for the authenticated admin subsystem."""

    status: str = "ok"
    admin_ready: bool = True
    crawler_ready: bool = True
    index_ready: bool = True
    timestamp: str
