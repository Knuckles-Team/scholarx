"""CONN-SCHOLARX-CONNECTOR-CONTENT-R002: the citing-papers operation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scholarx.api_client import ScholarXClient
from scholarx.mcp_server import register_search_tools
from scholarx.models import PaperSource
from scholarx.providers.semantic_scholar import SemanticScholarProvider

pytestmark = pytest.mark.spec("CONN-SCHOLARX-CONNECTOR-CONTENT-R002")


class _MCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator


def _client_with(provider):
    client = MagicMock()
    client._providers = {provider.source: provider}
    client.get_citing_papers = lambda *a, **k: ScholarXClient.get_citing_papers(client, *a, **k)
    return client


@pytest.mark.asyncio
async def test_sx_search_citations_returns_documented_fields():
    provider = SemanticScholarProvider()
    response = MagicMock()
    response.json.return_value = {
        "data": [
            {
                "citingPaper": {
                    "paperId": "c1",
                    "title": "A Citing Paper",
                    "authors": [{"name": "Ada"}],
                    "year": 2025,
                    "citationCount": 3,
                    "externalIds": {"DOI": "10.1/x"},
                }
            }
        ]
    }
    provider._get = AsyncMock(return_value=response)
    mcp = _MCP()
    register_search_tools(mcp)
    with patch("scholarx.mcp_server._get_client", return_value=_client_with(provider)):
        out = await mcp.tools["sx_search_citations"](paper_id="abc", sources="semantic_scholar", max_results=5)
    assert provider._get.call_args.args[0] == "/paper/abc/citations"
    assert out["total_count"] == 1
    paper = out["papers"][0]
    assert paper["id"] == "s2:c1"
    assert paper["title"] == "A Citing Paper"
    assert paper["authors"] == ["Ada"]
    assert paper["doi"] == "10.1/x"
    assert paper["citation_count"] == 3
    assert paper["source"] == PaperSource.SEMANTIC_SCHOLAR


@pytest.mark.asyncio
async def test_sx_search_citations_refuses_unsupported_source_and_missing_id():
    from scholarx.providers.arxiv import ArxivProvider

    mcp = _MCP()
    register_search_tools(mcp)
    with patch("scholarx.mcp_server._get_client", return_value=_client_with(ArxivProvider())):
        unsupported = await mcp.tools["sx_search_citations"](paper_id="1", sources="arxiv", max_results=5)
        missing = await mcp.tools["sx_search_citations"](paper_id="", sources="arxiv", max_results=5)
    assert "does not expose citing papers" in unsupported["error"]
    assert "paper_id" in missing["error"]
