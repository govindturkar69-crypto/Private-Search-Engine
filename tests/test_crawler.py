"""Unit and security tests for crawler components.

Covers URLFrontier, RobotsTxtParser, URL utils, and Fetcher.
"""

import gzip
from typing import List
import httpx
import pytest
from src.crawler import FetchResult, Fetcher, URLFrontier
from src.crawler.robots import RobotsTxtParser
from src.utils.url import extract_domain, is_valid_url, normalize_url, url_to_hash


# =====================================================================
# 1. URLFrontier Tests
# =====================================================================
class TestURLFrontier:
    def test_add_url(self):
        frontier = URLFrontier()
        assert frontier.add_url("https://example.com") is True
        assert frontier.size() == 1

    def test_get_next_url(self):
        frontier = URLFrontier()
        frontier.add_url("https://example.com")
        url = frontier.get_next_url()
        assert url == "https://example.com/"
        assert frontier.size() == 0

    def test_duplicate_queued_urls(self):
        frontier = URLFrontier()
        assert frontier.add_url("https://example.com/page") is True
        assert frontier.add_url("https://example.com/page") is False
        assert frontier.size() == 1

    def test_already_crawled_urls(self):
        frontier = URLFrontier()
        frontier.add_url("https://example.com")
        url = frontier.get_next_url()
        assert url is not None
        frontier.mark_crawled(url)
        assert frontier.add_url("https://example.com") is False
        assert frontier.size() == 0

    def test_visited_not_added_twice(self):
        frontier = URLFrontier()
        frontier.add_url("https://example.com")
        frontier.get_next_url()
        frontier.add_url("https://example.com")
        assert frontier.size() == 0

    def test_priority_behavior(self):
        frontier = URLFrontier()
        frontier.add_url("https://b.com", priority=2)
        frontier.add_url("https://a.com", priority=1)
        url1 = frontier.get_next_url()
        url2 = frontier.get_next_url()
        assert url1 == "https://a.com/"
        assert url2 == "https://b.com/"

    def test_per_domain_politeness(self):
        frontier = URLFrontier(crawl_delay=10.0)
        frontier.add_url("https://domain-a.com/1")
        frontier.add_url("https://domain-a.com/2")
        frontier.add_url("https://domain-b.com/1")

        # Pop first URL from domain-a
        first = frontier.get_next_url()
        assert first == "https://domain-a.com/1"
        frontier.mark_crawled(first)

        # Immediate next URL should be from domain-b because domain-a is cooling down
        second = frontier.get_next_url()
        assert second == "https://domain-b.com/1"

        # Now domain-a/2 should still be waiting for delay to expire
        third = frontier.get_next_url()
        assert third is None
        assert frontier.size() == 1


# =====================================================================
# 2. URL Normalization Tests
# =====================================================================
class TestURLNormalization:
    def test_normalize_case(self):
        url1 = "HTTPS://Example.COM/Path"
        url2 = "https://example.com/Path"
        assert normalize_url(url1) == normalize_url(url2)

    def test_remove_fragment(self):
        url1 = "https://example.com/path#section"
        url2 = "https://example.com/path"
        assert normalize_url(url1) == normalize_url(url2)

    def test_remove_default_ports(self):
        http_port = "http://example.com:80/path"
        http_clean = "http://example.com/path"
        assert normalize_url(http_port) == normalize_url(http_clean)

        https_port = "https://example.com:443/path"
        https_clean = "https://example.com/path"
        assert normalize_url(https_port) == normalize_url(https_clean)

        custom_port = "https://example.com:8443/path"
        assert normalize_url(custom_port) == "https://example.com:8443/path"

    def test_empty_path_normalization(self):
        assert normalize_url("https://example.com") == "https://example.com/"

    def test_query_order_preservation(self):
        # Default mode preserves query order
        raw = "https://example.com?b=2&a=1"
        assert normalize_url(raw, sort_query=False) == "https://example.com/?b=2&a=1"

        # Optional canonical mode sorts query
        assert normalize_url(raw, sort_query=True) == "https://example.com/?a=1&b=2"

    def test_url_to_hash(self):
        h1 = url_to_hash("https://example.com/path#fragment")
        h2 = url_to_hash("https://example.com/path")
        assert h1 == h2


