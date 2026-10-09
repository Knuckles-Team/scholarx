"""Native epistemic-graph typed-node ingestion — Wire-First coverage.

Exercises the real ``ingest_entities`` / ``ingest_documents`` / ``ingest_papers`` seam with a
fake SDK ingest **transport** (one level below the facade, per
FLEET-SDK-MIGRATION-RECIPE.md §2b) — no engine required — asserting the records/relationships
the SDK's own request builder produces and the ScholarX Paper -> :Paper/:PaperSource/
:ResearchCategory/:Person mapping. CONCEPT:AU-KG.ingest.enterprise-source-extractor.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from agent_connector_sdk.ingest import IngestError, KnowledgeIngest

from scholarx.kg_ingest import ingest_documents, ingest_entities, ingest_papers, paper_entities
from scholarx.models import Paper, PaperSource


class _FakeTransport:
    def __init__(self) -> None:
        self.requests = []

    async def source_status(self, connector, stream):
        return SimpleNamespace(accepted_checkpoint=None)

    async def submit(self, request):
        self.requests.append(request)
        return SimpleNamespace(
            affected_count=len(request.records),
            relationship_count=len(request.relationships),
        )

    async def store_blob(self, data):
        raise AssertionError("this test's ingestion carries no media")


@pytest.fixture
def ingest():
    transport = _FakeTransport()
    return KnowledgeIngest(transport, loop=None), transport


def _paper() -> Paper:
    return Paper(
        id="2603.09022",
        source=PaperSource.ARXIV,
        title="Emergent Coordination in Multi-Agent Systems",
        authors=["Ada Lovelace", "Alan Turing"],
        abstract="We study emergent coordination.",
        categories=["cs.AI", "cs.MA"],
        published_date="2026-03-01",
        doi="10.1234/abc",
        url="https://arxiv.org/abs/2603.09022",
        pdf_url="https://arxiv.org/pdf/2603.09022",
        citation_count=7,
    )


@pytest.mark.asyncio
async def test_ingest_entities_writes_nodes_and_edges(ingest):
    service, transport = ingest
    res = await ingest_entities(
        [{"id": "a", "node_type": "Paper", "name": "p"}, {"id": "b", "node_type": "PaperSource"}],
        [{"source": "a", "target": "b", "relationship": "publishedInSource"}],
        ingest=service,
    )
    assert res == {"nodes": 2, "edges": 1}
    assert len(transport.requests) == 1
    request = transport.requests[0]
    by_id = {r.record_id: r for r in request.records}
    assert set(by_id) == {"a", "b"}
    assert request.relationships[0].source.record_id == "a"
    assert request.relationships[0].target.record_id == "b"
    assert request.relationships[0].relation_reference.endswith("/relations/publishedInSource")


def test_paper_entities_maps_paper_source_category_author():
    entities, rels = paper_entities([_paper()])
    by_id = {e["id"]: e for e in entities}
    pid = "scholarx:paper:2603.09022"
    assert by_id[pid]["node_type"] == "Paper"
    assert by_id[pid]["externalToolId"] == "2603.09022"
    assert by_id[pid]["doi"] == "10.1234/abc"
    # abstract carried as searchable text (document modality)
    assert by_id[pid]["text"] == "We study emergent coordination."
    assert by_id[pid]["citationCount"] == 7
    assert by_id["scholarx:source:arxiv"]["node_type"] == "PaperSource"
    assert by_id["scholarx:category:cs.ai"]["node_type"] == "ResearchCategory"
    assert by_id["scholarx:person:ada-lovelace"]["node_type"] == "Person"
    rel_types = {(r["relationship"]) for r in rels}
    assert rel_types == {"publishedInSource", "hasCategory", "authoredBy"}
    # one publishedInSource, two categories, two authors
    assert sum(1 for r in rels if r["relationship"] == "authoredBy") == 2
    assert sum(1 for r in rels if r["relationship"] == "hasCategory") == 2


@pytest.mark.asyncio
async def test_ingest_papers_dedups_shared_nodes(ingest):
    service, transport = ingest
    # two arXiv papers sharing a source + one author
    p1 = _paper()
    p2 = Paper(
        id="2603.10000",
        source=PaperSource.ARXIV,
        title="Follow-up study",
        authors=["Ada Lovelace"],
        categories=["cs.AI"],
    )
    res = await ingest_papers([p1, p2], ingest=service)
    assert res is not None and len(transport.requests) == 1
    # shared scholarx:source:arxiv, scholarx:person:ada-lovelace, scholarx:category:cs.ai
    # written only once each
    record_ids = [r.record_id for r in transport.requests[0].records]
    assert record_ids.count("scholarx:source:arxiv") == 1


@pytest.mark.asyncio
async def test_ingest_documents_writes_document_nodes(ingest):
    service, transport = ingest
    res = await ingest_documents(
        [{"id": "scholarx:document:x", "text": "hello", "source_uri": "http://x"}],
        ingest=service,
    )
    assert res == {"nodes": 1, "edges": 0}
    record = transport.requests[0].records[0]
    assert record.record_id == "scholarx:document:x"
    assert record.payload["text"] == "hello"


@pytest.mark.asyncio
async def test_missing_node_type_is_rejected(ingest):
    service, _ = ingest
    with pytest.raises(IngestError, match="needs an id and a node_type"):
        await ingest_entities([{"id": "a"}], ingest=service)


@pytest.mark.asyncio
async def test_empty_ingest_entities_is_rejected(ingest):
    service, _ = ingest
    with pytest.raises(IngestError, match="at least one entity"):
        await ingest_entities([], ingest=service)
