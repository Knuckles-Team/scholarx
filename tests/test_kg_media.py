"""Native epistemic-graph PDF blob ingestion — Wire-First coverage.

Exercises ``scholarx.kg_media.ingest_pdf`` with a fake MediaStore (no engine required),
asserting the store_media call carries the right media/mime type, source, name and paper
metadata. CONCEPT:AU-KG.ingest.list-durable-media.
"""

from __future__ import annotations

from scholarx.kg_media import ingest_pdf
from scholarx.models import Paper, PaperSource


class _Stored:
    def __init__(self, asset_id, digest):
        self.asset_id = asset_id
        self.digest = digest


class _FakeStore:
    def __init__(self):
        self.calls = []

    def store_media(self, data, *, media_type, mime_type, source, name, extra):
        self.calls.append(
            {
                "data": data,
                "media_type": media_type,
                "mime_type": mime_type,
                "source": source,
                "name": name,
                "extra": extra,
            }
        )
        return _Stored(asset_id="asset-1", digest="deadbeefcafebabe0000")


def _paper() -> Paper:
    return Paper(
        id="2603.09022",
        source=PaperSource.ARXIV,
        title="Emergent Coordination in Multi-Agent Systems",
        doi="10.1234/abc",
        url="https://arxiv.org/abs/2603.09022",
        published_date="2026-03-01",
    )


def test_ingest_pdf_stores_blob_with_metadata(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7 fake bytes")
    store = _FakeStore()

    res = ingest_pdf(str(pdf), paper=_paper(), store=store)

    assert res == {
        "asset_id": "asset-1",
        "digest": "deadbeefcafebabe0000",
        "size_bytes": len(b"%PDF-1.7 fake bytes"),
        "media_type": "document",
    }
    call = store.calls[0]
    assert call["media_type"] == "document"
    assert call["mime_type"] == "application/pdf"
    assert call["source"] == "scholarx"
    assert call["name"] == "Emergent Coordination in Multi-Agent Systems"
    # StrEnum source is flattened to its string value
    assert call["extra"]["source"] == "arxiv"
    assert call["extra"]["doi"] == "10.1234/abc"
    assert call["extra"]["id"] == "2603.09022"


def test_ingest_pdf_noops_without_store(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"x")
    # No injected store + no reachable engine -> clean no-op.
    assert ingest_pdf(str(pdf), paper=_paper()) is None


def test_ingest_pdf_noops_on_missing_file():
    assert ingest_pdf("/no/such/file.pdf", store=_FakeStore()) is None
    assert ingest_pdf(None, store=_FakeStore()) is None
