#!/usr/bin/python
"""ScholarX MCP Server.

Thin MCP wrapper over the ScholarX API client. Provides search, discovery,
and storage tools via the standard scion-sdk MCP server factory.
"""

import asyncio
import logging
from dataclasses import dataclass

from fastmcp import Context
from pydantic import Field
from scion_sdk.config import load_config
from scion_sdk.mcp.concurrency import run_blocking

load_config()

# Wall budget for an inline single-paper download before it is handed to the
# background queue. Kept well under the MCP child-call timeout so a slow source
# can never hold the (serialized) server slot open and wedge subsequent calls.
_INLINE_DOWNLOAD_BUDGET_S = 60.0
_MAX_DIRECT_DOWNLOAD_IDS = 20
_MAX_DIRECT_DOWNLOAD_INPUT_CHARS = 4096
_MAX_DIRECT_DOWNLOAD_SECONDS = 180.0
_MAX_BULK_DOWNLOAD_IDS = 100
_MAX_BULK_DOWNLOAD_SECONDS = 180.0

logger = logging.getLogger(__name__)

# ── Lazy client singleton ───────────────────────────────────────────────────
_client = None


def _get_client():
    global _client
    if _client is None:
        from scholarx.api_client import ScholarXClient

        _client = ScholarXClient()
    return _client


async def _auto_ingest_papers(papers) -> None:
    """Best-effort native ingestion of papers as typed KG nodes. No-ops without an engine."""
    try:
        from scholarx.kg_ingest import ingest_papers

        await ingest_papers(papers)
    except Exception as e:  # noqa: BLE001 — KG ingestion is never fatal to a search
        logger.debug("Operation failed: error_type=%s", type(e).__name__)


def _parse_comma_list(value: str) -> list[str]:
    """Split a comma-separated string into trimmed, non-empty parts (`""` -> `[]`)."""
    return [v.strip() for v in value.split(",") if v.strip()]


def _parse_source_list(sources: str) -> list:
    from scholarx.models import PaperSource

    return [PaperSource(s) for s in _parse_comma_list(sources)]


async def _handle_sx_search_get(client, sources: str, paper_id: str, ctx) -> dict:
    if not sources or not paper_id:
        return {"error": "Both 'sources' and 'paper_id' required for sx_search_get"}
    from scholarx.models import PaperSource

    if ctx:
        await ctx.report_progress(10, 100)
    # Use the first provided source for a direct get
    paper = await client.get_paper(PaperSource(sources.split(",")[0].strip()), paper_id)
    if ctx:
        await ctx.report_progress(100, 100)
    return (
        paper.model_dump(exclude={"normalized_title", "normalized_authors"}) if paper else {"error": "Paper not found"}
    )


async def _handle_sx_search_author(client, author: str, max_results: int) -> dict:
    if not author:
        return {"error": "'author' is required for sx_search_author"}
    from scholarx.models import SearchQuery

    sq = SearchQuery(query=author, author=author, max_results=max_results)
    result = await client.search(sq)
    return {
        "papers": [p.model_dump(exclude={"normalized_title", "normalized_authors"}) for p in result.papers],
        "total_count": result.total_count,
    }


async def _handle_sx_search_recent(client, cat_list: list[str], days: int, source_list: list) -> dict:
    if not cat_list:
        cat_list = ["cs.AI", "cs.MA", "cs.SE", "cs.LG"]
    srcs = source_list if source_list else None
    result = await client.get_recent_papers(cat_list, days, srcs)
    return {
        "papers": [p.model_dump(exclude={"normalized_title", "normalized_authors"}) for p in result.papers],
        "total_count": result.total_count,
        "sources_queried": [s.value for s in result.sources_queried],
    }


@dataclass
class _SxSearchArgs:
    """The sx_search_search query parameters, bundled so the
    handler stays under the 7-parameter cap."""

    query: str
    source_list: list
    cat_list: list[str]
    max_results: int
    sort_by: str
    title: str
    paper_id: str


