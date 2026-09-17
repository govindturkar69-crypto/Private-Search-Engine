# Production Security Audit & Hardening Guide

> **Status:** Active / Production Verified (Phase 10)  
> **Classification:** Technical Security Architecture & Audit Report  
> **Last Updated:** 2026-09-15  
> **Audit Status:** Automated & Manual Verification Clean  

---

## 1. Executive Summary

This document establishes the authoritative production security posture, threat model, control assessment, and operating guidelines for the Private Search Engine. The search engine is architected as an air-gapped or self-hosted, privacy-first information retrieval platform comprising an asynchronous Python 3.11 / FastAPI backend and a React 18 / Vite 5 TypeScript single-page application.

During Phase 10 (Production Security Audit & Hardening), all threat vectors were audited against real attack surfaces without introducing superficial or disruptive filter layers:
- **Search Queries as Pure Data:** Search queries are treated as search text, never as filesystem paths. Traversal strings (`../`, `%2f`, `etc/passwd`) are indexed/matched as data without touching filesystem APIs.
- **Filesystem Boundaries:** Real filesystem access is strictly bounded to pre-configured paths (`data/app.log`, SQLite index path). Log streaming rejects all path traversal attempts.
- **Token-Protected Admin Authentication:** Constant-time token verification (`secrets.compare_digest`), deterministic environment precedence, and high-entropy production failsafe validation (>= 32 characters, >= 4 unique characters, runtime abort on weak tokens).
- **Comprehensive OWASP Top 10 (2021) Verification:** Audited and verified across all ten categories with automated regression suites.

---

## 2. Threat Model & Architecture Boundaries

```
[ External Untrusted Client ]
             │
             ▼
┌────────────────────────────────────────────────────────┐
│ 1. Network Boundary (FastAPI Gateway)                  │
│    - Right-to-left trusted proxy IP resolution         │
│    - Per-IP sliding-window rate limiting (Mock-clock) │
│    - Security headers (CSP, HSTS, X-Frame, Nosniff)    │
│    - 1MB body limit & unsupported Content-Type reject  │
└────────────────────────────┬───────────────────────────┘
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
┌───────────────────────────────┐ ┌────────────────────────────────┐
│ 2. Public Search Service API  │ │ 3. Admin Subsystem             │
│    - Read-only queries        │ │    - Constant-time token auth  │
│    - Input: Pure Text Data    │ │    - Bounded log viewer        │
│    - Zero filesystem access   │ │    - Parameterized crawler job │
│    - Parameterized SQLite     │ │    - SessionStorage in browser │
└───────────────────────────────┘ └────────────────┬───────────────┘
                                                   │
                                                   ▼
                                  ┌────────────────────────────────┐
                                  │ 4. Crawler & Fetcher Boundary  │
                                  │    - Two-tier SSRF validation  │
                                  │    - RFC 1918 / Loopback block │
                                  │    - Redirect revalidation     │
                                  │    - Robot exclusion standard  │
                                  └────────────────────────────────┘
```

### Trust Zones & Boundaries:
1. **Public Internet / Client Tier:** Zero trust. All query parameters and JSON payloads validated via strict Pydantic v2 contracts.
2. **Application Core (FastAPI / Inverted Index):** Read-only BM25 ranking. Search queries undergo tokenization and SQLite parameterized queries. No shell execution, no dynamic SQL string formatting.
3. **Admin Service Subsystem:** Protected by `X-Admin-Token` or `Authorization: Bearer`. Evaluated using `secrets.compare_digest()` to eliminate timing attacks.
4. **Outbound Crawler Subsystem:** Strictly partitioned. Enforces scheme allowlisting, comprehensive DNS resolution, IP address range filtering, and redirect-hop re-evaluation to block SSRF.

---

## 3. OWASP Top 10 (2021) Control Assessment Matrix

