# Architectural Decision Records (ADRs)

## D001: Technology Stack
**Status:** Accepted  
**Date:** Phase 1  
**Decision:** Python 3.11 + FastAPI + SQLite  
**Rationale:**
- Python 3.11: Rich ecosystem, fast iteration, strong typing support
- FastAPI: Modern, async, type-safe, automatic OpenAPI documentation
- SQLite: Zero-config, embedded, fast, suitable for local private search engine MVP
**Implications:** Single-machine deployment, easy development, no external DB dependencies

## D002: Configuration Precedence
**Status:** Accepted  
**Date:** Phase 1  
**Decision:** Precedence order: Environment Variables > config.yaml > Dataclass Defaults  
**Rationale:**
- Allows 12-factor app deployment in containerized environments while supporting file-based configuration for local development.

## D003: Logging Architecture
**Status:** Accepted  
**Date:** Phase 1  
**Decision:** Dual console & rotating file logging with automatic directory creation  
**Rationale:**
- Ensures logs are both visible in terminal/container stdout and safely rotated to prevent disk exhaustion.

## D004: robots.txt RFC 9309 Compliance
**Status:** Accepted  
**Date:** Phase 2  
**Decision:** Implement RFC 9309 longest-match semantics and tie-breaking (Allow wins over Disallow on equal length).  
**Rationale:**
- RFC 9309 is the current Internet Standard for robots.txt exclusion protocols.
- Avoids incorrect blanket precedence of Allow or Disallow.
- Crawl-delay and Request-rate are isolated as optional extensions.

## D005: SSRF Defense via DNS Resolution & IP Range Validation
**Status:** Accepted  
**Date:** Phase 2  
**Decision:** Validate URLs by resolving hostnames to all IPv4/IPv6 addresses and rejecting non-public ranges. Re-evaluate on every redirect hop.  
**Rationale:**
- Hostname prefix checks alone fail against DNS rebinding, internal subdomains, and 0.0.0.0/8 / link-local addresses.
- Re-evaluating on redirects prevents open redirect exploits leading to internal network targets.

## D006: Manual Redirect Control with Cycle Detection
**Status:** Accepted  
**Date:** Phase 2  
**Decision:** Follow redirects manually (`follow_redirects=False`) with a 5-hop maximum and visited tracking.  
**Rationale:**
- Automatic client redirects bypass per-hop SSRF validation.
- Cycle detection prevents denial of service from infinite redirect loops.

## D007: Streaming Size Limits & Decompression Bomb Protection
**Status:** Accepted  
**Date:** Phase 2  
**Decision:** Stream response chunks enforcing a 10MB wire limit and 50MB decompressed limit.  
**Rationale:**
- Prevents memory exhaustion from large downloads and highly compressed zip bombs.

## D008: BeautifulSoup4 with lxml Backend for HTML Processing
**Status:** Accepted  
**Date:** Phase 3  
**Decision:** Use BeautifulSoup4 with the `lxml` parser backend for all HTML stripping, metadata extraction, and tag hierarchy resolution.  
**Rationale:**
- `lxml` is written in C and offers orders of magnitude faster parse times than Python's built-in `html.parser`.
- Superior error recovery when processing poorly structured or broken real-world HTML.
- Robust decomposition of non-content elements (`<script>`, `<style>`, `<noscript>`, `<nav>`, `<footer>`).

## D009: Offline-First Tokenization and NLP Pipeline
**Status:** Accepted  
**Date:** Phase 3  
**Decision:** Prohibit runtime network calls (`nltk.download()`); bundle standard 179 English stop-words and maintain regex-based fallback tokenization (`r"[A-Za-z0-9]+(?:'[A-Za-z]+)?"`).  
**Rationale:**
- Ensures tests and production search engine instances run reliably in air-gapped, offline, and containerized CI/CD environments.
- Protects against runtime latency spikes and network failure points during scraping and indexing.
- Preserving token frequencies in `tokens` enables exact term frequency calculation for BM25 in Phase 4 while maintaining a clean unique `terms` vocabulary.

## D010: SHA-256 Deduplication with Strict Field Delimiters
**Status:** Accepted  
**Date:** Phase 3  
**Decision:** Use SHA-256 fingerprinting on normalized title and body separated by `\n---BODY---\n`. Document fingerprints are registered only after successful parsing completes.  
**Rationale:**
- Unseparated concatenation (`title + body`) permits collisions where characters shift between title and body.
- Process-local hash set avoids redundant indexing of mirrored or duplicate content.
- Committing the fingerprint only on parse success ensures malformed or failed documents do not falsely block future valid crawls of identical content.