async def _handle_sx_search_default(client, args: _SxSearchArgs, ctx) -> dict:
    from scholarx.models import SearchQuery

    id_list = [i.strip() for i in args.paper_id.split(",") if i.strip()] if args.paper_id else None
    sq = SearchQuery(
        query=args.query,
        sources=args.source_list,
        categories=args.cat_list,
        max_results=args.max_results,
        sort_by=args.sort_by,
        title=args.title if args.title else None,
        paper_ids=id_list,
    )
    if ctx:
        await ctx.report_progress(10, 100)
    result = await client.search(sq)
    if ctx:
        await ctx.report_progress(100, 100)
    await _auto_ingest_papers(result.papers)
    return {
        "papers": [p.model_dump(exclude={"normalized_title", "normalized_authors"}) for p in result.papers],
        "total_count": result.total_count,
        "sources_queried": [s.value for s in result.sources_queried],
        "deduplicated_count": result.deduplicated_count,
    }


# ── Tool Registration Functions ─────────────────────────────────────────────


def register_search_tools(mcp):
    """Register one typed tool per search operation."""

    read_only = {"readOnlyHint": True, "openWorldHint": True}

    @mcp.tool(tags={"search"}, annotations=read_only)
    async def sx_search_search(
        query: str = Field(default="", description="Search query string"),
        sources: str = Field(
            default="",
            description="Comma-separated sources (arxiv,pmc,biorxiv,medrxiv,psyarxiv,osf,semantic_scholar). Empty=all",
        ),
        categories: str = Field(default="", description="Comma-separated category filters (e.g., cs.AI,cs.MA)"),
        max_results: int = Field(default=20, description="Maximum results", ge=1, le=100),
        sort_by: str = Field(default="relevance", description="Sort: 'relevance' or 'date'"),
        title: str = Field(default="", description="Optional title to search for"),
        paper_id: str = Field(default="", description="Comma-separated source-specific paper IDs"),
        ctx: Context | None = Field(description="MCP context for progress reporting", default=None),
    ) -> dict:
        """Search for research papers across all configured sources."""
        return await _handle_sx_search_default(
            _get_client(),
            _SxSearchArgs(
                query=query,
                source_list=_parse_source_list(sources),
                cat_list=_parse_comma_list(categories),
                max_results=max_results,
                sort_by=sort_by,
                title=title,
                paper_id=paper_id,
            ),
            ctx,
        )

    @mcp.tool(tags={"search"}, annotations=read_only)
    async def sx_search_get(
        sources: str = Field(default="", description="Source of the paper (first of a comma-separated list is used)"),
        paper_id: str = Field(default="", description="Source-specific paper ID"),
        ctx: Context | None = Field(description="MCP context for progress reporting", default=None),
    ) -> dict:
        """Retrieve one paper by source and paper ID."""
        return await _handle_sx_search_get(_get_client(), sources, paper_id, ctx)

    @mcp.tool(tags={"search"}, annotations=read_only)
    async def sx_search_author(
        author: str = Field(default="", description="Author name to search for"),
        max_results: int = Field(default=20, description="Maximum results", ge=1, le=100),
    ) -> dict:
        """Search for papers by author name."""
        return await _handle_sx_search_author(_get_client(), author, max_results)

    @mcp.tool(tags={"search"}, annotations=read_only)
    async def sx_search_recent(
        categories: str = Field(
            default="", description="Comma-separated category filters (default cs.AI,cs.MA,cs.SE,cs.LG)"
        ),
        days: int = Field(default=1, description="Number of days to look back", ge=1, le=30),
        sources: str = Field(default="", description="Comma-separated sources. Empty=all"),
    ) -> dict:
        """List papers published in recent days for given categories."""
        return await _handle_sx_search_recent(
            _get_client(), _parse_comma_list(categories), days, _parse_source_list(sources)
        )


