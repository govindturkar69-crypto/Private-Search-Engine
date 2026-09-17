# Technical Requirements Document (TRD)

## Stack
- Python 3.11+
- FastAPI
- HTTPX (async client with streaming)
- SQLite
- BeautifulSoup4 + NLTK

## Performance Targets
- Indexing: >100 docs/minute
- Query: <1s (p95)
- Memory: <500MB crawl, <200MB idle
- Coverage: >80%

## Scalability
- Initial: 1K-10K documents
- Crawl: 10 req/sec global, 1 per domain
- Query: 10+ concurrent users

---

## Crawler Requirements (Phase 2)
- **Timeouts:** 10 seconds per request default.
- **Retries:** Up to 3 attempts with backoff (1s, 3s, 10s) for transient network timeouts and 5xx gateway errors.
- **Wire Size Limit:** 10MB (`10,485,760` bytes) maximum per document, enforced via streaming response chunks and `Content-Length`.
- **Decompressed Size Limit:** 50MB (`52,428,800` bytes) maximum decompressed content limit to prevent decompression/zip bombs.
- **Redirect Limit:** 5 hops maximum with explicit loop detection and redirect target validation.
- **User-Agent:** `PrivateSearchCrawler/1.0 (+http://localhost:8000)`.
- **robots.txt Compliance (RFC 9309):**
  - Most-specific (longest pattern length) matching directive wins.
  - If equally specific Allow and Disallow rules match, Allow wins.
  - Case-insensitive product token matching; fallback to wildcard `*`.
  - Non-standard extensions supported: `Crawl-delay` and `Request-rate`.
- **Politeness:** Per-domain rate limiting (default 1.0s) calculated via `time.monotonic()`.
- **SSRF Protection:**
  - Schemes: `http` and `https` exclusively.
  - DNS resolution of hostnames to all IPv4/IPv6 addresses.
  - Block: 127.0.0.0/8 (loopback), 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, 100.64.0.0/10 (CGNAT), 0.0.0.0/8, [::1], [::], fe80::/10 (IPv6 link-local), multicast, and reserved addresses.
  - SSRF validation re-evaluated on every redirect hop.

---

## Content Processing & Parser Requirements (Phase 3)
- **HTML Parsing Engine:** BeautifulSoup4 with `lxml` parser backend for speed and fault-tolerant DOM recovery.
- **Content Sanitization:** Decomposes non-content tags before text extraction: `<script>`, `<style>`, `<noscript>`, `<nav>`, `<footer>`, `<template>`, `<header>`, `<aside>`.
- **Extraction Hierarchies:**
  - **Body Content:** Prefers `<article>` → `<main>` → `<body>`.
  - **Title Extraction:** Prefers `<title>` → `<meta property="og:title">` → `<h1>`.
  - **Description Extraction:** Prefers `<meta property="og:description">` → `<meta name="description">`.
  - **Publication Date:** Prefers `<meta itemprop="datePublished">` → `<meta property="article:published_time">` → `<time datetime>` → `<meta name="pubdate">` / `<meta name="date">`.
- **Field Character Limits & Truncation:**
  - Title: 200 characters max (`[:200]`).
  - Description: 500 characters max (`[:500]`).
  - Body: Exactly 1,048,576 characters max (`[:1_048_576]`) applied after whitespace normalization to eliminate Unicode midpoint byte corruption.
- **NLP & Offline Tokenization:**
  - Zero runtime network calls: `nltk.download()` is never invoked at runtime.
  - Offline fallback regex tokenizer `r"[A-Za-z0-9]+(?:'[A-Za-z]+)?"` if NLTK data files are absent.
  - Bundled 179-word standard English stop-word set.
  - Porter Stemmer applied to clean tokens (min length 2, max length 50, digits stripped).
  - Term Frequency: `tokens` retains repeated tokens for BM25 term frequency calculation; `terms` provides unique vocabulary set.
- **Deduplication:**
  - In-memory SHA-256 fingerprinting using distinct field separator: `f"{title}\n---BODY---\n{body}"`.
  - Casing and internal whitespace normalized prior to hashing.
  - Safe registration: Document content hashes are registered only upon successful parse, preventing poison states on failure.
- **Link Extraction:**
  - Absolute URL resolution via `urllib.parse.urljoin`.
  - URL fragments stripped (`#...`); query string parameter ordering preserved.
  - Strict protocol filtering: Only `http` and `https` allowed; `javascript:`, `mailto:`, `tel:`, `data:`, `ftp:` discarded.
  - Configurable priority calculation based on domain match and path depth.

