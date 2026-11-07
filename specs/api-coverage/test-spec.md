# CONN-SCHOLARX-API-COVERAGE — Test specification

Governing spec: [spec.md](spec.md).

| Test ID | Requirement | Proving test | Expected observation |
|---|---|---|---|
| T-001 | `CONN-SCHOLARX-API-COVERAGE-R001` | `tests/test_operation_tools.py::test_tools_are_registered_with_hints` | The three tools are listed with the right annotations, return the client results, and the canonical connector-standard API-parity check passes at the repository's measured baseline. |
| T-002 | `CONN-SCHOLARX-API-COVERAGE-R002` | `tests/test_paper_maintenance_tool.py::test_tool_binds_the_scholarx_stream` (planned) | Test: `tests/test_paper_maintenance_tool.py::test_tool_binds_the_scholarx_stream` (L3). A served test applies an order against the scholarx stream and reads the receipt. |
| T-003 | `CONN-SCHOLARX-API-COVERAGE-R003` | `scholarx/kg_ingest.py::ingest_entities` | Test: `tests/test_paper_ingest_admission.py::test_ingest_job_uses_staging_and_admission` (L3). A served test asserts that no claim exists for the excluded paper. |

## Negative and boundary cases

Each proving test above includes the refusal or error case that its row names. A vendor outage or an unauthorised call must return the SDK typed error.

## Quality and release proof

Run `uv run pytest tests` and `pre-commit run --all-files` from the repository root. A planned test is added by the code change that lands the row.

## Adoption of scion-sdk 0.10.0 (`CONN-SCHOLARX-API-COVERAGE-R004`)

| Requirement | Test | Observation |
|---|---|---|
| `CONN-SCHOLARX-API-COVERAGE-R004` | `tests/test_scion_sdk_0_10_imports.py::test_every_scion_sdk_import_resolves_on_the_pinned_release` | Every `scion_sdk` import resolves on the pinned release; a removed path fails the test. |
