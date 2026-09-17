"""End-to-end browser test suite using Playwright.

Marked with @pytest.mark.e2e.
Designed for execution against dedicated local test servers (backend :8001,
frontend :3001) with failure screenshot artifacts and accessible role selectors.
"""

from datetime import datetime
import os
from pathlib import Path
from typing import Any, Generator
import pytest

# Graceful import check for Playwright
try:
    import playwright.sync_api as playwright_sync

    sync_playwright = playwright_sync.sync_playwright
except (ImportError, Exception):
    playwright_sync = None  # type: ignore
    sync_playwright = None  # type: ignore

DEFAULT_E2E_BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:3001")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "dev-admin-secret-token")

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        sync_playwright is None,
        reason="Playwright not installed or DLL blocked by OS policy",
    ),
]


@pytest.fixture(scope="class")
def browser_instance() -> Generator[Any, None, None]:
    """Launch headless Chromium browser instance."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(
    browser_instance: Any, request: pytest.FixtureRequest
) -> Generator[Any, None, None]:
    """Provide an isolated page with failure artifact capture."""
    context = browser_instance.new_context()
    page = context.new_page()

    yield page

    # Failure screenshot artifact capture
    if hasattr(request.node, "rep_call") and request.node.rep_call.failed:
        artifacts_dir = Path("test-results/e2e")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = request.node.name.replace("/", "_").replace(":", "_")
        screenshot_path = artifacts_dir / f"failure_{safe_name}_{ts}.png"
        try:
            page.screenshot(path=str(screenshot_path))
            print(f"\n[E2E Failure Artifact] Captured: {screenshot_path}")
        except Exception as e:
            print(f"\nFailed to capture failure screenshot: {e}")

    page.close()
    context.close()


@pytest.mark.e2e
class TestSearchE2E:
    """End-to-end frontend user journey tests."""

    def test_initial_search_page_elements(self, page: Any) -> None:
        """Verify search page loads and essential accessible elements exist."""
        page.goto(DEFAULT_E2E_BASE_URL, wait_until="domcontentloaded")

        # Heading / Brand
        assert page.locator("h1, .logo-title, .brand-title").first.is_visible()

        # Search combobox input
        search_input = page.locator('input[role="combobox"], input[type="text"]').first
        assert search_input.is_visible()

        # Search submit button
        submit_btn = page.locator('button[type="submit"]').first
        assert submit_btn.is_visible()

    def test_successful_search_and_results(self, page: Any) -> None:
        """Verify search submission renders results with titles, snippets, and links."""
        page.goto(DEFAULT_E2E_BASE_URL, wait_until="domcontentloaded")

        search_input = page.locator('input[role="combobox"], input[type="text"]').first
        search_input.fill("python")

        page.locator('button[type="submit"]').first.click()

        # Wait for search results
        page.wait_for_selector(
            'article, [role="article"], .search-result', timeout=8000
        )
        results = page.locator('article, [role="article"], .search-result')
        assert results.count() > 0

        first_title = results.first.locator("h3, .result-title").first
        assert first_title.is_visible()

    def test_no_results_found(self, page: Any) -> None:
        """Searching for non-existent term renders empty state gracefully."""
        page.goto(DEFAULT_E2E_BASE_URL, wait_until="domcontentloaded")

        search_input = page.locator('input[role="combobox"], input[type="text"]').first
        search_input.fill("nonexistentquerytermxyz123456789")

        page.locator('button[type="submit"]').first.click()

        # Check for empty state message or zero results
        page.wait_for_selector(
            '.empty-state, .no-results, [role="status"]', timeout=8000
        )
        assert page.locator('article, [role="article"]').count() == 0

    def test_autocomplete_suggestions(self, page: Any) -> None:
        """Typing search prefix triggers debounced autocomplete suggestions dropdown."""
        page.goto(DEFAULT_E2E_BASE_URL, wait_until="domcontentloaded")

        search_input = page.locator('input[role="combobox"], input[type="text"]').first
        search_input.fill("pyt")

        # Wait for suggestions listbox
        page.wait_for_selector('[role="listbox"], .suggestions-dropdown', timeout=4000)
        options = page.locator('[role="option"], .suggestion-item')
        assert options.count() > 0

        # Click first suggestion
        first_opt = options.first
        _ = first_opt.text_content() or ""
        first_opt.click()

        # Input should now reflect the selected term
        current_val = search_input.input_value()
        assert len(current_val) >= 3

    def test_pagination_navigation(self, page: Any) -> None:
        """Navigating through pages updates result set and pagination controls."""
        page.goto(
            f"{DEFAULT_E2E_BASE_URL}/?q=document&page=1", wait_until="domcontentloaded"
        )

        page.wait_for_selector(
            'article, [role="article"], .search-result', timeout=8000
        )

        # Check if pagination exists
        pagination_nav = page.locator(
            'nav.pagination, .pagination, [aria-label*="Pagination"]'
        )
        if pagination_nav.count() > 0:
            page2_btn = pagination_nav.locator(
                'button:has-text("2"), a:has-text("2")'
            ).first
            if page2_btn.is_visible():
                page2_btn.click()
                page.wait_for_function(
                    "() => window.location.search.includes('page=2')",
                    timeout=4000,
                )
                assert "page=2" in page.url

    def test_shareable_url_query_restoration(self, page: Any) -> None:
        """Loading URL with query parameters restores query and executes search."""
        page.goto(
            f"{DEFAULT_E2E_BASE_URL}/?q=python&page=1", wait_until="domcontentloaded"
        )

        # Verify input was populated from URL
        search_input = page.locator('input[role="combobox"], input[type="text"]').first
        assert search_input.input_value() == "python"

        # Verify results loaded
        page.wait_for_selector(
            'article, [role="article"], .search-result', timeout=8000
        )
        assert page.locator('article, [role="article"], .search-result').count() > 0

    def test_backend_unavailable_error_handling(self, page: Any) -> None:
        """Frontend displays error banner when backend search service is unavailable."""
        # Controlled route interceptor simulating 503 without killing the backend
        page.route(
            "**/api/v1/search*",
            lambda route: route.fulfill(
                status=503,
                content_type="application/json",
                body=(
                    '{"error": "Search engine service is unavailable",'
                    ' "code": 503, "timestamp": "2026-09-15T00:00:00Z",'
                    ' "request_id": "mock503"}'
                ),
            ),
        )

        page.goto(DEFAULT_E2E_BASE_URL, wait_until="domcontentloaded")
        search_input = page.locator('input[role="combobox"], input[type="text"]').first
        search_input.fill("query503")
        page.locator('button[type="submit"]').first.click()

        # Verify structured error alert is displayed
        page.wait_for_selector(
            '[role="alert"], .alert-error, .search-error', timeout=5000
        )
        alert = page.locator('[role="alert"], .alert-error, .search-error').first
        assert alert.is_visible()

        # Unroute so subsequent tests remain unaffected
        page.unroute("**/api/v1/search*")


@pytest.mark.e2e
class TestAdminE2E:
    """End-to-end admin dashboard user journey tests."""

    def test_admin_authentication_gate(self, page: Any) -> None:
        """Navigating to /admin renders the restricted access authentication gate."""
        page.goto(f"{DEFAULT_E2E_BASE_URL}/admin", wait_until="domcontentloaded")

        # Should display password/token input and submit button
        token_input = page.locator('input[type="password"]').first
        assert token_input.is_visible()

        submit_btn = page.locator(
            'button:has-text("Authenticate"), button[type="submit"]'
        ).first
        assert submit_btn.is_visible()

    def test_admin_invalid_token_rejected(self, page: Any) -> None:
        """Submitting an invalid admin token displays an error alert."""
        page.goto(f"{DEFAULT_E2E_BASE_URL}/admin", wait_until="domcontentloaded")

        token_input = page.locator('input[type="password"]').first
        token_input.fill("completely-wrong-token-abc123")

        page.locator(
            'button:has-text("Authenticate"), button[type="submit"]'
        ).first.click()

        # Verify error alert
        page.wait_for_selector('[role="alert"], .alert-error', timeout=5000)
        err_alert = page.locator('[role="alert"], .alert-error').first
        assert err_alert.is_visible()

    def test_admin_login_and_overview_stats(self, page: Any) -> None:
        """Submitting valid token enters the dashboard and displays telemetry cards."""
        page.goto(f"{DEFAULT_E2E_BASE_URL}/admin", wait_until="domcontentloaded")

        token_input = page.locator('input[type="password"]').first
        token_input.fill(ADMIN_TOKEN)

        page.locator(
            'button:has-text("Authenticate"), button[type="submit"]'
        ).first.click()

        # Dashboard layout should load
        page.wait_for_selector(".admin-layout, .admin-navbar", timeout=6000)
        assert page.locator(".admin-layout, .admin-navbar").first.is_visible()

        # Switch to Index Statistics tab
        index_tab = page.locator(
            'button:has-text("Index"), [role="tab"]:has-text("Index")'
        ).first
        if index_tab.is_visible():
            index_tab.click()
            page.wait_for_selector(".stat-card, .stats-cards-grid", timeout=5000)
            assert page.locator(".stat-card").count() >= 2

    def test_admin_crawl_controls_mock_safety(self, page: Any) -> None:
        """Admin crawler tab renders controls without external internet crawl."""
        page.goto(f"{DEFAULT_E2E_BASE_URL}/admin", wait_until="domcontentloaded")

        token_input = page.locator('input[type="password"]').first
        if token_input.is_visible():
            token_input.fill(ADMIN_TOKEN)
            page.locator(
                'button:has-text("Authenticate"), button[type="submit"]'
            ).first.click()
            page.wait_for_selector(".admin-layout", timeout=6000)

        # Crawler tab
        crawler_tab = page.locator('button:has-text("Crawler")').first
        if crawler_tab.is_visible():
            crawler_tab.click()
            # Form elements must exist
            assert page.locator(
                'textarea, input[placeholder*="http"]'
            ).first.is_visible()
            # Start / Launch Crawl button exists
            assert page.locator(
                'button:has-text("Launch"), button:has-text("Start"), .btn-start'
            ).first.is_visible()
