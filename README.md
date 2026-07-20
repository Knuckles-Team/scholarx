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

*Version: 1.0.1*

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

#### Condensed action-routed tools (default — `MCP_TOOL_MODE=condensed`)

| MCP Tool | Toggle Env Var | Description |
|----------|----------------|-------------|
| `sx_info` | `DISCOVERYTOOL` | Get metadata about sources and categories. |
| `sx_search` | `SEARCHTOOL` | Search for research papers across all configured sources. |
| `sx_storage` | `STORAGETOOL` | Manage offline PDF storage and background downloads. |

#### Verbose 1:1 API-mapped tools (`MCP_TOOL_MODE=verbose` or `both`)

<details>
<summary>11 per-operation tools — one per public API method (click to expand)</summary>

| MCP Tool | Toggle Env Var | Description |
|----------|----------------|-------------|
| `scholarx_download_paper` | `SCHOLAR_X_CLIENTTOOL` | Download a paper's full PDF synchronously. |
| `scholarx_download_papers` | `SCHOLAR_X_CLIENTTOOL` | Download many papers in parallel with bounded concurrency. |
| `scholarx_download_urls` | `SCHOLAR_X_CLIENTTOOL` | Download arXiv PDFs directly by id/URL with bounded concurrency. |
| `scholarx_get_download_status` | `SCHOLAR_X_CLIENTTOOL` | Get the status of a queued download job. |
| `scholarx_get_paper` | `SCHOLAR_X_CLIENTTOOL` | Retrieve a single paper from a specific source. |
| `scholarx_get_queue_status` | `SCHOLAR_X_CLIENTTOOL` | Get the status of all queued downloads. |
| `scholarx_get_recent_papers` | `SCHOLAR_X_CLIENTTOOL` | Retrieve recently published papers. |
| `scholarx_get_source_status` | `SCHOLAR_X_CLIENTTOOL` | Get the status of all configured sources. |
| `scholarx_list_categories` | `SCHOLAR_X_CLIENTTOOL` | List available categories for each source. |
| `scholarx_queue_download` | `SCHOLAR_X_CLIENTTOOL` | Queue a paper for background downloading. |
| `scholarx_search` | `SCHOLAR_X_CLIENTTOOL` | Search across all configured sources with deduplication. |

</details>

_3 action-routed tool(s) (default) · 11 verbose 1:1 tool(s). Each is enabled unless its `<DOMAIN>TOOL` toggle is set false; `MCP_TOOL_MODE` selects the surface (`condensed` default · `verbose` 1:1 · `both`). Auto-generated — do not edit._
<!-- MCP-TOOLS-TABLE:END -->

Detailed tool schemas, parameter shapes, and validation constraints are preserved in [docs/usage.md](docs/usage.md).

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

<!-- MCP-CONFIG-EXAMPLES:START -->

> **Install the connector-focused `[mcp]` extra.** Examples use `scholarx[mcp]` to add
> FastMCP / FastAPI through `agent-utilities[mcp]`; the required Agent Utilities core
> still carries `epistemic-graph[full]`. The `[agent-runtime]` extra additionally
> enables model orchestration.

#### stdio Transport (local IDEs — Cursor, Claude Desktop, VS Code)

```json
{
  "mcpServers": {
    "scholarx-mcp": {
      "command": "uvx",
      "args": [
        "--from",
        "scholarx[mcp]",
        "scholarx-mcp"
      ],
      "env": {
        "MCP_TOOL_MODE": "intent",
        "DISCOVERYTOOL": "True",
        "NCBI_API_KEY": "your_ncbi_api_key_here",
        "OSF_TOKEN": "your_osf_token_here",
        "S2_API_KEY": "your_s2_api_key_here",
        "SEARCHTOOL": "True",
        "STORAGETOOL": "True"
      }
    }
  }
}
```

Runtime references require an alias-aware launcher such as GraphOS. Other
launchers must omit those entries and inject the resolved values through their
own runtime secret boundary.

#### Streamable-HTTP Transport (networked / production)

