# Microtasks Breakdown

## Phase 1: Setup & Discovery
1. Create venv and install dependencies (30 min) ✅
2. Create directory structure (20 min) ✅
3. Setup logging system (20 min) ✅
4. Setup configuration system (30 min) ✅
5. Create Docker file (20 min) ✅
6. Setup git and .gitignore (10 min) ✅
7. Create test infrastructure (20 min) ✅
8. Verify build and test discovery (10 min) ✅

**Total:** 8 tasks, completed.

---

## Phase 2: Core Crawler
1. Refactor `src/utils` package with backward-compatible exports (20 min) ✅
2. Implement URL utilities (normalize, validate, extract domain, hash) (30 min) ✅
3. Implement `URLFrontier` with priority queue & domain politeness (45 min) ✅
4. Implement RFC 9309 `RobotsTxtParser` (longest match & tie-breaking) (45 min) ✅
5. Implement `Fetcher` with SSRF DNS checks & streaming limits (45 min) ✅
6. Implement manual redirect handling & loop detection (30 min) ✅
7. Write offline unit and security tests in `test_crawler.py` (45 min) ✅
8. Run test suite, black, flake8, mypy, and document synchronization (30 min) ✅

**Total:** 8 tasks, completed.

---

## Phase 3: Content Processing & Parser
1. Implement `HTMLParser` using BeautifulSoup4 + lxml with sanitization and deterministic fallbacks (45 min) ✅
2. Implement character truncation limits (title: 200, desc: 500, body: 1,048,576 Unicode characters) (20 min) ✅
3. Implement `TextProcessor` with bundled stop-words, offline regex fallback, and Porter stemmer (35 min) ✅
4. Preserve repeated term frequency in tokens and deduplicated unique vocabulary in terms (20 min) ✅
5. Implement `ContentDeduplicator` with SHA-256 fingerprinting and field separator (25 min) ✅
6. Implement `LinkExtractor` with absolute URL resolution, fragment stripping, and scoring (30 min) ✅
7. Implement `ParserPipeline` and `ParsedDocument` with dictionary subscript compatibility (35 min) ✅
8. Create comprehensive 30-test suite in `tests/test_parser.py` (45 min) ✅
9. Verify quality gates (pytest 77/77 passed, black, flake8, mypy) and synchronize 10 documents (35 min) ✅

**Total:** 9 tasks, completed.

---

## Phase 4: Indexing Engine
1. Create SQLite schema v4.0 with 4 tables, 6 indices, and metadata counters (30 min) ✅
2. Implement `SQLiteIndexer` with WAL mode, foreign keys, and connection lifecycle (`close()`, context manager) (50 min) ✅
3. Implement atomic single-document indexing and document length calculation based on token count (40 min) ✅
4. Implement separate term frequency tracking: raw TF, title_frequency, body_frequency, and positions (30 min) ✅
5. Implement `BM25Ranker` with Robertson-Spärck Jones IDF, field boosting, and length normalization (40 min) ✅
6. Implement `BatchIndexer` with true atomic single-transaction execution and rollback (30 min) ✅
7. Implement consistent deletion with metadata updates, cascade cleanup, and orphaned term removal (30 min) ✅
8. Write comprehensive 44-test suite in `tests/test_indexer.py` with 90% coverage and performance benchmark (50 min) ✅
9. Verify quality gates (pytest 121/121 passed, black, flake8, mypy) and synchronize 8 documents (30 min) ✅

**Total:** 9 tasks, completed.

---

## Phase 5: Ranking & Scoring Engine
1. Implement `ParsedQuery` and `QueryParser` supporting required (`+`), excluded (`-`), exact phrases (`"..."`), field filters (`field:val`), and safety limits (40 min) ✅
2. Implement `SnippetGenerator` with contextual windowing (150–200 chars), word boundary snapping, and markdown bolding (`**term**`) (40 min) ✅
3. Implement `SearchResult` dataclass with full metadata and dictionary serialization (20 min) ✅
4. Implement `SearchEngine` coordinating query parsing, BM25 candidate retrieval, multi-filter post-evaluation, score normalization (0–100%), and autocomplete suggestions (50 min) ✅
5. Implement `EndToEndPipeline` coordinating `URLFrontier`, `Fetcher`, `ParserPipeline`, `SQLiteIndexer`, `BatchIndexer`, and `SearchEngine` (45 min) ✅
6. Create comprehensive 38-test suite in `tests/test_ranker.py` achieving 91% code coverage (50 min) ✅
7. Benchmark query response time verifying sub-100ms response across synthetic corpus (20 min) ✅
8. Verify quality gates (pytest 159/159 passed, black clean, flake8 0 errors, mypy 0 errors) and synchronize 8 documents (35 min) ✅

