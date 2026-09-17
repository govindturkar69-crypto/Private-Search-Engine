"""Crawler module for Private Search Engine."""

import heapq
import logging
import time
from typing import Dict, List, Optional, Set, Tuple
from src.crawler.fetcher import FetchResult, Fetcher
from src.crawler.robots import RobotsTxtParser
from src.utils.url import extract_domain, is_valid_url, normalize_url

logger = logging.getLogger(__name__)

__all__ = ["URLFrontier", "Fetcher", "FetchResult", "RobotsTxtParser"]


class URLFrontier:
    """Priority queue for URLs with per-domain politeness and normalization."""

    def __init__(self, crawl_delay: float = 1.0) -> None:
        self.crawl_delay = crawl_delay
        self.queue: List[Tuple[int, int, str]] = []  # (priority, counter, url)
        self.queued: Set[str] = set()
        self.in_flight: Set[str] = set()
        self.crawled: Set[str] = set()
        self.domain_state: Dict[str, float] = {}  # domain -> last crawl monotonic time
        self.priority_counter = 0

    @property
    def visited(self) -> Set[str]:
        """Return set of all visited or in-progress URLs."""
        return self.crawled | self.in_flight

    def add_url(self, url: str, priority: int = 0) -> bool:
        """Add a URL to the frontier if not already queued, in flight, or crawled."""
        if not is_valid_url(url):
            return False

        normalized = normalize_url(url)
        if (
            normalized in self.queued
            or normalized in self.in_flight
            or normalized in self.crawled
        ):
            return False

        self.priority_counter += 1
        heapq.heappush(self.queue, (priority, self.priority_counter, normalized))
        self.queued.add(normalized)
        logger.debug(f"Frontier added: {normalized} (priority={priority})")
        return True

    def get_next_url(self) -> Optional[str]:
        """Retrieve the next ready URL respecting per-domain crawl delays.

        Avoids busy-wait spinning by checking ready domains and deferring
        cooling domains.
        """
        if not self.queue:
            return None

        now = time.monotonic()
        deferred: List[Tuple[int, int, str]] = []
        selected_url: Optional[str] = None

        while self.queue:
            item = heapq.heappop(self.queue)
            priority, counter, url = item
            domain = extract_domain(url)

            last_crawl = self.domain_state.get(domain)
            if last_crawl is not None and (now - last_crawl) < self.crawl_delay:
                deferred.append(item)
            else:
                selected_url = url
                self.queued.discard(selected_url)
                self.in_flight.add(selected_url)
                break

        # Restore deferred URLs back into heap
        for item in deferred:
            heapq.heappush(self.queue, item)

        return selected_url

    def mark_crawled(self, url: str) -> None:
        """Mark URL as crawled and update domain politeness timestamp."""
        normalized = normalize_url(url)
        self.in_flight.discard(normalized)
        self.queued.discard(normalized)
        self.crawled.add(normalized)
        domain = extract_domain(normalized)
        self.domain_state[domain] = time.monotonic()
        logger.debug(f"Frontier marked crawled: {normalized}")

    def size(self) -> int:
        """Return the number of URLs currently waiting in queue."""
        return len(self.queue)
