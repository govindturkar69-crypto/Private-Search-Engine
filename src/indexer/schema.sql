-- Private Search Engine Inverted Index Schema (Version 4.0)

-- Documents table: Stores indexed documents and metadata
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

-- Terms table: Stores unique terms and their collection statistics
CREATE TABLE IF NOT EXISTS terms (
    term_id INTEGER PRIMARY KEY AUTOINCREMENT,
    term TEXT UNIQUE NOT NULL,
    document_frequency INTEGER DEFAULT 0,
    collection_frequency INTEGER DEFAULT 0,
    idf REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Postings table: Inverted index (term -> documents with raw & field frequencies)
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

-- Indices for query performance
CREATE INDEX IF NOT EXISTS idx_documents_url ON documents(url);
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_documents_language ON documents(language);
CREATE INDEX IF NOT EXISTS idx_terms_term ON terms(term);
CREATE INDEX IF NOT EXISTS idx_postings_term_id ON postings(term_id);
CREATE INDEX IF NOT EXISTS idx_postings_doc_id ON postings(doc_id);

-- Metadata table: Track index-wide statistics and schema version
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Initialize metadata
INSERT OR IGNORE INTO metadata (key, value) VALUES ('total_documents', '0');
INSERT OR IGNORE INTO metadata (key, value) VALUES ('total_document_length', '0');
INSERT OR IGNORE INTO metadata (key, value) VALUES ('avg_document_length', '0.0');
INSERT OR IGNORE INTO metadata (key, value) VALUES ('total_terms', '0');
INSERT OR IGNORE INTO metadata (key, value) VALUES ('last_indexed', '');
INSERT OR IGNORE INTO metadata (key, value) VALUES ('schema_version', '4.0');
INSERT OR IGNORE INTO metadata (key, value) VALUES ('index_version', '1.0');
INSERT OR IGNORE INTO metadata (key, value) VALUES ('index_generation', '1');
