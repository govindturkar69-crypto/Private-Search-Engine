"""End-to-end search pipeline integrating crawler, parser, indexer, and search."""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple
from src.crawler import URLFrontier
from src.crawler.fetcher import FetchResult, Fetcher
from src.indexer import SQLiteIndexer
from src.indexer.batch import BatchIndexer
from src.parser.integration import ParsedDocument, ParserPipeline
from src.ranker.search import SearchEngine, SearchResult

logger = logging.getLogger(__name__)


class EndToEndPipeline:
    """Coordinating pipeline for crawl, parse, index, and search operations."""

    def __init__(
        self,
        db_path: str = "data/index.db",
        crawl_delay: float = 0.5,
        max_depth: int = 2,
        same_domain_only: bool = True,
        batch_size: int = 50,
        indexer: Optional[SQLiteIndexer] = None,
        fetcher: Optional[Fetcher] = None,
        parser_pipeline: Optional[ParserPipeline] = None,
        search_engine: Optional[SearchEngine] = None,
    ) -> None:
        self.indexer = indexer or SQLiteIndexer(db_path=db_path)
        self.batch_indexer = BatchIndexer(self.indexer, batch_size=batch_size)
        self.frontier = URLFrontier(crawl_delay=crawl_delay)
        self.fetcher = fetcher or Fetcher()
        self.parser = parser_pipeline or ParserPipeline(
            max_depth=max_depth, same_domain_only=same_domain_only
        )
        self.search_engine = (
            search_engine if search_engine is not None else SearchEngine(self.indexer)
        )

    def add_seed_urls(self, urls: List[str], priority: int = 0) -> int:
        """Add seed URLs to the crawl frontier.

        Returns count of successfully added URLs.
        """
        count = 0
        for u in urls:
            if self.frontier.add_url(u, priority=priority):
                count += 1
        return count

    async def crawl_and_index(
        self,
        max_documents: int = 10,
        timeout: float = 30.0,
        current_depth: int = 0,
    ) -> int:
        """Crawl frontier URLs, parse documents, and index them into SQLite.

        Returns the number of documents successfully indexed.
        """
        indexed_count = 0
        loop = asyncio.get_running_loop()
        start_time = loop.time()

        while indexed_count < max_documents:
            if loop.time() - start_time > timeout:
                logger.warning("Crawl and index operation timed out")
                break

            url = self.frontier.get_next_url()
            if not url:
                if self.frontier.size() == 0:
                    break
                await asyncio.sleep(0.05)
                continue

            try:
                result: FetchResult = await self.fetcher.fetch(url)
                self.frontier.mark_crawled(url)

                if result.status_code != 200 or not result.content:
                    continue

                parsed: Optional[ParsedDocument] = self.parser.process_document(
                    result.content, url, current_depth=current_depth
                )
                if not parsed:
                    continue

                # Add discovered links back to frontier
                for link, prio in parsed.links_with_priority:
                    self.frontier.add_url(link, priority=prio)

                # Add to batch indexer
                self.batch_indexer.add_to_batch(parsed)
                indexed_count += 1

            except Exception as e:
                logger.error(f"Error processing URL {url}: {e}")
                self.frontier.mark_crawled(url)

        # Flush any remaining items in batch indexer
        self.batch_indexer.flush()
        # Recalculate BM25 IDF across corpus
        self.indexer.calculate_idf(recalculate=True)

        return indexed_count

    def search(
        self, query: str, limit: int = 10, offset: int = 0
    ) -> Tuple[List[SearchResult], Optional[str]]:
        """Execute search query through the search engine."""
        return self.search_engine.search(query, limit=limit, offset=offset)

    def get_suggestions(self, prefix: str, limit: int = 5) -> List[str]:
        """Get term suggestions matching prefix."""
        return self.search_engine.get_suggestions(prefix, limit=limit)

    def get_statistics(self) -> Dict[str, Any]:
        """Collect aggregated statistics across all pipeline components."""
        index_stats = self.indexer.get_stats()
        return {
            "index": index_stats,
            "frontier": {
                "queued_urls": self.frontier.size(),
                "crawled_urls": len(self.frontier.crawled),
                "in_flight_urls": len(self.frontier.in_flight),
            },
        }

    def close(self) -> None:
        """Close indexer and flush pending documents."""
        try:
            self.batch_indexer.flush()
        except Exception:
            pass
        self.indexer.close()
