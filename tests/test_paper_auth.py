"""Paper search binds the verified MCP identity to the requested tenant."""

from __future__ import annotations

import asyncio
import json
import socket
from contextlib import asynccontextmanager

import pytest
import uvicorn
from agent_connector_sdk.adapters.paper_models import PaperQuery
from agent_connector_sdk.adapters.paper_quota import PaperQuotaPolicy, QuotaSlot
from agent_connector_sdk.adapters.paper_search import PaperSearchService, ProviderBinding
from agent_connector_sdk.http.options import HttpClientOptions
from agent_connector_sdk.http.retry import RetryPolicy
from agent_connector_sdk.testing.http_server import ScriptedHttpServer, ScriptedResponse
from fastmcp import Client
from fastmcp.client import BearerAuth

from scholarx.mcp_server import get_mcp_instance
from scholarx.paper_auth import VerifiedPaperAccess
from scholarx.paper_source import ArxivPaperSource

pytestmark = pytest.mark.spec("CONN-SCHOLARX-API-COVERAGE-R002")
_TOKEN = "synthetic-valid-token-" + "a" * 32  # sanitizer:ignore - test fixture
_LIMITED = "synthetic-limited-token-" + "b" * 32  # sanitizer:ignore - test fixture


class _Quota:
    @asynccontextmanager
    async def request_slot(self, policy):
        yield QuotaSlot()


async def _exercise(url):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    options = HttpClientOptions(
        base_url=url + "/api", pin_egress=True, allow_loopback=True, retry=RetryPolicy(max_attempts=1)
    )
    policy = PaperQuotaPolicy(provider_id="arxiv", credential_group="arxiv", policy_revision="v1", minimum_spacing_ns=1)
    service = PaperSearchService(
        {"arxiv": ProviderBinding(ArxivPaperSource(options), policy)},
        quota=_Quota(),
        authorize=VerifiedPaperAccess(tenant_claim="tenant_id", required_scopes=frozenset({"paper:read"})),
    )
    _, mcp = get_mcp_instance(paper_service=service)
    server = uvicorn.Server(uvicorn.Config(mcp.http_app(), log_level="error", lifespan="on"))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        for _ in range(500):
            if server.started:
                break
            await asyncio.sleep(0.01)
        assert server.started
        query = PaperQuery(tenant="tenant-a", query="graph", provider_ids=("arxiv",), schema_revision="v1")
        async with Client(f"http://127.0.0.1:{port}/mcp", auth=BearerAuth(_TOKEN)) as client:
            accepted = await client.call_tool("paper_search", {"query": query.model_dump(mode="json")})
            denied = await client.call_tool(
                "paper_search", {"query": query.model_copy(update={"tenant": "tenant-b"}).model_dump(mode="json")}
            )
        async with Client(f"http://127.0.0.1:{port}/mcp", auth=BearerAuth(_LIMITED)) as client:
            limited = await client.call_tool("paper_search", {"query": query.model_dump(mode="json")})
        return accepted.structured_content, denied.structured_content, limited.structured_content
    finally:
        server.should_exit = True
        await task


def test_verified_bearer_enforces_tenant_and_scope(monkeypatch):
    tokens = {
        _TOKEN: {"client_id": "reader", "tenant_id": "tenant-a", "scopes": ["paper:read"]},
        _LIMITED: {"client_id": "limited", "tenant_id": "tenant-a", "scopes": []},
    }
    monkeypatch.setenv("TEST_PAPER_TOKEN_MAP", json.dumps(tokens))
    monkeypatch.setattr(
        "sys.argv",
        [
            "scholarx",
            "--transport",
            "streamable-http",
            "--auth-type",
            "static",
            "--static-tokens-ref",
            "env://TEST_PAPER_TOKEN_MAP",
            "--token-audience",
            "paper-test",
        ],
    )
    body = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/1234.5678v1</id><title>Graph paper</title></entry></feed>'
    with ScriptedHttpServer(ScriptedResponse(body=body, headers={"Content-Type": "application/atom+xml"})) as provider:
        accepted, denied, limited = asyncio.run(_exercise(provider.base_url))
        assert accepted["completeness"] == "complete"
        assert denied["reports"][0]["reason"] == limited["reports"][0]["reason"] == "unauthorized"
        assert len(provider.requests) == 1


def test_policy_requires_host_supplied_scope():
    with pytest.raises(ValueError):
        VerifiedPaperAccess(tenant_claim="tenant_id", required_scopes=frozenset())


def test_host_refuses_stream_for_unconfigured_provider():
    from scholarx.paper_host import build_paper_mcp

    http = HttpClientOptions(base_url="https://example.org", pin_egress=True, retry=RetryPolicy(max_attempts=1))
    quota = PaperQuotaPolicy(provider_id="arxiv", credential_group="arxiv", policy_revision="v1", minimum_spacing_ns=1)
    query = PaperQuery(tenant="tenant-a", query="graph", provider_ids=("unknown",), schema_revision="v1")
    with pytest.raises(ValueError, match="configured provider"):
        build_paper_mcp(
            engine_client=object(),
            tenant_claim="tenant_id",
            required_scopes=frozenset({"paper:read"}),
            arxiv=(http, quota),
            streams={"paper_unknown": query},
        )
