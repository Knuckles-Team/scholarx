from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Context

from scholarx.mcp_server import (
    get_mcp_instance,
    mcp_server,
    register_prompts,
)
from scholarx.models import Paper, PaperSource, SearchResult, SourceStatus

# ── Mock MCP Helper ─────────────────────────────────────────────────────────


class MockMCP:
    def __init__(self):
        self.tools = {}
        self.prompts = {}

    def tool(self, *args, **kwargs):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator

    def prompt(self, *args, **kwargs):
        def decorator(func):
            self.prompts[func.__name__] = func
            return func

        return decorator


# ── Tool Call Wrappers ──────────────────────────────────────────────────────


async def call_sx_search(
    action="search",
    query="",
    sources="",
    categories="",
    max_results=20,
    sort_by="relevance",
    title="",
    paper_id="",
    author="",
    days=1,
    ctx=None,
):
    from scholarx.mcp_server import register_search_tools

    mcp = MockMCP()
    register_search_tools(mcp)
    sx_search = mcp.tools["sx_search"]
    return await sx_search(
        action=action,
        query=query,
        sources=sources,
        categories=categories,
        max_results=max_results,
        sort_by=sort_by,
        title=title,
        paper_id=paper_id,
        author=author,
        days=days,
        ctx=ctx,
    )


async def call_sx_info(action="sources", source="", ctx=None):
    from scholarx.mcp_server import register_discovery_tools

    mcp = MockMCP()
    register_discovery_tools(mcp)
    sx_info = mcp.tools["sx_info"]
    return await sx_info(action=action, source=source, ctx=ctx)


async def call_sx_storage(action="stored", source="", paper_ids="", job_id="", ctx=None):
    from scholarx.mcp_server import register_storage_tools

    mcp = MockMCP()
    register_storage_tools(mcp)
    sx_storage = mcp.tools["sx_storage"]
    return await sx_storage(action=action, source=source, paper_ids=paper_ids, job_id=job_id, ctx=ctx)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.storage = MagicMock()
    return client


# ── Search Tools Tests ───────────────────────────────────────────────────────


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_search_get_paper(mock_client):
    mock_ctx = AsyncMock(spec=Context)

    # Test error when missing paper_id or source
    err1 = await call_sx_search(action="get")
    assert err1 == {"error": "Both 'sources' and 'paper_id' required for 'get' action"}

    err2 = await call_sx_search(action="get", sources="arxiv")
    assert err2 == {"error": "Both 'sources' and 'paper_id' required for 'get' action"}

    # Mock success get_paper
    mock_paper = Paper(id="arxiv:1234.5678", title="Sample Paper", authors=["Author One"], source=PaperSource.ARXIV)
    mock_client.get_paper = AsyncMock(return_value=mock_paper)

    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        res = await call_sx_search(action="get", sources="arxiv", paper_id="1234.5678", ctx=mock_ctx)

        mock_client.get_paper.assert_called_once_with(PaperSource.ARXIV, "1234.5678")
        assert res["id"] == "arxiv:1234.5678"
        assert res["title"] == "Sample Paper"
        mock_ctx.report_progress.assert_any_call(10, 100)
        mock_ctx.report_progress.assert_any_call(100, 100)

    # Test paper not found
    mock_client.get_paper = AsyncMock(return_value=None)
    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        res = await call_sx_search(action="get", sources="arxiv", paper_id="9999")
        assert res == {"error": "Paper not found"}


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_search_author(mock_client):
    # Test error when author missing
    err = await call_sx_search(action="author")
    assert err == {"error": "'author' is required for 'author' action"}

    # Test author search success
    mock_result = SearchResult(
        papers=[Paper(id="arxiv:1", title="Paper One", authors=["Alice"], source=PaperSource.ARXIV)],
        total_count=1,
        sources_queried=[PaperSource.ARXIV],
        sources_failed=[],
        deduplicated_count=0,
        query="Alice",
    )
    mock_client.search = AsyncMock(return_value=mock_result)

    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        res = await call_sx_search(action="author", author="Alice")
        assert res["total_count"] == 1
        assert len(res["papers"]) == 1
        assert res["papers"][0]["title"] == "Paper One"


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_search_recent(mock_client):
    mock_result = SearchResult(
        papers=[Paper(id="arxiv:2", title="Paper Two", authors=["Bob"], source=PaperSource.ARXIV)],
        total_count=1,
        sources_queried=[PaperSource.ARXIV],
        sources_failed=[],
        deduplicated_count=0,
        query="recent papers",
    )
    mock_client.get_recent_papers = AsyncMock(return_value=mock_result)

    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        # Without explicit categories, defaults are used
        res = await call_sx_search(action="recent", sources="arxiv")
        mock_client.get_recent_papers.assert_called_once_with(
            ["cs.AI", "cs.MA", "cs.SE", "cs.LG"], 1, [PaperSource.ARXIV]
        )
        assert res["total_count"] == 1
        assert res["sources_queried"] == ["arxiv"]


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_search_default_search(mock_client):
    mock_ctx = AsyncMock(spec=Context)
    mock_result = SearchResult(
        papers=[Paper(id="arxiv:3", title="Paper Three", authors=["Charlie"], source=PaperSource.ARXIV)],
        total_count=1,
        sources_queried=[PaperSource.ARXIV],
        sources_failed=[],
        deduplicated_count=0,
        query="multi-agent",
    )
    mock_client.search = AsyncMock(return_value=mock_result)

    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        res = await call_sx_search(
            action="search",
            query="multi-agent",
            sources="arxiv",
            categories="cs.MA",
            paper_id="arxiv:3",
            title="Paper Three",
            ctx=mock_ctx,
        )
        assert res["total_count"] == 1
        assert res["sources_queried"] == ["arxiv"]
        assert res["deduplicated_count"] == 0
        mock_ctx.report_progress.assert_any_call(10, 100)
        mock_ctx.report_progress.assert_any_call(100, 100)


