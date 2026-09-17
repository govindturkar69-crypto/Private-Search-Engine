"""Pydantic v2 request and response models for Search API."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SearchRequest(BaseModel):
    """Search query request payload."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "python programming",
                "limit": 10,
                "offset": 0,
            }
        }
    )

    query: str = Field(
        ...,
        description=(
            "Search query string with optional +required, -excluded, and phrases"
        ),
    )
    limit: int = Field(
        10,
        ge=1,
        le=100,
        description="Maximum number of results to return (1-100)",
    )
    offset: int = Field(
        0,
        ge=0,
        description="Pagination offset",
    )

    @field_validator("query", mode="before")
    @classmethod
    def validate_query(cls, v: Any) -> str:
        """Strip whitespace and enforce length limits."""
        if not isinstance(v, str):
            raise ValueError("Query must be a string")
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Query cannot be empty or whitespace-only")
        if len(cleaned) > 500:
            raise ValueError("Query length exceeds maximum of 500 characters")
        return cleaned


class SearchResultItem(BaseModel):
    """Individual ranked search result."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "doc_id": 1,
                "url": "https://example.com/python",
                "title": "Python Programming",
                "description": "Learn Python",
                "snippet": "Python is a **programming** language...",
                "score": 2.451,
                "relevance": 75,
            }
        }
    )

    doc_id: int
    url: str
    title: str
    description: str
    snippet: str
    score: float
    relevance: int = Field(
        ...,
        ge=0,
        le=100,
        description="Normalized percentage relevance score relative to top result",
    )
    metadata: Optional[Dict[str, Any]] = None


class SearchResponse(BaseModel):
    """Search execution response with pagination and timing metrics."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "python",
                "results": [],
                "count": 0,
                "total_available": 0,
                "limit": 10,
                "offset": 0,
                "execution_time_ms": 12.5,
            }
        }
    )

    query: str
    results: List[SearchResultItem]
    count: int = Field(
        ...,
        description="Number of results returned in this response page",
    )
    total_available: int = Field(
        ...,
        description="Total matching documents before pagination",
    )
    limit: int
    offset: int
    execution_time_ms: float


class SuggestRequest(BaseModel):
    """Autocomplete suggestions request."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"prefix": "pyt", "limit": 5}}
    )

    prefix: str = Field(..., description="Term prefix to autocomplete")
    limit: int = Field(5, ge=1, le=20, description="Max suggestions to return")

    @field_validator("prefix", mode="before")
    @classmethod
    def validate_prefix(cls, v: Any) -> str:
        """Strip whitespace and enforce length limits."""
        if not isinstance(v, str):
            raise ValueError("Prefix must be a string")
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Prefix cannot be empty or whitespace-only")
        if len(cleaned) > 50:
            raise ValueError("Prefix length exceeds maximum of 50 characters")
        return cleaned


class SuggestResponse(BaseModel):
    """Autocomplete suggestions response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "prefix": "pyt",
                "suggestions": ["python", "pytest", "pytorch"],
            }
        }
    )

    prefix: str
    suggestions: List[str]


class StatsResponse(BaseModel):
    """Index statistics and storage utilization."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_documents": 1000,
                "total_terms": 5000,
                "total_postings": 50000,
                "avg_postings_per_term": 10.0,
                "index_size_mb": 5.2,
            }
        }
    )

    total_documents: int
    total_terms: int
    total_postings: int
    avg_postings_per_term: float
    index_size_mb: float


class HealthResponse(BaseModel):
    """Health check readiness response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "version": "1.0.0",
                "timestamp": "2026-09-12T14:10:00Z",
                "index_ready": True,
            }
        }
    )

    status: str
    version: str
    timestamp: str
    index_ready: bool


class ErrorResponse(BaseModel):
    """Consistent structured error response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "Invalid query",
                "code": 400,
                "timestamp": "2026-09-12T14:10:00Z",
                "request_id": "req-123456",
            }
        }
    )

    error: str
    code: int
    timestamp: str
    request_id: Optional[str] = None
    details: Optional[Any] = None
