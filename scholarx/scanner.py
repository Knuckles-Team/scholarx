#!/usr/bin/python
"""Research Scanner Engine — Relevance Scoring and Daily Paper Pipeline.

Consolidates all paper scanning functionality into a reusable library:
- Configurable multi-domain relevance taxonomy
- Keyword-based scoring engine with weighted domains
- RSS-powered daily scanning for arXiv feeds
- Query-based search scanning via ScholarX API
- Synergy report generation with domain roadmaps
- Rate-limited PDF downloading with deduplication

Usage::

    from scholarx.scanner import RelevanceScanner, DEFAULT_TAXONOMY

    scanner = RelevanceScanner()
    result = await scanner.scan_daily(
        categories=["cs.AI"],
        output_dir="scholarx_papers/daily_2026-05-08",
    )
    print(f"Found {result.relevant_count} relevant papers")

    # Or score individual papers
    scored = scanner.score_papers(papers)
    for sp in scored:
        print(f"[{sp.score:.1f}] {sp.paper.title}")
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from .models import Paper

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────────

DOWNLOAD_DELAY = 3.5  # seconds between downloads (arXiv: 1 req/3s + margin)
MAX_RETRIES = 3
RETRY_BACKOFF = [5, 10, 20]


# ── Default Taxonomy ────────────────────────────────────────────────────────

DEFAULT_TAXONOMY: dict[str, dict[str, Any]] = {
    "orchestration": {
        "weight": 3.0,
        "keywords": [
            "orchestrat",
            "multi-agent",
            "multiagent",
            "multi agent",
            "agent coordination",
            "task decomposition",
            "workflow",
            "agent framework",
            "agent system",
            "agentic",
            "tool orchestration",
            "agent architecture",
        ],
    },
    "knowledge_graph": {
        "weight": 3.0,
        "keywords": [
            "knowledge graph",
            "ontology",
            "owl",
            "semantic web",
            "entity relation",
            "graph neural",
            "graph reasoning",
            "node embedding",
            "link prediction",
            "triple",
            "knowledge base",
            "structured knowledge",
        ],
    },
    "planning_reasoning": {
        "weight": 2.5,
        "keywords": [
            "planning",
            "tree of thought",
            "chain of thought",
            "reasoning",
            "deliberat",
            "test-time compute",
            "inference-time",
            "search agent",
            "mcts",
            "monte carlo tree",
            "beam search",
            "self-refin",
            "step-by-step",
            "problem solving",
        ],
    },
    "memory_retrieval": {
        "weight": 2.5,
        "keywords": [
            "memory",
            "retrieval augmented",
            "rag",
            "episodic",
            "experience replay",
            "context window",
            "long-context",
            "vector store",
            "embedding retrieval",
            "hybrid retrieval",
            "continual learning",
            "catastrophic forgetting",
        ],
    },
    "tool_use": {
        "weight": 2.0,
        "keywords": [
            "tool use",
            "tool calling",
            "function calling",
            "api integration",
            "mcp",
            "model context protocol",
            "tool learning",
            "code generation",
            "code execution",
            "plugin",
            "tool augmented",
        ],
    },
    "evaluation_safety": {
        "weight": 2.0,
        "keywords": [
            "evaluation",
            "benchmark",
            "red team",
            "safety",
            "alignment",
            "guardrail",
            "adversarial",
            "robustness",
            "hallucination",
            "faithfulness",
            "grounding",
            "reward model",
            "reward shaping",
        ],
    },
    "swarm_evolution": {
        "weight": 2.0,
        "keywords": [
            "swarm",
            "evolutionary",
            "genetic algorithm",
            "population-based",
            "ant colony",
            "stigmergy",
            "quorum sensing",
            "self-organizing",
            "emergence",
            "collective intelligence",
            "biomimicry",
        ],
    },
    "llm_architecture": {
        "weight": 1.5,
        "keywords": [
            "transformer",
            "attention mechanism",
            "scaling law",
            "mixture of experts",
            "moe",
            "fine-tuning",
            "sft",
            "reinforcement learning from",
            "rlhf",
            "dpo",
            "distillation",
            "quantization",
            "efficient inference",
        ],
    },
    "human_ai": {
        "weight": 1.0,
        "keywords": [
            "human-in-the-loop",
            "human-ai",
            "collaborative",
            "interactive",
            "conversational",
            "dialogue",
            "user interface",
            "decision support",
        ],
    },
    "terminal_ui": {
        "weight": 2.5,
        "keywords": [
            "terminal",
            "command line",
            "cli",
            "tui",
            "session management",
            "workspace",
            "context compaction",
            "approval",
            "sandbox",
            "notification",
        ],
    },
    "web_ui": {
        "weight": 2.0,
        "keywords": [
            "web interface",
            "dashboard",
            "visualization",
            "graph visualization",
            "knowledge management",
            "chat interface",
            "streaming",
            "react",
        ],
    },
}


# ── Pydantic Models ─────────────────────────────────────────────────────────


class DomainHit(BaseModel):
    """A single domain's keyword matches and score."""

    keywords: list[dict[str, Any]] = Field(default_factory=list)
    domain_score: float = 0.0


