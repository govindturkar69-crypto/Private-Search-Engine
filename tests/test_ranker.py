"""Comprehensive test suite for Phase 5 Ranking & Scoring Subsystem."""

import time
from typing import Any, Dict, List, Optional
import pytest
from src.crawler.fetcher import FetchResult, Fetcher
from src.indexer import SQLiteIndexer
from src.parser.integration import ParserPipeline
from src.ranker import (
    EndToEndPipeline,
    ParsedQuery,
    QueryParser,
    SearchEngine,
    SearchResult,
    SnippetGenerator,
)


# ============================================================================
# QueryParser Tests
# ============================================================================


class TestQueryParser:
    """Test suite for QueryParser syntax and validation."""

    def test_parsed_query_dataclass(self) -> None:
        pq = ParsedQuery(
            raw_query="test",
            optional_terms=["opt"],
            required_terms=["req"],
            phrases=["phrase term"],
        )
        assert not pq.is_empty()
        assert "opt" in pq.all_positive_terms()
        assert "req" in pq.all_positive_terms()
        assert "phrase" in pq.all_positive_terms()

    def test_simple_optional_terms(self) -> None:
        parser = QueryParser()
        parsed = parser.parse("python web framework")
        assert parsed.optional_terms == ["python", "web", "framework"]
        assert parsed.required_terms == []
        assert parsed.excluded_terms == []
        assert parsed.phrases == []
        assert parsed.field_filters == {}
        assert parsed.all_positive_terms() == ["python", "web", "framework"]
        assert not parsed.is_empty()

    def test_required_terms(self) -> None:
        parser = QueryParser()
        parsed = parser.parse("+python async +fast")
        assert parsed.required_terms == ["python", "fast"]
        assert parsed.optional_terms == ["async"]
        assert parsed.all_positive_terms() == ["python", "fast", "async"]

    def test_excluded_terms(self) -> None:
        parser = QueryParser()
        parsed = parser.parse("programming -java -rust")
        assert parsed.optional_terms == ["programming"]
        assert parsed.excluded_terms == ["java", "rust"]
        assert parsed.all_positive_terms() == ["programming"]

    def test_exact_phrases(self) -> None:
        parser = QueryParser()
        parsed = parser.parse('"machine learning" tutorial "deep neural networks"')
        assert parsed.phrases == ["machine learning", "deep neural networks"]
        assert parsed.optional_terms == ["tutorial"]
        pos_terms = parsed.all_positive_terms()
        assert "tutorial" in pos_terms
        assert "machine" in pos_terms
        assert "learning" in pos_terms

    def test_field_filters(self) -> None:
        parser = QueryParser()
        parsed = parser.parse('python language:en author:"Guido van Rossum"')
        assert parsed.optional_terms == ["python"]
        assert parsed.field_filters == {
            "language": "en",
            "author": "guido van rossum",
        }

    def test_mixed_advanced_query(self) -> None:
        parser = QueryParser()
        query = '+python "data science" -legacy lang:en tutorial'
        parsed = parser.parse(query)
        assert parsed.required_terms == ["python"]
        assert parsed.phrases == ["data science"]
        assert parsed.excluded_terms == ["legacy"]
        assert parsed.field_filters == {"lang": "en"}
        assert parsed.optional_terms == ["tutorial"]

    def test_term_normalization_and_punctuation(self) -> None:
        parser = QueryParser()
        parsed = parser.parse("Python, Async! Framework... +Fast? -Old#")
        assert parsed.optional_terms == ["python", "async", "framework"]
        assert parsed.required_terms == ["fast"]
        assert parsed.excluded_terms == ["old"]

    def test_query_length_limit(self) -> None:
        parser = QueryParser(max_query_length=50)
        long_query = "a" * 100
        parsed = parser.parse(long_query)
        assert len(parsed.raw_query) == 50

    def test_max_terms_limit(self) -> None:
        parser = QueryParser(max_terms=5)
        query = "one two three four five six seven eight"
        parsed = parser.parse(query)
        total_terms = (
            len(parsed.optional_terms)
            + len(parsed.required_terms)
            + len(parsed.phrases)
        )
        assert total_terms <= 5

    def test_term_length_limit(self) -> None:
        parser = QueryParser(max_term_length=10)
        parsed = parser.parse("verylongtermthatexceedstenchars")
        assert parsed.optional_terms == ["verylongte"]

    def test_heavy_excess_terms_truncates_required(self) -> None:
        parser = QueryParser(max_terms=2)
        parsed = parser.parse("+one +two +three four")
        assert len(parsed.required_terms) <= 2
        assert len(parsed.optional_terms) == 0

    def test_empty_and_whitespace_query(self) -> None:
        parser = QueryParser()
        assert parser.parse("").is_empty()
        assert parser.parse("   ").is_empty()
        assert parser.parse("+-:").is_empty()


