# Changelog

## Phase 1 - Setup & Discovery
- ✅ Initialized Python 3.11 project and virtual environment
- ✅ Created directory structure for crawler, parser, indexer, ranker, and frontend
- ✅ Setup dual console & rotating file logging system with automatic directory creation
- ✅ Setup YAML + .env configuration with precedence (Env > YAML > Defaults)
- ✅ Created Dockerfile with stdlib healthcheck
- ✅ Setup pytest infrastructure with unit, integration, security, and performance markers
- ✅ Created .gitignore (including config.yaml and data/)
- ✅ Configured Black and Mypy via pyproject.toml
- ✅ Created 18 documentation files (8 core, 10 templates)
- ✅ Verified Phase 1 tests, CLI, formatting, and linting

---

## Phase 2 - Core Crawler
- ✅ Refactored `src/utils.py` into package `src/utils/` while preserving backward compatibility for `from src.utils import compute_sha256`
- ✅ Implemented `URLFrontier` with `heapq` priority queue, `time.monotonic()` per-domain politeness delay, and separated queued/in-flight/crawled state tracking
- ✅ Implemented RFC 9309 compliant `RobotsTxtParser` supporting longest matching pattern evaluation, Allow-over-Disallow tie-breaking, and Crawl-delay extensions
- ✅ Implemented async streaming `Fetcher` with `FetchResult` dataclass supporting typed attributes and backward-compatible tuple unpacking
- ✅ Implemented hardened SSRF defense blocking loopback, private IPv4, IPv6 loopback, link-local, multicast, unspecified, and DNS resolution to private addresses
- ✅ Implemented manual redirect handling with 5-hop cap, loop detection, and per-hop SSRF validation
- ✅ Implemented wire size (10MB) and decompression bomb (50MB) streaming guards
- ✅ Implemented 40 deterministic, offline unit and security tests in `tests/test_crawler.py`
- ✅ Passed pytest (47 passed), Black, Flake8, and Mypy checks

**Status:** Phase 2 Complete ✅

---

## Phase 3 - Content Processing & Parser
- ✅ Implemented `HTMLParser` (`src/parser/__init__.py`) using BeautifulSoup4 + `lxml` with non-content tag decomposition (`script`, `style`, `noscript`, `nav`, `footer`, `template`, `header`, `aside`)
- ✅ Implemented deterministic fallback chains for title (`title` → `og:title` → `h1`), description (`og:description` → `meta[name=description]`), body (`article` → `main` → `body`), and publication date (`itemprop="datePublished"` → `og:published_time` → `<time datetime>` → `meta[name=pubdate]`)
- ✅ Implemented normalized Unicode character truncation limits: Title (200 chars), Description (500 chars), Body (1,048,576 chars)
- ✅ Implemented offline-first `TextProcessor` (`src/parser/text.py`) with bundled 179 English stop-words, offline regex fallback tokenizer, and Porter stemmer
- ✅ Preserved raw term frequency in `tokens` list for BM25 ranking while providing unique deduplicated vocabulary in `terms`
- ✅ Implemented `ContentDeduplicator` (`src/parser/dedup.py`) using SHA-256 fingerprinting with distinct field separator `\n---BODY---\n` and safe parse-commit lifecycle
- ✅ Implemented `LinkExtractor` (`src/parser/linker.py`) with absolute URL resolution, fragment stripping, same-domain filtering, and depth/domain priority scoring
- ✅ Implemented `ParserPipeline` and `ParsedDocument` (`src/parser/integration.py`) with dictionary subscript access compatibility (`doc["key"]` / `doc.get(...)`) and duplicate suppression (returning `None`)
- ✅ Implemented 30 deterministic offline unit and integration tests in `tests/test_parser.py`
- ✅ Passed entire test suite (77 passed, 5 skipped) with zero warnings or failures
- ✅ Verified full code formatting, Flake8 compliance, and Mypy static typing across all 18 source files

**Status:** Phase 3 Complete ✅

---

