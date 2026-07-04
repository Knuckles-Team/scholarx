"""Native epistemic-graph blob ingestion for ScholarX full-text PDFs.

CONCEPT:AU-KG.ingest.list-durable-media. When a live epistemic-graph engine is reachable, a
downloaded paper PDF is stored as a content-addressed **blob** with a ``:MediaAsset`` graph
node (carrying the paper's metadata) in ONE cross-modal ACID commit, via the agent-utilities
``MediaStore`` — the same blob path media-downloader uses. This makes the raw PDF bytes — not
just a filesystem path — durable, deduped, and queryable inside the knowledge graph, and lets
the twin :mod:`scholarx.kg_ingest` typed ``:Paper`` node point at it via ``:hasFullText``.

Entirely best-effort and dependency-guarded: if the shared ``native_ingest`` primitive, the
agent-utilities KG stack, or a live engine is absent, every entry point **no-ops** (returns
``None``), so downloads keep working with zero KG infrastructure.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("scholarx.kg")

# Paper metadata worth carrying onto the :MediaAsset node.
_META_FIELDS = ("id", "title", "doi", "url", "source", "published_date")


def media_store() -> Any | None:
    """Return a ``MediaStore`` over a live engine, or ``None`` when unavailable.

    Prefers the shared ``native_ingest.media_store`` factory; falls back to building the
    store directly. Never raises.
    """
    try:
        from agent_utilities.knowledge_graph.memory import native_ingest

        store = native_ingest.media_store()
        if store is not None:
            return store
    except Exception as e:  # noqa: BLE001 — primitive not shipped; fall through
        logger.debug("scholarx KG media: shared primitive unavailable (%s)", e)
    try:
        from agent_utilities.knowledge_graph.core.graph_compute import GraphComputeEngine
        from agent_utilities.knowledge_graph.memory.media_store import MediaStore

        engine = GraphComputeEngine()
        if getattr(engine, "_client", None) is None:
            return None
        return MediaStore(engine)
    except Exception as e:  # noqa: BLE001 — no reachable engine
        logger.debug("scholarx KG media: engine unreachable: %s", e)
        return None


def ingest_pdf(
    file_path: str | None,
    *,
    paper: Any | None = None,
    source: str = "scholarx",
    store: Any | None = None,
) -> dict[str, Any] | None:
    """Store a downloaded paper PDF as a blob + ``:MediaAsset`` in the knowledge graph.

    ``paper`` may be a ScholarX ``Paper`` model or a plain dict of its metadata. Returns
    ``{asset_id, digest, size_bytes, media_type}`` on success, or ``None`` when there is no
    engine, no file, or the store failed (never raises). ``store`` may be injected (tests).
    """
    if not file_path or not os.path.exists(file_path):
        return None
    store = store if store is not None else media_store()
    if store is None:
        return None

    meta: dict[str, Any] = {}
    if paper is not None:
        meta = paper.model_dump() if hasattr(paper, "model_dump") else dict(paper)

    try:
        with open(file_path, "rb") as fh:
            data = fh.read()
    except OSError as e:
        logger.warning("scholarx KG media: cannot read %s: %s", file_path, e)
        return None

    extra: dict[str, Any] = {}
    for key in _META_FIELDS:
        val = meta.get(key)
        val = getattr(val, "value", val)  # StrEnum source -> str
        if val is not None:
            extra[key] = val
    name = meta.get("title") or os.path.basename(file_path)

    try:
        stored = store.store_media(
            data,
            media_type="document",
            mime_type="application/pdf",
            source=source,
            name=name,
            extra=extra,
        )
    except Exception as e:  # noqa: BLE001 — engine/store failure is non-fatal
        logger.warning("scholarx KG media: store_media failed: %s", e)
        return None
    if stored is None:
        return None

    logger.info(
        "scholarx KG media: stored %s (%s bytes) as asset %s digest %s",
        name,
        len(data),
        stored.asset_id,
        stored.digest[:16],
    )
    return {
        "asset_id": stored.asset_id,
        "digest": stored.digest,
        "size_bytes": len(data),
        "media_type": "document",
    }