## D011: SQLite Inverted Index with WAL Mode and Schema Versioning
**Status:** Accepted  
**Date:** Phase 4  
**Decision:** Use SQLite 3 as the inverted index datastore configured with `PRAGMA journal_mode = WAL;`, `PRAGMA foreign_keys = ON;`, `PRAGMA busy_timeout = 5000;`, and schema versioning (`schema_version = '4.0'`).  
**Rationale:**
- Zero-configuration, embedded relational engine with ACID transactional guarantees.
- WAL mode allows concurrent search queries while indexing batches write without contention.
- Relational foreign key cascades guarantee no orphaned postings when documents are deleted.
- Automated migration logic prevents silent corruption or crashes when running across upgrades.

## D012: Robertson-SpÃ¤rck Jones BM25 with Field Boosting
**Status:** Accepted  
**Date:** Phase 4  
**Decision:** Implement Okapi BM25 ranking utilizing Robertson-SpÃ¤rck Jones IDF formula `log(1.0 + (N - df + 0.5) / (df + 0.5))` and store raw frequencies separately from field frequencies (`title_frequency`, `body_frequency`).  
**Rationale:**
- Unlike basic `log(N / df)` which drops to zero or goes negative for common terms, Robertson BM25 IDF remains strictly positive for all document frequencies ($0 < \text{df} \le N$).
- Storing unweighted raw TF along with title and body frequencies allows configurable, dynamic field boosting (`title_boost=2.0`, `body_boost=1.0`) at query time without baking weights irreversibly into the index.
- Document length is strictly computed as processed token count, and index-wide average length is maintained in metadata for $O(1)$ scoring performance.

## D013: Atomic Batch Accumulation with All-or-Nothing Flushes
**Status:** Accepted  
**Date:** Phase 4  
**Decision:** Implement `BatchIndexer` with in-memory accumulation and single-transaction flushes, rolling back all batch writes if any database error occurs.  
**Rationale:**
- Committing after every individual document introduces excessive SQLite disk sync overhead, throttling throughput.
- A single batch transaction dramatically improves write performance to exceed >50 docs/sec while maintaining ACID transactional guarantees.
- Recalculating IDFs post-batch rather than per-document eliminates redundant full-index recalculation overhead.

## D014: Structured Query Syntax & Two-Stage Search Evaluation
**Status:** Accepted  
**Date:** Phase 5  
**Decision:** Parse queries into structured `ParsedQuery` separating required (`+`), excluded (`-`), exact phrases (`"..."`), field filters (`field:val`), and optional terms. Candidate documents are retrieved via BM25 over-sampling with vocabulary stem expansion, followed by in-memory post-filtering.  
**Rationale:**
- Decoupling candidate retrieval from exact phrase and Boolean constraints enables fast inverted index lookups followed by precise in-memory filtering, avoiding fragile dynamic SQL query construction.
- Stemming expansion during query lookup bridges user-entered inflected forms (e.g. "algorithms") with stemmed inverted index terms ("algorithm").
- Strict safety limits (500 chars, 100 terms, 50 chars/term) prevent regex catastrophic backtracking and memory exhaustion.

## D015: Word-Boundary Aligned Contextual Snippet Generation & Term Highlighting
**Status:** Accepted  
**Date:** Phase 5  
**Decision:** Generate snippets centered on query term matches (150â€“200 chars), snap window boundaries backwards/forwards to whitespace, highlight matches using Markdown bolding (`**term**`) sorted descending by length, and format boundaries with ellipses.  
**Rationale:**
- Snapping to word boundaries prevents severed words at snippet boundaries, providing clean, readable excerpts in search results.
- Sorting query terms descending by length prior to regex compilation prevents partial substring collisions (e.g. replacing "learn" inside "learning").
- Ellipsis formatting (`... ` / ` ...`) indicates snippet truncation to the user.

