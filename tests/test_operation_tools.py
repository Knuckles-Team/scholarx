"""CONN-SCHOLARX-API-COVERAGE-R001: one MCP tool per remaining API operation, coverage at the 90 baseline."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scholarx.mcp_server import register_operation_tools
from scholarx.models import PaperSource

pytestmark = pytest.mark.spec("CONN-SCHOLARX-API-COVERAGE-R001")

ROOT = Path(__file__).resolve().parents[1]


class MockMCP:
    def __init__(self):
        self.tools = {}
        self.kwargs = {}

    def tool(self, *args, **kwargs):
        def decorator(func):
            self.tools[func.__name__] = func
            self.kwargs[func.__name__] = kwargs
            return func

        return decorator


@pytest.fixture
def tools():
    mcp = MockMCP()
    register_operation_tools(mcp)
    return mcp


def test_tools_are_registered_with_hints(tools):
    assert set(tools.tools) == {"sx_enabled_sources", "sx_download_papers", "sx_download_urls"}
    assert tools.kwargs["sx_enabled_sources"]["annotations"]["readOnlyHint"] is True
    assert tools.kwargs["sx_download_papers"]["annotations"]["readOnlyHint"] is False
    assert tools.kwargs["sx_download_urls"]["annotations"]["readOnlyHint"] is False


@pytest.mark.asyncio
async def test_enabled_sources(tools):
    client = MagicMock(enabled_sources=[PaperSource.ARXIV])
    with patch("scholarx.mcp_server._get_client", return_value=client):
        assert await tools.tools["sx_enabled_sources"]() == {"sources": ["arxiv"]}


@pytest.mark.asyncio
async def test_download_papers(tools):
    client = MagicMock()
    client.get_paper = AsyncMock(side_effect=lambda src, pid: MagicMock(id=pid))
    client.download_papers = AsyncMock(return_value=[{"paper_id": "1", "status": "downloaded"}])
    with patch("scholarx.mcp_server._get_client", return_value=client):
        out = await tools.tools["sx_download_papers"](source="arxiv", paper_ids="1,2", concurrency=3)
    assert out == {"results": [{"paper_id": "1", "status": "downloaded"}]}
    assert len(client.download_papers.call_args.args[0]) == 2
    assert client.download_papers.call_args.kwargs == {"concurrency": 3}


@pytest.mark.asyncio
async def test_download_papers_rejects_bad_input(tools):
    with patch("scholarx.mcp_server._get_client", return_value=MagicMock()):
        out = await tools.tools["sx_download_papers"](source="nope", paper_ids="1", concurrency=0)
    assert "error" in out


@pytest.mark.asyncio
async def test_download_urls(tools):
    client = MagicMock()
    client.download_urls = AsyncMock(return_value=[{"paper_id": "2603.09022", "status": "cached"}])
    with patch("scholarx.mcp_server._get_client", return_value=client):
        out = await tools.tools["sx_download_urls"](paper_ids="2603.09022, 2603.09023", concurrency=0)
    assert out["results"][0]["status"] == "cached"
    assert client.download_urls.call_args.args[0] == ["2603.09022", "2603.09023"]


@pytest.mark.asyncio
async def test_download_urls_requires_ids_and_maps_limit_errors(tools):
    client = MagicMock()
    client.download_urls = AsyncMock(side_effect=ValueError("limit"))
    with patch("scholarx.mcp_server._get_client", return_value=client):
        assert "error" in await tools.tools["sx_download_urls"](paper_ids="", concurrency=0)
        assert "error" in await tools.tools["sx_download_urls"](paper_ids="1", concurrency=0)


def test_coverage_gate_holds_at_the_baseline():
    script = (ROOT / "scripts/verify_api_integration.py").read_text()
    assert '"scholarx": 90.0' in script
    # The checker names the agent from the directory; run it from a directory called scholarx.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, importlib.util as u;"
            "s=u.spec_from_file_location('v', sys.argv[1]);m=u.module_from_spec(s);s.loader.exec_module(m);"
            "r=m.verify_agent(sys.argv[2]);print(r['coverage'])",
            str(ROOT / "scripts/verify_api_integration.py"),
            str(ROOT),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert float(result.stdout.strip()) >= 90.0
