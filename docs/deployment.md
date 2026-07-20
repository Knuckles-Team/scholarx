# Deployment

<!-- BEGIN GENERATED: deployment-options -->
## Deployment Options

`scholarx` supports local stdio, a loopback-only development listener, a
least-privilege stdio container, and a remote authenticated HTTPS boundary.
Provider endpoint, credential, selector, identity, and trust material are supplied
at runtime through `AgentConfig`; none is stored in this repository.

### Installed stdio process

```json
{
  "mcpServers": {
    "scholarx": {
      "command": "scholarx-mcp",
      "args": [],
      "env": {"MCP_TOOL_MODE": "intent"}
    }
  }
}
```

### Loopback development listener

```bash
scholarx-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

Do not expose this listener beyond loopback. Network deployments require direct TLS
or an explicitly trusted TLS-terminating ingress, configured authentication, exact
`MCP_ALLOWED_HOSTS`, and an exact trusted-proxy CIDR policy.

### Least-privilege local container

```bash
docker run -i --rm \
  --read-only \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  --pids-limit=256 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m \
  -e TRANSPORT=stdio \
  registry.example.invalid/scholarx@sha256:<digest> scholarx-mcp
```

The operator projects the selected AgentConfig profile into the process at runtime;
the image remains immutable and contains no environment connection profile.

### Remote authenticated HTTPS endpoint

```json
{
  "mcpServers": {
    "scholarx": {"url": "https://service.example.invalid/mcp"}
  }
}
```

Store the real remote URL, outbound identity reference, and TLS-profile reference in
`AgentConfig`, not in MCP client JSON or documentation.
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
    image: example/scholarx@sha256:<digest>
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
    image: example/scholarx@sha256:<digest>
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
# Internal (self-signed) — homelab .example.invalid zone
scholarx.example.invalid {
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
curl -s "http://technitium.example.invalid:5380/api/zones/records/add" \
  --data-urlencode "token=$TECHNITIUM_DNS_TOKEN" \
  --data-urlencode "domain=scholarx.example.invalid" \
  --data-urlencode "zone=arpa" \
  --data-urlencode "type=A" \
  --data-urlencode "ipAddress=192.0.2.10" \
  --data-urlencode "ttl=3600"
```

…or add an **A record** `scholarx.example.invalid → <caddy-host-ip>` in the Technitium web
console (`http://technitium.example.invalid:5380`). The ecosystem
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

For a remote HTTP server, point the client at `http://scholarx.example.invalid/mcp` instead.
