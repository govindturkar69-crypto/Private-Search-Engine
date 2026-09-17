"""Unit and integration tests for HTMLParser, TextProcessor, and pipelines."""

from src.parser import (
    HTMLParser,
    TextProcessor,
    LinkExtractor,
    ContentDeduplicator,
    ParserPipeline,
    ParsedDocument,
)


# =====================================================================
# 1. HTMLParser Tests
# =====================================================================
class TestHTMLParser:
    def test_title_tag_extraction(self):
        html = "<html><head><title>  Primary Page Title  </title></head></html>"
        parser = HTMLParser()
        res = parser.parse(html, "https://example.com")
        assert res is not None
        assert res["title"] == "Primary Page Title"

    def test_og_title_fallback(self):
        html = (
            "<html><head><meta property='og:title' content='OpenGraph Title' />"
            "</head><body><h1>Header</h1></body></html>"
        )
        parser = HTMLParser()
        res = parser.parse(html, "https://example.com")
        assert res is not None
        assert res["title"] == "OpenGraph Title"

    def test_h1_fallback(self):
        html = (
            "<html><body><h1>First Heading Title</h1>"
            "<h1>Second Heading</h1></body></html>"
        )
        parser = HTMLParser()
        res = parser.parse(html, "https://example.com")
        assert res is not None
        assert res["title"] == "First Heading Title"

    def test_description_fallback_og_then_meta(self):
        # 1. OG Description precedence
        html_og = """
        <html><head>
            <meta property="og:description" content="OG description text" />
            <meta name="description" content="Standard description" />
        </head></html>
        """
        parser = HTMLParser()
        res_og = parser.parse(html_og)
        assert res_og is not None
        assert res_og["description"] == "OG description text"

        # 2. Meta description fallback
        html_meta = (
            "<html><head><meta name='description' "
            "content='Standard description' /></head></html>"
        )
        res_meta = parser.parse(html_meta)
        assert res_meta is not None
        assert res_meta["description"] == "Standard description"

    def test_body_extraction_hierarchy_article_main_body(self):
        # 1. <article> preferred
        html_article = (
            "<html><body><main><p>Main text</p></main>"
            "<article><p>Article text</p></article></body></html>"
        )
        parser = HTMLParser()
        res = parser.parse(html_article)
        assert res is not None
        assert "Article text" in res["body"]

        # 2. <main> when no <article>
        html_main = (
            "<html><body><main><p>Main content only</p></main>"
            "<div>Other text</div></body></html>"
        )
        res_main = parser.parse(html_main)
        assert res_main is not None
        assert "Main content only" in res_main["body"]

        # 3. <body> fallback
        html_body = "<html><body><p>Standard body paragraph</p></body></html>"
        res_body = parser.parse(html_body)
        assert res_body is not None
        assert "Standard body paragraph" in res_body["body"]

    def test_non_content_element_removal(self):
        html = """
        <html><body>
            <script>var x = 10;</script>
            <style>body { color: red; }</style>
            <noscript>Please enable javascript</noscript>
            <nav><a href="/home">Home</a></nav>
            <article>
                <p>Clean informative article content.</p>
            </article>
            <footer>Copyright 2026</footer>
            <template><p>Template content</p></template>
        </body></html>
        """
        parser = HTMLParser()
        res = parser.parse(html)
        assert res is not None
        body = res["body"]
        assert "Clean informative article content." in body
        assert "var x = 10" not in body
        assert "color: red" not in body
        assert "Please enable javascript" not in body
        assert "Home" not in body
        assert "Copyright 2026" not in body
        assert "Template content" not in body

    def test_whitespace_normalization(self):
        html = (
            "<html><body><article><p>Line   1\n\n\twith   excessive \r\n"
            "   whitespace.</p></article></body></html>"
        )
        parser = HTMLParser()
        res = parser.parse(html)
        assert res is not None
        assert res["body"] == "Line 1 with excessive whitespace."

    def test_empty_and_malformed_html(self):
        parser = HTMLParser()
        assert parser.parse("") is None
        assert parser.parse("   \n\t  ") is None

        # Malformed HTML is gracefully recovered by lxml backend
        malformed = (
            "<html><head><title>Malformed Page</title><body>"
            "<p>Paragraph without closing tags<div>Nested"
        )
        res = parser.parse(malformed)
        assert res is not None
        assert res["title"] == "Malformed Page"
        assert "Paragraph without closing tags" in res["body"]

    def test_truncation_limits(self):
        long_title = "T" * 350
        long_desc = "D" * 800
        long_body = "B" * 1_200_000

        html = f"""
        <html>
        <head>
            <title>{long_title}</title>
            <meta name="description" content="{long_desc}">
        </head>
        <body><article><p>{long_body}</p></article></body>
        </html>
        """
        parser = HTMLParser()
        res = parser.parse(html)
        assert res is not None
        assert len(res["title"]) == 200
        assert len(res["description"]) == 500
        assert len(res["body"]) == 1_048_576

    def test_metadata_extraction_and_fallbacks(self):
        html = """
        <html lang="fr">
        <head>
            <meta name="author" content="Jane Doe" />
            <meta charset="utf-8" />
            <link rel="canonical" href="https://example.com/canonical-page" />
            <meta property="article:published_time" content="2026-03-01T12:00:00Z" />
        </head>
        <body><p>Content</p></body>
        </html>
        """
        parser = HTMLParser()
        res = parser.parse(html, "https://example.com/original")
        assert res is not None
        assert res["author"] == "Jane Doe"
        assert res["language"] == "fr"
        assert res["charset"] == "utf-8"
        assert res["canonical_url"] == "https://example.com/canonical-page"
        assert res["published_at"] == "2026-03-01T12:00:00Z"

    def test_publication_date_deterministic_fallbacks(self):
        parser = HTMLParser()

        # 1. itemprop datePublished
        html_itemprop = (
            '<html><head><meta itemprop="datePublished" content="2026-01-15" />'
            "</head></html>"
        )
        res1 = parser.parse(html_itemprop)
        assert res1 is not None and res1["published_at"] == "2026-01-15"

        # 2. <time datetime="...">
        html_time = (
            '<html><body><time datetime="2026-02-20">Feb 20</time></body></html>'
        )
        res2 = parser.parse(html_time)
        assert res2 is not None and res2["published_at"] == "2026-02-20"

        # 3. meta name=pubdate
        html_meta_pub = (
            '<html><head><meta name="pubdate" content="2026-03-10" /></head></html>'
        )
        res3 = parser.parse(html_meta_pub)
        assert res3 is not None and res3["published_at"] == "2026-03-10"

    def test_link_extraction_resolution_and_filtering(self):
        html = """
        <html><body>
            <a href="/relative/path">Relative Link</a>
            <a href="https://example.com/relative/path#fragment">Frag</a>
            <a href="https://external.org/page?b=2&a=1">External Query</a>
            <a href="javascript:void(0)">JS Link</a>
            <a href="mailto:info@example.com">Mailto</a>
            <a href="tel:+123456789">Tel</a>
            <a href="data:text/html,abc">Data</a>
            <a href="ftp://files.example.com">FTP</a>
        </body></html>
        """
        parser = HTMLParser()
        res = parser.parse(html, "https://example.com/dir/index.html")
        assert res is not None
        links = res["links"]

        # Relative link resolved to absolute
        assert "https://example.com/relative/path" in links
        # Fragment stripped and deduplicated against first link
        assert links.count("https://example.com/relative/path") == 1
        # Query order preserved by default
        assert "https://external.org/page?b=2&a=1" in links
        # Non-http/https schemes rejected
        assert not any(
            link_url.startswith(("javascript:", "mailto:", "tel:", "data:", "ftp:"))
            for link_url in links
        )


