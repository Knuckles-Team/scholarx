# Installation

`scholarx` is a standard Python package and a prebuilt container image. Pick the path
that matches how you want to run it.

## Requirements

- **Python 3.11 – 3.14**.
- Network access to the public research APIs (arXiv, PubMed Central, bioRxiv,
  medRxiv, OSF / PsyArXiv, Semantic Scholar). No backing service to deploy — see
  [Deployment](deployment.md) for the optional API credentials that raise rate limits.

## From PyPI (recommended)

```bash
pip install scholarx
```

### Optional extras

The base install ships the `ScholarXClient` API and the `scholarx` CLI. Install the
extra for the surface you need:

| Extra | Install | Pulls in |
|---|---|---|
| `mcp` | `pip install "scholarx[mcp]"` | FastMCP MCP-server runtime (`agent-utilities[mcp]`) |
| `agent` | `pip install "scholarx[agent]"` | Pydantic-AI agent + Logfire tracing (`agent-utilities[agent,logfire]`) |
| `all` | `pip install "scholarx[all]"` | Both the MCP server and the agent |

```bash
# Typical: run the MCP server and the graph agent
pip install "scholarx[all]"
```

## From source

```bash
git clone https://github.com/Knuckles-Team/scholarx.git
cd scholarx
pip install -e ".[all]"          # editable install with every extra
```

With [`uv`](https://docs.astral.sh/uv/):

```bash
uv pip install -e ".[all]"
uv run scholarx-mcp
```

## Prebuilt Docker image

A multi-stage, slim image is published on every release (entrypoint `scholarx-mcp`):

```bash
docker pull knucklessg1/scholarx:latest

docker run --rm -i \
  -e OSF_TOKEN=... \
  -e S2_API_KEY=... \
  knucklessg1/scholarx:latest        # stdio transport (default)
```

For an HTTP server with a published port, and to run the agent alongside it, see
[Deployment](deployment.md).

## Verify the install

```bash
scholarx --help
scholarx-mcp --help
python -c "import scholarx; print(scholarx.__version__)"
```

## Next steps

- **[Deployment](deployment.md)** — run it as a long-lived MCP server (and agent) behind Caddy + DNS.
- **[Usage](usage.md)** — call the tools, the `ScholarXClient` API, and the CLI.
- **[Configuration](deployment.md#configuration-environment)** — every environment variable.
