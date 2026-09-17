"""Crawl manager coordinating background crawl execution, states, and telemetry."""

import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import Dict, Optional
from urllib.parse import urlparse
import uuid

from src.api.admin_models import (
    CrawlPriority,
    CrawlRequest,
    CrawlResponse,
    CrawlStatus,
)
from src.crawler import URLFrontier
from src.crawler.fetcher import Fetcher
from src.crawler.robots import RobotsTxtParser
from src.indexer import SQLiteIndexer
from src.indexer.batch import BatchIndexer
from src.parser.integration import ParserPipeline
from src.utils.url import extract_domain, is_valid_url

logger = logging.getLogger(__name__)


class CrawlManager:
    """Process-local crawl coordinator managing background crawling tasks."""

    def __init__(
        self,
        indexer: Optional[SQLiteIndexer] = None,
        fetcher: Optional[Fetcher] = None,
    ) -> None:
        self.indexer = indexer
        self.fetcher = fetcher or Fetcher()
        self._lock = asyncio.Lock()
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Unpaused by default
        self._stop_event = asyncio.Event()

        self._status = CrawlStatus.IDLE
        self._crawl_id: str = "crawl-idle"
        self._start_time: Optional[str] = None
        self._documents_crawled = 0
        self._documents_indexed = 0
        self._errors = 0
        self._current_url: Optional[str] = None
        self._max_documents = 1000
        self._frontier: Optional[URLFrontier] = None
        self._active_task: Optional[asyncio.Task] = None
        self._robots_cache: Dict[str, RobotsTxtParser] = {}

    def set_indexer(self, indexer: SQLiteIndexer) -> None:
        """Update the underlying SQLiteIndexer instance."""
        self.indexer = indexer

    def set_fetcher(self, fetcher: Fetcher) -> None:
        """Update the underlying Fetcher instance."""
        self.fetcher = fetcher

    @property
    def status(self) -> CrawlStatus:
        """Get current crawl status."""
        return self._status

    def validate_seed_url_ssrf(self, url: str) -> bool:
        """Defense-in-depth SSRF pre-validation for seed URLs."""
        if not is_valid_url(url):
            return False
        return self.fetcher._is_safe_url(url)

    async def start_crawl(
        self,
        request: CrawlRequest,
        fetcher: Optional[Fetcher] = None,
        batch_indexer: Optional[BatchIndexer] = None,
    ) -> CrawlResponse:
        """Initiate a new crawl job in a background task."""
        async with self._lock:
            # Check state transitions: idle, stopped, or error can start
            if self._status in (CrawlStatus.RUNNING, CrawlStatus.PAUSED):
                raise ValueError("A crawl job is already in progress.")

            # Validate seed URLs against SSRF
            for seed in request.seed_urls:
                if not self.validate_seed_url_ssrf(seed):
                    raise ValueError(
                        f"Seed URL '{seed}' failed SSRF safety validation."
                    )

            if not self.indexer and not batch_indexer:
                raise ValueError("Database indexer is not configured or available.")

            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            self._crawl_id = f"crawl-{int(time.time())}-{uuid.uuid4().hex[:6]}"
            self._start_time = now_iso
            self._documents_crawled = 0
            self._documents_indexed = 0
            self._errors = 0
            self._current_url = None
            self._max_documents = request.max_documents
            self._robots_cache.clear()

            priority_val = 1
            if request.priority == CrawlPriority.HIGH:
                priority_val = 0
            elif request.priority == CrawlPriority.LOW:
                priority_val = 2

            self._frontier = URLFrontier(crawl_delay=1.0)
            for seed in request.seed_urls:
                self._frontier.add_url(seed, priority=priority_val)

            self._stop_event.clear()
            self._pause_event.set()
            self._status = CrawlStatus.RUNNING

            self._active_task = asyncio.create_task(
                self._run_crawl(
                    request=request,
                    fetcher=fetcher or self.fetcher,
                    batch_indexer=batch_indexer,
                )
            )

            logger.info(
                f"Started crawl {self._crawl_id} with {len(request.seed_urls)} seeds"
            )
            return self.get_status()

    async def pause_crawl(self) -> CrawlResponse:
        """Cooperatively pause an active crawl job."""
        async with self._lock:
            if self._status != CrawlStatus.RUNNING:
                raise ValueError(
                    f"Cannot pause crawl: current status is '{self._status.value}'."
                )
            self._pause_event.clear()
            self._status = CrawlStatus.PAUSED
            logger.info(f"Crawl {self._crawl_id} paused.")
            return self.get_status()

    async def resume_crawl(self) -> CrawlResponse:
        """Resume a paused crawl job."""
        async with self._lock:
            if self._status != CrawlStatus.PAUSED:
                raise ValueError(
                    f"Cannot resume crawl: current status is '{self._status.value}'."
                )
            self._pause_event.set()
            self._status = CrawlStatus.RUNNING
            logger.info(f"Crawl {self._crawl_id} resumed.")
            return self.get_status()

    async def stop_crawl(self) -> CrawlResponse:
        """Cooperatively stop and finalize the crawl job."""
        async with self._lock:
            if self._status not in (CrawlStatus.RUNNING, CrawlStatus.PAUSED):
                raise ValueError(
                    f"Cannot stop crawl: current status is '{self._status.value}'."
                )
            self._stop_event.set()
            self._pause_event.set()  # Unblock in case waiting on pause
            self._status = CrawlStatus.STOPPED
            self._current_url = None
            logger.info(f"Crawl {self._crawl_id} stopped.")
            return self.get_status()

    def get_status(self) -> CrawlResponse:
        """Return the current crawl state and telemetry."""
        progress = 0
        if self._max_documents > 0:
            progress = min(
                100,
                int((self._documents_crawled / self._max_documents) * 100),
            )

        urls_queued = self._frontier.size() if self._frontier else 0

        return CrawlResponse(
            crawl_id=self._crawl_id,
            status=self._status,
            start_time=self._start_time,
            documents_crawled=self._documents_crawled,
            documents_indexed=self._documents_indexed,
            errors=self._errors,
            urls_queued=urls_queued,
            current_url=self._current_url,
            progress_percent=progress,
        )

    async def _run_crawl(
        self,
        request: CrawlRequest,
        fetcher: Optional[Fetcher] = None,
        batch_indexer: Optional[BatchIndexer] = None,
    ) -> None:
        """Background crawl execution loop."""
        active_fetcher = fetcher or Fetcher()
        active_batch_indexer = (
            batch_indexer
            if batch_indexer is not None
            else (BatchIndexer(self.indexer) if self.indexer else None)
        )
        pipeline = ParserPipeline(max_depth=request.max_depth)

        try:
            while (
                not self._stop_event.is_set()
                and self._documents_crawled < self._max_documents
            ):
                # Cooperative pause check
                await self._pause_event.wait()
                if self._stop_event.is_set():
                    break

                assert self._frontier is not None
                url = self._frontier.get_next_url()
                if not url:
                    # Queue exhausted or waiting on delay
                    if self._frontier.size() == 0:
                        break
                    await asyncio.sleep(0.1)
                    continue

                self._current_url = url

                # Robots.txt politeness check
                domain = extract_domain(url)
                if domain not in self._robots_cache:
                    robots_parser = RobotsTxtParser()
                    robots_url = f"https://{domain}/robots.txt"
                    try:
                        robots_res = await active_fetcher.fetch(robots_url)
                        if robots_res.status_code == 200 and robots_res.content:
                            robots_parser.parse(robots_res.content)
                    except Exception:
                        pass
                    self._robots_cache[domain] = robots_parser

                path = urlparse(url).path or "/"
                allowed = self._robots_cache[domain].can_fetch(
                    active_fetcher.user_agent, path
                )
                if not allowed:
                    logger.info(f"Disallowed by robots.txt: {url}")
                    self._frontier.mark_crawled(url)
                    continue

                # Fetch document
                try:
                    fetch_result = await active_fetcher.fetch(url)
                except Exception as e:
                    logger.warning(f"Error fetching {url}: {e}")
                    self._errors += 1
                    self._frontier.mark_crawled(url)
                    continue

                if fetch_result.status_code != 200 or not fetch_result.content:
                    self._errors += 1
                    self._frontier.mark_crawled(url)
                    continue

                # Parse document
                try:
                    parsed_doc = pipeline.process_document(
                        html=fetch_result.content,
                        url=fetch_result.final_url,
                    )
                    if parsed_doc:
                        # Extract and queue discovered links
                        for link in parsed_doc.links:
                            self._frontier.add_url(link, priority=1)

                        if active_batch_indexer:
                            active_batch_indexer.add_to_batch(parsed_doc)
                            self._documents_indexed += 1
                    self._documents_crawled += 1
                except Exception as e:
                    logger.error(f"Error parsing document {url}: {e}")
                    self._errors += 1

                self._frontier.mark_crawled(url)
                await asyncio.sleep(0.01)

        except Exception as e:
            logger.error(f"Fatal error in crawl loop: {e}", exc_info=True)
            self._status = CrawlStatus.ERROR
        finally:
            if active_batch_indexer:
                try:
                    active_batch_indexer.flush(recalculate_idf=True)
                except Exception as e:
                    logger.error(f"Error during final batch flush: {e}")

            self._current_url = None
            if self._status != CrawlStatus.ERROR:
                self._status = CrawlStatus.STOPPED
            logger.info(
                f"Crawl {self._crawl_id} finished. "
                f"Crawled: {self._documents_crawled}, "
                f"Indexed: {self._documents_indexed}"
            )