# =====================================================================
# 3. URL Validation Tests
# =====================================================================
class TestURLValidation:
    def test_valid_url(self):
        assert is_valid_url("https://example.com")
        assert is_valid_url("http://sub.domain.org/path?q=1")

    def test_invalid_scheme(self):
        assert not is_valid_url("ftp://example.com")
        assert not is_valid_url("file:///etc/passwd")
        assert not is_valid_url("javascript:alert(1)")
        assert not is_valid_url("data:text/html,<h1>test</h1>")

    def test_missing_hostname(self):
        assert not is_valid_url("http:///path")
        assert not is_valid_url("https://")

    def test_malformed_ports(self):
        assert not is_valid_url("http://example.com:999999/")
        assert not is_valid_url("http://example.com:abc/")

    def test_extract_domain(self):
        assert extract_domain("https://example.com/path") == "example.com"
        assert extract_domain("http://sub.test.org:8080/") == "sub.test.org"

    def test_ipv6_handling(self):
        assert is_valid_url("http://[::1]/")
        assert extract_domain("http://[::1]:8080/path") == "::1"


# =====================================================================
# 4. Robots.txt RFC 9309 Tests
# =====================================================================
class TestRobotsTxt:
    def test_parse_disallow(self):
        robots = "User-agent: *\nDisallow: /admin"
        parser = RobotsTxtParser(robots)
        assert not parser.can_fetch("*", "/admin")
        assert not parser.can_fetch("*", "/admin/settings")
        assert parser.can_fetch("*", "/public")

    def test_parse_allow(self):
        robots = "User-agent: *\nDisallow: /\nAllow: /public"
        parser = RobotsTxtParser(robots)
        assert parser.can_fetch("*", "/public")
        assert parser.can_fetch("*", "/public/docs")
        assert not parser.can_fetch("*", "/private")

    def test_crawl_delay_extension(self):
        robots = "User-agent: *\nCrawl-delay: 2.5"
        parser = RobotsTxtParser(robots)
        assert parser.get_crawl_delay("*") == 2.5

    def test_longest_match_behavior(self):
        # Allow /a/b (len 4) vs Disallow /a (len 2) -> /a/b should be allowed
        robots1 = "User-agent: *\nDisallow: /a\nAllow: /a/b"
        p1 = RobotsTxtParser(robots1)
        assert p1.can_fetch("*", "/a/b")
        assert not p1.can_fetch("*", "/a/c")

        # Disallow /a/b (len 4) vs Allow /a (len 2) -> /a/b should be disallowed
        robots2 = "User-agent: *\nAllow: /a\nDisallow: /a/b"
        p2 = RobotsTxtParser(robots2)
        assert not p2.can_fetch("*", "/a/b")
        assert p2.can_fetch("*", "/a/c")

    def test_tie_behavior_allow_wins(self):
        # RFC 9309 2.2.2: Equal length conflict -> Allow wins
        robots = "User-agent: *\nDisallow: /test\nAllow: /test"
        parser = RobotsTxtParser(robots)
        assert parser.can_fetch("*", "/test")

    def test_wildcard_and_specific_user_agent(self):
        robots = (
            "User-agent: *\n"
            "Disallow: /global-block\n\n"
            "User-agent: PrivateSearchCrawler\n"
            "Disallow: /crawler-block\n"
        )
        parser = RobotsTxtParser(robots)
        # Specific agent gets its own group
        assert not parser.can_fetch("PrivateSearchCrawler", "/crawler-block")
        assert parser.can_fetch("PrivateSearchCrawler", "/global-block")
        # Other agent falls back to wildcard
        assert not parser.can_fetch("OtherBot", "/global-block")
        assert parser.can_fetch("OtherBot", "/crawler-block")

    def test_pattern_wildcards_and_end_anchor(self):
        robots = "User-agent: *\nDisallow: /*.php$\nAllow: /public/*.php"
        parser = RobotsTxtParser(robots)
        assert not parser.can_fetch("*", "/index.php")
        assert parser.can_fetch("*", "/index.php?query=1")  # Doesn't end in .php
        # /public/*.php has length 14 vs /*.php$ length 8 -> Allow wins
        assert parser.can_fetch("*", "/public/index.php")


