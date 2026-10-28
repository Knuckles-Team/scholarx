"""Real EG authority and catalog fixtures for the paper process test."""

from epistemic_graph.generated.connector_pack import AgentLibraryMutationContext, McpCatalogSnapshotBinding


def catalog():
    return McpCatalogSnapshotBinding(
        configuration_revision=7,
        catalog_generation=11,
        snapshot_digest="a" * 64,
        child_connection_generation=3,
        authorization_scope_digest="b" * 64,
    )


def mutation_context():
    return AgentLibraryMutationContext(
        request_id=1,
        principal="principal-a",
        caller_principal="caller-a",
        attempt_nonce="07" * 32,
        tenant_id="tenant-a",
        actor_scope="scope-a",
        purpose_id="purpose-a",
        policy_revision="policy-1",
        policy_digest="sha256:" + "c" * 64,
        policy_decision_id="decision-1",
        idempotency_key="caller-value",
        expected_revision=1,
        trace_id="trace-1",
        created_at_ms=1_700_000_000_000,
    )
