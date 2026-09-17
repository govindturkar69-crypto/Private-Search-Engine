# Data Model Specification

## Overview
This document specifies the document models, in-memory representations, and data structures utilized by the Private Search Engine pipeline.

---

## 1. Document Representation (`ParsedDocument`)

Defined in `src/parser/integration.py`, `ParsedDocument` represents the fully parsed, sanitized, and tokenized content of a crawled web resource.

### Field Definitions

| Field Name | Type | Description | Constraints / Normalization |
| :--- | :--- | :--- | :--- |
| `url` | `str` | Fetch or canonical URL of the document | Validated HTTP/HTTPS absolute URI |
| `title` | `str` | Extracted page title | Fallback order: `<title>` → `og:title` → `<h1>`. Max 200 chars. |
| `description` | `str` | Page summary / snippet description | Fallback order: `og:description` → `meta[name="description"]`. Max 500 chars. |
| `body` | `str` | Extracted main textual content | Tag priority: `<article>` → `<main>` → `<body>`. Max 1,048,576 chars. |
| `author` | `Optional[str]` | Author name metadata | Extracted from `meta[name="author"]` or JSON-LD if available |
| `language` | `Optional[str]` | HTML language tag | Extracted from `<html lang="...">` or `meta[http-equiv="content-language"]` |
| `published_at` | `Optional[str]` | Publication timestamp | Fallback order: `itemprop="datePublished"` → `og:published_time` → `<time datetime>` → `meta[name="pubdate"]` |
| `charset` | `str` | Character encoding | Default `"utf-8"` |
| `canonical_url`| `Optional[str]` | Canonical link relation | Extracted from `<link rel="canonical">` |
| `tokens` | `List[str]` | Cleaned & stemmed tokens in document order | Retains term frequencies for BM25 term weighting |
| `terms` | `List[str]` | Unique set of terms (vocabulary) | Deduplicated, sorted term list |
| `links` | `List[str]` | Extracted outbound hyperlinks | Canonical absolute URLs, fragments stripped, non-HTTP filtered |
| `content_hash` | `str` | Content deduplication fingerprint | 64-character hexadecimal SHA-256 string |

### Subscript Access Interface
To provide maximum compatibility with dictionary-based indexing pipelines, `ParsedDocument` implements both `__getitem__` and `.get()`:
```python
doc = pipeline.process_document(html, url)
title = doc["title"]  # or doc.get("title", "")
tokens = doc["tokens"]  # or doc.get("tokens", [])
all_terms = doc["all_terms"]  # alias for doc.terms
```

---

## 2. Inverted Index Schema (SQLite v4.0 - Implemented in Phase 4)

### Documents Table (`documents`)
Stores document content, metadata, and token count length.
```sql
CREATE TABLE IF NOT EXISTS documents (
    doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    body TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    language TEXT DEFAULT 'en',
    author TEXT,
    publish_date TEXT,
    document_length INTEGER NOT NULL DEFAULT 0,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'indexed' CHECK(status IN ('indexed', 'processing', 'failed'))
);
```

### Terms Table (`terms`)
Stores unique vocabulary terms along with document frequency, collection frequency, and Robertson BM25 IDF.
```sql
CREATE TABLE IF NOT EXISTS terms (
    term_id INTEGER PRIMARY KEY AUTOINCREMENT,
    term TEXT UNIQUE NOT NULL,
    document_frequency INTEGER DEFAULT 0,
    collection_frequency INTEGER DEFAULT 0,
    idf REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Postings Table (`postings`)
Inverted index linking terms to documents with separate raw and field-specific term frequencies and serialized token positions.
```sql
CREATE TABLE IF NOT EXISTS postings (
    posting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    term_id INTEGER NOT NULL,
    doc_id INTEGER NOT NULL,
    term_frequency INTEGER DEFAULT 1,
    title_frequency INTEGER DEFAULT 0,
    body_frequency INTEGER DEFAULT 0,
    positions TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (term_id) REFERENCES terms(term_id) ON DELETE CASCADE,
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE,
    UNIQUE(term_id, doc_id)
);
```

### Metadata Table (`metadata`)
Stores system configuration, running document lengths, and schema version.
```sql
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Performance Indices
```sql
CREATE INDEX IF NOT EXISTS idx_documents_url ON documents(url);
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_documents_language ON documents(language);
CREATE INDEX IF NOT EXISTS idx_terms_term ON terms(term);
CREATE INDEX IF NOT EXISTS idx_postings_term_id ON postings(term_id);
CREATE INDEX IF NOT EXISTS idx_postings_doc_id ON postings(doc_id);
```

### BM25 Formulation & Field Boosting
```text
score(D, Q) = Σ IDF(t) * [ effective_tf * (k1 + 1.0) ] / [ effective_tf + k1 * (1.0 - b + b * (doc_len / avg_doc_len)) ]

Where:
- k1 = 1.5 (term frequency saturation parameter)
- b = 0.75 (document length normalization factor)
- doc_len = processed token count of document D
- avg_doc_len = average processed token count across all documents (maintained in metadata)
- effective_tf = title_frequency * title_boost + body_frequency * body_boost (defaults: title_boost=2.0, body_boost=1.0)
- IDF(t) = log(1.0 + (N - df + 0.5) / (df + 0.5)) (Robertson-Spärck Jones BM25 formula)
```

---

## 3. Crawler Data Model (Phase 2)

### URLFrontier Queue Tuple
- `(priority: int, timestamp: float, url: str)` stored in in-memory priority min-heap.
- `crawled_urls`: `set[str]` tracking sha256 hashes of canonical URLs.
- `domain_last_crawled`: `dict[str, float]` tracking timestamp of last fetch per domain.