| OWASP Category | Attack Surface | Existing Controls | Automated Verification | Manual Evidence | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A01:2021 — Broken Access Control** | `/api/v1/admin/*` administrative endpoints | Enforces `verify_admin_token` dependency on all admin routes. Missing token -> 401; invalid token -> 403. Constant-time `secrets.compare_digest`. Frontend stores token in `sessionStorage` only. | `test_missing_token_returns_401`, `test_invalid_token_returns_403`, `test_admin_auth_status_codes` | Verified 401 without header, 403 on invalid secret, 200 on authorized secret. | **Mitigated** |
| **A02:2021 — Cryptographic Failures** | Token verification, session handling, content deduplication hashing | Python `secrets.compare_digest` prevents side-channel timing analysis. Production startup enforces >= 32 char token entropy. Non-cryptographic deduplication hashes flagged with `usedforsecurity=False`. Sensitive secrets redacted in logs. | `test_constant_time_comparison_is_invoked`, `test_production_failsafe_on_missing_or_weak_admin_token` | AST scanner verifies no insecure crypto; MD5 restricted strictly to document fingerprinting with Bandit B324 resolved. | **Mitigated** |
| **A03:2021 — Injection** | Search queries, seed URLs, configuration updates, SQLite database | SQLite queries use parameterized SQL (`?` placeholders). Search queries are treated as search text, not executable SQL or filesystem paths. Pydantic schemas enforce length and type bounds. Ast audit verifies zero string-formatted SQL. | `test_sql_injection_payloads`, `test_sql_injection_payloads_do_not_corrupt_database`, `test_search_service_has_no_path_construction` | Payloads containing `' OR 1=1 --`, `UNION SELECT`, and `DROP TABLE` executed harmlessly; database schema and doc counts remain intact. | **Mitigated** |
| **A04:2021 — Insecure Design** | Crawler SSRF, excessive pagination offset DOS, runaway crawl jobs | Outbound fetcher enforces DNS resolution & IP block filtering before TCP connection and on every redirect. Max offset constrained to 1,000. Crawl limits constrained to 10 seeds, depth 5, 10,000 docs. | `test_ssrf_blocked_destinations`, `test_ssrf_dns_resolution_to_private_target`, `test_ssrf_redirect_to_private_target`, `test_admin_crawler_cannot_bypass_ssrf_protection` | Verified loopback, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, link-local, and redirect targets are blocked. | **Mitigated** |
| **A05:2021 — Security Misconfiguration** | HTTP security headers, CORS origins, default production credentials | Response headers include CSP, `nosniff`, `DENY` framing, `no-referrer`, and conditional HSTS. CORS restricted to explicit allowed origins. Production failsafe halts startup if admin token is missing or default dev token. | `test_baseline_security_headers`, `test_hsts_header_policy`, `test_cors_allowed_origin`, `test_cors_disallowed_origin`, `test_environment_normalization_production_precedence` | Security headers confirmed present on all responses; unauthorized origins receive no CORS allow headers. | **Mitigated** |
| **A06:2021 — Vulnerable and Outdated Components** | Python virtual environment dependencies and NPM packages | Automated scanners (`pip-audit`, `npm audit`) integrated into CI/CD security scan scripts. Dependency vulnerabilities cataloged with formal triage analysis. | `scripts/security_scan.py` automated multi-tool audit execution | Zero critical vulnerabilities in production runtime code; known dev/indirect vulnerabilities documented and risk-accepted. | **Partially mitigated** |
| **A07:2021 — Identification and Authentication Failures** | Administrative access and brute-force token enumeration | Sliding-window per-IP rate limiting throttles brute force attempts with HTTP 429 and `Retry-After`. Startup validator checks token length and character diversity. | `test_admin_endpoint_rate_limiting_with_mock_clock`, `test_rate_limiter_threshold_and_retry_after` | Rate limiter strictly throttles rapid requests; 429 response includes `Retry-After` header. | **Mitigated** |
| **A08:2021 — Software and Data Integrity Failures** | Untrusted deserialization, dynamic code execution, package integrity | Zero usage of `pickle.loads`, `eval()`, `exec()`, or `yaml.load()` without `SafeLoader`. Subprocess calls banned from web API path. Package versions pinned in requirements. | `scripts/security_ast_audit.py` AST scanner | AST scan verifies 0 dangerous execution primitives in `src/`. PyYAML uses SafeLoader. | **Mitigated** |
| **A09:2021 — Security Logging and Monitoring Failures** | Audit logging, sensitive data leakage, log injection | `LogService` sanitizes and redacts credentials (`***REDACTED***`). Bounded tail extraction (max 500 lines). Request ID correlation (`X-Request-ID`) on every response. | `test_log_service_reads_strictly_configured_file`, `test_log_service_path_is_not_request_controllable` | Log viewer confines file reads to `data/app.log`; admin credentials never logged or leaked. | **Mitigated** |
| **A10:2021 — Server-Side Request Forgery (SSRF)** | Background crawler and admin crawl triggers | Comprehensive IP validation rejecting IPv4/IPv6 private, link-local, loopback, multicast, and CGNAT blocks. Defense-in-depth at API boundary and fetcher network layer. | `test_ssrf_blocked_destinations`, `test_crawler_blocks_loopback_and_private_destinations`, `test_admin_crawler_cannot_bypass_ssrf_protection` | Outbound requests to `127.0.0.1`, `localhost`, `169.254.169.254`, and AWS metadata endpoints blocked. | **Mitigated** |