## Phase 4 - Indexing Engine
- ✅ Implemented SQLite schema v4.0 (`src/indexer/schema.sql`) with `documents`, `terms`, `postings`, `metadata`, and 6 performance indices.
- ✅ Implemented `SQLiteIndexer` (`src/indexer/__init__.py`) with `PRAGMA foreign_keys = ON`, `PRAGMA journal_mode = WAL`, and `busy_timeout = 5000`.
- ✅ Implemented public lifecycle management (`close()`, `__enter__`, `__exit__`) and automatic migration from legacy unversioned schemas.
- ✅ Supported both Phase 3 `ParsedDocument` instances and dictionaries through an internal normalization adapter.
- ✅ Implemented document length calculation based on processed token count (`document_length INTEGER NOT NULL DEFAULT 0`).
- ✅ Separated term frequencies in `postings`: raw total `term_frequency`, `title_frequency`, `body_frequency`, and JSON-serialized `positions`.
- ✅ Implemented `BM25Ranker` (`src/indexer/tfidf.py`) with Robertson-Spärck Jones IDF `log(1.0 + (N - df + 0.5) / (df + 0.5))` and backward-compatible alias `TFIDFRanker = BM25Ranker`.
- ✅ Implemented dynamic field boosting (`title_boost=2.0`, `body_boost=1.0`) and document length normalization via $O(1)$ metadata lookup.
- ✅ Implemented `BatchIndexer` (`src/indexer/batch.py`) with atomic single-transaction execution and complete rollback on failure.
- ✅ Implemented consistent document deletion (`delete_document`) with DF/CF decrements, metadata updates, and orphaned term cleanup.
- ✅ Created comprehensive 44-test suite in `tests/test_indexer.py` achieving 90% test coverage and verified >50 docs/sec throughput benchmark.
- ✅ Verified entire project test suite (121 passed, 4 skipped) with zero warnings or failures.
- ✅ Verified formatting, Flake8 compliance, and Mypy static typing across all 20 source files.

**Status:** Phase 4 Complete ✅

---

## Phase 5 - Ranking & Scoring Engine
- ✅ Implemented `ParsedQuery` and `QueryParser` (`src/ranker/__init__.py`) with full syntax support: required (`+term`), excluded (`-term`), exact phrases (`"phrase"`), and metadata field filters (`field:val`).
- ✅ Enforced strict query safety limits (max 500 characters, max 100 terms, max 50 characters per term) and defensive normalization.
- ✅ Implemented `SnippetGenerator` (`src/ranker/snippets.py`) with contextual windowing (150–200 characters), word boundary snapping, markdown bold highlighting (`**term**`), and sentence context extraction (`extract_context`).
- ✅ Implemented `SearchResult` dataclass (`src/ranker/search.py`) with raw BM25 score, normalized percentage relevance score (`0–100%`), and dictionary serialization.
- ✅ Implemented `SearchEngine` (`src/ranker/search.py`) coordinating query parsing, BM25 candidate retrieval with stemmed variant vocabulary expansion, multi-filter post-evaluation, and autocomplete suggestions (`get_suggestions`).
- ✅ Implemented `EndToEndPipeline` (`src/ranker/pipeline.py`) integrating `URLFrontier`, `Fetcher`, `ParserPipeline`, `SQLiteIndexer`, `BatchIndexer`, and `SearchEngine`.
- ✅ Created comprehensive 38-test suite in `tests/test_ranker.py` achieving 91% code coverage on `src.ranker`.
- ✅ Benchmarked query performance verifying sub-100ms response time per query across synthetic corpus.
- ✅ Passed entire project test suite (159 passed, 3 skipped) with zero warnings or failures.
- ✅ Verified formatting, Flake8 compliance, and Mypy static typing across all 23 source files.

**Status:** Phase 5 Complete ✅

---

