#!/usr/bin/python
"""ScholarX MCP Server.

Thin MCP wrapper over the ScholarX API client. Provides search, discovery,
and storage tools via the standard agent-utilities MCP server factory.
"""

import asyncio
import logging
import sys

from agent_utilities.core.config import load_config, setting
from agent_utilities.mcp.action_dispatch import resolve_action
from agent_utilities.mcp.concurrency import run_blocking
from agent_utilities.mcp.verbose_tools import register_tool_surface
from fastmcp import Context
from pydantic import Field

load_config()

__version__ = "2.0.0"

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

# ── Valid actions per action-routed tool ────────────────────────────────────
SEARCH_ACTIONS = ("search", "get", "author", "recent")
INFO_ACTIONS = ("sources", "categories")
STORAGE_ACTIONS = (
    "download",
    "download_url",
    "bulk_download",
    "stored",
    "status",
    "queue",
)

# ── Lazy client singleton ───────────────────────────────────────────────────
_client = None


def _get_client():
    global _client
    if _client is None:
        from scholarx.api_client import ScholarXClient

        _client = ScholarXClient()
    return _client


def _auto_ingest_papers(papers) -> None:
    """Best-effort native ingestion of papers as typed KG nodes. No-ops without an engine."""
    try:
        from scholarx.kg_ingest import ingest_papers

        ingest_papers(papers)
    except Exception as e:  # noqa: BLE001 — KG ingestion is never fatal to a search
        logger.debug("Operation failed: error_type=%s", type(e).__name__)


# ── Tool Registration Functions ─────────────────────────────────────────────


def register_search_tools(mcp):
    """Register search-related tools."""

    @mcp.tool(
        tags={"search"},
        annotations={"readOnlyHint": True, "openWorldHint": True},
    )
    async def sx_search(
        action: str = Field(
            description="Action: 'search', 'get', 'author', 'recent'. Use 'list_actions' to discover all."
        ),
        query: str = Field(default="", description="Search query string"),
        sources: str = Field(
            default="",
            description="Comma-separated sources (arxiv,pmc,biorxiv,medrxiv,psyarxiv,osf,semantic_scholar). Empty=all",
        ),
        categories: str = Field(default="", description="Comma-separated category filters (e.g., cs.AI,cs.MA)"),
        max_results: int = Field(default=20, description="Maximum results", ge=1, le=100),
        sort_by: str = Field(default="relevance", description="Sort: 'relevance' or 'date'"),
        title: str = Field(default="", description="Optional title to search for"),
        paper_id: str = Field(
            default="", description="Source-specific paper ID for 'get', or comma-separated for 'search'"
        ),
        author: str = Field(default="", description="Author name to search for"),
        days: int = Field(default=1, description="Number of days to look back for 'recent'", ge=1, le=30),
        ctx: Context | None = Field(description="MCP context for progress reporting", default=None),
    ) -> dict:
        """Search for research papers across all configured sources."""
        from scholarx.models import PaperSource, SearchQuery

        resolved = resolve_action(action, SEARCH_ACTIONS, service="scholarx")
        if isinstance(resolved, dict):
            return resolved
        action = resolved

        client = _get_client()
        source_list = [PaperSource(s.strip()) for s in sources.split(",") if s.strip()] if sources else []
        cat_list = [c.strip() for c in categories.split(",") if c.strip()] if categories else []

        if action == "get":
            if not sources or not paper_id:
                return {"error": "Both 'sources' and 'paper_id' required for 'get' action"}
            if ctx:
                await ctx.report_progress(10, 100)
            # Use the first provided source for a direct get
            paper = await client.get_paper(PaperSource(sources.split(",")[0].strip()), paper_id)
            if ctx:
                await ctx.report_progress(100, 100)
            return (
                paper.model_dump(exclude={"normalized_title", "normalized_authors"})
                if paper
                else {"error": "Paper not found"}
            )

        if action == "author":
            if not author:
                return {"error": "'author' is required for 'author' action"}
            sq = SearchQuery(query=author, author=author, max_results=max_results)
            result = await client.search(sq)
            return {
                "papers": [p.model_dump(exclude={"normalized_title", "normalized_authors"}) for p in result.papers],
                "total_count": result.total_count,
            }

        if action == "recent":
            if not cat_list:
                cat_list = ["cs.AI", "cs.MA", "cs.SE", "cs.LG"]
            srcs = source_list if source_list else None
            result = await client.get_recent_papers(cat_list, days, srcs)
            return {
                "papers": [p.model_dump(exclude={"normalized_title", "normalized_authors"}) for p in result.papers],
                "total_count": result.total_count,
                "sources_queried": [s.value for s in result.sources_queried],
            }

        # Default action: search
        id_list = [i.strip() for i in paper_id.split(",") if i.strip()] if paper_id else None
        sq = SearchQuery(
            query=query,
            sources=source_list,
            categories=cat_list,
            max_results=max_results,
            sort_by=sort_by,
            title=title if title else None,
            paper_ids=id_list,
        )
        if ctx:
            await ctx.report_progress(10, 100)
        result = await client.search(sq)
        if ctx:
            await ctx.report_progress(100, 100)
        _auto_ingest_papers(result.papers)
        return {
            "papers": [p.model_dump(exclude={"normalized_title", "normalized_authors"}) for p in result.papers],
            "total_count": result.total_count,
            "sources_queried": [s.value for s in result.sources_queried],
            "deduplicated_count": result.deduplicated_count,
        }


