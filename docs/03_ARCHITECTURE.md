# Architecture Overview

## Components
1. **Crawler** - URL frontier, fetcher, robots.txt parser
2. **Parser** - HTML extraction, tokenization, deduplication
3. **Indexer** - Inverted index, SQLite persistence
4. **Ranker** - BM25 scoring, query parsing
5. **API** - FastAPI endpoints
6. **Frontend** - HTML/CSS/JS search interface
7. **Admin** - Crawl dashboard

## Data Flow
```
Seed URLs → Crawler → Parser → Indexer → SQLite → API → Frontend
```

## Module Organization
```
src/
├── crawler/
│   ├── __init__.py      # URLFrontier priority queue & politeness
│   ├── fetcher.py       # Fetcher (async, streaming, SSRF, limits)
│   └── robots.py        # RFC 9309 RobotsTxtParser
├── utils/
│   ├── __init__.py      # Backward-compatible exports
│   └── url.py           # URL normalization, validation, domain extract
├── parser/
│   ├── __init__.py      # HTMLParser (lxml, metadata, extraction hierarchy)
│   ├── text.py          # TextProcessor (offline tokenization, stop-words, stemmer)
│   ├── dedup.py         # ContentDeduplicator (SHA-256 fingerprinting)
│   ├── linker.py        # LinkExtractor (prioritization, domain & depth filtering)
│   └── integration.py   # ParserPipeline & ParsedDocument dataclass
├── indexer/
│   ├── __init__.py      # SQLiteIndexer (schema v4.0, transactional updates, DF/CF, WAL)
│   ├── schema.sql       # 4-table relational inverted index schema & 6 indices
│   ├── tfidf.py         # BM25Ranker (Robertson IDF, field boosting, TFIDFRanker alias)
│   └── batch.py         # BatchIndexer (atomic all-or-nothing batch flushes)
├── ranker/
├── models.py
├── config.py
├── logger.py
├── main.py
└── cli.py
```

---

## Crawler Architecture (Phase 2)

### URLFrontier
- Priority queue using Python's `heapq` module with integer priority (lower integer = higher priority).
- Per-domain politeness tracking using high-resolution `time.monotonic()`.
- Separated URL state tracking: `queued`, `in_flight`, and `crawled` to prevent duplicate enqueuing.
- Automatic canonical normalization before insertion.
- Non-blocking domain scheduling to avoid busy-wait loops on cooled domains.

### Fetcher & FetchResult
- Built on `httpx.AsyncClient` with streaming response iteration.
- Strict SSRF defense: DNS resolution of hostnames and IP address validation across IPv4 and IPv6 non-public ranges.
- Manual redirect execution (`follow_redirects=False`) ensuring SSRF re-validation on every redirect target.
- Loop detection and hop cap (5 max redirects).
- Dual size bounds: 10MB wire limit and 50MB decompressed limit.
- Typed `FetchResult` dataclass with backward-compatible tuple unpacking.

### RobotsTxtParser (RFC 9309)
- RFC 9309 compliant path pattern matching with `*` wildcards and `$` end anchors.
- Precedence: longest matching pattern wins; if equal length conflict occurs, Allow wins.
- Case-insensitive agent selection with wildcard fallback.
- Extensions: `Crawl-delay` and `Request-rate` extraction.

---

## Parser Architecture (Phase 3)

### HTMLParser
- Built with BeautifulSoup4 utilizing the high-performance C-based `lxml` backend.
- Non-content element stripping: Automatically decomposes `<script>`, `<style>`, `<noscript>`, `<nav>`, `<footer>`, `<template>`, `<header>`, `<aside>` nodes.
- Extraction fallbacks:
  - **Body Content:** Prefers `<article>` → `<main>` → `<body>`.
  - **Title:** `<title>` → `<meta property="og:title">` → `<h1>`.
  - **Description:** `<meta property="og:description">` → `<meta name="description">`.
  - **Publication Date:** `<meta itemprop="datePublished">` → `<meta property="article:published_time">` → `<time datetime>` → `<meta name="pubdate">` / `<meta name="date">`.
