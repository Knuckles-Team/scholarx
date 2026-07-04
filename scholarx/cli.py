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
import re
import sys
from collections import defaultdict
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


def generate_synergy_report(
    output_dir: Path,
    scored: list[dict],
    accepted: list[dict],
) -> Path:
    """Generate a consolidated synergy_report.md from scored papers."""
    domain_agg: dict[str, list[dict]] = defaultdict(list)
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

    for i, sp in enumerate(accepted, 1):
        p = sp["paper"]
        s = sp["score"]
        title = p.title if hasattr(p, "title") else p.get("title", "")
        domains = ", ".join(s["domain_hits"].keys()) if s["domain_hits"] else "—"
        icon = {"relevant": "✅", "marginal": "🟡", "irrelevant": "❌"}[s["verdict"]]
        lines.append(f"| {i} | {s['total_score']} | {icon} {s['verdict']} | {domains} | {title[:70]} |")
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

    filtered = [sp for sp in scored if sp["score"]["verdict"] == "irrelevant"]
    if filtered:
        lines += ["## Filtered Papers (No Value)", ""]
        for sp in filtered:
            title = sp["paper"].title if hasattr(sp["paper"], "title") else sp["paper"].get("title", "")
            lines.append(f"- ❌ [{sp['score']['total_score']}] {title}")
        lines.append("")

    report_path = output_dir / "synergy_report.md"
    report_path.write_text("\n".join(lines))
    return report_path


# ── Main Pipeline ───────────────────────────────────────────────────────────


