"""Search execution engine with BM25 ranking, filtering, and snippets."""

from dataclasses import dataclass, field
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from src.indexer import SQLiteIndexer
from src.indexer.tfidf import BM25Ranker
from src.parser.text import TextProcessor
from src.ranker import ParsedQuery, QueryParser
from src.ranker.snippets import SnippetGenerator

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Individual ranked and enriched search result."""

    doc_id: int
    url: str
    title: str
    description: str
    snippet: str
    score: float
    relevance_score: int  # 0 to 100 percentage
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert search result to dictionary representation."""
        return {
            "doc_id": self.doc_id,
            "url": self.url,
            "title": self.title,
            "description": self.description,
            "snippet": self.snippet,
            "score": self.score,
            "relevance_score": self.relevance_score,
            "metadata": self.metadata,
        }


class SearchEngine:
    """High-level search engine coordinating parsing, BM25 ranking, and snippets."""

    def __init__(
        self,
        indexer: SQLiteIndexer,
        ranker: Optional[BM25Ranker] = None,
        snippet_generator: Optional[SnippetGenerator] = None,
        query_parser: Optional[QueryParser] = None,
        text_processor: Optional[TextProcessor] = None,
    ) -> None:
        self.indexer = indexer
        self.ranker = ranker if ranker is not None else BM25Ranker(indexer)
        self.snippet_generator = (
            snippet_generator if snippet_generator is not None else SnippetGenerator()
        )
        self.query_parser = query_parser if query_parser is not None else QueryParser()
        self.text_processor = (
            text_processor if text_processor is not None else TextProcessor()
        )

    def search_with_total(
        self, query: str, limit: int = 10, offset: int = 0
    ) -> Tuple[List[SearchResult], int, Optional[str]]:
        """Execute a search query with full parsing, ranking, and post-filtering.

        Args:
            query: Raw query string.
            limit: Max results to return (1-100).
            offset: Result offset for pagination.

        Returns:
            Tuple of (list of SearchResult, total_matching_count, error_message).
        """
        if not query or not query.strip():
            return [], 0, None

        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        try:
            parsed = self.query_parser.parse(query)
        except Exception as e:
            logger.error(f"Failed to parse query '{query}': {e}")
            return [], 0, f"Invalid query syntax: {e}"

        if parsed.is_empty():
            return [], 0, None

        search_terms = parsed.all_positive_terms()

        # Step 1: Candidate retrieval via BM25
        candidate_docs: List[Tuple[int, float]] = []
        if search_terms:
            # Expand with stemmed/processed variants to match inverted index vocabulary
            lookup_terms: List[str] = []
            seen_terms: Set[str] = set()
            for term in search_terms:
                if term not in seen_terms:
                    seen_terms.add(term)
                    lookup_terms.append(term)
                stemmed_tokens = self.text_processor.process(term)
                for st in stemmed_tokens:
                    if st not in seen_terms:
                        seen_terms.add(st)
                        lookup_terms.append(st)

            # Retrieve wide candidate pool for post-filtering
            candidate_docs = self.ranker.rank_documents(
                lookup_terms, limit=max(limit * 5, 100)
            )
        elif parsed.field_filters:
            # Query has only field filters (e.g. language:en)
            assert self.indexer.connection is not None
            cur = self.indexer.connection.execute(
                "SELECT doc_id FROM documents LIMIT 200"
            )
            candidate_docs = [(int(row[0]), 1.0) for row in cur.fetchall()]
        else:
            # Query with only excluded terms or unsupported tokens
            return [], 0, None

        if not candidate_docs:
            return [], 0, None

        # Step 2: Post-filtering (required, excluded, phrases, field filters)
        candidate_ids = [doc_id for doc_id, _ in candidate_docs]
        if hasattr(self.indexer, "get_documents_by_ids"):
            docs_map = self.indexer.get_documents_by_ids(candidate_ids)
        else:
            docs_map = {}

        filtered_candidates: List[Tuple[Dict[str, Any], float]] = []
        for doc_id, score in candidate_docs:
            doc = docs_map.get(doc_id)
            if not doc:
                doc = self.indexer.get_document(doc_id)
            if not doc:
                continue

            if self._matches_filters(doc, parsed):
                filtered_candidates.append((doc, score))

        if not filtered_candidates:
            return [], 0, None

        total_available = len(filtered_candidates)

        # Step 3: Relevance score normalization (0-100 percentage relative to top)
        top_score = filtered_candidates[0][1]
        end_idx = offset + limit
        paginated = filtered_candidates[offset:end_idx]

        results: List[SearchResult] = []
        for doc, raw_score in paginated:
            if top_score > 0:
                rel_score = int(round((raw_score / top_score) * 100))
                rel_score = max(0, min(100, rel_score))
            else:
                rel_score = 0

            # Content for snippet generation
            content_text = doc.get("body") or doc.get("description") or ""
            snippet = self.snippet_generator.generate(
                content_text, query_terms=search_terms
            )

            results.append(
                SearchResult(
                    doc_id=doc["doc_id"],
                    url=doc["url"],
                    title=doc.get("title") or "Untitled",
                    description=doc.get("description") or "",
                    snippet=snippet,
                    score=round(raw_score, 4),
                    relevance_score=rel_score,
                    metadata={
                        "author": doc.get("author"),
                        "language": doc.get("language"),
                        "published_at": doc.get("published_at"),
                        "content_hash": doc.get("content_hash"),
                        "document_length": doc.get("document_length"),
                    },
                )
            )

        return results, total_available, None

    def search(
        self, query: str, limit: int = 10, offset: int = 0
    ) -> Tuple[List[SearchResult], Optional[str]]:
        """Execute a search query returning (results, error_message)."""
        results, _, err = self.search_with_total(query, limit=limit, offset=offset)
        return results, err

    def _matches_filters(self, doc: Dict[str, Any], parsed: ParsedQuery) -> bool:
        """Evaluate if document satisfies filters (required, excluded, phrases)."""
        title = (doc.get("title") or "").lower()
        body = (doc.get("body") or "").lower()
        desc = (doc.get("description") or "").lower()
        full_text = f"{title} {desc} {body}"

        # 1. Required terms: must all be present
        for term in parsed.required_terms:
            if not self._term_in_text(term, full_text):
                return False

        # 2. Excluded terms: must none be present
        for term in parsed.excluded_terms:
            if self._term_in_text(term, full_text):
                return False

        # 3. Exact phrases: must all appear as exact substring
        for phrase in parsed.phrases:
            if phrase not in full_text:
                return False

        # 4. Field filters: match against document metadata attributes
        for field_name, expected_val in parsed.field_filters.items():
            if field_name in ("lang", "language"):
                doc_lang = (doc.get("language") or "").lower()
                if doc_lang != expected_val:
                    return False
            elif field_name == "author":
                doc_author = (doc.get("author") or "").lower()
                if expected_val not in doc_author:
                    return False
            elif field_name in ("url", "domain"):
                doc_url = (doc.get("url") or "").lower()
                if expected_val not in doc_url:
                    return False
            elif field_name == "title":
                if expected_val not in title:
                    return False
            elif field_name in doc:
                val_str = str(doc.get(field_name) or "").lower()
                if expected_val not in val_str:
                    return False

        return True

    def _term_in_text(self, term: str, text: str) -> bool:
        """Check if term or stemmed variant matches inside text."""
        pattern = rf"\b{re.escape(term)}\b"
        if re.search(pattern, text, re.IGNORECASE):
            return True
        if term.lower() in text.lower():
            return True
        # Check stemmed variants
        stemmed_tokens = self.text_processor.process(term)
        for st in stemmed_tokens:
            if re.search(rf"\b{re.escape(st)}\b", text, re.IGNORECASE) or st in text:
                return True
        return False

    def get_suggestions(self, prefix: str, limit: int = 5) -> List[str]:
        """Retrieve autocomplete search suggestions matching term prefix.

        Ordered by collection frequency and document frequency.
        """
        if not prefix or not prefix.strip():
            return []

        clean_prefix = prefix.strip().lower()
        limit = max(1, min(limit, 50))

        if self.indexer.connection is None:
            return []

        cur = self.indexer.connection.execute(
            """
            SELECT term FROM terms
            WHERE term LIKE ?
            ORDER BY collection_frequency DESC, document_frequency DESC
            LIMIT ?
            """,
            (f"{clean_prefix}%", limit),
        )
        return [str(row[0]) for row in cur.fetchall()]
