# Master Rules & Status

## Project: Private Search Engine
**Current Phase:** PHASE 12 - PRODUCTION DEPLOYMENT & OPERATIONAL READINESS  
**Status:** Implementation Complete — Environment-Specific Deployment Verification Required  
**Next Phase:** Project Complete (Phases 1–12 Successfully Delivered)  

---

## Global Guidelines

### Code Quality
- ✅ No hardcoded secrets
- ✅ Production quality always
- ✅ All tests passing (306 Backend [unit + integration + security + metrics + backup] + 20 Vitest Frontend + E2E Playwright)
- ✅ Code formatted (black, flake8 max-line-length=88, mypy strict, tsc strict)

### Documentation
- ✅ 18 documents synchronized
- ✅ Each phase updates specified docs
- ✅ No contradictions
- ✅ Code examples match implementation

### Security & Performance
- ✅ SSRF protection (DNS resolution, private/link-local/loopback IP validation)
- ✅ Input validation & URL canonicalization
- ✅ robots.txt enforcement (RFC 9309 longest-match semantics)
- ✅ Size and decompression bomb limits
- ✅ Content parsing sanitization & script/style stripping
- ✅ Truncation limits preventing memory exhaustion
- ✅ Atomic transactions & SQL injection defense (parameterized queries)
- ✅ Foreign key constraint enforcement (`PRAGMA foreign_keys = ON`)
- ✅ Query syntax sanitization (max 500 chars, max 100 terms, max 50 chars/term)
- ✅ Sliding-window rate limiting (per-IP, 429 Retry-After, trusted proxy policy)
- ✅ Security headers on all responses (nosniff, DENY, CSP, XSS-Protection, HSTS config)
- ✅ Strict Pydantic v2 input validation with whitespace stripping
- ✅ Safe request ID tracing (sanitized regex `^[a-zA-Z0-9\-_]{1,64}$`)
- ✅ Zero stack trace or internal path leaks in HTTP error responses
- ✅ Safe snippet highlighting without `dangerouslySetInnerHTML` (React DOM `<mark>`)
- ✅ In-flight request cancellation via `AbortController` preventing stale overwrites
- ✅ No sensitive search telemetry or raw query logging (zero query text stored)
- ✅ Constant-time token authentication (`secrets.compare_digest`) on admin endpoints
- ✅ Admin token stored exclusively in `sessionStorage`; never in `localStorage` or URLs
- ✅ Defense-in-depth SSRF pre-validation at admin API boundary
- ✅ Bounded log tail inspection (≤500 lines) with automated secret & token redaction
- ✅ Allowlisted in-memory configuration updates with zero disk pollution
- ✅ Security regression test suite: SQL injection, XSS, payload size, headers, SSRF, DOS
- ✅ In-memory thread-safe LRU search cache (`LRUCache`) with `X-Cache: HIT/MISS` headers
- ✅ Persistent index generation counter in SQLite `metadata` surviving restarts
- ✅ Immediate logical invalidation of cached queries on index write transactions
- ✅ Parameterized batch document prefetch eliminating N+1 SQL queries on hot search path
- ✅ Bounded query latency telemetry (`deque(maxlen=1000)`) with p50/p95/p99 calculation
- ✅ Dedicated non-request-path database maintenance CLI (`scripts/optimize_database.py`)
- ✅ Single-replica deployment constraint strictly enforced for embedded SQLite (ADR D039)
- ✅ Official `prometheus-client` exposition at `GET /metrics` with isolated `CollectorRegistry` (ADR D040)
- ✅ Centralized HTTP middleware metrics with normalized route template labels preventing cardinality explosion
- ✅ Transactionally consistent online SQLite backups via `sqlite3.backup()` API with SHA-256 and sandbox restore verification (ADR D041)
- ✅ Hardened multi-stage Docker container with unprivileged `appuser` (UID 1000) runtime and Python stdlib healthcheck

---