async def run_scan(args: argparse.Namespace) -> dict:
    """Execute the full research scanning pipeline with rich progress bars."""
    from scholarx.api_client import ScholarXClient
    from scholarx.models import PaperSource, SearchQuery

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = output_dir / "pdfs"
    pdf_dir.mkdir(exist_ok=True)

    # Load custom taxonomy if provided
    taxonomy = DEFAULT_TAXONOMY
    if args.taxonomy:
        tax_path = Path(args.taxonomy)
        if tax_path.exists():
            tax_data = json.loads(tax_path.read_text())
            taxonomy = tax_data.get("domains", tax_data)
            console.print(f"[dim]📋 Loaded custom taxonomy: {len(taxonomy)} domains[/dim]")

    categories = [c.strip() for c in args.categories.split(",")]

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

    # ── Phase 1: Fetch papers ────────────────────────────────────────────
    client = ScholarXClient(
        sources=[PaperSource.ARXIV],
        storage_dir=str(pdf_dir),
    )

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

    if not result.papers:
        console.print("[red]❌ No papers found. Exiting.[/red]")
        return {"status": "no_papers", "count": 0}

    # ── Phase 2: Score relevance ─────────────────────────────────────────
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
            total=len(result.papers),
        )
        for paper in result.papers:
            score = score_paper(paper.title, paper.abstract, taxonomy)
            scored.append({"paper": paper, "score": score})
            progress.update(score_task, advance=1)

    scored.sort(key=lambda x: x["score"]["total_score"], reverse=True)

    # ── Phase 3: Filter & Display ────────────────────────────────────────
    relevant = [s for s in scored if s["score"]["verdict"] == "relevant"]
    marginal = [s for s in scored if s["score"]["verdict"] == "marginal"]
    irrelevant = [s for s in scored if s["score"]["verdict"] == "irrelevant"]
    accepted = relevant + marginal

    # Results table
    table = Table(title="📊 Relevance Scoring Results", show_lines=False, expand=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Score", style="bold", width=6, justify="right")
    table.add_column("Verdict", width=10)
    table.add_column("Domains", style="cyan", width=30)
    table.add_column("Title", style="white", no_wrap=False)

    for i, sp in enumerate(scored, 1):
        s = sp["score"]
        p = sp["paper"]
        verdict_style = {
            "relevant": "[bold green]✅ relevant[/bold green]",
            "marginal": "[yellow]🟡 marginal[/yellow]",
            "irrelevant": "[dim red]❌ irrelevant[/dim red]",
        }[s["verdict"]]
        domains = ", ".join(s["domain_hits"].keys()) if s["domain_hits"] else "—"
        table.add_row(
            str(i),
            f"{s['total_score']:.1f}",
            verdict_style,
            domains,
            p.title[:80],
        )

    console.print(table)

    # Summary panel
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

    # ── Save outputs ─────────────────────────────────────────────────────

    # Scoring summary JSON
    scoring_summary = {
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
    (output_dir / "relevance_scores.json").write_text(json.dumps(scoring_summary, indent=2, default=str))

    # Paper markdowns for accepted papers
    for i, sp in enumerate(accepted, 1):
        paper = sp["paper"]
        score_data = sp["score"]
        content = f"# {paper.title}\n\n"
        content += f"**Relevance Score:** {score_data['total_score']} ({score_data['verdict']})\n"
        content += f"**Domains Matched:** {', '.join(score_data['domain_hits'].keys()) if score_data['domain_hits'] else 'none'}\n"
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
        (output_dir / f"paper_{i:02d}.md").write_text(content)

    # Metadata
    accepted_meta = [sp["paper"].model_dump(exclude={"normalized_title", "normalized_authors"}) for sp in accepted]
    (output_dir / "papers_metadata.json").write_text(json.dumps(accepted_meta, indent=2, default=str))

    # ── Phase 4: Download PDFs with progress bar ─────────────────────────
    download_delay = 3.5  # arXiv rate limit
    max_retries = 3
    retry_backoff = [5, 10, 20]
    downloaded = 0
    skipped = 0
    failed_papers = []

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

        for i, sp in enumerate(accepted, 1):
            paper = sp["paper"]

            # Check if already downloaded (dedup)
            existing = client.storage.get_local_path(paper.id)
            if existing and existing.exists():
                skipped += 1
                progress.update(
                    dl_task,
                    advance=1,
                    description=f"[dim]⏭️  Already stored: {paper.title[:40]}...[/dim]",
                )
                continue

            # Rate limit between downloads
            if i > 1:
                progress.update(
                    dl_task,
                    description=f"[dim]⏳ Rate limiting ({download_delay}s)...[/dim]",
                )
                await asyncio.sleep(download_delay)

            success = False
            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        await asyncio.sleep(retry_backoff[attempt])

                    path = await client.download_paper(paper)
                    if path:
                        downloaded += 1
                        progress.update(
                            dl_task,
                            advance=1,
                            description=f"[green]✅ {paper.title[:45]}...[/green]",
                        )
                        success = True
                        break
                    else:
                        progress.update(
                            dl_task,
                            advance=1,
                            description=f"[yellow]⚠️  No PDF URL: {paper.title[:40]}...[/yellow]",
                        )
                        success = True  # Not a retry-able error
                        break
                except Exception:
                    if attempt < max_retries - 1:
                        progress.update(
                            dl_task,
                            description=f"[yellow]🔄 Retry {attempt + 1}: {paper.title[:35]}...[/yellow]",
                        )
                    else:
                        progress.update(
                            dl_task,
                            advance=1,
                            description=f"[red]❌ Failed: {paper.title[:40]}...[/red]",
                        )
                        failed_papers.append(paper.title)
                        success = True  # Exhausted retries

            if not success:
                progress.update(dl_task, advance=1)

    # ── Phase 5: Generate synergy report ─────────────────────────────────
    report_path = generate_synergy_report(output_dir, scored, accepted)

    # ── Final Summary ────────────────────────────────────────────────────
    summary_table = Table(title="🎯 Scan Complete", show_header=False, border_style="green")
    summary_table.add_column("Metric", style="bold")
    summary_table.add_column("Value", style="cyan")
    summary_table.add_row("Papers fetched", str(len(scored)))
    summary_table.add_row("Papers accepted", f"{len(accepted)} (relevant + marginal)")
    summary_table.add_row("Papers filtered", f"{len(irrelevant)} (zero value)")
    summary_table.add_row("PDFs downloaded", str(downloaded))
    summary_table.add_row("PDFs skipped (dedup)", str(skipped))
    if failed_papers:
        summary_table.add_row("PDFs failed", f"[red]{len(failed_papers)}[/red]")
    summary_table.add_row("Output directory", str(output_dir))
    summary_table.add_row("Synergy report", str(report_path))
    console.print(summary_table)

    return {
        "status": "success",
        "total_fetched": len(scored),
        "relevant": len(relevant),
        "marginal": len(marginal),
        "filtered_out": len(irrelevant),
        "downloaded": downloaded,
        "skipped_dedup": skipped,
        "failed": len(failed_papers),
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
        default="/home/apps/workspace/scholarx_papers/daily_scan",
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


def _run_auto_analysis(args: argparse.Namespace) -> None:
    """Run comparative-analysis innovation extraction on relevant papers.

    CONCEPT:SX-OS.scaling.chains-comparative-analysis-extract — Chains the comparative-analysis extract_innovations.py
    script on papers with score >= 3.0 against the target project codebases.
    """
    import subprocess

    output_dir = Path(args.output_dir)

    # Locate the innovation extractor script
    extractor_paths = [
        Path.home() / ".gemini/antigravity/skills/comparative-analysis/scripts/extract_innovations.py",
        Path(
            "/home/apps/workspace/agent-packages/skills/universal-skills"
            "/universal_skills/research/comparative-analysis/scripts/extract_innovations.py"
        ),
    ]
    extractor = next((p for p in extractor_paths if p.exists()), None)

    if not extractor:
        console.print("[yellow]⚠️  comparative-analysis skill not found. Skipping auto-analysis.[/yellow]")
        console.print("[dim]   Install via: skill-installer --tool antigravity --skills comparative-analysis[/dim]")
        return

    # Auto-detect target projects or use user-specified
    if args.target_projects:
        targets = [Path(t) for t in args.target_projects]
    else:
        # Default: scan the main ecosystem codebases
        agents_root = Path("/home/apps/workspace/agent-packages")
        targets = [
            agents_root / "agent-utilities",
            agents_root / "agents" / "scholarx",
        ]
        # Also scan agent-terminal-ui and agent-webui if they exist
        for sub in ["agent-terminal-ui", "agent-webui"]:
            candidate = agents_root / sub
            if candidate.exists():
                targets.append(candidate)

    targets = [t for t in targets if t.exists()]
    if not targets:
        console.print("[yellow]⚠️  No target projects found for analysis.[/yellow]")
        return

    # Find relevant paper markdowns (score >= 3.0)
    paper_mds = sorted(output_dir.glob("paper_*.md"))
    if not paper_mds:
        console.print("[yellow]⚠️  No paper markdowns found in output directory.[/yellow]")
        return

    # Only analyze top N papers to keep it focused
    max_papers = min(10, len(paper_mds))
    paper_mds = paper_mds[:max_papers]

    console.print(
        Panel.fit(
            f"[bold magenta]🔬 Innovation Extraction (CONCEPT:SX-OS.scaling.chains-comparative-analysis-extract)[/bold magenta]\n"
            f"Papers: [green]{len(paper_mds)}[/green] (top {max_papers} by relevance)\n"
            f"Targets: [cyan]{', '.join(t.name for t in targets)}[/cyan]\n"
            f"Extractor: [dim]{extractor}[/dim]",
            title="Auto-Analysis",
            border_style="magenta",
        )
    )

    innovations_dir = output_dir / "innovations"
    innovations_dir.mkdir(exist_ok=True)
    all_innovations = []

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
            paper_name = paper_md.stem
            progress.update(
                analysis_task,
                description=f"[magenta]Analyzing {paper_name}...",
            )

            for target in targets:
                out_file = innovations_dir / f"{paper_name}_{target.name}_innovations.json"
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
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if out_file.exists():
                        try:
                            data = json.loads(out_file.read_text())
                            if data.get("innovations"):
                                all_innovations.append(
                                    {
                                        "paper": paper_name,
                                        "target": target.name,
                                        "innovations": data["innovations"],
                                    }
                                )
                        except json.JSONDecodeError:
                            pass
                except (subprocess.TimeoutExpired, Exception) as e:
                    console.print(f"[dim yellow]  ⚠ {paper_name} → {target.name}: {e}[/dim yellow]")

            progress.update(analysis_task, advance=1)

    # ── Consolidate innovations report ───────────────────────────────────
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
        report_lines.append("## Innovations by Paper\n")
        for entry in all_innovations:
            report_lines.append(f"### {entry['paper']} → {entry['target']}\n")
            for innov in entry["innovations"]:
                report_lines.append(f"- **{innov.get('concept', 'N/A')}**: {innov.get('description', '')}")
                if innov.get("domain"):
                    report_lines.append(f"  - Domain: `{innov['domain']}`")
                if innov.get("analogy"):
                    report_lines.append(f"  - Analogy: {innov['analogy']}")
            report_lines.append("")
    else:
        report_lines.append("> No transferable innovations extracted.\n")

    innovations_report = output_dir / "innovations_report.md"
    innovations_report.write_text("\n".join(report_lines))

    # Save consolidated JSON
    (innovations_dir / "consolidated.json").write_text(json.dumps(all_innovations, indent=2))

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
