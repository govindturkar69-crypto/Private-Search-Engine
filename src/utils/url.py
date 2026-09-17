"""URL normalization, validation, and extraction utilities."""

import hashlib
import logging
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

logger = logging.getLogger(__name__)


def normalize_url(url: str, sort_query: bool = False) -> str:
    """Normalize a URL for deduplication and canonical referencing.

    Rules:
    - Lowercase scheme and netloc (including IPv6 hosts).
    - Remove default ports (:80 for http, :443 for https).
    - Strip fragment.
    - Default empty path to '/'.
    - Preserve query parameter ordering by default. If sort_query=True,
      sorts query parameters for canonical indexing.
    """
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if not scheme:
            return url

        # Process netloc and port
        hostname = parsed.hostname.lower() if parsed.hostname else ""
        port = parsed.port

        # Reconstruct netloc without default ports
        if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
            port = None

        if port is not None:
            # Handle IPv6 host formatting with port
            if ":" in hostname and not hostname.startswith("["):
                netloc = f"[{hostname}]:{port}"
            else:
                netloc = f"{hostname}:{port}"
        else:
            if ":" in hostname and not hostname.startswith("["):
                netloc = f"[{hostname}]"
            else:
                netloc = hostname

        # Normalize path
        path = parsed.path if parsed.path else "/"

        # Query handling
        query = parsed.query
        if sort_query and query:
            query_params = parse_qs(query, keep_blank_values=True)
            query = urlencode(sorted(query_params.items()), doseq=True)

        # Drop fragment
        return urlunparse((scheme, netloc, path, parsed.params, query, ""))
    except Exception as e:
        logger.error(f"URL normalization failed for '{url}': {e}")
        return url


def is_valid_url(url: str) -> bool:
    """Validate if URL has a supported scheme, valid host, and valid port.

    Supports: http, https.
    Rejects: file, ftp, data, javascript, missing hostnames, malformed ports.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in ("http", "https"):
            return False

        if not parsed.hostname:
            return False

        # Validate port if present
        try:
            port = parsed.port
            if port is not None and not (1 <= port <= 65535):
                return False
        except ValueError:
            return False

        return True
    except Exception:
        return False


def extract_domain(url: str) -> str:
    """Extract domain or hostname from URL."""
    try:
        parsed = urlparse(url)
        return parsed.hostname.lower() if parsed.hostname else ""
    except Exception:
        return ""


def url_to_hash(url: str) -> str:
    """Compute SHA-256 hash of normalized URL."""
    normalized = normalize_url(url)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