def register_discovery_tools(mcp):
    """Register one typed tool per discovery operation."""

    @mcp.tool(tags={"discovery"}, annotations={"readOnlyHint": True})
    async def sx_info_sources(
        ctx: Context | None = Field(description="MCP context for progress reporting", default=None),
    ) -> dict:
        """Get the status of every configured paper source."""
        client = _get_client()
        if ctx:
            await ctx.report_progress(10, 100)
        statuses = await client.get_source_status()
        if ctx:
            await ctx.report_progress(100, 100)
        return {"sources": [s.model_dump() for s in statuses]}

    @mcp.tool(tags={"discovery"}, annotations={"readOnlyHint": True})
    async def sx_info_categories(
        source: str = Field(default="", description="Filter by source. Empty=all"),
    ) -> dict:
        """List the categories each paper source offers."""
        from scholarx.models import PaperSource

        src = PaperSource(source) if source else None
        return await _get_client().list_categories(src)


def _find_locally_stored_paper(stored, source, pid):
    """Return the first stored-paper record matching ``source``/``pid`` whose
    local file still exists on disk, else ``None``.

    Shared by the ``download`` and ``bulk_download`` handlers, which previously
    each carried an identical copy of this scan-and-check loop.
    """
    for p in stored:
        if p.get("source") == source and (pid == p.get("id") or pid in p.get("id", "")):
            local_path = p.get("local_path")
            if local_path and __import__("pathlib").Path(local_path).exists():
                return p
    return None


async def _download_single_paper(client, paper, ctx):
    """Fetch one already-resolved ``paper`` inline within the inline budget.

    On timeout, hand the job to the background download queue instead of
    blocking the (serialized) MCP server slot further.
    """
    if ctx:
        await ctx.report_progress(10, 100)
    # Bound the inline fetch so a slow/large source can never exceed the MCP
    # call timeout and wedge the (serialized) server — on timeout, hand the
    # job to the background download queue and return its id to poll via
    # sx_storage_status. Fast downloads still return the local path inline.
    try:
        path = await asyncio.wait_for(client.download_paper(paper), timeout=_INLINE_DOWNLOAD_BUDGET_S)
    except TimeoutError:
        jid = await run_blocking(client.queue_download, paper)
        return {
            "status": "queued",
            "job_id": jid,
            "paper_id": paper.id,
            "note": (
                "download exceeded the inline budget; running in background — poll sx_storage_status with job_id=<id>"
            ),
        }
    if ctx:
        await ctx.report_progress(100, 100)
    return {
        "status": "downloaded" if path else "failed",
        "local_path": str(path) if path else None,
        "paper_id": paper.id,
    }


async def _sx_storage_stored(client) -> dict:
    papers = await run_blocking(client.storage.list_stored_papers)
    stats = await run_blocking(client.storage.get_storage_stats)
    return {"papers": papers, "stats": stats}


async def _sx_storage_status(client, job_id) -> dict:
    if not job_id:
        return {"error": "'job_id' required for 'sx_storage_status'"}
    status = await run_blocking(client.get_download_status, job_id)
    return status if status else {"error": f"Job {job_id} not found."}


async def _sx_storage_queue(client) -> dict:
    return {"downloads": await run_blocking(client.get_queue_status)}


async def _sx_storage_download(client, source, paper_ids, ctx, PaperSource) -> dict:
    if not source or not paper_ids:
        return {"error": "'source' and 'paper_ids' required for 'sx_storage_download'"}
    if len(paper_ids) > _MAX_DIRECT_DOWNLOAD_INPUT_CHARS:
        return {"error": "'paper_ids' input limit exceeded"}
    pid = paper_ids.split(",")[0].strip()
    try:
        paper_source = PaperSource(source)
    except ValueError:
        return {"error": "Invalid paper source"}

    # Check local storage first
    stored = await run_blocking(client.storage.list_stored_papers)
    match = _find_locally_stored_paper(stored, source, pid)
    if match:
        return {"status": "already_exists", "local_path": match.get("local_path"), "paper_id": match.get("id")}

    paper = await client.get_paper(paper_source, pid)
    if not paper:
        return {"error": "Paper not found"}
    return await _download_single_paper(client, paper, ctx)