class PaperScore(BaseModel):
    """Relevance score for a single paper.

    Attributes:
        total_score: Aggregate weighted score across all domains.
        domain_hits: Per-domain breakdown of keyword matches.
        domains_matched: Number of domains with at least one match.
        verdict: Classification — 'relevant', 'marginal', or 'irrelevant'.
    """

    total_score: float = 0.0
    domain_hits: dict[str, DomainHit] = Field(default_factory=dict)
    domains_matched: int = 0
    verdict: str = "irrelevant"


class ScoredPaper(BaseModel):
    """A paper paired with its relevance score.

    Attributes:
        paper: The paper data (dict for flexibility with RSS/API sources).
        score: The computed relevance score.
    """

    paper: dict[str, Any] = Field(default_factory=dict)
    score: PaperScore = Field(default_factory=PaperScore)


class ScanStats(BaseModel):
    """Statistics from a scan operation.

    Attributes:
        total_fetched: Total papers fetched from source.
        relevant_count: Papers scoring >= 3.0.
        marginal_count: Papers scoring 1.0-2.9.
        filtered_count: Papers scoring < 1.0.
        downloaded_count: PDFs successfully downloaded.
        failed_count: PDF downloads that failed.
        deduplicated_count: Papers skipped as duplicates.
    """

    total_fetched: int = 0
    relevant_count: int = 0
    marginal_count: int = 0
    filtered_count: int = 0
    downloaded_count: int = 0
    failed_count: int = 0
    deduplicated_count: int = 0


class ScanResult(BaseModel):
    """Result of a full scanning pipeline execution.

    Attributes:
        status: 'success', 'no_papers', or 'error'.
        stats: Aggregate statistics.
        scored_papers: All scored papers (sorted by score descending).
        output_dir: Where results were written.
        synergy_report_path: Path to the generated synergy report.
        scan_date: When the scan was performed.
    """

    status: str = "success"
    stats: ScanStats = Field(default_factory=ScanStats)
    scored_papers: list[ScoredPaper] = Field(default_factory=list)
    output_dir: str = ""
    synergy_report_path: str = ""
    scan_date: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


# ── Scoring Engine ──────────────────────────────────────────────────────────


def score_paper(
    title: str,
    abstract: str,
    taxonomy: dict[str, dict[str, Any]] | None = None,
) -> PaperScore:
    """Score a paper's relevance against a taxonomy.

    Args:
        title: Paper title.
        abstract: Paper abstract.
        taxonomy: Domain taxonomy dict. Defaults to DEFAULT_TAXONOMY.

    Returns:
        PaperScore with total score, domain hits, and verdict.
    """
    if taxonomy is None:
        taxonomy = DEFAULT_TAXONOMY

    text = f"{title} {abstract}".lower()
    total_score = 0.0
    domain_hits: dict[str, DomainHit] = {}

    for domain, config in taxonomy.items():
        hits = []
        for kw in config["keywords"]:
            count = len(re.findall(re.escape(kw.lower()), text))
            if count > 0:
                hits.append({"keyword": kw, "count": count})
        if hits:
            unique_count = len(hits)
            domain_score = config["weight"] * (unique_count + sum(min(h["count"], 3) * 0.2 for h in hits))
            total_score += domain_score
            domain_hits[domain] = DomainHit(
                keywords=hits,
                domain_score=round(domain_score, 2),
            )

    if total_score >= 3.0:
        verdict = "relevant"
    elif total_score >= 1.0:
        verdict = "marginal"
    else:
        verdict = "irrelevant"

    return PaperScore(
        total_score=round(total_score, 2),
        domain_hits=domain_hits,
        domains_matched=len(domain_hits),
        verdict=verdict,
    )


# ── Synergy Report Generator ───────────────────────────────────────────────


