"""Native epistemic-graph ingestion for ScholarX papers (typed graph nodes + documents).

CONCEPT:AU-KG.ingest.enterprise-source-extractor. ScholarX natively pushes the papers it
fetches into the ONE epistemic-graph knowledge graph as **typed OWL nodes** (``:Paper``,
``:PaperSource``, ``:ResearchCategory``, shared ``:Person``) with their links
(``:publishedInSource`` / ``:authoredBy`` / ``:hasCategory``), and — because a :Paper carries
its abstract as searchable ``text`` — as the **document** modality in the same node. Raw PDF
bytes ride the **blob** path in :mod:`scholarx.kg_media`.

The write path is the required shared fleet transaction primitive
``agent_utilities.knowledge_graph.memory.native_ingest``. Engine failures are explicit and
partial writes are never acknowledged. Node ids follow
``scholarx:<class>:<externalId>`` and ``node_type`` matches the classes federated by
``scholarx.ontology``.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from agent_utilities.knowledge_graph.memory.native_ingest import (
    ingest_documents as _native_ingest_documents,
)
from agent_utilities.knowledge_graph.memory.native_ingest import (
    ingest_entities as _native_ingest_entities,
)

logger = logging.getLogger("scholarx.kg")

_SOURCE = "scholarx"
_DOMAIN = "scholarx"


def ingest_entities(
    entities: list[dict[str, Any]],
    relationships: list[dict[str, Any]] | None = None,
    *,
    source: str = _SOURCE,
    domain: str = _DOMAIN,
    client: Any | None = None,
    graph: str | None = None,
) -> dict[str, int]:
    """Write typed OWL nodes (+ edges) into the engine.

    Nodes use ``node_type`` and relationships use ``relationship``.
    """
    return _native_ingest_entities(
        entities,
        relationships,
        source=source,
        domain=domain,
        client=client,
        graph=graph,
    )


def ingest_documents(
    docs: list[dict[str, Any]],
    *,
    source: str = _SOURCE,
    domain: str = _DOMAIN,
    client: Any | None = None,
    graph: str | None = None,
) -> dict[str, int]:
    """Write text records as ``:Document`` nodes (semantic-search fodder).

    Each doc: ``{"id":..., "text":..., "title"?:..., "source_uri"?:..., ...props}``.
    The native primitive performs validation, enrichment stamping, and commit.
    """
    return _native_ingest_documents(docs, source=source, domain=domain, client=client, graph=graph)


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
        abstract = p.get("abstract") or ""
        _add(
            {
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
        )

        if src:
            source_id = f"scholarx:source:{_slug(str(src))}"
            _add({"id": source_id, "node_type": "PaperSource", "name": str(src)})
            relationships.append({"source": paper_node_id, "target": source_id, "relationship": "publishedInSource"})

        for cat in p.get("categories") or []:
            cat_id = f"scholarx:category:{_slug(str(cat))}"
            _add({"id": cat_id, "node_type": "ResearchCategory", "name": str(cat)})
            relationships.append({"source": paper_node_id, "target": cat_id, "relationship": "hasCategory"})

        for author in (p.get("authors") or [])[:20]:
            if not author:
                continue
            person_id = f"scholarx:person:{_slug(str(author), 80)}"
            _add({"id": person_id, "node_type": "Person", "name": str(author)})
            relationships.append({"source": paper_node_id, "target": person_id, "relationship": "authoredBy"})

    return entities, relationships


def ingest_papers(
    papers: list[Any],
    *,
    client: Any | None = None,
    graph: str | None = None,
) -> dict[str, int] | None:
    """Map ScholarX papers → typed nodes and ingest them in one txn.

    Best-effort: returns ``{"nodes":n, "edges":m}`` or ``None`` (no engine / nothing to
    write). Never raises — safe to call default-on from the fetch flow.
    """
    entities, relationships = paper_entities(papers)
    return ingest_entities(entities, relationships, client=client, graph=graph)
