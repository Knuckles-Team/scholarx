# Scholarx
## CLI or API | MCP | Agent

![PyPI - Version](https://img.shields.io/pypi/v/scholarx)
![MCP Server](https://badge.mcpx.dev?type=server 'MCP Server')
![PyPI - Downloads](https://img.shields.io/pypi/dd/scholarx)
![GitHub Repo stars](https://img.shields.io/github/stars/Knuckles-Team/scholarx)
![GitHub forks](https://img.shields.io/github/forks/Knuckles-Team/scholarx)
![GitHub contributors](https://img.shields.io/github/contributors/Knuckles-Team/scholarx)
![PyPI - License](https://img.shields.io/pypi/l/scholarx)
![GitHub](https://img.shields.io/github/license/Knuckles-Team/scholarx)
![GitHub last commit (by committer)](https://img.shields.io/github/last-commit/Knuckles-Team/scholarx)
![GitHub pull requests](https://img.shields.io/github/issues-pr/Knuckles-Team/scholarx)
![GitHub closed pull requests](https://img.shields.io/github/issues-pr-closed/Knuckles-Team/scholarx)
![GitHub issues](https://img.shields.io/github/issues/Knuckles-Team/scholarx)
![GitHub top language](https://img.shields.io/github/languages/top/Knuckles-Team/scholarx)
![GitHub language count](https://img.shields.io/github/languages/count/Knuckles-Team/scholarx)
![GitHub repo size](https://img.shields.io/github/repo-size/Knuckles-Team/scholarx)
![GitHub repo file count (file type)](https://img.shields.io/github/directory-file-count/Knuckles-Team/scholarx)
![PyPI - Wheel](https://img.shields.io/pypi/wheel/scholarx)
![PyPI - Implementation](https://img.shields.io/pypi/implementation/scholarx)

*Version: 0.30.0*

> **Documentation** — Installation, deployment, usage across the API, CLI, MCP, and
> agent interfaces are maintained in the
> [official documentation](https://knuckles-team.github.io/scholarx/).

---

## Overview

**Scholarx** is a production-grade Agent and Model Context Protocol (MCP) server designed to interface directly with Universal Research Paper API — single entry point for arXiv, PMC, bioRxiv, medRxiv, PsyArXiv, OSF, and Semantic Scholar.

---

## Key Features

- **Consolidated Action-Routed MCP Tools:** Minimizes token overhead and eliminates tool bloat in LLM contexts by grouping methods into optimized, togglable tool modules.
- **Enterprise-Grade Security:** Comprehensive support for Eunomia policies, OIDC token delegation, and granular execution context tracking.
- **Integrated Graph Agent:** Built-in Pydantic AI agent supporting the Agent Control Protocol (ACP) and standard Web interfaces (AG-UI).
- **Native Telemetry & Tracing:** Out-of-the-box OpenTelemetry exports and native Langfuse tracing.

---

## CLI or API

This agent wraps the Universal Research Paper API — single entry point for arXiv, PMC, bioRxiv, medRxiv, PsyArXiv, OSF, and Semantic Scholar API. You can interact with it programmatically or via its integrated execution entrypoints.

Detailed instructions on how to use the underlying API wrappers, extended schema bindings, and developer SDK references are maintained in [docs/index.md](docs/index.md).

---

## MCP

This server utilizes dynamic Action-Routed tools to optimize token overhead and maximize IDE compatibility.

### Available MCP Tools

The table below is auto-generated from the MCP server — do not edit by hand.

<!-- MCP-TOOLS-TABLE:START -->

| MCP Tool | Toggle Env Var | Description |
|----------|----------------|-------------|
| `sx_info` | `DISCOVERYTOOL` | Get metadata about sources and categories. |
| `sx_search` | `SEARCHTOOL` | Search for research papers across all configured sources. |
| `sx_storage` | `STORAGETOOL` | Manage offline PDF storage and background downloads. |

_3 action-routed tools (default `MCP_TOOL_MODE=condensed`). Each is enabled unless its toggle is set false; set `MCP_TOOL_MODE=verbose` (or `both`) for the 1:1 per-operation surface. Auto-generated — do not edit._
<!-- MCP-TOOLS-TABLE:END -->

Detailed tool schemas, parameter shapes, and validation constraints are preserved in [docs/mcp.md](docs/mcp.md).

### Dynamic Tool Selection & Visibility

This MCP server supports dynamic toolset selection and visibility filtering at runtime. This allows you to restrict the set of exposed tools in order to prevent blowing up the LLM's context window.

You can configure tool filtering via multiple input channels:

- **CLI Arguments:** Pass `--tools` or `--toolsets` (or their disabled counterparts `--disabled-tools` and `--disabled-toolsets`) during startup.
- **Environment Variables:** Define standard environment variables:
  - `MCP_ENABLED_TOOLS` / `MCP_DISABLED_TOOLS`
  - `MCP_ENABLED_TAGS` / `MCP_DISABLED_TAGS`
- **HTTP SSE Request Headers:** Pass custom headers during transport initialization:
  - `x-mcp-enabled-tools` / `x-mcp-disabled-tools`
  - `x-mcp-enabled-tags` / `x-mcp-disabled-tags`
- **HTTP SSE Request Query Parameters:** Append query parameters directly to your transport connection URL:
  - `?tools=tool1,tool2`
  - `?tags=tag1`

When query strings or parameters are supplied, an LLM-free **Knowledge Graph resolution layer** (using `DynamicToolOrchestrator`) matches query intents against known tool tags, names, or descriptions, with safe fallback and automated 24-hour background cache refreshing.

---

### MCP Configuration Examples

> **Install the slim `[mcp]` extra.** All examples below install
> `scholarx[mcp]` — the MCP-server extra that pulls only the FastMCP /
> FastAPI tooling (`agent-utilities[mcp]`). It deliberately **excludes** the heavy
> agent runtime (the epistemic-graph engine, `pydantic-ai`, `dspy`, `llama-index`,
> `tree-sitter`), so `uvx`/container installs are dramatically smaller and faster.
> Use the full `[agent]` extra only when you need the integrated Pydantic AI agent
> (see [Installation](#installation)).

#### stdio Transport (Recommended for local IDEs e.g., Cursor, Claude Desktop)
Configure your IDE's `mcp.json` to launch the MCP server via `uvx`:

```json
{
  "mcpServers": {
    "scholarx": {
      "command": "uvx",
      "args": [
        "--from",
        "scholarx[mcp]",
        "scholarx-mcp"
      ],
      "env": {
        "SCHOLARX_STORAGE_DIR": "your_scholarx_storage_dir_here",
        "DEBUG": "your_debug_here",
        "PYTHONUNBUFFERED": "your_pythonunbuffered_here",
        "SERVICENOW_INSTANCE": "your_servicenow_instance_here",
        "SERVICENOW_USERNAME": "your_servicenow_username_here",
        "OSF_TOKEN": "your_osf_token_here",
        "S2_API_KEY": "your_s2_api_key_here",
        "NCBI_API_KEY": "your_ncbi_api_key_here",
        "SERVICENOW_PASSWORD": "your_servicenow_password_here"
      }
    }
  }
}
```

#### Streamable-HTTP Transport (Recommended for production deployments)
Configure your client's `mcp.json` to launch the Streamable-HTTP server via `uvx` with explicit host and port definition:

```json
{
  "mcpServers": {
    "scholarx": {
      "command": "uvx",
      "args": [
        "--from",
        "scholarx[mcp]",
        "scholarx-mcp"
      ],
      "env": {
        "TRANSPORT": "streamable-http",
        "HOST": "0.0.0.0",
        "PORT": "8000",
        "SCHOLARX_STORAGE_DIR": "your_scholarx_storage_dir_here",
        "DEBUG": "your_debug_here",
        "PYTHONUNBUFFERED": "your_pythonunbuffered_here",
        "SERVICENOW_INSTANCE": "your_servicenow_instance_here",
        "SERVICENOW_USERNAME": "your_servicenow_username_here",
        "OSF_TOKEN": "your_osf_token_here",
        "S2_API_KEY": "your_s2_api_key_here",
        "NCBI_API_KEY": "your_ncbi_api_key_here",
        "SERVICENOW_PASSWORD": "your_servicenow_password_here"
      }
    }
  }
}
```

Alternatively, connect to a pre-deployed remote or local Streamable-HTTP instance:

```json
{
  "mcpServers": {
    "scholarx": {
      "url": "http://localhost:8004/scholarx/mcp"
    }
  }
}
```

Deploying the Streamable-HTTP server via Docker:

```bash
docker run -d \
  --name scholarx-mcp \
  -p 8004:8004 \
  -e TRANSPORT=streamable-http \
  -e PORT=8004 \
  -e SCHOLARX_STORAGE_DIR="your_value" \
  -e DEBUG="your_value" \
  -e PYTHONUNBUFFERED="your_value" \
  -e SERVICENOW_INSTANCE="your_value" \
  -e SERVICENOW_USERNAME="your_value" \
  -e OSF_TOKEN="your_value" \
  -e S2_API_KEY="your_value" \
  -e NCBI_API_KEY="your_value" \
  -e SERVICENOW_PASSWORD="your_value" \
  knucklessg1/scholarx:mcp
```

> The `:mcp` tag is the **slim MCP-server image** (built from
> `docker/Dockerfile --target mcp`, installing `scholarx[mcp]`). The default
> `:latest` tag is the **full agent image** (`--target agent`, `scholarx[agent]`)
> which also bundles the Pydantic AI agent and the epistemic-graph engine — use it
> when you run `scholarx-agent` (the agent), not just the MCP server. See
> [Container images](#container-images-mcp-vs-agent).

---

<!-- BEGIN GENERATED: additional-deployment-options -->
### Additional Deployment Options

`scholarx` can also run as a **local container** (Docker / Podman / `uv`) or be
consumed from a **remote deployment**. The
[Deployment guide](https://knuckles-team.github.io/scholarx/deployment/) has full, copy-paste
`mcp_config.json` for all four transports — **stdio**, **streamable-http**,
**local container / uv**, and **remote URL**:

- **Local container / uv** — launch the server from `mcp_config.json` via `uvx`,
  `docker run`, or `podman run`, or point at a local streamable-http container by `url`.
- **Remote URL** — connect to a server deployed behind Caddy at
  `http://scholarx-mcp.arpa/mcp` using the `"url"` key.
<!-- END GENERATED: additional-deployment-options -->

## Agent

This repository features a fully integrated Pydantic AI Graph Agent. It communicates over the **Agent Control Protocol (ACP)** and interacts seamlessly with the **Agent Web UI (AG-UI)** and Terminal interface.

### Running the Agent CLI
To start the interactive command-line agent:

```bash
# Set credentials
export SCHOLARX_STORAGE_DIR="your_value"
export DEBUG="your_value"
export PYTHONUNBUFFERED="your_value"
export SERVICENOW_INSTANCE="your_value"
export SERVICENOW_USERNAME="your_value"
export OSF_TOKEN="your_value"
export S2_API_KEY="your_value"
export NCBI_API_KEY="your_value"
export SERVICENOW_PASSWORD="your_value"

# Run the agent server
scholarx-agent --provider openai --model-id gpt-4o
```

### Docker Compose Orchestration
The following `docker/agent.compose.yml` configures the Agent, Web UI, and Terminal Interface together:

```yaml
version: '3.8'

services:
  scholarx-mcp:
    image: knucklessg1/scholarx:latest
    container_name: scholarx-mcp
    hostname: scholarx-mcp
    restart: always
    env_file:
      - ../.env
    environment:
      - PYTHONUNBUFFERED=1
      - HOST=0.0.0.0
      - PORT=8004
      - TRANSPORT=streamable-http
    ports:
      - "8004:8004"
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8004/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  scholarx-agent:
    image: knucklessg1/scholarx:latest
    container_name: scholarx-agent
    hostname: scholarx-agent
    restart: always
    depends_on:
      - scholarx-mcp
    env_file:
      - ../.env
    command: [ "scholarx-agent" ]
    environment:
      - PYTHONUNBUFFERED=1
      - HOST=0.0.0.0
      - PORT=9600
      - MCP_URL=http://scholarx-mcp:8004/mcp
      - PROVIDER=${PROVIDER:-openai}
      - MODEL_ID=${MODEL_ID:-gpt-4o}
      - ENABLE_WEB_UI=True
      - ENABLE_OTEL=True
    ports:
      - "9600:9600"
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:9600/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

```

Detailed graph node architecture explanations, custom skill configurations, and agentic trace guides are available in [docs/agent.md](docs/agent.md).

---

## Security & Governance

Built directly upon the enterprise-ready [`agent-utilities`](https://github.com/Knuckles-Team/agent-utilities) core, standard security parameters are fully supported:

### Access Control & Policy Enforcement
- **Eunomia Policies:** Fine-grained, policy-driven tool authorization. Supports `none`, local `embedded` (`mcp_policies.json`), or centralized `remote` modes.
- **OIDC Token Delegation:** Compliant with RFC 8693 token exchange for flowing authenticating user credentials from Web UI / ACP → Agent → MCP.
- **Scoped Credentials:** Execution context runs restricted to the specific caller identity.

### Runtime Security Grid
| Feature | Functionality | Enablement |
|---------|---------------|------------|
| **Tool Guard** | Sensitivity inspection with human-in-the-loop validation | Enabled by default |
| **Prompt Injection Defense** | Input scanning, repetition monitoring, and recursive loop blocks | Enabled by default |
| **Context Safety Guard** | Stuck-loop detectors and contextual overflow preemptive alerts | Enabled by default |

---

## Environment Variables

<!-- ENV-VARS-TABLE:START -->

#### Package environment variables

| Variable | Example | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` |  |
| `PORT` | `8004` |  |
| `TRANSPORT` | `stdio` | options: stdio, streamable-http, sse |
| `AUTH_TYPE` | `none` | options: none, basic, custom |
| `DEFAULT_AGENT_NAME` | `ScholarX Agent` |  |
| `ENABLE_OTEL` | `True` |  |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:8080/api/public/otel` |  |
| `OTEL_EXPORTER_OTLP_PUBLIC_KEY` | `pk-...` |  |
| `OTEL_EXPORTER_OTLP_SECRET_KEY` | `sk-...` |  |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` |  |
| `EUNOMIA_TYPE` | `none` | options: none, embedded, remote |
| `EUNOMIA_POLICY_FILE` | `mcp_policies.json` |  |
| `EUNOMIA_REMOTE_URL` | `http://eunomia-server:8000` |  |
| `SCHOLARX_STORAGE_DIR` | — | Custom storage dir (default: ~/.scholarx/papers) |
| `DEBUG` | `False` |  |
| `PYTHONUNBUFFERED` | `1` |  |
| `SERVICENOW_INSTANCE` | `https://dev350360.service-now.com` |  |
| `SERVICENOW_USERNAME` | `admin` |  |
| `OSF_TOKEN` | `your_osf_token_here` |  |
| `S2_API_KEY` | `your_s2_api_key_here` |  |
| `NCBI_API_KEY` | `your_ncbi_api_key_here` |  |
| `SERVICENOW_PASSWORD` | `your_servicenow_password_here` |  |
| `SEARCHTOOL` | `True` |  |
| `DISCOVERYTOOL` | `True` |  |
| `STORAGETOOL` | `True` |  |

#### Inherited agent-utilities variables (apply to every connector)

| Variable | Example | Description |
|----------|---------|-------------|
| `MCP_TOOL_MODE` | `condensed` | Tool surface: `condensed` | `verbose` | `both` |
| `MCP_ENABLED_TOOLS` | — | Comma-separated tool allow-list |
| `MCP_DISABLED_TOOLS` | — | Comma-separated tool deny-list |
| `MCP_ENABLED_TAGS` | — | Comma-separated tag allow-list |
| `MCP_DISABLED_TAGS` | — | Comma-separated tag deny-list |
| `MCP_CLIENT_AUTH` | — | Outbound MCP auth (`oidc-client-credentials` for fleet calls) |
| `OIDC_CLIENT_ID` | — | OIDC client id (service-account auth) |
| `OIDC_CLIENT_SECRET` | — | OIDC client secret (service-account auth) |
| `MCP_URL` | `http://localhost:8000/mcp` | URL of the MCP server the agent connects to |
| `PROVIDER` | `openai` | LLM provider for the agent |
| `MODEL_ID` | `gpt-4o` | Model id for the agent |
| `ENABLE_WEB_UI` | `True` | Serve the AG-UI web interface |

_25 package + 12 inherited variable(s). Auto-generated from `.env.example` + the shared agent-utilities set — do not edit._
<!-- ENV-VARS-TABLE:END -->


The application can be configured using the following environment variables:

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `HOST` | String | `0.0.0.0` | Host IP address to bind the servers to. |
| `PORT` | Integer | `8004` | Port number to run the servers on. |
| `TRANSPORT` | String | `stdio` | MCP transport type (`stdio`, `streamable-http`, `sse`). |
| `AUTH_TYPE` | String | `none` | Authentication type for access control (`none`, `basic`, `custom`). |
| `DEFAULT_AGENT_NAME` | String | `ScholarX Agent` | Custom display name for the Pydantic AI Graph Agent. |
| `ENABLE_OTEL` | Boolean | `True` | Enable OpenTelemetry tracing and exports. |
| `EUNOMIA_TYPE` | String | `none` | Eunomia policy evaluation mode (`none`, `embedded`, `remote`). |
| `EUNOMIA_POLICY_FILE` | String | `mcp_policies.json` | Path to the local Eunomia policy configuration file. |
| `EUNOMIA_REMOTE_URL` | String | | Centralized Eunomia server endpoint. |
| `SCHOLARX_STORAGE_DIR` | String | `~/.local/share/scholarx/papers` | Directory path where downloaded PDF papers are cached. |
| `DEBUG` | Boolean | `False` | Enable verbose debugging mode. |
| `PYTHONUNBUFFERED` | Integer | `1` | Forces stdout and stderr to be unbuffered. |
| `SERVICENOW_INSTANCE` | String | | ServiceNow instance base URL. |
| `SERVICENOW_USERNAME` | String | | ServiceNow account username. |
| `SERVICENOW_PASSWORD` | String | | ServiceNow account password. |
| `OSF_TOKEN` | String | | API Access Token for OSF integration. |
| `S2_API_KEY` | String | | Semantic Scholar API Key to bypass public rate limits. |
| `NCBI_API_KEY` | String | | NCBI API Key for PubMed Central (PMC) queries. |
| `SEARCHTOOL` | Boolean | `True` | Toggle to enable/disable Search MCP tool category. |
| `DISCOVERYTOOL` | Boolean | `True` | Toggle to enable/disable Discovery MCP tool category. |
| `STORAGETOOL` | Boolean | `True` | Toggle to enable/disable Storage MCP tool category. |

---

## Installation

Pick the extra that matches what you want to run:

| Extra | Installs | Use when |
|-------|----------|----------|
| `scholarx[mcp]` | Slim MCP server only (`agent-utilities[mcp]` — FastMCP/FastAPI) | You only run the **MCP server** (smallest install / image) |
| `scholarx[agent]` | Full agent runtime (`agent-utilities[agent,logfire]` — Pydantic AI + the epistemic-graph engine) | You run the **integrated agent** |
| `scholarx[all]` | Everything (`mcp` + `agent`) | Development / both surfaces |

```bash
# MCP server only (recommended for tool hosting — slim deps)
uv pip install "scholarx[mcp]"

# Full agent runtime (Pydantic AI + epistemic-graph engine)
uv pip install "scholarx[agent]"

# Everything (development)
uv pip install "scholarx[all]"      # or: python -m pip install "scholarx[all]"
```

### Container images (`:mcp` vs `:agent`)

One multi-stage `docker/Dockerfile` builds two right-sized images, selected by `--target`:

| Image tag | Build target | Contents | Entrypoint |
|-----------|--------------|----------|------------|
| `knucklessg1/scholarx:mcp` | `--target mcp` | `scholarx[mcp]` — **slim**, no engine/`pydantic-ai`/`dspy`/`llama-index`/`tree-sitter` | `scholarx-mcp` |
| `knucklessg1/scholarx:latest` | `--target agent` (default) | `scholarx[agent]` — **full** agent runtime + epistemic-graph engine | `scholarx-agent` |

```bash
docker build --target mcp   -t knucklessg1/scholarx:mcp    docker/   # slim MCP server
docker build --target agent -t knucklessg1/scholarx:latest docker/   # full agent
```

`docker/mcp.compose.yml` runs the slim `:mcp` server; `docker/agent.compose.yml` runs the
agent (`:latest`) with a co-located `:mcp` sidecar.

### Knowledge-graph database (`epistemic-graph`)

The **full agent** (`[agent]` / `:latest`) embeds the **epistemic-graph** engine (pulled in
transitively via `agent-utilities[agent]`). For production — or to share one knowledge graph
across multiple agents — run **epistemic-graph as its own database container** and point the
agent at it instead of embedding it. Deployment recipes (single-node + Raft HA), connection
config, and the full database architecture (with diagrams) are documented in the
[epistemic-graph deployment guide](https://knuckles-team.github.io/epistemic-graph/deployment/).
The slim `[mcp]` server does **not** require the database.

---

## Documentation

The complete documentation is published as the
[official documentation site](https://knuckles-team.github.io/scholarx/) and is the
recommended reference for installation, deployment, and day-to-day operation.

| Page | Contents |
|---|---|
| [Installation](https://knuckles-team.github.io/scholarx/installation/) | pip, source, extras, prebuilt Docker image |
| [Deployment](https://knuckles-team.github.io/scholarx/deployment/) | run the MCP server and the agent, Compose, Caddy + Technitium, env config |
| [Usage](https://knuckles-team.github.io/scholarx/usage/) | the MCP tools, the `ScholarXClient` API, the CLI |
| [Overview](https://knuckles-team.github.io/scholarx/overview/) | ecosystem role, enterprise readiness, architecture |
| [Concepts](https://knuckles-team.github.io/scholarx/concepts/) | concept registry (`CONCEPT:SX-*`) |
| [Coverage Report](https://knuckles-team.github.io/scholarx/scholarx_coverage_report/) | per-source coverage and verification |

`AGENTS.md` is the canonical contributor/agent guidance.

---

## Repository Owners

<img width="100%" height="180em" src="https://github-readme-stats.vercel.app/api?username=Knucklessg1&show_icons=true&hide_border=true&&count_private=true&include_all_commits=true" />

![GitHub followers](https://img.shields.io/github/followers/Knucklessg1)
![GitHub User's stars](https://img.shields.io/github/stars/Knucklessg1)

---

## Contribute

Contributions are welcome! Please ensure code quality by executing local checks before submitting pull requests:
- Format code using `ruff format .`
- Lint code using `ruff check .`
- Validate type-safety with `mypy .`
- Execute test suites using `pytest`


<!-- BEGIN agent-os-genesis-deploy (generated; do not edit between markers) -->

## Deploy with `agent-os-genesis`

This package can be provisioned for you — skill-guided — by the **`agent-os-genesis`**
universal skill (its *single-package deploy mode*): it picks your install method, seeds
secrets to OpenBao/Vault (or `.env`), trusts your enterprise CA, registers the MCP
server, and verifies it — the same machinery that stands up the whole Agent OS, narrowed
to just this package. Ask your agent to **"deploy `scholarx` with agent-os-genesis"**.

| Install mode | Command |
|------|---------|
| Bare-metal, prod (PyPI) | `uvx scholarx-mcp` · or `uv tool install scholarx` |
| Bare-metal, dev (editable) | `uv pip install -e ".[all]"` · or `pip install -e ".[all]"` |
| Container, prod | deploy `knucklessg1/scholarx:latest` via docker-compose / swarm / podman / podman-compose / kubernetes |
| Container, dev (editable) | deploy `docker/compose.dev.yml` (source-mounted at `/src`; edits live on restart) |

Secrets are read-existing + seeded via `vault_sync` — you are only prompted for what's missing.

<!-- END agent-os-genesis-deploy -->
