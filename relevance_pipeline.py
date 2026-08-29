#!/usr/bin/env python3
"""ScholarX Relevance-Scored Paper Pipeline.

Fetches 30 papers from arXiv cs.AI, scores each abstract against
agent-utilities domain concepts, and saves only the relevant ones
for comparative analysis.

Relevance scoring uses keyword matching against core agent-utilities
domains: knowledge graphs, multi-agent orchestration, planning,
reasoning, tool use, memory, evaluation, etc.
"""

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from scholarx.api_client import ScholarXClient
from scholarx.models import PaperSource, SearchQuery

OUTPUT_DIR = Path(os.environ.get("SCHOLARX_OUTPUT_DIR", str(Path.cwd() / "scholarx_papers" / "batch_30"))).expanduser()

# ── Relevance Concept Taxonomy ──────────────────────────────────────────────
# Weighted keywords grouped by agent-utilities domains.
# Higher weight = more directly relevant to AU concepts.

RELEVANCE_TAXONOMY = {
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
}


def _score_domain_hits(config: dict, text: str) -> tuple[float, list[dict]] | None:
    """Score one taxonomy domain's keyword hits against `text`.

    Returns (raw domain_score, hits) or None if the domain has no hits (or an
    invalid keyword list).
    """
    keywords = config["keywords"]
    if not isinstance(keywords, list):
        return None
    hits = []
    for kw in keywords:
        # Count occurrences (but cap contribution per keyword)
        count = len(re.findall(re.escape(kw.lower()), text))
        if count > 0:
            hits.append({"keyword": kw, "count": count})
    if not hits:
        return None
    # Score: weight * (unique keywords matched + log bonus for frequency)
    unique_count = len(hits)
    domain_score = config["weight"] * (unique_count + sum(min(h["count"], 3) * 0.2 for h in hits))
    return domain_score, hits


def _verdict_for_score(total_score: float) -> str:
    if total_score >= 3.0:
        return "relevant"
    if total_score >= 1.0:
        return "marginal"
    return "irrelevant"


def score_paper(title: str, abstract: str) -> dict:
    """Score a paper's relevance to agent-utilities.

    Returns a dict with:
      - total_score: weighted relevance score
      - domain_hits: dict of domain -> matched keywords
      - verdict: 'relevant' | 'marginal' | 'irrelevant'
    """
    text = f"{title} {abstract}".lower()
    total_score = 0.0
    domain_hits = {}

    for domain, config in RELEVANCE_TAXONOMY.items():
        scored = _score_domain_hits(config, text)
        if scored is None:
            continue
        domain_score, hits = scored
        total_score += domain_score
        domain_hits[domain] = {
            "keywords": hits,
            "domain_score": round(domain_score, 2),
        }

    return {
        "total_score": round(total_score, 2),
        "domain_hits": domain_hits,
        "domains_matched": len(domain_hits),
        "verdict": _verdict_for_score(total_score),
    }


@dataclass
class _BatchDownloadRun:
    """Config shared by every paper download in the batch pipeline."""

    client: Any
    max_retries: int = 3
    retry_backoff: tuple[int, ...] = (5, 10, 20)
    download_delay: float = 3.5


async def _attempt_batch_download(run: _BatchDownloadRun, sp: dict, index: int, total: int, attempt: int) -> str:
    """One download attempt (rate-limit sleep + the actual download).
    Returns "downloaded" or "no_url"; raises on any download error."""
    if index > 1 or attempt > 0:
        delay = run.download_delay if attempt == 0 else run.retry_backoff[attempt]
        await asyncio.sleep(delay)

    path = await run.client.download_paper(sp["paper"])
    if path:
        print(f"  ✅ [{index}/{total}] Downloaded: {sp['paper'].title[:60]}...", file=sys.stderr)
        return "downloaded"
    print(
        f"  ⚠️  [{index}/{total}] No PDF URL",
        file=sys.stderr,
    )
    # No URL is not a retriable error
    return "no_url"


def _log_batch_download_error(run: _BatchDownloadRun, e: Exception, attempt: int, index: int, total: int) -> str | None:
    """Log a failed download attempt. Returns "failed" once retries are
    exhausted, else None (the caller should retry)."""
    if attempt < run.max_retries - 1:
        print(
            f"  🔄 [{index}/{total}] Retry {attempt + 1}/{run.max_retries} "
            f"(waiting {run.retry_backoff[attempt]}s): {type(e).__name__}",
            file=sys.stderr,
        )
        return None
    print(
        f"  ❌ [{index}/{total}] Failed after {run.max_retries} attempts: {type(e).__name__}",
        file=sys.stderr,
    )
    return "failed"