- Truncation limits enforced on normalized Unicode character strings:
  - Title: 200 characters max (`[:200]`).
  - Description: 500 characters max (`[:500]`).
  - Body: 1,048,576 characters max (`[:1_048_576]`).

### TextProcessor
- Completely offline operation: zero runtime remote calls (`nltk.download()` prohibited).
- Fallback tokenization: If NLTK data files are absent, seamlessly falls back to regex pattern `r"[A-Za-z0-9]+(?:'[A-Za-z]+)?"`.
- Bundled 179-word standard English stop-words dataset.
- Porter Stemming via NLTK `PorterStemmer` with defensive fallback.
- Frequency preservation: `tokens` retains repeated terms for BM25 term frequencies; `terms` preserves the unique set.

### ContentDeduplicator
- SHA-256 fingerprinting using distinct field separator: `f"{title}\n---BODY---\n{body}"`.
- Whitespace-collapsed and lowercased input normalization prevents false differences from insignificant whitespace changes.
- Safe lifecycle: Hash is only committed to the seen registry after successful document parsing.

### LinkExtractor
- Resolves relative links against document canonical/fetch URL using `urllib.parse.urljoin`.
- Strips fragment identifiers (`#...`) and rejects non-HTTP schemes (`javascript:`, `mailto:`, `tel:`, `data:`, `ftp:`).
- Configurable priority scoring based on same-domain preference and path depth penalization.

### ParserPipeline & ParsedDocument
- End-to-end coordinator chaining HTML parsing, duplicate check, tokenization, and link extraction.
- Outputs typed `ParsedDocument` dataclass supporting dict-subscript indexing (`doc["title"]`, `doc.get(...)`).
- Duplicate documents return `None`, cleanly terminating downstream indexing without side effects.

---

## Indexer Architecture (Phase 4)

### SQLiteIndexer
- **Relational Storage & PRAGMAs**: SQLite 3 configured with `PRAGMA foreign_keys = ON;`, `PRAGMA journal_mode = WAL;`, and `PRAGMA busy_timeout = 5000;`.
- **Lifecycle Protocol**: Explicit `close()` method and context manager protocol (`with SQLiteIndexer(...) as indexer:`).
- **Schema Management (v4.0)**: Automates initialization and migration from legacy schemas via `schema_version` validation in the `metadata` table.
- **Input Adapter**: Normalizes `ParsedDocument` or dictionary instances, validating required fields (`url`, `content_hash`) prior to database transactions.
- **Atomic Operations**: Single document indexing executes inside an atomic SQLite transaction updating `documents`, `terms`, `postings`, DF/CF statistics, and metadata.
- **Document Length**: Recorded as processed token count (`document_length INTEGER NOT NULL DEFAULT 0`).
- **Postings Storage**: Stores raw `term_frequency`, `title_frequency`, `body_frequency`, and JSON-serialized `positions`.
- **Deletion Consistency**: `delete_document(doc_id)` decrements term frequencies, updates running metadata, and deletes orphaned terms whose document frequency reaches zero.

### BM25Ranker (Aliased as `TFIDFRanker`)
- **Ranking Formula**: Robertson-Spärck Jones BM25 with parameter defaults `k1=1.5`, `b=0.75`.
- **Inherently Positive IDF**: `idf = log(1.0 + (N - df + 0.5) / (df + 0.5))`, ensuring positive scores across all document frequencies.
- **Field Boosting**: Calculates effective term frequency via configurable weights (`title_boost=2.0`, `body_boost=1.0`).
- **Length Normalization**: Retrieves `avg_document_length` in $O(1)$ from `metadata`, avoiding table scans during query time.
- **Query Processing**: Handles multi-term queries, repeated query terms, unknown terms, and Unicode queries.

### BatchIndexer
- **Transactional Batching**: Accumulates documents in-memory up to `batch_size` (default 100).
- **All-or-Nothing Flushes**: Flushes accumulated documents within a single atomic database transaction, rolling back all items on failure.
- **Post-Batch Optimization**: Automatically recalculates IDFs upon successful batch commit.

---

## Ranker Subsystem Architecture (Phase 5)

