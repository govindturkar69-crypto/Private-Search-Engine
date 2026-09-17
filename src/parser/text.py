"""Text normalization, tokenization, stop-word filtering, and stemming."""

import logging
import re
from typing import List, Set
from nltk.stem.porter import PorterStemmer

logger = logging.getLogger(__name__)

# Bundled fallback English stop-words to ensure 100% offline operation
BUNDLED_STOPWORDS: Set[str] = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "aren't",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can",
    "cannot",
    "could",
    "couldn't",
    "did",
    "didn't",
    "do",
    "does",
    "doesn't",
    "doing",
    "don't",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "hadn't",
    "has",
    "hasn't",
    "have",
    "haven't",
    "having",
    "he",
    "he'd",
    "he'll",
    "he's",
    "her",
    "here",
    "here's",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "how's",
    "i",
    "i'd",
    "i'll",
    "i'm",
    "i've",
    "if",
    "in",
    "into",
    "is",
    "isn't",
    "it",
    "it's",
    "its",
    "itself",
    "let's",
    "me",
    "more",
    "most",
    "mustn't",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "ought",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "shan't",
    "she",
    "she'd",
    "she'll",
    "she's",
    "should",
    "shouldn't",
    "so",
    "some",
    "such",
    "than",
    "that",
    "that's",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "there's",
    "these",
    "they",
    "they'd",
    "they'll",
    "they're",
    "they've",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "wasn't",
    "we",
    "we'd",
    "we'll",
    "we're",
    "we've",
    "were",
    "weren't",
    "what",
    "what's",
    "when",
    "when's",
    "where",
    "where's",
    "which",
    "while",
    "who",
    "who's",
    "whom",
    "why",
    "why's",
    "with",
    "won't",
    "would",
    "wouldn't",
    "you",
    "you'd",
    "you'll",
    "you're",
    "you've",
    "your",
    "yours",
    "yourself",
    "yourselves",
    # Common web noise tokens
    "http",
    "https",
    "www",
    "com",
    "org",
    "net",
    "html",
    "php",
    "page",
    "click",
    "read",
    "article",
    "post",
    "blog",
}


def _regex_tokenize(text: str) -> List[str]:
    """Deterministic regex tokenizer preserving words, hyphens, and apostrophes."""
    # Match sequences of Unicode word chars joined by hyphens/apostrophes
    return re.findall(r"\b[\w]+(?:['’\-][\w]+)*\b", text, flags=re.UNICODE)


class TextProcessor:
    """Offline-resilient text processor for tokenization, stop-words, and stemming."""

    def __init__(self, language: str = "english") -> None:
        self.language = language
        self.stemmer = PorterStemmer()
        self.stop_words: Set[str] = set(BUNDLED_STOPWORDS)

        # Attempt to augment with NLTK stopwords if already present on disk
        try:
            from nltk.corpus import stopwords

            nltk_words = stopwords.words(language)
            self.stop_words.update(w.lower() for w in nltk_words)
        except Exception:
            logger.debug(
                "NLTK stopwords corpus unavailable; using bundled stop-word set."
            )

    def tokenize(self, text: str) -> List[str]:
        """Normalize whitespace, lowercase, remove URLs, and tokenize text."""
        if not text:
            return []

        # Convert to lowercase
        text = text.lower()

        # Remove URLs safely
        text = re.sub(r"https?://\S+", " ", text)

        # Try NLTK word_tokenize if punkt is available;
        # otherwise use deterministic regex
        try:
            from nltk.tokenize import word_tokenize

            raw_tokens = word_tokenize(text)
            # Filter tokens to keep word characters
            tokens: List[str] = []
            for t in raw_tokens:
                # Strip leading/trailing punctuation from token
                cleaned = re.sub(r"^[^\w]+|[^\w]+$", "", t, flags=re.UNICODE)
                if cleaned:
                    tokens.append(cleaned)
            return tokens
        except Exception:
            return _regex_tokenize(text)

    def filter_stopwords(self, tokens: List[str]) -> List[str]:
        """Filter stop-words, short tokens (<3 chars), and pure numeric tokens.

        Preserves token sequence and repeated terms for indexing frequency.
        """
        filtered: List[str] = []
        for token in tokens:
            # Length filter: minimum 3 characters
            if len(token) < 3:
                continue

            # Numeric filter: skip pure numbers
            if token.isdigit():
                continue

            # Stop-words filter
            if token in self.stop_words:
                continue

            filtered.append(token)
        return filtered

    def stem(self, tokens: List[str]) -> List[str]:
        """Apply Porter stemming to token sequence while preserving order."""
        return [self.stemmer.stem(token) for token in tokens]

    def process(self, text: str) -> List[str]:
        """Execute complete linguistic pipeline: tokenize -> filter -> stem.

        Preserves repeated terms so downstream BM25 ranker can calculate term frequency.
        """
        tokens = self.tokenize(text)
        filtered = self.filter_stopwords(tokens)
        return self.stem(filtered)

    def get_terms(self, text: str) -> List[str]:
        """Extract unique terms from text while preserving discovery order."""
        seen: Set[str] = set()
        unique_terms: List[str] = []
        for term in self.process(text):
            if term not in seen:
                seen.add(term)
                unique_terms.append(term)
        return unique_terms
