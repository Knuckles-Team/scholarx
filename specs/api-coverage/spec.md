# CONN-SCHOLARX-API-COVERAGE — Direct tools cover uncovered API operations

Owner: scholarx. Cross-repo IDs: none.

## Purpose and user stories

The `scholarx-mcp` server exposes direct tools for client operations that are not
already covered by the action-routed surface. The canonical
`connector-standard` aggregate runs the API-parity check against the measured
repository baseline configured in `pyproject.toml`; the baseline is an explicit
gate threshold and does not claim that every client method is exposed.

## Delivery mapping

Component: scholarx connector

Code: ../../scholarx/__init__.py

## User Scenarios & Testing

### User Story 1 - Direct operation tools (Priority: P1)

The fleet operator and the engine rely on this behaviour of `scholarx`: `scholarx/mcp_server.py` exposes `sx_enabled_sources` (read-only), `sx_download_papers` and `sx_download_urls` for client operations not already covered by the action-routed surface. It is proven independently of the other stories.

**Acceptance Scenarios**:

1. **Given** the `scholarx` connector built from the default branch, **When** `tests/test_operation_tools.py::test_tools_are_registered_with_hints` runs, **Then** the three tools are listed with the right annotations, return the client results, and the canonical connector-standard API-parity check passes at the repository's measured baseline.

### User Story 2 - Paper maintenance tool (Priority: P1)

The fleet operator and the engine rely on this behaviour of `scholarx`: Subsystem: scholarx served tools (new spec in scholarx). It is proven independently of the other stories.

**Acceptance Scenarios**:

1. **Given** the `scholarx` connector built from the default branch, **When** `tests/test_paper_maintenance_tool.py::test_tool_binds_the_scholarx_stream` runs, **Then** test: `tests/test_paper_maintenance_tool.py::test_tool_binds_the_scholarx_stream` (L3). A served test applies an order against the scholarx stream and reads the receipt.

### User Story 3 - Paper ingest job stages and admits (Priority: P1)

The fleet operator and the engine rely on this behaviour of `scholarx`: Subsystem: scholarx ingest job. It is proven independently of the other stories.

**Acceptance Scenarios**:

1. **Given** the `scholarx` connector built from the default branch, **When** `scholarx/kg_ingest.py::ingest_entities` runs, **Then** test: `tests/test_paper_ingest_admission.py::test_ingest_job_uses_staging_and_admission` (L3). A served test asserts that no claim exists for the excluded paper.

### Edge Cases

- The vendor service is unreachable or rejects the credential: the connector returns the SDK typed error and never a partial result.
- An argument outside the documented inputs is refused with the SDK typed refusal and causes no effect on the vendor service.

## Requirements

- **FR-001**: Direct operation tools. Rows: `CONN-SCHOLARX-API-COVERAGE-R001`.
- **FR-002**: Paper maintenance tool. Rows: `CONN-SCHOLARX-API-COVERAGE-R002`.
- **FR-003**: Paper ingest job stages and admits. Rows: `CONN-SCHOLARX-API-COVERAGE-R003`.

## Success Criteria

- **SC-001**: The three tools are listed with the right annotations, return the client results, and the canonical connector-standard API-parity check passes at the repository's measured baseline. Rows: `CONN-SCHOLARX-API-COVERAGE-R001`.
- **SC-002**: Test: `tests/test_paper_maintenance_tool.py::test_tool_binds_the_scholarx_stream` (L3). A served test applies an order against the scholarx stream and reads the receipt. Rows: `CONN-SCHOLARX-API-COVERAGE-R002`.
- **SC-003**: Test: `tests/test_paper_ingest_admission.py::test_ingest_job_uses_staging_and_admission` (L3). A served test asserts that no claim exists for the excluded paper. Rows: `CONN-SCHOLARX-API-COVERAGE-R003`.

## Assumptions

- The `scholarx` package keeps the entry point and module layout named in the rows.
- The shared SDK supplies the transport, authentication, retry and certification helpers the rows reuse.

## Why a new spec

Searched `specs/` of `scholarx` with `git grep` for the terms of this spec. No other spec of this repository owns the capability, so this spec owns it.

## Traceability

| Label | Rows | Design section | Test ID | Evidence |
|---|---|---|---|---|
| FR-001 | `CONN-SCHOLARX-API-COVERAGE-R001` | plan.md Production caller chain | T-001 | tests/test_operation_tools.py::test_tools_are_registered_with_hints |
| FR-002 | `CONN-SCHOLARX-API-COVERAGE-R002` | plan.md Production caller chain | T-002 | tests/test_paper_maintenance_tool.py::test_tool_binds_the_scholarx_stream |
| FR-003 | `CONN-SCHOLARX-API-COVERAGE-R003` | plan.md Production caller chain | T-003 | scholarx/kg_ingest.py::ingest_entities |