## Phase 6 - Search API & FastAPI Server
- ✅ Extended `ServerConfig` (`src/config.py`) with `rate_limit_per_minute`, `trusted_proxies`, `enable_hsts`, `cors_origins`, `max_offset`, `log_queries`, and dictionary `.get()` compatibility across all config classes.
- ✅ Implemented Pydantic v2 schemas (`src/api/models.py`) with strict field validators: `SearchRequest`, `SearchResultItem`, `SearchResponse`, `SuggestRequest`, `SuggestResponse`, `StatsResponse`, `HealthResponse`, `ErrorResponse`.
- ✅ Implemented in-memory sliding-window `RateLimiter` (`src/api/middleware.py`) with per-client timestamp tracking, `Retry-After` calculation, standard `X-RateLimit-*` headers, lazy stale bucket eviction, and trusted proxy IP extraction policy.
- ✅ Enhanced `SearchEngine` (`src/ranker/search.py`) with `search_with_total` returning `(results, total_available, error)` for exact pagination totals, and enabled `check_same_thread=False` in `SQLiteIndexer` for threadpool concurrency.
- ✅ Implemented FastAPI route handlers (`src/api/routes.py`) with dependency injection (`get_indexer`, `get_search_engine`), supporting POST and GET `/api/v1/search`, `/api/v1/suggest`, `/api/v1/stats`, `/api/v1/health`, and legacy aliases (`/api/search`, `/api/suggest`, `/api/stats`, `/api/health`, `/health`, `/`).
- ✅ Implemented FastAPI application factory `create_app` (`src/main.py`) with asynchronous lifespan context manager, request ID propagation (`X-Request-ID`), high-resolution latency logging, security headers (`nosniff`, `DENY`, `no-referrer`, `CSP`, conditional `HSTS`), CORS middleware, and structured exception handlers (400, 404, 422, 429, 500, 503) ensuring zero internal trace leaks.
- ✅ Implemented 44 deterministic offline tests in `tests/test_api.py` covering pagination, edge boundaries, rate limiting with controllable mock clock, security headers, XSS prevention in snippets, and error contracts, achieving 91% code coverage on `src.api` and `src.main`.
- ✅ Passed entire project test suite (201 passed, 3 skipped) with zero warnings or failures.
- ✅ Verified formatting (Black), linting (Flake8 0 errors), and static typing (Mypy 0 errors) across all 27 source files.

**Status:** Phase 6 Complete ✅

---

## Phase 7 - Frontend Search UI
- ✅ Initialized modern React 18, Vite 5, and TypeScript 5 (strict mode) frontend architecture in `frontend/`.
- ✅ Configured Vite environment variable support (`VITE_API_BASE_URL`) with fallback to `/api/v1` and development reverse proxy to backend `http://localhost:8000`.
- ✅ Implemented strongly typed API client `SearchAPIClient` (`src/api/client.ts`) with Axios, supporting native `AbortSignal` for request cancellation and human-friendly mapping of 422, 429 (with `Retry-After`), 500, 503, and network offline states.
- ✅ Implemented safe snippet keyword highlighting `renderSafeSnippet` (`src/utils/highlight.tsx`) parsing backend `**term**` tags into React `<mark>` elements, completely eliminating `dangerouslySetInnerHTML`.
- ✅ Implemented custom hooks: `useSearch` (with in-flight AbortController cancellation), `useSuggestions` (with 300ms debounce, minimum 2 characters, AbortController, and arrow key navigation), `usePagination` (offset calculation, smooth page-change scrolling), and `useTheme` (Dark/Light mode with system fallback and `localStorage` persistence).
- ✅ Built accessible UI components with full WCAG 2.1 AA keyboard support and ARIA semantics: `Header` (readiness status, metrics, theme toggle), `SearchBar` (`combobox`), `Suggestions` (`listbox`), `SearchResult` (relevance pill, domain, highlighted snippet, score), `ResultsList` (spinner loading, error alert, empty state, polite screen reader updates), and `Pagination` (windowed pages, active `aria-current`).
- ✅ Integrated React Router with bidirectional URL search parameter synchronization (`/?q=...&page=...`), resetting to page 1 on new query submissions and supporting bookmarking and browser history back/forward traversal.
- ✅ Created responsive CSS design system with CSS custom properties (`variables.css`), dark and light theme palettes, responsive cards, and mobile viewports ($\le 768\text{px}$).
- ✅ Created 41 deterministic frontend unit and integration tests in Vitest + Testing Library achieving 100% pass rate.
- ✅ Verified TypeScript type checking (`tsc --noEmit`), Vitest suite (41/41 passing), and production Vite bundle build (`dist/`).
- ✅ Verified zero regressions across backend test suite (201 passed, 3 skipped), Black, Flake8, and Mypy.

