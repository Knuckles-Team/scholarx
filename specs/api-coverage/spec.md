# CONN-SCHOLARX-API-COVERAGE — Direct tools cover uncovered API operations

Owner: scholarx. Cross-repo IDs: none.

## Purpose and user stories

The `scholarx-mcp` server exposes direct tools for client operations that are not
already covered by the action-routed surface. The canonical
`connector-standard` aggregate runs the API-parity check against the measured
repository baseline configured in `pyproject.toml`; the baseline is an explicit
gate threshold and does not claim that every client method is exposed.

## Requirements and acceptance

See [requirements.md](requirements.md).
