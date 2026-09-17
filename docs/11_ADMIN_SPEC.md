# Admin Dashboard Specification (Phase 8)

> **Status:** Completed (Phase 8 Verified)  
> **Last Updated:** 2026-09-15  
> **Implementation:** Backend (`src/admin/`, `src/api/admin_routes.py`, `src/api/admin_models.py`), Frontend (`frontend/src/pages/AdminDashboard.tsx`, `frontend/src/components/admin/`)

## 1. Overview
The Admin Dashboard provides a dedicated, token-authenticated management and telemetry portal for the Private Search Engine. It allows system operators to configure and orchestrate background web crawling jobs, inspect live inverted index metrics, monitor host resource consumption (via psutil), review bounded application logs with credential redaction, and modify engine parameters at runtime in memory.

## 2. Authentication & Authorization
- **Model:** Token-protected administration (Single `X-Admin-Token` credential). This is strict admin authentication, not multi-tenant RBAC.
- **Verification:** Constant-time token comparison using `secrets.compare_digest()`.
- **Precedence & Fallback:**
  - `ADMIN_TOKEN` environment variable or `config.server.admin_token`.
  - In production (`ENV=production` or `ENVIRONMENT=production`), missing `ADMIN_TOKEN` causes server error (HTTP 500) preventing unauthorized access.
  - In development/testing (`ENV` in `["development", "test"]`), a documented default development token (`dev-admin-secret-token`) is enabled.
- **Headers:** `X-Admin-Token` or `Authorization: Bearer <token>`.
- **Responses:**
  - Missing token: HTTP 401 Unauthorized (`ErrorResponse`).
  - Invalid token: HTTP 403 Forbidden (`ErrorResponse`).
- **Frontend Storage:** Stored exclusively in `sessionStorage` (cleared on logout or window close); never stored in `localStorage` or URL query parameters.

## 3. Crawler Orchestration & State Machine
- **Deployment:** Single-worker, process-local coordination via `CrawlManager`.
- **Concurrency:** Thread-safe transitions guarded by `asyncio.Lock`.
- **States:** `idle`, `running`, `paused`, `stopped`, `error`.
- **Transitions:**
  - `idle`/`stopped`/`error` $\to$ `running` (`POST /crawler/start`)
  - `running` $\leftrightarrow$ `paused` (`POST /crawler/pause`, `POST /crawler/resume`)
  - `running`/`paused` $\to$ `stopped` (`POST /crawler/stop`)
  - Invalid transitions reject immediately with HTTP 409 Conflict.
- **Background Execution:**
  - Background asynchronous task driving `URLFrontier`, `Fetcher`, `RobotsTxtParser`, `ParserPipeline`, and `BatchIndexer`.
  - Cooperative pause using `asyncio.Event`.
  - Cooperative stop using `asyncio.Event`, ensuring in-flight batch flushes and BM25 IDF recalculations.
- **Defense-in-Depth SSRF Validation:**
  - Enforces URL scheme (`http`, `https`), DNS hostname resolution, and IPv4/IPv6 safety checks.
  - Rejects loopback (127.0.0.1, ::1), private subnets, link-local, multicast, and non-public ranges at the API boundary (HTTP 422).
  - Subsequent network requests continue revalidating redirects in `Fetcher`.

## 4. Telemetry & Metrics
- **Index Metrics (`GET /metrics/index`):**
  - `total_documents`: Live count from metadata table.
  - `total_terms`: Unique terms in inverted index.
  - `total_postings`: Inverted index postings count.
  - `avg_postings_per_term`: Derived posting density.
  - `index_size_mb`: Measured size of SQLite database file on disk.
  - `last_updated`: Timestamp of most recent document indexed.
  - `health_status`: State classification (`healthy`, `empty`, `uninitialized`, `error`).
- **System Metrics (`GET /metrics/system`):**
  - Host CPU utilization % sampled non-blockingly via `psutil.cpu_percent(interval=None)`.
  - Virtual memory utilization % and MB used/total via `psutil.virtual_memory()`.
  - Storage disk utilization % and GB used/total via `psutil.disk_usage('.')`.
  - Strictly measured values only; no placeholder or fake metrics.

## 5. Bounded Log Viewer
- **Endpoint:** `GET /logs`
- **Bounds:** Default 100 lines, strictly capped between 1 and 500 lines (HTTP 422 if exceeded).
- **File:** `data/app.log` read from tail via bounded collections.
- **Filtering:** Optional log level filter (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
- **Sanitization:** Automatic regex redaction of sensitive credentials, admin tokens, passwords, and authorization headers (`***REDACTED***`).
- **Safe Rendering:** Frontend renders logs as pure text nodes (zero usage of `dangerouslySetInnerHTML`).

## 6. Runtime Configuration Allowlist
- **Endpoint:** `GET /config`, `POST /config`
- **Storage:** In-memory overrides only; never mutates `config.yaml` or `.env` on disk.
- **Allowlist:**
  - `log_level`: String (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).
  - `rate_limit_per_minute`: Integer (1 to 10,000).
  - `crawler_max_depth`: Integer (1 to 5).
  - `crawler_politeness_delay`: Float (0.1 to 30.0s).
- Any attempt to modify unlisted settings rejects with HTTP 400 Bad Request.

## 7. Frontend Interface
- **Components:**
  - `CrawlManager.tsx`: Target inputs, validation, controls, and live polling.
  - `StatisticsPanel.tsx`: Key index metrics, refresh trigger, and modal double-confirmation ("CLEAR") index wiper.
  - `SystemMetrics.tsx`: Non-blocking resource gauges with auto-refresh.
  - `LogViewer.tsx`: Tail log stream, line/level filters, and level badge formatting.
  - `ConfigManager.tsx`: Interactive parameter adjustment with in-memory persistence warnings.
- **Theme Support:** Fully cohesive dark and light themes integrated with `variables.css`.
