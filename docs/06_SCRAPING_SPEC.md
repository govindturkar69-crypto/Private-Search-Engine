# Scraping Specification (Phase 2)

## robots.txt Compliance (RFC 9309)
1. **Fetching**: Request `/robots.txt` from origin host using standard User-Agent.
2. **Caching**: Cache parsed directive groups per domain.
3. **Agent Selection**:
   - Product token match evaluated case-insensitively.
   - If specific token matched, its group takes precedence.
   - If not found, fall back to wildcard `*` group.
   - If no matching groups exist, all paths permitted.
4. **Rule Matching (RFC 9309 Section 2.2.2)**:
   - Longest matching pattern (in octets/characters) determines outcome.
   - If equally specific Allow and Disallow rules match, **Allow wins**.
   - Empty `Disallow:` resets restrictions.
5. **Extensions**: Support `Crawl-delay` and `Request-rate` extensions.

---

## URL Validation & Canonicalization
- **Allowed Schemes**: `http`, `https` exclusively.
- **Normalization**:
  - Lowercase scheme and hostname.
  - Remove default ports (`:80` for HTTP, `:443` for HTTPS).
  - Strip URL fragment (`#...`).
  - Normalize empty paths to `/`.
  - Preserve query parameter order by default (order can be semantically significant).

---

## Fetch Safety & Limits
- **Timeout**: 10.0 seconds per request.
- **Retries**: Up to 3 attempts with exponential backoff (1s, 3s, 10s) on timeouts and connection failures.
- **Redirects**:
  - Maximum 5 hops.
  - Followed explicitly/manually.
  - Cycle detection prevents infinite redirect loops.
  - SSRF checks executed against every intermediate and final redirect target.
- **Size Bounds**:
  - Max wire download size: 10MB (`10,485,760` bytes).
  - Max decompressed size: 50MB (`52,428,800` bytes).
  - Checked progressively while streaming chunks.

---

## Security Safeguards
- **SSRF Defense**:
  - Hostnames resolved via DNS.
  - Resolved IP addresses validated against non-public blocks:
    - Loopback: `127.0.0.0/8`, `::1`
    - CGNAT & Unspecified: `100.64.0.0/10`, `0.0.0.0/8`, `::`
    - Multicast & Reserved ranges.

---

## Content Parsing & Sanitization (Phase 3)

### DOM Preprocessing & Sanitization
1. **Parser Selection**: BeautifulSoup4 with `lxml` parser backend.
2. **Tag Decomposition**: Recursively decomposes non-content and layout noise before extracting text:
   - `<script>`, `<style>`, `<noscript>`, `<nav>`, `<footer>`, `<template>`, `<header>`, `<aside>`.

### Extraction Fallback Hierarchies
1. **Title Extraction**:
   - Primary: `<title>` tag content.
   - Secondary: `<meta property="og:title">` attribute.
   - Tertiary: First `<h1>` heading text.
   - Fallback: Empty string `""`.
2. **Description Extraction**:
   - Primary: `<meta property="og:description">`.
   - Secondary: `<meta name="description">`.
   - Fallback: Empty string `""`.
3. **Body Extraction**:
   - Priority 1: First `<article>` tag.
   - Priority 2: First `<main>` tag.
   - Priority 3: `<body>` element.
   - Separates nested blocks with single spaces; collapses multiple whitespace/newlines into single spaces.
4. **Metadata Extraction**:
   - `author`: `<meta name="author">` or schema author.
   - `language`: `<html lang="...">` or `<meta http-equiv="content-language">`.
   - `charset`: `<meta charset="...">` or content-type declaration (defaults to `"utf-8"`).
   - `canonical_url`: `<link rel="canonical" href="...">`.
   - `published_at`:
     1. `<meta itemprop="datePublished">`
     2. `<meta property="article:published_time">`
     3. `<time datetime="...">`
     4. `<meta name="pubdate">` or `<meta name="date">`

### Truncation Limits & Boundaries
- All truncations operate on validated, normalized Python Unicode `str` characters:
  - Title: capped at 200 characters (`title[:200]`).
  - Description: capped at 500 characters (`description[:500]`).
  - Body: capped at exactly 1,048,576 characters (`body[:1_048_576]`).
- Whitespace normalization occurs before truncation to guarantee limits are strictly applied to substantive content.

### Link Extraction & Filtering
- Converts all `href` attributes to absolute URLs via `urllib.parse.urljoin(base_url, href)`.
- Strips fragment identifiers (`#...`) so URLs referencing same documents merge.
- Skips empty links and non-HTTP/HTTPS schemes (`javascript:`, `mailto:`, `tel:`, `data:`, `ftp:`).
- Supports domain boundary filtering (`same_domain_only=True/False`).
