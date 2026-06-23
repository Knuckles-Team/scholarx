"""Tests for bounded-concurrency parallel downloads on ScholarXClient.

Covers:
- ``download_papers`` / ``download_urls`` cap in-flight at the semaphore limit.
- Already-stored papers are reported without re-downloading.
- Per-item errors aggregate without failing the whole batch.
"""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scholarx.api_client import ARXIV_DOWNLOAD_CONCURRENCY, ScholarXClient
from scholarx.models import Paper, PaperSource


def _paper(pid: str) -> Paper:
    return Paper(
        id=pid,
        title=f"Paper {pid}",
        authors=["A"],
        source=PaperSource.ARXIV,
        pdf_url=f"https://arxiv.org/pdf/{pid}",
    )


def _client_with_mock_storage(tmp_path) -> ScholarXClient:
    """Build a client whose storage is a MagicMock we can program per-test."""
    client = ScholarXClient.__new__(ScholarXClient)
    client._providers = {}
    storage = MagicMock()
    storage.storage_dir = tmp_path
    client.storage = storage
    return client


# ── download_papers ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_papers_caps_in_flight(tmp_path):
    """Concurrency must never exceed the requested limit."""
    state = {"in_flight": 0, "max_in_flight": 0}
    lock = asyncio.Lock()

    async def slow_download(paper):
        async with lock:
            state["in_flight"] += 1
            state["max_in_flight"] = max(state["max_in_flight"], state["in_flight"])
        try:
            await asyncio.sleep(0.02)
            return Path(f"/tmp/{paper.id}.pdf")
        finally:
            async with lock:
                state["in_flight"] -= 1

    client = _client_with_mock_storage(tmp_path)
    client.storage.get_local_path = MagicMock(return_value=None)
    client.storage.download_paper = slow_download

    papers = [_paper(f"p{i}") for i in range(20)]
    results = await client.download_papers(papers, concurrency=3)

    assert state["max_in_flight"] <= 3
    assert state["max_in_flight"] >= 2
    assert len(results) == 20
    assert all(r["status"] == "downloaded" for r in results)


@pytest.mark.asyncio
async def test_download_papers_default_concurrency(tmp_path):
    """concurrency=0 auto-sizes to the module constant."""
    state = {"in_flight": 0, "max_in_flight": 0}
    lock = asyncio.Lock()

    async def slow_download(paper):
        async with lock:
            state["in_flight"] += 1
            state["max_in_flight"] = max(state["max_in_flight"], state["in_flight"])
        try:
            await asyncio.sleep(0.02)
            return Path(f"/tmp/{paper.id}.pdf")
        finally:
            async with lock:
                state["in_flight"] -= 1

    client = _client_with_mock_storage(tmp_path)
    client.storage.get_local_path = MagicMock(return_value=None)
    client.storage.download_paper = slow_download

    papers = [_paper(f"p{i}") for i in range(ARXIV_DOWNLOAD_CONCURRENCY * 3)]
    await client.download_papers(papers)
    assert state["max_in_flight"] <= ARXIV_DOWNLOAD_CONCURRENCY


@pytest.mark.asyncio
async def test_download_papers_skips_cached(tmp_path):
    """Already-stored papers are reported 'cached' without re-downloading."""
    cached_file = tmp_path / "cached.pdf"
    cached_file.write_bytes(b"%PDF-cached")

    downloaded_ids = []

    async def download(paper):
        downloaded_ids.append(paper.id)
        return Path(f"/tmp/{paper.id}.pdf")

    client = _client_with_mock_storage(tmp_path)

    def get_local_path(pid):
        return cached_file if pid == "cached-1" else None

    client.storage.get_local_path = MagicMock(side_effect=get_local_path)
    client.storage.download_paper = download

    results = await client.download_papers([_paper("cached-1"), _paper("fresh-1")])
    by_id = {r["paper_id"]: r for r in results}

    assert by_id["cached-1"]["status"] == "cached"
    assert by_id["cached-1"]["local_path"] == str(cached_file)
    assert by_id["fresh-1"]["status"] == "downloaded"
    # The cached paper must NOT have been re-downloaded.
    assert downloaded_ids == ["fresh-1"]


