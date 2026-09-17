# Testing Strategy & Test Plan

> **Status:** Active / Updated with Phase 11 (Measurement-Driven Performance Optimization)  
> **Last Updated:** 2026-09-16  
> **Total Test Baseline:** **365 passing tests** (291 Backend + 63 Frontend + 11 E2E Playwright)

## 1. Test Architecture Overview
The project employs a dual test harness:
- **Backend:** `pytest` (with `asyncio`, `anyio`, `pytest-cov`, `playwright`), FastAPI `TestClient`, SQLite isolated temp databases.
- **Frontend:** `vitest` (v1.6+), JSDOM test environment, React Testing Library (`@testing-library/react`).

### Test Tier Separation
| Marker | Description | Included in default `pytest tests/`? |
|---|---|---|
| _(none)_ | Unit and integration tests | ✅ Yes |
| `security` | Security regression and penetration tests | ✅ Yes |
| `integration` | End-to-end pipeline integration tests | ✅ Yes |
| `performance` | Benchmark/latency tests (soft thresholds) | ❌ No (run via `scripts/run_benchmarks.ps1`) |
| `e2e` | Playwright browser tests | ❌ No (run via `scripts/run_e2e_tests.ps1`) |
| `slow` | Long-running or resource-intensive tests | ❌ No |

Default run: `pytest tests/ -m "not e2e and not performance and not slow"`

---

## 2. Backend Test Suites (`tests/` — 291 passed, 16 deselected)

| Test Suite | Tests | Scope & Coverage Description |
|---|---|---|
| `test_admin_api.py` | 24 | Admin token auth (401/403/200), dev/prod fallbacks, crawler state machine (idle/running/paused/stopped), 409 conflicts, SSRF pre-validation (422), index/system metrics, log tail bounds and redaction, config allowlist. |
| `test_api.py` | 44 | Search endpoints (`POST`/`GET`), structured queries, autocomplete suggestions, rate limiting, request ID tracing, security headers, health endpoints. |
| `test_cache.py` | 12 | In-memory LRU search cache: hit/miss, mock monotonic clock TTL expiry, capacity eviction, MRU promotion, disabled mode, generation isolation, concurrency safety, API cache headers (`X-Cache: HIT/MISS`), and document write invalidation. |
| `test_config.py` | 3 | Configuration precedence: Environment Variables > `config.yaml` > Dataclass defaults. |
| `test_crawler.py` | 40 | `URLFrontier` priority & politeness, RFC 9309 `RobotsTxtParser`, `Fetcher` async streaming, redirect bounds, SSRF validation. |
| `test_db_optimizer.py` | 8 | Persistent index generation across indexer restarts, duplicate URL/hash no-op generation invariance, batch flush single increment, chunked prefetching >500 IDs, explain query execution, database maintenance actions. |
| `test_indexer.py` | 44 | SQLite inverted index (schema v4.0), document normalization, postings indexing, term DF/CF tracking, Robertson BM25 IDF, atomic batch flush. |
| `test_logger.py` | 2 | Logging setup, log level thresholds, rotating file handler, `data/` directory auto-creation. |
| `test_monitoring.py` | 6 | Bounded deque ring buffer (1000 items), percentiles computation (p50/p95/p99), concurrency safety, privacy assurance (zero query strings logged/stored), and performance threshold alerts. |
| `test_parser.py` | 30 | BeautifulSoup + lxml extraction hierarchy, field character limits, Unicode truncation, stop-words, stemmer, dedup, linker. |
| `test_ranker.py` | 38 | Okapi BM25 scoring, field boost weighting, document length normalization, query parsing, snippet extraction with word-boundary snapping. |
| `test_integration.py` | 8 | `@pytest.mark.integration` — Full pipeline: mock fetch → parse → dedup → index → search API. Concurrency, pagination, error handling, data integrity. Uses `create_app` factory; no global state mutation. |
| `test_security.py` | 19 | `@pytest.mark.security` — SQL injection (schema integrity), XSS payloads, 422 payload size, security headers (CSP/X-Content-Type-Options/X-Frame-Options/Referrer-Policy), HSTS policy, CORS allowed/disallowed, rate limiting (mock clock, client isolation, stale buckets), admin auth (`secrets.compare_digest` verified), SSRF regression (localhost/private/IPv6/DNS/redirect), DOS resilience. |
| `test_security_regression.py` | 14 | `@pytest.mark.security` — Search queries as pure data (path traversal strings execute safely without filesystem access), `LogService` boundary path confinement, SQL injection payload execution safety, XSS data handling, crawler SSRF blocks (loopback/private RFC1918/link-local/admin seeds), admin auth hardening (`secrets.compare_digest` spy, deterministic environment normalization, production failsafe startup), rate limiting & mock clock brute-force throttling, and unsupported XML/XXE 422 rejection. |
| `test_performance.py` | 4 | `@pytest.mark.performance` — Excluded from default run. Parser throughput, single-doc and batch indexing, query latency (single-term, multi-term, phrase, field-filter) p95, autocomplete latency, SQLite storage overhead ratio. |
| `test_e2e.py` | 11 | `@pytest.mark.e2e` — Excluded from default run. Playwright browser scenarios: page load, search, pagination, autocomplete keyboard navigation, empty/error states, admin authentication gate, admin invalid token rejection, admin overview stats, and crawler controls. |

---

