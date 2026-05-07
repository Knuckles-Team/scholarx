# ScholarX 📚 - API | MCP | AgentOS

![PyPI - Version](https://img.shields.io/pypi/v/scholarx)
![MCP Server](https://badge.mcpx.dev?type=server 'MCP Server')
![PyPI - Downloads](https://img.shields.io/pypi/dd/scholarx)
![GitHub Repo stars](https://img.shields.io/github/stars/Knuckles-Team/scholarx)
![GitHub forks](https://img.shields.io/github/forks/Knuckles-Team/scholarx)
![GitHub contributors](https://img.shields.io/github/contributors/Knuckles-Team/scholarx)
![PyPI - License](https://img.shields.io/pypi/l/scholarx)
![GitHub](https://img.shields.io/github/license/Knuckles-Team/scholarx)

![GitHub last commit (by committer)](https://img.shields.io/github/last-commit/Knuckles-Team/scholarx)
![GitHub pull requests](https://img.shields.io/github/issues-pr/Knuckles-Team/scholarx)
![GitHub closed pull requests](https://img.shields.io/github/issues-pr-closed/Knuckles-Team/scholarx)
![GitHub issues](https://img.shields.io/github/issues/Knuckles-Team/scholarx)

![GitHub top language](https://img.shields.io/github/languages/top/Knuckles-Team/scholarx)
![GitHub language count](https://img.shields.io/github/languages/count/Knuckles-Team/scholarx)
![GitHub repo size](https://img.shields.io/github/repo-size/Knuckles-Team/scholarx)
![GitHub repo file count (file type)](https://img.shields.io/github/directory-file-count/Knuckles-Team/scholarx)
![PyPI - Wheel](https://img.shields.io/pypi/wheel/scholarx)
![PyPI - Implementation](https://img.shields.io/pypi/implementation/scholarx)

*Version: 1.8.0*

**Universal Research Paper API** — a single entry point for querying, downloading, and ingesting research papers from all major preprint and academic repositories.

Version: 0.5.0

## Overview

ScholarX provides a unified interface to search across **7 paper sources** simultaneously, with automatic cross-source deduplication, full PDF downloads, and Knowledge Graph integration. It is registered as an **Agent OS subsystem** in the genius-agent ecosystem.

### Supported Sources

| Source | API | Auth | Rate Limit |
|--------|-----|------|------------|
| **arXiv** | Atom/OpenSearch | Free | 1 req/3s |
| **PubMed Central** | NCBI E-utilities | Optional `NCBI_API_KEY` | 3 req/s (10 with key) |
| **bioRxiv** | bioRxiv REST | Free | 1 req/s |
| **medRxiv** | bioRxiv REST | Free | 1 req/s |
| **PsyArXiv** | OSF v2 | `OSF_TOKEN` | 1 req/s |
| **OSF** | OSF v2 | `OSF_TOKEN` | 1 req/s |
| **Semantic Scholar** | Academic Graph v1 | Optional `S2_API_KEY` | 100 req/min |

### Key Features

- **Unified Search** — Single `SearchQuery` model works across all sources
- **3-Tier Deduplication** — DOI exact match → cross-ID mapping → fuzzy title+author (Levenshtein ≥ 0.90)
- **Full Paper Download** — Download and store complete PDFs locally (`~/.scholarx/papers/`)
- **Knowledge Graph Integration** — Ingest papers via existing `KBIngestionEngine` (ArticleNode, SourceNode, PersonNode)
- **RLM Auto-Trigger** — Large papers (>50K chars) automatically route through Recursive Language Model decomposition
- **Per-Source Rate Limiting** — Token-bucket rate limiter in the abstract provider base class
- **Configurable Watchlists** — Register custom research topics as MaintenanceCron tasks

## Installation

```bash
# Core (API client only)
pip install scholarx

# With MCP server
pip install scholarx[mcp]

# With agent server
pip install scholarx[agent]

# Everything
pip install scholarx[all]
```

## Quick Start

### Python API

```python
import asyncio
from scholarx.api_client import ScholarXClient
from scholarx.models import SearchQuery, PaperSource

async def main():
    client = ScholarXClient()

    # Search across all sources
    result = await client.search(SearchQuery(
        query="multi-agent orchestration",
        categories=["cs.AI", "cs.MA"],
        max_results=10,
    ))

    for paper in result.papers:
        print(f"[{paper.source}] {paper.title}")
        print(f"  Authors: {', '.join(paper.authors[:3])}")
        print(f"  DOI: {paper.doi}")
        print()

    # Download a paper
    if result.papers:
        path = await client.download_paper(result.papers[0])
        print(f"Downloaded to: {path}")

asyncio.run(main())
```

### CLI

ScholarX includes a rich CLI with progress bars for paper discovery, relevance scoring, and PDF downloads.

```bash
# Scan for recent AI papers across 7 CS categories
scholarx scan --query "artificial intelligence" --output-dir ./papers

# Customize categories and result count
scholarx scan --categories cs.AI,cs.LG,cs.CL --max-results 30 --output-dir ./papers

# Use a custom relevance taxonomy
scholarx scan --query "knowledge graphs" --taxonomy custom_taxonomy.json --output-dir ./papers

# Auto-trigger comparative analysis on high-confidence papers
scholarx scan --analyze --output-dir ./papers

# Show stored paper library status
scholarx status
```

#### Relevance Scoring

The CLI scores each paper's abstract against a 9-domain weighted keyword taxonomy:

| Domain | Weight | Focus |
|--------|--------|-------|
| Orchestration | 3.0 | Multi-agent, workflow, task decomposition |
| Knowledge Graph | 3.0 | Ontology, OWL, entity relations, graph reasoning |
| Planning & Reasoning | 2.5 | Chain-of-thought, MCTS, deliberation |
| Memory & Retrieval | 2.5 | RAG, episodic memory, continual learning |
| Tool Use | 2.0 | Function calling, MCP, code generation |
| Evaluation & Safety | 2.0 | Benchmarks, red teaming, hallucination |
| Swarm & Evolution | 2.0 | Evolutionary methods, stigmergy, biomimicry |
| LLM Architecture | 1.5 | Transformers, MoE, distillation |
| Human-AI | 1.0 | Human-in-the-loop, decision support |

Papers are classified into three tiers:
- **✅ Relevant** (score ≥ 3.0) — Direct value for the target domain
- **🟡 Marginal** (score 1.0–2.9) — Potential indirect value
- **❌ Irrelevant** (score < 1.0) — Filtered out

#### Deduplication

ScholarX prevents duplicate downloads through two mechanisms:

1. **Cross-source deduplication** (`deduplication.py`): 3-tier matching removes duplicates when the same paper appears across multiple sources:
   - **Tier 1**: DOI exact match
   - **Tier 2**: Cross-ID mapping (arXiv ID ↔ S2 corpus ID via metadata)
   - **Tier 3**: Normalized title + first-author last name (Levenshtein ≥ 0.90)

2. **Storage deduplication** (`paper_storage.py`): Before downloading, `PaperStorage.download_paper()` checks if the paper ID's metadata hash already exists in `~/.scholarx/papers/.metadata/`. Already-downloaded papers are skipped instantly.

### MCP Server

```bash
# Start in stdio mode (for agent integration)
scholarx-mcp --transport stdio

# Start in HTTP mode
scholarx-mcp --transport streamable-http --host 0.0.0.0 --port 9600
```

### MCP Tools

| Tool | Description |
|------|-------------|
| `search_papers` | Multi-source search with deduplication |
| `get_paper` | Single paper by source + ID |
| `search_by_author` | Author-based search |
| `get_recent_papers` | Papers from last N days |
| `list_sources` | Available sources and status |
| `list_categories` | Categories per source |
| `download_paper` | Download full PDF |
| `get_stored_papers` | List locally stored papers |

### MCP Prompts

| Prompt | Purpose |
|--------|---------|
| `agent_utilities_enhancement_scan` | Scan CS/AI papers for AU concept enhancement opportunities |
| `biomimicry_innovation_scan` | Scan biology papers for biomimetic agent patterns |

## Docker

```bash
# Build and run
docker compose up -d

# Debug mode (mounts local source)
docker compose -f compose.yml up --build
```

## Environment Variables

```bash
# API Keys (all optional for basic functionality)
OSF_TOKEN=              # OSF/PsyArXiv API token
S2_API_KEY=             # Semantic Scholar (higher rate limits)
NCBI_API_KEY=           # PubMed Central (higher rate limits)

# MCP Server
TRANSPORT=stdio         # stdio | streamable-http
HOST=0.0.0.0
PORT=9600

# Tool Toggles
SEARCHTOOL=True
DISCOVERYTOOL=True
STORAGETOOL=True

# Paper Storage
SCHOLARX_STORAGE_DIR=   # Default: ~/.scholarx/papers/
```

## Architecture

```
User/Agent
    │
    ▼
┌─────────────────────────┐
│  ScholarX MCP Server    │  12 tools + prompts
│  (mcp_server.py)        │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  ScholarXClient         │  Unified API
│  (api_client.py)        │
└────────┬────────────────┘
         │
    ┌────┼────┬────┬────┬────┬────┐
    ▼    ▼    ▼    ▼    ▼    ▼    ▼
  arXiv PMC bioRx medRx PsyAr OSF  S2    ← Per-source rate limiting
    │    │    │    │    │    │    │
    └────┴────┴────┴────┴────┴────┘
         │
         ▼
┌─────────────────────────┐
│  Deduplication Engine   │  DOI → cross-ID → fuzzy title
│  (deduplication.py)     │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Paper Storage          │  Full PDF download
│  (~/.scholarx/papers/)  │
│         │               │
│         ▼               │
│  KBIngestionEngine      │  → ArticleNode + PersonNode
│  (KG auto-ingest)       │     + SourceNode + KBConceptNode
│         │               │
│    RLM (AU-007)         │  Auto-triggers for >50K char papers
└─────────────────────────┘
```

## Agent OS Subsystem

ScholarX is registered as an Agent OS subsystem alongside:

| Subsystem | Role |
|-----------|------|
| `container-manager-mcp` | Infrastructure provisioning |
| `systems-manager` | Host/OS operations |
| `tunnel-manager` | Network tunneling |
| `repository-manager` | Git/repo operations |
| **`scholarx`** | **Research intelligence** |

## Maintenance Cron

A `SIX_HOURLY` maintenance task (`scholarx_paper_discovery`) automatically:
1. Checks for new papers across configured categories
2. Evaluates relevance to Knowledge Graph concepts
3. Ingests high-relevance papers (score > 0.6)
4. Produces actionable research digests

Custom watchlists can be added via `MaintenanceCron.add_task()` or the `create_research_watchlist` MCP tool.

## License

MIT


## MCP Configuration Examples

### 1. Standard IO (stdio) Deployment

```json
{
  "mcpServers": {
    "scholarx": {
      "command": "uv",
      "args": [
        "run",
        "scholarx-mcp"
      ],
      "env": {
        "AGENT_DESCRIPTION": "<YOUR_AGENT_DESCRIPTION>",
        "AGENT_SYSTEM_PROMPT": "<YOUR_AGENT_SYSTEM_PROMPT>",
        "DEFAULT_AGENT_NAME": "<YOUR_DEFAULT_AGENT_NAME>",
        "DISCOVERYTOOL": "True",
        "SEARCHTOOL": "True",
        "STORAGETOOL": "True"
      }
    }
  }
}
```

### 2. Streamable HTTP (SSE) Deployment

```json
{
  "mcpServers": {
    "scholarx": {
      "command": "uv",
      "args": [
        "run",
        "scholarx-mcp",
        "--transport",
        "http",
        "--host",
        "0.0.0.0",
        "--port",
        "8000"
      ],
      "env": {
        "AGENT_DESCRIPTION": "<YOUR_AGENT_DESCRIPTION>",
        "AGENT_SYSTEM_PROMPT": "<YOUR_AGENT_SYSTEM_PROMPT>",
        "DEFAULT_AGENT_NAME": "<YOUR_DEFAULT_AGENT_NAME>",
        "DISCOVERYTOOL": "True",
        "SEARCHTOOL": "True",
        "STORAGETOOL": "True"
      }
    }
  }
}
```
