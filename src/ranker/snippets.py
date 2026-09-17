"""Contextual snippet generator with term highlighting and word boundary alignment."""

import logging
import re
from typing import List, Optional, Set

logger = logging.getLogger(__name__)

DEFAULT_SNIPPET_LENGTH = 180
DEFAULT_WINDOW_RADIUS = 80
SENTENCE_SPLIT_REGEX = re.compile(r"(?<=[.!?])\s+")


class SnippetGenerator:
    """Extracts contextual snippets around query terms and highlights matches."""

    def __init__(
        self,
        default_length: int = DEFAULT_SNIPPET_LENGTH,
        window_radius: int = DEFAULT_WINDOW_RADIUS,
    ) -> None:
        self.default_length = default_length
        self.window_radius = window_radius

    def highlight_terms(self, text: str, query_terms: List[str]) -> str:
        """Bold query terms inside text using Markdown bolding (**term**).

        Sorts terms descending by length to prevent partial substring collisions.
        """
        if not text or not query_terms:
            return text

        valid_terms: Set[str] = {
            t.strip() for t in query_terms if t and len(t.strip()) > 0
        }
        if not valid_terms:
            return text

        sorted_terms = sorted(valid_terms, key=len, reverse=True)
        escaped_terms = [re.escape(t) for t in sorted_terms]
        pattern = re.compile(rf"\b({'|'.join(escaped_terms)})\b", re.IGNORECASE)

        return pattern.sub(r"**\1**", text)

    def generate(
        self,
        text: str,
        query_terms: List[str],
        max_length: Optional[int] = None,
        window_radius: Optional[int] = None,
    ) -> str:
        """Generate a contextual snippet from text centered around query terms.

        Snaps to word boundaries and marks boundaries with ellipsis (...).
        """
        if not text or not text.strip():
            return ""

        clean_text = " ".join(text.split())
        target_length = max_length or self.default_length
        radius = window_radius or self.window_radius

        valid_terms = [
            t.strip().lower() for t in query_terms if t and len(t.strip()) > 0
        ]

        # Find first matching term position
        first_match_idx = -1
        matched_term_len = 0

        lower_text = clean_text.lower()
        for term in sorted(valid_terms, key=len, reverse=True):
            # Try whole-word match first
            word_match = re.search(rf"\b{re.escape(term)}\b", lower_text)
            if word_match:
                idx = word_match.start()
                if first_match_idx == -1 or idx < first_match_idx:
                    first_match_idx = idx
                    matched_term_len = len(term)
            else:
                # Substring fallback
                idx = lower_text.find(term)
                if idx != -1:
                    if first_match_idx == -1 or idx < first_match_idx:
                        first_match_idx = idx
                        matched_term_len = len(term)

        # Fallback: if no terms found in text, extract from start
        if first_match_idx == -1:
            if len(clean_text) <= target_length:
                return self.highlight_terms(clean_text, valid_terms)

            # Snap to word boundary near target_length
            cut = target_length
            space_idx = clean_text.rfind(" ", 0, cut)
            if space_idx > target_length // 2:
                cut = space_idx
            raw_snippet = clean_text[:cut].strip() + " ..."
            return self.highlight_terms(raw_snippet, valid_terms)

        # Window calculation
        start = max(0, first_match_idx - radius)
        end = min(len(clean_text), first_match_idx + matched_term_len + radius)

        # Adjust start to word boundary
        if start > 0:
            space_idx = clean_text.find(" ", start)
            if space_idx != -1 and space_idx < first_match_idx:
                start = space_idx + 1

        # Adjust end to word boundary
        if end < len(clean_text):
            space_idx = clean_text.rfind(" ", first_match_idx + matched_term_len, end)
            if space_idx != -1 and space_idx > first_match_idx:
                end = space_idx

        raw_snippet = clean_text[start:end].strip()

        # Add ellipsis
        prefix = "... " if start > 0 else ""
        suffix = " ..." if end < len(clean_text) else ""
        full_snippet = f"{prefix}{raw_snippet}{suffix}"

        return self.highlight_terms(full_snippet, valid_terms)

    def extract_context(self, text: str, term: str, max_sentences: int = 1) -> str:
        """Extract full sentences containing term."""
        if not text or not text.strip() or not term:
            return ""

        clean_text = " ".join(text.split())
        sentences = SENTENCE_SPLIT_REGEX.split(clean_text)
        lower_term = term.strip().lower()

        matching_sentences: List[str] = []
        for s in sentences:
            if re.search(rf"\b{re.escape(lower_term)}\b", s, re.IGNORECASE):
                matching_sentences.append(s.strip())
                if len(matching_sentences) >= max_sentences:
                    break

        if not matching_sentences:
            # Fallback to substring search
            for s in sentences:
                if lower_term in s.lower():
                    matching_sentences.append(s.strip())
                    if len(matching_sentences) >= max_sentences:
                        break

        if not matching_sentences:
            return ""

        result = " ".join(matching_sentences)
        return self.highlight_terms(result, [term])
