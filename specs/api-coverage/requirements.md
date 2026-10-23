# CONN-SCHOLARX-API-COVERAGE — Requirements

Governing spec: [spec.md](spec.md).

Each row is one requirement. A row names the file it touches and the test that proves it. The generator sets each row's state in `status.json`.

| ID | Requirement | Acceptance |
|---|---|---|
| `CONN-SCHOLARX-API-COVERAGE-R001` | **One tool per operation.** `scholarx/mcp_server.py` exposes `sx_enabled_sources` (read-only), `sx_download_papers` and `sx_download_urls`, one per `ScholarXClient` operation. The coverage baseline in `scripts/verify_api_integration.py` is 90.0 and the measured coverage is at least 90. Proving test: `tests/test_operation_tools.py`. | The three tools are listed with the right annotations, return the client results, and the coverage check reports at least 90 percent. |
