# CONN-SCHOLARX-API-COVERAGE — Requirements

Governing spec: [spec.md](spec.md).

Each row is one requirement. A row names the file it touches and the test that proves it. The generator sets each row's state in `status.json`.

| ID | Requirement | Acceptance |
|---|---|---|
| `CONN-SCHOLARX-API-COVERAGE-R001` | **Direct operation tools.** `scholarx/mcp_server.py` exposes `sx_enabled_sources` (read-only), `sx_download_papers` and `sx_download_urls` for client operations not already covered by the action-routed surface. The canonical API-parity baseline is the measured `50.0` value configured in `pyproject.toml`; it is a gate threshold and does not claim complete client-method coverage. Proving test: `tests/test_operation_tools.py`. | The three tools are listed with the right annotations, return the client results, and the canonical connector-standard API-parity check passes at the repository's measured baseline. |