### QueryParser & ParsedQuery
- **Structured Parsing**: Deconstructs raw user input into `ParsedQuery` containing:
  - `optional_terms`: Standard terms contributing to BM25 candidate scoring.
  - `required_terms`: Terms prefixed with `+` that must appear in candidate documents.
  - `excluded_terms`: Terms prefixed with `-` that disqualify candidate documents.
  - `phrases`: Multi-word expressions enclosed in quotes (`"..."`) requiring contiguous substring matches.
  - `field_filters`: Structured key-value constraints (`field:val`) matching metadata columns (`language`, `author`, `domain`, `title`).
- **Safety Limits**: Limits input to 500 characters, 100 terms maximum, and 50 characters per term.
- **Defensive Normalization**: Cleans punctuation edges, lowercases all tokens, and preserves intra-word hyphens.

### SnippetGenerator
- **Contextual Centering**: Identifies first or densest query term occurrence and constructs a 150–200 character window.
- **Word Boundary Snapping**: Walks backwards and forwards to the nearest whitespace to prevent truncated or severed words.
- **Markdown Highlighting**: Wraps matching query terms in `**term**` markdown tags using regex with word boundary anchoring (`\b`), sorted descending by term length to eliminate substring collisions.
- **Ellipsis Formatting**: Adds prefix `... ` and suffix ` ...` when boundaries fall within the document text.
- **Sentence Context**: Provides `extract_context(text, term)` extracting complete sentences containing the requested term.

### SearchEngine
- **Two-Stage Execution**:
  1. **Candidate Retrieval**: Passes query terms and their stemmed variants to `BM25Ranker` to retrieve an over-sampled candidate pool from the SQLite inverted index.
  2. **Post-Filtering**: Evaluates candidates against required terms, excluded terms, exact phrases, and field filters.
- **Relevance Normalization**:
  - Maps raw BM25 floating-point scores to a user-facing `0–100` percentage relative to the top candidate score (`(score / top_score) * 100`).
  - Top document receives 100%; subsequent documents are scaled proportionately.
- **Query Autocomplete**: `get_suggestions(prefix)` queries the SQLite `terms` table by prefix ordered by collection frequency and document frequency.

### EndToEndPipeline
- **Unified Coordinator**: Glues together `URLFrontier`, `Fetcher`, `ParserPipeline`, `SQLiteIndexer`, `BatchIndexer`, and `SearchEngine`.
- **Asynchronous Crawl Loop**:
  - Dequeues URLs from frontier with politeness delays.
  - Asynchronously fetches HTML documents.
  - Parses content, extracts links, and enqueues discovered URLs back into the frontier.
  - Batches parsed documents and atomically commits them to the SQLite index.
  - Recalculates corpus-wide BM25 IDFs upon crawl completion.
- **Search & Admin Interface**: Exposes unified `search()`, `get_suggestions()`, and `get_statistics()`.

---

## FastAPI Server & REST API Architecture (Phase 6)

### Application Lifecycle & Factory Pattern
- **Application Factory (`create_app`)**:
  - Accepts optional `Config`, `SQLiteIndexer`, `SearchEngine`, and `RateLimiter` instances.
  - Allows unit and integration tests to inject temporary in-memory databases and controllable clocks without mutating global state.
  - Dynamically builds FastAPI instance with metadata, tags (`search`, `suggest`, `stats`, `health`, `system`), and route registrations.
- **Lifespan Context Manager (`lifespan`)**:
  - **Startup**: Ensures logging is configured, loads configuration if not provided, creates `SQLiteIndexer` (`check_same_thread=False` for threadpool safety), instantiates `SearchEngine`, and registers them on `app.state.indexer` and `app.state.search_engine`.
  - **Shutdown**: Gracefully invokes `indexer.close()`, cleanly terminating SQLite connections and releasing write locks.

```
                    ┌────────────────────────┐
                    │    HTTP Request        │
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │  Request ID Extraction │ (Generates/validates safe X-Request-ID)
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │ RateLimiter Middleware │ (Sliding-window IP check; 429 if exceeded)
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │    CORS Middleware     │ (Origins, methods, headers filtering)
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │ Router & Validation    │ (Pydantic v2 schemas: 422 if invalid)
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │ Dependency Injection   │ (Extracts indexer/engine from app.state)
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │ Service Execution      │ (_execute_search_service / BM25 search)
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │ Security Headers Added │ (nosniff, DENY, CSP, XSS, HSTS)
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │  HTTP Response Sent    │ (Status code, body, latency logged)
                    └────────────────────────┘
```

