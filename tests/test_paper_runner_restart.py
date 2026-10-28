import asyncio
import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest
import uvicorn
from agent_connector_sdk.adapters.paper_models import DocumentOffer, PaperQuery
from agent_connector_sdk.adapters.paper_quota import PaperQuotaPolicy
from agent_connector_sdk.http.options import HttpClientOptions
from agent_connector_sdk.http.retry import RetryPolicy
from agent_connector_sdk.sinks.epistemic_graph import EpistemicGraphSink
from agent_connector_sdk.testing.http_server import ScriptedHttpServer, ScriptedResponse
from epistemic_graph.connector_pack import ConnectorPackArchiveBuilder, ConnectorPackClient, ConnectorPackEntryContent
from epistemic_graph.generated.connector_pack import PackEntryKind, PackProducer
from fastmcp import Client
from fastmcp.client import BearerAuth

from scholarx.paper_host import build_paper_mcp
from tests.live_engine import _LIVE, PRINCIPAL, TENANT, live_ingest, scoped_client  # noqa: F401
from tests.paper_support import catalog as _catalog
from tests.paper_support import mutation_context as _mutation_context

TOKEN = "synthetic-runner-token-" + "a" * 32  # sanitizer:ignore - synthetic fixture
CONNECTOR = "scholarx-mcp"


async def start(url):
    engine = await scoped_client(["*"])
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    authority_calls = []

    async def document_authority(request, ctx):
        authority_calls.append(request)
        return None

    query = PaperQuery(tenant=TENANT, query="graph", provider_ids=("arxiv",), schema_revision="v1", page_bound=1)
    _, mcp = build_paper_mcp(
        engine_client=engine,
        tenant_claim="tenant_id",
        required_scopes=frozenset({"paper:read"}),
        arxiv=(
            HttpClientOptions(
                base_url=url + "/api", pin_egress=True, allow_loopback=True, retry=RetryPolicy(max_attempts=1)
            ),
            PaperQuotaPolicy(
                provider_id="arxiv", credential_group="runner-arxiv", policy_revision="v1", minimum_spacing_ns=1
            ),
        ),
        document_authority=document_authority,
        streams={"paper_arxiv_ingest": query},
    )
    server = uvicorn.Server(uvicorn.Config(mcp.http_app(), log_level="error", lifespan="on"))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    for _ in range(500):
        if server.started:
            break
        await asyncio.sleep(0.01)
    assert server.started
    async with Client(f"http://127.0.0.1:{port}/mcp", auth=BearerAuth(TOKEN)) as client:
        denied = await client.call_tool(
            "paper_download",
            {
                "request": {
                    "tenant": "another-tenant",
                    "paper_id": "paper",
                    "revision": None,
                    "offer": DocumentOffer(
                        provider_id="arxiv", url=url + "/document", media_type="text/html"
                    ).model_dump(mode="json"),
                }
            },
        )
        assert denied.structured_content["reason"] == "unauthorized"
        assert authority_calls == []
        resource = await client.read_resource("connector://resources")
        body = resource[0].text.encode()
    context = _mutation_context().model_copy(update={"tenant_id": TENANT})
    key = "paper-runner:bind"
    await engine._send(
        "ConnectorPack",
        {
            "op": {
                "op": "bind",
                "request": {
                    "context": context.model_copy(update={"idempotency_key": key}).model_dump(mode="json"),
                    "connector": CONNECTOR,
                    "importer": "principal:sha256:" + hashlib.sha256(PRINCIPAL.encode()).hexdigest(),
                },
            }
        },
        None,
        idempotency_key=key,
    )
    server_entry = ConnectorPackEntryContent(
        kind=PackEntryKind.MCP_SERVER,
        uri="mcp-server://scholarx-mcp",
        name=CONNECTOR,
        media_type="application/json",
        body=b'{"name":"scholarx-mcp"}',
    )
    resource_entry = ConnectorPackEntryContent(
        kind=PackEntryKind.RESOURCE,
        uri="connector://resources",
        name="connector-resources",
        media_type="application/json",
        body=body,
        output_schema=b'{"type":"object"}',
    )
    result = await ConnectorPackClient(engine).import_pack(
        ConnectorPackArchiveBuilder.build(server_entry, [resource_entry]),
        connector=CONNECTOR,
        server_package_version="1.0.0",
        producer=PackProducer(name="paper-test", version="1"),
        catalog=_catalog(),
        context=context,
    )
    assert result.result == "imported", result
    return engine, server, task, port


async def status(engine):
    async def authority(connector):
        return _catalog(), _mutation_context().model_copy(update={"tenant_id": TENANT})

    return await EpistemicGraphSink(engine, authority).source_status(CONNECTOR, "paper_arxiv_ingest")


async def finish(engine, server, task):
    rows = await engine.query.cypher_read("MATCH (n) RETURN n LIMIT 100")
    server.should_exit = True
    await task
    await engine.close()
    return rows


@pytest.mark.spec("CONN-SCHOLARX-API-COVERAGE-R002")
def test_authenticated_cli_process_restart(live_ingest, monkeypatch, tmp_path):  # noqa: F811
    monkeypatch.setenv(
        "TEST_PAPER_TOKEN_MAP",
        json.dumps({TOKEN: {"client_id": "runner", "tenant_id": TENANT, "scopes": ["paper:read"]}}),
    )
    monkeypatch.setenv("TEST_PAPER_TOKEN", TOKEN)
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

    def feed(paper):
        return f'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/{paper}v1</id><title>Graph paper</title></entry></feed>'.encode()

    headers = {"Content-Type": "application/atom+xml"}
    with ScriptedHttpServer(
        ScriptedResponse(body=feed("1234.5678"), headers=headers),
        ScriptedResponse(status=503),
        ScriptedResponse(status=503),
        ScriptedResponse(status=503),
        ScriptedResponse(body=feed("9876.5432"), headers=headers),
    ) as provider:
        loop = live_ingest._loop
        engine, server, task, port = asyncio.run_coroutine_threadsafe(start(provider.base_url), loop).result(30)
        try:
            config = tmp_path / "runner.yml"
            config.write_text(
                f"connectors:\n  - connector: scholarx-mcp\n    endpoint:\n      url: http://127.0.0.1:{port}/mcp\n      bearer_token: env://TEST_PAPER_TOKEN\n    presets: [paper_arxiv_ingest]\n    provision: false\n    mapping_reference: connector:scholarx-mcp#mappings/Paper\n    max_pages_per_cycle: 1\n"
            )

            def worker():
                return subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__).with_name("paper_runner_process.py")),
                        str(_LIVE["socket"]),
                        str(config),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env=os.environ.copy(),
                )

            first = worker()
            assert first.returncode == 0, first.stderr
            prior = asyncio.run_coroutine_threadsafe(status(engine), loop).result(30)
            failed = worker()
            assert failed.returncode == 1, failed.stderr
            after = asyncio.run_coroutine_threadsafe(status(engine), loop).result(30)
            assert prior.accepted_checkpoint == after.accepted_checkpoint
            second = worker()
            assert second.returncode == 0, second.stderr
            assert "start=1" in provider.requests[4].path
        finally:
            rows = asyncio.run_coroutine_threadsafe(finish(engine, server, task), loop).result(30)
        nodes = [row["n"] for row in rows if row["n"].get("source_stream") == "paper_arxiv_ingest"]
        assert len(nodes) == 2, nodes
