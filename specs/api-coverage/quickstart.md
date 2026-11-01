# CONN-SCHOLARX-API-COVERAGE — Quickstart

The shortest path that shows the served behaviour working.

```text
uv run pytest scholarx/kg_ingest.py tests/test_operation_tools.py tests/test_paper_ingest_admission.py tests/test_paper_maintenance_tool.py
```

The command starts the connector in process and calls the served tools through the MCP client. A test marked planned in `test-spec.md` runs once the code change that lands its row adds it.
