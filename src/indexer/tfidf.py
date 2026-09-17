"""BM25 ranking implementation with TF/IDF calculations and field boosting."""

import logging
import math
from typing import Any, Dict, List, Tuple, Union
from src.indexer import SQLiteIndexer

logger = logging.getLogger(__name__)


class BM25Ranker:
    """Okapi BM25 ranking algorithm utilizing SQLite inverted index statistics."""

    def __init__(
        self,
        indexer: SQLiteIndexer,
        k1: float = 1.5,
        b: float = 0.75,
        title_boost: float = 2.0,
        body_boost: float = 1.0,
    ) -> None:
        self.indexer = indexer
        self.k1 = k1
        self.b = b
        self.title_boost = title_boost
        self.body_boost = body_boost

        # Ensure IDFs are pre-calculated
        self.indexer.calculate_idf()

    def rank_documents(
        self, query_terms: Union[List[str], str], limit: int = 10
    ) -> List[Tuple[int, float]]:
        """Rank indexed documents for query terms using BM25 scoring with field boosts.

        Args:
            query_terms: Normalized query terms list or whitespace-separated string.
            limit: Maximum number of ranked results to return.

        Returns:
            List of (doc_id, score) sorted descending by relevance.
        """
        if isinstance(query_terms, str):
            terms_list = [t.strip().lower() for t in query_terms.split() if t.strip()]
        else:
            terms_list = [str(t).strip().lower() for t in query_terms if str(t).strip()]

        if not terms_list:
            return []

        stats = self.indexer.get_stats()
        total_docs = stats["total_documents"]
        if total_docs == 0:
            return []

        avg_doc_length = stats.get("avg_document_length") or 1.0
        if avg_doc_length <= 0:
            avg_doc_length = 1.0

        # Count query term frequencies for multi-term query weighting
        q_counts: Dict[str, int] = {}
        for t in terms_list:
            q_counts[t] = q_counts.get(t, 0) + 1

        # Collect detailed postings and candidate document IDs across all query terms
        term_postings: List[Tuple[str, int, float, List[Dict[str, Any]]]] = []
        all_candidate_ids: List[int] = []

        for term, qtf in q_counts.items():
            detailed_postings = self.indexer.search_detailed_postings(term)
            if not detailed_postings:
                continue

            term_idf = self._get_term_idf(term, total_docs)
            if term_idf <= 0.0:
                continue

            term_postings.append((term, qtf, term_idf, detailed_postings))
            for posting in detailed_postings:
                all_candidate_ids.append(posting["doc_id"])

        if not term_postings:
            return []

        # Batch prefetch candidate documents in a single SQL operation
        if hasattr(self.indexer, "get_documents_by_ids"):
            docs_map = self.indexer.get_documents_by_ids(all_candidate_ids)
        else:
            docs_map = {}

        doc_scores: Dict[int, float] = {}

        for term, qtf, term_idf, detailed_postings in term_postings:
            for posting in detailed_postings:
                doc_id = posting["doc_id"]
                raw_tf = posting["term_frequency"]
                title_tf = posting["title_frequency"]
                body_tf = posting["body_frequency"]

                doc = docs_map.get(doc_id)
                if not doc:
                    doc = self.indexer.get_document(doc_id)
                if not doc:
                    continue

                doc_length = doc.get("document_length")
                if doc_length is None or doc_length <= 0:
                    # Fallback to body token count
                    body_text = doc.get("body", "")
                    doc_length = max(len(body_text.split()), 1)

                # Field-weighted effective term frequency
                if title_tf > 0 or body_tf > 0:
                    effective_tf = (
                        title_tf * self.title_boost + body_tf * self.body_boost
                    )
                else:
                    effective_tf = raw_tf * self.body_boost

                score = self._bm25_score(
                    effective_tf=effective_tf,
                    idf=term_idf,
                    doc_length=doc_length,
                    avg_doc_length=avg_doc_length,
                )

                # Factor in query term frequency
                total_term_score = score * qtf
                doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + total_term_score

        ranked = sorted(doc_scores.items(), key=lambda item: item[1], reverse=True)
        return ranked[:limit]

    def _bm25_score(
        self,
        effective_tf: float,
        idf: float,
        doc_length: int,
        avg_doc_length: float,
    ) -> float:
        """Calculate single-term BM25 score with length normalization."""
        numerator = effective_tf * (self.k1 + 1.0)
        len_norm = 1.0 - self.b + self.b * (doc_length / max(avg_doc_length, 1.0))
        denominator = effective_tf + self.k1 * len_norm
        if denominator <= 0:
            return 0.0
        return idf * (numerator / denominator)

    def _get_term_idf(self, term: str, total_docs: int) -> float:
        """Retrieve pre-calculated IDF or compute on-the-fly."""
        conn = self.indexer.connection
        if conn is None:
            return 0.0

        cursor = conn.execute(
            "SELECT idf, document_frequency FROM terms WHERE term = ?", (term,)
        )
        row = cursor.fetchone()
        if not row:
            return 0.0

        stored_idf = float(row[0]) if row[0] is not None else 0.0
        if stored_idf > 0.0:
            return stored_idf

        # Compute on-demand Robertson BM25 IDF
        doc_freq = int(row[1]) if row[1] is not None else 1
        numerator = total_docs - doc_freq + 0.5
        denominator = doc_freq + 0.5
        computed_idf = math.log(1.0 + max(0.0, numerator / denominator))
        return computed_idf


# Backward-compatible alias
TFIDFRanker = BM25Ranker