## D016: Unified End-to-End Pipeline Architecture
**Status:** Accepted  
**Date:** Phase 5  
**Decision:** Implement `EndToEndPipeline` coordinating `URLFrontier`, `Fetcher`, `ParserPipeline`, `SQLiteIndexer`, `BatchIndexer`, and `SearchEngine` with async crawl loops and automatic IDF updates.  
**Rationale:**
- Encapsulates the entire search lifecycle (crawl â†’ parse â†’ index â†’ rank â†’ snippet) behind a single unified interface.
- Simplifies FastAPI endpoint integration in Phase 6 and guarantees proper resource cleanup across fetcher and indexer connections.
- Automates post-crawl batch flushing and BM25 IDF recalculation.

## D017: FastAPI Application Factory, Lifespan Lifecycle, and app.state Dependency Injection
**Status:** Accepted  
**Date:** Phase 6  
**Decision:** Implement application factory `create_app()` utilizing FastAPI's asynchronous `lifespan` manager and `app.state` for resource management (`app.state.indexer`, `app.state.search_engine`, `app.state.config`). Avoid mutable global state. Expose dependencies to routes via `Depends(get_indexer)` and `Depends(get_search_engine)`.  
**Rationale:**
- Eliminates global mutable singletons (`set_search_engine`), enabling fully isolated concurrent tests with temporary SQLite databases and mock clocks.
- Ensures graceful resource lifecycle: database connections and write locks in `SQLiteIndexer` are cleanly terminated upon server shutdown.
- Routes cleanly report HTTP 503 Service Unavailable if dependencies are missing or uninitialized.

## D018: In-Memory Sliding-Window Rate Limiter & Stale Bucket Eviction
**Status:** Accepted  
**Date:** Phase 6  
**Decision:** Implement an in-memory sliding-window rate limiter tracking timestamp deques per client IP. Extract client IP directly from `request.client.host` unless the peer IP matches a configured `trusted_proxies` list (in which case the left-most client IP from `X-Forwarded-For` is used). Periodically prune stale IP buckets lazily and bound maximum stored buckets.  
**Rationale:**
- Sliding-window algorithm eliminates boundary burst vulnerabilities inherent to fixed-window counters.
- Strictly protects against IP spoofing via `X-Forwarded-For` headers from untrusted clients while retaining compatibility with reverse proxies (e.g. Nginx, Cloudflare) when configured.
- Lazy, size-bounded bucket pruning prevents gradual memory leaks over extended operational periods.
- Standard headers (`X-RateLimit-*` and `Retry-After`) provide transparent back-off signals to API consumers.

## D019: Dual Method Search Routing (POST Body & GET Query) with Legacy Compatibility
**Status:** Accepted  
**Date:** Phase 6  
**Decision:** Provide both `POST /api/v1/search` (accepting JSON payload) and `GET /api/v1/search` (accepting query parameters `q`, `limit`, `offset`), delegating to a shared search handler `_execute_search_service`. Register legacy route aliases (`/api/search`, `/api/suggest`, `/api/stats`, `/api/health`, `/health`, `/`) ensuring existing tools and health probes continue without disruption.  
**Rationale:**
- POST endpoint allows rich JSON request payloads, avoiding URL encoding issues with complex query expressions (+terms, -terms, "quotes", field filters).
- GET endpoint preserves standard browser navigability, bookmarking, and simple cURL workflows.
- Legacy aliases provide seamless backward compatibility for existing monitoring agents and test scripts.

## D020: React 18 + Vite 5 + TypeScript Single-Page Application Architecture
**Status:** Accepted  
**Date:** Phase 7  
**Decision:** Adopt React 18, Vite 5, and TypeScript in strict mode for the frontend client. Configure an Axios API client reading `VITE_API_BASE_URL` with a development reverse proxy forwarding `/api` to the FastAPI backend.  
**Rationale:**
- Vite provides instant Hot Module Replacement (HMR) and sub-second production builds (ESBuild + Rollup).
- TypeScript strict mode guarantees complete interface parity between backend Pydantic models and frontend data representations.
- Dev proxy eliminates CORS concerns during local development while environment variables allow seamless containerized or reverse-proxied production deployments.

## D021: URL-Driven State Synchronization & In-Flight AbortController Cancellation
**Status:** Accepted  
**Date:** Phase 7  
**Decision:** Use React Router `useSearchParams` as the single source of truth for query (`q`) and page (`page`). Automatically reset pagination to page 1 upon new search submissions. Enforce native `AbortController` cancellation across both search executions and debounced autocomplete suggestions.  
**Rationale:**
- Making search state shareable through URL query parameters enables standard browser bookmarking, sharing, and native back/forward history navigation.
- In-flight request cancellation completely prevents network race conditions where earlier slow responses overwrite newer user searches or typed prefixes.
- Resetting to page 1 on new queries prevents out-of-bounds pagination errors on smaller result sets.

