# CONN-SCHOLARX-API-COVERAGE — Requirements

Governing spec: [spec.md](spec.md).

Each row is one requirement. A row names the file it touches and the test that proves it. The generator sets each row's state in `status.json`.

| ID | Requirement | Acceptance |
|---|---|---|
| `CONN-SCHOLARX-API-COVERAGE-R001` | **Direct operation tools.** `scholarx/mcp_server.py` exposes `sx_enabled_sources` (read-only), `sx_download_papers` and `sx_download_urls` for client operations not already covered by the action-routed surface. The canonical API-parity baseline is the measured `50.0` value configured in `pyproject.toml`; it is a gate threshold and does not claim complete client-method coverage. Proving test: `tests/test_operation_tools.py`. | The three tools are listed with the right annotations, return the client results, and the canonical connector-standard API-parity check passes at the repository's measured baseline. |
| `CONN-SCHOLARX-API-COVERAGE-R002` | **Shared paper search source.** A host-authorized ScholarX registrar exposes paper search, document transfer, and per-provider ingest streams. Bounded adapters cover arXiv, PMC, bioRxiv, medRxiv, OSF, PsyArXiv, and Semantic Scholar. Each uses governed HTTP and retains source field evidence. Search never uses fuzzy title matching. The host supplies tenant authorization and quota policy. | `tests/test_paper_source_contract.py` checks controlled provider pages, pagination, and refusals. SDK integration tests cover served operations, real EG quota, document bytes, accepted graph checkpoints, and failure without cursor advance. |
