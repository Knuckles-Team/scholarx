"""Native epistemic-graph blob ingestion for ScholarX full-text PDFs.

CONCEPT:AU-KG.ingest.list-durable-media. When a live epistemic-graph engine is reachable, a
downloaded paper PDF is stored as a content-addressed **blob** with a ``:MediaAsset`` graph
node (carrying the paper's metadata) via the SDK's knowledge-ingest facade
(:mod:`agent_connector_sdk.ingest`) — the same ``ChangeSet.media`` path every connector's blob
ingestion goes through. This makes the raw PDF bytes — not just a filesystem path — durable,
deduped, and queryable inside the knowledge graph, and lets the twin :mod:`scholarx.kg_ingest`
typed ``:Paper`` node point at it via ``:hasFullText``.

Entirely best-effort and dependency-guarded: if no engine is configured or reachable, every
entry point **no-ops** (returns ``None``), so downloads keep working with zero KG infrastructure.
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

from agent_connector_sdk.ingest import (
    ChangeSet,
    IngestBinding,
    IngestError,
    IngestUnavailableError,
    KnowledgeIngest,
    MediaAsset,
    current_ingest,
)

logger = logging.getLogger("scholarx.kg")

_BINDING = IngestBinding(connector="scholarx", stream="scholarx")

# Paper metadata worth carrying onto the stored media asset's properties.
_META_FIELDS = ("id", "title", "doi", "url", "source", "published_date")


def _extract_paper_metadata(paper: Any | None) -> dict[str, Any]:
    if paper is None:
        return {}
    return paper.model_dump() if hasattr(paper, "model_dump") else dict(paper)


def _read_pdf_bytes(file_path: str) -> bytes | None:
    try:
        with open(file_path, "rb") as fh:
            return fh.read()
    except OSError as e:
        logger.warning("Operation failed: error_type=%s", type(e).__name__)
        return None


def _build_media_extra(meta: dict[str, Any]) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    for key in _META_FIELDS:
        val = meta.get(key)
        val = getattr(val, "value", val)  # StrEnum source -> str
        if val is not None:
            extra[key] = val
    return extra


async def ingest_pdf(
    file_path: str | None,
    *,
    paper: Any | None = None,
    source: str = "scholarx",
    ingest: KnowledgeIngest | None = None,
) -> dict[str, Any] | None:
    """Store a downloaded paper PDF as a blob + media-asset node in the knowledge graph.

    ``paper`` may be a ScholarX ``Paper`` model or a plain dict of its metadata. Returns
    ``{asset_id, digest, size_bytes, media_type}`` on success, or ``None`` when there is no
    engine, no file, or the engine rejected it (never raises). ``ingest`` may be injected
    (tests) with a fake transport; ``source`` is carried onto the asset's properties for
    parity with the pre-migration record shape.
    """
    if not file_path or not os.path.exists(file_path):
        return None

    data = _read_pdf_bytes(file_path)
    if data is None:
        return None

    meta = _extract_paper_metadata(paper)
    extra = _build_media_extra(meta)
    extra.setdefault("source", source)
    name = meta.get("title") or os.path.basename(file_path)

    service = ingest
    if service is None:
        try:
            service = current_ingest()
        except IngestUnavailableError as e:
            logger.debug("Operation failed: error_type=%s", type(e).__name__)
            return None

    asset = MediaAsset(data=data, mime_type="application/pdf", name=name, properties=extra)
    change_set = ChangeSet(media=(asset,))
    try:
        await service.submit(_BINDING, change_set)
    except IngestError as e:  # noqa: BLE001 — engine/transport failure is non-fatal
        logger.warning("scholarx KG media store failed: error_type=%s", type(e).__name__)
        return None

    # The engine's own Blob CAS digest is opaque to this facade (submit() does not echo it
    # back); this is a locally-computed content digest for the return shape, the closest
    # honest analogue — see FLEET-SDK-MIGRATION-RECIPE.md §2a point 3 for the same tradeoff
    # on node/edge counts.
    digest = hashlib.sha256(data).hexdigest()
    asset_id = asset.id or f"blob:{digest}"

    logger.info(
        "scholarx KG media: stored %s (%s bytes) as asset %s digest %s",
        name,
        len(data),
        asset_id,
        digest[:16],
    )
    return {
        "asset_id": asset_id,
        "digest": digest,
        "size_bytes": len(data),
        "media_type": "document",
    }
