---
name: scholarx-operations
skill_type: skill
description: >-
  Operate scholarx through its governed MCP and Arbora capabilities, including scholarx kg ingestion, scholarx paper library, scholarx paper search. Use when a request requires this provider's read, change, automation, ingestion, troubleshooting, or evidence workflows.
---

# Scholarx Operations

Use the provider's governed MCP tools through Arbora delegation.

## Workflow

1. Establish the verified GraphSession and tenant before discovery or retrieval.
2. Discover the current condensed tool surface; never assume a stale tool name or schema.
3. Prefer read-only inspection first. For changes, present impact and use the provider's
   dry-run or preview mode when available.
4. Execute mutations as fenced WorkItems so retries remain idempotent and auditable.
5. Ingest source data only through the signed connector preset and ChangeEnvelope path.
6. Verify the durable result and its trace/evidence before reporting completion.

## Steps

1. Confirm the available sources by calling `sx_info_sources`. Verify the response lists the sources the request needs.
2. Discover before acting by reading `references/catalog.md` and calling `sx_enabled_sources`. Verify every tool name you plan to use is present.
3. Run a read-only lookup by calling `sx_search_search` with `query` and `max_results`. Verify the papers returned match the request.
4. Persist results only after approval by calling `scholarx_ingest_papers` as a fenced WorkItem. Verify `ingested` is not `null` and the WorkItem id is recorded.

## Failure recovery

| Failure | Cause | Recovery |
|---------|-------|----------|
| Tool name or schema rejected | A stale tool name was assumed | Re-read `references/catalog.md` and `sx_enabled_sources`, and call the current name |
| `ingested` is `null` | No engine reachable | Restore the engine connection and run `scholarx_ingest_papers` again as a new WorkItem |
| Session or tenant missing | GraphSession not established | Stop, establish a verified GraphSession for the tenant, and restart from step 1 |

## Safety contract

- Never persist credentials, endpoints, raw personal identifiers, hostnames, or local paths.
- Resolve TLS trust and verification from environment/configuration; never hardcode bypasses.
- Treat unknown ACL, tenant, schema, or tool-contract state as a hard failure.
- Require explicit approval for destructive, externally visible, or irreversible actions.
- Keep runtime traces policy-scoped and privacy-sanitized.

## Specialized workflows

Read [the workflow catalog](references/catalog.md) only when the request needs a
provider-specific procedure, parameter map, script, or reference asset.