### Middleware Chain
1. **Request ID & Audit Logging Middleware**:
   - Inspects incoming `X-Request-ID`. If matching `^[a-zA-Z0-9\-_]{1,64}$`, retains it; otherwise generates an 8-character UUID.
   - Stores `request_id` in `request.state.request_id` for downstream handlers and logging.
   - Measures request duration with high-resolution `time.perf_counter()` and logs method, path, status, and latency.
   - Appends `X-Request-ID` to all outgoing responses.
2. **Rate Limiting Middleware**:
   - Evaluates client IP against an in-memory sliding-window bucket.
   - Client IP is extracted directly via `request.client.host` unless peer matches `trusted_proxies`.
   - Appends `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` to all responses.
   - If exceeded, short-circuits with HTTP 429 and `Retry-After` header.
3. **Security Headers Middleware**:
   - Enforces nosniff, DENY framing, no-referrer, XSS protection, and Content Security Policy on all responses including error paths.
   - Injects `Strict-Transport-Security` if configured or requested over HTTPS.
4. **CORS Middleware**:
   - Configurable via `server.cors_origins` allowing cross-origin frontends.

### Dependency Injection Pattern
- Replaces mutable module-level globals (`set_search_engine`) with FastAPI dependencies:
  - `get_indexer(request: Request) -> SQLiteIndexer`: Accesses `request.app.state.indexer`.
  - `get_search_engine(request: Request) -> SearchEngine`: Accesses `request.app.state.search_engine`.
  - Raises HTTP 503 Service Unavailable if dependencies are uninitialized or degraded.

---

## Frontend Search UI Architecture (Phase 7)

### Component Hierarchy
```
App (BrowserRouter)
 └── SearchContent (useSearchParams, useTheme)
      ├── Header (Branding, Metrics, Theme Toggle)
      ├── SearchBar (useSuggestions, Keyboard Nav, ARIA combobox)
      │    └── Suggestions (ARIA listbox, active item highlights)
      ├── ResultsList (Loading Spinner, Error Alert, Empty State)
      │    └── SearchResult (Safe Snippet Highlighting, Relevance Badge)
      ├── Pagination (Windowed Pages, ARIA current, Next/Prev)
      └── Footer (Privacy notice)
```

### Custom Hooks & State Flow
```
                     ┌────────────────────────┐
                     │    Browser URL Query   │ (/?q=term&page=2)
                     └───────────┬────────────┘
                                 │
                     ┌───────────▼────────────┐
                     │     SearchContent      │ (useSearchParams synchronization)
                     └───────────┬────────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            │                    │                    │
┌───────────▼────────────┐┌──────▼─────────────┐┌─────▼──────────────┐
│       useSearch        ││   useSuggestions   ││   usePagination    │
│  - AbortController     ││  - 300ms debounce  ││  - totalPages math │
│  - in-flight cancel    ││  - AbortController ││  - smooth scroll   │
│  - error mapping       ││  - Arrow Up/Down   ││  - active indicator│
└───────────┬────────────┘└──────┬─────────────┘└────────────────────┘
            │                    │
            └──────────┬─────────┘
                       │ (Axios HTTP Client)
            ┌──────────▼────────────┐
            │ Vite Dev Server Proxy │ (/api -> http://localhost:8000)
            └──────────┬────────────┘
                       │
            ┌──────────▼────────────┐
            │    FastAPI Backend    │ (/api/v1/search, /api/v1/suggest)
            └───────────────────────┘
```

### Key Architectural Principles
1. **Unidirectional URL Data Flow**:
   - The URL parameter `q` and `page` is the single source of truth for query and pagination.
   - Form submission and pagination click handlers invoke `setSearchParams`, which triggers downstream hooks, ensuring browser back/forward buttons work flawlessly.
