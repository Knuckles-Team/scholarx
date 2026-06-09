# Usage — MCP / API / CLI

`scholarx` exposes the same capability three ways: as **MCP tools** an agent calls, as
a **Python API** (`ScholarXClient`) you import, and as a **CLI**. The full tool surface
and ecosystem role are described in [Overview](overview.md).

## As an MCP server

Once [deployed](deployment.md), the server registers three action-routed tool modules.
Each is togglable so you can keep the surface compact for an LLM context.

| Module | Toggle | Actions |
|---|---|---|
| `search` | `SEARCHTOOL` | `search`, `get`, `author`, `recent` |
| `discovery` | `DISCOVERYTOOL` | `sources`, `categories` |
| `storage` | `STORAGETOOL` | `download`, `download_url`, `bulk_download`, `queue`, `status`, `stored` |

Example agent prompts that map onto these tools:

- *"Search every source for recent papers on multi-agent orchestration"* → `search` (`search`)
- *"List the categories available on arXiv"* → `discovery` (`categories`)
- *"Download the PDF for arXiv paper `2401.00001` and store it"* → `storage` (`download`)

Two analysis prompts ship with the server: `agent_utilities_enhancement_scan` and
`biomimicry_innovation_scan`.

## As a Python API

`ScholarXClient` is the unified async client. It fans a `SearchQuery` out to every
provider in parallel, applies per-source rate limiting, then merges and deduplicates
the results into a `SearchResult`.

```python
import asyncio
from scholarx.api_client import ScholarXClient
from scholarx.models import SearchQuery

async def main():
    client = ScholarXClient()

    # Search across all sources at once
    result = await client.search(SearchQuery(
        query="multi-agent orchestration",
        categories=["cs.AI", "cs.MA"],
        max_results=10,
    ))

    for paper in result.papers:
        print(f"[{paper.source}] {paper.title}")
        print(f"  authors: {', '.join(paper.authors[:3])}")
        print(f"  doi: {paper.doi}")

    # Download the first result's full PDF to the local store
    if result.papers:
        path = await client.download_paper(result.papers[0])
        print(f"stored at: {path}")

asyncio.run(main())
```

Results are deduplicated across sources by DOI, then cross-identifier mapping, then a
fuzzy title and first-author match, so a paper that appears on both arXiv and Semantic
Scholar is collapsed into a single record.

## As a CLI

The `scholarx` console script wraps the same client with a Rich progress UI. It scores
each result against a weighted relevance taxonomy and reports the local paper library.

```bash
# Scan for recent papers and score relevance
scholarx scan --query "multi-agent systems" --output-dir ./papers

# Restrict to specific arXiv categories and cap the result count
scholarx scan --categories cs.AI,cs.LG,cs.CL --max-results 50 --output-dir ./papers

# Use a custom relevance taxonomy, and auto-trigger comparative analysis
scholarx scan --query "knowledge graphs" --taxonomy custom_taxonomy.json --output-dir ./papers
scholarx scan --analyze --output-dir ./papers

# Show the stored paper library
scholarx status
```

The authenticated sources (OSF / PsyArXiv, and the rate-limit boosts for Semantic
Scholar and PubMed Central) read their credentials from the environment
(`OSF_TOKEN`, `S2_API_KEY`, `NCBI_API_KEY`) and remain inactive when those credentials
are absent.
