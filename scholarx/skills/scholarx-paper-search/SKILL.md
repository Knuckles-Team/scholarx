---
name: scholarx-paper-search
skill_type: skill
description: >-
  Federated paper search via the scholarx MCP server: one query across arXiv, PMC, bioRxiv, medRxiv, PsyArXiv, OSF and Semantic Scholar with deduplication. Use to find papers by topic, look up one paper by id, list an author's papers or pull recent ones. Not for PDFs (scholarx-paper-library) or KG ingest (scholarx-kg-ingestion).
license: MIT
tags: [scholarx, research, papers, arxiv, search, mcp]
metadata:
  author: Knuckles-Team
  version: '0.1.0'
---
# ScholarX Paper Search

Scope: Federated research-paper search via the scholarx MCP server — one query fanned out across arXiv, PMC, bioRxiv, medRxiv, PsyArXiv, OSF and Semantic Scholar, with cross-source deduplication. Use when the agent must find papers by topic/keyword, look up one paper by source + id, list an author's papers, or pull recent publications in a category. Do NOT use to download full PDFs or manage the offline library (use scholarx-paper-library) or to push papers into the knowledge graph (use scholarx-kg-ingestion).

Federated discovery across every configured research source through one
deduplicated tool surface. Prefer these tools over hitting arXiv/PMC/etc.
directly — the client fans out concurrently, normalizes titles/authors, and
removes cross-source duplicates for you.

## When to use
- Search papers by topic/keyword across all (or selected) sources.
- Fetch one paper by its source-native id (`get`).
- List a specific author's papers (`author`).
- Pull recently published papers in a set of categories (`recent`).
- Enumerate available sources / categories (`sx_info_sources`, `sx_info_categories`).

## When NOT to use
- Downloading full-text PDFs or managing the offline store → `scholarx-paper-library`.
- Ingesting papers as typed nodes/blobs into the KG → `scholarx-kg-ingestion`.
- General open-web / social search (not papers) → `pulselink-mcp`.

## Prerequisites & environment
Connect via the `mcp-client` skill against the **`scholarx`** MCP server. No API
key is required for the default sources; optional keys raise rate limits.

| Variable | Required | Notes |
|----------|----------|-------|
| `NCBI_API_KEY` | optional | Raises PMC/NCBI limit (3/s → 10/s) |
| `S2_API_KEY` | optional | Semantic Scholar API key |
| `OSF_TOKEN` | optional | OSF / PsyArXiv token |

## Steps

1. Check which sources are live by calling `sx_info_sources`. Verify each source you need reports as enabled.
2. Search by topic by calling `sx_search_search` with `query`, `sources`, `max_results` and optionally `sort_by`. Verify the result lists papers and reports a `deduplicated_count`.
3. Look up one paper by calling `sx_search_get` with a single `sources` value and `paper_id`. Verify the returned title and authors match the intended paper.
4. For an author or recent sweep, call `sx_search_author` with `author`, or `sx_search_recent` with `categories` and `days`. Verify results fall in the requested window or author.
5. Follow citations by calling `sx_search_citations` for the chosen paper. Verify the citing papers list is returned.

## Failure recovery

| Failure | Cause | Recovery |
|---------|-------|----------|
| `sx_search_get` returns an error | `sources` held several values or `paper_id` was missing | Pass exactly one source in `sources` and the source-native `paper_id` |
| Search is slow or partly empty | arXiv rate limit or a source is down | Check `sx_info_sources`, narrow `sources`, or set `NCBI_API_KEY` or `S2_API_KEY` to raise limits |
| Zero results | Query too narrow or category filter wrong | Broaden `query`, and list valid filters with `sx_info_categories` before retrying with a new `categories` value |

## Tools
| Tool | Purpose |
|------|---------|
| `sx_search_search` | Search papers across sources with filters. |
| `sx_search_get` | Retrieve one paper by source and id. |
| `sx_search_author` | Search papers by author name. |
| `sx_search_citations` | List papers that cite a given paper. |
| `scholarx_get_citing_papers` | List papers that cite a given paper (client operation). |
| `sx_search_recent` | Papers published in recent days for categories. |
| `sx_info_sources` | Status of every configured source. |
| `sx_info_categories` | Categories each source offers. |
| `sx_enabled_sources` | Sources enabled on this server. |
| `scholarx_search` | Search with a full search-query object. |
| `scholarx_get_paper` | Retrieve a paper from one source. |
| `scholarx_get_recent_papers` | Recent papers for categories. |
| `scholarx_get_source_status` | Status of all configured sources. |
| `scholarx_list_categories` | Categories per source. |
| `scholarx_enabled_sources` | Enabled sources. |

### Key parameters
- `query` - free-text search string (for `sx_search_search`).
- `sources` — comma-separated (`arxiv,pmc,biorxiv,medrxiv,psyarxiv,osf,semantic_scholar`); empty = all.
- `categories` — comma-separated filters (e.g. `cs.AI,cs.MA`); also seeds `recent`.
- `paper_id` — source-native id; required with `sources` for `get`.
- `author` — author name (required for `author`).
- `days` — look-back window for `recent` (1–30).
- `max_results` — per-query cap (1–100).

## Recipes
Search multi-agent papers on arXiv + Semantic Scholar, newest first:
```
sx_search_search query="multi-agent reinforcement learning" sources="arxiv,semantic_scholar" sort_by=date max_results=25
```
Get one arXiv paper by id:
```
sx_search_get sources=arxiv paper_id=2603.09022
```
Recent cs.AI / cs.MA preprints from the last 2 days:
```
sx_search_recent categories="cs.AI,cs.MA" days=2
```

## Gotchas
- arXiv is polite-rate-limited (~1 req / 3 s); large fan-outs take a few seconds.
- `get` needs **both** a single `sources` value and `paper_id`.
- Results are already deduplicated across sources — `deduplicated_count` reports
  how many duplicates were collapsed.
- `recent` defaults to `cs.AI, cs.MA, cs.SE, cs.LG` when no categories are given.

## Related
- **Downloads / offline library:** `scholarx-paper-library`.
- **Native KG ingestion:** `scholarx-kg-ingestion` (search results are also
  auto-ingested as typed `:Paper` nodes best-effort when an engine is reachable).
