# CONN-SCHOLARX-API-COVERAGE — Design and implementation plan

Governing spec: [spec.md](spec.md).

## Architecture

`register_operation_tools` in `scholarx/mcp_server.py` registers direct tools for client operations that the action-routed tools do not expose: `sx_enabled_sources` (read-only), `sx_download_papers` and `sx_download_urls`. Each applies the same input limits as the routed download actions. The canonical API-parity baseline is recorded in `pyproject.toml` and is a measured gate threshold, not a claim of complete client-method coverage.

## Shared paper-source integration

A host supplies an authenticated paper search service and its shared EG quota.
Each source reads bounded pages through the SDK governed HTTP client. PMC holds
one quota slot across search and summary requests, with admitted spacing.
bioRxiv and medRxiv bind their date interval into the continuation and advance
only through records actually scanned. Each source retains identity and field
locations for exact SDK normalization. Malformed responses and upstream errors
are explicit refusals. The existing fuzzy aggregate search remains separate.
The host supplies authorization and storage admission for the document tool.
Only host-configured provider streams advertise live source metadata. The
connector must be certified against the authenticated host before deployment.

The host may bind paper access to the verified MCP bearer identity. It chooses
the tenant claim and required scopes. Missing identity, session, tenant or
scope refuses access. A query tenant must match the verified token's tenant.
This check does not select a credential or grant storage access.
