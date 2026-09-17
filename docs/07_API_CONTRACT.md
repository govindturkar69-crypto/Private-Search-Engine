# API Contract Specification

> **Status:** Active / Synchronized with Phase 6 (Search API & FastAPI Server Complete)

## Overview
Production REST API implemented with FastAPI, exposing search, autocomplete suggestions, index statistics, and health check endpoints. Includes strict Pydantic v2 validation, sliding-window rate limiting, security headers, and structured error responses.

---

## Standard Headers

### Request Headers
| Header | Type | Description |
|---|---|---|
| `X-Request-ID` | String | Optional client request identifier (alphanumeric, `-`, `_`, max 64 chars). Preserved if valid; generated UUID otherwise. |
| `Content-Type` | String | `application/json` for POST requests. |

### Response Headers
| Header | Example | Description |
|---|---|---|
| `X-Request-ID` | `c3f81e09` | Unique identifier for request tracing. |
| `X-RateLimit-Limit` | `60` | Maximum requests permitted per client IP per window (60s). |
| `X-RateLimit-Remaining` | `59` | Remaining requests permitted in the current window. |
| `X-RateLimit-Reset` | `1726154820` | Unix epoch timestamp when the current window resets. |
| `Retry-After` | `45` | Seconds to wait before retrying (sent on HTTP 429). |
| `X-Content-Type-Options` | `nosniff` | Prevents MIME type sniffing. |
| `X-Frame-Options` | `DENY` | Prevents clickjacking framing. |
| `Referrer-Policy` | `no-referrer` | Restricts referrer leakage. |
| `X-XSS-Protection` | `1; mode=block` | Legacy cross-site scripting filter. |
| `Content-Security-Policy` | `default-src 'self'` | Restricts resource loading. |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | Enforced when HTTPS or `server.enable_hsts=true`. |

---

## Endpoints

### 1. Search Endpoints

#### POST `/api/v1/search` (and legacy alias `POST /api/search`)
- **Description:** Primary full-text search endpoint supporting JSON payloads.
- **Request Body (`SearchRequest`):**
```json
{
  "query": "python +fast -legacy \"machine learning\"",
  "limit": 10,
  "offset": 0
}
```
- **Constraints:**
  - `query`: String, min length 1, max length 500. Leading/trailing whitespace is stripped. Empty/whitespace-only rejected with HTTP 422.
  - `limit`: Integer, min 1, max 100, default 10.
  - `offset`: Integer, min 0, default 0. Cannot exceed `server.max_offset` (default: 10,000; returns HTTP 400).

#### GET `/api/v1/search` (and legacy alias `GET /api/search`)
- **Description:** Idempotent GET search supporting browser and bookmark lookups.
- **Query Parameters:**
  - `q` (string, required): Query string (1–500 chars).
  - `limit` (int, optional, default: 10): Results per page (1–100).
  - `offset` (int, optional, default: 0): Pagination offset (>= 0).

#### Search Response (`200 OK` - `SearchResponse`)
```json
{
  "query": "python +fast -legacy",
  "total": 1,
  "limit": 10,
  "offset": 0,
  "took_ms": 12.45,
  "results": [
    {
      "doc_id": 1,
      "url": "https://example.com/python-fast",
      "title": "Python Fast Applications",
      "description": "Building fast web apps with modern Python.",
      "snippet": "... modern **Python** is an expressive and **fast** programming language ...",
      "score": 3.8421,
      "relevance_score": 100,
      "metadata": {
        "author": "Guido van Rossum",
        "language": "en",
        "published_at": "2026-01-15T00:00:00Z",
        "content_hash": "a1b2c3d4e5f6...",
        "document_length": 142
      }
    }
  ]
}
```

---

### 2. Autocomplete Suggestions

#### GET `/api/v1/suggest` (and legacy alias `GET /api/suggest`)
- **Description:** Autocomplete suggestions based on indexed term frequencies.
- **Query Parameters:**
  - `prefix` (string, required): Prefix to complete (1–50 characters, whitespace stripped).
  - `limit` (int, optional, default: 5): Maximum suggestions (1–50).
