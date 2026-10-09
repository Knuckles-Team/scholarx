"""Native epistemic-graph PDF blob ingestion — Wire-First coverage.

Exercises ``scholarx.kg_media.ingest_pdf`` with a fake SDK ingest transport (no engine
required), asserting the stored media asset's mime type, name and paper-metadata properties.
CONCEPT:AU-KG.ingest.list-durable-media.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from agent_connector_sdk.ingest import KnowledgeIngest

from scholarx.kg_media import ingest_pdf
from scholarx.models import Paper, PaperSource


class _FakeTransport:
    def __init__(self) -> None:
        self.requests = []

    async def source_status(self, connector, stream):
        return SimpleNamespace(accepted_checkpoint=None)

    async def submit(self, request):
        self.requests.append(request)
        return SimpleNamespace(affected_count=len(request.records), relationship_count=0)

    async def store_blob(self, data):
        return "deadbeefcafebabe0000"


@pytest.fixture
def ingest():
    transport = _FakeTransport()
    return KnowledgeIngest(transport, loop=None), transport


def _paper() -> Paper:
    return Paper(
        id="2603.09022",
        source=PaperSource.ARXIV,
        title="Emergent Coordination in Multi-Agent Systems",
        doi="10.1234/abc",
        url="https://arxiv.org/abs/2603.09022",
        published_date="2026-03-01",
    )


@pytest.mark.asyncio
async def test_ingest_pdf_stores_blob_with_metadata(tmp_path, ingest):
    service, transport = ingest
    pdf = tmp_path / "paper.pdf"
    data = b"%PDF-1.7 fake bytes"
    pdf.write_bytes(data)

    res = await ingest_pdf(str(pdf), paper=_paper(), ingest=service)

    assert res is not None
    assert res["media_type"] == "document"
    assert res["size_bytes"] == len(data)
    assert len(transport.requests) == 1
    record = transport.requests[0].records[0]
    assert record.payload["mime_type"] == "application/pdf"
    assert record.payload["name"] == "Emergent Coordination in Multi-Agent Systems"
    # StrEnum source is flattened to its string value
    assert record.payload["source"] == "arxiv"
    assert record.payload["doi"] == "10.1234/abc"
    assert record.payload["id"] == "2603.09022"


@pytest.mark.asyncio
async def test_ingest_pdf_noops_without_engine(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"x")
    # No injected ingest + no reachable engine -> clean no-op.
    assert await ingest_pdf(str(pdf), paper=_paper()) is None


@pytest.mark.asyncio
async def test_ingest_pdf_noops_on_missing_file(ingest):
    service, _ = ingest
    assert await ingest_pdf("/no/such/file.pdf", ingest=service) is None
    assert await ingest_pdf(None, ingest=service) is None
