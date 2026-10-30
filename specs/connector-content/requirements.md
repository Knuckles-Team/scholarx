# CONN-SCHOLARX-CONNECTOR-CONTENT — Requirements

Governing spec: [spec.md](spec.md).

Each row is one requirement. A row names the file it touches and the test that proves it. The generator sets each row's state in `status.json`.

| ID | Requirement | Acceptance |
|---|---|---|
| `CONN-SCHOLARX-CONNECTOR-CONTENT-R001` | **Default content.** `pyproject.toml` declares `scholarx-mcp` as the single `agent_connector_sdk.connector` entry point. The server lists the packaged `skill://` and `ontology://` resources and the packaged prompts with no `content=` argument. Proving test: `tests/test_default_content_surfaces.py`. | `resources/list` includes `skill://` and `ontology://`; `prompts/list` includes each packaged prompt. |
| `CONN-SCHOLARX-CONNECTOR-CONTENT-R002` | **Citing-papers operation: sx_search action citations.** Add sx_search action citations returning papers that cite a given id. Medulla abstains on the scholarx competency question naming this operation until it lands. | Test: the action returns the documented fields. |
