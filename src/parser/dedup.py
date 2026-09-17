"""Content deduplication using deterministic SHA-256 fingerprinting."""

import hashlib
import logging
import re
from typing import Any, Dict, Set

logger = logging.getLogger(__name__)


def normalize_for_hash(text: str) -> str:
    """Normalize text whitespace and lowercase for deterministic fingerprinting."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip().lower()


class ContentDeduplicator:
    """In-memory content deduplicator using SHA-256 fingerprinting.

    NOTE: This implementation is process-local and non-persistent for Phase 3.
    Persistent database-backed deduplication will be integrated in Phase 4.
    """

    def __init__(self, hash_algorithm: str = "sha256") -> None:
        self.hash_algorithm = hash_algorithm
        self.seen_hashes: Set[str] = set()

    def compute_hash(self, content: str) -> str:
        """Compute cryptographic hash of arbitrary string content."""
        if not content:
            return ""
        if self.hash_algorithm == "md5":
            # MD5 is used strictly for non-cryptographic content fingerprinting
            return hashlib.md5(
                content.encode("utf-8"), usedforsecurity=False
            ).hexdigest()
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def compute_document_hash(self, title: str, body: str) -> str:
        """Compute document hash using field normalization and separator."""
        norm_title = normalize_for_hash(title)
        norm_body = normalize_for_hash(body)
        payload = f"{norm_title}\n---BODY---\n{norm_body}"
        return self.compute_hash(payload)

    def is_duplicate(self, content: str, register: bool = False) -> bool:
        """Check if raw content is a duplicate. Optionally registers the hash."""
        content_hash = self.compute_hash(content)
        if content_hash in self.seen_hashes:
            return True
        if register:
            self.seen_hashes.add(content_hash)
        return False

    def is_duplicate_hash(self, content_hash: str) -> bool:
        """Check if a computed hash exists in seen hashes without registering it."""
        return content_hash in self.seen_hashes

    def register_hash(self, content_hash: str) -> None:
        """Register a content hash only after parsing has succeeded completely."""
        if content_hash:
            self.seen_hashes.add(content_hash)

    def clear(self) -> None:
        """Clear all registered hashes."""
        self.seen_hashes.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Return deduplication statistics."""
        return {
            "unique_hashes": len(self.seen_hashes),
            "algorithm": self.hash_algorithm,
            "persistent": False,
        }