async def _download_one_arxiv_url(client, raw_id, deadline):
    """Process one ``download_url`` id. Returns ``(result, should_stop)``;
    ``should_stop`` mirrors the original loop's ``break`` on time-limit."""
    from scholarx.paper_storage import normalize_arxiv_id

    try:
        pid = normalize_arxiv_id(raw_id)
    except ValueError:
        return {"paper_id": "invalid", "status": "rejected", "error": "Invalid arXiv identifier"}, False
    try:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError
        path, size_bytes, created = await asyncio.wait_for(
            client.storage.download_arxiv_id(pid),
            timeout=remaining,
        )
        return {
            "paper_id": pid,
            "status": "downloaded" if created else "already_exists",
            "local_path": str(path),
            "size_bytes": size_bytes,
        }, False
    except TimeoutError:
        return {"paper_id": pid, "status": "failed", "error": "direct download time limit exceeded"}, True
    except Exception:
        return {"paper_id": pid, "status": "failed", "error": "Operation failed"}, False


async def _sx_storage_download_url(client, paper_ids) -> dict:
    if not paper_ids:
        return {"error": "'paper_ids' required for 'sx_storage_download_url'"}
    if len(paper_ids) > _MAX_DIRECT_DOWNLOAD_INPUT_CHARS:
        return {"error": "'paper_ids' input limit exceeded"}

    raw_ids = [i.strip() for i in paper_ids.split(",") if i.strip()]
    if len(raw_ids) > _MAX_DIRECT_DOWNLOAD_IDS:
        return {"error": "direct download count limit exceeded"}

    results = []
    deadline = asyncio.get_running_loop().time() + _MAX_DIRECT_DOWNLOAD_SECONDS
    for raw_id in raw_ids:
        result, should_stop = await _download_one_arxiv_url(client, raw_id, deadline)
        results.append(result)
        if should_stop:
            break
    return {"results": results}


async def _bulk_download_one(client, paper_source, source, stored, pid, remaining):
    """Process one ``bulk_download`` id (deadline already checked by the
    caller). Returns ``(result, should_stop)``."""
    match = _find_locally_stored_paper(stored, source, pid)
    if match:
        return {"paper_id": pid, "status": "already_exists", "local_path": match.get("local_path")}, False

    try:
        paper = await asyncio.wait_for(client.get_paper(paper_source, pid), timeout=remaining)
    except TimeoutError:
        return {"paper_id": pid, "status": "failed", "error": "bulk download time limit exceeded"}, True
    if not paper:
        return {"paper_id": pid, "status": "failed", "error": "Paper not found"}, False
    jid = await run_blocking(client.queue_download, paper)
    return {"paper_id": pid, "status": "queued", "job_id": jid}, False


def _validate_bulk_download_request(source, paper_ids, PaperSource):
    """Validate + parse ``bulk_download`` inputs, in the original check order.

    Returns ``(error, paper_source, ids)``: ``error`` is the response dict to
    return immediately on failure (``None`` on success), in which case
    ``paper_source``/``ids`` carry the parsed values.
    """
    if not source or not paper_ids:
        return {"error": "'source' and 'paper_ids' required for 'sx_storage_bulk_download'"}, None, None
    if len(paper_ids) > _MAX_DIRECT_DOWNLOAD_INPUT_CHARS:
        return {"error": "'paper_ids' input limit exceeded"}, None, None
    ids = [i.strip() for i in paper_ids.split(",") if i.strip()]
    if len(ids) > _MAX_BULK_DOWNLOAD_IDS:
        return {"error": "bulk download count limit exceeded"}, None, None
    try:
        paper_source = PaperSource(source)
    except ValueError:
        return {"error": "Invalid paper source"}, None, None
    return None, paper_source, ids