---

## Indexing Engine Requirements (Phase 4)
- **Database Engine:** SQLite 3 with ACID transactional guarantees.
- **Connection PRAGMAs:**
  - `PRAGMA foreign_keys = ON;` (enforces relational integrity and cascade deletes)
  - `PRAGMA journal_mode = WAL;` (Write-Ahead Logging for high-concurrency reading/writing)
  - `PRAGMA busy_timeout = 5000;` (prevents lock exceptions during concurrent operations)
  - `PRAGMA synchronous = NORMAL;` (optimal balance of durability and write throughput)
- **Lifecycle & Connection Management:**
  - Public `close()` method with explicit cleanup.
  - Full Python context manager protocol (`__enter__` and `__exit__`).
- **Schema & Versioning (v4.0):**
  - Explicit `schema_version = '4.0'` stored in `metadata` table.
  - Automated migration logic detecting older unversioned or legacy table layouts.
  - 4 relational tables: `documents`, `terms`, `postings`, `metadata`.
  - 6 performance indices covering URL, content hash, language, terms, and posting foreign keys.
- **Document Length & Dynamic Averages:**
  - Document length is strictly defined as processed token count (`document_length INTEGER NOT NULL DEFAULT 0`).
  - Index metadata maintains running totals: `total_documents`, `total_document_length`, `avg_document_length`.
  - Average document length is read directly in `O(1)` from metadata during ranking, avoiding table scans.
- **Frequencies & Field Weighting:**
  - Postings table stores separate numeric columns:
    - `term_frequency` (raw total document occurrences)
    - `title_frequency` (occurrences in title tokens)
    - `body_frequency` (occurrences in body tokens)
    - `positions` (JSON-encoded array of token offsets, e.g. `[0, 5, 12]`)
  - Configurable field boosts applied during scoring: `effective_tf = title_frequency * title_boost + body_frequency * body_boost` (defaults: `title_boost=2.0`, `body_boost=1.0`).
- **BM25 Formulation (Robertson-Spärck Jones):**
  - `idf = log(1.0 + (N - df + 0.5) / (df + 0.5))` (strictly positive for all terms, including terms in 100% of documents).
  - BM25 score: `idf * (effective_tf * (k1 + 1.0)) / (effective_tf + k1 * (1.0 - b + b * (doc_len / avg_doc_len)))` with `k1=1.5`, `b=0.75`.
- **Duplicate URL and Content Behavior:**
  - URL uniqueness enforced via `url TEXT UNIQUE NOT NULL`. Duplicate URL returns existing `doc_id` without duplicate re-indexing.
  - Content hash indexed via `idx_documents_content_hash`. If identical hash is submitted under another URL, returns canonical `doc_id`.
- **Atomic Transactions & True Batching:**
  - Single document insertion atomically updates `documents`, `terms`, `postings`, frequencies, and `metadata`.
  - `BatchIndexer` accumulates documents in-memory and flushes them inside a single atomic SQLite transaction with all-or-nothing rollback semantics.
- **Deletion Consistency:**
  - `delete_document(doc_id)` decrements term `document_frequency` and `collection_frequency`, recalculates running metadata lengths, and deletes orphaned terms whose document frequency reaches zero in a single transaction.
- **Performance:**
  - Batch indexing throughput target: `>50 docs/sec` in production batching.

---

## Ranking & Scoring Engine Requirements (Phase 5)
- **Query Parser & Syntax:**
  - Standard terms: `term` (optional BM25 scoring match).
  - Required terms: `+term` (document must contain term or stemmed variant; failure rejects candidate).
  - Excluded terms: `-term` (document must NOT contain term; match rejects candidate).
  - Exact phrases: `"exact phrase"` (must match case-insensitive substring sequence).
  - Field filters: `field:value` (matches metadata attributes including `language:`, `author:`, `domain:`, `title:`).
  - Safety limits: Max 500 query characters, max 100 terms, max 50 characters per term.
  - Normalization: Leading/trailing punctuation stripped, casing lowercased, hyphens inside words preserved.
- **BM25 Relevance Scoring & Normalization:**
  - Candidate retrieval: Queries inverted index postings for query terms and stemmed variants.
  - Score normalization: Raw BM25 score mapped to a user-facing `0–100` integer percentage relative to top scoring candidate (`int(round((score / top_score) * 100))`).
  - Top result always assigned `100%`; secondary candidates scaled proportionally.
