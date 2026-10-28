"""A real, ephemeral epistemic-graph server for live-path tests.

Starts the ``epistemic-graph-server`` binary from the ``epistemic-graph[server]``
extra on a private Unix socket with test-only credentials, enrolls the test
signer, creates one graph, and returns a connected
:class:`~agent_connector_sdk.ingest.service.KnowledgeIngest`. Tests skip when
the server package is not installed.
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404 - fixed server argv, test-only
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from agent_connector_sdk.ingest.engine import EngineSettings, connect_ingest
from agent_connector_sdk.ingest.service import KnowledgeIngest

AUDIENCE = "epistemic-graph"
TENANT = "tenant:sdk-test"
POLICY = "policy:current"
PRINCIPAL = "service:connector"
GRAPH = "sdk-live"
_SECRET = "sdk-live-engine-" + "test-secret-0123456789abcdef"  # nosec B105  # sanitizer:ignore - synthetic engine test fixture
_SIGNER_KEY = "sdk-live-engine-" + "signer-key-0123456789abcdef"  # nosec B105  # sanitizer:ignore - synthetic engine test fixture
_DATA_KEY = "sdk-live-engine-" + "encryption-key-0123456789abcdef"  # nosec B105
_SECRET_ENV = "SDK_LIVE_ENGINE_SECRET"  # sanitizer:ignore - environment variable name, not a secret value


def _context(roles: list[str], scopes: list[str]) -> dict[str, object]:
    return {
        "principal": PRINCIPAL,
        "tenant": TENANT,
        "audience": AUDIENCE,
        "agent_id": PRINCIPAL,
        "roles": roles,
        "scopes": scopes,
        "policy_version": POLICY,
        "delegation": [],
    }


#: The socket of the engine the current ``live_ingest`` fixture started.
_LIVE: dict[str, Path] = {}


async def scoped_client(scopes: list[str]) -> Any:
    """Another client on the live engine's graph with ``scopes``."""
    from epistemic_graph import EpistemicGraphClient

    return await EpistemicGraphClient.connect(
        socket_path=str(_LIVE["socket"]),
        auth_secret=_SECRET,
        graph_name=GRAPH,
        verified_context=_context(["connector"], scopes),
    )


def _wait_for(socket_path: Path, proc: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("epistemic-graph-server exited during startup")
        if socket_path.exists():
            return
        time.sleep(0.05)
    raise RuntimeError("epistemic-graph-server did not open its socket")


def _bootstrap(socket_path: Path) -> None:
    from epistemic_graph.client import SyncEpistemicGraphClient

    client = SyncEpistemicGraphClient.connect(
        socket_path=str(socket_path),
        auth_secret=_SECRET,
        verified_context=_context([], ["security:bootstrap"]),
    )
    try:
        client.consensus.bootstrap_system_identity(agent_id=PRINCIPAL, signer_id=PRINCIPAL, signer_key=_SIGNER_KEY)
    finally:
        client.close()
    client = SyncEpistemicGraphClient.connect(
        socket_path=str(socket_path),
        auth_secret=_SECRET,
        verified_context=_context(["test"], ["*"]),
    )
    try:
        client.tenants.create(GRAPH)
    finally:
        client.close()


@pytest.fixture
def live_ingest(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Iterator[KnowledgeIngest]:
    """A knowledge-ingest service connected to a fresh real engine."""
    from epistemic_graph.server_binary import (
        ServerBinaryNotFoundError,
        resolve_server_binary,
    )

    try:
        binary = resolve_server_binary()
    except ServerBinaryNotFoundError:
        pytest.skip("epistemic-graph[server] is not installed")
    root = Path(tmp_path_factory.mktemp("eg"))
    socket_path = root / "eg.sock"
    (root / "security").mkdir()
    env = {
        **os.environ,
        "GRAPH_SERVICE_AUTH_SECRET": _SECRET,
        "EPISTEMIC_GRAPH_AUDIENCE": AUDIENCE,
        "EPISTEMIC_GRAPH_TENANT": TENANT,
        "EPISTEMIC_GRAPH_POLICY_VERSION": POLICY,
        "EPISTEMIC_GRAPH_REQUIRE_OIDC": "false",
        "EPISTEMIC_GRAPH_SECURITY_STATE_DIR": str(root / "security"),
        "EPISTEMIC_GRAPH_SIGNER_KEYS_JSON": json.dumps(
            {
                PRINCIPAL: {
                    "key": _SIGNER_KEY,
                    "allowed_roles": [],
                    "may_grant_system": True,
                }
            }
        ),
        "EPISTEMIC_GRAPH_ENCRYPTION_KEY": _DATA_KEY,
    }
    with (root / "engine.log").open("wb") as log:
        proc = subprocess.Popen(  # nosec B603 - fixed argv
            [
                binary,
                "--socket-path",
                str(socket_path),
                "--auth-secret",
                _SECRET,
                "--persist-dir",
                str(root / "data"),
            ],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_for(socket_path, proc)
            _bootstrap(socket_path)
            _LIVE["socket"] = socket_path
            monkeypatch.setenv(_SECRET_ENV, _SECRET)
            yield connect_ingest(
                EngineSettings(
                    endpoint=f"unix://{socket_path}",
                    auth_secret_ref=f"env://{_SECRET_ENV}",
                    tenant=TENANT,
                    graph=GRAPH,
                    principal=PRINCIPAL,
                    policy_version=POLICY,
                )
            )
        finally:
            proc.terminate()
            proc.wait(timeout=30)
