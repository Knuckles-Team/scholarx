# CONN-SCHOLARX-API-COVERAGE — Implementation plan

Governing spec: [spec.md](spec.md). Rows: [requirements.md](requirements.md).

## Summary

This plan states how `scholarx` delivers the rows of `CONN-SCHOLARX-API-COVERAGE`. The live caller is the `scholarx` console script. The owner is the `scholarx` package. The rows reuse the `scion-sdk` helpers and add no second authority. The plan changes no runtime code.

## Technical Context

- **Language/Version**: Python >=3.12, <3.15
- **Primary Dependencies**: scion-sdk[mcp]>=0.6.4,<0.7.0; fastmcp; further pins in `pyproject.toml` (scion-sdk[mcp]>=0.6.4,<0.7.0, httpx>=0.28.1, python-dotenv>=1.2.4, Levenshtein>=0.27.5, pypdf>=6.21.0, rich>=15.0.0)
- **Storage**: N/A, the connector keeps no store of its own
- **Testing**: pytest; each row names the proving test as `path::name`
- **Target Platform**: Linux container and stdio or streamable HTTP MCP clients
- **Project Type**: connector
- **Performance Goals**: N/A, the vendor service sets the latency
- **Constraints**: vendor calls go through the SDK governed client; no connector-local transport
- **Scale/Scope**: 3 active row(s) in this spec

## Constitution Check

- Organization constitution 1.5.0, spec-first change: pass. Every behaviour is a row of this spec with a bound or planned test.
- Repository article R-I, connector scope: pass. The rows stay inside this connector's one external system and reuse the SDK for shared capabilities.

## Project Structure

- `scholarx/mcp_server.py` (existing)
- `pyproject.toml` (existing)
- `tests/test_operation_tools.py` (existing)
- `scholarx/kg_ingest.py` (existing)
- `tests/test_paper_maintenance_tool.py` (new, planned)
- `tests/test_paper_ingest_admission.py` (new, planned)

## Phase 0: Research

No unknowns. Every row names its code and test; the caller chain of each row was read from the code.

## Phase 1: Design

### Architecture

`register_operation_tools` in `scholarx/mcp_server.py` registers direct tools for client operations that the action-routed tools do not expose: `sx_enabled_sources` (read-only), `sx_download_papers` and `sx_download_urls`. Each applies the same input limits as the routed download actions. The canonical API-parity baseline is recorded in `pyproject.toml` and is a measured gate threshold, not a claim of complete client-method coverage.

### Adoption of scion-sdk 0.10.0 (CONN-SCHOLARX-API-COVERAGE-R004)

- Owner. This repository, the import lines named in `CONN-SCHOLARX-API-COVERAGE-R004`. The paths belong to scion-sdk.
- Cohesion. The import edits, the pin and the lock change together and sit in one change.
- Dependency direction. The connector imports public modules of the SDK units; no import points to a private module.
- Interface depth. The connector uses the public surface only.
- Special cases. None. Every removed path takes the same replacement, with no alias.
- State. None.
- Environment. None. The pin is package metadata, not environment code.

## Phase 2: Task approach

`tasks.md` holds one task per row, producer first. Rows that depend on none run in parallel. A task is checked when its `Spec:` trailer is on the default branch.

## Complexity Tracking

None. The constitution check passed.

## Build contract

- `pre-commit run --all-files` runs ruff check, ruff format, the shared `connector-standard`, `spec`, `secrets` and `dependency-readiness` gates at the pinned shared revision.
- `uv run pytest tests` runs the proving tests; the shared complexity, duplication and KISS gates apply their org thresholds and this repository sets no local override.
- A change adds no scanner suppression and no duplicate implementation of an SDK helper.

## Production caller chain

- `CONN-SCHOLARX-API-COVERAGE-R001`: an MCP client calls `sx_enabled_sources` (scholarx/mcp_server.py:510), `sx_download_papers` or `sx_download_urls` in `scholarx/mcp_server.py`, which call the matching client methods.
- `CONN-SCHOLARX-API-COVERAGE-R002`: process start runs `scholarx/mcp_server.py`, which calls `register_paper_maintenance_tool` from `scion_sdk.adapters.paper_tool` with the sink used by `scholarx/kg_ingest.py`.
- `CONN-SCHOLARX-API-COVERAGE-R003`: the ingest job calls `ingest_entities` in `scholarx/kg_ingest.py`, which calls `stage_papers` and `admit_staged_papers` from `scion_sdk.adapters.paper_admission`.

## Cross-repo seams

None. The rows depend only on the published `scion-sdk` package, which the connector imports.
