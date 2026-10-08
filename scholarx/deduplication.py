#!/usr/bin/python
"""Cross-source paper deduplication.

Implements a multi-tier matching strategy to identify duplicate papers
across different sources (e.g., the same paper on arXiv and Semantic Scholar).

Matching tiers (ordered by confidence):
1. DOI exact match
2. Cross-ID mapping (arXiv ID ↔ S2 corpus ID via metadata)
3. Normalized title + first-author last name (Levenshtein ≥ 0.90)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .models import Paper

logger = logging.getLogger(__name__)


def _get_doi(paper: Paper) -> str | None:
    """Extract normalized DOI."""
    if paper.doi:
        return paper.doi.lower().strip()
    return None


def _get_cross_ids(paper: Paper) -> set[str]:
    """Extract all known cross-reference IDs from metadata."""
    ids: set[str] = set()
    ids.add(paper.id.lower())

    if paper.doi:
        ids.add(f"doi:{paper.doi.lower()}")

    # S2 stores arXiv/PMID in metadata
    arxiv_id = paper.metadata.get("arxiv_id")
    if arxiv_id:
        ids.add(f"arxiv:{arxiv_id.lower()}")

    pmid = paper.metadata.get("pmid")
    if pmid:
        ids.add(f"pmid:{str(pmid).lower()}")

    s2_id = paper.metadata.get("s2_id")
    if s2_id:
        ids.add(f"s2:{s2_id.lower()}")

    return ids


def _first_author_last_name(paper: Paper) -> str:
    """Extract the first author's last name for fuzzy matching."""
    if paper.normalized_authors:
        parts = paper.normalized_authors[0].split()
        return parts[-1] if parts else ""
    return ""


def _title_similarity(a: str, b: str) -> float:
    """Compute Levenshtein ratio between two normalized titles."""
    try:
        from Levenshtein import ratio

        return ratio(a, b)
    except ImportError:
        # Fallback: simple exact match
        return 1.0 if a == b else 0.0


@dataclass
class _DedupIndex:
    """Accumulated dedup state: the deduplicated result list, plus each
    matching tier's lookup index."""

    result: list[Paper] = field(default_factory=list)
    doi_index: dict[str, int] = field(default_factory=dict)  # DOI → index in result
    cross_id_index: dict[str, int] = field(default_factory=dict)  # cross-ref ID → index in result
    title_index: list[tuple[str, str, int]] = field(default_factory=list)  # (norm_title, first_author, idx)


def _match_by_cross_id(cross_ids: set[str], cross_id_index: dict[str, int]) -> int | None:
    for cid in cross_ids:
        if cid in cross_id_index:
            return cross_id_index[cid]
    return None


def _match_by_fuzzy_title(title_index: list[tuple[str, str, int]], paper: Paper, threshold: float) -> int | None:
    first_author = _first_author_last_name(paper)
    for existing_title, existing_author, existing_idx in title_index:
        if first_author and existing_author and first_author != existing_author:
            continue
        similarity = _title_similarity(paper.normalized_title, existing_title)
        if similarity >= threshold:
            return existing_idx
    return None


def _find_duplicate_index(
    index: _DedupIndex, paper: Paper, doi: str | None, cross_ids: set[str], threshold: float
) -> int | None:
    """Try each matching tier in confidence order; return the matched
    result index, or None if `paper` doesn't match anything seen so far."""
    if doi and doi in index.doi_index:
        return index.doi_index[doi]

    matched = _match_by_cross_id(cross_ids, index.cross_id_index)
    if matched is not None:
        return matched

    if paper.normalized_title:
        return _match_by_fuzzy_title(index.title_index, paper, threshold)

    return None