2. **Deterministic Request Cancellation**:
   - Both `useSearch` and `useSuggestions` store the active `AbortController` in a React ref.
   - When a new request is queued, any preceding in-flight request is immediately aborted, preventing race conditions or outdated results from overwriting newer queries.
3. **Safe Virtual DOM Highlighting**:
   - Excerpts are parsed and transformed directly into React elements (`<mark className="highlight-term">` and text fragments).
   - Bypasses `dangerouslySetInnerHTML` entirely, completely eliminating client-side XSS attack vectors.
4. **Theme Management**:
---

## Admin Subsystem Architecture (Phase 8)

### Module Organization
```
src/
├── admin/
│   ├── __init__.py           # Subsystem exports (CrawlManager, MetricsCollector, etc.)
│   ├── crawl_manager.py      # Background crawl coordinator, state machine & cooperative events
│   ├── metrics.py            # SQLite index metrics & psutil host utilization sampler
│   ├── config_service.py     # In-memory allowlist for runtime engine reconfiguration
│   └── log_service.py        # Bounded tail reader with credential/token redaction
├── api/
│   ├── admin_models.py       # Pydantic v2 schemas for request, response, telemetry
│   └── admin_routes.py       # FastApi router (/api/v1/admin/*) with constant-time token auth
```

### Architecture & Component Interaction
```
┌─────────────────────────────────────────────────────────────┐
│                 React Admin Dashboard UI                    │
│ (sessionStorage Token, CrawlManager, Stats, Logs, Config)   │
└──────────────────────────────┬──────────────────────────────┘
                               │ (X-Admin-Token Header)
┌──────────────────────────────▼──────────────────────────────┐
│               FastAPI verify_admin_token Dependency         │
│         (Constant-time secrets.compare_digest)             │
└──────┬───────────────────────┼───────────────────────┬──────┘
       │                       │                       │
┌──────▼──────────┐     ┌──────▼──────────┐     ┌──────▼──────────┐
│  CrawlManager   │     │MetricsCollector │     │  ConfigService  │
│ - asyncio.Lock  │     │ - SQLite stats  │     │ - in-memory map │
│ - State Machine │     │ - psutil metrics│     │ - runtime apply │
│ - Async Worker  │     └─────────────────┘     └─────────────────┘
└──────┬──────────┘
       │ (Drives Crawl Pipeline)
┌──────▼──────────────────────────────────────────────────────┐
│ URLFrontier → Fetcher (SSRF) → RobotsTxtParser → Pipeline   │
└─────────────────────────────────────────────────────────────┘
```

### State Machine & Concurrency Control
- Thread-safe state transitions guarded by `asyncio.Lock`.
- States: `idle`, `running`, `paused`, `stopped`, `error`.
- Cooperative pause: Workers check `_pause_event.wait()` between iterations, completing active HTTP transactions before suspending.
- Cooperative stop: Workers observe `_stop_event.is_set()`, safely break loop, and atomically flush all buffered documents in `BatchIndexer`.
- Defense-in-depth SSRF: Seed URLs undergo scheme validation, hostname resolution, and IPv4/IPv6 safety checks prior to job acceptance.

### Strictly Measured Telemetry
- **Host Metrics:** Sampled via non-blocking `psutil.cpu_percent(interval=None)`, `psutil.virtual_memory()`, and `psutil.disk_usage('.')`. No synthetic or placeholder statistics.
- **Index Metrics:** Extracted directly from SQLite metadata table and database file filesystem statistics.
- **Log Inspection:** Bounded tail access ($\le 500$ lines) with multi-pattern regex redaction (`***REDACTED***`).

### Security Model
- Described as token-protected administration (not full RBAC).
- Missing token yields HTTP 401; invalid token yields HTTP 403.
- Production mode strictly requires `ADMIN_TOKEN` environment variable; development/test environments permit fallback dev token.
- Token stored only in `sessionStorage` and cleared upon logout.

---

## Security Architecture & Defense Boundaries (Phase 10)

