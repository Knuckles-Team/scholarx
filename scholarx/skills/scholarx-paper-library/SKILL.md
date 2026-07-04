---
name: scholarx-paper-library
description: >-
  Full-text PDF download and offline library management via the scholarx MCP
  server — fetch a paper's PDF, bulk-queue downloads, download straight from an
  arXiv id/URL, and list/stat the local store. Use when the agent needs the
  actual PDF bytes of a paper (not just metadata) or must inspect what is already
  stored. Each successful download is also stored as a durable :MediaAsset blob
  in the knowledge graph. Do NOT use to search/discover papers (use
  scholarx-paper-search) or to push typed paper nodes into the KG (use
  scholarx-kg-ingestion).
license: MIT
tags: [scholarx, research, papers, pdf, storage, mcp]
metadata:
  author: Genius
  version: '0.1.0'
---
# ScholarX Paper Library

Download full-text PDFs and manage the local offline store. Slow/large downloads
that exceed the inline budget are handed to a background queue and polled by
`job_id`. Every completed download is additionally ingested into the knowledge
graph as a content-addressed PDF blob (`:MediaAsset`), best-effort.

## When to use
- Download one paper's PDF by `source` + `paper_id` (`download`).
- Download directly from an arXiv id or abs/pdf URL, bypassing the API (`download_url`).
- Bulk-queue several papers for background download (`bulk_download`).
- List locally stored papers + storage stats (`stored`).
- Poll a queued download (`status`) or view the queue (`queue`).

## When NOT to use
- Finding papers / metadata lookups → `scholarx-paper-search`.
- Ingesting papers as typed `:Paper` graph nodes → `scholarx-kg-ingestion`.

## Prerequisites & environment
Connect via the `mcp-client` skill against the **`scholarx`** MCP server. PDFs
are written under the shared research dir (`<research_dir>/papers`); the KG blob
ingestion no-ops when no epistemic-graph engine is reachable.

| Variable | Required | Notes |
|----------|----------|-------|
| `MCP_TOOL_MODE` | optional | `condensed` \| `verbose` \| `both` |

## Tools & actions
| Tool | Actions |
|------|---------|
| `sx_storage` | `download`, `download_url`, `bulk_download`, `stored`, `status`, `queue` |

### Key parameters
- `source` — paper source (`arxiv`, `pmc`, …); required with `paper_ids` for `download`/`bulk_download`.
- `paper_ids` — comma-separated ids (or arXiv ids/URLs for `download_url`).
- `job_id` — required for `status`.

## Recipes
Download one arXiv paper (inline, or queued if slow):
```
sx_storage action=download source=arxiv paper_ids=2603.09022
```
Download straight from arXiv URLs, no API round-trip:
```
sx_storage action=download_url paper_ids="https://arxiv.org/abs/2603.09022,2601.01234"
```
Bulk-queue several PMC papers, then poll one:
```
sx_storage action=bulk_download source=pmc paper_ids="PMC10000001,PMC10000002"
sx_storage action=status job_id=<job_id>
```
List what is stored locally:
```
sx_storage action=stored
```

## Gotchas
- `download` bounds the inline fetch (~60 s); slower ones return `status="queued"`
  with a `job_id` — poll with `action=status`.
- `download_url` is arXiv-only and strips version suffixes for the local filename
  (keeps them for the fetch URL).
- Already-present PDFs short-circuit to `status="already_exists"` (idempotent).
- KG blob ingestion is best-effort — a missing engine never fails the download.

## Related
- **Search / discovery:** `scholarx-paper-search`.
- **Typed-node KG ingestion:** `scholarx-kg-ingestion`.