---

## 4. Secret Management Policy & Production Failsafe Rules

### Principles:
1. **Zero Hardcoded Secrets in Production:** Under no circumstances may production credentials be hardcoded in repository code, committed configurations, or client bundles.
2. **Authoritative Configuration Hierarchy:** Production configuration is loaded exclusively through `src/config.py:load_config()`.
3. **Environment Normalization:** `normalize_environment()` evaluates environment flags (`ENVIRONMENT`, `ENV`, `APP_ENV`). If any variable specifies `production`, production mode is enforced deterministically.
4. **Startup Validation Failsafe:** During application startup (`src/main.py:lifespan`), if `environment == "production"`, the following invariants are enforced:
   - `admin_token` must exist and be non-empty.
   - `admin_token` must not equal the development default (`dev-admin-secret-token`).
   - `admin_token` must be at least 32 characters in length.
   - `admin_token` must contain at least 4 unique characters (entropy check).
   - If validation fails, `RuntimeError` is raised immediately, halting process startup before any network ports are bound. The secret value is never logged or exposed in exception messages.
5. **Client Credential Containment:** The frontend stores the token exclusively in browser `sessionStorage`. It is cleared on logout and never written to `localStorage` or URL query parameters.

---

## 5. Filesystem Boundaries & Traversal Safety

### Search Input Treated as Pure Text Data:
- In `src/api/routes.py` and `src/ranker/search.py`, search queries are treated strictly as query text.
- Traversal characters (`../`, `..\\`, `/etc/passwd`, `C:\Windows\System32`) are legitimate search terms for users searching for technical documentation, code snippets, or system administration articles.
- The search engine does not construct filesystem paths from user search input. Search terms are tokenized, processed against an in-memory or SQLite inverted index, and returned as BM25 ranked documents.
- **Architectural Rule:** Never add path-filtering regular expressions to `/api/v1/search`. Path validation belongs exclusively at real filesystem boundaries.

### Log File Access Boundary:
- In `src/admin/log_service.py`, `LogService` reads exclusively from the explicitly configured `log_file_path` (default: `data/app.log`).
- The API endpoints do not accept client-controlled file paths.
- Line bounds are strictly clamped to a maximum of 500 lines.
- Content is parsed line-by-line with sensitive token masking.

---

## 6. Automated Security Scanners & Verification Gates

The repository provides a multi-layer security scanning toolchain run via `scripts/security_scan.py` (and cross-platform wrappers `run_security_scan.ps1` / `run_security_scan.sh`):

```powershell
.\scripts\run_security_scan.ps1
```

### Exit Code Semantics:
- `0`: Scan passed clean. No blocking security issues.
- `1`: Blocking security findings detected (HIGH/CRITICAL Bandit issues, dangerous AST calls, exposed private keys/secrets).
- `2`: Tooling execution error (scanner crash or configuration fault).