```
[ Incoming Request ]
         │
         ▼
┌────────────────────────────────────────────────────────┐
│ 1. Network Boundary (Middleware Layer)                 │
│    - Right-to-left trusted proxy traversal             │
│    - Per-IP sliding window rate limiting               │
│    - Baseline security headers                         │
│    - 1MB body limit & unsupported Content-Type reject  │
└────────────────────────┬───────────────────────────────┘
                         │
        ┌────────────────┴────────────────┐
        ▼                                 ▼
┌───────────────────────────────┐ ┌────────────────────────────────┐
│ 2. Public Search Pipeline     │ │ 3. Administrative Boundary     │
│    - Pure text data queries   │ │    - Constant-time token auth  │
│    - Zero filesystem access   │ │    - Production entropy check  │
│    - Parameterized SQLite     │ │    - In-memory config map      │
│    - BM25 Okapi ranking       │ │    - Bounded log viewer        │
└───────────────────────────────┘ └────────────────┬───────────────┘
                                                   │
                                                   ▼
                                  ┌────────────────────────────────┐
                                  │ 4. Outbound Crawler Boundary   │
                                  │    - Two-phase SSRF validation │
                                  │    - Scheme & IP block checks  │
                                  │    - Redirect-hop revalidation │
                                  └────────────────────────────────┘
```

### 1. Search Query as Pure Data
- User search queries are treated strictly as query text data, not filesystem paths or SQL instructions.
- Search queries containing traversal sequences (`../`, `%2f`, `etc/passwd`) are indexed and matched against document content without touching the filesystem.
- Parameterized SQLite queries (`?` placeholders) eliminate SQL injection vectors.

### 2. Filesystem Confinement Boundary
- Filesystem operations are strictly confined:
  - `LogService`: Reads exclusively from pre-configured `log_file_path` (default `data/app.log`) with bounded tail (max 500 lines) and credential masking.
  - `SQLiteIndexer`: Interacts exclusively with the pre-configured database path.

### 3. Production Admin Token Failsafe
- In production (`environment == "production"`), `src/main.py:lifespan` validates that `ADMIN_TOKEN` is set, >= 32 characters, contains >= 4 distinct characters, and does not equal the default dev token.
- Violations trigger an immediate `RuntimeError` on startup without leaking token contents in logs.
- Admin token comparison uses `secrets.compare_digest()` to eliminate timing attacks.

### 4. Crawler SSRF Defense Boundary
- Crawler seed URLs and discovered links are validated against private, loopback, link-local, multicast, and CGNAT IP spaces prior to initiating connections.
- Validation is re-evaluated on every redirect hop to prevent redirect-based SSRF.

---

## Performance & Query Caching Architecture (Phase 11)

### Subsystem Overview
```
┌────────────────────────────────────────────────────────────────────────┐
│                        Incoming Search Request                         │
│                    (/api/v1/search?q=term&limit=10)                    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                         ┌──────────▼──────────┐
                         │  Clean & Normalize  │ (clean_query = query.strip())
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │   Get Generation    │ (indexer.get_generation() from SQLite)
                         └──────────┬──────────┘
                                    │
                                    │ Cache Key: (gen, clean_query.lower(), limit, offset)
                         ┌──────────▼──────────┐
                         │   LRUCache Lookup   │
                         └─────┬──────────┬────┘
                    HIT        │          │ MISS
         ┌─────────────────────┘          └─────────────────────┐
         ▼                                                      ▼
┌──────────────────┐                                  ┌──────────────────┐
│ Clone Cached Res │                                  │  Search Engine   │
│ X-Cache: HIT     │                                  │  (BM25 Ranking)  │
└────────┬─────────┘                                  └────────┬─────────┘
         │                                                     │
         │                                            ┌────────▼─────────┐
         │                                            │ Batch Prefetch   │
         │                                            │ (chunked SQL)    │
         │                                            └────────┬─────────┘
         │                                                     │
         │                                            ┌────────▼─────────┐
         │                                            │ Store in Cache   │
         │                                            │ X-Cache: MISS    │
         │                                            └────────┬─────────┘
         │                                                     │
         └─────────────────────┬───────────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │ Record Latency &    │ (Rolling deque, zero raw queries)
                    │ Cache Telemetry     │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │    HTTP Response    │
                    └─────────────────────┘
```