# =====================================================================
# 2. TextProcessor Tests
# =====================================================================
class TestTextProcessor:
    def test_tokenization_and_url_stripping(self):
        proc = TextProcessor()
        text = (
            "Visit https://search.engine.local/docs for state-of-the-art information!"
        )
        tokens = proc.tokenize(text)
        assert "visit" in tokens
        assert "state-of-the-art" in tokens
        assert "information" in tokens
        # URL removed
        assert not any("http" in t for t in tokens)

    def test_stop_word_filtering(self):
        proc = TextProcessor()
        tokens = ["the", "quick", "brown", "and", "or", "fox", "it", "is"]
        filtered = proc.filter_stopwords(tokens)
        assert "quick" in filtered
        assert "brown" in filtered
        assert "fox" in filtered
        assert "the" not in filtered
        assert "and" not in filtered
        assert "or" not in filtered
        assert "is" not in filtered

    def test_length_and_digit_filtering(self):
        proc = TextProcessor()
        tokens = ["hi", "ai", "12345", "python", "algorithm", "99"]
        filtered = proc.filter_stopwords(tokens)
        assert "python" in filtered
        assert "algorithm" in filtered
        assert "hi" not in filtered  # < 3 chars
        assert "ai" not in filtered  # < 3 chars
        assert "12345" not in filtered  # pure digits

    def test_stemming_porter(self):
        proc = TextProcessor()
        tokens = ["running", "runs", "runner"]
        stemmed = proc.stem(tokens)
        assert stemmed[0] == "run"
        assert stemmed[1] == "run"
        assert stemmed[2] == "runner"

    def test_repeated_token_frequency_preservation(self):
        proc = TextProcessor()
        text = "Search engines index search queries and search documents."
        tokens = proc.process(text)
        # 'search' appears 3 times in original text and must be preserved 3 times
        search_count = tokens.count("search")
        assert search_count == 3

    def test_unique_get_terms_behavior(self):
        proc = TextProcessor()
        text = "Search engines index search queries and search documents."
        unique_terms = proc.get_terms(text)
        assert len(unique_terms) == len(set(unique_terms))
        assert unique_terms.count("search") == 1

    def test_unicode_and_international_text(self):
        proc = TextProcessor()
        unicode_text = "Übergröße café façade naïve piñata Übergröße"
        tokens = proc.tokenize(unicode_text)
        assert "übergröße" in tokens or "ubergröße" in tokens
        assert "café" in tokens or "cafe" in tokens

        processed = proc.process(unicode_text)
        assert len(processed) > 0