**Status:** Phase 7 Complete ✅

---

## Phase 8 - Admin Dashboard
- ✅ Added `psutil>=5.9.0` to `requirements.txt` and verified installation in Python 3.11 environment.
- ✅ Implemented Pydantic v2 schemas in `src/api/admin_models.py` (`CrawlStatus`, `CrawlPriority`, `CrawlRequest`, `CrawlResponse`, `IndexMetrics`, `SystemMetrics`, `LogEntry`, `ConfigUpdateRequest`, `RuntimeConfigResponse`, `AdminHealthResponse`) with strict input limits (1–10 seeds, max 2048 chars, 1–10000 docs, 1–5 depth).
- ✅ Implemented `CrawlManager` (`src/admin/crawl_manager.py`) coordinating background crawl tasks, `asyncio.Lock` state machine (`idle`, `running`, `paused`, `stopped`, `error`), cooperative pause/stop events, SSRF seed validation, and `BatchIndexer` flushing.
- ✅ Implemented `MetricsCollector` (`src/admin/metrics.py`) returning genuine SQLite metadata table metrics, database file size, and non-blocking `psutil` CPU/memory/disk utilization with zero placeholder metrics.
- ✅ Implemented `ConfigService` (`src/admin/config_service.py`) with strict runtime allowlist (`log_level`, `rate_limit_per_minute`, `crawler_max_depth`, `crawler_politeness_delay`), in-memory updates, and dynamic logger level propagation.
- ✅ Implemented `LogService` (`src/admin/log_service.py`) providing bounded tail inspection ($\le 500$ lines), level filtering, and automatic regex redaction of tokens, secrets, API keys, passwords, and authorization headers (`***REDACTED***`).
- ✅ Implemented token-protected admin endpoints in `src/api/admin_routes.py` with constant-time token comparison (`secrets.compare_digest`), 401/403 errors, 409 conflict checks, and dependency injection from `app.state`.
- ✅ Integrated admin router and services into `src/main.py` lifespan with graceful background crawl cancellation on server shutdown.
- ✅ Built dedicated frontend `AdminAPIClient` (`frontend/src/api/adminClient.ts`) storing tokens exclusively in `sessionStorage` and attaching headers only to `/api/v1/admin/*`.
- ✅ Built accessible admin components in `frontend/src/components/admin/`: `CrawlManager` (live progress polling), `StatisticsPanel` (metrics cards, double-confirmation "CLEAR" modal), `SystemMetrics` (resource gauges), `LogViewer` (safe React text rendering, level badges), and `ConfigManager` (runtime parameter updates with restart warnings).
- ✅ Implemented `AdminDashboard.tsx` page with authentication gate, session verification, tab navigation, and navigation link in `Header.tsx`.
- ✅ Designed responsive modern styling in `frontend/src/styles/AdminDashboard.css` with dark/light theme integration.
- ✅ Created 24 backend tests in `tests/test_admin_api.py` covering token auth, SSRF rejection, state transitions, metrics, logs, and config.
- ✅ Created 21 frontend tests in Vitest + Testing Library covering `AdminAPIClient`, `AdminDashboard`, and all admin components.
- ✅ Verified 100% passing tests: **225 backend tests passed** (3 skipped placeholders) and **62 frontend tests passed**.
- ✅ Verified zero linting or static typing errors: Black clean, Flake8 clean (0 errors), Mypy clean (0 errors), TypeScript clean (`tsc --noEmit`), and Vite production build clean (`npm run build`).

**Status:** Phase 8 Complete ✅

---