def register_discovery_tools(mcp):
    """Register discovery-related tools."""

    @mcp.tool(tags={"discovery"}, annotations={"readOnlyHint": True})
    async def sx_info(
        action: str = Field(
            default="sources",
            description="Action: 'sources' or 'categories'. Use 'list_actions' to discover all.",
        ),
        source: str = Field(default="", description="Filter by source for 'categories'. Empty=all"),
        ctx: Context | None = Field(description="MCP context for progress reporting", default=None),
    ) -> dict:
        """Get metadata about sources and categories."""
        from scholarx.models import PaperSource

        resolved = resolve_action(action, INFO_ACTIONS, service="scholarx")
        if isinstance(resolved, dict):
            return resolved
        action = resolved

        client = _get_client()
        if action == "categories":
            src = PaperSource(source) if source else None
            return await client.list_categories(src)

        # Default action: sources
        if ctx:
            await ctx.report_progress(10, 100)
        statuses = await client.get_source_status()
        if ctx:
            await ctx.report_progress(100, 100)
        return {"sources": [s.model_dump() for s in statuses]}


def register_storage_tools(mcp):
    """Register paper storage tools."""

    @mcp.tool(tags={"storage"})
    async def sx_storage(
        action: str = Field(
            default="stored",
            description=(
                "Action: 'download', 'download_url', 'bulk_download', 'stored', "
                "'status', 'queue'. Use 'list_actions' to discover all."
            ),
        ),
        source: str = Field(default="", description="Paper source (arxiv, pmc, etc.)"),
        paper_ids: str = Field(default="", description="Comma-separated list of paper IDs to download"),
        job_id: str = Field(default="", description="The job_id to check status for"),
        ctx: Context | None = Field(description="MCP context for progress reporting", default=None),
    ) -> dict:
        """Manage offline PDF storage and background downloads."""
        from scholarx.models import PaperSource

        resolved = resolve_action(action, STORAGE_ACTIONS, service="scholarx")
        if isinstance(resolved, dict):
            return resolved
        action = resolved

        client = _get_client()
        if action == "stored":
            papers = await run_blocking(client.storage.list_stored_papers)
            stats = await run_blocking(client.storage.get_storage_stats)
            return {"papers": papers, "stats": stats}

        if action == "status":
            if not job_id:
                return {"error": "'job_id' required for 'status' action"}
            status = await run_blocking(client.get_download_status, job_id)
            return status if status else {"error": f"Job {job_id} not found."}

        if action == "queue":
            return {"downloads": await run_blocking(client.get_queue_status)}

        if action == "download":
            if not source or not paper_ids:
                return {"error": "'source' and 'paper_ids' required for 'download' action"}
            if len(paper_ids) > _MAX_DIRECT_DOWNLOAD_INPUT_CHARS:
                return {"error": "'paper_ids' input limit exceeded"}
            pid = paper_ids.split(",")[0].strip()
            try:
                paper_source = PaperSource(source)
            except ValueError:
                return {"error": "Invalid paper source"}

            # Check local storage first
            stored = await run_blocking(client.storage.list_stored_papers)
            for p in stored:
                if p.get("source") == source and (pid == p.get("id") or pid in p.get("id", "")):
                    local_path = p.get("local_path")
                    if local_path and __import__("pathlib").Path(local_path).exists():
                        return {"status": "already_exists", "local_path": local_path, "paper_id": p.get("id")}

            paper = await client.get_paper(paper_source, pid)
            if not paper:
                return {"error": "Paper not found"}
            if ctx:
                await ctx.report_progress(10, 100)
            # Bound the inline fetch so a slow/large source can never exceed the MCP
            # call timeout and wedge the (serialized) server — on timeout, hand the
            # job to the background download queue and return its id to poll via
            # action='status'. Fast downloads still return the local path inline.
            try:
                path = await asyncio.wait_for(client.download_paper(paper), timeout=_INLINE_DOWNLOAD_BUDGET_S)
            except TimeoutError:
                jid = await run_blocking(client.queue_download, paper)
                return {
                    "status": "queued",
                    "job_id": jid,
                    "paper_id": paper.id,
                    "note": (
                        "download exceeded the inline budget; running in background "
                        "— poll with action='status', job_id=<id>"
                    ),
                }
            if ctx:
                await ctx.report_progress(100, 100)
            return {
                "status": "downloaded" if path else "failed",
                "local_path": str(path) if path else None,
                "paper_id": paper.id,
            }

        if action == "download_url":
            if not paper_ids:
                return {"error": "'paper_ids' required for 'download_url' action"}
            if len(paper_ids) > _MAX_DIRECT_DOWNLOAD_INPUT_CHARS:
                return {"error": "'paper_ids' input limit exceeded"}
            from typing import Any

            from scholarx.paper_storage import normalize_arxiv_id

            raw_ids = [i.strip() for i in paper_ids.split(",") if i.strip()]
            if len(raw_ids) > _MAX_DIRECT_DOWNLOAD_IDS:
                return {"error": "direct download count limit exceeded"}

            results: list[dict[str, Any]] = []
            deadline = asyncio.get_running_loop().time() + _MAX_DIRECT_DOWNLOAD_SECONDS
            for raw_id in raw_ids:
                try:
                    pid = normalize_arxiv_id(raw_id)
                except ValueError:
                    results.append(
                        {
                            "paper_id": "invalid",
                            "status": "rejected",
                            "error": "Invalid arXiv identifier",
                        }
                    )
                    continue
                try:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        raise TimeoutError
                    path, size_bytes, created = await asyncio.wait_for(
                        client.storage.download_arxiv_id(pid),
                        timeout=remaining,
                    )
                    results.append(
                        {
                            "paper_id": pid,
                            "status": "downloaded" if created else "already_exists",
                            "local_path": str(path),
                            "size_bytes": size_bytes,
                        }
                    )
                except TimeoutError:
                    results.append(
                        {
                            "paper_id": pid,
                            "status": "failed",
                            "error": "direct download time limit exceeded",
                        }
                    )
                    break
                except Exception:
                    results.append(
                        {
                            "paper_id": pid,
                            "status": "failed",
                            "error": "Operation failed",
                        }
                    )
            return {"results": results}

        if action == "bulk_download":
            if not source or not paper_ids:
                return {"error": "'source' and 'paper_ids' required for 'bulk_download' action"}
            if len(paper_ids) > _MAX_DIRECT_DOWNLOAD_INPUT_CHARS:
                return {"error": "'paper_ids' input limit exceeded"}
            ids = [i.strip() for i in paper_ids.split(",") if i.strip()]
            if len(ids) > _MAX_BULK_DOWNLOAD_IDS:
                return {"error": "bulk download count limit exceeded"}
            try:
                paper_source = PaperSource(source)
            except ValueError:
                return {"error": "Invalid paper source"}
            results = []
            stored = await run_blocking(client.storage.list_stored_papers)
            deadline = asyncio.get_running_loop().time() + _MAX_BULK_DOWNLOAD_SECONDS
            for pid in ids:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    results.append(
                        {
                            "paper_id": pid,
                            "status": "failed",
                            "error": "bulk download time limit exceeded",
                        }
                    )
                    break
                # Check local storage first
                already_exists = False
                for p in stored:
                    if p.get("source") == source and (pid == p.get("id") or pid in p.get("id", "")):
                        local_path = p.get("local_path")
                        if local_path and __import__("pathlib").Path(local_path).exists():
                            results.append({"paper_id": pid, "status": "already_exists", "local_path": local_path})
                            already_exists = True
                            break
                if already_exists:
                    continue

                try:
                    paper = await asyncio.wait_for(
                        client.get_paper(paper_source, pid), timeout=remaining
                    )
                except TimeoutError:
                    results.append(
                        {
                            "paper_id": pid,
                            "status": "failed",
                            "error": "bulk download time limit exceeded",
                        }
                    )
                    break
                if not paper:
                    results.append({"paper_id": pid, "status": "failed", "error": "Paper not found"})
                    continue
                jid = await run_blocking(client.queue_download, paper)
                results.append({"paper_id": pid, "status": "queued", "job_id": jid})
            return {"results": results}

        # resolve_action guarantees a valid canonical action above.
        return {"error": f"Unknown action: {action}"}  # pragma: no cover


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
        """Fetch papers and natively ingest them into epistemic-graph as typed :Paper nodes.

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
        ingested = await run_blocking(ingest_papers, result.papers)
        if ctx:
            await ctx.report_progress(100, 100)
        return {"fetched": len(result.papers), "ingested": ingested}


def register_prompts(mcp):
    """Register analysis prompts for the genius-agent."""

    @mcp.prompt()
    def agent_utilities_enhancement_scan() -> str:
        """Scan recent CS/AI papers for agent-utilities enhancement opportunities."""
        return (
            "Search for recent papers in cs.AI, cs.MA, cs.SE, cs.LG, cs.CL.\n"
            "For each paper, evaluate against agent-utilities concepts (AU-001 through AU-047):\n"
            "1. Primary contribution type (theoretical/empirical/artifact/methodology)\n"
            "2. Gap addressed relative to existing AU concepts\n"
            "3. Theoretical relationship (extends/contradicts/complements)\n"
            "4. Key concepts introduced or reused\n"
            "5. Methodological compatibility with graph-native architecture\n"
            "6. Level of analysis (micro-agent/meso-swarm/macro-ecosystem)\n"
            "7. Evidence maturity (proposal/prototype/validated/production)\n"
            "8. Complementary or substitution potential\n"
            "Output a ranked list of actionable enhancement proposals."
        )

    @mcp.prompt()
    def biomimicry_innovation_scan() -> str:
        """Scan biology/chemistry for biomimetic agent patterns."""
        return (
            "Search bioRxiv, PMC for: swarm intelligence, stigmergy, quorum sensing, "
            "neural plasticity, homeostasis, immune response, chemical signaling, "
            "self-organizing systems, emergent behavior.\n"
            "Map findings to AU-033 (Quorum Sensing), AU-034 (Ant Colony), "
            "AU-037 (Homeostatic Cron), and novel mechanisms."
        )


# ── MCP Server Factory ──────────────────────────────────────────────────────


def get_mcp_instance():
    """Create and configure the MCP server instance."""
    from agent_utilities.mcp.server_factory import create_mcp_server

    args, mcp, middlewares = create_mcp_server(
        name="ScholarX MCP",
        version=__version__,
        instructions=(
            "Universal research paper search and analysis across arXiv, PMC, "
            "bioRxiv, medRxiv, PsyArXiv, OSF, and Semantic Scholar. "
            "Use search tools to find papers, discovery tools to explore "
            "recent publications, and storage tools to download full PDFs."
        ),
    )

    from scholarx.api_client import ScholarXClient

    register_tool_surface(
        mcp,
        client_cls=ScholarXClient,
        get_client=_get_client,
        service="scholarx",
        registrars=[
            register_search_tools,
            register_discovery_tools,
            register_storage_tools,
            register_kg_tools,
        ],
    )

    register_prompts(mcp)

    return args, mcp


def mcp_server():
    """MCP server entry point."""
    print(f"ScholarX MCP v{__version__}", file=sys.stderr)
    args, mcp = get_mcp_instance()

    transport = getattr(args, "transport", setting("TRANSPORT", "stdio"))
    host = getattr(args, "host", setting("HOST", "127.0.0.1"))
    port = int(getattr(args, "port", setting("PORT", "9600")))

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    mcp_server()
