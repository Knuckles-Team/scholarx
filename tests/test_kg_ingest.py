"""Native epistemic-graph typed-node ingestion — Wire-First coverage.

Exercises the real ``ingest_entities`` / ``ingest_documents`` / ``ingest_papers`` seam with a
fake engine client (no engine required), asserting the single-transaction node/edge staging and commit and the
ScholarX Paper -> :Paper/:PaperSource/:ResearchCategory/:Person mapping.
CONCEPT:AU-KG.ingest.enterprise-source-extractor.
"""

from __future__ import annotations

from typing import Any

import msgpack
import pytest
from agent_utilities.knowledge_graph.memory.native_ingest import NativeIngestError
from agent_utilities.security.brain_context import ActorContext, use_actor
from agent_utilities.models.company_brain import ActorType
from agent_utilities.knowledge_graph.core.session import GraphSession, use_session

from scholarx.kg_ingest import ingest_documents, ingest_entities, ingest_papers, paper_entities
from scholarx.models import Paper, PaperSource


@pytest.fixture(autouse=True)
def _governed_session():
    actor = ActorContext(
        actor_id="subject:opaque:synthetic",
        actor_type=ActorType.AUTOMATED_SERVICE,
        roles=(),
        tenant_id="tenant:opaque:synthetic",
        authenticated=True,
    )
    session = GraphSession(
        actor=actor,
        tenant=actor.tenant_id,
        scopes=frozenset({"kg:write"}),
        graph="graph:opaque:synthetic",
        policy_version="policy:opaque:synthetic",
        audience="epistemic-graph",
    )
    with use_actor(actor), use_session(session):
        yield


class _FakeNodes:
    def __init__(self) -> None:
        self.values: dict[str, dict[str, Any]] = {}

    def properties(self, node_id: str) -> dict[str, Any] | None:
        return self.values.get(node_id)

    def list(self) -> list[tuple[str, dict[str, Any]]]:
        return list(self.values.items())


class _FakeChanges:
    def __init__(self, nodes: _FakeNodes) -> None:
        self.nodes = nodes
        self.edges: list[tuple[str, str, dict[str, Any]]] = []
        self.applied: list[dict[str, Any]] = []
        self.records: dict[str, dict[str, Any]] = {}
        self.versions: dict[str, dict[str, Any]] = {}

    def get(self, envelope_id: str) -> dict[str, Any] | None:
        return self.records.get(envelope_id)

    def content_version(self, object_id: str) -> dict[str, Any] | None:
        return self.versions.get(object_id)

    def cursor(self, _source: str, _partition: str = "") -> None:
        return None

    def apply(self, envelope: dict[str, Any]) -> dict[str, Any]:
        self.applied.append(envelope)
        mutation = envelope["mutation"]
        for operation in mutation["operations"]:
            method = operation["method"]
            params = method["params"]
            properties = msgpack.unpackb(params["properties_msgpack"], raw=False)
            if method["method"] == "AddNode":
                self.nodes.values[params["node_id"]] = properties
            elif method["method"] == "AddEdge":
                self.edges.append(
                    (params["source_id"], params["target_id"], properties)
                )
        version = envelope["content_version"]
        self.versions[version["object_id"]] = version
        self.records[envelope["envelope_id"]] = envelope
        return {
            "batch_id": mutation["batch_id"],
            "replayed": False,
            "projection_pending": False,
        }


class _FakeRdf:
    def validate_shacl(self, _shapes: str, _data_graph: str) -> dict[str, Any]:
        return {"conforms": True, "results": []}


class _FakeClient:
    def __init__(self) -> None:
        self.nodes = _FakeNodes()
        self.changes = _FakeChanges(self.nodes)
        self.rdf = _FakeRdf()

    @staticmethod
    def supports(operation: str) -> bool:
        return operation == "ApplyChangeEnvelope"


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


def test_ingest_entities_writes_nodes_and_edges():
    c = _FakeClient()
    res = ingest_entities(
        [{"id": "a", "node_type": "Paper", "name": "p"}, {"id": "b", "node_type": "PaperSource"}],
        [{"source": "a", "target": "b", "relationship": "publishedInSource"}],
        client=c,
    )
    assert res == {"nodes": 2, "edges": 1}
    assert len(c.changes.applied) == 1
    assert set(c.nodes.values) == {"a", "b"}
    # provenance is stamped
    assert c.nodes.values["a"]["source"] == "scholarx"
    assert c.nodes.values["a"]["domain"] == "scholarx"
    assert c.changes.edges == [("a", "b", {"relationship": "publishedInSource"})]


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


def test_ingest_papers_dedups_shared_nodes():
    c = _FakeClient()
    # two arXiv papers sharing a source + one author
    p1 = _paper()
    p2 = Paper(
        id="2603.10000",
        source=PaperSource.ARXIV,
        title="Follow-up study",
        authors=["Ada Lovelace"],
        categories=["cs.AI"],
    )
    res = ingest_papers([p1, p2], client=c)
    # shared scholarx:source:arxiv, scholarx:person:ada-lovelace, scholarx:category:cs.ai
    # written only once each
    assert "scholarx:source:arxiv" in c.nodes.values
    assert res is not None and len(c.changes.applied) == 1
    # source node appears exactly once
    assert sum(1 for k in c.nodes.values if k == "scholarx:source:arxiv") == 1


def test_ingest_documents_writes_document_nodes():
    c = _FakeClient()
    res = ingest_documents(
        [{"id": "scholarx:document:x", "text": "hello", "source_uri": "http://x"}],
        client=c,
    )
    assert res == {"nodes": 1, "edges": 0}
    assert c.nodes.values["scholarx:document:x"]["node_type"] == "Document"
    assert c.nodes.values["scholarx:document:x"]["text"] == "hello"


def test_retired_structural_alias_is_rejected():
    with pytest.raises(NativeIngestError, match="canonical node_type"):
        ingest_entities([{"id": "a", "type": "Paper"}], client=_FakeClient())


def test_empty_native_ingest_is_rejected():
    with pytest.raises(NativeIngestError, match="at least one entity"):
        ingest_entities([], client=_FakeClient())