## Phase 9 � Comprehensive Testing & Hardening
- Configured test tier separation in `pytest.ini`: registered 6 markers (unit, integration, security, e2e, performance, slow); default addopts excludes e2e, performance, and slow from normal regression runs.
- Created `.coveragerc` with only defensible exclusions: `pragma: no cover`, `TYPE_CHECKING`, `abstractmethod`, `__main__` guards.
- Rewrote `tests/conftest.py` with isolated fixtures: `test_db` (temp SQLite), `seeded_indexer` (10 deterministic docs), `test_app_with_engine` using `create_app` factory � zero global state mutation.
- Created `tests/test_integration.py` (8 @pytest.mark.integration tests): full pipeline mock fetch->parse->dedup->index->search->API, pagination, concurrency via thread pool, data dedup idempotency, error handling.
- Created `tests/test_security.py` (19 @pytest.mark.security tests): SQL injection (schema integrity verified), XSS payload safety, 422 payload size contract (100k chars), security headers (CSP/X-Content-Type-Options/X-Frame-Options/Referrer-Policy/X-XSS-Protection), HSTS conditional, CORS, rate limiting with mock clock injection, admin auth 401/403, secrets.compare_digest verified, SSRF regression, DOS resilience.
- Created `tests/test_performance.py` (4 @pytest.mark.performance benchmarks): parser throughput (676 docs/sec), single-doc (824/sec), batch (2815/sec), query latency p95 (single-term: 1.03ms, multi-term: 4.86ms, phrase: 4.55ms, field-filtered: 0.69ms), autocomplete median 0.01ms, SQLite overhead ratio 11x.
- Created `tests/test_e2e.py` (10 @pytest.mark.e2e scenarios): page load, basic search, pagination, autocomplete keyboard navigation, empty/error/loading states with ARIA role selectors.
- Created `tests/load/locustfile.py`: explicit LOAD_TEST_HOST validation, ALLOW_REMOTE_LOAD_TEST guard, weighted tasks (search:7, suggest:2, stats:1), timestamped CSV output.
- Created `scripts/seed_e2e_db.py`: deterministic E2E seeder (16 docs) into `data/e2e_test.db`.
- Installed Playwright Chromium and Locust 2.46.5.
- Applied Black formatting; fixed Flake8 F401/F541/F841/E501; set max-line-length=99; mypy 0 issues in 34 source files.
- Verified npm type-check (0 errors), npm build (260 kB JS, 22 kB CSS), npm test (62 passed/15 suites).
- Measured backend coverage: 86.08% total (gate: >=80% PASS).
- Created 6 runner script pairs (PowerShell + Bash): run_fast_tests, run_coverage, run_benchmarks, run_e2e_tests, run_load_tests, run_all_quality.
- Backend regression: 251 passed, 16 deselected (e2e/performance/slow).

**Status:** Phase 9 Complete ✅

---

## Phase 10 — Production Security Audit & Hardening
- ✅ Resolved Bandit B324 in `src/parser/dedup.py` by specifying `usedforsecurity=False` on `hashlib.md5()` with explicit non-cryptographic content fingerprinting documentation.
- ✅ Extended `ServerConfig` (`src/config.py`) with `environment: str = "development"`, implemented `normalize_environment(env_vars)` with deterministic production precedence, and wired into `load_config()`.
- ✅ Implemented production startup security failsafe in `src/main.py:lifespan`: validates `admin_token` exists, is ≥ 32 characters, contains ≥ 4 distinct characters, and is not the dev default. Raises `RuntimeError` without logging secret values.
- ✅ Hardened `verify_admin_token` in `src/api/admin_routes.py` to enforce production entropy and constant-time `secrets.compare_digest()`.
- ✅ Hardened `get_client_ip` in `src/api/middleware.py` with RFC 7239 compliant right-to-left traversal of `X-Forwarded-For` against configured `trusted_proxies`.
- ✅ Isolated security audit tools (`pip-audit`, `bandit`) in `requirements-dev.txt`, preserving clean production runtime dependencies.
- ✅ Restored strict `max-line-length = 88` in `.flake8` and reformatted all lines in `src/` and `tests/`.
- ✅ Built automated security scanners:
  - `scripts/security_ast_audit.py`: AST analyzer checking for `eval`, `exec`, `pickle`, `yaml.load` without SafeLoader, `subprocess(shell=True)`, `os.system`, and dynamic SQL formatting (0 dangerous calls found).
  - `scripts/security_secret_scan.py`: Secret scanner checking for private keys, AWS/GitHub/Slack tokens, and unmasked credentials (0 exposed secrets found).
  - `scripts/security_scan.py`, `scripts/run_security_scan.ps1`, `scripts/run_security_scan.sh`: Multi-scanner aggregators with 0/1/2 exit code semantics.
