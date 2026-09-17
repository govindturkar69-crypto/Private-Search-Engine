"""Utility package for Private Search Engine."""

import hashlib
from src.utils.url import (
    extract_domain,
    is_valid_url,
    normalize_url,
    url_to_hash,
)


def compute_sha256(content: str) -> str:
    """Compute SHA-256 hash of a string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


__all__ = [
    "compute_sha256",
    "normalize_url",
    "is_valid_url",
    "extract_domain",
    "url_to_hash",
]