- **Contextual Snippet Generation:**
  - Window radius: Centered around first/best query term match (150–200 characters total).
  - Word boundary snapping: Backwards and forwards search for whitespace preventing severed words.
  - Markdown highlighting: Matching query terms enclosed in `**term**` (sorted descending by length).
  - Ellipsis formatting: Boundaries prepended with `... ` and appended with ` ...`.
  - Sentence context: `extract_context()` extracts complete sentence containing term.
- **Search Latency Target:**
  - Sub-100ms response time for multi-term queries across index.
- **Integrated Pipeline:**
  - `EndToEndPipeline` connects `URLFrontier` + `Fetcher` + `ParserPipeline` + `SQLiteIndexer` + `BatchIndexer` + `SearchEngine`.

---

## Search API & FastAPI Server Requirements (Phase 6)
- **Application Lifecycle & Dependency Injection:**
  - FastAPI asynchronous lifespan manager controls setup (logging, configuration, SQLite indexer, search engine) and teardown (`indexer.close()`).
  - Application services are attached to `app.state` (`app.state.indexer`, `app.state.search_engine`, `app.state.config`).
  - Route handlers consume dependencies through FastAPI `Depends(get_indexer)` and `Depends(get_search_engine)`.
  - Application factory `create_app(config, indexer, search_engine, rate_limiter, ...)` enables 100% isolated testing without touching persistent databases.
- **REST Endpoints & Backward Compatibility:**
  - Primary search: `POST /api/v1/search` (JSON body) and `GET /api/v1/search?q=...&limit=...&offset=...`.
  - Legacy search aliases: `GET /api/search` and `POST /api/search`.
  - Term suggestions: `GET /api/v1/suggest?prefix=...&limit=...` and legacy alias `GET /api/suggest`.
  - System statistics: `GET /api/v1/stats` and legacy alias `GET /api/stats`.
  - Health & readiness: `GET /api/v1/health` (evaluates database connectivity, terms count, documents count), `GET /health`, `GET /api/health`, and root `GET /`.
- **Validation & Pagination Constraints (Pydantic v2):**
  - Search query: 1–500 characters, whitespace-stripped; empty or whitespace-only queries rejected with HTTP 422.
  - Limit: Integer between 1 and 100 (default: 10).
  - Offset: Non-negative integer (default: 0); enforced against `server.max_offset` (default: 10,000) returning HTTP 400 if exceeded.
  - Suggest prefix: 1–50 characters, whitespace-stripped; empty rejected with HTTP 422.
  - Suggest limit: Integer between 1 and 50 (default: 5).
- **In-Memory Sliding-Window Rate Limiting:**
  - Configurable rate limit: `rate_limit_per_minute` (default: 60 requests/minute per client IP).
  - Sliding timestamp window tracked per IP; requests exceeding limit return HTTP 429 Too Many Requests.
  - Headers attached to all responses: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.
  - HTTP 429 response includes `Retry-After: <seconds>` header.
  - Lazy, size-bounded cleanup prevents memory leak from stale IP buckets.
  - Client IP extraction defaults to `request.client.host`, honoring `X-Forwarded-For` only if the immediate peer IP is in `trusted_proxies`.
- **Security Headers & Request ID Tracing:**
  - Standard security headers enforced across all responses (including 4xx/5xx errors):
    - `X-Content-Type-Options: nosniff`
    - `X-Frame-Options: DENY`
    - `Referrer-Policy: no-referrer`
    - `X-XSS-Protection: 1; mode=block`
    - `Content-Security-Policy: default-src 'self'`
    - `Strict-Transport-Security: max-age=31536000; includeSubDomains` (enabled when `server.enable_hsts` is True or scheme is HTTPS).
  - CORS configurable via `server.cors_origins` (default: `["*"]`).
  - Request ID tracing: Propagates client `X-Request-ID` if matching regex `^[a-zA-Z0-9\-_]{1,64}$`, otherwise generates a new random safe UUID.
  - Zero traceback leak: Internal server errors (HTTP 500) log details internally and return a generic error message with the associated `request_id`.

---

## Frontend Search UI Requirements (Phase 7)
- **Application Architecture:**
  - Single-Page Application (SPA) built with React 18, Vite 5, and TypeScript in strict mode.
  - Client routing powered by React Router (`BrowserRouter`, `useSearchParams`), making search state fully shareable and bookmarkable via URL parameters: `/?q=...&page=...`.
  - Local Vite development proxy maps `/api` to `http://localhost:8000`. API client reads base URL dynamically from `import.meta.env.VITE_API_BASE_URL` (defaulting to `/api/v1`).