```json
{
  "mcpServers": {
    "scholarx-mcp": {
      "command": "uvx",
      "args": [
        "--from",
        "scholarx[mcp]",
        "scholarx-mcp",
        "--transport",
        "streamable-http",
        "--port",
        "8000"
      ],
      "env": {
        "TRANSPORT": "streamable-http",
        "HOST": "127.0.0.1",
        "PORT": "8000",
        "MCP_TOOL_MODE": "intent",
        "DISCOVERYTOOL": "True",
        "NCBI_API_KEY": "your_ncbi_api_key_here",
        "OSF_TOKEN": "your_osf_token_here",
        "S2_API_KEY": "your_s2_api_key_here",
        "SEARCHTOOL": "True",
        "STORAGETOOL": "True"
      }
    }
  }
}
```

Alternatively, connect to a pre-deployed Streamable-HTTP instance by `url`:

```json
{
  "mcpServers": {
    "scholarx-mcp": {
      "url": "http://localhost:8000/scholarx-mcp/mcp"
    }
  }
}
```

Run a reviewed container image as a least-privilege stdio child (no
listener or published port):

```bash
docker run -i --rm \
  --read-only \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  --pids-limit=256 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m \
  -e TRANSPORT=stdio \
  -e MCP_TOOL_MODE=intent \
  -e DISCOVERYTOOL=True \
  -e NCBI_API_KEY=your_ncbi_api_key_here \
  -e OSF_TOKEN=your_osf_token_here \
  -e S2_API_KEY=your_s2_api_key_here \
  -e SEARCHTOOL=True \
  -e STORAGETOOL=True \
  registry.example.invalid/scholarx@sha256:<digest> scholarx-mcp
```

For containerized network HTTP, supply an authenticated TLS ingress (or
direct server TLS), exact `MCP_ALLOWED_HOSTS`, and an exact trusted-proxy
CIDR policy through the operator-owned deployment profile. The generator
does not emit an unauthenticated non-loopback listener.

_Auto-generated from the code-read env surface (`MCP_TOOL_MODE` + package vars) — do not edit._
<!-- MCP-CONFIG-EXAMPLES:END -->

<!-- BEGIN GENERATED: additional-deployment-options -->
### Additional Deployment Options