def _register_new_paper(index: _DedupIndex, paper: Paper, doi: str | None, cross_ids: set[str]) -> None:
    """Add `paper` as a new (non-duplicate) entry and index it for later tiers."""
    idx = len(index.result)
    index.result.append(paper)

    if doi:
        index.doi_index[doi] = idx
    for cid in cross_ids:
        index.cross_id_index[cid] = idx
    if paper.normalized_title:
        index.title_index.append((paper.normalized_title, _first_author_last_name(paper), idx))


def deduplicate_papers(papers: list[Paper], threshold: float = 0.90) -> tuple[list[Paper], int]:
    """Deduplicate papers across sources. (CONCEPT:SX-OS.config.sx-3)

    Args:
        papers: List of papers potentially containing duplicates.
        threshold: Levenshtein similarity threshold for title matching.

    Returns:
        Tuple of (deduplicated papers, count of duplicates removed).
        When duplicates are found, the paper with the most metadata wins.
    """
    if not papers:
        return [], 0

    index = _DedupIndex()
    duplicates_removed = 0

    for paper in papers:
        doi = _get_doi(paper)
        cross_ids = _get_cross_ids(paper)

        matched_idx = _find_duplicate_index(index, paper, doi, cross_ids, threshold)
        if matched_idx is not None:
            index.result[matched_idx] = _merge_papers(index.result[matched_idx], paper)
            duplicates_removed += 1
            continue

        _register_new_paper(index, paper, doi, cross_ids)

    logger.info(f"Deduplication: {len(papers)} → {len(index.result)} ({duplicates_removed} duplicates removed)")
    return index.result, duplicates_removed


def _paper_completeness_score(p: Paper) -> int:
    """Score how complete a paper's metadata is, to pick the merge base."""
    s = 0
    if p.abstract:
        s += 3
    if p.doi:
        s += 2
    if p.pdf_url:
        s += 2
    if p.authors:
        s += len(p.authors)
    if p.citation_count is not None:
        s += 1
    if p.categories:
        s += 1
    return s


_FALLBACK_FIELDS = ("abstract", "doi", "pdf_url", "authors")


def _fill_falsy_fields(merged_data: dict, other: Paper) -> None:
    """Fill each of `_FALLBACK_FIELDS` from `other` if `merged_data` has no
    truthy value for it yet, in place."""
    for field_name in _FALLBACK_FIELDS:
        if merged_data.get(field_name):
            continue
        other_value = getattr(other, field_name)
        if other_value:
            merged_data[field_name] = other_value


def _fill_citation_count(merged_data: dict, other: Paper) -> None:
    """citation_count uses an is-None check (unlike _FALLBACK_FIELDS' truthy
    check) since 0 is a valid, meaningful count."""
    if merged_data.get("citation_count") is None and other.citation_count is not None:
        merged_data["citation_count"] = other.citation_count


def _fill_missing_fields(merged_data: dict, other: Paper) -> None:
    """Fill `merged_data`'s missing scalar fields from `other`, in place."""
    _fill_falsy_fields(merged_data, other)
    _fill_citation_count(merged_data, other)


def _merge_metadata_dicts(merged_data: dict, other: Paper) -> None:
    """Merge `other`'s metadata into `merged_data["metadata"]`, in place, and
    record which source `other` was also found on."""
    other_meta = other.metadata or {}
    merged_meta = {**other_meta, **(merged_data.get("metadata") or {})}
    merged_meta[f"also_found_on_{other.source.value}"] = other.id
    merged_data["metadata"] = merged_meta


def _merge_papers(existing: Paper, new: Paper) -> Paper:
    """Merge metadata from a duplicate paper into the existing one. (CONCEPT:SX-OS.config.sx-3)

    Prefers the paper with more complete metadata. Fills in missing fields.
    """
    if _paper_completeness_score(new) > _paper_completeness_score(existing):
        base, other = new, existing
    else:
        base, other = existing, new

    merged_data = base.model_dump()
    _fill_missing_fields(merged_data, other)
    _merge_metadata_dicts(merged_data, other)

    return Paper(**merged_data)