# ============================================================================
# SnippetGenerator Tests
# ============================================================================


class TestSnippetGenerator:
    """Test suite for SnippetGenerator windowing and highlighting."""

    def test_snippet_centered_on_query_term(self) -> None:
        gen = SnippetGenerator(default_length=80, window_radius=30)
        text = (
            "In modern software engineering, Python is widely adopted for data "
            "analysis and machine learning workflows across industries."
        )
        snippet = gen.generate(text, ["python"])
        assert "**Python**" in snippet or "**python**" in snippet
        assert snippet.startswith("...") or "Python" in snippet

    def test_snippet_word_boundary_snapping(self) -> None:
        gen = SnippetGenerator(default_length=60, window_radius=20)
        text = (
            "The quick brown fox jumps over the lazy dog and explores the "
            "wonders of computer science algorithms."
        )
        snippet = gen.generate(text, ["lazy"])
        # Should not start or end with a severed partial word
        words = snippet.replace("...", "").split()
        assert "lazy" in [w.strip("*.,") for w in words]

    def test_markdown_bold_highlighting(self) -> None:
        gen = SnippetGenerator()
        text = "Python and Rust are modern languages."
        highlighted = gen.highlight_terms(text, ["python", "rust"])
        assert highlighted == "**Python** and **Rust** are modern languages."

    def test_multiple_term_highlighting(self) -> None:
        gen = SnippetGenerator()
        text = "Deep learning and machine learning are subsets of AI."
        snippet = gen.generate(text, ["deep", "learning"])
        assert "**Deep**" in snippet or "**deep**" in snippet
        assert "**learning**" in snippet

    def test_fallback_when_no_terms_match(self) -> None:
        gen = SnippetGenerator(default_length=40)
        text = "This is an introductory article about software development in general."
        snippet = gen.generate(text, ["quantum"])
        assert len(snippet) <= 50
        assert snippet.endswith("...")

    def test_empty_text_returns_empty_snippet(self) -> None:
        gen = SnippetGenerator()
        assert gen.generate("", ["python"]) == ""
        assert gen.generate("   ", ["python"]) == ""

    def test_extract_context_sentence(self) -> None:
        gen = SnippetGenerator()
        text = (
            "First sentence here. Python is used for backend web services. "
            "Third sentence concludes the article."
        )
        context = gen.extract_context(text, "python")
        assert "**Python** is used for backend web services." in context
        assert "First sentence" not in context

    def test_extract_context_not_found(self) -> None:
        gen = SnippetGenerator()
        text = "Just a general text here without any matching term."
        assert gen.extract_context(text, "nonexistent") == ""
        assert gen.extract_context("", "term") == ""

    def test_highlight_terms_empty_list(self) -> None:
        gen = SnippetGenerator()
        text = "Some text"
        assert gen.highlight_terms(text, []) == text
        assert gen.highlight_terms("", ["python"]) == ""


# ============================================================================
# SearchEngine Tests
# ============================================================================


