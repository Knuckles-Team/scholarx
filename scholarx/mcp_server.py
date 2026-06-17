#!/usr/bin/python
"""ScholarX MCP Server.

Thin MCP wrapper over the ScholarX API client. Provides search, discovery,
and storage tools via the standard agent-utilities MCP server factory.
"""

import asyncio
import logging
import os
import sys

from agent_utilities.base_utilities import to_boolean
from agent_utilities.mcp_utilities import resolve_action, run_blocking
from dotenv import find_dotenv, load_dotenv
from fastmcp import Context
from pydantic import Field

load_dotenv(find_dotenv())

__version__ = "0.30.0"

# Wall budget for an inline single-paper download before it is handed to the
# background queue. Kept well under the MCP child-call timeout so a slow source
# can never hold the (serialized) server slot open and wedge subsequent calls.
_INLINE_DOWNLOAD_BUDGET_S = 60.0

logger = logging.getLogger(__name__)

# ── Tag-Gated Tool Toggles ──────────────────────────────────────────────────
DEFAULT_SEARCHTOOL = to_boolean(os.getenv("SEARCHTOOL", "True"))
DEFAULT_DISCOVERYTOOL = to_boolean(os.getenv("DISCOVERYTOOL", "True"))
DEFAULT_STORAGETOOL = to_boolean(os.getenv("STORAGETOOL", "True"))

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
            pid = paper_ids.split(",")[0].strip()

            # Check local storage first
            stored = await run_blocking(client.storage.list_stored_papers)
            for p in stored:
                if p.get("source") == source and (pid == p.get("id") or pid in p.get("id", "")):
                    local_path = p.get("local_path")
                    if local_path and __import__("pathlib").Path(local_path).exists():
                        return {"status": "already_exists", "local_path": local_path, "paper_id": p.get("id")}

            paper = await client.get_paper(PaperSource(source), pid)
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
            # Direct URL-based download — bypasses the arXiv API entirely.
            # Accepts paper_ids as arXiv IDs (e.g. "2603.09022") or full URLs
            # (e.g. "https://arxiv.org/abs/2603.09022").
            if not paper_ids:
                return {"error": "'paper_ids' required for 'download_url' action"}
            from typing import Any

            results: list[dict[str, Any]] = []
            for raw_id in [i.strip() for i in paper_ids.split(",") if i.strip()]:
                # Extract arXiv ID from URL if provided
                pid = raw_id
                for prefix in ("https://arxiv.org/abs/", "https://arxiv.org/pdf/", "http://arxiv.org/abs/"):
                    if raw_id.startswith(prefix):
                        pid = raw_id.split(prefix)[-1].rstrip("/")
                        break
                # Strip version suffix for filename, keep for URL
                base_id = pid.split("v")[0] if "v" in pid and pid[-1].isdigit() else pid
                pdf_url = f"https://arxiv.org/pdf/{pid}"
                dest = client.storage.storage_dir / f"{base_id}.pdf"
                if dest.exists():
                    results.append({"paper_id": pid, "status": "already_exists", "local_path": str(dest)})
                    continue
                try:
                    import httpx as _httpx

                    async with _httpx.AsyncClient(
                        timeout=_httpx.Timeout(120.0, connect=30.0),
                        follow_redirects=True,
                    ) as http:
                        resp = await http.get(pdf_url)
                        resp.raise_for_status()
                        dest.write_bytes(resp.content)
                        results.append(
                            {
                                "paper_id": pid,
                                "status": "downloaded",
                                "local_path": str(dest),
                                "size_bytes": len(resp.content),
                            }
                        )
                except Exception as e:
                    results.append({"paper_id": pid, "status": "failed", "error": str(e)})
            return {"results": results}

        if action == "bulk_download":
            if not source or not paper_ids:
                return {"error": "'source' and 'paper_ids' required for 'bulk_download' action"}
            ids = [i.strip() for i in paper_ids.split(",") if i.strip()]
            results = []
            stored = await run_blocking(client.storage.list_stored_papers)
            for pid in ids:
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

                paper = await client.get_paper(PaperSource(source), pid)
                if not paper:
                    results.append({"paper_id": pid, "status": "failed", "error": "Paper not found"})
                    continue
                jid = await run_blocking(client.queue_download, paper)
                results.append({"paper_id": pid, "status": "queued", "job_id": jid})
            return {"results": results}

        # resolve_action guarantees a valid canonical action above.
        return {"error": f"Unknown action: {action}"}  # pragma: no cover


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
    from agent_utilities.mcp_utilities import create_mcp_server

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

    if DEFAULT_SEARCHTOOL:
        register_search_tools(mcp)
    if DEFAULT_DISCOVERYTOOL:
        register_discovery_tools(mcp)
    if DEFAULT_STORAGETOOL:
        register_storage_tools(mcp)

    register_prompts(mcp)

    return args, mcp


def mcp_server():
    """MCP server entry point."""
    print(f"ScholarX MCP v{__version__}", file=sys.stderr)
    args, mcp = get_mcp_instance()

    transport = getattr(args, "transport", os.getenv("TRANSPORT", "stdio"))
    host = getattr(args, "host", os.getenv("HOST", "0.0.0.0"))  # nosec B104
    port = int(getattr(args, "port", os.getenv("PORT", "9600")))

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    mcp_server()