**Total:** 8 tasks, completed.

---

## Phase 6: Search API & FastAPI Server
1. Extend `ServerConfig` in `src/config.py` with rate limiting, trusted proxies, HSTS, CORS, max offset, and query logging (25 min) ✅
2. Implement Pydantic v2 schemas in `src/api/models.py` (`SearchRequest`, `SearchResultItem`, `SearchResponse`, `SuggestRequest`, `SuggestResponse`, `StatsResponse`, `HealthResponse`, `ErrorResponse`) (40 min) ✅
3. Implement in-memory sliding-window `RateLimiter`, IP trusted proxy extraction, and rate limit responses in `src/api/middleware.py` (45 min) ✅
4. Refactor `SearchEngine` with `search_with_total` and update `SQLiteIndexer` with `check_same_thread=False` for threadpool safety (20 min) ✅
5. Implement dependency injection (`get_indexer`, `get_search_engine`), search GET/POST, suggest, stats, and health endpoints in `src/api/routes.py` (50 min) ✅
6. Implement `create_app` factory in `src/main.py` with lifespan manager, security headers, request ID tracing, and exception handlers (45 min) ✅
7. Create comprehensive 44-test suite in `tests/test_api.py` achieving 91% coverage across `src.api` and `src.main` (55 min) ✅
8. Verify quality gates (pytest 201/201 passed, black clean, flake8 0 errors, mypy 0 errors) and synchronize 8 documents (35 min) ✅

**Total:** 8 tasks, completed.

---

## Phase 7: Frontend Search UI
1. Setup React 18 + Vite 5 + TypeScript strict project configuration (`package.json`, `vite.config.ts`, `tsconfig.json`, `tsconfig.node.json`, `.env.example`) (25 min) ✅
2. Define TypeScript interfaces in `types/index.ts` strictly compatible with Phase 6 Pydantic response models (20 min) ✅
3. Implement `SearchAPIClient` in `api/client.ts` with Axios, environment-driven baseURL, error status normalization, and `AbortSignal` cancellation (35 min) ✅
4. Implement safe snippet highlighting in `utils/highlight.tsx` using React virtual DOM elements (`<mark>`) and text fragments without `dangerouslySetInnerHTML` (25 min) ✅
5. Implement custom hooks: `useTheme` (dark/light + localStorage), `useSuggestions` (300ms debounce, min 2 chars, AbortController), `useSearch` (AbortController), and `usePagination` (45 min) ✅
6. Build accessible React components: `Header`, `SearchBar` (combobox ARIA roles), `Suggestions` (listbox ARIA roles), `SearchResult`, `ResultsList`, and `Pagination` (50 min) ✅
7. Implement React Router URL search state synchronization (`/?q=...&page=...`) and smooth scrolling in `App.tsx` and mount in `main.tsx` (30 min) ✅
8. Create modern CSS design system with Dark/Light CSS variables, gradient cards, and responsive layout $\le 768\text{px}$ (35 min) ✅
9. Create comprehensive 41-test suite in Vitest + Testing Library covering all components, hooks, cancellation, and API mapping (45 min) ✅
10. Verify quality gates (`npm run type-check`, `npm test`, `npm run build`, `pytest`, `black`, `flake8`, `mypy`) and synchronize 8 documents (30 min) ✅

**Total:** 10 tasks, completed.

---

