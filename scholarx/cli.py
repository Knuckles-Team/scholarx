#!/usr/bin/env python
"""ScholarX CLI — Research paper discovery with progress bars.

Provides a rich terminal interface for:
- Fetching recent papers from arXiv (with progress bar)
- Scoring relevance against a configurable taxonomy
- Downloading PDFs with rate limiting and dedup checking (with progress bar)
- Generating synergy reports
- Auto-chaining comparative analysis (--analyze flag)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

console = Console()

__version__ = "0.4.1"

# ── Default Relevance Taxonomy ──────────────────────────────────────────────

DEFAULT_TAXONOMY: dict[str, Any] = {
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


# ── Scoring Engine ──────────────────────────────────────────────────────────


def score_paper(title: str, abstract: str, taxonomy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Score a paper's relevance against the taxonomy."""
    taxonomy = taxonomy or DEFAULT_TAXONOMY
    text = f"{title} {abstract}".lower()
    total_score = 0.0
    domain_hits = {}

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
            domain_hits[domain] = {
                "keywords": hits,
                "domain_score": round(domain_score, 2),
            }

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


# ── Synergy Report ──────────────────────────────────────────────────────────


def _render_ranking_rows(accepted: list[dict]) -> list[str]:
    rows = []
    for i, sp in enumerate(accepted, 1):
        p = sp["paper"]
        s = sp["score"]
        title = p.title if hasattr(p, "title") else p.get("title", "")
        domains = ", ".join(s["domain_hits"].keys()) if s["domain_hits"] else "—"
        icon = {"relevant": "✅", "marginal": "🟡", "irrelevant": "❌"}[s["verdict"]]
        rows.append(f"| {i} | {s['total_score']} | {icon} {s['verdict']} | {domains} | {title[:70]} |")
    return rows


def _aggregate_domain_hits(accepted: list[dict]) -> dict[str, list[dict]]:
    domain_agg: dict[str, list[dict]] = defaultdict(list)
    for sp in accepted:
        p = sp["paper"]
        s = sp["score"]
        title = p.title if hasattr(p, "title") else p.get("title", "")
        for domain, info in s["domain_hits"].items():
            for kw in info.get("keywords", []):
                domain_agg[domain].append(
                    {
                        "paper": title,
                        "keyword": kw["keyword"],
                        "count": kw["count"],
                        "domain_score": info["domain_score"],
                    }
                )
    return domain_agg


