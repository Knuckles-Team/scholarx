---
name: scholarx-paper-library
skill_type: skill
description: >-
  Download full-text PDFs and manage the offline store via the scholarx MCP server: fetch a paper PDF, queue bulk downloads, download from an arXiv id or URL, and list stored papers. Use when the PDF itself is needed. Not for search (scholarx-paper-search) or typed KG ingest (scholarx-kg-ingestion).
license: MIT
tags: [scholarx, research, papers, pdf, storage, mcp]
metadata:
  author: Knuckles-Team
  version: '0.1.0'
---
# ScholarX Paper Library

Scope: Full-text PDF download and offline library management via the scholarx MCP server — fetch a paper's PDF, bulk-queue downloads, download straight from an arXiv id/URL, and list/stat the local store. Use when the agent needs the actual PDF bytes of a paper (not just metadata) or must inspect what is already stored. Each successful download is also stored as a durable :MediaAsset blob in the knowledge graph. Do NOT use to search/discover papers (use scholarx-paper-search) or to push typed paper nodes into the KG (use scholarx-kg-ingestion).

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
ingestion no-ops when no medulla engine is reachable.

| Variable | Required | Notes |
|----------|----------|-------|

## Steps

1. Check what is already stored by calling `sx_storage_stored`. Verify the paper you need is not listed, to avoid a redundant download.
2. Download one paper by calling `sx_storage_download` with `source` and `paper_ids`, or `sx_storage_download_url` for arXiv ids and URLs. Verify the response `status` is a completed download or `already_exists`.
3. For many papers, call `sx_storage_bulk_download` with `source` and `paper_ids`. Verify the response returns a `job_id`.
4. Poll a queued job by calling `sx_storage_status` with `job_id`. Verify the status reaches completed, or inspect all jobs with `sx_storage_queue`.
5. Confirm the PDFs landed by calling `sx_storage_stored` again. Verify the storage statistics count increased.

## Failure recovery

| Failure | Cause | Recovery |
|---------|-------|----------|
| Response has `status` queued | Download exceeded the inline time budget | Poll `sx_storage_status` with the returned `job_id` until it completes |
| `sx_storage_download_url` rejects an id | The tool is arXiv-only | Use `sx_storage_download` with the right `source` and `paper_ids` instead |
| Job status shows failed | Source unreachable or paper has no open PDF | Check the source with `sx_info_sources`, then re-queue with `sx_storage_bulk_download` for a different `source` if available |

## Tools
| Tool | Purpose |
|------|---------|
| `sx_storage_download` | Download one paper's PDF inline, queueing it when the source is slow. |
| `sx_storage_download_url` | Download arXiv PDFs by id or URL within a bounded wall time. |
| `sx_storage_bulk_download` | Queue many papers from one source for background download. |
| `sx_download_papers` | Download many papers from one source in parallel. |
| `sx_download_urls` | Download arXiv PDFs by id or URL in parallel. |
| `sx_storage_stored` | List locally stored papers and storage statistics. |
| `sx_storage_status` | Status of one queued download by `job_id`. |
| `sx_storage_queue` | Every queued background download. |
| `scholarx_download_paper` | Download one paper object synchronously. |
| `scholarx_download_papers` | Download paper objects in parallel with bounded concurrency. |
| `scholarx_download_urls` | Download arXiv PDFs by id or URL with bounded concurrency. |
| `scholarx_queue_download` | Queue a paper for background download. |
| `scholarx_get_download_status` | Status of a queued job. |
| `scholarx_get_queue_status` | Status of all queued downloads. |

### Key parameters
- `source` - paper source (`arxiv`, `pmc`, ...); required with `paper_ids` for downloads.
- `paper_ids` - comma-separated ids (or arXiv ids/URLs for the URL tools).
- `job_id` - required for `sx_storage_status`.

## Recipes
Download one arXiv paper (inline, or queued if slow): `sx_storage_download` with `source=arxiv`, `paper_ids=2603.09022`.

Download straight from arXiv URLs: `sx_storage_download_url` with `paper_ids="https://arxiv.org/abs/2603.09022,2601.01234"`.

Bulk-queue PMC papers, then poll: `sx_storage_bulk_download` with `source=pmc`, `paper_ids="PMC10000001,PMC10000002"`, then `sx_storage_status` with `job_id=<job_id>`.

List what is stored locally: `sx_storage_stored`.

## Gotchas
- `download` bounds the inline fetch (~60 s); slower ones return `status="queued"`
  with a `job_id` — poll with `sx_storage_status`.
- `download_url` is arXiv-only and strips version suffixes for the local filename
  (keeps them for the fetch URL).
- Already-present PDFs short-circuit to `status="already_exists"` (idempotent).
- KG blob ingestion is best-effort — a missing engine never fails the download.

## Related
- **Search / discovery:** `scholarx-paper-search`.
- **Typed-node KG ingestion:** `scholarx-kg-ingestion`.