# ── Discovery Tools Tests ───────────────────────────────────────────────────


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_info_categories(mock_client):
    mock_client.list_categories = AsyncMock(return_value={"arxiv": [{"id": "cs.AI", "name": "AI"}]})

    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        res = await call_sx_info(action="categories", source="arxiv")
        mock_client.list_categories.assert_called_once_with(PaperSource.ARXIV)
        assert "arxiv" in res


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_info_sources(mock_client):
    mock_ctx = AsyncMock(spec=Context)
    mock_client.get_source_status = AsyncMock(return_value=[SourceStatus(source=PaperSource.ARXIV, available=True)])

    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        res = await call_sx_info(action="sources", ctx=mock_ctx)
        assert len(res["sources"]) == 1
        assert res["sources"][0]["source"] == "arxiv"
        mock_ctx.report_progress.assert_any_call(10, 100)
        mock_ctx.report_progress.assert_any_call(100, 100)


# ── Storage Tools Tests ──────────────────────────────────────────────────────


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_storage_basic_actions(mock_client):
    # Action "stored"
    mock_client.storage.list_stored_papers = MagicMock(return_value=[{"id": "arxiv:1"}])
    mock_client.storage.get_storage_stats = MagicMock(return_value={"total_papers": 1})

    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        res = await call_sx_storage(action="stored")
        assert res["papers"] == [{"id": "arxiv:1"}]
        assert res["stats"] == {"total_papers": 1}

    # Action "status" error
    err = await call_sx_storage(action="status")
    assert err == {"error": "'job_id' required for 'status' action"}

    # Action "status" not found
    mock_client.get_download_status = MagicMock(return_value=None)
    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        res = await call_sx_storage(action="status", job_id="job-123")
        assert res == {"error": "Job job-123 not found."}

    # Action "status" success
    mock_client.get_download_status = MagicMock(return_value={"status": "pending"})
    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        res = await call_sx_storage(action="status", job_id="job-123")
        assert res == {"status": "pending"}

    # Action "queue"
    mock_client.get_queue_status = MagicMock(return_value={"job-123": {"status": "running"}})
    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        res = await call_sx_storage(action="queue")
        assert res == {"downloads": {"job-123": {"status": "running"}}}

    # Unknown action now raises a rich did-you-mean error pointing at list_actions
    # (standardized via the shared agent-utilities action-discovery helper).
    with pytest.raises(ValueError, match="list_actions"):
        await call_sx_storage(action="nonsense")


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_storage_download_already_exists(mock_client):
    # Test missing source or paper_ids
    err = await call_sx_storage(action="download")
    assert err == {"error": "'source' and 'paper_ids' required for 'download' action"}

    # Mock storage listing to contain the paper already
    mock_client.storage.list_stored_papers = MagicMock(
        return_value=[{"id": "arxiv:1234.5678", "source": "arxiv", "local_path": "/tmp/stored.pdf"}]
    )

    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        with patch("pathlib.Path.exists", return_value=True):
            res = await call_sx_storage(action="download", source="arxiv", paper_ids="1234.5678")
            assert res["status"] == "already_exists"
            assert res["local_path"] == "/tmp/stored.pdf"


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_storage_download_new(mock_client):
    mock_client.storage.list_stored_papers = MagicMock(return_value=[])

    # Paper not found
    mock_client.get_paper = AsyncMock(return_value=None)
    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        res = await call_sx_storage(action="download", source="arxiv", paper_ids="1234.5678")
        assert res == {"error": "Paper not found"}

    # Paper found, successful download
    mock_paper = Paper(id="arxiv:1234.5678", title="A", authors=["B"], source=PaperSource.ARXIV)
    mock_client.get_paper = AsyncMock(return_value=mock_paper)
    mock_client.download_paper = AsyncMock(return_value="/tmp/downloaded.pdf")
    mock_ctx = AsyncMock(spec=Context)

    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        res = await call_sx_storage(action="download", source="arxiv", paper_ids="1234.5678", ctx=mock_ctx)
        assert res["status"] == "downloaded"
        assert res["local_path"] == "/tmp/downloaded.pdf"
        mock_ctx.report_progress.assert_any_call(10, 100)
        mock_ctx.report_progress.assert_any_call(100, 100)


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_storage_download_url(mock_client, tmp_path):
    # Test error when missing paper_ids
    err = await call_sx_storage(action="download_url")
    assert err == {"error": "'paper_ids' required for 'download_url' action"}

    destination = tmp_path / "2603.09022.pdf"
    mock_client.storage.download_arxiv_id = AsyncMock(
        side_effect=[
            (destination, len(b"%PDF-1.7"), True),
            (destination, len(b"%PDF-1.7"), False),
            RuntimeError("network timeout"),
        ]
    )

    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        # Test download with URL
        res = await call_sx_storage(action="download_url", paper_ids="https://arxiv.org/abs/2603.09022")

        results = res["results"]
        assert len(results) == 1
        assert results[0]["paper_id"] == "2603.09022"
        assert results[0]["status"] == "downloaded"
        assert results[0]["size_bytes"] == len(b"%PDF-1.7")

        # Try again, now it already exists
        res_exists = await call_sx_storage(action="download_url", paper_ids="https://arxiv.org/abs/2603.09022")
        assert res_exists["results"][0]["status"] == "already_exists"

        # Exceptions are sanitized at the MCP boundary.
        res_fail = await call_sx_storage(action="download_url", paper_ids="9999.9999")
        assert res_fail["results"][0] == {
            "paper_id": "9999.9999",
            "status": "failed",
            "error": "Operation failed",
        }


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_storage_download_url_rejects_traversal(mock_client):
    mock_client.storage.download_arxiv_id = AsyncMock()

    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        result = await call_sx_storage(
            action="download_url", paper_ids="../../outside,https://example.com/a.pdf"
        )

    assert [item["status"] for item in result["results"]] == ["rejected", "rejected"]
    mock_client.storage.download_arxiv_id.assert_not_awaited()


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_storage_bulk_download(mock_client):
    # Test error when arguments missing
    err = await call_sx_storage(action="bulk_download")
    assert err == {"error": "'source' and 'paper_ids' required for 'bulk_download' action"}

    # Setup stored papers and new paper mocking
    mock_client.storage.list_stored_papers = MagicMock(
        return_value=[{"id": "arxiv:1111", "source": "arxiv", "local_path": "/tmp/stored1.pdf"}]
    )

    mock_paper2 = Paper(id="arxiv:2222", title="P2", authors=["A"], source=PaperSource.ARXIV)

    # Mock first to exist locally, second to be queued, third not found
    mock_client.get_paper = AsyncMock(side_effect=[mock_paper2, None])
    mock_client.queue_download = MagicMock(return_value="job-queued")

    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        with patch("pathlib.Path.exists", return_value=True):
            res = await call_sx_storage(action="bulk_download", source="arxiv", paper_ids="1111,2222,3333")

            results = res["results"]
            assert len(results) == 3
            # 1111 already exists
            assert results[0] == {"paper_id": "1111", "status": "already_exists", "local_path": "/tmp/stored1.pdf"}
            # 2222 is queued
            assert results[1] == {"paper_id": "2222", "status": "queued", "job_id": "job-queued"}
            # 3333 not found
            assert results[2] == {"paper_id": "3333", "status": "failed", "error": "Paper not found"}


