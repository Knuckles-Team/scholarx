# Concept Registry — scholarx

> **Prefix**: `CONCEPT:SX-*`
> **Version**: 0.11.0
> **Bridge**: [`CONCEPT:AU-ECO.messaging.native-backend-abstraction`](https://knuckles-team.github.io/agent-connector-sdk/concepts/) (Unified Toolkit Ingestion)

---

## Project-Specific Concepts

| Concept ID | Name | Description |
|------------|------|-------------|
| `CONCEPT:SX-OS.governance.sx` | Resource Discovery | MCP tool domain `discovery` — Action-routed dynamic tool registration |
| `CONCEPT:SX-OS.governance.sx-2` | Search & Discovery | MCP tool domain `search` — Action-routed dynamic tool registration |
| `CONCEPT:SX-OS.governance.sx-3` | Storage & Persistence | MCP tool domain `storage` — Action-routed dynamic tool registration |

## Cross-Project References (from agent-connector-sdk)

| Concept ID | Name | Origin |
|------------|------|--------|
| `CONCEPT:AU-ECO.messaging.native-backend-abstraction` | Unified Toolkit Ingestion | agent-connector-sdk |
| `CONCEPT:AU-ORCH.adapter.hot-cache-invalidation` | Confidence-Gated Router | agent-connector-sdk |
| `CONCEPT:AU-OS.config.secrets-authentication` | Prompt Injection Defense | agent-connector-sdk |
| `CONCEPT:AU-OS.state.cognitive-scheduler-preemption` | Cognitive Scheduler | agent-connector-sdk |
| `CONCEPT:AU-OS.governance.reactive-multi-axis-budget` | Guardrail Engine | agent-connector-sdk |
| `CONCEPT:AU-OS.governance.wasm-micro-agent-sandbox` | Audit Logging | agent-connector-sdk |
| `CONCEPT:AU-KG.query.object-graph-mapper` | Knowledge Graph Core | agent-connector-sdk |

## Synergy with agent-connector-sdk

This project integrates with `agent-connector-sdk` via `CONCEPT:AU-ECO.messaging.native-backend-abstraction` (Unified Toolkit Ingestion). The `scholarx` MCP server registers its tools with the agent-connector-sdk FastMCP middleware, enabling automatic discovery, telemetry, and Knowledge Graph ingestion of all SX-* concepts.