## Tech Stack
- **Backend Language:** Python 3.11+
- **Backend Framework:** FastAPI (lifespan lifecycle, `app.state` dependency injection)
- **Validation:** Pydantic v2 schemas
- **HTTP Client:** HTTPX (async, streaming)
- **HTML Parsing:** BeautifulSoup4 + lxml
- **NLP / Tokenization:** NLTK (Porter stemmer, bundled stop-words, offline fallback)
- **Database & Inverted Index:** SQLite 3 (WAL mode, foreign keys, persistent generation, schema v4.0)
- **Ranking Engine:** Okapi BM25 (Robertson-Spärck Jones IDF, field boosting, batch prefetch)
- **Query Parser:** Custom structured parser (+required, -excluded, "phrases", field:val)
- **Snippet Generator:** Contextual windowing, word boundary snapping, markdown bolding
- **Caching Layer:** Thread-safe in-memory LRUCache with generation keying
- **Telemetry & Monitoring:** psutil + Bounded PerformanceMetricsCollector + Prometheus (`prometheus-client`)
- **Containerization:** Multi-stage Docker (Node 20 builder, Python 3.11 wheel builder, unprivileged runtime)
- **Orchestration:** Kubernetes (1-replica Recreate Deployment, PVC, ConfigMap, Secret, Ingress, NetworkPolicy)
- **Frontend Framework:** React 18, Vite 5, TypeScript 5 (strict mode)
- **Frontend Routing:** React Router 6 (URL search parameters `/?q=...&page=...`, `/admin`)
- **Frontend Testing:** Vitest 1.4, JSDOM, React Testing Library
- **HTTP Client (Frontend):** Axios 1.6 with Vite dev proxy and AbortSignal cancellation
- **E2E Testing:** Playwright (Chromium headless)
- **Load Testing:** Locust 2.46.5

---

## Completed Phases
- ✅ Phase 1: Setup & Discovery
- ✅ Phase 2: Core Crawler
- ✅ Phase 3: Content Processing & Parser
- ✅ Phase 4: Indexing Engine
- ✅ Phase 5: Ranking & Scoring Engine
- ✅ Phase 6: Search API & FastAPI Server
- ✅ Phase 7: Frontend Search UI
- ✅ Phase 8: Admin Dashboard
- ✅ Phase 9: Comprehensive Testing & Hardening
- ✅ Phase 10: Production Security Audit & Hardening
- ✅ Phase 11: Measurement-Driven Performance Optimization
- ✅ Phase 12: Production Deployment & Operational Readiness

---

## Document Status (Phase 12 Updates)
- ✅ 00_MASTER_RULES - Updated (Phase 12 complete)
- ✅ 01_PRD - Current
- ✅ 02_TRD - Updated (Phase 12 operational & deployment specifications)
- ✅ 03_ARCHITECTURE - Updated (Phase 12 containerization, k8s, Prometheus, backup architecture)
- ✅ 04_DATA_MODEL - Current
- ✅ 05_DATA_SOURCES - Current
- ✅ 06_SCRAPING_SPEC - Current
- ✅ 07_API_CONTRACT - Updated (GET /metrics Prometheus endpoint)
- ✅ 08_UI_SPEC - Current
- ✅ 09_ERROR_HANDLING - Current
- ✅ 10_SECURITY - Current
- ✅ 11_ADMIN_SPEC - Current
- ✅ 12_GITHUB_ACTIONS - Finalized (Phase 12 3-job CI/CD pipeline)
- ✅ 13_TESTING - Updated (306 backend passed, 20 Vitest passed, E2E passed)
- ✅ 14_PRODUCTION_CHECKLIST - Finalized (Phase 12 production readiness checklist)
- ✅ 15_MICROTASKS - Updated (Phase 12 tasks complete)
- ✅ 16_CHANGELOG - Updated (Phase 12 deliverables)
- ✅ 17_DECISIONS - Updated (ADRs D039–D041)

