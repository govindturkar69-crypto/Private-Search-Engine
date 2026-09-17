"""In-memory sliding-window rate limiter and security middleware."""

from collections import defaultdict
from datetime import datetime, timezone
import logging
import time
from typing import Callable, Dict, List, Optional
from fastapi import Request
from fastapi.responses import JSONResponse
from src.api.models import ErrorResponse

logger = logging.getLogger(__name__)

DEFAULT_RATE_LIMIT = 100
DEFAULT_WINDOW_SECONDS = 60.0
MAX_TRACKED_IPS = 10000


class RateLimiter:
    """In-memory sliding-window rate limiter.

    Note on limitations:
    - Process-local only: state is in-memory and not shared across workers.
    - Resets upon server restart.
    - Unsuitable for multi-node deployments without an external store (e.g. Redis).
    """

    def __init__(
        self,
        requests_per_minute: int = DEFAULT_RATE_LIMIT,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        max_tracked_ips: int = MAX_TRACKED_IPS,
        time_func: Optional[Callable[[], float]] = None,
    ) -> None:
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds
        self.max_tracked_ips = max_tracked_ips
        self.time_func = time_func or time.monotonic
        self.requests: Dict[str, List[float]] = defaultdict(list)

    def _cleanup_expired(self, ip: str, now: float) -> None:
        """Prune timestamps older than window for given IP."""
        cutoff = now - self.window_seconds
        if ip in self.requests:
            self.requests[ip] = [ts for ts in self.requests[ip] if ts > cutoff]
            if not self.requests[ip]:
                del self.requests[ip]

    def _evict_stale_buckets(self, now: float) -> None:
        """Evict empty or completely expired IP buckets if map grows too large."""
        if len(self.requests) > self.max_tracked_ips:
            cutoff = now - self.window_seconds
            expired_keys = [
                ip
                for ip, timestamps in self.requests.items()
                if not timestamps or timestamps[-1] <= cutoff
            ]
            for ip in expired_keys:
                self.requests.pop(ip, None)

    def is_allowed(self, ip: str) -> bool:
        """Check if incoming request from IP is within rate limits."""
        now = self.time_func()
        self._cleanup_expired(ip, now)
        self._evict_stale_buckets(now)

        current_count = len(self.requests.get(ip, []))
        if current_count >= self.requests_per_minute:
            return False

        self.requests[ip].append(now)
        return True

    def get_remaining(self, ip: str) -> int:
        """Get number of remaining permitted requests in the current window."""
        now = self.time_func()
        self._cleanup_expired(ip, now)
        current_count = len(self.requests.get(ip, []))
        return max(0, self.requests_per_minute - current_count)

    def get_retry_after(self, ip: str) -> int:
        """Calculate seconds until the oldest request timestamp expires."""
        now = self.time_func()
        timestamps = self.requests.get(ip, [])
        if not timestamps:
            return 0
        oldest = timestamps[0]
        remaining_wait = (oldest + self.window_seconds) - now
        return max(1, int(remaining_wait) + 1)

    def reset(self) -> None:
        """Clear all tracked request timestamps."""
        self.requests.clear()


def get_client_ip(request: Request, trusted_proxies: Optional[List[str]] = None) -> str:
    """Extract client IP safely without blindly trusting spoofable proxy headers.

    If direct request or untrusted peer -> returns request.client.host.
    If direct peer is in trusted_proxies -> parses X-Forwarded-For chain from right
    to left, stepping through trusted intermediate proxies until reaching the first
    untrusted client IP.
    """
    direct_ip = request.client.host if request.client else "127.0.0.1"
    if not trusted_proxies or direct_ip not in trusted_proxies:
        return direct_ip

    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return direct_ip

    ips = [p.strip() for p in forwarded.split(",") if p.strip()]
    if not ips:
        return direct_ip

    for ip in reversed(ips):
        if ip not in trusted_proxies:
            return ip

    return ips[0]


def create_rate_limit_response(
    rate_limiter: RateLimiter, client_ip: str, request_id: Optional[str] = None
) -> JSONResponse:
    """Construct standard HTTP 429 response with Retry-After headers."""
    retry_after = rate_limiter.get_retry_after(client_ip)
    remaining = rate_limiter.get_remaining(client_ip)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = ErrorResponse(
        error="Rate limit exceeded. Please retry later.",
        code=429,
        timestamp=now_iso,
        request_id=request_id,
        details={
            "requests_per_minute": rate_limiter.requests_per_minute,
            "retry_after_seconds": retry_after,
        },
    ).model_dump()

    headers = {
        "Retry-After": str(retry_after),
        "X-RateLimit-Limit": str(rate_limiter.requests_per_minute),
        "X-RateLimit-Remaining": str(remaining),
    }
    if request_id:
        headers["X-Request-ID"] = request_id

    return JSONResponse(status_code=429, content=payload, headers=headers)