async def _download_batch_paper(run: _BatchDownloadRun, sp: dict, index: int, total: int) -> str:
    """Download one accepted paper's PDF with bounded retries.
    Returns "downloaded", "no_url", "failed", or "unresolved"."""
    for attempt in range(run.max_retries):
        try:
            return await _attempt_batch_download(run, sp, index, total, attempt)
        except Exception as e:
            status = _log_batch_download_error(run, e, attempt, index, total)
            if status is not None:
                return status
    return "unresolved"


async def _download_batch_accepted_papers(client: Any, accepted: list[dict]) -> tuple[int, int]:
    """Download PDFs for every accepted paper, with rate limiting + bounded
    retries. Returns (downloaded_count, failed_count)."""
    download_delay = 3.5  # seconds between downloads (slightly over 3s to be safe)
    max_retries = 3
    retry_backoff = (5, 10, 20)  # exponential backoff seconds

    print(f"\n📥 Downloading PDFs for {len(accepted)} accepted papers...", file=sys.stderr)
    print(f"   Rate limit: {download_delay}s between downloads (arXiv policy)", file=sys.stderr)

    run = _BatchDownloadRun(
        client=client, max_retries=max_retries, retry_backoff=retry_backoff, download_delay=download_delay
    )
    downloaded = 0
    failed = 0
    for i, sp in enumerate(accepted, 1):
        status = await _download_batch_paper(run, sp, i, len(accepted))
        if status == "downloaded":
            downloaded += 1
        elif status == "failed":
            failed += 1

    if failed:
        print(f"\n  ⚠️  {failed} downloads failed after retries", file=sys.stderr)

    return downloaded, failed


def _score_batch_papers(papers: list) -> list[dict]:
    scored_papers = []
    for paper in papers:
        score_result = score_paper(paper.title, paper.abstract)
        scored_papers.append(
            {
                "paper": paper,
                "score": score_result,
            }
        )
    scored_papers.sort(key=lambda x: x["score"]["total_score"], reverse=True)
    return scored_papers


