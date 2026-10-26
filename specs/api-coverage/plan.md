# CONN-SCHOLARX-API-COVERAGE — Design and implementation plan

Governing spec: [spec.md](spec.md).

## Architecture

`register_operation_tools` in `scholarx/mcp_server.py` registers direct tools for client operations that the action-routed tools do not expose: `sx_enabled_sources` (read-only), `sx_download_papers` and `sx_download_urls`. Each applies the same input limits as the routed download actions. The canonical API-parity baseline is recorded in `pyproject.toml` and is a measured gate threshold, not a claim of complete client-method coverage.