## D022: Safe Virtual DOM Snippet Highlighting Without dangerouslySetInnerHTML
**Status:** Accepted  
**Date:** Phase 7  
**Decision:** Parse backend markdown bold markers (`**term**`) and query terms into React virtual DOM elements (`<mark className="highlight-term">` and text fragments), strictly rejecting `dangerouslySetInnerHTML`.  
**Rationale:**
- Eliminates Cross-Site Scripting (XSS) attack vectors completely, even when indexing untrusted web documents with embedded HTML or script injections.
- Produces clean, accessible markup compatible with styling tokens in both Dark and Light themes.
- Fallback tokenizer ensures clean query term highlighting even when raw snippets lack explicit markdown tags.

## D023: Token-Protected Admin Authentication
**Status:** Accepted  
**Date:** Phase 8  
**Decision:** Secure admin endpoints (`/api/v1/admin/*`) via a dedicated `X-Admin-Token` header. Compare tokens in constant time using `secrets.compare_digest()`. In production mode (`ENVIRONMENT=production`), require `ADMIN_TOKEN` to be explicitly set and reject requests with 401 (missing) or 403 (invalid/disabled). Retain tokens client-side in `sessionStorage` rather than `localStorage`.  
**Rationale:**
- Constant-time comparison mitigates timing-attack vulnerabilities against the administrative token.
- Avoids claiming full Role-Based Access Control (RBAC) where single-token verification is used without user identities or database-backed permission tiers.
- `sessionStorage` confines the token to the active browser tab session, reducing exposure to cross-site scripting (XSS) or persistent machine extraction compared to `localStorage`.

## D024: Process-Local In-Memory Crawl State Coordinator
**Status:** Accepted  
**Date:** Phase 8  
**Decision:** Manage crawler execution using a process-local `CrawlManager` maintaining an explicit state machine (`idle`, `running`, `paused`, `stopped`, `error`). Use an `asyncio.Lock` to prevent concurrent crawl jobs and cooperative `asyncio.Event` flags (`_pause_event`, `_stop_event`) for responsive pause, resume, and cancellation. Enforce defense-in-depth SSRF pre-validation of seed URLs before launching crawl workers.  
**Rationale:**
- Eliminates concurrency race conditions and prevents overlapping crawls from competing for database write locks or exhausting local network resources.
- Cooperative async events ensure that crawling can be paused or stopped immediately between document fetches without leaving SQLite transactions or HTTP connections hanging.
- Defense-in-depth seed URL validation at the API boundary rejects obvious non-public or loopback targets early while relying on the underlying `Fetcher` for full per-hop DNS and redirect verification during execution.

## D025: Strictly Measured Non-Blocking Telemetry & Bounded Redacted Logs
**Status:** Accepted  
**Date:** Phase 8  
**Decision:** Collect host metrics (CPU percentage, memory usage, disk space) using non-blocking `psutil` calls (`cpu_percent(interval=None)`) and compute index statistics directly from SQLite metadata (`COUNT(*)` on documents and terms). Expose bounded log tailing (max 500 lines) with multi-pattern regex redaction (`***REDACTED***`) for sensitive credentials (`ADMIN_TOKEN`, API keys, passwords, authorization headers). Restrict runtime configuration updates to a safe in-memory allowlist.  
**Rationale:**
- Non-blocking telemetry guarantees that admin monitoring polls never delay or freeze search API request serving.
- Omitting unmeasured metrics (such as uninstrumented request latency or fake connection counters) maintains strict telemetry integrity.
- Regex-based token redaction and bounded line limits protect sensitive credentials and prevent memory exhaustion during log viewing.
- In-memory configuration updates allow safe live operational adjustments (e.g. log level, rate limits) without permanently mutating persistent configuration files (`config.yaml`, `.env`) on disk.