async def _sx_storage_bulk_download(client, source, paper_ids, PaperSource) -> dict:
    error, paper_source, ids = _validate_bulk_download_request(source, paper_ids, PaperSource)
    if error:
        return error

    results = []
    stored = await run_blocking(client.storage.list_stored_papers)
    deadline = asyncio.get_running_loop().time() + _MAX_BULK_DOWNLOAD_SECONDS
    for pid in ids:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            results.append({"paper_id": pid, "status": "failed", "error": "bulk download time limit exceeded"})
            break
        # Check local storage first
        result, should_stop = await _bulk_download_one(client, paper_source, source, stored, pid, remaining)
        results.append(result)
        if should_stop:
            break
    return {"results": results}


def register_storage_tools(mcp):
    """Register one typed tool per paper-storage operation."""

    @mcp.tool(tags={"storage"}, annotations={"readOnlyHint": True})
    async def sx_storage_stored() -> dict:
        """List the locally stored papers and the storage statistics."""
        return await _sx_storage_stored(_get_client())

    @mcp.tool(tags={"storage"}, annotations={"readOnlyHint": True})
    async def sx_storage_status(
        job_id: str = Field(default="", description="The job_id to check status for"),
    ) -> dict:
        """Get the status of one queued background download."""
        return await _sx_storage_status(_get_client(), job_id)

    @mcp.tool(tags={"storage"}, annotations={"readOnlyHint": True})
    async def sx_storage_queue() -> dict:
        """List every queued background download."""
        return await _sx_storage_queue(_get_client())

    @mcp.tool(tags={"storage"})
    async def sx_storage_download(
        source: str = Field(default="", description="Paper source (arxiv, pmc, etc.)"),
        paper_ids: str = Field(default="", description="Paper ID to download (the first of a comma-separated list)"),
        ctx: Context | None = Field(description="MCP context for progress reporting", default=None),
    ) -> dict:
        """Download one paper's PDF, queueing it when the source is slow."""
        from scholarx.models import PaperSource

        return await _sx_storage_download(_get_client(), source, paper_ids, ctx, PaperSource)

    @mcp.tool(tags={"storage"})
    async def sx_storage_download_url(
        paper_ids: str = Field(default="", description="Comma-separated arXiv ids or abs/pdf URLs"),
    ) -> dict:
        """Download arXiv PDFs by id or URL within a bounded wall time."""
        return await _sx_storage_download_url(_get_client(), paper_ids)

    @mcp.tool(tags={"storage"})
    async def sx_storage_bulk_download(
        source: str = Field(default="", description="Paper source (arxiv, pmc, etc.)"),
        paper_ids: str = Field(default="", description="Comma-separated paper IDs to queue"),
    ) -> dict:
        """Queue many papers from one source for background download."""
        from scholarx.models import PaperSource

        return await _sx_storage_bulk_download(_get_client(), source, paper_ids, PaperSource)


async def _sx_resolve_papers(client, paper_source, ids) -> list:
    """Resolve each id to a Paper; ids that cannot be resolved are dropped."""
    found = await asyncio.gather(*(client.get_paper(paper_source, pid) for pid in ids))
    return [paper for paper in found if paper]


