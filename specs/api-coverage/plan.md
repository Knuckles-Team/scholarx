# CONN-SCHOLARX-API-COVERAGE — Design and implementation plan

Governing spec: [spec.md](spec.md).

## Architecture

`register_operation_tools` in `scholarx/mcp_server.py` registers one tool per client operation that the action-routed tools do not expose: `sx_enabled_sources` (read-only), `sx_download_papers` and `sx_download_urls`. Each applies the same input limits as the routed download actions.