## D026: Test Tier Separation via pytest Markers
**Status:** Accepted
**Date:** Phase 9
**Decision:** Register six pytest markers (unit, integration, security, e2e, performance, slow) in `pytest.ini`. Configure `addopts` to exclude e2e, performance, and slow from all default `pytest` invocations. Run expensive tests only through explicit script invocations.
**Rationale:**
- Prevents expensive browser, load, and long-running tests from blocking fast developer feedback loops.
- Keeps the normal regression suite deterministic and completable in under 20 seconds on a development machine.
- Allows CI to gate on different tiers (fast regression, security, E2E) in separate pipeline stages.

## D027: Create-App Factory Pattern for Test Isolation
**Status:** Accepted
**Date:** Phase 9
**Decision:** All tests that require a running FastAPI application create it through the `create_app(indexer=..., search_engine=..., config=..., rate_limiter=...)` factory, using isolated temporary SQLite databases per test. No global state is mutated.
**Rationale:**
- Eliminates state leakage between tests caused by shared module-level singletons.
- Mirrors the production lifespan exactly — same code path, different dependencies.
- Makes tests safe to run in parallel with `pytest-xdist` in future without conflict.

## D028: Mock Clock Injection for Rate Limiter Tests
**Status:** Accepted
**Date:** Phase 9
**Decision:** The Phase 6 `RateLimiter` accepts an optional `time_func: Callable[[], float]` parameter. Tests inject a controllable mock clock via `mock_clock` fixture that increments on demand, eliminating real `time.sleep` calls.
**Rationale:**
- Makes rate limit threshold tests fully deterministic — no wall-clock sensitivity.
- Allows time-dependent behaviors (window expiry, stale bucket cleanup) to be tested in milliseconds.
- `time_func` injection was a Phase 6 production design; Phase 9 exploits it without modifying production code.

## D029: Flake8 max-line-length Set to 99
**Status:** Accepted
**Date:** Phase 9
**Decision:** Set `.flake8` `max-line-length` to 99 (up from 88).
**Rationale:**
- Black's line length is 88 for structured code, but Black intentionally does not break string literals or comments. Long f-strings in test HTML templates and long JSON payloads in security tests legitimately exceed 88 characters and cannot be split without degrading readability.
- 99 is a widely accepted practical ceiling when using Black as the primary formatter, matching Black's own documentation recommendation.

## D030: E2E Test Architecture — Dedicated Controlled Servers
**Status:** Accepted
**Date:** Phase 9
**Decision:** E2E Playwright tests require dedicated servers: backend on :8001 with seeded `data/e2e_test.db`, frontend preview on :3001 built with `VITE_API_BASE_URL=http://localhost:8001`. Runner scripts (`run_e2e_tests.ps1/.sh`) start both servers, wait for health readiness, run Playwright, and tear down via try/finally or bash trap regardless of test outcome.
**Rationale:**
- Deterministic seeded database guarantees reproducible E2E results independent of any running production database.
- Frontend must be rebuilt before E2E because `VITE_API_BASE_URL` is bundled at build time and cannot be changed after the bundle is created.
- Try/finally teardown prevents orphaned background processes on test failure.
- Non-standard ports (:8001, :3001) prevent accidentally testing a running production server.

## D031: Locust Load Test Explicit Host Safety Guard
**Status:** Accepted
**Date:** Phase 9
**Decision:** The Locust load test runner requires `LOAD_TEST_HOST` to be explicitly set by the caller, or it starts its own isolated server on :8099. Remote (non-localhost) targets require `ALLOW_REMOTE_LOAD_TEST=true` to be set explicitly. Pass/fail thresholds: failure rate <= 1%, p95 <= 200ms.
**Rationale:**
- Prevents accidental load testing of a production server by defaulting to an isolated local test server.
- `ALLOW_REMOTE_LOAD_TEST` acts as a deliberate human confirmation before load testing any shared environment.
- Timestamped CSV output in `reports/load/` allows longitudinal performance tracking without overwriting previous results.

## D032: Search Input as Pure Text Data (No Path Traversal Filter in Search Service)
**Status:** Accepted
**Date:** Phase 10
**Decision:** Search queries submitted to `/api/v1/search` and executed by `SearchEngine` are treated strictly as query text data, not filesystem paths. Path-traversal patterns (`../`, `%2f`, `etc/passwd`, `windows/system32`) are neither rejected nor stripped by the search service; they are tokenized and queried against the SQLite inverted index. Filesystem path traversal protection belongs and is strictly enforced at actual filesystem boundaries (`LogService`, database file loader).
**Rationale:**
- Search queries are data. Path traversal is an attack against filesystem APIs, not search engines.
- Destructive filtering or rejecting path-like strings causes false positives on valid technical queries (e.g. searching for documentation on `../../lib/utils` or `etc/passwd`).
- Security is guaranteed by ensuring the search service has zero code paths that convert query text into filesystem paths.

