import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from scholarx.models import Paper, PaperSource
from scholarx.paper_storage import PaperStorage


@pytest.mark.concept("SX-1.3")
def test_paper_storage_init(tmp_path):
    # Test custom storage directory
    storage = PaperStorage(tmp_path)
    assert storage.storage_dir == tmp_path
    assert (tmp_path / ".metadata").exists()
    assert (tmp_path / ".metadata").is_dir()

    # Test default storage directory fallback
    with patch("scholarx.paper_storage.DEFAULT_STORAGE_DIR", tmp_path / "default_subdir"):
        storage_default = PaperStorage()
        assert storage_default.storage_dir == tmp_path / "default_subdir"
        assert (tmp_path / "default_subdir" / ".metadata").exists()


@pytest.mark.concept("SX-1.3")
@pytest.mark.asyncio
async def test_download_paper_no_pdf_url(temp_storage):
    paper = Paper(id="arxiv:123", title="Sample Title", authors=["Author A"], source=PaperSource.ARXIV, pdf_url="")
    res = await temp_storage.download_paper(paper)
    assert res is None


@pytest.mark.concept("SX-1.3")
@pytest.mark.asyncio
async def test_download_paper_already_exists(temp_storage, sample_arxiv_paper):
    # Pre-create metadata and pdf file to simulate already downloaded
    safe_name = temp_storage._safe_filename(sample_arxiv_paper)
    pdf_file = temp_storage.storage_dir / f"{safe_name}.pdf"
    pdf_file.write_bytes(b"existing content")

    temp_storage._save_metadata(sample_arxiv_paper, pdf_file)

    # Download should return the existing path without initiating a download
    with patch("httpx.AsyncClient") as mock_client_cls:
        res = await temp_storage.download_paper(sample_arxiv_paper)
        assert res == pdf_file
        assert res.read_bytes() == b"existing content"
        mock_client_cls.assert_not_called()


@pytest.mark.concept("SX-1.3")
@pytest.mark.asyncio
async def test_download_paper_success(temp_storage, sample_arxiv_paper):
    # Mock httpx response
    mock_response = MagicMock()
    mock_response.content = b"PDF bytes"
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        res = await temp_storage.download_paper(sample_arxiv_paper)

        # Verify the file was saved
        assert res is not None
        assert res.exists()
        assert res.read_bytes() == b"PDF bytes"

        # Verify metadata is correct and fully validated
        local_meta_path = temp_storage._metadata_dir / f"{temp_storage._id_hash(sample_arxiv_paper.id)}.json"
        assert local_meta_path.exists()
        meta = json.loads(local_meta_path.read_text())

        # Schema-level strict assertions
        assert meta["id"] == sample_arxiv_paper.id
        assert meta["title"] == sample_arxiv_paper.title
        assert meta["authors"] == sample_arxiv_paper.authors
        assert meta["source"] == sample_arxiv_paper.source.value
        assert meta["local_path"] == str(res)


@pytest.mark.concept("SX-1.3")
@pytest.mark.asyncio
async def test_download_paper_http_error(temp_storage, sample_arxiv_paper):
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    # Simulate HTTP error
    mock_client.get = AsyncMock(
        side_effect=httpx.HTTPStatusError("404 Not Found", request=MagicMock(), response=MagicMock())
    )

    with patch("httpx.AsyncClient", return_value=mock_client):
        res = await temp_storage.download_paper(sample_arxiv_paper)
        assert res is None


@pytest.mark.concept("SX-1.3")
def test_get_local_path_invalid_json(temp_storage):
    paper_id = "arxiv:corrupted"

    # Pre-create a corrupted metadata file
    meta_file = temp_storage._metadata_dir / f"{temp_storage._id_hash(paper_id)}.json"
    meta_file.write_text("invalid json content{")

    assert temp_storage.get_local_path(paper_id) is None


@pytest.mark.concept("SX-1.3")
@pytest.mark.parametrize(
    "papers_data",
    [
        (
            [
                ("arxiv:1", "Alpha Title", ["A"], "http://pdf1", b"bytes1", True),
                ("arxiv:2", "Beta Title", ["B"], "http://pdf2", b"", False),
            ]
        )
    ],
)
def test_list_stored_papers(temp_storage, papers_data):
    for pid, title, authors, pdf_url, content, create_file in papers_data:
        paper = Paper(id=pid, title=title, authors=authors, source=PaperSource.ARXIV, pdf_url=pdf_url)
        safe_name = temp_storage._safe_filename(paper)
        pdf_path = temp_storage.storage_dir / f"{safe_name}.pdf"
        if create_file:
            pdf_path.write_bytes(content)
        temp_storage._save_metadata(paper, pdf_path)

    # Save a corrupted metadata file to trigger exception inside list_stored_papers
    corrupt_file = temp_storage._metadata_dir / "corrupted.json"
    corrupt_file.write_text("this is completely invalid")

    stored = temp_storage.list_stored_papers()

    assert len(stored) == 2

    # Assert proper sorting and precise details
    assert stored[0]["title"] == "Alpha Title"
    assert stored[0]["exists"] is True
    assert stored[0]["file_size"] == len(b"bytes1")

    assert stored[1]["title"] == "Beta Title"
    assert stored[1]["exists"] is False
    assert "file_size" not in stored[1]


@pytest.mark.concept("SX-1.3")
def test_get_storage_stats(temp_storage):
    # Create two PDF files of sizes 10 and 20 bytes
    (temp_storage.storage_dir / "file1.pdf").write_bytes(b"x" * 10)
    (temp_storage.storage_dir / "file2.pdf").write_bytes(b"y" * 20)
    # A non-pdf file shouldn't be counted
    (temp_storage.storage_dir / "other.txt").write_bytes(b"z" * 50)

    stats = temp_storage.get_storage_stats()
    assert stats["paper_count"] == 2
    assert stats["total_size_bytes"] == 30
    assert stats["total_size_mb"] == 0.0