# =====================================================================
# 3. ContentDeduplicator Tests
# =====================================================================
class TestContentDeduplicator:
    def test_deterministic_hashing(self):
        dedup = ContentDeduplicator()
        h1 = dedup.compute_hash("deterministic sample text")
        h2 = dedup.compute_hash("deterministic sample text")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex string

    def test_document_hash_whitespace_and_casing_normalization(self):
        dedup = ContentDeduplicator()
        h1 = dedup.compute_document_hash(
            "  My Article Title  \n", "Body   paragraph   text.  "
        )
        h2 = dedup.compute_document_hash("my article title", "body paragraph text.")
        assert h1 == h2

    def test_field_separator_prevents_concatenation_collision(self):
        dedup = ContentDeduplicator()
        # Title "A B", Body "C" vs Title "A", Body "B C"
        h1 = dedup.compute_document_hash("A B", "C")
        h2 = dedup.compute_document_hash("A", "B C")
        assert h1 != h2

    def test_duplicate_detection_and_registration(self):
        dedup = ContentDeduplicator()
        content = "unique fresh content"
        # Not duplicate initially
        assert not dedup.is_duplicate(content, register=False)
        # Register hash
        h = dedup.compute_hash(content)
        dedup.register_hash(h)
        # Now recognized as duplicate
        assert dedup.is_duplicate(content)
        assert dedup.is_duplicate_hash(h)

    def test_stats_and_clearing(self):
        dedup = ContentDeduplicator()
        dedup.register_hash("hash1")
        dedup.register_hash("hash2")
        stats = dedup.get_stats()
        assert stats["unique_hashes"] == 2
        assert stats["algorithm"] == "sha256"

        dedup.clear()
        assert dedup.get_stats()["unique_hashes"] == 0


