"""Action-discovery contract for the action-routed ScholarX MCP tools.

Each action-routed tool standardizes on the shared agent-utilities helper
(``resolve_action``), so it must:
  * return a ``list_actions`` discovery payload listing the valid actions, and
  * raise a rich ``ValueError`` mentioning ``list_actions`` on an unknown action.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from scholarx.mcp_server import (
    register_discovery_tools,
    register_search_tools,
    register_storage_tools,
)


class MockMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator


def _register(register_fn):
    mcp = MockMCP()
    register_fn(mcp)
    return next(iter(mcp.tools.values()))


@pytest.mark.parametrize(
    ("register_fn", "expected"),
    [
        (register_search_tools, {"search", "get", "author", "recent"}),
        (register_discovery_tools, {"sources", "categories"}),
        (
            register_storage_tools,
            {"download", "download_url", "bulk_download", "stored", "status", "queue"},
        ),
    ],
)
def test_list_actions_returns_names(register_fn, expected):
    tool = _register(register_fn)
    result = asyncio.run(tool(action="list_actions"))
    assert result["service"] == "scholarx"
    assert set(result["actions"]) == expected


@pytest.mark.parametrize(
    "register_fn",
    [register_search_tools, register_discovery_tools, register_storage_tools],
)
def test_bogus_action_raises_with_hint(register_fn):
    tool = _register(register_fn)
    with pytest.raises(ValueError) as exc:
        asyncio.run(tool(action="totally_bogus_action"))
    assert "list_actions" in str(exc.value)


def test_plural_alias_resolves(monkeypatch):
    """A plural alias (queues -> queue) resolves to the canonical action."""
    client = MagicMock()
    client.get_queue_status.return_value = ["job-1"]
    monkeypatch.setattr("scholarx.mcp_server._get_client", lambda: client)
    tool = _register(register_storage_tools)
    result = asyncio.run(tool(action="queues"))
    assert result == {"downloads": ["job-1"]}
