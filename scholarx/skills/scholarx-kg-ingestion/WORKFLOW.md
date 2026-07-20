# Scholarx Kg Ingestion

Native epistemic-graph ingestion of research papers via the scholarx MCP server — fetch papers and push them into the knowledge graph as typed :Paper nodes with their :PaperSource, :ResearchCategory and :Person (author) nodes and links, plus full-text PDFs as :AssetOccurrence blobs. Use when the agent must persist papers into the KG for later graph/semantic queries or build a research corpus. Do NOT use for plain search/metadata lookups (use scholarx-paper-search) or for downloading PDFs to disk without KG persistence (use scholarx-paper-library).

# ScholarX Knowledge-Graph Ingestion

Push fetched papers natively into the ONE epistemic-graph as typed OWL nodes. A
`:Paper` carries its abstract as searchable `text` (the document modality), links
to its `:PaperSource`, `:ResearchCategory` and `:Person` authors, and — once its
PDF is downloaded — to a `:AssetOccurrence` PDF blob via `:hasFullText`. All writes are
best-effort and no-op cleanly when no engine is reachable.

## When to use
- Persist a search's worth of papers into the KG as typed `:Paper` nodes (`scholarx_ingest_papers`).
- Build a durable, queryable research corpus for later graph/semantic queries.
- Ensure authors/sources/categories are materialized as linked graph nodes.

## When NOT to use
- One-off metadata lookups with no persistence → `scholarx-paper-search`.
- Downloading PDFs to disk without needing KG nodes → `scholarx-paper-library`
  (though it still ingests the PDF blob best-effort).

## Prerequisites & environment
Connect via the `mcp-client` skill against the **`scholarx`** MCP server. Native
ingestion targets a reachable epistemic-graph engine (the `GraphComputeEngine`
fast client); with no engine present every ingestion path silently no-ops.

| Variable | Required | Notes |
|----------|----------|-------|
| `NCBI_API_KEY` / `S2_API_KEY` / `OSF_TOKEN` | optional | Raise per-source fetch limits |
| `MCP_TOOL_MODE` | optional | `condensed` \| `verbose` \| `both` |

## Tools & actions
| Tool | Purpose |
|------|---------|
| `scholarx_ingest_papers` | Search + push results as typed `:Paper` nodes into the KG |

Search (`sx_search`) and download (`sx_storage action=download`) **also** ingest
best-effort automatically — this tool is the explicit, parameterized entry point.

### Key parameters
- `query` — search query for the papers to ingest.
- `sources` — comma-separated sources; empty = all.
- `categories` — comma-separated category filters.
- `max_results` — how many papers to fetch and ingest (1–100).

### Ontology written (`[configured-endpoint]`)
- Nodes: `:Paper` (id `scholarx:paper:<id>`), `:PaperSource` (`scholarx:source:<src>`),
  `:ResearchCategory` (`scholarx:category:<cat>`), shared `:Person` (`scholarx:person:<slug>`).
- Links: `:publishedInSource`, `:hasCategory`, `:authoredBy`, `:hasFullText`.

## Recipes
Ingest recent multi-agent papers into the KG:
```
scholarx_ingest_papers query="multi-agent systems" sources="arxiv,semantic_scholar" max_results=30
```
Ingest a category slice for corpus building:
```
scholarx_ingest_papers query="graph neural networks" categories="cs.LG" max_results=50
```

## Gotchas
- Ingestion is idempotent — node ids are content-stable (`scholarx:paper:<id>`),
  so re-ingesting a paper MERGEs rather than duplicates.
- `ingested` is `null` when no engine is reachable — that is a clean no-op, not an error.
- The PDF `:AssetOccurrence` blob is created only after the paper is downloaded
  (`scholarx-paper-library`); metadata-only ingestion carries the abstract text.

## Related
- **Programmatic API:** `scholarx.kg_ingest.ingest_papers` (typed nodes) and
  `scholarx.kg_media.ingest_pdf` (PDF blobs) — the mappers this tool wraps.
- **Search / library:** `scholarx-paper-search`, `scholarx-paper-library`.
