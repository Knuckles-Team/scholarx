"""Native epistemic-graph ingestion for ScholarX papers (typed graph nodes + documents).

CONCEPT:AU-KG.ingest.enterprise-source-extractor. ScholarX natively pushes the papers it
fetches into the ONE epistemic-graph knowledge graph as **typed OWL nodes** (``:Paper``,
``:PaperSource``, ``:ResearchCategory``, shared ``:Person``) with their links
(``:publishedInSource`` / ``:authoredBy`` / ``:hasCategory``), and — because a :Paper carries
its abstract as searchable ``text`` — as the **document** modality in the same node. Raw PDF
bytes ride the **blob** path in :mod:`scholarx.kg_media`.

The write path is the shared fleet primitive
``agent_utilities.knowledge_graph.memory.native_ingest`` (the lightweight
``GraphComputeEngine()._client`` + ``txn`` — never the heavy in-process engine). That primitive
is not yet in every installed ``agent_utilities``, so it is imported **guarded**: when it is
absent this module falls back to a self-contained txn writer with identical semantics. Either
way everything is engine-guarded — with no reachable engine every entry point **no-ops**
(returns ``None``), so ScholarX runs with zero KG infrastructure. Node ids follow
``scholarx:<class>:<externalId>`` and ``type`` matches the classes federated by
``scholarx.ontology``.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

logger = logging.getLogger("scholarx.kg")

_SOURCE = "scholarx"
_DOMAIN = "scholarx"
_DEFAULT_GRAPH = "__commons__"


# ── Write path: prefer the shared primitive, else a self-contained fallback ──────────


def _primitive() -> Any | None:
    """Return the shared ``native_ingest`` module, or ``None`` when it is not installed."""
    try:
        from agent_utilities.knowledge_graph.memory import native_ingest

        return native_ingest
    except Exception as e:  # noqa: BLE001 — primitive not shipped in this agent_utilities
        logger.debug("scholarx KG: shared native_ingest unavailable (%s); using fallback", e)
        return None


def _client() -> tuple[Any | None, str]:
    """Fallback engine-client resolver (used only when the shared primitive is absent)."""
    try:
        from agent_utilities.knowledge_graph.core.graph_compute import GraphComputeEngine
    except Exception as e:  # noqa: BLE001 — KG stack absent
        logger.debug("scholarx KG ingest unavailable (import): %s", e)
        return None, ""
    try:
        engine = GraphComputeEngine()
        client = getattr(engine, "_client", None)
        if client is None:
            return None, ""
        return client, (getattr(engine, "graph_name", None) or _DEFAULT_GRAPH)
    except Exception as e:  # noqa: BLE001 — engine unreachable
        logger.debug("scholarx KG ingest: engine unreachable: %s", e)
        return None, ""


def _fallback_write(
    nodes: list[dict[str, Any]],
    relationships: list[dict[str, Any]] | None,
    *,
    source: str,
    domain: str,
    client: Any | None,
    graph: str | None,
) -> dict[str, int] | None:
    """Self-contained txn writer mirroring the shared primitive's semantics."""
    nodes = [n for n in nodes if n.get("id")]
    if not nodes:
        return None
    if client is None:
        client, graph = _client()
    if client is None:
        return None
    graph = graph or _DEFAULT_GRAPH
    try:
        txn = client.txn.begin(graph=graph)
        for node in nodes:
            props = {k: v for k, v in node.items() if k != "id" and v is not None}
            props.setdefault("source", source)
            props.setdefault("domain", domain)
            client.txn.add_node(txn, node["id"], props)
        committed = client.txn.commit(txn)
    except Exception as e:  # noqa: BLE001 — engine/txn failure is non-fatal
        logger.warning("scholarx KG ingest: txn failed: %s", e)
        return None
    if not committed:
        logger.warning("scholarx KG ingest: txn not committed (conflict)")
        return None

    edges = 0
    for rel in relationships or []:
        try:
            client.edges.add(rel["source"], rel["target"], {"type": rel.get("type", "RELATED")})
            edges += 1
        except Exception as e:  # noqa: BLE001 — pure edge link, best-effort
            logger.debug("scholarx KG ingest: edge skipped: %s", e)
    logger.info("scholarx KG ingest: wrote %d nodes, %d edges", len(nodes), edges)
    return {"nodes": len(nodes), "edges": edges}


def ingest_entities(
    entities: list[dict[str, Any]],
    relationships: list[dict[str, Any]] | None = None,
    *,
    source: str = _SOURCE,
    domain: str = _DOMAIN,
    client: Any | None = None,
    graph: str | None = None,
) -> dict[str, int] | None:
    """Write typed OWL nodes (+ edges) into the engine.

    ``entities``: ``[{"id":..., "type":<owl:Class>, ...props}]``.
    ``relationships``: ``[{"source":id, "target":id, "type":<link>}]``.
    Returns ``{"nodes":n, "edges":m}`` or ``None``. ``client``/``graph`` may be injected
    (tests); otherwise resolved on demand. Never raises.
    """
    if not entities:
        return None
    if client is None:
        prim = _primitive()
        if prim is not None:
            return prim.ingest_entities(entities, relationships, source=source, domain=domain, graph=graph)
    return _fallback_write(entities, relationships, source=source, domain=domain, client=client, graph=graph)


def ingest_documents(
    docs: list[dict[str, Any]],
    *,
    source: str = _SOURCE,
    domain: str = _DOMAIN,
    client: Any | None = None,
    graph: str | None = None,
) -> dict[str, int] | None:
    """Write text records as ``:Document`` nodes (semantic-search fodder).

    Each doc: ``{"id":..., "text":..., "title"?:..., "source_uri"?:..., ...props}``.
    Returns ``{"nodes":n, "edges":0}`` or ``None``. Never raises.
    """
    if not docs:
        return None
    if client is None:
        prim = _primitive()
        if prim is not None:
            return prim.ingest_documents(docs, source=source, domain=domain, graph=graph)
    # Fallback: shape docs into :Document nodes just like the primitive does.
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    nodes: list[dict[str, Any]] = []
    for doc in docs:
        did = doc.get("id")
        text = doc.get("text") or doc.get("content")
        if not did or not text:
            continue
        node = {k: v for k, v in doc.items() if k not in ("content",) and v is not None}
        node["id"] = did
        node["type"] = "Document"
        node["text"] = text
        node.setdefault("created_at", now)
        nodes.append(node)
    return _fallback_write(nodes, None, source=source, domain=domain, client=client, graph=graph)


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
                "type": "Paper",
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
            _add({"id": source_id, "type": "PaperSource", "name": str(src)})
            relationships.append({"source": paper_node_id, "target": source_id, "type": "publishedInSource"})

        for cat in p.get("categories") or []:
            cat_id = f"scholarx:category:{_slug(str(cat))}"
            _add({"id": cat_id, "type": "ResearchCategory", "name": str(cat)})
            relationships.append({"source": paper_node_id, "target": cat_id, "type": "hasCategory"})

        for author in (p.get("authors") or [])[:20]:
            if not author:
                continue
            person_id = f"scholarx:person:{_slug(str(author), 80)}"
            _add({"id": person_id, "type": "Person", "name": str(author)})
            relationships.append({"source": paper_node_id, "target": person_id, "type": "authoredBy"})

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
