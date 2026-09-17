"""Search Engine REST API package."""

API_VERSION = "1.0.0"

from src.api.models import (  # noqa: E402
    ErrorResponse,
    HealthResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    StatsResponse,
    SuggestRequest,
    SuggestResponse,
)
from src.api.middleware import RateLimiter, get_client_ip  # noqa: E402

__all__ = [
    "API_VERSION",
    "SearchRequest",
    "SearchResultItem",
    "SearchResponse",
    "SuggestRequest",
    "SuggestResponse",
    "StatsResponse",
    "HealthResponse",
    "ErrorResponse",
    "RateLimiter",
    "get_client_ip",
]