## Phase 8: Admin Dashboard
1. Add `psutil>=5.9.0` to `requirements.txt` and install in Python 3.11 venv (10 min) ✅
2. Define Pydantic v2 schemas in `src/api/admin_models.py` (`CrawlStatus`, `CrawlPriority`, `CrawlRequest`, `CrawlResponse`, `IndexMetrics`, `SystemMetrics`, `LogEntry`, `ConfigUpdateRequest`, `RuntimeConfigResponse`, `AdminHealthResponse`) with strict bounds (30 min) ✅
3. Implement `CrawlManager` in `src/admin/crawl_manager.py` with process-local state machine, `asyncio.Lock`, cooperative pause/resume/stop events, and seed SSRF pre-validation (50 min) ✅
4. Implement `MetricsCollector` in `src/admin/metrics.py` extracting real SQLite statistics and sampling host resource utilization non-blockingly via psutil (30 min) ✅
5. Implement `ConfigService` in `src/admin/config_service.py` with in-memory allowlist for dynamic log level, rate limits, and crawler politeness (30 min) ✅
6. Implement `LogService` in `src/admin/log_service.py` with bounded tail retrieval ($\le 500$ lines) and multi-pattern regex secret/token redaction (30 min) ✅
7. Implement admin routes in `src/api/admin_routes.py` with constant-time token comparison (`secrets.compare_digest`), 401/403 errors, and mount in `src/main.py` lifespan (45 min) ✅
8. Create comprehensive 24-test suite in `tests/test_admin_api.py` covering token security, state transitions, metrics, logs, and config updates (50 min) ✅
9. Implement frontend `AdminAPIClient` in `frontend/src/api/adminClient.ts` with `sessionStorage` token retention, error normalization, and typed endpoints (35 min) ✅
10. Build accessible React components in `frontend/src/components/admin/`: `CrawlManager`, `StatisticsPanel`, `SystemMetrics`, `LogViewer`, and `ConfigManager` (60 min) ✅
11. Build `AdminDashboard.tsx` page with authentication gate, session token verification, tabbed navigation, and link in `Header.tsx` (35 min) ✅
12. Create complete CSS stylesheet in `frontend/src/styles/AdminDashboard.css` with responsive layout and dual-theme variable integration (30 min) ✅
13. Write comprehensive 21-test frontend test suite in Vitest + Testing Library covering all admin components and clients (45 min) ✅
14. Verify all quality gates (`pytest` 225/225, `black`, `flake8`, `mypy`, `npm run type-check`, `npm test` 62/62, `npm run build`) and synchronize 8 documents (35 min) ✅

**Total:** 14 tasks, completed.

---

