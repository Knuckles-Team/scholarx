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


def deduplicate_papers(papers: list[Paper], threshold: float = 0.90) -> tuple[list[Paper], int]:
    """Deduplicate papers across sources.

    Args:
        papers: List of papers potentially containing duplicates.
        threshold: Levenshtein similarity threshold for title matching.

    Returns:
        Tuple of (deduplicated papers, count of duplicates removed).
        When duplicates are found, the paper with the most metadata wins.
    """
    if not papers:
        return [], 0

    # Build indices
    doi_index: dict[str, int] = {}  # DOI → index in result
    cross_id_index: dict[str, int] = {}  # cross-ref ID → index in result
    title_index: list[tuple[str, str, int]] = []  # (norm_title, first_author, idx)

    result: list[Paper] = []
    duplicates_removed = 0

    for paper in papers:
        doi = _get_doi(paper)
        cross_ids = _get_cross_ids(paper)

        # Tier 1: DOI exact match
        if doi and doi in doi_index:
            existing_idx = doi_index[doi]
            result[existing_idx] = _merge_papers(result[existing_idx], paper)
            duplicates_removed += 1
            continue

        # Tier 2: Cross-ID mapping
        matched_idx = None
        for cid in cross_ids:
            if cid in cross_id_index:
                matched_idx = cross_id_index[cid]
                break

        if matched_idx is not None:
            result[matched_idx] = _merge_papers(result[matched_idx], paper)
            duplicates_removed += 1
            continue

        # Tier 3: Fuzzy title + first author
        if paper.normalized_title:
            first_author = _first_author_last_name(paper)
            for existing_title, existing_author, existing_idx in title_index:
                if first_author and existing_author and first_author != existing_author:
                    continue
                similarity = _title_similarity(paper.normalized_title, existing_title)
                if similarity >= threshold:
                    result[existing_idx] = _merge_papers(result[existing_idx], paper)
                    duplicates_removed += 1
                    matched_idx = existing_idx
                    break

        if matched_idx is not None:
            continue

        # No match — add as new
        idx = len(result)
        result.append(paper)

        if doi:
            doi_index[doi] = idx
        for cid in cross_ids:
            cross_id_index[cid] = idx
        if paper.normalized_title:
            title_index.append((paper.normalized_title, _first_author_last_name(paper), idx))

    logger.info(f"Deduplication: {len(papers)} → {len(result)} ({duplicates_removed} duplicates removed)")
    return result, duplicates_removed


def _merge_papers(existing: Paper, new: Paper) -> Paper:
    """Merge metadata from a duplicate paper into the existing one.

    Prefers the paper with more complete metadata. Fills in missing fields.
    """

    # Score completeness
    def _score(p: Paper) -> int:
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

    if _score(new) > _score(existing):
        base, other = new, existing
    else:
        base, other = existing, new

    # Fill in missing fields from the other paper
    merged_data = base.model_dump()
    if not merged_data.get("abstract") and other.abstract:
        merged_data["abstract"] = other.abstract
    if not merged_data.get("doi") and other.doi:
        merged_data["doi"] = other.doi
    if not merged_data.get("pdf_url") and other.pdf_url:
        merged_data["pdf_url"] = other.pdf_url
    if not merged_data.get("authors") and other.authors:
        merged_data["authors"] = other.authors
    if merged_data.get("citation_count") is None and other.citation_count is not None:
        merged_data["citation_count"] = other.citation_count

    # Merge metadata dicts
    other_meta = other.metadata or {}
    merged_meta = {**other_meta, **(merged_data.get("metadata") or {})}
    merged_meta[f"also_found_on_{other.source.value}"] = other.id
    merged_data["metadata"] = merged_meta

    return Paper(**merged_data)
