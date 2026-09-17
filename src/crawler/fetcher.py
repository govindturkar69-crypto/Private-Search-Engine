"""Async HTTP fetcher with SSRF, size limits, and security protections."""

import asyncio
import ipaddress
import logging
import socket
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterator, List, Optional
from urllib.parse import urljoin, urlparse
import httpx
from src.utils.url import is_valid_url

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """Structured result of an HTTP fetch operation."""

    url: str
    final_url: str
    status_code: int
    headers: Dict[str, str] = field(default_factory=dict)
    content: Optional[str] = None
    content_type: Optional[str] = None
    elapsed: float = 0.0
    error: Optional[str] = None

    def __iter__(self) -> Iterator[object]:
        """Support legacy tuple unpacking: (content, status_code, headers)."""
        yield self.content
        yield self.status_code
        yield self.headers


def is_safe_ip(ip_str: str) -> bool:
    """Validate if IP is a safe public address.

    Rejects loopback, private, link-local, multicast, unspecified, reserved,
    and Carrier-Grade NAT addresses.
    """
    try:
        ip = ipaddress.ip_address(ip_str.strip("[]"))
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or ip.is_reserved
        ):
            return False

        if isinstance(ip, ipaddress.IPv4Address):
            # Block Carrier-Grade NAT (RFC 6598: 100.64.0.0/10)
            if ip in ipaddress.IPv4Network("100.64.0.0/10"):
                return False
            # Block 0.0.0.0/8
            if ip in ipaddress.IPv4Network("0.0.0.0/8"):
                return False

        return True
    except ValueError:
        return False