## Phase 9: Comprehensive Testing & Hardening
1. Configure test tier separation: register `unit`, `integration`, `security`, `e2e`, `performance`, `slow` markers in `pytest.ini`; set `addopts` to exclude e2e, performance, and slow from default run (10 min) ✅
2. Create `.coveragerc` with defensible exclusions only (`pragma: no cover`, `TYPE_CHECKING`, `abstractmethod`, `__main__`) (10 min) ✅
3. Rewrite `tests/conftest.py` with isolated `test_db`, `seeded_indexer` (10 docs), `test_app_with_engine` using `create_app` factory — zero global state mutation (40 min) ✅
4. Create `tests/test_integration.py`: 8 integration tests covering full pipeline, pagination, error handling, concurrency, dedup idempotency, and mock fetch→parse→index→search→API flow (50 min) ✅
5. Create `tests/test_security.py`: 19 security tests covering SQL injection, XSS, payload size, security headers (CSP/X-Content-Type-Options/X-Frame-Options/Referrer-Policy), HSTS policy, CORS, rate limiting with mock clock, admin auth constant-time comparison, SSRF regression, DOS resilience (60 min) ✅
6. Create `tests/test_performance.py`: 4 benchmark suites covering parser throughput, single-doc and batch indexing, query latency p95 (single-term, multi-term, phrase, field-filter), autocomplete latency, SQLite storage overhead ratio; marked `@pytest.mark.performance` and excluded from default run (50 min) ✅
7. Create `tests/test_e2e.py`: 10 Playwright E2E browser scenarios using accessible ARIA role selectors; marked `@pytest.mark.e2e` and excluded from default run (50 min) ✅
8. Create `tests/load/locustfile.py`: Locust load test with explicit LOAD_TEST_HOST safety validation, ALLOW_REMOTE_LOAD_TEST guard, weighted tasks (search:7, suggest:2, stats:1), timestamped JSON report output (40 min) ✅
9. Create `scripts/seed_e2e_db.py`: Controlled E2E test database seeder (16 documents) for deterministic Playwright tests (20 min) ✅
10. Install Playwright Chromium (`python -m playwright install chromium`) and Locust (30 min) ✅
11. Run Black formatter on all 8 non-conforming source/test files; verify `black --check src tests` passes (15 min) ✅
12. Run Flake8; fix F401 (unused imports in test_security), F541 (f-string without placeholder), F841 (unused variable in test_e2e), E501 (long lines in test_performance, test_integration, test_e2e); set max-line-length=99 to match Black's string-literal behavior (20 min) ✅
13. Verify `mypy src` — 0 issues in 34 source files (10 min) ✅
14. Verify `npm run type-check --prefix frontend` — 0 TypeScript errors (10 min) ✅
15. Verify `npm run build --prefix frontend` — production Vite bundle (260 kB JS, 22 kB CSS) (10 min) ✅
16. Verify frontend Vitest — 62 tests passed across 15 suites (10 min) ✅
17. Measure backend coverage: **86.08% total** (≥80% gate PASS); HTML report in `htmlcov/`, XML in `coverage.xml` (15 min) ✅
18. Create `scripts/run_fast_tests.ps1/.sh` — fast deterministic backend regression runner (15 min) ✅
19. Create `scripts/run_coverage.ps1/.sh` — backend coverage with ≥80% threshold enforcement (15 min) ✅
20. Create `scripts/run_benchmarks.ps1/.sh` — isolated performance benchmark runner (10 min) ✅
21. Create `scripts/run_e2e_tests.ps1/.sh` — E2E runner: starts backend :8001 + frontend :3001, waits for readiness, runs Playwright, tears down via try/finally / trap (30 min) ✅
22. Create `scripts/run_load_tests.ps1/.sh` — Locust runner: explicit LOAD_TEST_HOST or own server on :8099, safety guard, timestamped CSV, threshold evaluation (30 min) ✅
23. Create `scripts/run_all_quality.ps1/.sh` — master gate runner: Black → Flake8 → Mypy → Backend → Coverage → TypeScript → Build → Vitest in sequence with summary (20 min) ✅
24. Update `docs/13_TESTING.md` with actual test counts, tier table, runner scripts, measured gate results (15 min) ✅
25. Update `docs/15_MICROTASKS.md` — Phase 9 section (10 min) ✅
26. Update `docs/16_CHANGELOG.md` — Phase 9 entry (15 min) ✅
27. Update `docs/17_DECISIONS.md` — Phase 9 ADRs D026–D031 (20 min) ✅

**Total:** 27 tasks, completed.

---

## Phase 10: Production Security Audit & Hardening
1. Resolve Bandit B324 in `src/parser/dedup.py` by specifying `usedforsecurity=False` with explicit documentation for non-cryptographic content fingerprinting (10 min) ✅
2. Update `src/config.py` with `environment: str = "development"`, implement `normalize_environment()` with deterministic production precedence, and wire into `load_config()` (15 min) ✅
3. Implement production startup security failsafe in `src/main.py:lifespan`: validate `admin_token` >= 32 chars, >= 4 unique chars, not dev default, and abort before socket binding without logging secret value (20 min) ✅
4. Update `verify_admin_token` in `src/api/admin_routes.py` to enforce production entropy and constant-time `secrets.compare_digest()` (15 min) ✅
5. Harden `get_client_ip` in `src/api/middleware.py` with RFC 7239 right-to-left traversal of `X-Forwarded-For` against configured `trusted_proxies` (15 min) ✅
6. Configure `requirements-dev.txt` for `pip-audit` and `bandit`, keeping production `requirements.txt` clean (10 min) ✅
7. Enforce strict `max-line-length = 88` in `.flake8` and reformat all lines in `tests/` and `src/` to <= 88 characters (20 min) ✅
8. Create `scripts/security_ast_audit.py` to inspect AST for dangerous primitives (`eval`, `exec`, `pickle`, `shell=True`, dynamic SQL) (25 min) ✅
9. Create `scripts/security_secret_scan.py` to scan for unmasked private keys, AWS/GitHub/Slack tokens, and committed real credentials (25 min) ✅
10. Create `scripts/security_scan.py`, `scripts/run_security_scan.ps1`, and `scripts/run_security_scan.sh` multi-scanner aggregators with 0/1/2 exit semantics (30 min) ✅
11. Create comprehensive regression suite `tests/test_security_regression.py` (14 tests) covering pure text search queries, log service confinement, SQL injection safety, XSS data handling, SSRF blocks, admin token hardening, brute-force rate limiting with mock clock, and XML/XXE rejection (60 min) ✅
12. Add frontend XSS regression test in `frontend/src/components/__tests__/SearchResult.test.tsx` verifying text-only rendering and 0 executable DOM nodes (15 min) ✅
13. Fix Windows IPv6 localhost delay in `scripts/run_e2e_tests.ps1`, add `CORS_ORIGINS` and `DATABASE_PATH` overrides, and verify all 11 Playwright E2E tests pass (30 min) ✅
14. Rewrite `docs/10_SECURITY.md` with comprehensive OWASP Top 10 (2021) control matrix, secret policy, and supply-chain triage (45 min) ✅
15. Update core documentation: `docs/00_MASTER_RULES.md`, `docs/02_TRD.md`, `docs/03_ARCHITECTURE.md`, `docs/09_ERROR_HANDLING.md`, `docs/13_TESTING.md`, `docs/15_MICROTASKS.md`, `docs/16_CHANGELOG.md`, `docs/17_DECISIONS.md` (ADRs D032–D034) (35 min) ✅

