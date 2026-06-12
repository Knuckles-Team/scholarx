# Deployment

<!-- BEGIN GENERATED: deployment-options -->
## Deployment Options

`scholarx` exposes its MCP server (console script `scholarx-mcp`) four ways. Pick the row that
matches where the server runs relative to your MCP client, then copy the matching
`mcp_config.json` below. Replace the `<your-…>` placeholders with the values from the **Configuration / Environment Variables** section.

| # | Option | Transport | Where it runs | `mcp_config.json` key |
|---|--------|-----------|---------------|------------------------|
| 1 | stdio | `stdio` | client launches a subprocess | `command` |
| 2 | Streamable-HTTP (local) | `streamable-http` | a local network port | `command` or `url` |
| 3 | Local container / uv | `stdio` or `streamable-http` | Docker / Podman / uv on this host | `command` or `url` |
| 4 | Remote URL | `streamable-http` | a remote host behind Caddy | `url` |

### 1. stdio (local subprocess)

The client launches the server over stdio via `uvx` — best for local IDEs
(Cursor, Claude Desktop, VS Code):

```json
{
  "mcpServers": {
    "scholarx-mcp": {
      "command": "uvx",
      "args": ["--from", "scholarx", "scholarx-mcp"],
      "env": {
        "SERVICENOW_USERNAME": "<your-servicenow_username>"
      }
    }
  }
}
```

### 2. Streamable-HTTP (local process)

Run the server as a long-lived HTTP process:

```bash
uvx --from scholarx scholarx-mcp --transport streamable-http --host 0.0.0.0 --port 8000
curl -s http://localhost:8000/health        # {"status":"OK"}
```

Then either let the client launch it:

```json
{
  "mcpServers": {
    "scholarx-mcp": {
      "command": "uvx",
      "args": ["--from", "scholarx", "scholarx-mcp", "--transport", "streamable-http", "--port", "8000"],
      "env": {
        "TRANSPORT": "streamable-http",
        "HOST": "0.0.0.0",
        "PORT": "8000",
        "SERVICENOW_USERNAME": "<your-servicenow_username>"
      }
    }
  }
}
```

…or connect to the already-running process by URL:

```json
{
  "mcpServers": {
    "scholarx-mcp": { "url": "http://localhost:8000/mcp" }
  }
}
```

### 3. Local container / uv

**(a) Launch a container directly from `mcp_config.json`** (stdio over the container —
no ports to manage). Swap `docker` for `podman` for a daemonless runtime:

```json
{
  "mcpServers": {
    "scholarx-mcp": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "TRANSPORT=stdio",
        "-e", "SERVICENOW_USERNAME=<your-servicenow_username>",
        "knucklessg1/scholarx:latest"
      ]
    }
  }
}
```

**(b) Run a local streamable-http container, then connect by URL:**

```bash
docker run -d --name scholarx-mcp -p 8000:8000 \
  -e TRANSPORT=streamable-http \
  -e PORT=8000 \
  -e SERVICENOW_USERNAME="<your-servicenow_username>" \
  knucklessg1/scholarx:latest
# or, from a clone of this repo:
docker compose -f docker/mcp.compose.yml up -d
```

```json
{
  "mcpServers": {
    "scholarx-mcp": { "url": "http://localhost:8000/mcp" }
  }
}
```

**(c) From a local checkout with `uv`:**

```bash
uv run scholarx-mcp --transport streamable-http --port 8000
```

### 4. Remote URL (deployed behind Caddy)

When the server is deployed remotely (e.g. as a Docker service) and published through
Caddy on the internal `*.arpa` zone, connect with the `"url"` key — no local process or
image required:

```json
{
  "mcpServers": {
    "scholarx-mcp": { "url": "http://scholarx-mcp.arpa/mcp" }
  }
}
```

Caddy reverse-proxies `http://scholarx-mcp.arpa` to the container's `:8000`
streamable-http listener; `http://scholarx-mcp.arpa/health` returns
`{"status":"OK"}` when the service is live.
<!-- END GENERATED: deployment-options -->

This page covers running `scholarx` as a long-lived service: the transports, a Docker
Compose stack, the optional graph agent, putting it behind a Caddy reverse proxy, and
giving it a DNS name with Technitium.

> `scholarx` ships both an **MCP server** (console script `scholarx-mcp`) and a
> **Pydantic-AI graph agent** (console script `scholarx-agent`). The MCP server is the
> typed, deterministic tool surface a policy router / agent calls; the agent server is
> an autonomous orchestrator that connects to the MCP server over HTTP.

## Run the MCP server

The transport is selected with `--transport` (or the `TRANSPORT` env var):

=== "stdio (default)"

    ```bash
    scholarx-mcp
    ```
    For IDE / desktop MCP clients that launch the server as a subprocess.

=== "streamable-http"

    ```bash
    scholarx-mcp --transport streamable-http --host 0.0.0.0 --port 8004
    ```
    A network server with a `/health` endpoint and `/mcp` route.

=== "sse"

    ```bash
    scholarx-mcp --transport sse --host 0.0.0.0 --port 8004
    ```

Health check (HTTP transports):

```bash
curl -s http://localhost:8004/health        # {"status":"OK"}
```

## Configuration (environment)

`scholarx` is configured entirely from the environment. The **required** runtime set
(transport / server binding and tool toggles) is small; every paper-source API
credential is optional and only raises rate limits or unlocks an authenticated source.