- **Response (`200 OK` - `SuggestResponse`):**
```json
{
  "prefix": "py",
  "suggestions": [
    "python",
    "pytest",
    "pydantic",
    "pyyaml"
  ]
}
```

---

### 3. Statistics Endpoint

#### GET `/api/v1/stats` (and legacy alias `GET /api/stats`)
- **Description:** System corpus and index metrics.
- **Response (`200 OK` - `StatsResponse`):**
```json
{
  "index": {
    "total_documents": 1250,
    "total_terms": 18450,
    "total_postings": 154200,
    "total_document_length": 842000,
    "avg_document_length": 673.6,
    "avg_postings_per_term": 8.35,
    "schema_version": "4.0"
  },
  "frontier": {
    "queued_urls": 0,
    "crawled_urls": 0,
    "in_flight_urls": 0
  }
}
```

---

### 4. Health & Liveness Endpoints

#### GET `/api/v1/health`
- **Description:** Detailed health and readiness probe.
- **Response (`200 OK` - `HealthResponse`):**
```json
{
  "status": "healthy",
  "service": "Private Search Engine",
  "version": "1.0.0",
  "ready": true,
  "database_connected": true,
  "total_documents": 1250,
  "total_terms": 18450
}
```
*Note: Sensitive paths (e.g. database filesystem path) are strictly omitted.*

#### GET `/health` & GET `/api/health` & GET `/`
- **Description:** Lightweight liveness probes for Docker/Kubernetes and load balancers.
- **Response (`200 OK`):**
```json
{
  "status": "ok",
  "service": "Private Search Engine",
  "version": "1.0.0"
}
```

#### GET `/metrics`
- **Description:** Official Prometheus operational metrics exposition endpoint.
- **Content-Type:** `text/plain; version=0.0.4; charset=utf-8`
- **Network Boundary:** Internal cluster access only (blocked at external ingress).
- **Exported Telemetry:**
  - `http_requests_total`: Counter by `handler` (bounded route template), `method`, and `status`.
  - `http_request_duration_seconds`: Histogram across 11 latency buckets.
  - `search_engine_cache_hits_total`: Authoritative query cache hits counter.
  - `search_engine_cache_misses_total`: Authoritative query cache misses counter.
  - `search_engine_indexed_documents`: Instant gauge of total indexed documents.
  - `search_engine_unique_terms`: Instant gauge of unique indexed vocabulary terms.
  - `search_engine_index_generation`: Instant gauge of transactional index generation.
- **Privacy Guarantees:** Zero search query text, user identifiers, or IP addresses are exported.

### 5. Admin Dashboard Endpoints (Protected via `X-Admin-Token`)

All endpoints under `/api/v1/admin/*` require the `X-Admin-Token` header (or `Authorization: Bearer <token>`).

#### GET `/api/v1/admin/health`
- **Description:** Readiness probe for the admin subsystem.
- **Response (`200 OK` - `AdminHealthResponse`):**
```json
{
  "status": "ok",
  "admin_ready": true,
  "crawler_ready": true,
  "index_ready": true,
  "timestamp": "2026-09-15T12:00:00Z"
}
```

#### POST `/api/v1/admin/crawler/start`
- **Description:** Initiate background crawl job.
- **Request Body (`CrawlRequest`):**
```json
{
  "seed_urls": ["https://example.com"],
  "max_documents": 500,
  "max_depth": 3,
  "priority": "normal"
}
```
- **Response (`200 OK` - `CrawlResponse`):**
```json
{
  "crawl_id": "crawl-1726400000-a1b2c3",
  "status": "running",
  "start_time": "2026-09-15T12:00:00Z",
  "documents_crawled": 0,
  "documents_indexed": 0,
  "errors": 0,
  "urls_queued": 1,
  "current_url": null,
  "progress_percent": 0
}
```