- ✅ Created `tests/test_security_regression.py` (14 tests) validating pure text search queries, log service boundary confinement, SQL injection safety, XSS data handling, crawler SSRF blocks, admin auth hardening, rate limiting with mock clock, and XML/XXE rejection.
- ✅ Added frontend XSS regression test in `frontend/src/components/__tests__/SearchResult.test.tsx` verifying text-only rendering and 0 executable DOM nodes (63/63 frontend Vitest tests pass).
- ✅ Resolved Windows IPv6 localhost delay, added `DATABASE_URL` alias and `CORS_ORIGINS` override in `src/config.py`, and verified 100% pass rate (**11/11 passed**) on Playwright E2E browser tests (`scripts/run_e2e_tests.ps1`).
- ✅ Measured Quality Gate Results:
  - Backend regression: **265 passed**, 16 deselected in 20.94s
  - Backend coverage: **86.10%** total (≥80% gate PASS)
  - Black formatting: 50 files unchanged
  - Flake8 lint: 0 errors (strict `max-line-length=88`)
  - Mypy static typing: 0 issues in 34 source files
  - Frontend Vitest: 63 passed across 15 suites in 7.14s
  - Frontend TypeScript: `tsc --noEmit` — 0 errors
  - Frontend production build: Vite 5 bundle (260 kB JS / 22 kB CSS)
  - Playwright E2E: 11 passed in 14.72s against backend :8001 / frontend :3001
  - Security audit: Zero blocking vulnerabilities
- ✅ Rewrote `docs/10_SECURITY.md` with comprehensive OWASP Top 10 (2021) control matrix, secret policy, and supply-chain triage.

**Status:** Phase 10 Complete ✅

---

## Phase 11 — Measurement-Driven Performance Optimization
- ✅ Empirically profiled search and indexing pipelines using deterministic seeded benchmark harness (`scripts/benchmark.py`):
  - Document retrieval: Sequential N+1 lookups (50 docs) took p50 = 0.341ms; batch prefetch took p50 = 0.119ms (**2.9x speedup**; 50 SQL roundtrips reduced to 1).
  - Ingestion throughput: Single-doc writes yielded 665.0 docs/sec; `BatchIndexer` yielded 2,151.7 docs/sec (**3.24x speedup**).
  - Query latency: Uncached p50 = 0.456ms – 1.661ms; Cached p50 = **< 0.001ms** (in-memory LRU hit).
  - Verified index utilization via `EXPLAIN QUERY PLAN` showing zero table scans on candidate lookups (`sqlite_autoindex_terms_1`, `sqlite_autoindex_postings_1`, primary key `rowid`).
- ✅ Implemented persistent transactional `index_generation` counter (`src/indexer/`):
  - Schema initialization in `metadata` table (`'index_generation', '1'`).
  - Added `get_generation()` and internal transactional increments on committed writes (`add_document`, `delete_document`, `clear_index`, `BatchIndexer.flush()`).
  - Skipped duplicate documents (by URL or content hash) and rolled-back transactions never increment generation.
- ✅ Integrated parameterized batch document retrieval in hot ranking paths (`src/indexer/`, `src/ranker/`):
  - Implemented `SQLiteIndexer.get_documents_by_ids(doc_ids, batch_size=500)` with chunked parameterized SQL (`WHERE doc_id IN (?, ...)`).
  - Replaced N+1 candidate fetching loops in `BM25Ranker.rank_documents` and `SearchEngine.search_with_total` with batch prefetch.
  - Strictly preserved 100% BM25 ranking semantics, candidate document sets, scores, field boosts, length normalization, and ordering.