### 1. In-Memory Service-Layer LRU Cache (`src/cache/`)
- **Location:** Integrated directly in `src/api/routes.py:_execute_search_service()`.
- **Concurrency Safety:** Thread-safe using `threading.Lock()` wrapping an internal `collections.OrderedDict`.
- **Cache Key Design:** Deterministic 4-tuple `(generation, clean_query.lower(), limit, offset)` completely prevents collisions between distinct pagination windows or index states.
- **TTL Expiry & Capacity Eviction:** Monotonic clock verification (`time.monotonic()`) purges expired entries upon access. Exceeding `max_size` (1,000 entries) evicts the least-recently used entry via `OrderedDict.popitem(last=False)`.
- **Defensive Immutability:** Cache hits return fresh copies (`copy.deepcopy()` or reconstructed Pydantic schema) ensuring subsequent modifications do not corrupt cached objects.
- **Header Attribution:** `X-Cache: HIT` or `X-Cache: MISS` attached directly to the response object.

### 2. Persistent Transactional Index Generation
- **SQLite Storage:** Stored in `metadata` table under key `'index_generation'` (initialized to `'1'`).
- **Transactional Bumping:** Increments monotonically inside the exact same database transaction that commits mutations (`add_document`, `delete_document`, `clear_index`, `BatchIndexer.flush()`).
- **Rollback & No-Op Isolation:** Skipped duplicate documents (by URL or content hash) or aborted transactions do not advance the generation, avoiding unnecessary cache invalidation.
- **Process Restart Resilience:** Generation counter is read on startup and persists across server reboots.

### 3. Hot Path Batch Document Retrieval (`src/indexer/`, `src/ranker/`)
- **N+1 Elimination:** Replaced sequential `get_document(doc_id)` invocations across BM25 candidate sets with `indexer.get_documents_by_ids(doc_ids, batch_size=500)`.
- **Parameterized SQL:** Formulates parameterized `WHERE doc_id IN (?, ?, ...)` queries in chunks of 500, respecting SQLite parameter limits and eliminating dynamic SQL risks.
- **Ranking Invariance:** BM25 scoring, document candidate filtering, field boosting, and length normalization remain 100% invariant.

### 4. Bounded Latency Telemetry (`src/monitoring/`)
- **Storage:** Fixed-size ring buffer (`collections.deque(maxlen=1000)`) in `PerformanceMetricsCollector`.
- **Percentiles:** Computes exact nearest-rank p50, p95, and p99 percentiles without unbounded memory growth.
- **Privacy Boundary:** Strictly isolates telemetry from user data. Zero search query strings, IP addresses, or sensitive payloads are collected or exposed.

### 5. Database Query Optimization & Maintenance (`src/db/`, `scripts/`)
- **Query Plan Verification:** `QueryOptimizer.explain_query()` provides parameterized `EXPLAIN QUERY PLAN` inspection to verify index coverage (`sqlite_autoindex_terms_1`, `sqlite_autoindex_postings_1`).
- **Offline Maintenance:** `DatabaseOptimizer` wraps `PRAGMA optimize`, `ANALYZE`, `VACUUM`, and `REINDEX`. Exposed exclusively through `scripts/optimize_database.py` with operator prompts and safety warnings.

---

## Phase 12: Production Deployment & Operational Readiness Architecture