**Total:** 15 tasks, completed.

---

## Phase 11: Measurement-Driven Performance Optimization
1. Implement persistent index generation counter (`_index_generation`) in SQLite `metadata` table, initialize in `src/indexer/schema.sql`, and expose via `get_generation()` on `SQLiteIndexer` (20 min) ✅
2. Advance persistent index generation transactionally on committed mutations (`add_document`, `delete_document`, `clear_index`, and `BatchIndexer.flush()`), ensuring rollbacks and duplicate no-ops do not advance generation (25 min) ✅
3. Implement `SQLiteIndexer.get_documents_by_ids(doc_ids, batch_size=500)` with parameterized batching and empty/duplicate handling (20 min) ✅
4. Integrate batch prefetch into measured hot path in `BM25Ranker.rank_documents` (`src/indexer/tfidf.py`), eliminating N+1 `get_document(doc_id)` calls while strictly preserving BM25 ranking semantics and tie-breaking (30 min) ✅
5. Integrate batch prefetch into measured hot path in `SearchEngine.search_with_total` (`src/ranker/search.py`), eliminating secondary candidate document lookup loop while preserving filter semantics and snippet generation (20 min) ✅
6. Create thread-safe in-memory `LRUCache` (`src/cache/cache_layer.py`) with monotonic clock injection, collision-free tuple keys `(generation, clean_query, limit, offset)`, TTL expiry, and LRU eviction (35 min) ✅
7. Integrate `LRUCache` into service layer in `_execute_search_service` (`src/api/routes.py`), attaching `X-Cache: HIT` / `X-Cache: MISS` headers and returning fresh response copies without mutating cached objects (30 min) ✅
8. Initialize `search_cache` and `performance_metrics` in `app.state` within application factory lifespan and pre-startup dependencies (`src/main.py`) (20 min) ✅
9. Create `src/monitoring/metrics.py` with bounded rolling window (`collections.deque(maxlen=1000)`) computing p50/p95/p99 query percentiles, cache hit rate, and threshold alerts with zero raw query text stored (30 min) ✅
10. Create `src/db/query_optimizer.py` and `src/db/optimizer.py` for safe query plan analysis and administrative offline PRAGMA inspection/maintenance (25 min) ✅
11. Create dedicated operator maintenance CLI `scripts/optimize_database.py` with safety warnings and operator confirmation prompts for `VACUUM` and `REINDEX` (25 min) ✅
12. Create unit and integration test suite `tests/test_cache.py` (12 tests) verifying cache hit/miss, controllable TTL clock, bounded eviction, MRU promotion, disabled mode, generation isolation, concurrency safety, and HTTP API caching (35 min) ✅
13. Create unit test suite `tests/test_db_optimizer.py` (8 tests) verifying restart persistence, duplicate no-op non-advancement, batch flush single increment, prefetch chunking, explain query plans, and maintenance execution (30 min) ✅
14. Create unit test suite `tests/test_monitoring.py` (6 tests) verifying bounded window size, empty/single sample percentiles, uniform distribution quantiles, privacy guarantees, concurrency, and alert thresholding (25 min) ✅
15. Create reproducible benchmark harness `scripts/benchmark.py` measuring single vs batch writes, batch prefetch vs N+1 lookups, uncached vs cached query latencies, and generation invalidation lifecycle (30 min) ✅
16. Verify 100% passing quality gates: 291 backend tests, 86.44% coverage (>=80% gate), 33 security tests, `security_scan.py` clean, Black formatting, Flake8 88-char ceiling, Mypy type-check, 63 frontend Vitest tests, TypeScript check, production build, and 11 Playwright E2E browser tests (35 min) ✅
17. Synchronize core architecture documentation: `docs/00_MASTER_RULES.md`, `docs/02_TRD.md`, `docs/03_ARCHITECTURE.md`, `docs/09_ERROR_HANDLING.md`, `docs/13_TESTING.md`, `docs/15_MICROTASKS.md`, `docs/16_CHANGELOG.md`, `docs/17_DECISIONS.md` (ADRs D036–D038) (40 min) ✅

