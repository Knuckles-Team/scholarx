# CONN-SCHOLARX-CONNECTOR-CONTENT — The connector serves its packaged content

Owner: scholarx. Cross-repo IDs: `SCION-CONNECTOR-CONTROL-R071`, `SCION-CONNECTOR-CONTROL-R073`.

## Purpose and user stories

The `scholarx-mcp` server serves its packaged skills, prompts and ontology to any client, with no wiring of its own.

## Delivery mapping

Component: scholarx connector

Code: ../../scholarx/__init__.py

## User Scenarios & Testing

### User Story 1 - Citing-papers operation: sx_search action citations (Priority: P1)

The fleet operator and the engine rely on this behaviour of `scholarx`: Add sx_search action citations returning papers that cite a given id. It is proven independently of the other stories.

**Acceptance Scenarios**:

1. **Given** the `scholarx` connector built from the default branch, **When** `tests/test_citing_papers.py::test_sx_search_citations_returns_documented_fields` runs, **Then** test: the action returns the documented fields.

### User Story 2 - Default content (Priority: P1)

The fleet operator and the engine rely on this behaviour of `scholarx`: `pyproject.toml` declares `scholarx-mcp` as the single `scion_sdk.connector` entry point. It is proven independently of the other stories.

**Acceptance Scenarios**:

1. **Given** the `scholarx` connector built from the default branch, **When** `tests/test_default_content_surfaces.py::test_default_content_surfaces` runs, **Then** `resources/list` includes `skill://` and `ontology://`; `prompts/list` includes each packaged prompt.

### User Story 3 - Register the SDK paper tools and provider streams (Priority: P1)

The fleet operator and the engine rely on this behaviour of `scholarx`: Subsystem: connector. It is proven independently of the other stories.

**Acceptance Scenarios**:

1. **Given** the `scholarx` connector built from the default branch, **When** `tests/test_paper_tools_served.py::test_registered_tools_search_and_stream` runs, **Then** test: `tests/test_paper_tools_served.py::test_registered_tools_search_and_stream` (L3) calls the three tools through `tools/call` against controlled provider servers.

### Edge Cases

- The vendor service is unreachable or rejects the credential: the connector returns the SDK typed error and never a partial result.
- An argument outside the documented inputs is refused with the SDK typed refusal and causes no effect on the vendor service.

## Requirements

- **FR-001**: Citing-papers operation: sx_search action citations. Rows: `CONN-SCHOLARX-CONNECTOR-CONTENT-R002`.
- **FR-002**: Default content. Rows: `CONN-SCHOLARX-CONNECTOR-CONTENT-R001`.
- **FR-003**: Register the SDK paper tools and provider streams. Rows: `CONN-SCHOLARX-CONNECTOR-CONTENT-R003`.

## Success Criteria

- **SC-001**: Test: the action returns the documented fields. Rows: `CONN-SCHOLARX-CONNECTOR-CONTENT-R002`.
- **SC-002**: `resources/list` includes `skill://` and `ontology://`; `prompts/list` includes each packaged prompt. Rows: `CONN-SCHOLARX-CONNECTOR-CONTENT-R001`.
- **SC-003**: Test: `tests/test_paper_tools_served.py::test_registered_tools_search_and_stream` (L3) calls the three tools through `tools/call` against controlled provider servers. Rows: `CONN-SCHOLARX-CONNECTOR-CONTENT-R003`.

## Assumptions

- The `scholarx` package keeps the entry point and module layout named in the rows.
- The shared SDK supplies the transport, authentication, retry and certification helpers the rows reuse.

## Why a new spec

Searched `specs/` of `scholarx` with `git grep` for the terms of this spec. No other spec of this repository owns the capability, so this spec owns it.

## Traceability

| Label | Rows | Design section | Test ID | Evidence |
|---|---|---|---|---|
| FR-001 | `CONN-SCHOLARX-CONNECTOR-CONTENT-R002` | plan.md Production caller chain | T-001 | tests/test_citing_papers.py::test_sx_search_citations_returns_documented_fields |
| FR-002 | `CONN-SCHOLARX-CONNECTOR-CONTENT-R001` | plan.md Production caller chain | T-002 | tests/test_default_content_surfaces.py::test_default_content_surfaces |
| FR-003 | `CONN-SCHOLARX-CONNECTOR-CONTENT-R003` | plan.md Production caller chain | T-003 | tests/test_paper_tools_served.py::test_registered_tools_search_and_stream |