def generate_synergy_report(
    output_dir: Path,
    scored: list[ScoredPaper],
    title: str = "Research Synergy Report",
) -> Path:
    """Generate a consolidated synergy_report.md from scored papers.

    Groups synergies by target domain and produces a readable markdown
    report with per-paper breakdowns and a domain integration roadmap.

    Args:
        output_dir: Directory to write the report to.
        scored: List of all scored papers (relevant + marginal + irrelevant).
        title: Report title.

    Returns:
        Path to the generated report file.
    """
    accepted = [sp for sp in scored if sp.score.verdict != "irrelevant"]
    domain_agg: dict[str, list[dict]] = defaultdict(list)

    lines = [
        f"# {title}",
        "",
        f"**Date**: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Papers Scored**: {len(scored)}",
        f"**Papers Accepted**: {len(accepted)}",
        "",
        "## Relevance Ranking",
        "",
        "| # | Score | Verdict | Domains | Title |",
        "|---|-------|---------|---------|-------|",
    ]

    for i, sp in enumerate(accepted, 1):
        p = sp.paper
        s = sp.score
        domains = ", ".join(s.domain_hits.keys()) if s.domain_hits else "—"
        icon = {"relevant": "✅", "marginal": "🟡", "irrelevant": "❌"}[s.verdict]
        lines.append(f"| {i} | {s.total_score} | {icon} {s.verdict} | {domains} | {p.get('title', '')[:70]} |")
        # Collect domain hits for aggregation
        for domain, info in s.domain_hits.items():
            for kw in info.keywords:
                domain_agg[domain].append(
                    {
                        "paper": p.get("title", ""),
                        "keyword": kw["keyword"],
                        "count": kw["count"],
                        "domain_score": info.domain_score,
                    }
                )

    # Domain summary
    lines += [
        "",
        "## Synergies by Domain",
        "",
        "| Domain | Papers | Total Keywords | Aggregate Score |",
        "|--------|--------|---------------|-----------------|",
    ]
    for domain in sorted(domain_agg.keys(), key=lambda d: len(domain_agg[d]), reverse=True):
        entries = domain_agg[domain]
        papers = len(set(e["paper"] for e in entries))
        kws = len(entries)
        total_score = sum(e["domain_score"] for e in entries) / max(papers, 1)
        lines.append(f"| `{domain}` | {papers} | {kws} | {total_score:.1f} avg |")

    # Domain deep dive
    lines += ["", "## Domain Integration Roadmap", ""]
    for domain in sorted(domain_agg.keys(), key=lambda d: len(domain_agg[d]), reverse=True):
        entries = domain_agg[domain]
        paper_groups: dict[str, list[str]] = defaultdict(list)
        for e in entries:
            paper_groups[e["paper"]].append(e["keyword"])
        lines.append(f"### `{domain}` ({len(paper_groups)} papers)")
        lines.append("")
        for paper, paper_kws in paper_groups.items():
            lines.append(f"- **{paper[:70]}** — keywords: {', '.join(paper_kws)}")
        lines.append("")

    # Filtered papers
    filtered = [sp for sp in scored if sp.score.verdict == "irrelevant"]
    if filtered:
        lines += ["## Filtered Papers (No Value)", ""]
        for sp in filtered:
            lines.append(f"- ❌ [{sp.score.total_score}] {sp.paper.get('title', '')}")
        lines.append("")

    report_path = output_dir / "synergy_report.md"
    report_path.write_text("\n".join(lines))
    return report_path


# ── Deduplication ───────────────────────────────────────────────────────────


def load_existing_ids(library_dir: str | Path) -> set[str]:
    """Load arXiv IDs from all existing papers_metadata.json files.

    Args:
        library_dir: Root directory of the paper library.

    Returns:
        Set of normalized arXiv IDs already downloaded.
    """
    existing: set[str] = set()
    lib = Path(library_dir)
    if not lib.exists():
        return existing

    for meta_file in lib.rglob("papers_metadata.json"):
        try:
            data = json.loads(meta_file.read_text())
            for p in data:
                pid = p.get("id", "")
                # Normalize: "arxiv:2605.04050v1" -> "2605.04050"
                clean = pid.replace("arxiv:", "").split("v")[0]
                existing.add(clean)
        except Exception:
            pass  # nosec B110

    return existing


# ── PDF Download ────────────────────────────────────────────────────────────


