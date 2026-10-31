# CONN-SCHOLARX-CONNECTOR-CONTENT — Requirements

Governing spec: [spec.md](spec.md).

Each row is one requirement. A row names the file it touches and the test that proves it. The generator sets each row's state in `status.json`.

| ID | Requirement | Acceptance |
|---|---|---|
| `CONN-SCHOLARX-CONNECTOR-CONTENT-R001` | **Default content.** `pyproject.toml` declares `scholarx-mcp` as the single `scion_sdk.connector` entry point. The server lists the packaged `skill://` and `ontology://` resources and the packaged prompts with no `content=` argument. Proving test: `tests/test_default_content_surfaces.py`. | `resources/list` includes `skill://` and `ontology://`; `prompts/list` includes each packaged prompt. |
| `CONN-SCHOLARX-CONNECTOR-CONTENT-R002` | **Register the SDK paper tools and provider streams.** Subsystem: connector. Caller: process start → `scholarx/mcp_server.py` → `register_paper_search_tool`, `register_paper_download_tool`, `register_paper_provider_stream` with `ProviderBinding` values for each provider the connector supports. The connector owns provider API bindings, cursors and document offers. The connector also emits `PaperRecord` values with citation references for SCION-SOURCE-INGEST-R005.33. Refusals: reuse the closed reasons of SCION-SOURCE-INGEST-R005.4. Writes: none. Depends on: SCION-SOURCE-INGEST-R005.3. | Test: `tests/test_paper_tools_served.py::test_registered_tools_search_and_stream` (L3) calls the three tools through `tools/call` against controlled provider servers. |