## D033: Production Admin Token Entropy and Startup Failsafe
**Status:** Accepted
**Date:** Phase 10
**Decision:** The administrative token (`ADMIN_TOKEN`) is verified using `secrets.compare_digest()` to eliminate timing analysis side-channels. In production (`environment == "production"` enforced with deterministic precedence by `normalize_environment()`), application lifespan startup validates that `admin_token` exists, is at least 32 characters long, contains at least 4 unique characters, and does not match the default dev token. If validation fails, `RuntimeError` is raised immediately before binding sockets, without logging or leaking secret values.
**Rationale:**
- Production administration requires robust secret management. Default or low-entropy tokens expose systems to brute force and unauthorized control.
- Halting boot before socket binding guarantees an insecurely configured instance cannot accept external traffic.
- Constant-time comparison ensures timing attacks cannot deduce secret characters.

## D034: Evidence-Backed OWASP Top 10 Control Assessment
**Status:** Accepted
**Date:** Phase 10
**Decision:** The OWASP Top 10 (2021) control matrix in `docs/10_SECURITY.md` documents exact evidence-backed control statuses based on actual automated regression tests and architectural boundaries: Mitigated (A01, A02, A03, A04, A05, A07, A08, A09, A10) and Partially mitigated (A06 - vulnerable components triaged and cataloged). No fake security classes (e.g. `OWASPValidator`) or unauthenticated fake RBAC hierarchies were introduced.
**Rationale:**
- Security architecture must reflect genuine attack surfaces and defenses.
- Introducing artificial filters or fake user classes to satisfy superficial audit checklists compromises system stability and creates misleading representations of access control.

## D035: Flake8 Strict 88-Character Limit Enforcement
**Status:** Accepted (Supersedes D029)
**Date:** Phase 10
**Decision:** Restored `max-line-length = 88` in `.flake8`. All code and test files across `src/` and `tests/` are reformatted to strictly satisfy the 88-character limit.
**Rationale:**
- Strictly aligns the repository's linting ceiling with Black's default line-length standard, ensuring consistent formatting across all editor environments without discrepancy.

## D036: Service-Layer In-Memory LRU Query Caching with Persistent Generation Invalidation
**Status:** Accepted
**Date:** Phase 11
**Decision:** Implement query caching at the service layer (`_execute_search_service()`) using an in-process thread-safe `LRUCache` backed by `collections.OrderedDict` and `threading.Lock()`. Cache keys are collision-free 4-tuples: `(generation, clean_query.lower(), limit, offset)`. The index generation counter is transactionally stored and bumped in SQLite `metadata` on mutations (`add_document`, `delete_document`, `clear_index`, `BatchIndexer.flush()`). Cache hits return fresh copies (`copy.deepcopy()` or reconstructed Pydantic models) with `X-Cache: HIT` / `X-Cache: MISS` headers. Responses with error status codes (400, 422, 500) are never cached.
**Rationale:**
- Caching at the service layer avoids duplicate BM25 ranking and document fetches for repeated queries while ensuring the HTTP layer remains decoupled.
- In-memory `OrderedDict` provides sub-millisecond retrieval (<0.001ms p50) without the operational complexity or external dependency of Redis.
- Transactionally incrementing `index_generation` guarantees that write operations instantly invalidate stale cached entries for subsequent reads across processes without complex cache-purge pub/sub.
- Defensive copy return prevents mutations by calling scopes from corrupting cached data.

## D037: Evidence-Backed SQLite Schema & Maintenance Tooling Policy
**Status:** Accepted
**Date:** Phase 11
**Decision:** Do not modify the existing SQLite table schemas or add speculative indexes. Empirical query plan analysis confirmed that existing indexes (`sqlite_autoindex_terms_1`, `sqlite_autoindex_postings_1`, primary key `rowid`) fully cover all search and posting lookups with zero table scans. Maintenance routines (`VACUUM`, `REINDEX`, `ANALYZE`, `PRAGMA optimize`) are exposed strictly through an offline CLI tool (`scripts/optimize_database.py`) with explicit operator warnings and interactive confirmation, and are never executed on HTTP request paths.
**Rationale:**
- Adding speculative indices increases database write overhead and disk space without query performance benefits when query plans already prove index coverage.
- Running `VACUUM` or `REINDEX` during online HTTP requests can lock the SQLite database exclusively, introducing severe latency spikes or timeout errors for concurrent requests.
- Operator-gated CLI maintenance ensures database maintenance happens during controlled maintenance windows.

