# Error Handling Strategy

## Setup Errors
- Import errors → Show traceback
- Config errors → Show invalid line
- Directory errors → Suggest mkdir

---

## Crawler Error Handling (Phase 2)

### Network & Timeout Errors
- **Read / Connect Timeout**: Retry with backoff (1s, 3s, 10s) up to 3 times. Return status 408 on exhaustion.
- **Connection Refused / Network Unreachable**: Retry with backoff; return status 502.
- **DNS Failure**: Unresolvable hosts treated as unsafe destinations to prevent blind connection attempts.

### Security & SSRF Violations
- **SSRF Blocked Destination**: Abort immediately with status 403; log warning with target URL.
- **Redirect to Private Destination**: Catch before initiating redirect request, abort with status 403.
- **Redirect Loop**: Detected via visited set; abort with status 400.
- **Excessive Redirects**: Limit to 5 hops; abort with status 400.

### Document Size & Bomb Protection
- **Oversized Wire Content (>10MB)**: Abort response stream immediately; return status 413.
- **Decompression Bomb (>50MB)**: Abort streaming decompression immediately; return status 413.

### robots.txt Errors
- **Missing / 404 robots.txt**: Treat as permitted.
- **Malformed Line**: Skip individual invalid lines; preserve remaining valid rules.
- **No Rules Found**: Default to allow.

---

## Parser & NLP Error Handling (Phase 3)

### Malformed & Empty HTML
- **Empty / Whitespace Input**: `HTMLParser.parse()` detects empty or blank HTML strings, logs a warning, and safely returns `None` without throwing unhandled exceptions.
- **Malformed DOM**: Handled resiliently by the `lxml` tree builder, which auto-closes unclosed tags, cleans corrupted tag hierarchies, and ignores invalid syntax.
- **Missing Metadata Fields**: Missing `<title>`, `<meta>`, `<time>`, or `<article>` tags trigger deterministic fallbacks before defaulting to empty strings `""` or `None`.

### NLP & Tokenization Resilience
- **Missing NLTK Corpora**: `TextProcessor` avoids crashes when `nltk.download` or data packages are absent by falling back to bundled 179 English stop-words and an offline regex tokenizer (`r"[A-Za-z0-9]+(?:'[A-Za-z]+)?"`).
- **Stemming Exceptions**: If `PorterStemmer` encounters irregular character constructs, an exception guard logs a debug trace and falls back to the lowercased raw token.
- **Unicode & Character Encoding**: Normalized UTF-8 strings prevent character slicing errors or mid-codepoint truncation.

### Deduplication & Link Safety
- **Poison State Prevention**: In `ParserPipeline.process_document()`, duplicate fingerprints are only committed to the deduplicator's internal registry after successful document parsing and tokenization. A failed parse never locks out subsequent retries.
- **Malformed Hyperlinks**: Hyperlinks in `href` tags that contain unparseable URIs or non-HTTP schemes (`javascript:`, `mailto:`, `data:`, `ftp:`) are safely discarded without interrupting document processing.

---

## Indexer Error Handling (Phase 4)

### Database Connection & Concurrency Errors
- **Lock Contention**: Mitigated by `PRAGMA journal_mode = WAL;` and `PRAGMA busy_timeout = 5000;`. Writers do not block readers, and concurrent writes wait up to 5 seconds before raising `sqlite3.OperationalError`.
- **Foreign Key Violations**: Enforced via `PRAGMA foreign_keys = ON;`. Incomplete term or document references fail immediately with `sqlite3.IntegrityError`, guaranteeing no orphaned records.
- **Schema Migration**: Database initialization verifies `schema_version == '4.0'` in `metadata`. If legacy or unversioned schemas are found, they are automatically upgraded to v4.0.

### Document Validation & Duplicate Handling
- **Pre-Transaction Validation**: `_normalize_document()` validates required fields (`url`, `content_hash`) before opening database transactions, preventing malformed records.
- **Duplicate Normalized URL**: `add_document()` checks `SELECT doc_id FROM documents WHERE url = ?`. If found, returns existing `doc_id` without re-indexing.
- **Duplicate Content Hash**: Checks `SELECT doc_id FROM documents WHERE content_hash = ?`. If found under a different URL, returns canonical `doc_id` without inserting a redundant document.