### Integrated Scanners:
1. **pip-audit:** Scans Python dependencies in `requirements.txt` against the PyPA Advisory Database.
2. **Bandit:** Static AST security linter (`bandit -r src -ll`). Scans for high-severity vulnerabilities. Configured with `usedforsecurity=False` on MD5 deduplication hashing.
3. **npm audit:** Scans frontend NPM dependencies for known vulnerabilities in `frontend/package.json`.
4. **AST Dangerous Call Analyzer (`scripts/security_ast_audit.py`):** Parses the Python AST across `src/` to verify zero instances of `eval`, `exec`, `pickle.loads`, `yaml.load` (without SafeLoader), `subprocess(shell=True)`, `os.system`, or dynamic SQL string concatenation.
5. **Secret Exposure Scanner (`scripts/security_secret_scan.py`):** Scans source trees and configurations for unmasked RSA/EC private keys, AWS tokens, GitHub/Slack tokens, and committed real passwords.
6. **Semgrep (Optional):** Runs semgrep OWASP rule packs if semgrep is installed in the local environment.

---

## 7. Supply Chain & Vulnerability Triage Matrix

The automated dependency audit (`pip-audit` and `npm audit`) identifies known CVEs in pinned third-party dependencies. In accordance with strict software engineering practice, blind dependency upgrades that introduce breaking changes are avoided. Each advisory has been formally triaged:

| Ecosystem | Dependency | Current Version | Severity | Triage & Threat Assessment | Action / Resolution |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Python** | `starlette` / `fastapi` | `0.27.0` / `0.104.1` | Moderate | Vulnerability related to multi-part form parsing DOS. The Private Search Engine does not expose multi-part file upload endpoints. Gateway body size is capped at 1MB. | Accepted risk for development baseline. Update targeted for minor version release. |
| **Python** | `lxml` | `4.9.3` | Moderate | XML external entity / parsing issues in HTML cleaner. `src/parser/` uses BeautifulSoup4 with lxml strictly for text extraction from local crawled HTML with network entities disabled. | Mitigated by parser configuration. |
| **Python** | `nltk` | `3.8.1` | Moderate | Vulnerabilities in NLTK corpus downloaders and pickling utilities. Production runtime uses only `nltk.word_tokenize` and `stopwords`. No pickle or remote corpora downloaded at runtime. | Mitigated by application usage pattern. |
| **Node.js** | `esbuild` | `0.21.5` | High | Dev-server request origin issue. Does not affect production static build artifacts (`dist/`). | Non-blocking dev dependency. |
| **Node.js** | `react-router` | `6.30.1` | Critical | SSR DOM hydration vulnerability. The frontend is a static client-rendered SPA (`react-router-dom`) with no server-side Node.js rendering. | Non-blocking for static client bundle. |

---

## 8. Incident Response & Responsible Disclosure Guidelines

### Incident Classification:
- **P0 (Critical):** Remote code execution, unauthenticated administrative access, SSRF to private cloud metadata services (`169.254.169.254`), or direct filesystem exfiltration. Response SLA: < 4 hours.
- **P1 (High):** Denial of service affecting search availability, authentication bypass, or rate limiter failure. Response SLA: < 24 hours.
- **P2 (Medium):** Information disclosure of non-sensitive metadata or moderate dependency advisories. Response SLA: < 7 days.

### Mitigation Protocol:
1. **Isolate:** Stop affected crawler or admin processes immediately using `scripts/run_e2e_tests.ps1` or administrative process controls.
2. **Rotate:** Immediately rotate `ADMIN_TOKEN` across production environment variables.
3. **Patch:** Implement targeted code or configuration fix; verify against `tests/test_security_regression.py`.
4. **Audit:** Run `scripts/run_security_scan.ps1` to ensure zero regression before redeployment.
5. **Post-Mortem:** Document root cause, detection vector, and prevention controls in `docs/16_CHANGELOG.md` and `docs/17_DECISIONS.md`.