# ── Storage Tools Tests: characterization of branches the pre-existing suite
#    above did not exercise (CXA-FL-SCHOLARX-01) ────────────────────────────


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_storage_download_invalid_source(mock_client):
    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        res = await call_sx_storage(action="download", source="not-a-real-source", paper_ids="1234.5678")
    assert res == {"error": "Invalid paper source"}


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_storage_download_paper_ids_too_long(mock_client):
    huge = "1," * 3000
    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        res = await call_sx_storage(action="download", source="arxiv", paper_ids=huge)
    assert res == {"error": "'paper_ids' input limit exceeded"}


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_storage_download_timeout_queues(mock_client):
    # Budget shrunk so a slow client.download_paper trips the inline wait_for
    # timeout deterministically and fast, instead of waiting out the real
    # 60s _INLINE_DOWNLOAD_BUDGET_S.
    mock_client.storage.list_stored_papers = MagicMock(return_value=[])
    mock_paper = Paper(id="arxiv:1234.5678", title="A", authors=["B"], source=PaperSource.ARXIV)
    mock_client.get_paper = AsyncMock(return_value=mock_paper)

    async def _slow_download(paper):
        import asyncio as _asyncio

        await _asyncio.sleep(0.2)
        return "/tmp/never.pdf"

    mock_client.download_paper = _slow_download
    mock_client.queue_download = MagicMock(return_value="job-bg-1")

    with (
        patch("scholarx.mcp_server._get_client", return_value=mock_client),
        patch("scholarx.mcp_server._INLINE_DOWNLOAD_BUDGET_S", 0.01),
    ):
        res = await call_sx_storage(action="download", source="arxiv", paper_ids="1234.5678")

    assert res["status"] == "queued"
    assert res["job_id"] == "job-bg-1"
    assert res["paper_id"] == "arxiv:1234.5678"
    mock_client.queue_download.assert_called_once_with(mock_paper)


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_storage_download_url_too_long(mock_client):
    huge = "a," * 3000
    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        res = await call_sx_storage(action="download_url", paper_ids=huge)
    assert res == {"error": "'paper_ids' input limit exceeded"}


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_storage_download_url_too_many_ids(mock_client):
    ids = ",".join(f"{i:04d}.{i:04d}" for i in range(21))
    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        res = await call_sx_storage(action="download_url", paper_ids=ids)
    assert res == {"error": "direct download count limit exceeded"}


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_storage_download_url_deadline_exceeded_precheck(mock_client):
    # Deadline set in the past (negative budget) so the very first id hits the
    # manual "remaining <= 0" pre-check raise, not the wait_for() timeout path.
    mock_client.storage.download_arxiv_id = AsyncMock()
    with (
        patch("scholarx.mcp_server._get_client", return_value=mock_client),
        patch("scholarx.mcp_server._MAX_DIRECT_DOWNLOAD_SECONDS", -1.0),
    ):
        res = await call_sx_storage(
            action="download_url", paper_ids="2603.09022,2603.09023"
        )
    results = res["results"]
    assert len(results) == 1
    assert results[0] == {
        "paper_id": "2603.09022",
        "status": "failed",
        "error": "direct download time limit exceeded",
    }
    mock_client.storage.download_arxiv_id.assert_not_awaited()


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_storage_download_url_wait_for_timeout(mock_client):
    # Positive-but-tiny budget so the pre-check passes but the per-id
    # asyncio.wait_for() around download_arxiv_id itself times out.
    async def _slow_download_arxiv_id(pid):
        import asyncio as _asyncio

        await _asyncio.sleep(0.3)
        return ("/tmp/x.pdf", 1, True)

    mock_client.storage.download_arxiv_id = _slow_download_arxiv_id
    with (
        patch("scholarx.mcp_server._get_client", return_value=mock_client),
        patch("scholarx.mcp_server._MAX_DIRECT_DOWNLOAD_SECONDS", 0.02),
    ):
        res = await call_sx_storage(action="download_url", paper_ids="2603.09022")
    results = res["results"]
    assert results == [
        {
            "paper_id": "2603.09022",
            "status": "failed",
            "error": "direct download time limit exceeded",
        }
    ]


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_storage_bulk_download_invalid_source(mock_client):
    mock_client.storage.list_stored_papers = MagicMock(return_value=[])
    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        res = await call_sx_storage(action="bulk_download", source="not-a-real-source", paper_ids="1111")
    assert res == {"error": "Invalid paper source"}


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_storage_bulk_download_paper_ids_too_long(mock_client):
    huge = "1," * 3000
    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        res = await call_sx_storage(action="bulk_download", source="arxiv", paper_ids=huge)
    assert res == {"error": "'paper_ids' input limit exceeded"}


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_storage_bulk_download_too_many_ids(mock_client):
    ids = ",".join(str(i) for i in range(101))
    with patch("scholarx.mcp_server._get_client", return_value=mock_client):
        res = await call_sx_storage(action="bulk_download", source="arxiv", paper_ids=ids)
    assert res == {"error": "bulk download count limit exceeded"}


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_storage_bulk_download_deadline_exceeded_precheck(mock_client):
    mock_client.storage.list_stored_papers = MagicMock(return_value=[])
    mock_client.get_paper = AsyncMock()
    with (
        patch("scholarx.mcp_server._get_client", return_value=mock_client),
        patch("scholarx.mcp_server._MAX_BULK_DOWNLOAD_SECONDS", -1.0),
    ):
        res = await call_sx_storage(action="bulk_download", source="arxiv", paper_ids="1111,2222")
    results = res["results"]
    assert len(results) == 1
    assert results[0] == {
        "paper_id": "1111",
        "status": "failed",
        "error": "bulk download time limit exceeded",
    }
    mock_client.get_paper.assert_not_awaited()