### Atomic Transactions & Batch Rollback
- **Single Document Failure**: Inserting a document, updating term DF/CF, creating postings, and refreshing metadata occurs within `with self.connection:` (single atomic transaction). Any exception rolls back all changes completely.
- **Batch Processing Rollback**: `BatchIndexer.flush()` wraps all accumulated documents in one single database transaction. If any unhandled exception occurs, the entire batch transaction is rolled back atomically, ensuring no partial or corrupted batch writes.
- **Deletion Consistency**: `delete_document(doc_id)` atomically decrements term frequencies, updates total and average lengths in metadata, cascades postings deletion, and removes orphaned terms where `document_frequency <= 0`.

---

## Ranker Subsystem Error Handling (Phase 5)

### Query Parsing & Validation Errors
- **Query Length Overflow**: Queries exceeding 500 characters are safely truncated to 500 characters with a logged warning, preventing regex catastrophic backtracking or memory spikes.
- **Term Count Overflow**: Queries containing more than 100 terms are truncated, trimming optional terms first, then required terms.
- **Malformed Syntax Resilience**: Unmatched quotes, loose colons, or stray `+`/`-` characters are stripped and sanitized, guaranteeing that no arbitrary user query raises unhandled exceptions.
- **Empty or Whitespace Queries**: Queries with no valid search terms or filter constraints return empty results `([], None)` immediately without incurring database lookups.

### Search Engine & Ranking Edge Cases
- **Unknown Terms**: Query terms not present in the index vocabulary are ignored during BM25 scoring; if no query terms exist in the index, an empty result list is returned safely.
- **Filter Exclusion Edge Cases**: If all candidate documents are eliminated by `-term` or field filters, `SearchEngine.search()` returns `([], None)` cleanly.
- **Relevance Normalization**: If the top candidate raw score is 0.0 or negative, `relevance_score` safely defaults to 0 to prevent division by zero.
- **Snippet Generation Fallbacks**: If no query terms match within the text, the generator falls back to the document start, preserving word boundaries and avoiding severed tokens.

### End-to-End Pipeline Resilience
- **Crawl & Index Timeouts**: The crawler loop enforces an async timeout deadline, flushing accumulated batch documents and updating BM25 IDFs before terminating.
- **Per-Document Fetch & Parse Failures**: Network failures, HTTP 4xx/5xx errors, or unparseable HTML are caught per URL and marked crawled in the frontier, preventing queue deadlock.

---

## API Error Handling & Structured Responses (Phase 6)

### Uniform Error Response Schema
Every client and server error returns a consistent JSON payload adhering to `ErrorResponse`:
```json
{
  "error": "Error description message",
  "code": 404,
  "timestamp": "2026-09-12T14:30:00Z",
  "request_id": "c3f81e09",
  "details": null
}
```

### HTTP Status Codes Handled
- **400 Bad Request:**
  - Emitted when business rules or pagination constraints are violated (e.g. `offset > server.max_offset`).
  - Response message clearly states the constraint violation.
- **404 Not Found:**
  - Registered globally via `@app.exception_handler(404)`.
  - Returns `Endpoint not found` with `request_id` and standard security headers.
- **422 Unprocessable Entity:**
  - Triggered by FastAPI `RequestValidationError` on invalid query parameters or JSON body schemas.
  - Context objects sanitized with `fastapi.encoders.jsonable_encoder` to prevent non-serializable exception types.
  - Includes structured list of field validation errors in `details`.
- **429 Too Many Requests:**
  - Triggered by sliding-window `RateLimiter` when an IP exceeds `rate_limit_per_minute`.
  - Populates `Retry-After: <seconds>` header alongside standard `X-RateLimit-*` headers.
- **500 Internal Server Error:**
  - Caught globally via middleware or unhandled exception handler.
  - Server stack trace is logged internally with `request_id` and error details.
  - Response payload returns a sanitized generic message (`"Internal server error"`) with the correlating `request_id`, ensuring zero exposure of internal filesystem paths, stack frames, or credentials.
- **503 Service Unavailable:**
  - Raised when the underlying `SQLiteIndexer` or `SearchEngine` is not initialized or database connectivity fails.
  - Readiness check `/api/v1/health` marks `ready: false` and `database_connected: false`.

---

## Frontend Error Handling & State Resilience (Phase 7)