`scholarx` can run as a local stdio process or container, or behind a remote
network boundary. The
[Deployment guide](https://knuckles-team.github.io/scholarx/deployment/) carries
the detailed transport contract.

- **Local container** — launch a reviewed immutable image as a least-privilege
  stdio child with no listener or published port.
- **Remote URL** — connect through an operator-supplied authenticated HTTPS
  ingress. Keep its URL, outbound identity references, trust profile, and exact
  `MCP_ALLOWED_HOSTS` in `AgentConfig`.
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
    image: example/scholarx@sha256:<digest>
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
    image: example/scholarx@sha256:<digest>
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

Detailed graph node architecture explanations, custom skill configurations, and agentic trace guides are available in [docs/deployment.md](docs/deployment.md).

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
| `DEBUG` | `False` |  |
| `PYTHONUNBUFFERED` | `1` |  |
| `OSF_TOKEN` | `your_osf_token_here` | OSF / PsyArXiv |
| `S2_API_KEY` | `your_s2_api_key_here` | Semantic Scholar |
| `NCBI_API_KEY` | `your_ncbi_api_key_here` | PubMed Central (NCBI E-utilities) |
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

_21 package + 12 inherited variable(s). Auto-generated from `.env.example` + the shared agent-utilities set — do not edit._
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
| `scholarx[mcp]` | Connector-focused MCP server (`agent-utilities[mcp]` — FastMCP/FastAPI + `epistemic-graph[full]`) | You only run the **MCP server** (smallest install / image) |
| `scholarx[agent]` | Agent runtime (`agent-utilities[agent-runtime,logfire]` — model orchestration + `epistemic-graph[full]`) | You run the **integrated agent** |
| `scholarx[all]` | Everything (`mcp` + `agent`) | Development / both surfaces |

```bash
# Connector-focused MCP server (includes the shared graph engine)
uv pip install "scholarx[mcp]"

# Agent runtime (adds model orchestration to the shared graph engine)
uv pip install "scholarx[agent]"

# Everything (development)
uv pip install "scholarx[all]"      # or: python -m pip install "scholarx[all]"
```

### Container images (`:mcp` vs `:agent`)

One multi-stage `docker/Dockerfile` builds two right-sized images, selected by `--target`:

| Image tag | Build target | Contents | Entrypoint |
|-----------|--------------|----------|------------|
| `example/scholarx:mcp` | `--target mcp` | `scholarx[mcp]` — **connector-focused**, includes `epistemic-graph[full]`; no model-orchestration stack | `scholarx-mcp` |
| `example/scholarx@sha256:<digest>` | `--target agent` (default) | `scholarx[agent]` — **agent runtime**, model orchestration + `epistemic-graph[full]` | `scholarx-agent` |

```bash
docker build --target mcp   -t example/scholarx:mcp    docker/   # connector-focused MCP server
docker build --target agent -t example/scholarx:agent-local docker/   # agent runtime
```

`docker/mcp.compose.yml` runs the connector-focused `:mcp` server; `docker/agent.compose.yml` runs the
agent (`immutable agent digest`) with a co-located `:mcp` sidecar.

### Knowledge-graph database (`epistemic-graph`)

Both `[mcp]` and `[agent]` carry the **epistemic-graph** engine through the required
Agent Utilities core dependency (`epistemic-graph[full]`). The `[mcp]` extra keeps
the server connector-focused; `[agent]` additionally enables model orchestration. Local
deployments can use the bundled engine. For production or shared state, run
**epistemic-graph as a dedicated database service** and configure the runtime to use it.
Deployment recipes (single-node + Raft HA), connection configuration, and architecture
diagrams are documented in the
[epistemic-graph deployment guide](https://knuckles-team.github.io/epistemic-graph/deployment/).

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

<img width="100%" height="180em" src="https://github-readme-stats.vercel.app/api?username=example&show_icons=true&hide_border=true&&count_private=true&include_all_commits=true" />

![GitHub followers](https://img.shields.io/github/followers/example)
![GitHub User's stars](https://img.shields.io/github/stars/example)

---

## Contribute

Contributions are welcome! Please ensure code quality by executing local checks before submitting pull requests:
- Format code using `ruff format .`
- Lint code using `ruff check .`
- Validate type-safety with `mypy .`
- Execute test suites using `pytest`


<!-- BEGIN agent-utilities-deployment (generated; do not edit between markers) -->

## Deploy with `agent-utilities-deployment`

Provision this package with the consolidated **`agent-utilities-deployment`**
workflow. It selects an installed-package, editable-source, or immutable-container
path; records only runtime secret and TLS-profile references in `AgentConfig`; and
runs doctor, registration, policy, observability, and rollback gates. Ask your agent
to **"deploy `scholarx` with agent-utilities-deployment"**.

| Install mode | Command |
|------|---------|
| Installed package | `uv tool install "scholarx[mcp]"`, then run `scholarx-mcp` |
| Editable source | `uv pip install -e ".[agent]"`, then run `scholarx-mcp` |
| Immutable container | deploy `registry.example.invalid/scholarx@sha256:<digest>` through the operator-selected orchestrator |

The repository embeds no deployment profile, credential value, certificate path, or
environment-specific endpoint. Supply those at runtime through `AgentConfig` and the
configured secret provider.

<!-- END agent-utilities-deployment -->

<!-- GOVERNED-CAPABILITY:START -->
## Governed capability contract

This package ships a compact canonical skill surface with specialist procedures
kept as referenced workflows. The current MCP tools, skill metadata,
`connector_manifest.yml`, ontology, mappings, shapes, fixtures, migrations,
tool-schema fingerprints, and certification metadata form one versioned
capability contract. Validate them together; do not rely on stale tool names or
historical per-task skill wrappers.

Runtime endpoints, credentials, certificate trust, tenant identity, retention,
and observability policy are deployment inputs and are never packaged values.
See [Configuration, trust, and privacy](docs/configuration.md) before enabling a
network transport, connector ingestion, GraphOS delegation, or trace export.
<!-- GOVERNED-CAPABILITY:END -->
