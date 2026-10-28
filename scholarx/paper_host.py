"""Compose host-authorized paper tools on the ScholarX MCP factory."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from agent_connector_sdk.adapters.paper_download import DocumentAdmission, DocumentRequest, PaperDocumentService
from agent_connector_sdk.adapters.paper_models import PaperQuery
from agent_connector_sdk.adapters.paper_quota import PaperQuotaPolicy, SharedPaperQuota
from agent_connector_sdk.http.options import HttpClientOptions

from scholarx.mcp_server import get_mcp_instance
from scholarx.paper_auth import VerifiedPaperAccess
from scholarx.paper_source import create_paper_service

DocumentAuthority = Callable[[DocumentRequest, Any], Awaitable[DocumentAdmission | None]]


def build_paper_mcp(
    *,
    engine_client: Any,
    tenant_claim: str,
    required_scopes: frozenset[str],
    arxiv: tuple[HttpClientOptions, PaperQuotaPolicy],
    semantic_scholar: tuple[HttpClientOptions, PaperQuotaPolicy] | None = None,
    osf: Mapping[str, tuple[HttpClientOptions, PaperQuotaPolicy]] | None = None,
    biorxiv: Mapping[str, tuple[HttpClientOptions, PaperQuotaPolicy]] | None = None,
    pmc: tuple[HttpClientOptions, PaperQuotaPolicy] | None = None,
    document_authority: DocumentAuthority | None = None,
    streams: Mapping[str, PaperQuery] | None = None,
) -> tuple[Any, Any]:
    """Build a server from explicit verified host and destination authorities."""
    access = VerifiedPaperAccess(tenant_claim=tenant_claim, required_scopes=required_scopes)
    configured = {"arxiv", *(osf or {}), *(biorxiv or {})}
    if semantic_scholar is not None:
        configured.add("semantic_scholar")
    if pmc is not None:
        configured.add("pmc")
    for query in (streams or {}).values():
        if len(query.provider_ids) != 1 or query.provider_ids[0] not in configured:
            raise ValueError("each paper stream requires a configured provider")
    semantic_http, semantic_quota = semantic_scholar if semantic_scholar is not None else (None, None)
    service = create_paper_service(
        engine_client=engine_client,
        authorize=access,
        arxiv_http=arxiv[0],
        arxiv_quota=arxiv[1],
        semantic_http=semantic_http,
        semantic_quota=semantic_quota,
        osf_providers=dict(osf or {}),
        biorxiv_providers=dict(biorxiv or {}),
        pmc_provider=pmc,
    )
    document = None
    if document_authority is not None:

        async def authorize_document(request: DocumentRequest, ctx: Any) -> DocumentAdmission | None:
            if not await access(request, ctx):
                return None
            return await document_authority(request, ctx)

        document = PaperDocumentService(SharedPaperQuota(engine_client), authorize_document)
    return get_mcp_instance(
        paper_service=service, paper_document_service=document, paper_ingest_streams=tuple((streams or {}).items())
    )
