"""End-to-end parser pipeline integrating HTML, text, and links."""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from src.parser import HTMLParser
from src.parser.dedup import ContentDeduplicator
from src.parser.linker import LinkExtractor
from src.parser.text import TextProcessor

logger = logging.getLogger(__name__)


@dataclass
class ParsedDocument:
    """Typed representation of a parsed web document.

    Supports attribute access as well as dictionary subscripting for compatibility.
    """

    url: str
    canonical_url: Optional[str]
    title: str
    description: str
    body: str
    author: Optional[str]
    language: str
    published_at: Optional[str]
    charset: Optional[str]
    tokens: List[str]  # Full token sequence preserving term frequency
    terms: List[str]  # Unique terms for dictionary indexing
    content_hash: str
    links: List[str]
    links_with_priority: List[Tuple[str, int]]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        """Support dictionary-like indexing for compatibility."""
        if hasattr(self, key):
            return getattr(self, key)
        # Compatibility aliases
        if key == "title_terms":
            return [t for t in self.tokens if t in self.title.lower()]
        if key == "body_terms":
            return self.tokens
        if key == "description_terms":
            return [t for t in self.tokens if t in self.description.lower()]
        if key == "all_terms":
            return self.terms
        raise KeyError(f"Key '{key}' not found in ParsedDocument")

    def get(self, key: str, default: Any = None) -> Any:
        """Support dictionary .get() access for compatibility."""
        try:
            return self[key]
        except KeyError:
            return default

    def to_dict(self) -> Dict[str, Any]:
        """Convert to standard dictionary."""
        return {
            "url": self.url,
            "canonical_url": self.canonical_url,
            "title": self.title,
            "description": self.description,
            "body": self.body,
            "author": self.author,
            "language": self.language,
            "published_at": self.published_at,
            "charset": self.charset,
            "tokens": self.tokens,
            "terms": self.terms,
            "content_hash": self.content_hash,
            "links": self.links,
            "links_with_priority": self.links_with_priority,
            "metadata": self.metadata,
        }


class ParserPipeline:
    """Document pipeline: HTML parsing, text processing, dedup, and links."""

    def __init__(
        self,
        language: str = "english",
        max_depth: int = 2,
        same_domain_only: bool = True,
        deduplicator: Optional[ContentDeduplicator] = None,
    ) -> None:
        self.html_parser = HTMLParser()
        self.text_processor = TextProcessor(language=language)
        self.link_extractor = LinkExtractor(
            max_depth=max_depth, same_domain_only=same_domain_only
        )
        self.deduplicator = (
            deduplicator if deduplicator is not None else ContentDeduplicator()
        )

    def process_document(
        self, html: str, url: str, current_depth: int = 0
    ) -> Optional[ParsedDocument]:
        """Process an HTML document.

        Returns ParsedDocument on success, or None on invalid input/duplicate.
        """
        if not html or not html.strip():
            return None

        # 1. Parse HTML
        parsed = self.html_parser.parse(html, url)
        if not parsed:
            return None

        # 2. Check for duplicate content before registering hash
        title = parsed["title"]
        body = parsed["body"]
        doc_hash = self.deduplicator.compute_document_hash(title, body)

        if self.deduplicator.is_duplicate_hash(doc_hash):
            logger.debug(
                f"Duplicate content detected for '{url}' (hash={doc_hash[:12]})"
            )
            return None

        # 3. Process text (tokens preserve term frequency; terms are unique)
        combined_text = f"{title} {parsed['description']} {body}"
        tokens = self.text_processor.process(combined_text)
        terms = self.text_processor.get_terms(combined_text)

        # 4. Extract, filter, and prioritize links
        raw_links = parsed["links"]
        filtered_links = self.link_extractor.extract_and_filter(
            raw_links, url, current_depth=current_depth
        )
        prioritized_links = self.link_extractor.prioritize_links(filtered_links, url)
        links_only = [link for link, _ in prioritized_links]

        # 5. Successfully parsed: now register hash in deduplicator
        self.deduplicator.register_hash(doc_hash)

        return ParsedDocument(
            url=url,
            canonical_url=parsed.get("canonical_url"),
            title=title,
            description=parsed["description"],
            body=body,
            author=parsed.get("author"),
            language=parsed.get("language", "en"),
            published_at=parsed.get("published_at"),
            charset=parsed.get("charset"),
            tokens=tokens,
            terms=terms,
            content_hash=doc_hash,
            links=links_only,
            links_with_priority=prioritized_links,
            metadata=parsed["metadata"],
        )