| Var | Default | Meaning |
|---|---|---|
| `HOST` | `0.0.0.0` | Bind address for HTTP transports |
| `PORT` | `8004` | Port for HTTP transports |
| `TRANSPORT` | `stdio` | MCP transport (`stdio`, `streamable-http`, `sse`) |
| `AUTH_TYPE` | `none` | Access-control mode (`none`, `basic`, `custom`) |
| `SCHOLARX_STORAGE_DIR` | `~/.scholarx/papers` | Directory for downloaded PDFs |
| `SEARCHTOOL` | `True` | Register the `search` tool module |
| `DISCOVERYTOOL` | `True` | Register the `discovery` tool module |
| `STORAGETOOL` | `True` | Register the `storage` tool module |
| `OSF_TOKEN` | _(unset)_ | OSF / PsyArXiv API token (required for those sources) |
| `S2_API_KEY` | _(unset)_ | Semantic Scholar key — raises rate limits |
| `NCBI_API_KEY` | _(unset)_ | PubMed Central key — raises rate limits |

Each paper source remains usable with no credentials, and the authenticated sources
remain inactive when credentials are absent. The full set, with telemetry and Eunomia
governance options, is documented in
[`.env.example`](https://github.com/Knuckles-Team/scholarx/blob/main/.env.example).
Copy it to `.env` and populate only what you use.

## Docker Compose

The repo ships [`docker/mcp.compose.yml`](https://github.com/Knuckles-Team/scholarx/blob/main/docker/mcp.compose.yml).
It reads a sibling `.env` and publishes the HTTP server on `:8004`:

```yaml
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
```

```bash
cp .env.example .env          # then edit the values you need
docker compose -f docker/mcp.compose.yml up -d
docker compose -f docker/mcp.compose.yml logs -f
```

## Run the agent server

`scholarx` also publishes a Pydantic-AI graph agent as the `scholarx-agent` console
script. The agent connects to a running MCP server over HTTP (`MCP_URL`) and exposes
the Agent Control Protocol plus the Agent Web UI on its own port (`9600` by default).

```bash
# Start the MCP server first (streamable-http), then the agent against it
export MCP_URL=http://localhost:8004/mcp
scholarx-agent --provider openai --model-id gpt-4o
```

The repo ships [`docker/agent.compose.yml`](https://github.com/Knuckles-Team/scholarx/blob/main/docker/agent.compose.yml),
which deploys the MCP server and the agent together and wires `MCP_URL` between them:

```yaml
services:
  scholarx-mcp:
    image: knucklessg1/scholarx:latest
    container_name: scholarx-mcp
    hostname: scholarx-mcp
    restart: always
    env_file:
      - ../.env
    environment:
      - HOST=0.0.0.0
      - PORT=8004
      - TRANSPORT=streamable-http
    ports:
      - "8004:8004"

  scholarx-agent:
    image: knucklessg1/scholarx:latest
    container_name: scholarx-agent
    hostname: scholarx-agent
    restart: always
    depends_on:
      - scholarx-mcp
    env_file:
      - ../.env
    command: ["scholarx-agent"]
    environment:
      - HOST=0.0.0.0
      - PORT=9600
      - MCP_URL=http://scholarx-mcp:8004/mcp
      - PROVIDER=${PROVIDER:-openai}
      - MODEL_ID=${MODEL_ID:-gpt-4o}
      - ENABLE_WEB_UI=True
    ports:
      - "9600:9600"
```

```bash
docker compose -f docker/agent.compose.yml up -d
```

## Behind a Caddy reverse proxy

Expose the HTTP server on a hostname with automatic TLS. Add to your `Caddyfile`:

```caddy
# Internal (self-signed) — homelab .arpa zone
scholarx.arpa {
    tls internal
    reverse_proxy scholarx-mcp:8004
}
```

```caddy
# Public — automatic Let's Encrypt
scholarx.example.com {
    reverse_proxy scholarx-mcp:8004
}
```

To publish the agent's Web UI as well, add a second site block pointing at
`scholarx-agent:9600`. Reload Caddy:

```bash
docker compose -f services/caddy/compose.yml exec caddy caddy reload --config /etc/caddy/Caddyfile
```

## DNS with Technitium

Point the hostname at the host running Caddy. Via the Technitium API:

```bash
curl -s "http://technitium.arpa:5380/api/zones/records/add" \
  --data-urlencode "token=$TECHNITIUM_DNS_TOKEN" \
  --data-urlencode "domain=scholarx.arpa" \
  --data-urlencode "zone=arpa" \
  --data-urlencode "type=A" \
  --data-urlencode "ipAddress=10.0.0.10" \
  --data-urlencode "ttl=3600"
```

…or add an **A record** `scholarx.arpa → <caddy-host-ip>` in the Technitium web
console (`http://technitium.arpa:5380`). The ecosystem
[`technitium-dns-mcp`](https://knuckles-team.github.io/technitium-dns-mcp/) automates
this as a tool.

## Register with an MCP client

Add to your client's `mcp_config.json` (multiplexer nickname `sx`):

```json
{
  "mcpServers": {
    "scholarx": {
      "command": "uv",
      "args": ["run", "scholarx-mcp"],
      "env": {
        "SEARCHTOOL": "True",
        "DISCOVERYTOOL": "True",
        "STORAGETOOL": "True"
      }
    }
  }
}
```

For a remote HTTP server, point the client at `http://scholarx.arpa/mcp` instead.
