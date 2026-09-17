"""HTML content parsing, metadata extraction, and document processing."""

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from src.utils.url import is_valid_url, normalize_url

logger = logging.getLogger(__name__)

# Content limits
MAX_TITLE_CHARS = 200
MAX_DESCRIPTION_CHARS = 500
MAX_BODY_CHARS = 1_048_576  # 1MB in Unicode characters


class HTMLParser:
    """Parse HTML documents, extracting clean text, links, and structured metadata."""

    def __init__(self, base_url: str = "") -> None:
        self.base_url = base_url

    def parse(self, html: str, url: str = "") -> Optional[Dict[str, Any]]:
        """Parse HTML string into structured content dictionary.

        Returns None on empty or invalid input.
        """
        if not html or not html.strip():
            return None

        effective_base = url or self.base_url

        try:
            soup = BeautifulSoup(html, "lxml")

            # Extract title and description before cleaning non-content tags
            title = self._extract_title(soup)
            description = self._extract_description(soup)
            metadata = self._extract_metadata(soup, effective_base)
            links = self._extract_links(soup, effective_base)

            # Extract main body text after stripping non-content tags
            body = self._extract_body(soup)

            return {
                "title": title[:MAX_TITLE_CHARS],
                "description": description[:MAX_DESCRIPTION_CHARS],
                "body": body[:MAX_BODY_CHARS],
                "links": links,
                "metadata": metadata,
                "language": metadata.get("language", "en"),
                "author": metadata.get("author"),
                "published_at": metadata.get("published_at"),
                "charset": metadata.get("charset"),
                "canonical_url": metadata.get("canonical_url"),
            }
        except Exception as e:
            logger.error(f"HTML parsing failed for '{effective_base}': {e}")
            return None

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract title following fallback order: <title> -> og:title -> <h1>."""
        # 1. <title> tag
        title_tag = soup.find("title")
        if title_tag:
            text = title_tag.get_text()
            cleaned = re.sub(r"\s+", " ", text).strip()
            if cleaned:
                return cleaned

        # 2. og:title meta
        for attr in ({"property": "og:title"}, {"name": "og:title"}):
            og_tag = soup.find("meta", attrs=attr)
            if og_tag and og_tag.get("content"):
                cleaned = re.sub(r"\s+", " ", str(og_tag.get("content"))).strip()
                if cleaned:
                    return cleaned

        # 3. First <h1> tag
        h1_tag = soup.find("h1")
        if h1_tag:
            text = h1_tag.get_text()
            cleaned = re.sub(r"\s+", " ", text).strip()
            if cleaned:
                return cleaned

        return ""

    def _extract_description(self, soup: BeautifulSoup) -> str:
        """Extract description: og:description -> meta[description]."""
        # 1. og:description
        for attr in ({"property": "og:description"}, {"name": "og:description"}):
            og_tag = soup.find("meta", attrs=attr)
            if og_tag and og_tag.get("content"):
                cleaned = re.sub(r"\s+", " ", str(og_tag.get("content"))).strip()
                if cleaned:
                    return cleaned

        # 2. meta[name="description"]
        desc_pattern = re.compile(r"^description$", re.I)
        meta_tag = soup.find("meta", attrs={"name": desc_pattern})
        if meta_tag and meta_tag.get("content"):
            cleaned = re.sub(r"\s+", " ", str(meta_tag.get("content"))).strip()
            if cleaned:
                return cleaned

        return ""

    def _extract_body(self, soup: BeautifulSoup) -> str:
        """Extract main body text prioritizing <article> -> <main> -> <body>."""
        # Create a copy of the soup or clean non-content elements in place
        for non_content in soup(
            ["script", "style", "noscript", "nav", "footer", "template", "svg", "aside"]
        ):
            non_content.decompose()

        # Preferred hierarchy
        target = soup.find("article") or soup.find("main") or soup.find("body") or soup
        text = target.get_text(separator=" ")
        return re.sub(r"\s+", " ", text).strip()

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Extract, resolve, and normalize hyperlinks rejecting unsupported schemes."""
        seen: set = set()
        links: List[str] = []

        for a_tag in soup.find_all("a", href=True):
            raw_href = str(a_tag.get("href", "")).strip()
            if not raw_href:
                continue

            # Reject common non-http schemes upfront
            lower_href = raw_href.lower()
            if lower_href.startswith(
                ("javascript:", "mailto:", "tel:", "data:", "file:", "ftp:")
            ):
                continue

            try:
                resolved = urljoin(base_url, raw_href)
                # Strip fragment
                resolved = resolved.split("#", 1)[0]
                if not is_valid_url(resolved):
                    continue

                normalized = normalize_url(resolved, sort_query=False)
                if normalized not in seen:
                    seen.add(normalized)
                    links.append(normalized)
            except Exception as e:
                logger.debug(f"Link resolution error for '{raw_href}': {e}")

        return links

    def _extract_metadata(self, soup: BeautifulSoup, base_url: str) -> Dict[str, Any]:
        """Extract author, language, publication date, charset, and canonical URL."""
        metadata: Dict[str, Any] = {}

        try:
            # 1. Author
            for attr in (
                {"name": "author"},
                {"property": "article:author"},
                {"name": "twitter:creator"},
            ):
                tag = soup.find("meta", attrs=attr)
                if tag and tag.get("content"):
                    metadata["author"] = str(tag.get("content")).strip()
                    break

            # 2. Language
            html_tag = soup.find("html")
            if html_tag and html_tag.get("lang"):
                metadata["language"] = str(html_tag.get("lang")).strip().lower()
            else:
                lang_meta = soup.find(
                    "meta",
                    attrs={"http-equiv": re.compile(r"^content-language$", re.I)},
                )
                if lang_meta and lang_meta.get("content"):
                    metadata["language"] = str(lang_meta.get("content")).strip().lower()
                else:
                    metadata["language"] = "en"

            # 3. Publication Date (deterministic fallback order)
            published_at = None
            # 3a. article:published_time
            dt_tag = soup.find("meta", attrs={"property": "article:published_time"})
            if dt_tag and dt_tag.get("content"):
                published_at = str(dt_tag.get("content")).strip()

            # 3b. datePublished
            if not published_at:
                for attr in ({"itemprop": "datePublished"}, {"name": "datePublished"}):
                    dt_tag = soup.find("meta", attrs=attr)
                    if dt_tag and dt_tag.get("content"):
                        published_at = str(dt_tag.get("content")).strip()
                        break

            # 3c. <time datetime="...">
            if not published_at:
                time_tag = soup.find("time", attrs={"datetime": True})
                if time_tag and time_tag.get("datetime"):
                    published_at = str(time_tag.get("datetime")).strip()

            # 3d. Common publication date meta names
            if not published_at:
                for name in ("pubdate", "publishdate", "date", "DC.date.issued"):
                    dt_tag = soup.find(
                        "meta", attrs={"name": re.compile(f"^{name}$", re.I)}
                    )
                    if dt_tag and dt_tag.get("content"):
                        published_at = str(dt_tag.get("content")).strip()
                        break

            if published_at:
                metadata["published_at"] = published_at

            # 4. Charset
            charset_tag = soup.find("meta", attrs={"charset": True})
            if charset_tag and charset_tag.get("charset"):
                metadata["charset"] = str(charset_tag.get("charset")).strip().lower()
            else:
                ct_tag = soup.find(
                    "meta", attrs={"http-equiv": re.compile(r"^content-type$", re.I)}
                )
                if ct_tag and ct_tag.get("content"):
                    match = re.search(
                        r"charset=([^\s;]+)", str(ct_tag.get("content")), re.I
                    )
                    if match:
                        metadata["charset"] = match.group(1).strip().lower()

            # 5. Canonical URL
            canonical_tag = soup.find(
                "link", attrs={"rel": lambda x: x and "canonical" in x.lower()}
            )
            if canonical_tag and canonical_tag.get("href"):
                raw_can = str(canonical_tag.get("href")).strip()
                try:
                    can_resolved = urljoin(base_url, raw_can).split("#", 1)[0]
                    if is_valid_url(can_resolved):
                        metadata["canonical_url"] = normalize_url(
                            can_resolved, sort_query=False
                        )
                except Exception:
                    pass

        except Exception as e:
            logger.debug(f"Metadata extraction error: {e}")

        return metadata


from src.parser.dedup import ContentDeduplicator  # noqa: E402
from src.parser.integration import ParsedDocument, ParserPipeline  # noqa: E402
from src.parser.linker import LinkExtractor  # noqa: E402
from src.parser.text import TextProcessor  # noqa: E402

__all__ = [
    "HTMLParser",
    "TextProcessor",
    "LinkExtractor",
    "ContentDeduplicator",
    "ParserPipeline",
    "ParsedDocument",
]