def _display_scored_papers(scored_papers: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Print each scored paper and partition it by verdict."""
    relevant = []
    marginal = []
    irrelevant = []
    icons = {"relevant": "✅", "marginal": "🟡", "irrelevant": "❌"}

    for sp in scored_papers:
        p = sp["paper"]
        s = sp["score"]
        print(f"  {icons[s['verdict']]} [{s['total_score']:5.1f}] {p.title[:80]}", file=sys.stderr)
        if s["domain_hits"]:
            domains = ", ".join(s["domain_hits"].keys())
            print(f"         Domains: {domains}", file=sys.stderr)

        if s["verdict"] == "relevant":
            relevant.append(sp)
        elif s["verdict"] == "marginal":
            marginal.append(sp)
        else:
            irrelevant.append(sp)

    return relevant, marginal, irrelevant


def _print_partition_summary(relevant: list[dict], marginal: list[dict], irrelevant: list[dict], accepted: list[dict]) -> None:
    print(f"\n{'─' * 70}", file=sys.stderr)
    print(f"  ✅ Relevant:   {len(relevant)} papers (score ≥ 3.0)", file=sys.stderr)
    print(f"  🟡 Marginal:   {len(marginal)} papers (score 1.0-2.9)", file=sys.stderr)
    print(f"  ❌ Irrelevant: {len(irrelevant)} papers (score < 1.0)", file=sys.stderr)
    print(
        f"\n  📥 Accepting {len(accepted)} papers for analysis (filtering out {len(irrelevant)} junk)",
        file=sys.stderr,
    )


def _build_batch_scoring_summary(scored_papers: list[dict], accepted: list[dict], irrelevant: list[dict]) -> dict:
    scoring_summary = {
        "total_fetched": len(scored_papers),
        "accepted": len(accepted),
        "filtered_out": len(irrelevant),
        "papers": [],
    }

    for sp in scored_papers:
        scoring_summary["papers"].append(
            {
                "title": sp["paper"].title,
                "id": sp["paper"].id,
                "score": sp["score"]["total_score"],
                "verdict": sp["score"]["verdict"],
                "domains_matched": sp["score"]["domains_matched"],
                "domain_hits": {d: v["domain_score"] for d, v in sp["score"]["domain_hits"].items()},
            }
        )
    return scoring_summary


def _render_batch_paper_markdown(sp: dict) -> str:
    paper = sp["paper"]
    score = sp["score"]
    return f"""# {paper.title}

**Relevance Score:** {score["total_score"]} ({score["verdict"]})
**Domains Matched:** {", ".join(score["domain_hits"].keys()) if score["domain_hits"] else "none"}
**Source:** {paper.source.value}
**ID:** {paper.id}
**Published:** {paper.published_date}
**URL:** {paper.url}
**DOI:** {paper.doi or "N/A"}
**Categories:** {", ".join(paper.categories)}

## Authors
{chr(10).join(f"- {a}" for a in paper.authors)}

## Abstract
{paper.abstract}

## Relevance Analysis
{json.dumps(score["domain_hits"], indent=2)}
"""


def _write_batch_accepted_markdowns(output_dir: Path, accepted: list[dict]) -> None:
    for i, sp in enumerate(accepted, 1):
        paper_file = output_dir / f"paper_{i:02d}.md"
        paper_file.write_text(_render_batch_paper_markdown(sp))


def _write_batch_outputs(output_dir: Path, scored_papers: list[dict], accepted: list[dict], irrelevant: list[dict]) -> None:
    scoring_summary = _build_batch_scoring_summary(scored_papers, accepted, irrelevant)
    summary_path = output_dir / "relevance_scores.json"
    summary_path.write_text(json.dumps(scoring_summary, indent=2))
    print(f"\n💾 Scoring summary: {summary_path}", file=sys.stderr)

    _write_batch_accepted_markdowns(output_dir, accepted)
    print(f"📄 Saved {len(accepted)} paper markdowns to {output_dir}", file=sys.stderr)

    meta_path = output_dir / "papers_metadata.json"
    accepted_meta = [sp["paper"].model_dump(exclude={"normalized_title", "normalized_authors"}) for sp in accepted]
    meta_path.write_text(json.dumps(accepted_meta, indent=2, default=str))


def _print_pipeline_summary(scored_papers: list[dict], accepted: list[dict], irrelevant: list[dict], downloaded: int) -> None:
    print(f"\n{'=' * 70}", file=sys.stderr)
    print("✅ Pipeline complete!", file=sys.stderr)
    print(f"   Papers fetched:  {len(scored_papers)}", file=sys.stderr)
    print(f"   Papers accepted: {len(accepted)} (relevant + marginal)", file=sys.stderr)
    print(f"   Papers filtered: {len(irrelevant)} (zero value)", file=sys.stderr)
    print(f"   PDFs downloaded: {downloaded}", file=sys.stderr)
    print("   Output directory configured", file=sys.stderr)
    print(f"{'=' * 70}", file=sys.stderr)


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70, file=sys.stderr)
    print("ScholarX — 30-Paper Relevance-Scored Pipeline", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    # Initialize client (arXiv only for speed)
    client = ScholarXClient(
        sources=[PaperSource.ARXIV],
        storage_dir=str(OUTPUT_DIR / "pdfs"),
    )

    # Fetch 30 papers across key AI categories
    query = SearchQuery(
        query="artificial intelligence",
        sources=[PaperSource.ARXIV],
        categories=["cs.AI"],
        max_results=30,
        sort_by="date",
    )

    print("\n🔍 Fetching 30 papers from arXiv cs.AI...", file=sys.stderr)
    result = await client.search(query)
    print(f"   Retrieved: {result.total_count} papers", file=sys.stderr)

    # Score each paper
    print("\n📊 Scoring relevance against agent-utilities concepts...\n", file=sys.stderr)
    scored_papers = _score_batch_papers(result.papers)

    # Display results
    relevant, marginal, irrelevant = _display_scored_papers(scored_papers)

    # Include relevant + marginal (even small value is good)
    accepted = relevant + marginal
    _print_partition_summary(relevant, marginal, irrelevant, accepted)

    # Save scoring summary, paper markdowns, and metadata
    _write_batch_outputs(OUTPUT_DIR, scored_papers, accepted, irrelevant)

    # Download PDFs for accepted papers with rate limiting + retry
    # arXiv rate limit: 1 request per 3 seconds
    downloaded, _failed = await _download_batch_accepted_papers(client, accepted)

    _print_pipeline_summary(scored_papers, accepted, irrelevant, downloaded)


if __name__ == "__main__":
    asyncio.run(main())