## 3. Frontend Test Suites (`frontend/src/` — 62 Passed)

| Test Suite | Tests | Component / Module Covered |
|---|---|---|
| `adminClient.test.ts` | 5 | Dedicated admin client, `sessionStorage` token handling, request interceptor, error transformations. |
| `AdminDashboard.test.tsx`| 5 | Token authentication gate, invalid token alerts, login transition, tab switching, logout. |
| `CrawlManager.test.tsx` | 4 | Crawler telemetry progress, seed URLs validation, start/pause/resume/stop button actions. |
| `StatisticsPanel.test.tsx`| 2 | Inverted index metrics cards, refresh action, modal double-confirmation ("CLEAR") index wiper. |
| `SystemMetrics.test.tsx` | 1 | Strictly measured host CPU, memory, and disk utilization gauges. |
| `LogViewer.test.tsx` | 2 | Safe text log rendering, line bounds, level filter dropdowns, color badges. |
| `ConfigManager.test.tsx`| 2 | Runtime allowlist parameters, in-memory persistence notice, parameter updates. |
| `api.test.ts` | 8 | Search client, suggestion requests, health check, index stats, Axios error handling. |
| `cancellation.test.ts` | 2 | `AbortController` cancellation of stale search and suggestion requests. |
| `App.test.tsx` | 4 | URL synchronization (`/?q=...&page=...`), routing, header stats on mount. |
| `Header.test.tsx` | 3 | Branding, document counter, ready status, theme toggle, admin navigation. |
| `SearchBar.test.tsx` | 9 | Input handling, debounced autocomplete, keyboard navigation (Arrow Up/Down, Enter, Esc), outside-click dismiss. |
| `ResultsList.test.tsx` | 5 | Results rendering, loading skeleton, empty states, error alerts. |
| `SearchResult.test.tsx` | 5 | Result cards, metadata, safe virtual DOM highlight rendering (`<mark>`), and XSS attack vector text-only rendering regression test. |
| `Pagination.test.tsx` | 6 | Windowed page buttons, active page indicators, next/previous controls. |

---

## 4. Automation Runner Scripts

All scripts reside in `scripts/`. PowerShell (`.ps1`) and Bash (`.sh`) variants are provided.

| Script | Purpose |
|---|---|
| `run_fast_tests.ps1/.sh` | Fast deterministic backend regression (excludes e2e/performance/slow) |
| `run_coverage.ps1/.sh` | Backend coverage with ≥80% threshold; HTML + XML report |
| `run_benchmarks.ps1/.sh` | Isolated performance benchmarks (soft thresholds, excluded from default) |
| `run_e2e_tests.ps1/.sh` | Playwright E2E: starts backend :8001 + frontend :3001, readiness wait, runs tests, teardown via try/finally or trap |
| `run_load_tests.ps1/.sh` | Locust load test: explicit LOAD_TEST_HOST or own server; safety guard for non-local; timestamped CSV; failure rate ≤1%, p95 ≤200ms |
| `run_security_scan.ps1/.sh` | Production security audit aggregator: runs `pip-audit`, `bandit` (-ll), `npm audit`, `security_ast_audit.py`, and `security_secret_scan.py` with 0/1/2 exit semantics |
| `run_all_quality.ps1/.sh` | Runs all quality gates: Black → Flake8 → Mypy → Backend regression → Coverage → TypeScript → Build → Vitest |

---

## 5. Verification Commands

```bash
# Fast deterministic backend regression
pytest tests/ -v -m "not e2e and not performance and not slow"

# Backend coverage (>= 80%)
pytest tests/ -m "not e2e and not performance and not slow" \
  --cov=src --cov-report=term-missing --cov-fail-under=80

# Code formatting
python -m black --check src tests

# Linting
python -m flake8 src tests --max-line-length=88

# Static typing (backend)
python -m mypy src

# Frontend TypeScript
npm run type-check --prefix frontend

# Frontend tests
npm test --prefix frontend -- --run

# Frontend coverage
npm run test:coverage --prefix frontend

# Frontend production build
npm run build --prefix frontend

# Playwright E2E browser tests (against dedicated servers)
.\scripts\run_e2e_tests.ps1

# Production security vulnerability audit
.\scripts\run_security_scan.ps1
```

---

## 6. Measured Phase 11 Quality Gate Results (2026-09-16)

| Gate | Result | Detail |
|---|---|---|
| Backend regression | ✅ PASS | **291 passed**, 16 deselected (in 28.65s) |
| Backend coverage | ✅ PASS | **86.44%** total (≥80% threshold; cache 98.6%, metrics 90.8%, indexer 90.8%) |
| Black formatting | ✅ PASS | 66 files clean |
| Flake8 lint | ✅ PASS | 0 errors (strict `max-line-length=88`) |
| Mypy type check | ✅ PASS | 0 issues in 41 source files |
| Frontend Vitest | ✅ PASS | **63 passed** across 15 test suites (in 7.32s) |
| Frontend TypeScript | ✅ PASS | `tsc --noEmit` — 0 errors |
| Frontend build | ✅ PASS | Vite 5 production bundle (260 kB JS / 22 kB CSS) |
| Playwright E2E | ✅ PASS | **11 passed** in 7.58s against backend :8001 / frontend :3001 |
| Production Security Audit | ✅ PASS | Zero high severity vulnerabilities; AST dangerous calls clean; secrets clean |
