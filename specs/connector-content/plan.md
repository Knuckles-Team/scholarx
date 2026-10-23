# CONN-SCHOLARX-CONNECTOR-CONTENT — Design and implementation plan

Governing spec: [spec.md](spec.md).

## Architecture

`pyproject.toml` declares `scholarx-mcp` as the connector identity. `create_mcp_server` resolves the packaged content of `scholarx` from it.