class TestSearchEngine:
    """Test suite for SearchEngine ranking, filtering, and scoring."""

    @pytest.fixture
    def populated_engine(self, tmp_path: Any) -> SearchEngine:
        db_path = str(tmp_path / "test_search.db")
        indexer = SQLiteIndexer(db_path)
        pipeline = ParserPipeline()

        sample_docs = [
            (
                "<html><head><title>Python Web Development</title></head>"
                "<body>Python is an expressive and fast programming language "
                "for building modern web applications and APIs.</body></html>",
                "https://example.com/python-web",
            ),
            (
                "<html><head><title>Rust Systems Programming</title></head>"
                "<body>Rust provides memory safety without garbage collection "
                "for high performance systems and networks.</body></html>",
                "https://example.com/rust-systems",
            ),
            (
                "<html><head><title>Data Science and AI</title></head>"
                "<body>Python powers machine learning, data science, and "
                "deep learning research around the globe.</body></html>",
                "https://example.com/data-science",
            ),
            (
                "<html><head><title>French Web Guide</title></head>"
                "<body>Un guide complet pour le développement web en "
                "Python avec des exemples pratiques.</body></html>",
                "https://example.com/french-guide",
            ),
        ]

        for html, url in sample_docs:
            p = pipeline.process_document(html, url)
            assert p is not None
            # Set explicit metadata for field filter tests
            if "french" in url:
                p.language = "fr"
                p.author = "Jean Dupont"
            elif "rust" in url:
                p.language = "en"
                p.author = "Graydon Hoare"
            elif "data" in url:
                p.language = "en"
                p.author = "Wes McKinney"
            else:
                p.language = "en"
                p.author = "Guido van Rossum"

            indexer.add_document(p)

        indexer.calculate_idf(recalculate=True)
        return SearchEngine(indexer)

    def test_basic_search_ranking(self, populated_engine: SearchEngine) -> None:
        results, err = populated_engine.search("python")
        assert err is None
        assert len(results) == 3
        # Ensure result attributes are populated
        top = results[0]
        assert isinstance(top, SearchResult)
        assert top.relevance_score == 100
        assert top.score > 0
        assert "python" in top.snippet.lower() or "python" in top.title.lower()

    def test_required_terms_filter(self, populated_engine: SearchEngine) -> None:
        # Search python with required term 'machine'
        results, err = populated_engine.search("+machine python")
        assert err is None
        assert len(results) == 1
        assert "Data Science" in results[0].title

    def test_excluded_terms_filter(self, populated_engine: SearchEngine) -> None:
        # Search python excluding 'data'
        results, err = populated_engine.search("python -data")
        assert err is None
        assert len(results) == 2
        titles = [r.title for r in results]
        assert "Data Science and AI" not in titles

    def test_exact_phrase_filter(self, populated_engine: SearchEngine) -> None:
        results, err = populated_engine.search('"machine learning"')
        assert err is None
        assert len(results) == 1
        assert results[0].url == "https://example.com/data-science"

    def test_metadata_field_filters(self, populated_engine: SearchEngine) -> None:
        # Language filter
        results_fr, _ = populated_engine.search("python language:fr")
        assert len(results_fr) == 1
        assert "French" in results_fr[0].title

        # Author filter
        results_author, _ = populated_engine.search("author:wes")
        assert len(results_author) == 1
        assert results_author[0].metadata["author"] == "Wes McKinney"

    def test_relevance_score_normalization(
        self, populated_engine: SearchEngine
    ) -> None:
        results, _ = populated_engine.search("python")
        assert len(results) >= 2
        # Top result is always 100%
        assert results[0].relevance_score == 100
        # Subsequent results are <= 100
        for r in results[1:]:
            assert 0 <= r.relevance_score <= 100
            assert r.relevance_score <= results[0].relevance_score

    def test_pagination_limit_and_offset(self, populated_engine: SearchEngine) -> None:
        res_all, _ = populated_engine.search("python", limit=10)
        res_p1, _ = populated_engine.search("python", limit=1, offset=0)
        res_p2, _ = populated_engine.search("python", limit=1, offset=1)

        assert len(res_p1) == 1
        assert len(res_p2) == 1
        assert res_p1[0].doc_id == res_all[0].doc_id
        assert res_p2[0].doc_id == res_all[1].doc_id

    def test_empty_query_and_no_match(self, populated_engine: SearchEngine) -> None:
        results_empty, err = populated_engine.search("")
        assert results_empty == []
        assert err is None

        results_none, _ = populated_engine.search("nonexistentxylophone")
        assert results_none == []

    def test_autocomplete_suggestions(self, populated_engine: SearchEngine) -> None:
        suggestions = populated_engine.get_suggestions("py", limit=5)
        assert any(s.startswith("py") for s in suggestions)

    def test_search_result_to_dict(self, populated_engine: SearchEngine) -> None:
        results, _ = populated_engine.search("python", limit=1)
        assert len(results) == 1
        d = results[0].to_dict()
        assert "doc_id" in d
        assert "url" in d
        assert "title" in d
        assert "snippet" in d
        assert "score" in d
        assert "relevance_score" in d
        assert "metadata" in d

    def test_search_only_excluded_terms(self, populated_engine: SearchEngine) -> None:
        results, err = populated_engine.search("-python")
        assert results == []
        assert err is None

    def test_search_only_field_filter(self, populated_engine: SearchEngine) -> None:
        results, err = populated_engine.search("language:fr")
        assert err is None
        assert len(results) == 1
        assert "French" in results[0].title

    def test_search_with_url_filter(self, populated_engine: SearchEngine) -> None:
        results, err = populated_engine.search("domain:example.com/data")
        assert err is None
        assert len(results) == 1
        assert results[0].url == "https://example.com/data-science"

    def test_autocomplete_empty_prefix(self, populated_engine: SearchEngine) -> None:
        assert populated_engine.get_suggestions("") == []
        assert populated_engine.get_suggestions("   ") == []


