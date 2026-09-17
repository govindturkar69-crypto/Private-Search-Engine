"""Link extraction, filtering, and priority scoring."""

import logging
from typing import List, Set, Tuple
from src.utils.url import extract_domain, is_valid_url, normalize_url

logger = logging.getLogger(__name__)


class LinkExtractor:
    """Extract, filter by domain/depth, and prioritize links from parsed documents."""

    def __init__(
        self,
        max_depth: int = 2,
        same_domain_only: bool = True,
        base_score: int = 10,
        content_bonus: int = 5,
        same_domain_bonus: int = 2,
        navigation_penalty: int = 3,
        archive_penalty: int = 2,
    ) -> None:
        self.max_depth = max_depth
        self.same_domain_only = same_domain_only
        self.base_score = base_score
        self.content_bonus = content_bonus
        self.same_domain_bonus = same_domain_bonus
        self.navigation_penalty = navigation_penalty
        self.archive_penalty = archive_penalty

    def extract_and_filter(
        self, links: List[str], base_url: str, current_depth: int = 0
    ) -> List[str]:
        """Filter links by crawl depth, domain boundary, and validity."""
        if current_depth >= self.max_depth:
            return []

        base_domain = extract_domain(base_url).lower()
        seen: Set[str] = set()
        filtered: List[str] = []

        for link in links:
            if not is_valid_url(link):
                continue

            link_domain = extract_domain(link).lower()
            if self.same_domain_only and link_domain != base_domain:
                continue

            normalized = normalize_url(link, sort_query=False)
            if normalized not in seen:
                seen.add(normalized)
                filtered.append(normalized)

        return filtered

    def prioritize_links(
        self, links: List[str], base_url: str
    ) -> List[Tuple[str, int]]:
        """Compute priority scores for links based on path relevance and domain match.

        Higher integer priority score = higher relevance ranking.
        """
        base_domain = extract_domain(base_url).lower()
        prioritized: List[Tuple[str, int]] = []

        for link in links:
            if not is_valid_url(link):
                continue

            score = self.base_score
            lower_link = link.lower()

            # Content patterns
            if any(
                p in lower_link
                for p in ("/article", "/post", "/blog", "/news", "/docs")
            ):
                score += self.content_bonus

            # Navigation patterns
            if any(
                p in lower_link
                for p in ("/about", "/contact", "/privacy", "/terms", "/login")
            ):
                score -= self.navigation_penalty

            # Archive and pagination patterns
            if any(
                p in lower_link for p in ("/archive", "/tag", "/category", "/page/")
            ):
                score -= self.archive_penalty

            # Same-domain affinity
            link_domain = extract_domain(link).lower()
            if link_domain and link_domain == base_domain:
                score += self.same_domain_bonus

            prioritized.append((link, score))

        # Sort descending by priority score
        prioritized.sort(key=lambda x: x[1], reverse=True)
        return prioritized
