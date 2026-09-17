"""Thread-safe in-memory LRU cache with generation invalidation and TTL support."""

from dataclasses import dataclass
import logging
from collections import OrderedDict
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """Configuration for service-layer LRU search cache."""

    enabled: bool = True
    max_entries: int = 1000
    ttl_seconds: float = 300.0


@dataclass
class CacheEntry:
    """Single cache item with access tracking and monotonic expiration."""

    key: Tuple[Any, ...]
    value: Any
    expires_at: float
    created_at: float
    hit_count: int = 0


class LRUCache:
    """Thread-safe LRU cache with TTL expiration and generation isolation.

    Note:
        max_entries imposes an upper bound on the number of cached items in
        memory. It is an item-count bound rather than a strict byte-level memory bound.
        Each entry stores immutable search response payloads.
    """

    def __init__(
        self,
        max_entries: int = 1000,
        ttl_seconds: float = 300.0,
        enabled: bool = True,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.max_entries = max(1, max_entries)
        self.default_ttl = max(0.0, ttl_seconds)
        self.enabled = enabled
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._cache: OrderedDict[Tuple[Any, ...], CacheEntry] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: Tuple[Any, ...]) -> Optional[Any]:
        """Retrieve cached value if present, unexpired, and caching is enabled.

        Locks are held strictly during dictionary operations and never during external
        computation or I/O.
        """
        if not self.enabled:
            return None

        now = self._clock()
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            entry = self._cache[key]
            # Check TTL expiry
            if self.default_ttl > 0 and now >= entry.expires_at:
                del self._cache[key]
                self._misses += 1
                return None

            # Hit: mark as most recently used
            self._cache.move_to_end(key)
            entry.hit_count += 1
            self._hits += 1
            return entry.value

    def set(
        self,
        key: Tuple[Any, ...],
        value: Any,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        """Store value under key with monotonic expiry, evicting oldest if full."""
        if not self.enabled:
            return

        now = self._clock()
        ttl = self.default_ttl if ttl_seconds is None else max(0.0, ttl_seconds)
        expires_at = (now + ttl) if ttl > 0 else float("inf")

        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = CacheEntry(
                    key=key,
                    value=value,
                    expires_at=expires_at,
                    created_at=now,
                    hit_count=self._cache[key].hit_count,
                )
                return

            # Evict least recently used entries if capacity reached
            while len(self._cache) >= self.max_entries:
                self._cache.popitem(last=False)
                self._evictions += 1

            self._cache[key] = CacheEntry(
                key=key,
                value=value,
                expires_at=expires_at,
                created_at=now,
                hit_count=0,
            )

    def invalidate(self) -> None:
        """Clear all entries from cache and log invalidation."""
        with self._lock:
            self._cache.clear()
        logger.info("Search result LRU cache invalidated.")

    def clear(self) -> None:
        """Alias for invalidate."""
        self.invalidate()

    def get_stats(self) -> Dict[str, Any]:
        """Return operational cache statistics."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (
                round((self._hits / total_requests) * 100, 2)
                if total_requests > 0
                else 0.0
            )
            return {
                "enabled": self.enabled,
                "size": len(self._cache),
                "max_entries": self.max_entries,
                "ttl_seconds": self.default_ttl,
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "hit_rate_pct": hit_rate,
            }
