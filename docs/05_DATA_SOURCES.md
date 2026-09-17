# Data Sources & Seed URLs

## Seed URL Configuration (Phase 2)

### Development Seeds
```yaml
seed_urls:
  - https://example.com/
  - https://example.org/
  - https://httpbin.org/html
```

### URL Eligibility Criteria
- ✅ Publicly routable, valid HTTP/HTTPS schemes only.
- ✅ robots.txt permits crawling under crawler user-agent or wildcard `*`.
- ✅ Safe destination: passes DNS SSRF validation (no loopback, private, or link-local IPs).
- ✅ Clean canonical URL structure without fragment identifiers.

## Crawl Policy
```yaml
crawl:
  crawl_delay: 1.0          # seconds politeness delay per domain
  max_depth: 2              # crawl recursion depth (seed + links + sub-links)
  max_documents: 10000      # crawl capacity ceiling
  request_timeout: 10.0     # seconds before timing out
  max_document_size: 10485760 # 10MB maximum wire size
  max_decompressed_size: 52428800 # 50MB decompression bomb limit
  respect_robots_txt: true
```

---

## Content Processing & NLP Policy (Phase 3)

### Field Extraction & Limits
```yaml
parser:
  backend: "lxml"
  strip_tags:
    - script
    - style
    - noscript
    - nav
    - footer
    - template
    - header
    - aside
  max_title_length: 200        # characters
  max_description_length: 500  # characters
  max_body_length: 1048576     # characters (1,048,576 strictly Unicode)
  token_min_length: 2
  token_max_length: 50
  stemmer: "porter"
  same_domain_links_only: false
```

### Stop-Words Dataset
- Bundles 179 standard English stop-words (`src/parser/text.py`) including common determiners, prepositions, pronouns, and auxiliary verbs.
- Fully self-contained: no external API or remote corpus downloads required during crawl or indexing runs.