## D038: Bounded Rolling-Window Performance Telemetry and Privacy Isolation
**Status:** Accepted
**Date:** Phase 11
**Decision:** Track query latency percentiles (p50, p95, p99) and cache hit rate using `PerformanceMetricsCollector` backed by a fixed-size `collections.deque(maxlen=1000)`. Strictly forbid storing, logging, or exposing raw query strings or user identifiers within the telemetry collector.
**Rationale:**
- A bounded deque guarantees fixed memory consumption regardless of query throughput.
- Zero storage of raw query strings ensures user search queries remain private and cannot leak through telemetry endpoints or logs.

## D039: Single-Replica Production Deployment Architecture for Embedded SQLite
**Status:** Accepted
**Date:** Phase 12
**Decision:** Deploy the production application container with strictly `replicas: 1` using deployment `strategy: type: Recreate` mounted to a single `ReadWriteOnce` (RWO) PersistentVolumeClaim. Exclude Horizontal Pod Autoscaling (HPA) and Pod Disruption Budgets (PDB).
**Rationale:**
- The authoritative inverted index and document store is embedded SQLite running in WAL mode. Concurrent processes sharing a network-mounted SQLite file across multiple nodes can cause database locking errors, torn pages, and corrupted WAL logs.
- Key operational components—including the service-layer LRU cache, the token-bucket IP rate limiter, and the background crawler queue—are process-local and in-memory.
- Multi-replica active-active clustering requires distributed database engines (e.g. PostgreSQL, OpenSearch) and distributed cache/rate-limiting layers (e.g. Redis), which contradicts the lightweight, private, self-contained architectural mandate.

## D040: Application-Owned Prometheus Registry and Centralized Request Instrumentation
**Status:** Accepted
**Date:** Phase 12
**Decision:** Implement Prometheus metrics using the official `prometheus-client` library with an application-owned `CollectorRegistry` instance per FastAPI application factory call. Instrument HTTP traffic centrally in `request_lifecycle_middleware` using normalized route templates (`/api/v1/search`, `/health`, etc.) and bounded fallbacks (`"unmatched"`) to strictly prevent metric label cardinality explosion. Track cache hits and misses at the single authoritative execution site. Maintain strict telemetry privacy by forbidding raw query strings in labels or metric dimensions.
**Rationale:**
- Using the global default Prometheus registry prevents test isolation and raises `Duplicated timeseries` errors during repeated test runs.
- Centralized middleware instrumentation guarantees consistent tracking of request counts and duration histograms across all routes without manual route-level duplication.
- Normalizing route templates ensures unbounded or attacker-crafted URL paths cannot create high-cardinality metric labels.
- Banning search query text in metric dimensions protects user search privacy and aligns with privacy-first engine principles.

## D041: Transactionally Consistent Online SQLite Backup with Sandbox Restore Verification
**Status:** Accepted
**Date:** Phase 12
**Decision:** Implement live database backups using Python's `sqlite3.backup()` API in `scripts/backup_database.py`. Generate SHA-256 cryptographic checksums for every backup artifact. Execute `PRAGMA integrity_check` on the snapshot. Provide an automated non-destructive restore verification option (`--verify-restore`) that restores the backup into an isolated temporary workspace and runs smoke queries using `SQLiteIndexer` and `SearchEngine`. Purge backups exceeding retention policies strictly matching `index_backup_*.db`.
**Rationale:**
- Filesystem file copies (`cp`) of SQLite databases running in WAL mode can capture torn pages during concurrent write transactions. The online backup API guarantees transactionally consistent page snapshots without locking out concurrent readers or writers.
- Cryptographic digests and automated restore sandboxing verify that backup archives are valid and recoverable before disaster strikes.
- Automated retention purging with strict filename patterns prevents unbounded storage growth while preventing accidental deletion of non-backup files.