- **Search Bar & Autocomplete Suggestions:**
  - Real-time autocomplete suggestions debounced by 300ms with a minimum prefix threshold of 2 characters.
  - Active in-flight suggestion requests are cancelled via `AbortController` as user continues typing.
  - Keyboard navigation: `ArrowDown` (cycle down), `ArrowUp` (cycle up), `Enter` (select highlighted item), `Escape` (dismiss dropdown).
  - Outside-click listener dismisses dropdown without interfering with click selections.
  - Accessible ARIA attributes: `role="combobox"`, `aria-autocomplete="list"`, `aria-expanded`, `aria-controls="suggestions-listbox"`, `aria-activedescendant`.
- **Search Execution & Request Cancellation:**
  - Searches dispatched on form submission or suggestion selection.
  - Prior in-flight search requests are explicitly cancelled via `AbortController`, preventing stale responses from overwriting newer queries.
  - Submitting a new query automatically resets pagination to page 1 (`page=1`).
- **Safe Snippet Rendering:**
  - Excerpts containing backend `**term**` markdown tags or query keywords are rendered exclusively into React virtual DOM elements (`<mark className="highlight-term">` and text nodes).
  - Strictly prohibits `dangerouslySetInnerHTML`, guaranteeing immunity to XSS or malicious payload injection.
- **Pagination & Navigation:**
  - Windowed pagination with active page indicator (`aria-current="page"`), first/last page buttons, and ellipsis windowing.
  - Smoothly scrolls to the top of the search view when navigating between result pages.
- **Themes & Responsive Design:**
  - Dual theme engine (Dark & Light) styled via CSS variables with `[data-theme='dark']` and `[data-theme='light']`.
  - Automatically respects system preference (`prefers-color-scheme: dark`) with manual override persisted in `localStorage`.
  - Mobile-first responsive styling adapting fluidly down to mobile viewports ($\le 768\text{px}$).
- **Resilient Error & Status Handling:**
  - 422: Informative query validation errors.
  - 429: Rate limit alert displaying remaining back-off seconds (`Retry-After`).
  - 500: Sanitized unexpected error message.
  - 503: Service initializing or unavailable alert.
  - Network Failure: Offline and connection loss alerts.
  - Index Readiness & Document Counters: Real-time status badge (`Ready` vs `Initializing`) and total indexed document metrics fetched from Phase 6 `/health` and `/stats` endpoints.

---

## Admin Dashboard Requirements (Phase 8)
- **Token-Protected Authentication:**
  - Enforces administrative authentication via `X-Admin-Token` or `Authorization: Bearer <token>`.
  - Constant-time token verification using `secrets.compare_digest()` to eliminate timing attacks.
  - Missing token: HTTP 401 Unauthorized; invalid token: HTTP 403 Forbidden.
  - Production strictly requires `ADMIN_TOKEN` environment variable; development permits fallback dev token.
  - Token stored in browser exclusively via `sessionStorage` (cleared on logout or tab close).
- **Crawler State Machine & Background Task:**
  - Process-local coordination via `CrawlManager` protected by `asyncio.Lock`.
  - Lifecycle states: `idle`, `running`, `paused`, `stopped`, `error`.
  - Cooperative pause: Suspends URL iteration while allowing in-flight HTTP requests to complete cleanly.
  - Cooperative stop: Safely cancels loop and flushes pending document batch to SQLite inverted index.
  - Defense-in-depth SSRF: Validates seed URLs against private, loopback, and link-local address ranges prior to starting crawl.
  - Concurrency conflicts: Starting when active or pausing when idle returns HTTP 409 Conflict.
- **Strictly Measured Telemetry:**
  - System metrics: Non-blocking sampling via `psutil` (`cpu_percent(interval=None)`, `virtual_memory()`, `disk_usage('.')`). No synthetic placeholders.
  - Index metrics: SQLite database file size and live metadata table statistics.
- **Bounded Log Inspection:**
  - Tail inspection bounded to 1–500 lines (default 100).
  - Automatic regex redaction of tokens, passwords, API keys, and authorization headers (`***REDACTED***`).
  - Safe text rendering without `dangerouslySetInnerHTML`.
- **Runtime Configuration Management:**
  - Strict allowlist: `log_level`, `rate_limit_per_minute`, `crawler_max_depth`, `crawler_politeness_delay`.
  - Modifies in-memory runtime parameters with zero disk mutation to `config.yaml`.