# =====================================================================
# 4. LinkExtractor Tests
# =====================================================================
class TestLinkExtractor:
    def test_same_domain_filtering(self):
        extractor = LinkExtractor(same_domain_only=True)
        links = [
            "https://example.com/page1",
            "https://sub.example.com/page2",
            "https://external.org/page3",
            "https://example.com/page4",
        ]
        filtered = extractor.extract_and_filter(links, "https://example.com/index")
        assert "https://example.com/page1" in filtered
        assert "https://example.com/page4" in filtered
        assert "https://external.org/page3" not in filtered

    def test_depth_limiting(self):
        extractor = LinkExtractor(max_depth=2)
        links = ["https://example.com/page1"]
        # Depth 0 and 1 allowed
        assert (
            len(
                extractor.extract_and_filter(
                    links, "https://example.com", current_depth=0
                )
            )
            == 1
        )
        assert (
            len(
                extractor.extract_and_filter(
                    links, "https://example.com", current_depth=1
                )
            )
            == 1
        )
        # Depth 2 reaches ceiling
        assert (
            len(
                extractor.extract_and_filter(
                    links, "https://example.com", current_depth=2
                )
            )
            == 0
        )

    def test_configurable_link_prioritization(self):
        extractor = LinkExtractor(
            base_score=10,
            content_bonus=5,
            same_domain_bonus=2,
            navigation_penalty=3,
            archive_penalty=2,
        )
        links = [
            "https://example.com/privacy",  # 10 - 3 + 2 = 9
            "https://example.com/article/deep-learning",  # 10 + 5 + 2 = 17
            "https://external.org/blog/python-tips",  # 10 + 5 + 0 = 15
            "https://example.com/category/tech",  # 10 - 2 + 2 = 10
        ]
        prioritized = extractor.prioritize_links(links, "https://example.com")
        urls_by_priority = [u for u, _ in prioritized]
        assert urls_by_priority[0] == "https://example.com/article/deep-learning"
        assert urls_by_priority[1] == "https://external.org/blog/python-tips"
        assert urls_by_priority[2] == "https://example.com/category/tech"
        assert urls_by_priority[3] == "https://example.com/privacy"


# =====================================================================
# 5. ParserPipeline Integration Tests
# =====================================================================
class TestParserPipeline:
    def test_full_pipeline_processing(self):
        html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <title>Search Engine Architecture</title>
            <meta name="description"
                  content="Guide covering crawler and indexing architectures." />
            <meta name="author" content="DeepMind Engineer" />
            <link rel="canonical" href="https://example.com/architecture" />
        </head>
        <body>
            <article>
                <h1>Search Engine Architecture</h1>
                <p>Technical guide explaining crawler design and inverted indexes.</p>
                <a href="/docs/crawler">Crawler Details</a>
                <a href="https://external.net/reference">Reference Link</a>
            </article>
        </body>
        </html>
        """
        pipeline = ParserPipeline(same_domain_only=False)
        doc = pipeline.process_document(html, "https://example.com/architecture")

        assert isinstance(doc, ParsedDocument)
        assert doc.title == "Search Engine Architecture"
        assert doc.author == "DeepMind Engineer"
        assert doc.canonical_url == "https://example.com/architecture"
        assert len(doc.tokens) > 0
        assert len(doc.terms) > 0
        assert len(doc.links) == 2
        assert "https://example.com/docs/crawler" in doc.links
        assert len(doc.content_hash) == 64

        # Dictionary subscript compatibility test
        assert doc["title"] == "Search Engine Architecture"
        assert doc.get("author") == "DeepMind Engineer"
        assert len(doc["all_terms"]) > 0

    def test_duplicate_document_suppression(self):
        html = (
            "<html><head><title>Identical Page</title></head>"
            "<body><p>Identical body text content.</p></body></html>"
        )
        pipeline = ParserPipeline()

        # First crawl of content succeeds
        doc1 = pipeline.process_document(html, "https://example.com/page1")
        assert doc1 is not None

        # Duplicate crawl of identical content returns None
        doc2 = pipeline.process_document(html, "https://example.com/page2")
        assert doc2 is None

    def test_failed_parse_does_not_poison_dedup_state(self):
        pipeline = ParserPipeline()
        # Empty HTML fails
        assert pipeline.process_document("", "https://example.com/empty") is None
        # Valid document afterwards must not be affected
        doc = pipeline.process_document(
            "<html><head><title>Valid</title></head>"
            "<body><p>Valid content</p></body></html>",
            "https://example.com/valid",
        )
        assert doc is not None
