"""Data models for Private Search Engine."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Document:
    url: str
    title: Optional[str] = None
    content: str = ""
    content_hash: Optional[str] = None
    id: Optional[int] = None


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str
    score: float
    doc_id: int
