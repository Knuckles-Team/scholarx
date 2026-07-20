# Scholarx Paper Search

Federated research-paper search via the scholarx MCP server — one query fanned out across arXiv, PMC, bioRxiv, medRxiv, PsyArXiv, OSF and Semantic Scholar, with cross-source deduplication. Use when the agent must find papers by topic/keyword, look up one paper by source + id, list an author's papers, or pull recent publications in a category. Do NOT use to download full PDFs or manage the offline library (use scholarx-paper-library) or to push papers into the knowledge graph (use scholarx-kg-ingestion).

# ScholarX Paper Search

Federated discovery across every configured research source through one
deduplicated tool surface. Prefer these tools over hitting arXiv/PMC/etc.
directly — the client fans out concurrently, normalizes titles/authors, and
removes cross-source duplicates for you.

## When to use
- Search papers by topic/keyword across all (or selected) sources.
- Fetch one paper by its source-native id (`get`).
- List a specific author's papers (`author`).
- Pull recently published papers in a set of categories (`recent`).
- Enumerate available sources / categories (`sx_info`).

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
| `MCP_TOOL_MODE` | optional | `condensed` \| `verbose` \| `both` |

## Tools & actions
| Tool | Actions |
|------|---------|
| `sx_search` | `search`, `get`, `author`, `recent` |
| `sx_info` | `sources`, `categories` |

### Key parameters
- `query` — free-text search string (for `search`).
- `sources` — comma-separated (`arxiv,pmc,biorxiv,medrxiv,psyarxiv,osf,semantic_scholar`); empty = all.
- `categories` — comma-separated filters (e.g. `cs.AI,cs.MA`); also seeds `recent`.
- `paper_id` — source-native id; required with `sources` for `get`.
- `author` — author name (required for `author`).
- `days` — look-back window for `recent` (1–30).
- `max_results` — per-query cap (1–100).

## Recipes
Search multi-agent papers on arXiv + Semantic Scholar, newest first:
```
sx_search action=search query="multi-agent reinforcement learning" sources="arxiv,semantic_scholar" sort_by=date max_results=25
```
Get one arXiv paper by id:
```
sx_search action=get sources=arxiv paper_id=2603.09022
```
Recent cs.AI / cs.MA preprints from the last 2 days:
```
sx_search action=recent categories="cs.AI,cs.MA" days=2
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