- ✅ Implemented service-layer in-memory LRU search cache (`src/cache/`):
  - Created `CacheConfig`, `CacheEntry`, and thread-safe `LRUCache` using `collections.OrderedDict` and `threading.Lock()`.
  - Collision-free cache key: `(generation, clean_query.lower(), limit, offset)`.
  - Monotonic clock TTL expiry (default 300s) and MRU capacity eviction (1000 items).
  - Wired into `_execute_search_service` with `X-Cache: HIT` / `X-Cache: MISS` headers and defensive deepcopy immutability. HTTP 400, 422, and 500 errors are never cached.
- ✅ Implemented bounded latency telemetry (`src/monitoring/`):
  - Built `PerformanceMetricsCollector` with fixed-size `collections.deque(maxlen=1000)`.
  - Computes exact p50, p95, p99 percentiles, cache hit rate, and threshold alerts (`PerformanceAlert`).
  - Zero raw search query text logged or retained, upholding privacy guarantees.
- ✅ Built database query inspection and controlled maintenance tooling (`src/db/`, `scripts/`):
  - Implemented `QueryOptimizer` with parameterized query plan inspection (`explain_query`).
  - Implemented `DatabaseOptimizer` wrapping `PRAGMA optimize`, `ANALYZE`, `VACUUM`, and `REINDEX`.
  - Built standalone CLI utility `scripts/optimize_database.py` with operator double-confirmation and backup advisories.
- ✅ Created 26 comprehensive unit and integration tests across 3 new test suites (`tests/`):
  - `tests/test_cache.py` (12 tests): Hit, miss, mock clock TTL expiry, capacity eviction, MRU promotion, disabled flag, generation isolation, concurrency safety, API cache headers, mutation invalidation.
  - `tests/test_db_optimizer.py` (8 tests): Persistent generation across restarts, duplicate no-op non-advancement, batch flush single increment, prefetch chunking, query plans, maintenance operations.
  - `tests/test_monitoring.py` (6 tests): Bounded deque limit (1000), percentiles, concurrency safety, zero query string logging, threshold alerts.
- ✅ Verified 100% passing quality gates:
  - Backend regression: **291 passed**, 16 deselected in 28.65s (`pytest tests/ -m "not e2e and not performance and not slow"`)
  - Backend coverage: **86.44%** total (≥80% gate PASS)
  - Security test suite: **33 passed** in 5.63s (`pytest tests/ -m security`)
  - Security audit scanner: `python scripts/security_scan.py` passed exit code 0 (AST clean, secrets clean, zero high severity findings)
  - Code formatting: Black clean across 66 files
  - Linting: Flake8 clean with strict `max-line-length=88` (0 errors)
  - Static typing: Mypy clean across 41 source files (0 issues)
  - Frontend Vitest: **63/63 passed** across 15 test suites
  - Frontend TypeScript: `tsc --noEmit` clean (0 errors)
  - Frontend production build: Vite 5 bundle (260 kB JS / 22 kB CSS)
  - Playwright E2E: **11/11 passed** in 7.58s against dedicated backend and preview servers

**Status:** Phase 11 Complete ✅

---

## Phase 12: Production Deployment & Operational Readiness

- ✅ Centralized Prometheus Observability Subsystem (`src/monitoring/`, `src/main.py`, `src/api/routes.py`):
  - Created `PrometheusMetrics` in `src/monitoring/prometheus_exporter.py` with an isolated, application-owned `CollectorRegistry`.
  - Added centralized request instrumentation in `request_lifecycle_middleware` measuring `http_requests_total` (counter) and `http_request_duration_seconds` (histogram across 11 buckets) with normalized route template labels (e.g. `/api/v1/search`, `/health`, `"unmatched"` on 404).
  - Instrumented authoritative search cache hits (`search_engine_cache_hits_total`) and misses (`search_engine_cache_misses_total`) at the single execution site in `_execute_search_service()`.
  - Exported database gauges: `search_engine_indexed_documents`, `search_engine_unique_terms`, and `search_engine_index_generation`.
  - Exposed official Prometheus plaintext exposition at `GET /metrics`.
  - Guaranteed absolute telemetry privacy: zero raw search query strings or user identifiers in metric dimensions.
