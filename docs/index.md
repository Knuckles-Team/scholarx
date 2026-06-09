# scholarx

Universal Research Paper **API + MCP Server + Agent** for the agent-utilities
ecosystem — one entry point for arXiv, PubMed Central, bioRxiv, medRxiv, PsyArXiv,
OSF, and Semantic Scholar.

!!! info "Official documentation"
    This site is the canonical reference for `scholarx`, maintained alongside every
    release.

[![PyPI](https://img.shields.io/pypi/v/scholarx)](https://pypi.org/project/scholarx/)
![MCP Server](https://badge.mcpx.dev?type=server 'MCP Server')
[![License](https://img.shields.io/pypi/l/scholarx)](https://github.com/Knuckles-Team/scholarx/blob/main/LICENSE)
[![GitHub](https://img.shields.io/badge/source-GitHub-181717?logo=github)](https://github.com/Knuckles-Team/scholarx)

## Overview

`scholarx` is a single, deduplicated interface across **seven** preprint and academic
repositories. It fans a query out to every source in parallel, merges and
deduplicates the results, downloads full PDFs, and ingests them into the
epistemic-graph Knowledge Graph. The capability is exposed three ways:

- **`ScholarXClient`** — a unified async Python client that fans out to all providers,
  applies per-source rate limiting, and returns merged, deduplicated `SearchResult`
  records.
- **Action-routed MCP tools** — `search`, `discovery`, and `storage` tool modules,
  each togglable, that keep the tool surface compact for LLM contexts.
- **A Pydantic-AI graph agent** (`scholarx-agent`) for autonomous, multi-step research
  workflows over the Agent Control Protocol and the Agent Web UI.

Deduplication is three-tier — DOI exact match, cross-identifier mapping, then fuzzy
title and first-author matching — so the same paper appearing across multiple sources
is collapsed into one record.

## Explore the documentation

<div class="grid cards" markdown>

- :material-rocket-launch: **[Installation](installation.md)** — pip, source, extras, and the prebuilt Docker image.
- :material-server-network: **[Deployment](deployment.md)** — run the MCP server and the agent, Docker Compose, Caddy + Technitium.
- :material-console: **[Usage](usage.md)** — the MCP tools, the `ScholarXClient` API, and the `scholarx` CLI.
- :material-sitemap: **[Overview](overview.md)** — ecosystem role, enterprise readiness, and architecture.
- :material-tag-multiple: **[Concepts](concepts.md)** — the `CONCEPT:SX-*` registry.
- :material-file-document-multiple: **[Coverage Report](scholarx_coverage_report.md)** — per-source coverage and verification.

</div>

## Quick start

```bash
pip install "scholarx[mcp]"
scholarx-mcp                     # stdio MCP server (default transport)
```

Run a research scan from the CLI, or start the HTTP server:

```bash
scholarx scan --query "multi-agent orchestration" --output-dir ./papers
scholarx-mcp --transport streamable-http --host 0.0.0.0 --port 8004
```

See **[Installation](installation.md)** and **[Deployment](deployment.md)** for the
full matrix (PyPI extras, Docker image, all transports, the agent server, reverse
proxy, DNS).