def register_operation_tools(mcp):
    """Register one tool per API-client operation not covered by the routed tools."""

    @mcp.tool(tags={"discovery"}, annotations={"readOnlyHint": True})
    async def sx_enabled_sources() -> dict:
        """List the paper sources enabled on this server (``ScholarXClient.enabled_sources``)."""
        client = _get_client()
        return {"sources": [s.value for s in client.enabled_sources]}

    @mcp.tool(
        name="scholarx_enabled_sources",
        tags={"discovery"},
        annotations={"readOnlyHint": True},
    )
    async def scholarx_enabled_sources() -> dict:
        """List the paper sources enabled on this server (client-method name of ``sx_enabled_sources``)."""
        return {"sources": [s.value for s in _get_client().enabled_sources]}

    @mcp.tool(
        tags={"storage"},
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
    )
    async def sx_download_papers(
        source: str = Field(description="Paper source (arxiv, pmc, etc.)"),
        paper_ids: str = Field(description="Comma-separated paper IDs to download in parallel"),
        concurrency: int = Field(default=0, description="Max simultaneous downloads; 0 auto-sizes"),
    ) -> dict:
        """Download many papers in parallel (``ScholarXClient.download_papers``)."""
        from scholarx.models import PaperSource

        error, paper_source, ids = _validate_bulk_download_request(source, paper_ids, PaperSource)
        if error:
            return error
        client = _get_client()
        papers = await _sx_resolve_papers(client, paper_source, ids)
        try:
            results = await client.download_papers(papers, concurrency=concurrency)
        except ValueError:
            return {"error": "Invalid download request"}
        return {"results": results}

    @mcp.tool(
        tags={"storage"},
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
    )
    async def sx_download_urls(
        paper_ids: str = Field(description="Comma-separated arXiv ids or abs/pdf URLs"),
        concurrency: int = Field(default=0, description="Max simultaneous downloads; 0 auto-sizes"),
    ) -> dict:
        """Download arXiv PDFs directly by id or URL in parallel (``ScholarXClient.download_urls``)."""
        if not paper_ids:
            return {"error": "'paper_ids' required"}
        if len(paper_ids) > _MAX_DIRECT_DOWNLOAD_INPUT_CHARS:
            return {"error": "'paper_ids' input limit exceeded"}
        raw_ids = [i.strip() for i in paper_ids.split(",") if i.strip()]
        client = _get_client()
        try:
            results = await client.download_urls(raw_ids, concurrency=concurrency)
        except ValueError:
            return {"error": "Invalid download request"}
        return {"results": results}


def register_kg_tools(mcp):
    """Register native knowledge-graph ingestion tools (Wire-First)."""

    @mcp.tool(tags={"kg"})
    async def scholarx_ingest_papers(
        query: str = Field(default="", description="Search query to fetch papers to ingest"),
        sources: str = Field(
            default="",
            description="Comma-separated sources (arxiv,pmc,biorxiv,medrxiv,psyarxiv,osf,semantic_scholar). Empty=all",
        ),
        categories: str = Field(default="", description="Comma-separated category filters (e.g., cs.AI,cs.MA)"),
        max_results: int = Field(default=20, description="Maximum papers to fetch and ingest", ge=1, le=100),
        ctx: Context | None = Field(description="MCP context for progress reporting", default=None),
    ) -> dict:
        """Fetch papers and natively ingest them into medulla as typed :Paper nodes.

        Searches via the real ScholarX client and pushes the results (with their
        :PaperSource / :ResearchCategory / :Person nodes and :publishedInSource /
        :hasCategory / :authoredBy links) into the knowledge graph via the fast engine
        client. Best-effort: ``ingested`` is ``null`` when no engine is reachable.
        CONCEPT:AU-KG.ingest.enterprise-source-extractor.
        """
        from scholarx.kg_ingest import ingest_papers
        from scholarx.models import PaperSource, SearchQuery

        client = _get_client()
        source_list = [PaperSource(s.strip()) for s in sources.split(",") if s.strip()] if sources else []
        cat_list = [c.strip() for c in categories.split(",") if c.strip()] if categories else []
        sq = SearchQuery(query=query, sources=source_list, categories=cat_list, max_results=max_results)
        if ctx:
            await ctx.report_progress(10, 100)
        result = await client.search(sq)
        ingested = await ingest_papers(result.papers)
        if ctx:
            await ctx.report_progress(100, 100)
        return {"fetched": len(result.papers), "ingested": ingested}
