"""MCP tools for discovery operations.

Auto-generated from mcp_server.py during ecosystem standardization.
"""

from agent_utilities.mcp.action_dispatch import resolve_action
from fastmcp import Context
from pydantic import Field

from scholarx.mcp_server import INFO_ACTIONS, _get_client


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