@pytest.mark.concept("SX-1.0")
@pytest.mark.asyncio
async def test_sx_storage_bulk_download_wait_for_timeout(mock_client):
    mock_client.storage.list_stored_papers = MagicMock(return_value=[])

    async def _slow_get_paper(source, pid):
        import asyncio as _asyncio

        await _asyncio.sleep(0.3)
        return None

    mock_client.get_paper = _slow_get_paper
    with (
        patch("scholarx.mcp_server._get_client", return_value=mock_client),
        patch("scholarx.mcp_server._MAX_BULK_DOWNLOAD_SECONDS", 0.02),
    ):
        res = await call_sx_storage(action="bulk_download", source="arxiv", paper_ids="1111")
    assert res["results"] == [
        {
            "paper_id": "1111",
            "status": "failed",
            "error": "bulk download time limit exceeded",
        }
    ]


# ── Prompts Tests ───────────────────────────────────────────────────────────


@pytest.mark.concept("SX-1.4")
def test_prompts():
    mcp = MockMCP()
    register_prompts(mcp)

    assert "agent_utilities_enhancement_scan" in mcp.prompts
    assert "biomimicry_innovation_scan" in mcp.prompts

    prompt1 = mcp.prompts["agent_utilities_enhancement_scan"]()
    assert "Search for recent papers" in prompt1

    prompt2 = mcp.prompts["biomimicry_innovation_scan"]()
    assert "Search bioRxiv, PMC for" in prompt2


# ── Factory & Entrypoint Tests ──────────────────────────────────────────────


@pytest.mark.concept("SX-1.0")
def test_get_mcp_instance():
    with patch("agent_utilities.mcp.server_factory.create_mcp_server", return_value=(MagicMock(), MagicMock(), [])):
        args, mcp = get_mcp_instance()
        assert args is not None
        assert mcp is not None


@pytest.mark.concept("SX-1.0")
def test_mcp_server_run_stdio():
    mock_args = MagicMock()
    mock_args.transport = "stdio"

    mock_mcp = MagicMock()

    with patch("scholarx.mcp_server.get_mcp_instance", return_value=(mock_args, mock_mcp)):
        mcp_server()
        mock_mcp.run.assert_called_once_with(transport="stdio")


@pytest.mark.concept("SX-1.0")
def test_mcp_server_run_http():
    mock_args = MagicMock()
    mock_args.transport = "http"
    mock_args.host = "1.2.3.4"
    mock_args.port = "8888"

    mock_mcp = MagicMock()

    with patch("scholarx.mcp_server.get_mcp_instance", return_value=(mock_args, mock_mcp)):
        mcp_server()
        mock_mcp.run.assert_called_once_with(transport="streamable-http", host="1.2.3.4", port=8888)