async def download_pdf(pdf_url: str, output_path: Path) -> bool:
    """Download a PDF with retry logic.

    Args:
        pdf_url: URL to download from.
        output_path: Local path to save the PDF.

    Returns:
        True if download succeeded.
    """
    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                await asyncio.sleep(RETRY_BACKOFF[attempt])

            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                response = await client.get(pdf_url)
                if response.status_code == 200:
                    output_path.write_bytes(response.content)
                    return True
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                logger.warning("Download retry %d: %s", attempt + 1, e)
            else:
                logger.error("Download failed: %s", e)

    return False


# ── RelevanceScanner ────────────────────────────────────────────────────────


class RelevanceScanner:
    """Unified research paper scanning engine.

    Provides both daily RSS-based scanning and query-based search scanning,
    with configurable taxonomy, deduplication, and synergy reporting.

    Args:
        taxonomy: Domain taxonomy dict. Defaults to DEFAULT_TAXONOMY.
        library_dir: Existing paper library for deduplication.
        download_delay: Seconds between PDF downloads.
        min_download_score: Minimum score for PDF downloads.

    Example::

        scanner = RelevanceScanner()
        result = await scanner.scan_daily(["cs.AI"], output_dir="papers/daily")
        print(result.stats)
    """

    def __init__(
        self,
        taxonomy: dict[str, dict[str, Any]] | None = None,
        library_dir: str | Path | None = None,
        download_delay: float = DOWNLOAD_DELAY,
        min_download_score: float = 3.0,
    ) -> None:
        self.taxonomy = taxonomy or dict(DEFAULT_TAXONOMY)
        self.library_dir = library_dir
        self.download_delay = download_delay
        self.min_download_score = min_download_score

    def score_papers(
        self,
        papers: Sequence[dict[str, Any] | Paper],
    ) -> list[ScoredPaper]:
        """Score a list of papers against the taxonomy.

        Args:
            papers: List of paper dicts or Paper objects.

        Returns:
            List of ScoredPaper, sorted by score descending.
        """
        scored: list[ScoredPaper] = []
        for p in papers:
            if isinstance(p, Paper):
                paper_dict = p.model_dump(exclude={"normalized_title", "normalized_authors"})
            else:
                paper_dict = p

            title = paper_dict.get("title", "")
            abstract = paper_dict.get("abstract", "")
            paper_score = score_paper(title, abstract, self.taxonomy)
            scored.append(ScoredPaper(paper=paper_dict, score=paper_score))

        scored.sort(key=lambda x: x.score.total_score, reverse=True)
        return scored

    async def scan_daily(
        self,
        categories: list[str] | None = None,
        output_dir: str | Path = "",
        download_pdfs: bool = True,
    ) -> ScanResult:
        """Full daily RSS scanning pipeline.

        Fetches today's papers from arXiv RSS, scores, filters,
        optionally downloads PDFs, and generates a synergy report.

        Args:
            categories: arXiv categories to fetch. Defaults to ["cs.AI"].
            output_dir: Directory to save results. Auto-generated if empty.
            download_pdfs: Whether to download PDFs for top-scored papers.

        Returns:
            ScanResult with stats, scored papers, and report path.
        """
        if not categories:
            categories = ["cs.AI"]

        if not output_dir:
            output_dir = f"scholarx_papers/daily_{datetime.now().strftime('%Y-%m-%d')}"

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # Phase 1: Fetch papers from RSS
        from .providers.rss import RSSFeedProvider

        rss = RSSFeedProvider()
        feed_result = await rss.fetch_arxiv_daily(categories)

        papers_data = [p.model_dump(exclude={"normalized_title", "normalized_authors"}) for p in feed_result.papers]

        if not papers_data:
            return ScanResult(status="no_papers", output_dir=str(out_path))

        # Phase 2: Deduplication
        dedup_count = 0
        if self.library_dir:
            existing_ids = load_existing_ids(self.library_dir)
            if existing_ids:
                before = len(papers_data)
                papers_data = [
                    p for p in papers_data if p["id"].replace("arxiv:", "").split("v")[0] not in existing_ids
                ]
                dedup_count = before - len(papers_data)

        # Phase 3: Score
        scored = self.score_papers(papers_data)

        # Phase 4: Classify
        relevant = [s for s in scored if s.score.verdict == "relevant"]
        marginal = [s for s in scored if s.score.verdict == "marginal"]
        irrelevant = [s for s in scored if s.score.verdict == "irrelevant"]

        # Save outputs
        self._save_outputs(out_path, scored, relevant + marginal)

        # Phase 5: Download PDFs
        downloaded = 0
        failed = 0
        if download_pdfs:
            download_targets = [s for s in scored if s.score.total_score >= self.min_download_score]
            downloaded, failed = await self._download_papers(download_targets, out_path / "pdfs")

        # Phase 6: Generate synergy report
        report_path = generate_synergy_report(out_path, scored, title="Research Synergy Report — Daily cs.AI Scan")

        stats = ScanStats(
            total_fetched=len(papers_data),
            relevant_count=len(relevant),
            marginal_count=len(marginal),
            filtered_count=len(irrelevant),
            downloaded_count=downloaded,
            failed_count=failed,
            deduplicated_count=dedup_count,
        )

        return ScanResult(
            status="success",
            stats=stats,
            scored_papers=scored,
            output_dir=str(out_path),
            synergy_report_path=str(report_path),
        )

    async def scan_query(
        self,
        query: str,
        categories: list[str] | None = None,
        max_results: int = 30,
        output_dir: str | Path = "",
        download_pdfs: bool = True,
    ) -> ScanResult:
        """Query-based search scanning pipeline.

        Searches for papers via the ScholarX API, scores, filters,
        optionally downloads PDFs, and generates a synergy report.

        Args:
            query: Search query string.
            categories: arXiv category filters.
            max_results: Maximum papers to fetch.
            output_dir: Directory to save results.
            download_pdfs: Whether to download PDFs.

        Returns:
            ScanResult with stats, scored papers, and report path.
        """
        if not categories:
            categories = ["cs.AI", "cs.MA", "cs.LG"]

        if not output_dir:
            output_dir = f"scholarx_papers/query_{datetime.now().strftime('%Y%m%d_%H%M')}"

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # Fetch papers via API
        from .api_client import ScholarXClient
        from .models import PaperSource, SearchQuery

        client = ScholarXClient(sources=[PaperSource.ARXIV])
        sq = SearchQuery(
            query=query,
            sources=[PaperSource.ARXIV],
            categories=categories,
            max_results=max_results,
            sort_by="date",
        )
        result = await client.search(sq)

        papers_data = [p.model_dump(exclude={"normalized_title", "normalized_authors"}) for p in result.papers]

        if not papers_data:
            return ScanResult(status="no_papers", output_dir=str(out_path))

        # Score
        scored = self.score_papers(papers_data)

        relevant = [s for s in scored if s.score.verdict == "relevant"]
        marginal = [s for s in scored if s.score.verdict == "marginal"]
        irrelevant = [s for s in scored if s.score.verdict == "irrelevant"]

        # Save outputs
        self._save_outputs(out_path, scored, relevant + marginal)

        # Download PDFs
        downloaded = 0
        failed = 0
        if download_pdfs:
            download_targets = [s for s in scored if s.score.total_score >= self.min_download_score]
            downloaded, failed = await self._download_papers(download_targets, out_path / "pdfs")

        # Generate synergy report
        report_path = generate_synergy_report(out_path, scored)

        stats = ScanStats(
            total_fetched=len(papers_data),
            relevant_count=len(relevant),
            marginal_count=len(marginal),
            filtered_count=len(irrelevant),
            downloaded_count=downloaded,
            failed_count=failed,
        )

        return ScanResult(
            status="success",
            stats=stats,
            scored_papers=scored,
            output_dir=str(out_path),
            synergy_report_path=str(report_path),
        )

    async def scan_ids(
        self,
        paper_ids: list[str],
        output_dir: str | Path = "",
        download_pdfs: bool = True,
    ) -> ScanResult:
        """Fetch and score specific papers by ID.

        Args:
            paper_ids: List of paper IDs to fetch.
            output_dir: Directory to save results.
            download_pdfs: Whether to download PDFs.

        Returns:
            ScanResult with stats, scored papers, and report path.
        """
        if not output_dir:
            output_dir = f"scholarx_papers/fetch_{datetime.now().strftime('%Y%m%d_%H%M')}"

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        from .providers.arxiv import ArxivProvider

        provider = ArxivProvider()
        papers_data = []

        for p_id in paper_ids:
            paper = await provider.get_paper(p_id)
            if paper:
                papers_data.append(paper.model_dump(exclude={"normalized_title", "normalized_authors"}))

        if not papers_data:
            return ScanResult(status="no_papers", output_dir=str(out_path))

        # Score
        scored = self.score_papers(papers_data)

        relevant = [s for s in scored if s.score.verdict == "relevant"]
        marginal = [s for s in scored if s.score.verdict == "marginal"]
        irrelevant = [s for s in scored if s.score.verdict == "irrelevant"]

        # Save outputs (we accept all since user requested them)
        self._save_outputs(out_path, scored, scored)

        # Download PDFs for all requested papers
        downloaded = 0
        failed = 0
        if download_pdfs:
            downloaded, failed = await self._download_papers(scored, out_path / "pdfs")

        # Generate synergy report
        report_path = generate_synergy_report(out_path, scored)

        stats = ScanStats(
            total_fetched=len(papers_data),
            relevant_count=len(relevant),
            marginal_count=len(marginal),
            filtered_count=len(irrelevant),
            downloaded_count=downloaded,
            failed_count=failed,
        )

        return ScanResult(
            status="success",
            stats=stats,
            scored_papers=scored,
            output_dir=str(out_path),
            synergy_report_path=str(report_path),
        )

    # ── Private Helpers ──────────────────────────────────────────────────

    def _save_outputs(
        self,
        output_dir: Path,
        scored: list[ScoredPaper],
        accepted: list[ScoredPaper],
    ) -> None:
        """Save scoring summary, paper markdowns, and metadata."""
        # Scoring summary
        scoring_summary = {
            "scan_date": datetime.now(UTC).isoformat(),
            "total_scored": len(scored),
            "accepted": len(accepted),
            "filtered_out": len(scored) - len(accepted),
            "papers": [
                {
                    "title": sp.paper.get("title", ""),
                    "id": sp.paper.get("id", ""),
                    "announce_type": sp.paper.get("announce_type", ""),
                    "score": sp.score.total_score,
                    "verdict": sp.score.verdict,
                    "domains_matched": sp.score.domains_matched,
                    "domain_hits": {d: v.domain_score for d, v in sp.score.domain_hits.items()},
                }
                for sp in scored
            ],
        }
        (output_dir / "relevance_scores.json").write_text(json.dumps(scoring_summary, indent=2))

        # Paper markdowns
        for i, sp in enumerate(accepted, 1):
            paper = sp.paper
            s = sp.score
            domain_hits_dict = {
                d: {"keywords": v.keywords, "domain_score": v.domain_score} for d, v in s.domain_hits.items()
            }
            content = f"""# {paper.get("title", "")}

**Relevance Score:** {s.total_score} ({s.verdict})
**Domains Matched:** {", ".join(s.domain_hits.keys()) if s.domain_hits else "none"}
**Announce Type:** {paper.get("announce_type", "unknown")}
**Source:** {paper.get("source", "arxiv")}
**ID:** {paper.get("id", "unknown")}
**Published:** {paper.get("published_date", "unknown")}
**URL:** {paper.get("url", "")}
**DOI:** {paper.get("doi") or "N/A"}
**Categories:** {", ".join(paper.get("categories", []))}

## Authors
{chr(10).join(f"- {a}" for a in paper.get("authors", []))}

## Abstract
{paper.get("abstract", "N/A")}

## Relevance Analysis
{json.dumps(domain_hits_dict, indent=2)}
"""
            (output_dir / f"paper_{i:02d}.md").write_text(content)

        # Metadata
        accepted_meta = [sp.paper for sp in accepted]
        (output_dir / "papers_metadata.json").write_text(json.dumps(accepted_meta, indent=2, default=str))

    async def _download_papers(
        self,
        papers: list[ScoredPaper],
        pdf_dir: Path,
    ) -> tuple[int, int]:
        """Download PDFs for scored papers with rate limiting.

        Args:
            papers: Papers to download.
            pdf_dir: Directory to save PDFs.

        Returns:
            Tuple of (downloaded_count, failed_count).
        """
        pdf_dir.mkdir(parents=True, exist_ok=True)
        downloaded = 0
        failed = 0

        for i, sp in enumerate(papers, 1):
            paper = sp.paper
            pdf_url = paper.get("pdf_url", "")
            if not pdf_url:
                continue

            arxiv_id = paper.get("id", "").replace("arxiv:", "").replace("/", "_")
            pdf_path = pdf_dir / f"{arxiv_id}.pdf"

            if pdf_path.exists():
                downloaded += 1
                continue

            if i > 1:
                await asyncio.sleep(self.download_delay)

            if await download_pdf(pdf_url, pdf_path):
                downloaded += 1
                logger.info("Downloaded [%d/%d]: %s", i, len(papers), pdf_path.name)
            else:
                failed += 1
                logger.warning(
                    "Failed [%d/%d]: %s",
                    i,
                    len(papers),
                    paper.get("title", "")[:50],
                )

        return downloaded, failed
