"""Ranking and scoring module for Private Search Engine."""

from dataclasses import dataclass, field
import logging
import re
from typing import Dict, List, Set

logger = logging.getLogger(__name__)

MAX_QUERY_LENGTH = 500
MAX_TERMS = 100
MAX_TERM_LENGTH = 50

# Pattern to extract quoted phrases
# Pattern to extract field filters like author:guido or language:en
RE_FIELD = re.compile(r'(?:^|\s)([\w]+):("([^"]+)"|[^\s]+)')
# Pattern to extract quoted phrases
RE_PHRASE = re.compile(r'"([^"]+)"')
# Pattern for required terms: +word (must start with alphanumeric)
RE_REQUIRED = re.compile(r"(?:^|\s)\+([a-zA-Z0-9_\u00C0-\u017F][\w\-]*)")
# Pattern for excluded terms: -word (must start with alphanumeric)
RE_EXCLUDED = re.compile(r"(?:^|\s)\-([a-zA-Z0-9_\u00C0-\u017F][\w\-]*)")
# Word tokenization pattern
RE_WORD = re.compile(r"[\w\-]+", re.UNICODE)


@dataclass
class ParsedQuery:
    """Structured representation of a parsed search query."""

    raw_query: str
    optional_terms: List[str] = field(default_factory=list)
    required_terms: List[str] = field(default_factory=list)
    excluded_terms: List[str] = field(default_factory=list)
    phrases: List[str] = field(default_factory=list)
    field_filters: Dict[str, str] = field(default_factory=dict)

    def all_positive_terms(self) -> List[str]:
        """Return unique positive search terms from required, optional, and phrases."""
        terms: List[str] = []
        seen: Set[str] = set()

        for t in self.required_terms + self.optional_terms:
            if t not in seen:
                seen.add(t)
                terms.append(t)

        for phrase in self.phrases:
            for word in RE_WORD.findall(phrase.lower()):
                if word not in seen:
                    seen.add(word)
                    terms.append(word)

        return terms

    def is_empty(self) -> bool:
        """Check if parsed query has no search terms or filters."""
        return not (
            self.optional_terms
            or self.required_terms
            or self.excluded_terms
            or self.phrases
            or self.field_filters
        )


class QueryParser:
    """Parser and validator for advanced query syntax."""

    def __init__(
        self,
        max_query_length: int = MAX_QUERY_LENGTH,
        max_terms: int = MAX_TERMS,
        max_term_length: int = MAX_TERM_LENGTH,
    ) -> None:
        self.max_query_length = max_query_length
        self.max_terms = max_terms
        self.max_term_length = max_term_length

    def normalize_term(self, term: str) -> str:
        """Normalize a term: lowercased, stripped of surrounding punctuation."""
        term = term.strip().lower()
        # Strip punctuation and hyphens from edges while keeping internal hyphens
        term = term.strip(".,;:!?\"'()[]{}<>`~#$@%^&*+=|\\/-")
        if len(term) > self.max_term_length:
            term = term[: self.max_term_length]
        return term

    def parse(self, query: str) -> ParsedQuery:
        """Parse raw query string into structured ParsedQuery object."""
        if not query or not query.strip():
            return ParsedQuery(raw_query="")

        # Enforce max query length
        raw_clean = query.strip()
        if len(raw_clean) > self.max_query_length:
            logger.warning(
                f"Query exceeded {self.max_query_length} characters. Truncating."
            )
            raw_clean = raw_clean[: self.max_query_length]

        working_text = raw_clean

        # 1. Extract field filters first (e.g. language:en, author:"John Doe")
        field_filters: Dict[str, str] = {}
        for match in RE_FIELD.finditer(working_text):
            field_name = match.group(1).lower().strip()
            field_val = match.group(3) if match.group(3) else match.group(2)
            if field_name and field_val:
                field_filters[field_name] = field_val.strip("\"'").lower()
        working_text = RE_FIELD.sub(" ", working_text)

        # 2. Extract exact phrases in quotes
        phrases: List[str] = []
        for match in RE_PHRASE.finditer(working_text):
            phrase_content = match.group(1).strip()
            if phrase_content:
                phrases.append(phrase_content.lower())
        working_text = RE_PHRASE.sub(" ", working_text)

        # 3. Extract required terms (+term)
        required_terms: List[str] = []
        for match in RE_REQUIRED.finditer(working_text):
            norm = self.normalize_term(match.group(1))
            if norm and norm not in required_terms:
                required_terms.append(norm)
        working_text = RE_REQUIRED.sub(" ", working_text)

        # 4. Extract excluded terms (-term)
        excluded_terms: List[str] = []
        for match in RE_EXCLUDED.finditer(working_text):
            norm = self.normalize_term(match.group(1))
            if norm and norm not in excluded_terms:
                excluded_terms.append(norm)
        working_text = RE_EXCLUDED.sub(" ", working_text)

        # 5. Remaining words are optional terms
        optional_terms: List[str] = []
        for raw_token in working_text.split():
            norm = self.normalize_term(raw_token)
            if (
                norm
                and norm not in optional_terms
                and norm not in required_terms
                and norm not in excluded_terms
            ):
                optional_terms.append(norm)

        # Enforce max term limits
        total_terms_count = (
            len(required_terms)
            + len(excluded_terms)
            + len(optional_terms)
            + len(phrases)
        )
        if total_terms_count > self.max_terms:
            logger.warning(f"Query terms exceeded {self.max_terms}. Truncating.")
            excess = total_terms_count - self.max_terms
            if excess <= len(optional_terms):
                optional_terms = optional_terms[: len(optional_terms) - excess]
            else:
                excess -= len(optional_terms)
                optional_terms = []
                required_terms = required_terms[: max(0, len(required_terms) - excess)]

        return ParsedQuery(
            raw_query=raw_clean,
            optional_terms=optional_terms,
            required_terms=required_terms,
            excluded_terms=excluded_terms,
            phrases=phrases,
            field_filters=field_filters,
        )


# Import downstream components for convenient top-level access
from src.ranker.snippets import SnippetGenerator  # noqa: E402
from src.ranker.search import SearchResult, SearchEngine  # noqa: E402
from src.ranker.pipeline import EndToEndPipeline  # noqa: E402

__all__ = [
    "ParsedQuery",
    "QueryParser",
    "SnippetGenerator",
    "SearchResult",
    "SearchEngine",
    "EndToEndPipeline",
]
