import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import networkx as nx
from scholarx.models import Paper, PaperSource
from scholarx.kg_integration import ScholarXKGBridge


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    # Use a real networkx DiGraph for accurate graph behaviors (add_node, add_edge, has_edge, nodes)
    engine.graph = nx.DiGraph()
    return engine


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    storage.download_paper = AsyncMock()
    return storage


def test_kg_bridge_init(mock_engine, mock_storage):
    bridge = ScholarXKGBridge(mock_engine, mock_storage)
    assert bridge.engine == mock_engine
    assert bridge.storage == mock_storage
    assert bridge._kb_engine is None


def test_get_kb_engine_none():
    bridge = ScholarXKGBridge(None, None)
    assert bridge._get_kb_engine() is None


def test_get_kb_engine_success(mock_engine):
    bridge = ScholarXKGBridge(mock_engine, None)
    mock_kb_instance = MagicMock()

    with patch("agent_utilities.knowledge_graph.kb.ingestion.KBIngestionEngine", return_value=mock_kb_instance):
        kb_engine = bridge._get_kb_engine()
        assert kb_engine == mock_kb_instance
        # Verify second call is cached
        assert bridge._get_kb_engine() == mock_kb_instance


def test_get_kb_engine_import_error(mock_engine):
    bridge = ScholarXKGBridge(mock_engine, None)
    with patch("agent_utilities.knowledge_graph.kb.ingestion.KBIngestionEngine", side_effect=ImportError):
        assert bridge._get_kb_engine() is None


@pytest.mark.asyncio
async def test_ingest_paper_no_pdf_fallback_to_abstract(mock_engine, mock_storage):
    bridge = ScholarXKGBridge(mock_engine, mock_storage)
    mock_storage.download_paper.return_value = None  # PDF download fails

    paper = Paper(
        id="arxiv:1122.3344",
        title="Ingest Abstract Paper",
        abstract="This is a test abstract that will be ingested because PDF downloading failed.",
        authors=["Author One", "Author Two"],
        source=PaperSource.ARXIV,
        doi="10.1234/test.doi",
        url="http://arxiv.org/abs/1122.3344",
        pdf_url="http://arxiv.org/pdf/1122.3344",
        published_date="2026-05-22",
        categories=["cs.AI"],
    )

    res = await bridge.ingest_paper(paper)

    assert res["status"] == "ingested"
    assert res["paper_id"] == "arxiv:1122.3344"
    assert len(res["nodes_created"]) == 2

    # Assert nodes are created in the networkx graph
    graph = mock_engine.graph

    article_id = "article:scholarx:arxiv-1122.3344"
    source_id = "source:scholarx:arxiv-1122.3344"
    author1_id = "person:author-one"
    author2_id = "person:author-two"

    assert article_id in graph.nodes
    assert source_id in graph.nodes
    assert author1_id in graph.nodes
    assert author2_id in graph.nodes

    assert graph.has_edge(article_id, source_id)
    assert graph.has_edge(article_id, author1_id)
    assert graph.has_edge(article_id, author2_id)


@pytest.mark.asyncio
async def test_ingest_paper_abstract_fallback_no_engine(mock_storage):
    # If engine is None, abstract fallback should return skipped status
    bridge = ScholarXKGBridge(None, mock_storage)
    mock_storage.download_paper.return_value = None

    paper = Paper(id="arxiv:9999", title="No Engine Fallback", abstract="Abs", authors=["A"], source=PaperSource.ARXIV)

    res = await bridge.ingest_paper(paper)
    assert res["status"] == "skipped"
    assert "No engine" in res["reason"]


@pytest.mark.asyncio
async def test_ingest_paper_abstract_fallback_exception(mock_engine, mock_storage):
    bridge = ScholarXKGBridge(mock_engine, mock_storage)
    mock_storage.download_paper.return_value = None

    # Corrupt the graph attribute to raise an exception inside _ingest_abstract_only
    mock_engine.graph = None

    paper = Paper(id="arxiv:9999", title="Failing Ingestion", abstract="Abs", authors=["A"], source=PaperSource.ARXIV)

    res = await bridge.ingest_paper(paper)
    assert res["status"] == "error"
    assert "error" in res


@pytest.mark.asyncio
async def test_ingest_paper_with_pdf_success(mock_engine, mock_storage, tmp_path):
    bridge = ScholarXKGBridge(mock_engine, mock_storage)

    pdf_file = tmp_path / "stored_paper.pdf"
    pdf_file.write_bytes(b"pdf data")
    mock_storage.download_paper.return_value = pdf_file

    paper = Paper(
        id="arxiv:5566",
        title="Ingest PDF Paper",
        abstract="Test abstract",
        authors=["Bob Smith"],
        source=PaperSource.ARXIV,
    )

    mock_kb_meta = MagicMock()
    mock_kb_meta.id = "kb-123"
    mock_kb_meta.article_count = 5

    mock_kb_engine = MagicMock()
    mock_kb_engine.ingest_directory = AsyncMock(return_value=mock_kb_meta)

    with patch.object(bridge, "_get_kb_engine", return_value=mock_kb_engine):
        res = await bridge.ingest_paper(paper)

        mock_kb_engine.ingest_directory.assert_called_once_with(
            tmp_path, kb_name="scholarx-research", topic="Ingest PDF Paper"
        )
        assert res["status"] == "ingested"
        assert res["kb_id"] == "kb-123"
        assert res["article_count"] == 5

        # Verify auxiliary author PersonNodes are created
        assert "person:bob-smith" in mock_engine.graph.nodes