# =====================================================================
# 5. SSRF Security Tests
# =====================================================================
class TestSSRF:
    def test_ssrf_blocked_localhost(self):
        fetcher = Fetcher()
        assert not fetcher._is_safe_url("http://localhost/")
        assert not fetcher._is_safe_url("http://localhost:8080/")
        assert not fetcher._is_safe_url("http://127.0.0.1/")
        assert not fetcher._is_safe_url("http://127.0.0.2/")

    def test_ssrf_blocked_private(self):
        fetcher = Fetcher()
        assert not fetcher._is_safe_url("http://10.0.0.1/")
        assert not fetcher._is_safe_url("http://192.168.1.1/")
        assert not fetcher._is_safe_url("http://172.16.0.1/")
        assert not fetcher._is_safe_url("http://172.31.255.255/")
        assert not fetcher._is_safe_url("http://100.64.0.1/")  # CGNAT

    def test_ssrf_blocked_ipv6(self):
        fetcher = Fetcher()
        assert not fetcher._is_safe_url("http://[::1]/")
        assert not fetcher._is_safe_url("http://[::]/")

    def test_ssrf_blocked_link_local(self):
        fetcher = Fetcher()
        assert not fetcher._is_safe_url("http://169.254.169.254/")
        assert not fetcher._is_safe_url("http://[fe80::1]/")

    def test_hostname_resolving_to_private_ip(self):
        # Mock DNS resolver resolving internal hostname to private IP
        def mock_internal_dns(hostname: str) -> List[str]:
            if hostname == "company.internal":
                return ["10.50.1.1"]
            return ["93.184.216.34"]

        fetcher = Fetcher(dns_resolver=mock_internal_dns)
        assert not fetcher._is_safe_url("http://company.internal/secret")
        assert fetcher._is_safe_url("http://public.com/")

    def test_safe_url_allowed(self):
        def mock_public_dns(hostname: str) -> List[str]:
            return ["93.184.216.34"]

        fetcher = Fetcher(dns_resolver=mock_public_dns)
        assert fetcher._is_safe_url("https://example.com/")


