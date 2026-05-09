#!/usr/bin/python
"""ScholarX Domain Models.

Pydantic models for papers, search queries, search results, and source
configuration. All models are designed for serialization into the
Knowledge Graph via the existing ArticleNode / SourceNode patterns.
"""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class PaperSource(StrEnum):
    """Supported research paper sources."""

    ARXIV = "arxiv"
    PMC = "pmc"
    BIORXIV = "biorxiv"
    MEDRXIV = "medrxiv"
    PSYARXIV = "psyarxiv"
    OSF = "osf"
    SEMANTIC_SCHOLAR = "semantic_scholar"


# ── Source Metadata ──────────────────────────────────────────────────────────


class SourceConfig(BaseModel):
    """Configuration for a single paper source."""

    source: PaperSource
    enabled: bool = True
    api_key_env: str = ""  # Name of the env var holding the API key
    base_url: str = ""
    requests_per_second: float = 1.0  # Per-source rate limit
    max_results_per_query: int = 50


DEFAULT_SOURCE_CONFIGS: dict[PaperSource, SourceConfig] = {
    PaperSource.ARXIV: SourceConfig(
        source=PaperSource.ARXIV,
        base_url="https://export.arxiv.org/api",
        requests_per_second=0.33,  # arXiv: 1 request per 3 seconds
        max_results_per_query=100,
    ),
    PaperSource.PMC: SourceConfig(
        source=PaperSource.PMC,
        base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        requests_per_second=3.0,  # NCBI: 3/s without API key, 10/s with
        api_key_env="NCBI_API_KEY",
        max_results_per_query=100,
    ),
    PaperSource.BIORXIV: SourceConfig(
        source=PaperSource.BIORXIV,
        base_url="https://api.biorxiv.org",
        requests_per_second=1.0,
        max_results_per_query=100,
    ),
    PaperSource.MEDRXIV: SourceConfig(
        source=PaperSource.MEDRXIV,
        base_url="https://api.biorxiv.org",
        requests_per_second=1.0,
        max_results_per_query=100,
    ),
    PaperSource.PSYARXIV: SourceConfig(
        source=PaperSource.PSYARXIV,
        base_url="https://api.osf.io/v2",
        requests_per_second=1.0,
        api_key_env="OSF_TOKEN",
        max_results_per_query=50,
    ),
    PaperSource.OSF: SourceConfig(
        source=PaperSource.OSF,
        base_url="https://api.osf.io/v2",
        requests_per_second=1.0,
        api_key_env="OSF_TOKEN",
        max_results_per_query=50,
    ),
    PaperSource.SEMANTIC_SCHOLAR: SourceConfig(
        source=PaperSource.SEMANTIC_SCHOLAR,
        base_url="https://api.semanticscholar.org/graph/v1",
        requests_per_second=1.67,  # 100 requests per minute
        api_key_env="S2_API_KEY",
        max_results_per_query=100,
    ),
}


# ── Normalization Helpers ────────────────────────────────────────────────────


def normalize_title(title: str) -> str:
    """Normalize a paper title for deduplication matching.

    Strips whitespace, lowercases, removes punctuation and diacritics,
    and collapses multiple spaces.
    """
    text = unicodedata.normalize("NFKD", title)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s]", "", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def normalize_author(name: str) -> str:
    """Normalize an author name for deduplication matching."""
    text = unicodedata.normalize("NFKD", name)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s]", "", text.lower())
    return re.sub(r"\s+", " ", text).strip()


# ── Paper Model ──────────────────────────────────────────────────────────────


class Paper(BaseModel):
    """A research paper from any supported source.

    Designed to map directly to the KG's ArticleNode + SourceNode:
    - title → ArticleNode.name
    - abstract → ArticleNode.summary / ArticleNode.content
    - authors → PersonNode instances linked via AUTHORED edge
    - doi/url → SourceNode fields
    """

    id: str = Field(description="Source-specific paper identifier")
    source: PaperSource
    title: str
    authors: list[str] = Field(default_factory=lambda: [])
    abstract: str = ""
    categories: list[str] = Field(default_factory=lambda: [])
    published_date: str | None = None
    updated_date: str | None = None
    doi: str | None = None
    url: str = ""
    pdf_url: str | None = None
    citation_count: int | None = None
    reference_count: int | None = None
    announce_type: str | None = Field(
        default=None,
        description="RSS announce type: 'new', 'cross', or 'replace'. Set by RSS feed providers.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Computed deduplication fields
    normalized_title: str = ""
    normalized_authors: list[str] = Field(default_factory=lambda: [])

    @model_validator(mode="after")
    def _compute_normalized_fields(self) -> Paper:
        """Auto-compute normalized title and authors for deduplication."""
        if not self.normalized_title and self.title:
            self.normalized_title = normalize_title(self.title)
        if not self.normalized_authors and self.authors:
            self.normalized_authors = [normalize_author(a) for a in self.authors]
        return self


# ── Search Models ────────────────────────────────────────────────────────────


def _default_sources() -> list[PaperSource]:
    return list(PaperSource)


class SearchQuery(BaseModel):
    """A unified search query across all paper sources."""

    query: str = Field(description="Search query string")
    sources: list[PaperSource] = Field(
        default_factory=_default_sources,
        description="Sources to search (default: all)",
    )
    categories: list[str] = Field(
        default_factory=lambda: [],
        description="Category filters (e.g., 'cs.AI', 'q-bio.BM')",
    )
    max_results: int = Field(default=20, ge=1, le=200, description="Max results per source")
    date_from: str | None = Field(default=None, description="Start date filter (YYYY-MM-DD)")
    date_to: str | None = Field(default=None, description="End date filter (YYYY-MM-DD)")
    sort_by: str = Field(default="relevance", description="Sort order: 'relevance' or 'date'")
    author: str | None = Field(default=None, description="Author name filter")
    title: str | None = Field(default=None, description="Title search filter")
    paper_ids: list[str] | None = Field(default=None, description="List of specific paper IDs to search for")


class SearchResult(BaseModel):
    """Aggregated, deduplicated search results from multiple sources."""

    papers: list[Paper] = Field(default_factory=lambda: [])
    total_count: int = 0
    sources_queried: list[PaperSource] = Field(default_factory=lambda: [])
    sources_failed: list[str] = Field(default_factory=lambda: [])
    deduplicated_count: int = 0  # Papers removed as duplicates
    query: str = ""


# ── Category Models ──────────────────────────────────────────────────────────


class SourceCategory(BaseModel):
    """A category within a paper source."""

    source: PaperSource
    category_id: str
    name: str
    description: str = ""
    subcategories: list[str] = Field(default_factory=lambda: [])


class SourceStatus(BaseModel):
    """Status of a paper source."""

    source: PaperSource
    available: bool = True
    rate_limit_remaining: int | None = None
    last_successful_query: str | None = None
    error: str | None = None
