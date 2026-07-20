"""Native epistemic-graph typed-node ingestion — Wire-First coverage.

Exercises the real ``ingest_entities`` / ``ingest_documents`` / ``ingest_papers`` seam with a
fake engine client (no engine required), asserting the single-transaction node/edge staging and commit and the
ScholarX Paper -> :Paper/:PaperSource/:ResearchCategory/:Person mapping.
CONCEPT:AU-KG.ingest.enterprise-source-extractor.
"""

from __future__ import annotations

import pytest
from agent_utilities.knowledge_graph.memory.native_ingest import NativeIngestError

from scholarx.kg_ingest import ingest_documents, ingest_entities, ingest_papers, paper_entities
from scholarx.models import Paper, PaperSource


class _FakeTxn:
    def __init__(self):
        self.nodes = {}
        self.edges = []
        self.committed = False
        self.graph = None

    def begin(self, graph=None):
        self.graph = graph
        return "txn-1"

    def add_node(self, txn, node_id, props):
        self.nodes[node_id] = props

    def add_edge(self, txn, source, target, props):
        self.edges.append((source, target, props))

    def commit(self, txn):
        self.committed = True
        return True


class _FakeClient:
    def __init__(self):
        self.txn = _FakeTxn()


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
        graph="__commons__",
    )
    assert res == {"nodes": 2, "edges": 1}
    assert c.txn.committed is True
    assert set(c.txn.nodes) == {"a", "b"}
    # provenance is stamped
    assert c.txn.nodes["a"]["source"] == "scholarx"
    assert c.txn.nodes["a"]["domain"] == "scholarx"
    assert c.txn.edges == [("a", "b", {"relationship": "publishedInSource"})]


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
    res = ingest_papers([p1, p2], client=c, graph="__commons__")
    # shared scholarx:source:arxiv, scholarx:person:ada-lovelace, scholarx:category:cs.ai
    # written only once each
    assert "scholarx:source:arxiv" in c.txn.nodes
    assert res is not None and c.txn.committed is True
    # source node appears exactly once
    assert sum(1 for k in c.txn.nodes if k == "scholarx:source:arxiv") == 1


def test_ingest_documents_writes_document_nodes():
    c = _FakeClient()
    res = ingest_documents(
        [{"id": "scholarx:document:x", "text": "hello", "source_uri": "http://x"}],
        client=c,
        graph="__commons__",
    )
    assert res == {"nodes": 1, "edges": 0}
    assert c.txn.nodes["scholarx:document:x"]["node_type"] == "Document"
    assert c.txn.nodes["scholarx:document:x"]["text"] == "hello"


def test_retired_structural_alias_is_rejected():
    with pytest.raises(NativeIngestError, match="canonical node_type"):
        ingest_entities([{"id": "a", "type": "Paper"}], client=_FakeClient())


def test_empty_native_ingest_is_rejected():
    with pytest.raises(NativeIngestError, match="at least one entity"):
        ingest_entities([], client=_FakeClient())