# =====================================================================
# 6. Fetcher Integration & Edge Case Tests (Offline MockTransport)
# =====================================================================
class TestFetcher:
    @pytest.mark.asyncio
    async def test_successful_fetch_and_tuple_unpacking(self):
        def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"Content-Type": "text/html; charset=utf-8"},
                text="<html><body>Hello World</body></html>",
            )

        fetcher = Fetcher(
            dns_resolver=lambda h: ["93.184.216.34"],
            transport=httpx.MockTransport(mock_handler),
        )

        res = await fetcher.fetch("https://example.com/page")
        assert isinstance(res, FetchResult)
        assert res.status_code == 200
        assert res.content == "<html><body>Hello World</body></html>"
        assert res.content_type == "text/html; charset=utf-8"
        assert res.error is None

        # Verify backward-compatible tuple unpacking: content, status, headers
        content, status, headers = res
        assert status == 200
        assert content == "<html><body>Hello World</body></html>"
        assert "Content-Type" in headers or "content-type" in headers

    @pytest.mark.asyncio
    async def test_http_404_handling(self):
        def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text="Not Found")

        fetcher = Fetcher(
            dns_resolver=lambda h: ["93.184.216.34"],
            transport=httpx.MockTransport(mock_handler),
        )

        res = await fetcher.fetch("https://example.com/missing")
        assert res.status_code == 404
        assert res.content == "Not Found"

    @pytest.mark.asyncio
    async def test_redirect_to_private_destination_blocked(self):
        def mock_handler(request: httpx.Request) -> httpx.Response:
            if request.url == "https://example.com/redirect":
                return httpx.Response(
                    302,
                    headers={"Location": "http://127.0.0.1/admin"},
                )
            return httpx.Response(200, text="Admin Content")

        fetcher = Fetcher(
            dns_resolver=lambda h: ["93.184.216.34"],
            transport=httpx.MockTransport(mock_handler),
        )

        res = await fetcher.fetch("https://example.com/redirect")
        assert res.status_code == 403
        assert "SSRF blocked" in (res.error or "")

    @pytest.mark.asyncio
    async def test_redirect_loop_detected(self):
        def mock_handler(request: httpx.Request) -> httpx.Response:
            if request.url == "https://example.com/loop1":
                return httpx.Response(
                    301, headers={"Location": "https://example.com/loop2"}
                )
            if request.url == "https://example.com/loop2":
                return httpx.Response(
                    301, headers={"Location": "https://example.com/loop1"}
                )
            return httpx.Response(200)

        fetcher = Fetcher(
            dns_resolver=lambda h: ["93.184.216.34"],
            transport=httpx.MockTransport(mock_handler),
        )

        res = await fetcher.fetch("https://example.com/loop1")
        assert res.status_code == 400
        assert "Redirect loop detected" in (res.error or "")

    @pytest.mark.asyncio
    async def test_max_redirect_count_exceeded(self):
        def mock_handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            step = int(path.replace("/step", "") or 0)
            return httpx.Response(
                302, headers={"Location": f"https://example.com/step{step + 1}"}
            )

        fetcher = Fetcher(
            max_redirects=3,
            dns_resolver=lambda h: ["93.184.216.34"],
            transport=httpx.MockTransport(mock_handler),
        )

        res = await fetcher.fetch("https://example.com/step0")
        assert res.status_code == 400
        assert "Maximum redirects" in (res.error or "")

    @pytest.mark.asyncio
    async def test_oversized_document_blocked(self):
        large_body = b"A" * 150_000  # 150KB

        def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"Content-Length": str(len(large_body))},
                content=large_body,
            )

        # Configured max_size: 100KB
        fetcher = Fetcher(
            max_size=100_000,
            dns_resolver=lambda h: ["93.184.216.34"],
            transport=httpx.MockTransport(mock_handler),
        )

        res = await fetcher.fetch("https://example.com/large")
        assert res.status_code == 413
        assert "exceeds limit" in (res.error or "")

    @pytest.mark.asyncio
    async def test_decompression_bomb_protection(self):
        # 1MB repeated string compresses to small payload (~1KB)
        uncompressed = b"X" * 1_000_000
        compressed = gzip.compress(uncompressed)

        def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={
                    "Content-Encoding": "gzip",
                    "Content-Length": str(len(compressed)),
                },
                content=compressed,
            )

        # Set max_decompressed_size to 200KB (smaller than 1MB uncompressed)
        fetcher = Fetcher(
            max_size=100_000,
            max_decompressed_size=200_000,
            dns_resolver=lambda h: ["93.184.216.34"],
            transport=httpx.MockTransport(mock_handler),
        )

        res = await fetcher.fetch("https://example.com/bomb")
        assert res.status_code == 413
        assert "Decompression" in (res.error or "")

    @pytest.mark.asyncio
    async def test_timeout_and_retry_behavior(self):
        attempts = 0

        def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise httpx.ConnectTimeout("Connection timed out")
            return httpx.Response(200, text="Success on attempt 3")

        fetcher = Fetcher(
            backoff=[0.0, 0.0, 0.0],  # Immediate retry in tests
            dns_resolver=lambda h: ["93.184.216.34"],
            transport=httpx.MockTransport(mock_handler),
        )

        res = await fetcher.fetch("https://example.com/flaky")
        assert res.status_code == 200
        assert res.content == "Success on attempt 3"
        assert attempts == 3
