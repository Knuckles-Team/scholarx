"""Native epistemic-graph ingestion for ScholarX papers (typed graph nodes + documents).

CONCEPT:AU-KG.ingest.enterprise-source-extractor. ScholarX natively pushes the papers it
fetches into the ONE epistemic-graph knowledge graph as **typed OWL nodes** (``:Paper``,
``:PaperSource``, ``:ResearchCategory``, shared ``:Person``) with their links
(``:publishedInSource`` / ``:authoredBy`` / ``:hasCategory``), and — because a :Paper carries
its abstract as searchable ``text`` — as the **document** modality in the same node. Raw PDF
bytes ride the **blob** path in :mod:`scholarx.kg_media`.

The write path is the SDK's knowledge-ingest facade (:mod:`agent_connector_sdk.ingest`), which
submits a typed ``ChangeSet`` through the generated epistemic-graph ``SourceIngest`` request/
receipt types. Engine failures are explicit (:class:`~agent_connector_sdk.ingest.IngestError`)
and partial writes are never acknowledged. Node ids follow ``scholarx:<class>:<externalId>``
and ``node_type`` matches the classes federated by ``scholarx.ontology``.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from agent_connector_sdk.ingest import (
    ChangeSet,
    Document,
    Entity,
    IngestBinding,
    IngestError,
    KnowledgeIngest,
    Relationship,
    current_ingest,
)

logger = logging.getLogger("scholarx.kg")

_BINDING = IngestBinding(connector="scholarx", stream="scholarx")


def _to_entity(record: dict[str, Any]) -> Entity:
    return Entity(
        id=record.get("id"),
        node_type=record.get("node_type"),
        properties={k: v for k, v in record.items() if k not in ("id", "node_type")},
    )


def _to_relationship(record: dict[str, Any]) -> Relationship:
    props = {k: v for k, v in record.items() if k not in ("source", "target", "relationship")}
    return Relationship(
        source=record["source"],
        target=record["target"],
        relationship=record["relationship"],
        properties=props or None,
    )


def _to_document(record: dict[str, Any]) -> Document:
    return Document(
        id=record["id"],
        text=record["text"],
        title=record.get("title"),
        source_uri=record.get("source_uri"),
        properties={
            k: v for k, v in record.items() if k not in ("id", "text", "title", "source_uri", "updated_at")
        },
        updated_at=record.get("updated_at"),
    )


async def ingest_entities(
    entities: list[dict[str, Any]],
    relationships: list[dict[str, Any]] | None = None,
    *,
    ingest: KnowledgeIngest | None = None,
) -> dict[str, int]:
    """Write typed OWL nodes (+ edges) into the engine via the SDK's ingest facade.

    Nodes use ``node_type`` and relationships use ``relationship``. The returned
    ``{"nodes": n, "edges": m}`` is the closest honest analogue of the generated
    ``SourceIngestionReceipt``'s ``affected_count``/``relationship_count``.
    """
    if not entities:
        raise IngestError("ingest_entities needs at least one entity")
    change_set = ChangeSet(
        entities=tuple(_to_entity(e) for e in entities),
        relationships=tuple(_to_relationship(r) for r in relationships or ()),
    )
    service = ingest or current_ingest()
    receipt = await service.submit(_BINDING, change_set)
    return {"nodes": receipt.affected_count, "edges": receipt.relationship_count}


async def ingest_documents(
    docs: list[dict[str, Any]],
    *,
    ingest: KnowledgeIngest | None = None,
) -> dict[str, int]:
    """Write text records as ``:Document`` nodes (semantic-search fodder) via the SDK.

    Each doc: ``{"id":..., "text":..., "title"?:..., "source_uri"?:..., ...props}``.
    """
    if not docs:
        raise IngestError("ingest_documents needs at least one document")
    change_set = ChangeSet(documents=tuple(_to_document(d) for d in docs))
    service = ingest or current_ingest()
    receipt = await service.submit(_BINDING, change_set)
    return {"nodes": receipt.affected_count, "edges": receipt.relationship_count}


# ── Mapper: ScholarX Paper records → typed :Paper / :PaperSource / :Person / :ResearchCategory


def _slug(value: str, limit: int = 60) -> str:
    """Lower-case, ascii-safe slug for a stable node id fragment."""
    text = re.sub(r"[^\w.-]+", "-", value.strip().lower())
    return text.strip("-")[:limit] or "unknown"


def _as_dict(paper: Any) -> dict[str, Any]:
    """Accept a Paper pydantic model or a plain dict; return a plain dict."""
    if hasattr(paper, "model_dump"):
        return paper.model_dump()
    return dict(paper)


def _paper_node(p: dict[str, Any], pid: Any, paper_node_id: str) -> dict[str, Any]:
    abstract = p.get("abstract") or ""
    return {
        "id": paper_node_id,
        "node_type": "Paper",
        "name": p.get("title"),
        "title": p.get("title"),
        "text": abstract or p.get("title"),
        "abstract": abstract or None,
        "doi": p.get("doi"),
        "url": p.get("url") or None,
        "pdfUrl": p.get("pdf_url"),
        "publishedDate": p.get("published_date"),
        "citationCount": p.get("citation_count"),
        "externalToolId": str(pid),
        "source_uri": p.get("url") or None,
    }


def _source_node_and_edge(src: Any, paper_node_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    if not src:
        return None
    source_id = f"scholarx:source:{_slug(str(src))}"
    node = {"id": source_id, "node_type": "PaperSource", "name": str(src)}
    edge = {"source": paper_node_id, "target": source_id, "relationship": "publishedInSource"}
    return node, edge


def _category_nodes_and_edges(
    categories: list[Any] | None, paper_node_id: str
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs = []
    for cat in categories or []:
        cat_id = f"scholarx:category:{_slug(str(cat))}"
        node = {"id": cat_id, "node_type": "ResearchCategory", "name": str(cat)}
        edge = {"source": paper_node_id, "target": cat_id, "relationship": "hasCategory"}
        pairs.append((node, edge))
    return pairs


def _author_nodes_and_edges(
    authors: list[Any] | None, paper_node_id: str
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs = []
    for author in (authors or [])[:20]:
        if not author:
            continue
        person_id = f"scholarx:person:{_slug(str(author), 80)}"
        node = {"id": person_id, "node_type": "Person", "name": str(author)}
        edge = {"source": paper_node_id, "target": person_id, "relationship": "authoredBy"}
        pairs.append((node, edge))
    return pairs


def paper_entities(
    papers: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Map ScholarX papers → (entities, relationships) for :func:`ingest_entities`.

    Emits one ``:Paper`` node (carrying its abstract as ``text`` — the document modality)
    plus deduplicated ``:PaperSource`` / ``:ResearchCategory`` / ``:Person`` nodes, and their
    ``:publishedInSource`` / ``:hasCategory`` / ``:authoredBy`` links.
    """
    entities: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(node: dict[str, Any]) -> None:
        if node["id"] not in seen:
            seen.add(node["id"])
            entities.append(node)

    for raw in papers or []:
        p = _as_dict(raw)
        pid = p.get("id")
        if not pid:
            continue
        src = p.get("source")
        src = getattr(src, "value", src)  # StrEnum -> str
        paper_node_id = f"scholarx:paper:{_slug(str(pid), 120)}"

        _add(_paper_node(p, pid, paper_node_id))

        source_pair = _source_node_and_edge(src, paper_node_id)
        if source_pair:
            source_node, source_edge = source_pair
            _add(source_node)
            relationships.append(source_edge)

        for cat_node, cat_edge in _category_nodes_and_edges(p.get("categories"), paper_node_id):
            _add(cat_node)
            relationships.append(cat_edge)

        for person_node, person_edge in _author_nodes_and_edges(p.get("authors"), paper_node_id):
            _add(person_node)
            relationships.append(person_edge)

    return entities, relationships


async def ingest_papers(
    papers: list[Any],
    *,
    ingest: KnowledgeIngest | None = None,
) -> dict[str, int] | None:
    """Map ScholarX papers → typed nodes and ingest them in one txn.

    Best-effort: returns ``{"nodes":n, "edges":m}`` or ``None`` (nothing to write).
    Raises :class:`~agent_connector_sdk.ingest.IngestError` on an engine failure — callers
    that need "never raises" semantics (e.g. an auto-ingest hook on the search path) should
    catch it themselves, same as before.
    """
    entities, relationships = paper_entities(papers)
    if not entities:
        return None
    return await ingest_entities(entities, relationships, ingest=ingest)