```
                    ┌────────────────────────────────────────────────────────┐
                    │                   Kubernetes Ingress                   │
                    │               (TLS Termination, Port 443)              │
                    └───────────┬────────────────────────────────┬───────────┘
                                │                                │
                      /api, /   │                                │ /metrics
                                ▼                                ▼
                    ┌────────────────────────┐         ┌─────────────────────┐
                    │  search-engine-service │         │  BLOCKED AT INGRESS │
                    │       (ClusterIP)      │         │   (404 Forbidden)   │
                    └───────────┬────────────┘         └─────────────────────┘
                                │
                                ▼
                    ┌────────────────────────────────────────────────────────┐
                    │               search-engine-deployment                 │
                    │       replicas: 1 (ADR D039), strategy: Recreate       │
                    │   ┌────────────────────────────────────────────────┐   │
                    │   │        Pod: search-engine-api (appuser:1000)   │   │
                    │   │  - FastAPI App + SPA Static Files              │   │
                    │   │  - Centralized Prometheus Exporter (/metrics)  │   │
                    │   │  - Process-Local LRUCache & RateLimiter        │   │
                    │   │  - Embedded SQLite Engine (WAL Mode)           │   │
                    │   └───────────────────────┬────────────────────────┘   │
                    └───────────────────────────┼────────────────────────────┘
                                                │
                                                ▼
                               ┌─────────────────────────────────┐
                               │  search-engine-data-pvc (RWO)   │
                               │  /app/data/index.db + WAL       │
                               │  /app/data/backups/             │
                               └─────────────────────────────────┘
                                                ▲
                                                │ Scrape /metrics (15s)
                               ┌────────────────┴────────────────┐
                               │       Prometheus & Grafana      │
                               │   (Internal Cluster Monitoring) │
                               └─────────────────────────────────┘
```

### 1. Single-Replica Deployment Mandate (ADR D039)
- **Embedded Database Constraint:** The system is powered by embedded SQLite with Write-Ahead Logging (WAL). Concurrent write access across multiple container replicas sharing a networked file volume (`ReadWriteOnce`) causes database lock contention, torn pages, and corrupted WAL indexes.
- **Process-Local State:** Caching (`LRUCache`), rate-limiting (`RateLimiter`), and background crawl orchestration (`CrawlManager`) are entirely in-memory and process-local.
- **Enforcement:** `k8s/deployment.yaml` enforces `replicas: 1` with `strategy: type: Recreate` to ensure the existing pod is completely terminated before a replacement pod mounts the PVC. Horizontal Pod Autoscaling (HPA) and Pod Disruption Budgets (PDB) are intentionally omitted.

### 2. Centralized Prometheus Observability (ADR D040)
- **Application-Owned Registry:** Each FastAPI instance owns an isolated `prometheus_client.CollectorRegistry`, guaranteeing 100% test isolation and avoiding duplicate metric errors during unit testing.
- **Centralized HTTP Tracking:** `request_lifecycle_middleware` captures request counts (`http_requests_total`) and duration histograms (`http_request_duration_seconds`) using normalized route template labels (e.g. `/api/v1/search`, `/health`, or bounded `"unmatched"` on 404), preventing label cardinality explosion from attacker-crafted paths.
- **Authoritative Cache Metrics:** Search cache hits (`search_engine_cache_hits_total`) and misses (`search_engine_cache_misses_total`) are tracked at the single execution site in `_execute_search_service()`.
- **Telemetry Privacy Boundary:** Banning search query text in metric dimensions ensures user privacy is preserved.

### 3. Multi-Stage Hardened Containerization
- **Stage 1 (Frontend):** `node:20-alpine` builds the React/TypeScript SPA into static bundles (`/frontend/dist`).
- **Stage 2 (Python Builder):** `python:3.11-slim` installs system C compilers and builds binary wheels into `/wheels`.
- **Stage 3 (Runtime):** `python:3.11-slim` installs wheels without build compilers, copies built SPA assets and application source, creates unprivileged system user `appuser` (UID:GID 1000:1000), and drops root privileges.
- **Container Healthcheck:** Uses standard library `urllib.request` against `/health` without external curl dependencies.

### 4. Live WAL Consistent SQLite Backup Subsystem (ADR D041)
- **Online Backup API:** `scripts/backup_database.py` utilizes `sqlite3.connect().backup()` to capture transactionally consistent database snapshots without locking concurrent active readers or writers.
- **Integrity Digest:** Produces SHA-256 cryptographic checksum files alongside snapshots.
- **Logical Validation:** Executes `PRAGMA integrity_check` on snapshot before marking completion.
- **Non-Destructive Sandbox Verification:** The `--verify-restore` flag copies the snapshot into an isolated temporary directory, opens it via `SQLiteIndexer`, and executes smoke queries to verify full recoverability.
- **Safe Aging Purge:** Retains backups matching `index_backup_*.db` within configurable `--retention-days`.