#### POST `/api/v1/admin/crawler/pause` / `resume` / `stop`
- **Description:** Manage active crawl job lifecycle.
- **Response (`200 OK` - `CrawlResponse`).**
- **Conflict:** Returns `409 Conflict` if crawler is not in a valid state for the transition.

#### GET `/api/v1/admin/crawler/status`
- **Description:** Poll live crawler progress and telemetry metrics.
- **Response (`200 OK` - `CrawlResponse`).**

#### GET `/api/v1/admin/metrics/index`
- **Description:** Inverted index statistics and SQLite database file size.
- **Response (`200 OK` - `IndexMetrics`):**
```json
{
  "total_documents": 1250,
  "total_terms": 18450,
  "total_postings": 154200,
  "avg_postings_per_term": 8.35,
  "index_size_mb": 4.5,
  "last_updated": "2026-09-15 12:00:00",
  "health_status": "healthy"
}
```

#### GET `/api/v1/admin/metrics/system`
- **Description:** Measured host machine utilization sampled via non-blocking `psutil`.
- **Response (`200 OK` - `SystemMetrics`):**
```json
{
  "cpu_percent": 14.2,
  "memory_percent": 48.5,
  "disk_percent": 62.1,
  "memory_used_mb": 3950.0,
  "memory_total_mb": 8192.0,
  "disk_used_gb": 124.5,
  "disk_total_gb": 256.0
}
```

#### POST `/api/v1/admin/index/clear`
- **Description:** Danger zone: permanently delete all documents and postings from SQLite.
- **Response (`200 OK`):** `{"message": "Inverted index cleared successfully."}`

#### GET `/api/v1/admin/logs`
- **Description:** Retrieve bounded tail of application log with automated credential redaction.
- **Parameters:** `lines` (int, default: 100, max: 500), `level` (optional filter).
- **Response (`200 OK` - `List[LogEntry]`):**
```json
[
  {
    "timestamp": "2026-09-15 12:00:00,000",
    "level": "INFO",
    "module": "src.main",
    "message": "Application started"
  }
]
```

#### GET `/api/v1/admin/config` & POST `/api/v1/admin/config`
- **Description:** Inspect or update in-memory allowlisted configuration parameters (`log_level`, `rate_limit_per_minute`, `crawler_max_depth`, `crawler_politeness_delay`).
- **Response (`200 OK` - `RuntimeConfigResponse`):**
```json
{
  "settings": {
    "log_level": "INFO",
    "rate_limit_per_minute": 100,
    "crawler_max_depth": 2,
    "crawler_politeness_delay": 1.0
  },
  "notice": "Runtime-only settings. Changes reset when the server restarts."
}
```

---

## Error Handling & Status Codes

All errors return the standardized `ErrorResponse` schema:

```json
{
  "error": "Error description message",
  "code": 404,
  "timestamp": "2026-09-12T14:30:00Z",
  "request_id": "c3f81e09",
  "details": null
}
```

| HTTP Code | Name | Description / Example Cause |
|---|---|---|
| `400` | Bad Request | Offset exceeds `server.max_offset` or unallowlisted config key supplied. |
| `401` | Unauthorized | Missing admin token on protected `/api/v1/admin/*` endpoints. |
| `403` | Forbidden | Invalid admin token. |
| `404` | Not Found | Route does not exist (`Endpoint not found`). |
| `409` | Conflict | Invalid crawler state transition (e.g. starting when running, pausing when idle). |
| `422` | Unprocessable Entity | Pydantic validation failure (e.g. query empty, seed URL SSRF failure, lines > 500). |
| `429` | Too Many Requests | Rate limit exceeded. Includes `Retry-After` header. |
| `500` | Internal Server Error | Unhandled server exception. Details logged internally; sanitized message returned to client. |
| `503` | Service Unavailable | Database or search engine uninitialized or temporarily down. |
