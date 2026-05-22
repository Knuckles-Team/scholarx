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

*Version: 0.9.0*

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

Detailed instructions on how to use the underlying API wrappers, extended schema bindings, and developer SDK references are maintained in [docs/index.md](file:///home/apps/workspace/agent-packages/agents/scholarx/docs/index.md).

---

## MCP

This server utilizes dynamic Action-Routed tools to optimize token overhead and maximize IDE compatibility.

### Available MCP Tools
| Tool Module | Toggle Env Var | Enabled by Default | Description & Nested Methods |
|-------------|----------------|--------------------|------------------------------|
| **Search** | `SEARCHTOOL` | `True` | Register search-related tools. Action-routed methods: `get`, `author`, `recent`. |
| **Discovery** | `DISCOVERYTOOL` | `True` | Register discovery-related tools. Action-routed methods: `categories`. |
| **Storage** | `STORAGETOOL` | `True` | Register paper storage tools. Action-routed methods: `stored`, `status`, `queue`, `download`, `download_url`, `bulk_download`. |

Detailed tool schemas, parameter shapes, and validation constraints are preserved in [docs/mcp.md](file:///home/apps/workspace/agent-packages/agents/scholarx/docs/mcp.md).

### MCP Configuration Examples

#### stdio Transport (Recommended for local IDEs e.g., Cursor, Claude Desktop)
Configure your IDE's `mcp.json` to launch the MCP server via `uvx`:

```json
{
  "mcpServers": {
    "scholarx": {
      "command": "uvx",
      "args": [
        "--from",
        "scholarx",
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
        "scholarx",
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
  knucklessg1/scholarx:latest
```

---

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

Detailed graph node architecture explanations, custom skill configurations, and agentic trace guides are available in [docs/agent.md](file:///home/apps/workspace/agent-packages/agents/scholarx/docs/agent.md).

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

## Installation

Install the Python package locally:

```bash
# Using uv (highly recommended)
uv pip install scholarx[all]

# Using standard pip
python -m pip install scholarx[all]
```

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