---

## Production Security Audit & Hardening Requirements (Phase 10)
- **Search Query Data Semantics:**
  - Search queries are data, not filesystem paths.
  - Path-like patterns (`../`, `%2f`, `etc/passwd`, `windows/system32`) are accepted as legitimate query text.
  - Search service is strictly non-filesystem: queries are parsed, tokenized, and resolved against SQLite inverted index.
  - Filesystem path traversal protection is enforced at real filesystem boundaries (`LogService`, database file loader).
- **Production Admin Token Failsafe:**
  - Startup lifespan validation halts boot if `environment == "production"` and `admin_token` is unset, default, <32 characters, or has <4 unique characters.
  - Secrets are never logged or leaked in error responses.
  - `verify_admin_token` enforces production entropy and constant-time `secrets.compare_digest()`.
- **Network Boundary & IP Resolution:**
  - Client IP resolution enforces right-to-left traversal of `X-Forwarded-For` against configured `trusted_proxies`.
  - Per-IP rate limiting (100 req/min default) returns HTTP 429 with `Retry-After` header.
  - Unsupported content types (e.g., XML) safely rejected with HTTP 422 without XXE evaluation.
- **Automated Security Audit Tooling:**
  - `scripts/security_scan.py` executes multi-scanner toolchain: `pip-audit`, `bandit` (zero HIGH severity), `npm audit`, `scripts/security_ast_audit.py` (zero dangerous calls), and `scripts/security_secret_scan.py` (zero exposed secrets).
  - Exit code contracts: 0 = PASS, 1 = BLOCKING FINDINGS, 2 = TOOL ERROR.

---

## Measurement-Driven Performance Optimization Requirements (Phase 11)
- **Empirically Proven Bottleneck Optimization:**
  - Optimizations must target empirically profiled bottlenecks; no speculative refactoring.
  - Primary uncached bottleneck resolved: N+1 `get_document(doc_id)` lookups during ranking eliminated via parameterized chunked prefetching (`get_documents_by_ids` with `batch_size=500`).
  - Retrieval throughput: Single batch prefetch achieves 2.9x speedup over sequential N+1 queries (0.119ms vs 0.341ms for 50 candidate docs).
  - Ingestion throughput: `BatchIndexer` delivers 2,151.7 docs/sec (3.24x speedup over single-document writes at 665.0 docs/sec).
- **BM25 Ranking Semantics Preservation:**
  - Batch prefetching and query optimization must strictly preserve ranking semantics.
  - BM25Okapi calculation, candidate document set, title/body weighting, document-length normalization, ordering, tie-breaking, pagination, and snippet extraction remain identical.
  - Raw `term_frequency` is never treated as a "rank".
- **Service-Layer In-Memory Query Cache:**
  - Process-local thread-safe LRU cache (`LRUCache`) backed by `collections.OrderedDict` and `threading.Lock()`.
  - Collision-free cache key: `(generation, clean_query.lower(), limit, offset)`.
  - Response headers: `X-Cache: HIT` and `X-Cache: MISS`.
  - Fresh response copies returned on hit to prevent caller mutation of cached instances.
  - Sub-millisecond latency: Cached query latency < 0.001ms p50.
  - Cache TTL: Configurable monotonic clock TTL (default 300s); capacity capped at 1,000 entries.
  - Error isolation: Non-200 responses (400, 422, 500) are never cached.
- **Persistent Transactional Index Generation:**
  - `index_generation` counter persisted in SQLite `metadata` table across process restarts.
  - Bumps monotonically within committed write transactions (`add_document`, `delete_document`, `clear_index`, `BatchIndexer.flush()`).
  - Skipped duplicates (URL or content hash) and rolled-back transactions never increment generation.
- **Database Maintenance & Tooling Policy:**
  - Maintenance operations (`VACUUM`, `REINDEX`, `ANALYZE`, `PRAGMA optimize`) run exclusively through controlled offline tooling (`scripts/optimize_database.py`).
  - Interactive operator confirmation and backup advisories required prior to locking operations (`VACUUM`/`REINDEX`).
  - Zero heavy maintenance executed in online HTTP request paths.
- **Privacy-Preserving Telemetry & Bounded Metrics:**
  - Rolling-window latency percentiles (p50, p95, p99) and cache hit rate computed via `PerformanceMetricsCollector`.
  - Ring buffer bounded to fixed size (`maxlen=1000`) using `collections.deque`.
  - Zero raw search query text logged, stored, or exposed via metrics APIs.