class Fetcher:
    """Async HTTP fetcher with timeouts, retries, and security protections."""

    def __init__(
        self,
        timeout: float = 10.0,
        max_size: int = 10_485_760,  # 10MB max document wire size
        max_decompressed_size: int = 52_428_800,  # 50MB max decompressed size
        max_redirects: int = 5,
        user_agent: str = "PrivateSearchCrawler/1.0 (+http://localhost:8000)",
        backoff: Optional[List[float]] = None,
        dns_resolver: Optional[Callable[[str], List[str]]] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.timeout = timeout
        self.max_size = max_size
        self.max_decompressed_size = max_decompressed_size
        self.max_redirects = max_redirects
        self.user_agent = user_agent
        self.backoff = backoff if backoff is not None else [1.0, 3.0, 10.0]
        self.dns_resolver = dns_resolver
        self.transport = transport

    def _resolve_hostname(self, hostname: str) -> List[str]:
        """Resolve hostname to a list of IP addresses."""
        if self.dns_resolver is not None:
            return self.dns_resolver(hostname)

        # Standard DNS resolution
        ips: List[str] = []
        try:
            addr_info = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
            for _, _, _, _, sockaddr in addr_info:
                ip = sockaddr[0]
                if ip not in ips:
                    ips.append(ip)
        except socket.gaierror:
            pass
        return ips

    def _is_safe_url(self, url: str) -> bool:
        """Validate URL against SSRF rules including DNS resolution checks."""
        try:
            if not is_valid_url(url):
                return False

            parsed = urlparse(url)
            scheme = parsed.scheme.lower()
            if scheme not in ("http", "https"):
                return False

            raw_host = parsed.hostname
            if not raw_host:
                return False

            host = raw_host.lower().strip("[]")

            # Check well-known local/loopback names
            if host in ("localhost", "localhost.localdomain") or host.endswith(
                ".localhost"
            ):
                return False

            # Check if host is an IP literal
            try:
                ip_obj = ipaddress.ip_address(host)
                return is_safe_ip(str(ip_obj))
            except ValueError:
                # Not an IP literal, proceed to DNS resolution
                pass

            # Resolve DNS
            resolved_ips = self._resolve_hostname(host)
            if resolved_ips:
                # If DNS resolved, every address must be safe
                for resolved_ip in resolved_ips:
                    if not is_safe_ip(resolved_ip):
                        return False
            elif self.transport is None:
                # In real network operation, unresolvable host is unsafe
                return False

            return True
        except Exception as e:
            logger.warning(f"SSRF safety check error for {url}: {e}")
            return False

    async def fetch(self, url: str) -> FetchResult:
        """Fetch URL asynchronously with security checks and retries."""
        start_time = time.monotonic()
        retries = len(self.backoff)

        for attempt in range(retries):
            try:
                result = await self._fetch_attempt(url, start_time)
                # If network timeout or connection error occurred, retry with backoff
                if result.error and result.status_code in (408, 504, 502, 503):
                    if attempt < retries - 1:
                        sleep_time = self.backoff[attempt]
                        if sleep_time > 0:
                            await asyncio.sleep(sleep_time)
                        continue
                return result
            except (asyncio.TimeoutError, httpx.TimeoutException) as e:
                logger.warning(
                    f"Timeout fetching {url} (attempt {attempt + 1}/{retries}): {e}"
                )
                if attempt < retries - 1:
                    sleep_time = self.backoff[attempt]
                    if sleep_time > 0:
                        await asyncio.sleep(sleep_time)
                else:
                    elapsed = time.monotonic() - start_time
                    return FetchResult(
                        url=url,
                        final_url=url,
                        status_code=408,
                        elapsed=elapsed,
                        error=f"Timeout after {retries} retries",
                    )
            except httpx.ConnectError as e:
                logger.warning(
                    f"Connection error for {url} (attempt {attempt + 1}/{retries}): {e}"
                )
                if attempt < retries - 1:
                    sleep_time = self.backoff[attempt]
                    if sleep_time > 0:
                        await asyncio.sleep(sleep_time)
                else:
                    elapsed = time.monotonic() - start_time
                    return FetchResult(
                        url=url,
                        final_url=url,
                        status_code=502,
                        elapsed=elapsed,
                        error=f"Connection failed after {retries} retries",
                    )
            except Exception as e:
                logger.error(f"Unexpected fetch error for {url}: {e}")
                elapsed = time.monotonic() - start_time
                return FetchResult(
                    url=url,
                    final_url=url,
                    status_code=500,
                    elapsed=elapsed,
                    error=str(e),
                )

        elapsed = time.monotonic() - start_time
        return FetchResult(
            url=url,
            final_url=url,
            status_code=500,
            elapsed=elapsed,
            error=f"Failed after {retries} retries",
        )

    async def _fetch_attempt(self, start_url: str, start_time: float) -> FetchResult:
        """Execute single fetch handling manual redirects and limits."""
        current_url = start_url
        visited_redirects: List[str] = []
        redirect_count = 0

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            transport=self.transport,
            follow_redirects=False,
            headers={"User-Agent": self.user_agent},
        ) as client:
            while True:
                # 1. SSRF check on current URL
                if not self._is_safe_url(current_url):
                    logger.warning(f"SSRF blocked: {current_url}")
                    elapsed = time.monotonic() - start_time
                    return FetchResult(
                        url=start_url,
                        final_url=current_url,
                        status_code=403,
                        elapsed=elapsed,
                        error=f"SSRF blocked: unsafe destination '{current_url}'",
                    )

                # 2. Redirect loop detection
                if current_url in visited_redirects:
                    logger.warning(f"Redirect loop detected: {current_url}")
                    elapsed = time.monotonic() - start_time
                    return FetchResult(
                        url=start_url,
                        final_url=current_url,
                        status_code=400,
                        elapsed=elapsed,
                        error=f"Redirect loop detected at '{current_url}'",
                    )
                visited_redirects.append(current_url)

                # 3. Redirect count limit
                if redirect_count > self.max_redirects:
                    logger.warning(
                        f"Max redirects ({self.max_redirects}) exceeded: {current_url}"
                    )
                    elapsed = time.monotonic() - start_time
                    return FetchResult(
                        url=start_url,
                        final_url=current_url,
                        status_code=400,
                        elapsed=elapsed,
                        error=f"Maximum redirects ({self.max_redirects}) exceeded",
                    )

                # 4. Stream response to enforce size limits
                async with client.stream("GET", current_url) as response:
                    headers_dict = dict(response.headers)
                    status_code = response.status_code

                    # Check for redirect
                    if status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            elapsed = time.monotonic() - start_time
                            return FetchResult(
                                url=start_url,
                                final_url=current_url,
                                status_code=status_code,
                                headers=headers_dict,
                                elapsed=elapsed,
                                error="Redirect missing Location header",
                            )
                        redirect_count += 1
                        current_url = urljoin(current_url, location)
                        continue

                    # Non-redirect response: inspect content length header
                    content_len_header = response.headers.get("content-length")
                    if content_len_header:
                        try:
                            clen = int(content_len_header)
                            if clen > self.max_size:
                                logger.warning(
                                    f"Content-Length {clen} exceeds max_size "
                                    f"{self.max_size}: {current_url}"
                                )
                                elapsed = time.monotonic() - start_time
                                return FetchResult(
                                    url=start_url,
                                    final_url=current_url,
                                    status_code=413,
                                    headers=headers_dict,
                                    elapsed=elapsed,
                                    error=(
                                        f"Document size ({clen} bytes) exceeds limit "
                                        f"({self.max_size} bytes)"
                                    ),
                                )
                        except ValueError:
                            pass

                    # Stream chunks and enforce wire and decompression bounds
                    total_decompressed = 0
                    chunks: List[bytes] = []
                    is_compressed = response.headers.get(
                        "content-encoding", ""
                    ).lower() in ("gzip", "deflate", "br")

                    async for chunk in response.aiter_bytes():
                        # Enforce wire download limit
                        downloaded = getattr(response, "num_bytes_downloaded", 0)
                        if downloaded > self.max_size:
                            logger.warning(
                                f"Wire download limit exceeded "
                                f"({downloaded} > {self.max_size})"
                            )
                            elapsed = time.monotonic() - start_time
                            return FetchResult(
                                url=start_url,
                                final_url=current_url,
                                status_code=413,
                                headers=headers_dict,
                                elapsed=elapsed,
                                error=(
                                    f"Document wire size exceeds limit "
                                    f"({self.max_size} bytes)"
                                ),
                            )

                        # Enforce decompressed size limit
                        total_decompressed += len(chunk)
                        limit = (
                            self.max_decompressed_size
                            if is_compressed
                            else self.max_size
                        )
                        if total_decompressed > limit:
                            err_msg = (
                                f"Decompression bomb detected "
                                f"({total_decompressed} > "
                                f"{self.max_decompressed_size} bytes)"
                                if is_compressed
                                else (
                                    f"Document content exceeds size limit "
                                    f"({total_decompressed} > {self.max_size} bytes)"
                                )
                            )
                            logger.warning(err_msg)
                            elapsed = time.monotonic() - start_time
                            return FetchResult(
                                url=start_url,
                                final_url=current_url,
                                status_code=413,
                                headers=headers_dict,
                                elapsed=elapsed,
                                error=err_msg,
                            )
                        chunks.append(chunk)

                    raw_body = b"".join(chunks)
                    # Decode to text
                    encoding = response.encoding or "utf-8"
                    try:
                        text_content = raw_body.decode(encoding, errors="replace")
                    except Exception:
                        text_content = raw_body.decode("utf-8", errors="replace")

                    elapsed = time.monotonic() - start_time
                    content_type = response.headers.get("content-type")
                    return FetchResult(
                        url=start_url,
                        final_url=current_url,
                        status_code=status_code,
                        headers=headers_dict,
                        content=text_content,
                        content_type=content_type,
                        elapsed=elapsed,
                    )
