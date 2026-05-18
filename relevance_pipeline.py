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
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scholarx.api_client import ScholarXClient
from scholarx.models import PaperSource, SearchQuery

OUTPUT_DIR = Path("/home/apps/workspace/scholarx_papers/batch_30")

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
        hits = []
        keywords = config["keywords"]
        if not isinstance(keywords, list):
            continue
        for kw in keywords:
            # Count occurrences (but cap contribution per keyword)
            count = len(re.findall(re.escape(kw.lower()), text))
            if count > 0:
                hits.append({"keyword": kw, "count": count})
        if hits:
            # Score: weight * (unique keywords matched + log bonus for frequency)
            unique_count = len(hits)
            domain_score = config["weight"] * (unique_count + sum(min(h["count"], 3) * 0.2 for h in hits))
            total_score += domain_score
            domain_hits[domain] = {
                "keywords": hits,
                "domain_score": round(domain_score, 2),
            }

    # Verdict thresholds
    if total_score >= 3.0:
        verdict = "relevant"
    elif total_score >= 1.0:
        verdict = "marginal"
    else:
        verdict = "irrelevant"

    return {
        "total_score": round(total_score, 2),
        "domain_hits": domain_hits,
        "domains_matched": len(domain_hits),
        "verdict": verdict,
    }


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
    scored_papers = []

    for paper in result.papers:
        score_result = score_paper(paper.title, paper.abstract)
        scored_papers.append(
            {
                "paper": paper,
                "score": score_result,
            }
        )

    # Sort by score descending
    scored_papers.sort(key=lambda x: x["score"]["total_score"], reverse=True)

    # Display results
    relevant = []
    marginal = []
    irrelevant = []

    for sp in scored_papers:
        p = sp["paper"]
        s = sp["score"]
        icon = {"relevant": "✅", "marginal": "🟡", "irrelevant": "❌"}[s["verdict"]]
        print(f"  {icon} [{s['total_score']:5.1f}] {p.title[:80]}", file=sys.stderr)
        if s["domain_hits"]:
            domains = ", ".join(s["domain_hits"].keys())
            print(f"         Domains: {domains}", file=sys.stderr)

        if s["verdict"] == "relevant":
            relevant.append(sp)
        elif s["verdict"] == "marginal":
            marginal.append(sp)
        else:
            irrelevant.append(sp)

    print(f"\n{'─' * 70}", file=sys.stderr)
    print(f"  ✅ Relevant:   {len(relevant)} papers (score ≥ 3.0)", file=sys.stderr)
    print(f"  🟡 Marginal:   {len(marginal)} papers (score 1.0-2.9)", file=sys.stderr)
    print(f"  ❌ Irrelevant: {len(irrelevant)} papers (score < 1.0)", file=sys.stderr)

    # Include relevant + marginal (even small value is good)
    accepted = relevant + marginal
    print(
        f"\n  📥 Accepting {len(accepted)} papers for analysis (filtering out {len(irrelevant)} junk)", file=sys.stderr
    )

    # Save scoring summary
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

    summary_path = OUTPUT_DIR / "relevance_scores.json"
    summary_path.write_text(json.dumps(scoring_summary, indent=2))
    print(f"\n💾 Scoring summary: {summary_path}", file=sys.stderr)

    # Save accepted papers as markdown
    for i, sp in enumerate(accepted, 1):
        paper = sp["paper"]
        score = sp["score"]
        paper_file = OUTPUT_DIR / f"paper_{i:02d}.md"
        content = f"""# {paper.title}

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
        paper_file.write_text(content)

    print(f"📄 Saved {len(accepted)} paper markdowns to {OUTPUT_DIR}", file=sys.stderr)

    # Save metadata
    meta_path = OUTPUT_DIR / "papers_metadata.json"
    accepted_meta = [sp["paper"].model_dump(exclude={"normalized_title", "normalized_authors"}) for sp in accepted]
    meta_path.write_text(json.dumps(accepted_meta, indent=2, default=str))

    # Download PDFs for accepted papers with rate limiting + retry
    # arXiv rate limit: 1 request per 3 seconds
    DOWNLOAD_DELAY = 3.5  # seconds between downloads (slightly over 3s to be safe)
    MAX_RETRIES = 3
    RETRY_BACKOFF = [5, 10, 20]  # exponential backoff seconds

    print(f"\n📥 Downloading PDFs for {len(accepted)} accepted papers...", file=sys.stderr)
    print(f"   Rate limit: {DOWNLOAD_DELAY}s between downloads (arXiv policy)", file=sys.stderr)
    downloaded = 0
    failed = []
    for i, sp in enumerate(accepted, 1):
        for attempt in range(MAX_RETRIES):
            try:
                # Rate limit: wait between downloads
                if i > 1 or attempt > 0:
                    delay = DOWNLOAD_DELAY if attempt == 0 else RETRY_BACKOFF[attempt]
                    await asyncio.sleep(delay)

                path = await client.download_paper(sp["paper"])
                if path:
                    downloaded += 1
                    print(f"  ✅ [{i}/{len(accepted)}] Downloaded: {sp['paper'].title[:60]}...", file=sys.stderr)

                    break
                else:
                    print(f"  ⚠️  [{i}/{len(accepted)}] No PDF URL: {sp['paper'].title[:60]}...", file=sys.stderr)
                    # No URL is not a retriable error
                    break
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    print(
                        f"  🔄 [{i}/{len(accepted)}] Retry {attempt + 1}/{MAX_RETRIES} "
                        f"(waiting {RETRY_BACKOFF[attempt]}s): {e}",
                        file=sys.stderr,
                    )
                else:
                    print(f"  ❌ [{i}/{len(accepted)}] Failed after {MAX_RETRIES} attempts: {e}", file=sys.stderr)
                    failed.append(sp["paper"].title)

    if failed:
        print(f"\n  ⚠️  {len(failed)} downloads failed after retries:", file=sys.stderr)
        for t in failed:
            print(f"     - {t[:70]}", file=sys.stderr)

    print(f"\n{'=' * 70}", file=sys.stderr)
    print("✅ Pipeline complete!", file=sys.stderr)
    print(f"   Papers fetched:  {len(scored_papers)}", file=sys.stderr)
    print(f"   Papers accepted: {len(accepted)} (relevant + marginal)", file=sys.stderr)
    print(f"   Papers filtered: {len(irrelevant)} (zero value)", file=sys.stderr)
    print(f"   PDFs downloaded: {downloaded}", file=sys.stderr)
    print(f"   Output dir:      {OUTPUT_DIR}", file=sys.stderr)
    print(f"{'=' * 70}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
