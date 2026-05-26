"""MCP tools for search operations.

Auto-generated from mcp_server.py during ecosystem standardization.
"""

from fastmcp import Context
from pydantic import Field

from scholarx.mcp_server import _get_client


def register_search_tools(mcp):
    """Register search-related tools."""

    @mcp.tool(
        tags={"search"},
        annotations={"readOnlyHint": True, "openWorldHint": True},
    )
    async def sx_search(
        action: str = Field(description="Action: 'search', 'get', 'author', 'recent'"),
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