def _render_domain_synergies_section(domain_agg: dict[str, list[dict]]) -> list[str]:
    lines = [
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
    return lines


def _render_domain_roadmap_section(domain_agg: dict[str, list[dict]]) -> list[str]:
    lines = ["", "## Domain Integration Roadmap", ""]
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
    return lines


def _render_filtered_papers_section(scored: list[dict]) -> list[str]:
    filtered = [sp for sp in scored if sp["score"]["verdict"] == "irrelevant"]
    if not filtered:
        return []
    lines = ["## Filtered Papers (No Value)", ""]
    for sp in filtered:
        title = sp["paper"].title if hasattr(sp["paper"], "title") else sp["paper"].get("title", "")
        lines.append(f"- ❌ [{sp['score']['total_score']}] {title}")
    lines.append("")
    return lines


def generate_synergy_report(
    output_dir: Path,
    scored: list[dict],
    accepted: list[dict],
) -> Path:
    """Generate a consolidated synergy_report.md from scored papers."""
    lines = [
        "# Research Synergy Report",
        "",
        f"**Date**: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Papers Fetched**: {len(scored)}",
        f"**Papers Accepted**: {len(accepted)}",
        "",
        "## Relevance Ranking",
        "",
        "| # | Score | Verdict | Domains | Title |",
        "|---|-------|---------|---------|-------|",
    ]
    lines.extend(_render_ranking_rows(accepted))

    domain_agg = _aggregate_domain_hits(accepted)
    lines.extend(_render_domain_synergies_section(domain_agg))
    lines.extend(_render_domain_roadmap_section(domain_agg))
    lines.extend(_render_filtered_papers_section(scored))

    report_path = output_dir / "synergy_report.md"
    report_path.write_text("\n".join(lines))
    return report_path


# ── Main Pipeline ───────────────────────────────────────────────────────────


def _load_scan_taxonomy(args: argparse.Namespace) -> dict[str, Any]:
    """Load a custom relevance taxonomy if `--taxonomy` was given, else the default."""
    taxonomy = DEFAULT_TAXONOMY
    if args.taxonomy:
        tax_path = Path(args.taxonomy)
        if tax_path.exists():
            tax_data = json.loads(tax_path.read_text())
            taxonomy = tax_data.get("domains", tax_data)
            console.print(f"[dim]📋 Loaded custom taxonomy: {len(taxonomy)} domains[/dim]")
    return taxonomy


def _print_scan_header(args: argparse.Namespace, categories: list[str], output_dir: Path) -> None:
    console.print(
        Panel.fit(
            f"[bold cyan]ScholarX Research Scanner v{__version__}[/bold cyan]\n"
            f"Query: [green]{args.query}[/green]\n"
            f"Categories: [yellow]{', '.join(categories)}[/yellow]\n"
            f"Max results: [blue]{args.max_results}[/blue]\n"
            f"Output: [dim]{output_dir}[/dim]",
            title="🔬 Research Discovery Pipeline",
            border_style="cyan",
        )
    )


async def _fetch_scan_papers(client: Any, args: argparse.Namespace, categories: list[str]) -> Any:
    """Phase 1: fetch papers from arXiv for the scan query, with a progress bar."""
    from scholarx.models import PaperSource, SearchQuery

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        fetch_task = progress.add_task("[cyan]Fetching papers from arXiv...", total=1)

        query = SearchQuery(
            query=args.query,
            sources=[PaperSource.ARXIV],
            categories=categories,
            max_results=args.max_results,
            sort_by="date",
        )
        result = await client.search(query)
        progress.update(fetch_task, completed=1)

    console.print(
        f"  📊 Fetched [bold]{result.total_count}[/bold] papers "
        f"([dim]{result.deduplicated_count} duplicates removed[/dim])"
    )
    return result


def _score_scan_papers(papers: list[Any], taxonomy: dict[str, Any]) -> list[dict[str, Any]]:
    """Phase 2: score every fetched paper against the taxonomy, with a progress bar."""
    scored: list[dict[str, Any]] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        score_task = progress.add_task(
            f"[yellow]Scoring relevance ({len(taxonomy)} domains)...",
            total=len(papers),
        )
        for paper in papers:
            score = score_paper(paper.title, paper.abstract, taxonomy)
            scored.append({"paper": paper, "score": score})
            progress.update(score_task, advance=1)

    scored.sort(key=lambda x: x["score"]["total_score"], reverse=True)
    return scored


def _partition_scored_papers(
    scored: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Split scored papers by verdict; `accepted` is relevant + marginal."""
    relevant = [s for s in scored if s["score"]["verdict"] == "relevant"]
    marginal = [s for s in scored if s["score"]["verdict"] == "marginal"]
    irrelevant = [s for s in scored if s["score"]["verdict"] == "irrelevant"]
    accepted = relevant + marginal
    return relevant, marginal, irrelevant, accepted


def _render_scoring_table(scored: list[dict[str, Any]]) -> Table:
    table = Table(title="📊 Relevance Scoring Results", show_lines=False, expand=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Score", style="bold", width=6, justify="right")
    table.add_column("Verdict", width=10)
    table.add_column("Domains", style="cyan", width=30)
    table.add_column("Title", style="white", no_wrap=False)

    verdict_styles = {
        "relevant": "[bold green]✅ relevant[/bold green]",
        "marginal": "[yellow]🟡 marginal[/yellow]",
        "irrelevant": "[dim red]❌ irrelevant[/dim red]",
    }
    for i, sp in enumerate(scored, 1):
        s = sp["score"]
        p = sp["paper"]
        domains = ", ".join(s["domain_hits"].keys()) if s["domain_hits"] else "—"
        table.add_row(
            str(i),
            f"{s['total_score']:.1f}",
            verdict_styles[s["verdict"]],
            domains,
            p.title[:80],
        )
    return table


def _print_filter_summary(
    relevant: list[dict[str, Any]],
    marginal: list[dict[str, Any]],
    irrelevant: list[dict[str, Any]],
    accepted: list[dict[str, Any]],
) -> None:
    console.print(
        Panel.fit(
            f"[bold green]✅ Relevant:[/bold green]   {len(relevant)} papers (score ≥ 3.0)\n"
            f"[bold yellow]🟡 Marginal:[/bold yellow]   {len(marginal)} papers (score 1.0-2.9)\n"
            f"[bold red]❌ Irrelevant:[/bold red] {len(irrelevant)} papers (score < 1.0)\n"
            f"[bold cyan]📥 Accepting:[/bold cyan]  {len(accepted)} papers for analysis",
            title="Filter Summary",
            border_style="green",
        )
    )


def _build_scoring_summary(
    args: argparse.Namespace,
    categories: list[str],
    scored: list[dict[str, Any]],
    accepted: list[dict[str, Any]],
    irrelevant: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "scan_date": datetime.now(UTC).isoformat(),
        "query": args.query,
        "categories": categories,
        "total_fetched": len(scored),
        "accepted": len(accepted),
        "filtered_out": len(irrelevant),
        "papers": [
            {
                "title": sp["paper"].title,
                "id": sp["paper"].id,
                "url": sp["paper"].url,
                "published_date": sp["paper"].published_date,
                "score": sp["score"]["total_score"],
                "verdict": sp["score"]["verdict"],
                "domains_matched": sp["score"]["domains_matched"],
                "domain_hits": {d: v["domain_score"] for d, v in sp["score"]["domain_hits"].items()},
            }
            for sp in scored
        ],
    }


def _render_paper_markdown(sp: dict[str, Any]) -> str:
    """Render a single accepted paper's markdown summary."""
    paper = sp["paper"]
    score_data = sp["score"]
    content = f"# {paper.title}\n\n"
    content += f"**Relevance Score:** {score_data['total_score']} ({score_data['verdict']})\n"
    content += (
        f"**Domains Matched:** {', '.join(score_data['domain_hits'].keys()) if score_data['domain_hits'] else 'none'}\n"
    )
    content += f"**Source:** {paper.source.value}\n"
    content += f"**ID:** {paper.id}\n"
    content += f"**Published:** {paper.published_date}\n"
    content += f"**URL:** {paper.url}\n"
    content += f"**DOI:** {paper.doi or 'N/A'}\n"
    content += f"**Categories:** {', '.join(paper.categories)}\n\n"
    content += "## Authors\n"
    content += "\n".join(f"- {a}" for a in paper.authors) + "\n\n"
    content += f"## Abstract\n{paper.abstract}\n\n"
    content += "## Relevance Analysis\n"
    content += json.dumps(score_data["domain_hits"], indent=2) + "\n"
    return content


def _write_accepted_paper_markdowns(output_dir: Path, accepted: list[dict[str, Any]]) -> None:
    for i, sp in enumerate(accepted, 1):
        (output_dir / f"paper_{i:02d}.md").write_text(_render_paper_markdown(sp))


def _write_scan_outputs(
    output_dir: Path,
    args: argparse.Namespace,
    categories: list[str],
    scored: list[dict[str, Any]],
    accepted: list[dict[str, Any]],
    irrelevant: list[dict[str, Any]],
) -> None:
    """Write relevance_scores.json, per-paper markdowns, and papers_metadata.json."""
    scoring_summary = _build_scoring_summary(args, categories, scored, accepted, irrelevant)
    (output_dir / "relevance_scores.json").write_text(json.dumps(scoring_summary, indent=2, default=str))

    _write_accepted_paper_markdowns(output_dir, accepted)

    accepted_meta = [sp["paper"].model_dump(exclude={"normalized_title", "normalized_authors"}) for sp in accepted]
    (output_dir / "papers_metadata.json").write_text(json.dumps(accepted_meta, indent=2, default=str))


@dataclass
class _DownloadStats:
    """Outcome tally for a scan's PDF-download phase."""

    downloaded: int = 0
    skipped: int = 0
    failed_papers: list[str] = field(default_factory=list)


@dataclass
class _PdfDownloadRun:
    """Config + the shared rich Progress handle for one scan's PDF downloads."""

    client: Any
    progress: Progress
    task_id: Any
    max_retries: int = 3
    retry_backoff: tuple[int, ...] = (5, 10, 20)
    download_delay: float = 3.5


async def _download_one_paper(run: _PdfDownloadRun, paper: Any, index: int) -> str:
    """Download one paper's PDF with rate limiting + bounded retries, updating the
    progress bar as it goes. Returns "skipped", "downloaded", "no_url", or "failed"."""
    existing = run.client.storage.get_local_path(paper.id)
    if existing and existing.exists():
        run.progress.update(
            run.task_id,
            advance=1,
            description=f"[dim]⏭️  Already stored: {paper.title[:40]}...[/dim]",
        )
        return "skipped"

    if index > 1:
        run.progress.update(
            run.task_id,
            description=f"[dim]⏳ Rate limiting ({run.download_delay}s)...[/dim]",
        )
        await asyncio.sleep(run.download_delay)

    success = False
    for attempt in range(run.max_retries):
        try:
            if attempt > 0:
                await asyncio.sleep(run.retry_backoff[attempt])

            path = await run.client.download_paper(paper)
            if path:
                run.progress.update(
                    run.task_id,
                    advance=1,
                    description=f"[green]✅ {paper.title[:45]}...[/green]",
                )
                return "downloaded"
            run.progress.update(
                run.task_id,
                advance=1,
                description=f"[yellow]⚠️  No PDF URL: {paper.title[:40]}...[/yellow]",
            )
            return "no_url"
        except Exception:
            if attempt < run.max_retries - 1:
                run.progress.update(
                    run.task_id,
                    description=f"[yellow]🔄 Retry {attempt + 1}: {paper.title[:35]}...[/yellow]",
                )
            else:
                run.progress.update(
                    run.task_id,
                    advance=1,
                    description=f"[red]❌ Failed: {paper.title[:40]}...[/red]",
                )
                return "failed"

    if not success:
        run.progress.update(run.task_id, advance=1)
    return "unresolved"


async def _download_accepted_papers(client: Any, accepted: list[dict[str, Any]]) -> _DownloadStats:
    """Phase 4: download PDFs for every accepted paper, with rate limiting,
    dedup skipping, and bounded per-paper retries."""
    stats = _DownloadStats()
    download_delay = 3.5  # arXiv rate limit
    max_retries = 3
    retry_backoff = (5, 10, 20)

    console.print(f"\n[bold cyan]📥 Downloading PDFs for {len(accepted)} papers[/bold cyan]")
    console.print(f"[dim]   Rate limit: {download_delay}s between requests (arXiv policy)[/dim]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        dl_task = progress.add_task("[green]Downloading PDFs...", total=len(accepted))
        run = _PdfDownloadRun(
            client=client,
            progress=progress,
            task_id=dl_task,
            max_retries=max_retries,
            retry_backoff=retry_backoff,
            download_delay=download_delay,
        )

        for i, sp in enumerate(accepted, 1):
            status = await _download_one_paper(run, sp["paper"], i)
            if status == "downloaded":
                stats.downloaded += 1
            elif status == "skipped":
                stats.skipped += 1
            elif status == "failed":
                stats.failed_papers.append(sp["paper"].title)

    return stats


def _print_scan_summary(
    scored_count: int,
    accepted_count: int,
    irrelevant_count: int,
    stats: _DownloadStats,
    output_dir: Path,
    report_path: Path,
) -> None:
    summary_table = Table(title="🎯 Scan Complete", show_header=False, border_style="green")
    summary_table.add_column("Metric", style="bold")
    summary_table.add_column("Value", style="cyan")
    summary_table.add_row("Papers fetched", str(scored_count))
    summary_table.add_row("Papers accepted", f"{accepted_count} (relevant + marginal)")
    summary_table.add_row("Papers filtered", f"{irrelevant_count} (zero value)")
    summary_table.add_row("PDFs downloaded", str(stats.downloaded))
    summary_table.add_row("PDFs skipped (dedup)", str(stats.skipped))
    if stats.failed_papers:
        summary_table.add_row("PDFs failed", f"[red]{len(stats.failed_papers)}[/red]")
    summary_table.add_row("Output directory", str(output_dir))
    summary_table.add_row("Synergy report", str(report_path))
    console.print(summary_table)


async def run_scan(args: argparse.Namespace) -> dict:
    """Execute the full research scanning pipeline with rich progress bars."""
    from scholarx.api_client import ScholarXClient
    from scholarx.models import PaperSource

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = output_dir / "pdfs"
    pdf_dir.mkdir(exist_ok=True)

    taxonomy = _load_scan_taxonomy(args)
    categories = [c.strip() for c in args.categories.split(",")]
    _print_scan_header(args, categories, output_dir)

    client = ScholarXClient(sources=[PaperSource.ARXIV], storage_dir=str(pdf_dir))
    result = await _fetch_scan_papers(client, args, categories)

    if not result.papers:
        console.print("[red]❌ No papers found. Exiting.[/red]")
        return {"status": "no_papers", "count": 0}

    scored = _score_scan_papers(result.papers, taxonomy)
    relevant, marginal, irrelevant, accepted = _partition_scored_papers(scored)

    console.print(_render_scoring_table(scored))
    _print_filter_summary(relevant, marginal, irrelevant, accepted)
    _write_scan_outputs(output_dir, args, categories, scored, accepted, irrelevant)

    stats = await _download_accepted_papers(client, accepted)

    report_path = generate_synergy_report(output_dir, scored, accepted)
    _print_scan_summary(len(scored), len(accepted), len(irrelevant), stats, output_dir, report_path)

    return {
        "status": "success",
        "total_fetched": len(scored),
        "relevant": len(relevant),
        "marginal": len(marginal),
        "filtered_out": len(irrelevant),
        "downloaded": stats.downloaded,
        "skipped_dedup": stats.skipped,
        "failed": len(stats.failed_papers),
        "output_dir": str(output_dir),
        "synergy_report": str(report_path),
    }


# ── CLI Entry Point ─────────────────────────────────────────────────────────


def cli():
    """ScholarX CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="scholarx",
        description="ScholarX — Research paper discovery with relevance scoring",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  scholarx scan --query 'multi-agent systems' --output-dir ./papers\n"
            "  scholarx scan --categories cs.AI,cs.LG,cs.CL --max-results 50 --output-dir ./papers\n"
            "  scholarx scan --query 'knowledge graphs' --taxonomy custom_taxonomy.json --output-dir ./papers\n"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── scan command ─────────────────────────────────────────────────────
    scan_parser = subparsers.add_parser("scan", help="Scan for research papers and score relevance")
    scan_parser.add_argument(
        "--query",
        default="artificial intelligence",
        help="Search query (default: 'artificial intelligence')",
    )
    scan_parser.add_argument(
        "--categories",
        default="cs.AI,cs.MA,cs.LG,cs.CL,cs.SE,cs.IR,cs.DC",
        help="Comma-separated arXiv categories (default: cs.AI,cs.MA,cs.LG,cs.CL,cs.SE,cs.IR,cs.DC)",
    )
    scan_parser.add_argument(
        "--max-results",
        type=int,
        default=50,
        help="Maximum papers to fetch (default: 50)",
    )
    scan_parser.add_argument(
        "--output-dir",
        default=os.environ.get("SCHOLARX_OUTPUT_DIR", str(Path.cwd() / "scholarx_papers" / "daily_scan")),
        help="Directory to save papers and reports",
    )
    scan_parser.add_argument(
        "--taxonomy",
        default=None,
        help="Path to custom relevance_taxonomy.json",
    )
    scan_parser.add_argument(
        "--analyze",
        action="store_true",
        help="Auto-trigger comparative analysis on relevant papers (score >= 3.0)",
    )
    scan_parser.add_argument(
        "--target-projects",
        nargs="*",
        default=None,
        help="Target project paths for --analyze (default: auto-detect from ecosystem)",
    )

    # ── status command ───────────────────────────────────────────────────
    subparsers.add_parser("status", help="Show stored paper library status")

    args = parser.parse_args()

    if args.command == "scan":
        result = asyncio.run(run_scan(args))
        if args.analyze and result.get("relevant", 0) > 0:
            _run_auto_analysis(args)
    elif args.command == "status":
        _show_status()
    else:
        parser.print_help()


def _locate_innovation_extractor(args: argparse.Namespace, packages_root: Path) -> Path | None:
    """Find the comparative-analysis `extract_innovations.py` script, honoring
    `SCHOLARX_ANALYSIS_SCRIPT` if set."""
    configured_extractor = os.environ.get("SCHOLARX_ANALYSIS_SCRIPT")
    extractor_paths = [Path(configured_extractor).expanduser()] if configured_extractor else []
    extractor_paths.append(
        packages_root
        / "skills"
        / "universal-skills"
        / "universal_skills"
        / "research"
        / "comparative-analysis"
        / "scripts"
        / "extract_innovations.py"
    )
    return next((p for p in extractor_paths if p.exists()), None)


def _resolve_analysis_targets(args: argparse.Namespace, packages_root: Path) -> list[Path]:
    """Auto-detect target project codebases to scan, or use user-specified ones."""
    if args.target_projects:
        targets = [Path(t) for t in args.target_projects]
    else:
        agents_root = packages_root
        targets = [
            agents_root / "agent-utilities",
            agents_root / "agents" / "scholarx",
        ]
        for sub in ["agent-terminal-ui", "agent-webui"]:
            candidate = agents_root / sub
            if candidate.exists():
                targets.append(candidate)

    return [t for t in targets if t.exists()]


def _select_relevant_paper_markdowns(output_dir: Path, max_papers: int = 10) -> list[Path]:
    """Return the top-N accepted paper markdowns (by relevance) to analyze."""
    paper_mds = sorted(output_dir.glob("paper_*.md"))
    limit = min(max_papers, len(paper_mds))
    return paper_mds[:limit]


def _print_auto_analysis_header(paper_mds: list[Path], targets: list[Path], extractor: Path) -> None:
    console.print(
        Panel.fit(
            f"[bold magenta]🔬 Innovation Extraction (CONCEPT:SX-OS.scaling.chains-comparative-analysis-extract)[/bold magenta]\n"
            f"Papers: [green]{len(paper_mds)}[/green] (top {len(paper_mds)} by relevance)\n"
            f"Targets: [cyan]{', '.join(t.name for t in targets)}[/cyan]\n"
            f"Extractor: [dim]{extractor}[/dim]",
            title="Auto-Analysis",
            border_style="magenta",
        )
    )


def _extract_innovations_for_target(
    paper_md: Path, target: Path, innovations_dir: Path, extractor: Path
) -> dict | None:
    """Run the extractor for one (paper, target) pair and return its
    `{"paper", "target", "innovations"}` entry, or None if nothing usable came back."""
    out_file = innovations_dir / f"{paper_md.stem}_{target.name}_innovations.json"
    cmd = [
        sys.executable,
        str(extractor),
        "--source",
        str(paper_md),
        "--target",
        str(target),
        "--output",
        str(out_file),
    ]
    try:
        subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=False,
        )
        if out_file.exists():
            try:
                data = json.loads(out_file.read_text())
                if data.get("innovations"):
                    return {
                        "paper": paper_md.stem,
                        "target": target.name,
                        "innovations": data["innovations"],
                    }
            except json.JSONDecodeError:
                pass
    except Exception as e:
        console.print(f"[dim yellow]  ⚠ Paper analysis failed: {type(e).__name__}[/dim yellow]")
    return None


def _run_innovation_extraction(
    paper_mds: list[Path], targets: list[Path], innovations_dir: Path, extractor: Path
) -> list[dict]:
    """Extract innovations for every (paper, target) pair, with a progress bar."""
    all_innovations: list[dict] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        analysis_task = progress.add_task("[magenta]Extracting innovations...", total=len(paper_mds))

        for paper_md in paper_mds:
            progress.update(
                analysis_task,
                description=f"[magenta]Analyzing {paper_md.stem}...",
            )
            for target in targets:
                entry = _extract_innovations_for_target(paper_md, target, innovations_dir, extractor)
                if entry is not None:
                    all_innovations.append(entry)
            progress.update(analysis_task, advance=1)

    return all_innovations


def _render_innovation_bullet(innov: dict) -> list[str]:
    """Render one innovation's markdown bullet, with its optional domain/analogy sub-lines."""
    lines = [f"- **{innov.get('concept', 'N/A')}**: {innov.get('description', '')}"]
    if innov.get("domain"):
        lines.append(f"  - Domain: `{innov['domain']}`")
    if innov.get("analogy"):
        lines.append(f"  - Analogy: {innov['analogy']}")
    return lines


def _render_innovations_by_paper(all_innovations: list[dict]) -> list[str]:
    """Render the '## Innovations by Paper' section body."""
    lines = ["## Innovations by Paper\n"]
    for entry in all_innovations:
        lines.append(f"### {entry['paper']} → {entry['target']}\n")
        for innov in entry["innovations"]:
            lines.extend(_render_innovation_bullet(innov))
        lines.append("")
    return lines


def _render_innovations_report(paper_mds: list[Path], targets: list[Path], all_innovations: list[dict]) -> str:
    """Build the markdown body of the consolidated innovations report."""
    report_lines = [
        "# Innovation Extraction Report",
        "",
        f"**Date**: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Papers Analyzed**: {len(paper_mds)}",
        f"**Target Projects**: {', '.join(t.name for t in targets)}",
        f"**Total Innovations Found**: {sum(len(i['innovations']) for i in all_innovations)}",
        "",
    ]

    if all_innovations:
        report_lines.extend(_render_innovations_by_paper(all_innovations))
    else:
        report_lines.append("> No transferable innovations extracted.\n")

    return "\n".join(report_lines)


def _write_innovations_report(
    output_dir: Path, innovations_dir: Path, paper_mds: list[Path], targets: list[Path], all_innovations: list[dict]
) -> Path:
    """Write the consolidated markdown report and JSON, returning the report path."""
    innovations_report = output_dir / "innovations_report.md"
    innovations_report.write_text(_render_innovations_report(paper_mds, targets, all_innovations))
    (innovations_dir / "consolidated.json").write_text(json.dumps(all_innovations, indent=2))
    return innovations_report


def _print_auto_analysis_complete(innovations_report: Path, innovations_dir: Path, all_innovations: list[dict]) -> None:
    total = sum(len(i["innovations"]) for i in all_innovations)
    console.print(
        Panel.fit(
            f"[bold green]✅ Innovation Extraction Complete[/bold green]\n"
            f"Innovations found: [cyan]{total}[/cyan]\n"
            f"Report: [dim]{innovations_report}[/dim]\n"
            f"Details: [dim]{innovations_dir}[/dim]",
            title="Analysis Results",
            border_style="green",
        )
    )


def _run_auto_analysis(args: argparse.Namespace) -> None:
    """Run comparative-analysis innovation extraction on relevant papers.

    CONCEPT:SX-OS.scaling.chains-comparative-analysis-extract — Chains the comparative-analysis extract_innovations.py
    script on papers with score >= 3.0 against the target project codebases.
    """
    output_dir = Path(args.output_dir)
    packages_root = Path(os.environ.get("AGENT_PACKAGES_ROOT", str(Path(__file__).resolve().parents[3]))).expanduser()

    extractor = _locate_innovation_extractor(args, packages_root)
    if not extractor:
        console.print("[yellow]⚠️  comparative-analysis skill not found. Skipping auto-analysis.[/yellow]")
        console.print("[dim]   Install via: skill-installer --tool antigravity --skills comparative-analysis[/dim]")
        return

    targets = _resolve_analysis_targets(args, packages_root)
    if not targets:
        console.print("[yellow]⚠️  No target projects found for analysis.[/yellow]")
        return

    paper_mds = _select_relevant_paper_markdowns(output_dir)
    if not paper_mds:
        console.print("[yellow]⚠️  No paper markdowns found in output directory.[/yellow]")
        return

    _print_auto_analysis_header(paper_mds, targets, extractor)

    innovations_dir = output_dir / "innovations"
    innovations_dir.mkdir(exist_ok=True)

    all_innovations = _run_innovation_extraction(paper_mds, targets, innovations_dir, extractor)
    innovations_report = _write_innovations_report(output_dir, innovations_dir, paper_mds, targets, all_innovations)
    _print_auto_analysis_complete(innovations_report, innovations_dir, all_innovations)


def _show_status():
    """Show the paper library status."""
    from scholarx.paper_storage import PaperStorage

    storage = PaperStorage()
    stats = storage.get_storage_stats()
    papers = storage.list_stored_papers()

    table = Table(title="📚 ScholarX Paper Library", border_style="cyan")
    table.add_column("#", style="dim", width=3)
    table.add_column("Title", style="white", no_wrap=False)
    table.add_column("Source", style="cyan", width=8)
    table.add_column("Date", style="dim", width=12)
    table.add_column("Status", width=8)

    for i, p in enumerate(papers, 1):
        status = "[green]✅[/green]" if p.get("exists") else "[red]❌[/red]"
        table.add_row(
            str(i),
            (p.get("title", "Unknown"))[:70],
            p.get("source", "?"),
            p.get("published_date", "?"),
            status,
        )

    console.print(table)
    console.print(
        f"\n[dim]Storage: {stats['paper_count']} papers, {stats['total_size_mb']} MB in {stats['storage_dir']}[/dim]"
    )


if __name__ == "__main__":
    cli()