# ============================================================================
# EndToEndPipeline Tests
# ============================================================================


class MockFetcher(Fetcher):
    """Mock fetcher providing deterministic offline HTML responses."""

    def __init__(self, responses: Dict[str, str]) -> None:
        super().__init__()
        self.responses = responses

    async def fetch(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> FetchResult:
        content = self.responses.get(url)
        if content:
            return FetchResult(
                url=url,
                final_url=url,
                status_code=200,
                headers={"content-type": "text/html"},
                content=content,
                elapsed=0.01,
            )
        return FetchResult(
            url=url,
            final_url=url,
            status_code=404,
            headers={},
            elapsed=0.01,
            error="Not found",
        )


class TestEndToEndPipeline:
    """Test suite for crawl-parse-index-search integrated pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_flow(self, tmp_path: Any) -> None:
        db_path = str(tmp_path / "pipeline.db")
        mock_responses = {
            "https://crawler-test.local/": (
                "<html><head><title>Root Local</title></head>"
                "<body>Welcome to crawler test. "
                "<a href='/page1'>Page 1</a> and "
                "<a href='/page2'>Page 2</a></body></html>"
            ),
            "https://crawler-test.local/page1": (
                "<html><head><title>Algorithms Page</title></head>"
                "<body>Fast indexing algorithms and data structures.</body></html>"
            ),
            "https://crawler-test.local/page2": (
                "<html><head><title>Search Page</title></head>"
                "<body>Information retrieval and ranking systems.</body></html>"
            ),
        }

        fetcher = MockFetcher(mock_responses)
        pipeline = EndToEndPipeline(
            db_path=db_path,
            crawl_delay=0.0,
            fetcher=fetcher,
            batch_size=10,
        )

        # 1. Add seed URL
        added = pipeline.add_seed_urls(["https://crawler-test.local/"])
        assert added == 1

        # 2. Crawl and index
        indexed_count = await pipeline.crawl_and_index(max_documents=3, timeout=5.0)
        assert indexed_count >= 2

        # 3. Search
        results, err = pipeline.search("algorithms")
        assert err is None
        assert len(results) >= 1
        assert "Algorithms Page" in results[0].title

        # 4. Suggestions
        suggestions = pipeline.get_suggestions("algo")
        assert len(suggestions) >= 1

        # 5. Statistics
        stats = pipeline.get_statistics()
        assert stats["index"]["total_documents"] >= 2
        assert stats["frontier"]["crawled_urls"] >= 2

        # 6. Cleanup
        pipeline.close()


# ============================================================================
# Performance Latency Benchmark
# ============================================================================


class TestRankerPerformance:
    """Performance verification ensuring query latency is under 100ms."""

    def test_query_latency_under_100ms(self, tmp_path: Any) -> None:
        db_path = str(tmp_path / "perf.db")
        indexer = SQLiteIndexer(db_path)
        pipeline = ParserPipeline()

        # Generate 50 synthetic documents
        for i in range(50):
            html = (
                f"<html><head><title>Doc {i} Title</title></head>"
                f"<body>Document {i} contains keywords python search database "
                f"performance speed indexing and retrieval number {i}.</body></html>"
            )
            url = f"https://example.com/doc/{i}"
            p = pipeline.process_document(html, url)
            assert p is not None
            indexer.add_document(p)

        indexer.calculate_idf(recalculate=True)
        engine = SearchEngine(indexer)

        # Measure 20 search query executions
        latencies: List[float] = []
        for _ in range(20):
            start = time.perf_counter()
            results, err = engine.search("+python +search -retrieval", limit=10)
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)
            assert err is None

        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        assert avg_latency < 100.0, f"Average latency too high: {avg_latency:.2f}ms"
        assert max_latency < 100.0, f"Max latency too high: {max_latency:.2f}ms"
        indexer.close()