**Total:** 17 tasks, completed.

---

### Phase 12: Production Deployment & Operational Readiness

1. Add `prometheus-client>=0.20.0` to `requirements.txt` and install into environment (15 min) ✅
2. Implement `src/monitoring/prometheus_exporter.py` with application-owned `CollectorRegistry` and HTTP/cache/index metrics (25 min) ✅
3. Integrate centralized HTTP request middleware tracking in `src/main.py` with normalized route templates (`/api/v1/search`, `/health`, `"unmatched"` on 404) (30 min) ✅
4. Add authoritative search cache hit/miss increments to `src/api/routes.py` and implement `GET /metrics` Prometheus endpoint (20 min) ✅
5. Implement SPA static asset fallback in `src/main.py` preserving API route isolation and path traversal defense (25 min) ✅
6. Create test suite `tests/test_prometheus.py` (8 tests) covering Prometheus exposition, route normalization, cache counters, privacy, and SPA confinement (30 min) ✅
7. Implement `scripts/backup_database.py` with live WAL backup API, SHA-256 digests, `PRAGMA integrity_check`, non-destructive restore sandbox, and safe retention purge (35 min) ✅
8. Create test suite `tests/test_backup.py` (7 tests) verifying backup creation, checksums, corruption detection, sandbox restore smoke search, concurrent WAL writes, and retention purging (30 min) ✅
9. Create production multi-stage `Dockerfile` with Node 20 builder, Python 3.11 wheel builder, and non-root `appuser` (UID 1000) runtime (30 min) ✅
10. Create `.dockerignore` excluding caches, venvs, test data, and temporary files (15 min) ✅
11. Create `.env.production.example` configuration template with minimum 16-char token instructions (15 min) ✅
12. Create `docker-compose.yml` with API, Prometheus v2.51.0, and Grafana v10.4.0 (zero Redis, zero node_exporter, zero Alertmanager) (25 min) ✅
13. Create Kubernetes manifests in `k8s/`: `deployment.yaml` (`replicas: 1`, `strategy: Recreate`), `service.yaml`, `pvc.yaml` (`search-engine-data-pvc`), `configmap.yaml`, `secret.yaml.example`, `ingress.yaml` (blocking `/metrics`), and `networkpolicy.yaml` (35 min) ✅
14. Create Prometheus & Grafana configurations in `monitoring/`: `prometheus.yml`, `alerts.yml`, datasource and dashboard provisioning (30 min) ✅
15. Create runner scripts: `scripts/backup-database.sh`, `scripts/backup-database.ps1`, `scripts/production-test.sh`, `scripts/production-test.ps1`, `scripts/production_smoke_test.py` (25 min) ✅
16. Create `.github/workflows/deploy.yml` with 3-job pipeline: `test` (all quality gates), `build` (Docker multi-stage & container smoke), `deploy` (Kubernetes rollout & rollback) (35 min) ✅
17. Create root `DEPLOYMENT.md` and `PRODUCTION_CHECKLIST.md` with explicit status indicators (`PASS`, `MANUAL REQUIRED`) (30 min) ✅
18. Synchronize all 18 core documentation files in `docs/` and add ADRs D039, D040, D041 in `docs/17_DECISIONS.md` (35 min) ✅

**Total:** 18 tasks, completed.




