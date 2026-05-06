#!/usr/bin/env python3
"""Fetch top 5 AI research papers from arXiv using ScholarX.

Saves paper metadata (JSON) and downloads PDFs to the workspace
directory: /home/apps/workspace/scholarx_papers/
"""

import asyncio
import json
import sys
from pathlib import Path

# Ensure the local package is importable
sys.path.insert(0, str(Path(__file__).parent))

from scholarx.api_client import ScholarXClient
from scholarx.models import PaperSource, SearchQuery

OUTPUT_DIR = Path("/home/apps/workspace/scholarx_papers")


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("ScholarX — Fetching Top 5 AI Papers from arXiv")
    print("=" * 70)

    # Initialize client with only arXiv enabled
    client = ScholarXClient(
        sources=[PaperSource.ARXIV],
        storage_dir=str(OUTPUT_DIR / "pdfs"),
    )

    # Search for latest AI papers
    query = SearchQuery(
        query="artificial intelligence",
        sources=[PaperSource.ARXIV],
        categories=["cs.AI"],
        max_results=5,
        sort_by="date",
    )

    print("\n🔍 Searching arXiv for cs.AI papers...")
    result = await client.search(query)

    print(f"\n📊 Results: {result.total_count} papers found, {result.deduplicated_count} deduplicated")
    print(f"   Sources queried: {[s.value for s in result.sources_queried]}")

    if result.sources_failed:
        print(f"   ⚠️  Failed sources: {result.sources_failed}")

    if not result.papers:
        print("\n❌ No papers found. Exiting.")
        return

    # Save metadata
    papers_meta = []
    for i, paper in enumerate(result.papers[:5], 1):
        print(f"\n{'─' * 60}")
        print(f"  Paper {i}: {paper.title}")
        print(
            f"  Authors: {', '.join(paper.authors[:3])}"
            + (f" +{len(paper.authors) - 3} more" if len(paper.authors) > 3 else "")
        )
        print(f"  Date: {paper.published_date}")
        print(f"  Categories: {', '.join(paper.categories[:5])}")
        print(f"  URL: {paper.url}")
        print(f"  PDF: {paper.pdf_url}")
        if paper.abstract:
            abstract_preview = paper.abstract[:200] + "..." if len(paper.abstract) > 200 else paper.abstract
            print(f"  Abstract: {abstract_preview}")

        papers_meta.append(paper.model_dump(exclude={"normalized_title", "normalized_authors"}))

    # Save metadata JSON
    meta_path = OUTPUT_DIR / "papers_metadata.json"
    meta_path.write_text(json.dumps(papers_meta, indent=2, default=str))
    print(f"\n\n💾 Metadata saved to: {meta_path}")

    # Save individual paper text files (for comparative analysis)
    for i, paper in enumerate(result.papers[:5], 1):
        paper_file = OUTPUT_DIR / f"paper_{i}.md"
        content = f"""# {paper.title}

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
"""
        paper_file.write_text(content)
        print(f"📄 Saved paper {i} markdown: {paper_file}")

    # Download PDFs
    print("\n📥 Downloading PDFs...")
    for i, paper in enumerate(result.papers[:5], 1):
        try:
            path = await client.download_paper(paper)
            if path:
                print(f"  ✅ Paper {i} PDF downloaded: {path}")
            else:
                print(f"  ⚠️  Paper {i} PDF download failed (no path returned)")
        except Exception as e:
            print(f"  ❌ Paper {i} PDF download error: {e}")

    print(f"\n{'=' * 70}")
    print(f"✅ Done! All outputs saved to: {OUTPUT_DIR}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(main())