@pytest.mark.asyncio
async def test_download_papers_aggregates_errors(tmp_path):
    """A failing item must not fail the whole batch."""

    async def download(paper):
        if paper.id == "boom":
            raise RuntimeError("network exploded")
        if paper.id == "none":
            return None
        return Path(f"/tmp/{paper.id}.pdf")

    client = _client_with_mock_storage(tmp_path)
    client.storage.get_local_path = MagicMock(return_value=None)
    client.storage.download_paper = download

    results = await client.download_papers([_paper("ok"), _paper("boom"), _paper("none")])
    by_id = {r["paper_id"]: r for r in results}

    assert by_id["ok"]["status"] == "downloaded"
    assert by_id["boom"]["status"] == "failed"
    assert "network exploded" in by_id["boom"]["error"]
    assert by_id["none"]["status"] == "failed"


# ── download_urls ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_urls_caps_in_flight(tmp_path, monkeypatch):
    """download_urls shares one client and caps concurrency."""
    state = {"in_flight": 0, "max_in_flight": 0}
    lock = asyncio.Lock()
    clients_created = {"n": 0}

    class _Resp:
        content = b"%PDF-data"

        def raise_for_status(self):
            return None

    class _FakeClient:
        def __init__(self, *a, **k):
            clients_created["n"] += 1

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            async with lock:
                state["in_flight"] += 1
                state["max_in_flight"] = max(state["max_in_flight"], state["in_flight"])
            try:
                await asyncio.sleep(0.02)
                return _Resp()
            finally:
                async with lock:
                    state["in_flight"] -= 1

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    client = _client_with_mock_storage(tmp_path)
    raw_ids = [f"2603.{i:05d}" for i in range(20)]
    results = await client.download_urls(raw_ids, concurrency=4)

    assert clients_created["n"] == 1  # ONE shared client across the batch
    assert state["max_in_flight"] <= 4
    assert state["max_in_flight"] >= 2
    assert len(results) == 20
    assert all(r["status"] == "downloaded" for r in results)
    # Files were actually written.
    assert len(list(tmp_path.glob("*.pdf"))) == 20


@pytest.mark.asyncio
async def test_download_urls_skips_existing(tmp_path, monkeypatch):
    """Existing dest files are reported cached without an HTTP fetch."""
    existing = tmp_path / "2603.00001.pdf"
    existing.write_bytes(b"%PDF-old")

    fetched = []

    class _Resp:
        content = b"%PDF-new"

        def raise_for_status(self):
            return None

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            fetched.append(url)
            return _Resp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    client = _client_with_mock_storage(tmp_path)
    results = await client.download_urls(
        ["https://arxiv.org/abs/2603.00001", "2603.00002"]
    )
    by_id = {r["paper_id"]: r for r in results}

    assert by_id["2603.00001"]["status"] == "cached"
    assert by_id["2603.00002"]["status"] == "downloaded"
    # Only the uncached id triggered an HTTP fetch.
    assert fetched == ["https://arxiv.org/pdf/2603.00002"]


@pytest.mark.asyncio
async def test_download_urls_aggregates_errors(tmp_path, monkeypatch):
    """A failing fetch is captured per-item, not raised for the batch."""

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            if "boom" in url or url.endswith("9999"):
                raise RuntimeError("502 bad gateway")

            class _R:
                content = b"%PDF"

                def raise_for_status(self):
                    return None

            return _R()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    client = _client_with_mock_storage(tmp_path)
    results = await client.download_urls(["2603.00010", "2603.09999"])
    by_id = {r["paper_id"]: r for r in results}

    assert by_id["2603.00010"]["status"] == "downloaded"
    assert by_id["2603.09999"]["status"] == "failed"
    assert "502 bad gateway" in by_id["2603.09999"]["error"]