### API Error Normalization (`SearchAPIError`)
The Axios client in `frontend/src/api/client.ts` intercepts HTTP responses and maps status codes to human-readable explanations with structured metadata:
- **422 Unprocessable Entity:** Extracts Pydantic validation message (e.g. *"Query cannot be empty or exceeds 500 characters"*).
- **429 Too Many Requests:** Inspects `Retry-After` response header and displays *"Rate limit exceeded. Please wait X seconds before searching again."*
- **500 Internal Server Error:** Sanitized to *"An unexpected server error occurred. Please try again later."*
- **503 Service Unavailable:** Displays *"Search index service is currently initializing or unavailable."*
- **Network / Offline Failures:** Detects dropped connections and displays *"Unable to connect to search service. Please check your network connection."*

### In-Flight Request Cancellation
- Uses native `AbortController` instances stored in React refs within `useSearch` and `useSuggestions`.
- When a user continues typing or submits a new query, previous pending HTTP requests are aborted immediately.
- The UI filters out cancellation errors (`axios.isCancel` / `err.status === 0`), preventing obsolete or out-of-order responses from overwriting the latest search state.

---

## Security Error Handling & Production Failsafes (Phase 10)

### Administrative Authentication Errors
- **Missing Token (HTTP 401):** When no `X-Admin-Token` or `Authorization: Bearer <token>` header is present, the server returns HTTP 401 with a clean JSON error response (`Admin authentication required.`).
- **Invalid Token (HTTP 403):** If the supplied token does not match the configured admin token via `secrets.compare_digest()`, the server returns HTTP 403 (`Invalid admin token. Access denied.`).
- **Production Misconfiguration (HTTP 500):** If running in production and `admin_token` is unconfigured, empty, or shorter than 32 characters, requests fail with HTTP 500 without leaking token state.

### Production Startup Failsafe
- During application lifespan initialization, `validate_production_security()` validates that when `environment == "production"`, `ADMIN_TOKEN` must be set, >= 32 characters, and have >= 4 distinct characters.
- If any check fails, a `RuntimeError` is raised immediately, halting process startup before socket binding.
- Exception messages and log records strictly avoid printing or logging secret values.

### Injection & Filesystem Boundary Error Handling
- **Search Query Path Traversal:** Search queries containing traversal sequences (`../`, `%2f`, `etc/passwd`) are handled normally as search query text, avoiding false-positive 400/403 rejections. They query SQLite without filesystem access.
- **LogService Traversal Guard:** Any attempt to pass arbitrary filesystem paths to `LogService` is impossible at the API layer because the path is hardcoded to server config.
- **Unsupported Content-Type:** Requests with non-JSON content types (e.g. `application/xml`) to API endpoints reject with HTTP 422, preventing XML External Entity (XXE) attacks.

---

## Cache & Performance Resilience (Phase 11)

### Cache Subsystem Fault Isolation
- **Cache Miss Fallthrough:** The LRU search cache is purely an acceleration layer. If a lookup yields `None` (miss, expired TTL, or disabled), the execution falls through to `SearchEngine.search_with_total()` with zero interruption.
- **Cache Failure Immunity:** Any unexpected exception in the cache layer (e.g., lock contention, eviction errors) is handled defensively without failing user queries, treating errors as transparent cache misses.
- **Non-200 Error Exclusion:** HTTP errors (400 Bad Request, 422 Unprocessable Entity, 500 Internal Error) are never cached. Transient query validation failures or server errors do not pollute the cache or become persistent.

### Telemetry & Metrics Resilience
- **Bounded Deque Protection:** `PerformanceMetricsCollector` uses a fixed-size `collections.deque(maxlen=1000)`. High request volume cannot cause memory leaks or unbounded growth.
- **Lock Contention Defense:** Telemetry recording uses quick thread-safe append operations guarded by `threading.Lock()`. Metric readout calculations use snapshots to prevent holding locks during percentile computation.
- **Zero Query Persistence:** The collector strictly measures duration and cache outcome. No query string or user identifier is ever retained, ensuring that corrupted or malicious query payloads cannot leak into monitoring logs.

### Database Maintenance Safeguards
- **Operator Double Confirmation:** Heavy database operations (`VACUUM`, `REINDEX`) invoked via `scripts/optimize_database.py` require explicit interactive typing confirmation (`yes`) or an explicit `--force` flag.
- **Exclusive Lock Warnings:** The maintenance CLI warns operators that `VACUUM` and `REINDEX` obtain exclusive database locks and suggests making a filesystem backup before proceeding.
- **Zero Request-Path Maintenance:** Maintenance commands are completely decoupled from runtime HTTP request handlers, preventing database locks during live traffic.





