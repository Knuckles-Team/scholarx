"""MCP tool registration modules for scholarx.

Auto-generated during ecosystem standardization.
Each domain has its own module with a register_*_tools function.
"""

from scholarx.mcp.mcp_discovery import register_discovery_tools
from scholarx.mcp.mcp_search import register_search_tools
from scholarx.mcp.mcp_storage import register_storage_tools

__all__ = [
    "register_discovery_tools",
    "register_search_tools",
    "register_storage_tools",
]
