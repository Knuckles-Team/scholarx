# CONN-SCHOLARX-CONNECTOR-CONTENT — Test specification

Governing spec: [spec.md](spec.md).

| Test ID | Requirement | Proving test | Expected observation |
|---|---|---|---|
| T-001 | `CONN-SCHOLARX-CONNECTOR-CONTENT-R002` | `tests/test_citing_papers.py::test_sx_search_citations_returns_documented_fields` (planned) | Test: the action returns the documented fields. |
| T-002 | `CONN-SCHOLARX-CONNECTOR-CONTENT-R001` | `tests/test_default_content_surfaces.py::test_default_content_surfaces` | `resources/list` includes `skill://` and `ontology://`; `prompts/list` includes each packaged prompt. |
| T-003 | `CONN-SCHOLARX-CONNECTOR-CONTENT-R003` | `tests/test_paper_tools_served.py::test_registered_tools_search_and_stream` (planned) | Test: `tests/test_paper_tools_served.py::test_registered_tools_search_and_stream` (L3) calls the three tools through `tools/call` against controlled provider servers. |

## Negative and boundary cases

Each proving test above includes the refusal or error case that its row names. A vendor outage or an unauthorised call must return the SDK typed error.

## Quality and release proof

Run `uv run pytest tests` and `pre-commit run --all-files` from the repository root. A planned test is added by the code change that lands the row.
