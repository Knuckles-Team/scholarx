#!/usr/bin/python
"""ScholarX MCP Server.

Thin MCP wrapper over the ScholarX API client. Provides search, discovery,
and storage tools via the standard agent-utilities MCP server factory.
"""

import logging
import os
import sys

from agent_utilities.base_utilities import to_boolean
from dotenv import find_dotenv, load_dotenv
from pydantic import Field

load_dotenv(find_dotenv())

__version__ = "0.5.0"

logger = logging.getLogger(__name__)

# ── Tag-Gated Tool Toggles ──────────────────────────────────────────────────
DEFAULT_SEARCHTOOL = to_boolean(os.getenv("SEARCHTOOL", "True"))
DEFAULT_DISCOVERYTOOL = to_boolean(os.getenv("DISCOVERYTOOL", "True"))
DEFAULT_STORAGETOOL = to_boolean(os.getenv("STORAGETOOL", "True"))

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
    async def search_papers(
        query: str = Field(description="Search query string"),
        sources: str = Field(
            default="",
            description="Comma-separated sources (arxiv,pmc,biorxiv,medrxiv,psyarxiv,osf,semantic_scholar). Empty=all",
        ),
        categories: str = Field(default="", description="Comma-separated category filters (e.g., cs.AI,cs.MA)"),
        max_results: int = Field(default=20, description="Maximum results", ge=1, le=100),
        sort_by: str = Field(default="relevance", description="Sort: 'relevance' or 'date'"),
    ) -> dict:
        """Search for research papers across all configured sources with deduplication."""
        from scholarx.models import PaperSource, SearchQuery

        client = _get_client()
        source_list = [PaperSource(s.strip()) for s in sources.split(",") if s.strip()] if sources else []
        cat_list = [c.strip() for c in categories.split(",") if c.strip()] if categories else []
        sq = SearchQuery(
            query=query, sources=source_list, categories=cat_list, max_results=max_results, sort_by=sort_by
        )
        result = await client.search(sq)
        return {
            "papers": [p.model_dump(exclude={"normalized_title", "normalized_authors"}) for p in result.papers],
            "total_count": result.total_count,
            "sources_queried": [s.value for s in result.sources_queried],
            "deduplicated_count": result.deduplicated_count,
        }

    @mcp.tool(tags={"search"}, annotations={"readOnlyHint": True})
    async def get_paper(
        source: str = Field(description="Paper source (arxiv, pmc, semantic_scholar, etc.)"),
        paper_id: str = Field(description="Source-specific paper ID"),
    ) -> dict:
        """Retrieve a single paper by source and ID."""
        from scholarx.models import PaperSource

        client = _get_client()
        paper = await client.get_paper(PaperSource(source), paper_id)
        return (
            paper.model_dump(exclude={"normalized_title", "normalized_authors"})
            if paper
            else {"error": "Paper not found"}
        )

    @mcp.tool(tags={"search"}, annotations={"readOnlyHint": True})
    async def search_by_author(
        author: str = Field(description="Author name to search for"),
        max_results: int = Field(default=20, description="Maximum results"),
    ) -> dict:
        """Search for papers by a specific author across all sources."""
        from scholarx.models import SearchQuery

        client = _get_client()
        sq = SearchQuery(query=author, author=author, max_results=max_results)
        result = await client.search(sq)
        return {
            "papers": [p.model_dump(exclude={"normalized_title", "normalized_authors"}) for p in result.papers],
            "total_count": result.total_count,
        }


def register_discovery_tools(mcp):
    """Register discovery-related tools."""

    @mcp.tool(tags={"discovery"}, annotations={"readOnlyHint": True})
    async def get_recent_papers(
        categories: str = Field(default="cs.AI,cs.MA,cs.SE,cs.LG", description="Comma-separated categories"),
        days: int = Field(default=1, description="Number of days to look back", ge=1, le=30),
        sources: str = Field(default="", description="Comma-separated sources. Empty=all"),
    ) -> dict:
        """Get recently published papers across sources."""
        from scholarx.models import PaperSource

        client = _get_client()
        cat_list = [c.strip() for c in categories.split(",") if c.strip()]
        source_list = [PaperSource(s.strip()) for s in sources.split(",") if s.strip()] if sources else None
        result = await client.get_recent_papers(cat_list, days, source_list)
        return {
            "papers": [p.model_dump(exclude={"normalized_title", "normalized_authors"}) for p in result.papers],
            "total_count": result.total_count,
            "sources_queried": [s.value for s in result.sources_queried],
        }

    @mcp.tool(tags={"discovery"}, annotations={"readOnlyHint": True})
    async def list_sources() -> dict:
        """List all available paper sources and their status."""
        client = _get_client()
        statuses = await client.get_source_status()
        return {"sources": [s.model_dump() for s in statuses]}

    @mcp.tool(tags={"discovery"}, annotations={"readOnlyHint": True})
    async def list_categories(
        source: str = Field(default="", description="Filter by source. Empty=all"),
    ) -> dict:
        """List available categories for each paper source."""
        from scholarx.models import PaperSource

        client = _get_client()
        src = PaperSource(source) if source else None
        return await client.list_categories(src)


def register_storage_tools(mcp):
    """Register paper storage tools."""

    @mcp.tool(tags={"storage"})
    async def download_paper(
        source: str = Field(description="Paper source"),
        paper_id: str = Field(description="Source-specific paper ID"),
    ) -> dict:
        """Download the full PDF of a paper to local storage."""
        from scholarx.models import PaperSource

        client = _get_client()
        paper = await client.get_paper(PaperSource(source), paper_id)
        if not paper:
            return {"error": "Paper not found"}
        path = await client.download_paper(paper)
        return {"status": "downloaded" if path else "failed", "local_path": path, "paper_id": paper.id}

    @mcp.tool(tags={"storage"}, annotations={"readOnlyHint": True})
    async def get_stored_papers() -> dict:
        """List all locally stored papers."""
        client = _get_client()
        papers = client.storage.list_stored_papers()
        stats = client.storage.get_storage_stats()
        return {"papers": papers, "stats": stats}


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
