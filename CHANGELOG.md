# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Background Download Queue** — `queue_download()`, `get_download_status()`, and `get_queue_status()` methods on `ScholarXClient` for non-blocking paper downloads. New module: `queue.py`.
- **MCP Download Management** — `download_status` and `list_downloads` MCP tools for monitoring queued background downloads.
- **Docker Reorganization** — Moved `Dockerfile`, `compose.yml`, and `debug.Dockerfile` into `docker/` subdirectory. Added `mcp.compose.yml` for MCP-specific container orchestration.
- **Pre-commit Configuration** — Added `.pre-commit-config.yaml` for automated code quality checks.

### Changed
- **`bulk_download_papers`** — Refactored from synchronous to queue-based background downloading. Returns `job_id` references instead of blocking until completion.
- **MCP Server Cleanup** — Removed `scanner` tool group (`scan_daily`, `score_papers`) and `DEFAULT_SCANNERTOOL` environment variable. Relevance scoring is now handled by the `research-scanner` universal skill.
- **`api_client.py`** — Expanded with queue management methods and updated `download_paper` docstring for clarity.

### Removed
- **`scanner.py`** — Deleted the monolithic `RelevanceScanner` module. Functionality replaced by the agentic `research-scanner` skill workflow using `dynamic_scorer.py`.
- **`SCANNERTOOL` toggle** — Removed the `SCANNERTOOL` environment variable and `register_scanner_tools` from MCP server initialization.

### Fixed
- **`paper_storage.py`** — Minor fix to storage path handling.

## [1.8.0] - 2026-04-30

### Added
- Initial release with 7-source paper search, 3-tier deduplication, and KG integration.