- ✅ Single-Origin Frontend Static Asset Serving & SPA Fallback (`src/main.py`):
  - Mounted production SPA distribution fallback (`serve_spa`) without shadowing API, documentation, health, or metrics routes.
  - Enforced strict directory traversal prevention (`..` blocks with 403 Forbidden). Missing static files with extensions return 404 rather than falling back to `index.html`.
- ✅ Live WAL Consistent SQLite Database Backup Subsystem (`scripts/backup_database.py`):
  - Implemented atomic database snapshots using Python `sqlite3.connect().backup()` API without blocking concurrent reads or writes.
  - Computed and persisted SHA-256 integrity digests in companion `.db.sha256` files.
  - Verified logical database correctness via `PRAGMA integrity_check`.
  - Implemented automated non-destructive restore verification into an isolated temporary workspace (`--verify-restore`), initializing `SQLiteIndexer` and executing smoke queries.
  - Implemented safe expiration purge (`purge_expired_backups`) strictly targeting `index_backup_*.db` files with dry-run support.
- ✅ Hardened Multi-Stage Containerization (`Dockerfile`, `.dockerignore`, `docker-compose.yml`):
  - 3-stage minimal Dockerfile: Node 20 builder, Python 3.11 wheel compiler, and unprivileged runtime (`USER appuser`, UID 1000).
  - Lightweight container healthcheck using Python standard library `urllib` without external curl dependency.
  - Single-host Docker Compose stack with API, Prometheus v2.51.0, and Grafana v10.4.0 (zero Redis, zero node_exporter, zero Alertmanager).
- ✅ Kubernetes Manifests (`k8s/`):
  - `deployment.yaml`: Single application replica (`replicas: 1`) with `strategy: type: Recreate` (ADR D039), hardened securityContext (`runAsNonRoot`, `readOnlyRootFilesystem`), and probes (`startupProbe`, `livenessProbe`, `readinessProbe`).
  - `service.yaml`: ClusterIP on port 8000.
  - `pvc.yaml`: Single ReadWriteOnce `search-engine-data-pvc` (10Gi).
  - `configmap.yaml` & `secret.yaml.example`: Non-secret settings and secret template.
  - `ingress.yaml`: Ingress routing `/` and `/api` while blocking `/metrics`.
  - `networkpolicy.yaml`: Restrictive ingress and egress policies with SSRF perimeter defense.
- ✅ Monitoring & Dashboard Configuration (`monitoring/`):
  - `prometheus.yml`: Authoritative scrape target `api:8000`.
  - `alerts.yml`: Safe zero-denominator alerts for `HighErrorRate` and `HighSearchLatency`.
  - Grafana datasource and dashboard provisioning (`search_engine.json`) displaying request rate, latency percentiles, cache hit rate, and corpus size gauges.
- ✅ Shell & PowerShell Runners:
  - `scripts/backup-database.sh` & `scripts/backup-database.ps1`.
  - `scripts/production-test.sh`, `scripts/production-test.ps1`, `scripts/production_smoke_test.py`.
- ✅ End-to-End CI/CD Pipeline (`.github/workflows/deploy.yml`):
  - 3 sequential jobs: `test` (quality gates, security scanners, unit/integration/frontend/E2E suites), `build` (Docker build, container smoke, GHCR publish), and `deploy` (Kubernetes rollout with automatic rollback).
- ✅ Documentation & Operational Runbooks:
  - Root `DEPLOYMENT.md` and `PRODUCTION_CHECKLIST.md`.
  - Synchronized all 18 documents in `docs/` and added ADRs D039, D040, D041 in `docs/17_DECISIONS.md`.

**Status:** Phase 12 Implementation Complete — Environment-Specific Deployment Verification Required ✅