@pytest.mark.asyncio
async def test_ingest_paper_with_pdf_engine_error(mock_engine, mock_storage, tmp_path):
    bridge = ScholarXKGBridge(mock_engine, mock_storage)

    pdf_file = tmp_path / "stored_paper.pdf"
    pdf_file.write_bytes(b"pdf data")
    mock_storage.download_paper.return_value = pdf_file

    paper = Paper(
        id="arxiv:5566",
        title="Failing PDF Paper",
        abstract="Test abstract",
        authors=["Bob Smith"],
        source=PaperSource.ARXIV,
    )

    mock_kb_engine = MagicMock()
    mock_kb_engine.ingest_directory = AsyncMock(side_effect=RuntimeError("PDF parsing failed"))

    with patch.object(bridge, "_get_kb_engine", return_value=mock_kb_engine):
        res = await bridge.ingest_paper(paper)
        assert res["status"] == "error"
        assert res["error"] == "PDF parsing failed"


@pytest.mark.asyncio
async def test_ingest_paper_with_pdf_no_kb_engine(mock_engine, mock_storage, tmp_path):
    bridge = ScholarXKGBridge(mock_engine, mock_storage)

    pdf_file = tmp_path / "stored_paper.pdf"
    pdf_file.write_bytes(b"pdf data")
    mock_storage.download_paper.return_value = pdf_file

    paper = Paper(
        id="arxiv:5566",
        title="Skipped PDF Paper",
        abstract="Test abstract",
        authors=["Bob Smith"],
        source=PaperSource.ARXIV,
    )

    with patch.object(bridge, "_get_kb_engine", return_value=None):
        res = await bridge.ingest_paper(paper)
        assert res["status"] == "skipped"
        assert "KBIngestionEngine not available" in res["reason"]


def test_paper_exists_in_kg_no_engine():
    bridge = ScholarXKGBridge(None, None)
    paper = Paper(id="arxiv:1", title="A", authors=["A"], source=PaperSource.ARXIV)
    assert not bridge._paper_exists_in_kg(paper)


def test_paper_exists_in_kg_matching_doi(mock_engine):
    bridge = ScholarXKGBridge(mock_engine, None)

    paper = Paper(
        id="arxiv:123", title="Check DOI Paper", authors=["A"], source=PaperSource.ARXIV, doi="10.1234/found.doi"
    )

    # Pre-populate graph with a source node having the matching DOI
    mock_engine.graph.add_node("source:1", type="source", doi="10.1234/found.doi")

    assert bridge._paper_exists_in_kg(paper)


def test_paper_exists_in_kg_matching_title(mock_engine):
    bridge = ScholarXKGBridge(mock_engine, None)

    paper = Paper(id="arxiv:123", title="Ingested Paper Title", authors=["A"], source=PaperSource.ARXIV)

    # Pre-populate graph with an article node having the matching title
    mock_engine.graph.add_node("article:1", type="article", name="Ingested Paper Title")

    assert bridge._paper_exists_in_kg(paper)


@pytest.mark.asyncio
async def test_ingest_batch(mock_engine, mock_storage):
    bridge = ScholarXKGBridge(mock_engine, mock_storage)

    # Setup 4 papers:
    # 1. Already exists in KG (skipped)
    # 2. Ingest success
    # 3. Ingest error
    # 4. Ingest skipped
    papers = [
        Paper(id="arxiv:1", title="Already Stored", authors=["A"], source=PaperSource.ARXIV, doi="10.1234/already"),
        Paper(id="arxiv:2", title="Success Paper", authors=["A"], source=PaperSource.ARXIV),
        Paper(id="arxiv:3", title="Error Paper", authors=["A"], source=PaperSource.ARXIV),
        Paper(id="arxiv:4", title="Skipped Paper", authors=["A"], source=PaperSource.ARXIV),
    ]

    # Add paper1's DOI to the graph to simulate existence
    mock_engine.graph.add_node("source:existing", type="source", doi="10.1234/already")

    # Mock ingest_paper outcomes
    async def mock_ingest_paper(paper, kb_name):
        if paper.id == "arxiv:2":
            return {"status": "ingested"}
        elif paper.id == "arxiv:3":
            return {"status": "error"}
        else:
            return {"status": "skipped"}

    with patch.object(bridge, "ingest_paper", side_effect=mock_ingest_paper):
        summary = await bridge.ingest_batch(papers, kb_name="batch-test")

        assert summary == {
            "total": 4,
            "ingested": 1,
            "skipped": 2,  # paper1 (exists) and paper4 (skipped status)
            "errors": 1,
            "kb_name": "batch-test",
        }
