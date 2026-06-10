# AGENTS.md

> Claude Code loads this file via `CLAUDE.md` (`@AGENTS.md` import) — the two stay
> in sync. Edit **this** file, not `CLAUDE.md`.

<!-- CONCEPT:SX-1.0 CLI — Rich terminal interface with progress bars, scan/status commands -->
<!-- CONCEPT:SX-1.1 Relevance Scoring — Delegated to research-scanner skill with dynamic_scorer.py -->
<!-- CONCEPT:SX-1.2 3-Tier Deduplication — DOI exact match → cross-ID mapping → fuzzy title+author (Levenshtein ≥ 0.90) -->
<!-- CONCEPT:SX-1.3 Storage Dedup — PaperStorage skips already-downloaded PDFs via metadata hash lookup -->
<!-- CONCEPT:SX-1.4 Auto-Analysis — --analyze flag chains comparative-analysis innovation extraction on relevant papers -->
<!-- CONCEPT:SX-1.5 Category OR-Join — arXiv query builder uses OR-joined categories so a paper in ANY listed category matches -->
<!-- CONCEPT:SX-1.6 Background Download Queue — Non-blocking paper downloads via queue.py with job tracking -->

## Tech Stack & Architecture
- Language/Version: Python 3.11+
- Core Libraries: `agent-utilities`, `fastmcp`, `pydantic`, `httpx`, `rich`
- Key principles: Per-source rate limiting, 3-tier deduplication, full paper storage, existing KG node types.
- Architecture:
    - `cli.py`: Rich CLI with progress bars for scan/status commands (CONCEPT:SX-1.0).
    - `mcp_server.py`: MCP server entry point with tools across 3 tag groups (search, discovery, storage).
    - `queue.py`: Background download queue with job tracking and status reporting.
    - `agent_server.py`: Graph agent server for autonomous operation.
    - `api_client.py`: Unified client — fan-out to all providers, dedup, merge.
    - `providers/`: One module per paper source (arXiv, PMC, bioRxiv, OSF, S2).
    - `kg_integration.py`: Bridges papers into existing KG via KBIngestionEngine.

### Architecture Diagram
```mermaid
graph TD
    User([User/Agent]) --> MCP[ScholarX MCP Server]
    MCP --> Client[ScholarXClient]
    Client --> ArXiv[arXiv API]
    Client --> PMC[PubMed Central]
    Client --> BioRxiv[bioRxiv/medRxiv]
    Client --> OSF[OSF/PsyArXiv]
    Client --> S2[Semantic Scholar]
    Client --> Dedup[Deduplication Engine]
    Client --> Storage[Paper Storage]
    Storage --> KG[Knowledge Graph via KBIngestionEngine]
```

### Workflow Diagram
```mermaid
sequenceDiagram
    participant U as User
    participant M as MCP Server
    participant C as ScholarXClient
    participant P as Providers
    participant D as Deduplicator
    participant S as PaperStorage

    U->>M: search_papers("multi-agent systems")
    M->>C: search(SearchQuery)
    par Fan-out to all sources
        C->>P: arXiv.search()
        C->>P: PMC.search()
        C->>P: S2.search()
    end
    P-->>C: Raw results
    C->>D: deduplicate_papers()
    D-->>C: Merged, deduped results
    C-->>M: SearchResult
    M-->>U: Papers with metadata
    U->>M: download_paper(paper_id)
    M->>S: download_paper(paper)
    S-->>M: Local PDF path
```

## Commands (run these exactly)
```bash
# Installation
pip install .[all]

# Quality & Linting (run from project root)
SKIP=no-commit-to-branch,uv-lock pre-commit run --all-files

# CLI Commands (CONCEPT:SX-1.0)
scholarx scan --query "multi-agent systems" --output-dir ./papers
scholarx scan --categories cs.AI,cs.LG --max-results 50 --output-dir ./papers
scholarx scan --analyze --output-dir ./papers  # Auto-trigger comparative analysis
scholarx status                                 # Show stored paper library

# Entry Points
# scholarx       → scholarx.cli:cli
# scholarx-mcp   → scholarx.mcp_server:mcp_server
# scholarx-agent → scholarx.agent_server:agent_server

# Testing
pytest tests/ -v
```

## Project Structure Quick Reference
- MCP Entry Point → `mcp_server.py`
- Agent Entry Point → `agent_server.py`
- Unified Client → `api_client.py`
- Provider Layer → `providers/`
- Background Queue → `queue.py`
- Deduplication → `deduplication.py`
- Paper Storage → `paper_storage.py`
- KG Bridge → `kg_integration.py`
- Models → `models.py`
- Docker → `docker/`

### File Tree
```text
scholarx/
├── __init__.py              # Lazy imports (servicenow-api pattern)
├── __main__.py              # CLI entry point → cli.py
├── cli.py                    # Rich CLI: scan, status, --analyze (CONCEPT:SX-1.0)
├── models.py                # Paper, PaperSource, SearchQuery, SearchResult
├── api_client.py            # ScholarXClient — unified entry point + queue management
├── queue.py                  # Background download queue with job tracking (CONCEPT:SX-1.6)
├── deduplication.py          # 3-tier dedup: DOI → cross-ID → fuzzy title+author (CONCEPT:SX-1.2)
├── paper_storage.py          # Full PDF download + local storage with dedup (CONCEPT:SX-1.3)
├── kg_integration.py         # ScholarXKGBridge → KBIngestionEngine
├── mcp_server.py             # MCP tools (search, discovery, storage) + 2 analysis prompts
├── agent_server.py           # Graph agent server
├── main_agent.json           # Agent identity
├── mcp_config.json           # MCP client config
└── providers/
    ├── base.py               # Abstract PaperProvider + rate limiter
    ├── arxiv.py              # arXiv Atom API (CONCEPT:SX-1.5 OR-joined categories)
    ├── pmc.py                # NCBI E-utilities
    ├── biorxiv.py            # bioRxiv + medRxiv API
    ├── osf.py                # OSF + PsyArXiv API
    └── semantic_scholar.py   # S2 Academic Graph API
```

## Code Style & Conventions
**Always:**
- Use `agent-utilities` for common patterns (e.g., `create_mcp_server`, `create_graph_agent_server`).
- Define models using Pydantic with descriptive docstrings.
- Use per-source rate limiting via the `PaperProvider` base class.
- Lazy-import agent-utilities KG types inside functions (they're optional deps).

**Good example:**
```python
from scholarx.api_client import ScholarXClient
from scholarx.models import SearchQuery

client = ScholarXClient()
result = await client.search(SearchQuery(query="attention mechanisms"))
for paper in result.papers:
    print(f"{paper.title} ({paper.source})")
```

## Dos and Don'ts
**Do:**
- Run `pre-commit` before pushing changes.
- Use existing KG node types (ArticleNode, SourceNode, PersonNode).
- Add new sources by subclassing `PaperProvider`.
- Use `SearchQuery` for all search operations.

**Don't:**
- Call provider APIs directly — always go through `ScholarXClient`.
- Hardcode API keys — use environment variables (`OSF_TOKEN`, `S2_API_KEY`, `NCBI_API_KEY`).
- Create new KG node types — use existing patterns.
- Skip rate limiting — all providers must use `_wait_for_rate_limit()`.

## Safety & Boundaries
**Always do:**
- Run lint/test via `pre-commit`.
- Use the `PaperProvider` base class for new sources.

**Ask first:**
- Adding new paper sources.
- Changing deduplication thresholds.
- Modifying the KG bridge node mapping.

**Never do:**
- Commit `.env` files or API keys.
- Bypass per-source rate limiting.
- Modify `agent-utilities` models from within this package.


## Testing with Timeout

To run tests with a timeout to prevent hanging, use the `pytest-timeout` plugin. You can combine it with the `-k` flag to run specific tests:

```bash
uv run pytest --timeout=60 -k "test_name_pattern"
```

## ⛔ No Scratch or Temporary Files in Repository

**NEVER write any of the following to this repository:**
- Temporary test scripts (`test_*.py`, `debug_*.py` outside of `tests/`)
- Scratch scripts or experimental one-off files
- Log files (`.log`, `.txt` command output)
- Random text files with command output or debug dumps
- Any file that is NOT production source code, tests in `tests/`, or documentation

**Why:** These files expose private filesystem paths, credentials, and internal infrastructure details when pushed to GitHub publicly.

**Where to put scratch work instead:**
- Use `~/workspace/scratch/` for temporary scripts and experiments
- Use `~/workspace/reports/` for command output and reports
- Keep test scripts in the `tests/` directory following proper pytest conventions

## ⛔ Keep the Repository Root Pristine — No Scratch / Temp / Debug Files

**The repository ROOT must contain only canonical project files** (packaging,
config, docs, lockfiles). The only hidden directories allowed at root are
`.git/`, `.github/`, and `.specify/` (plus a local, git-ignored `.venv/`).

**NEVER write any of the following — anywhere in the repo, and ESPECIALLY at the root:**
- One-off / debug / migration scripts: `fix_*.py`, `migrate_*.py`, `refactor_*.py`,
  `replace_*.py`, `update_*.py`, `debug_*.py`, or `test_*.py` **at the root**
  (real tests live in `tests/` only).
- Databases / data dumps: `*.db`, `*.db-wal`, `*.sqlite*`, `*.corrupted`.
- Logs / command output: `*.log`, scratch `*.txt`, `*.orig`, `*.rej`, `*.bak`.
- Build artifacts: `*.tsbuildinfo`, compiled binaries, coverage files.
- AI agent scratch directories: `.agent/`, `.agents/`, `.agent_data/`, `.tmp/`,
  `.hypothesis/`, or any per-tool cache committed to git.
- Any file that is NOT production source, a test in `tests/`, documentation, or
  a recognized config/lockfile.

**Why:** scratch at the root leaks private paths/credentials, bloats the tree,
and erodes a pristine codebase.

**Where scratch goes instead:** `~/workspace/scratch/` (experiments),
`~/workspace/reports/` (command output); tests go in `tests/` (pytest).
Before finishing a task, run `git status` and confirm no stray root files were added.

## Working Discipline — think, simplify, stay surgical, verify

These four habits cut the most common LLM coding mistakes. For trivial tasks, use
judgment; the bias here is correctness over speed.

- **Think before coding.** State your assumptions explicitly. If a request has more than
  one reasonable reading, surface the options instead of silently picking one. If a
  simpler approach exists, say so and push back when warranted. When something is
  genuinely unclear, stop and name what's confusing — ask, don't guess.
- **Simplicity first.** Write the minimum code that solves the stated problem — no
  speculative features, no abstraction for single-use code, no configurability that
  wasn't requested, no error handling for impossible states. If you wrote 200 lines and
  it could be 50, rewrite it. (Name code from its purpose, never `wave0`/`phase2`/`v2`.)
- **Stay surgical.** Every changed line should trace directly to the task. Don't refactor,
  reformat, or "improve" working code adjacent to your change; match the existing style
  even where you'd do it differently. Remove only the imports/symbols your own change
  orphaned; if you spot unrelated dead code, mention it rather than deleting it inline.
  *Exception — the Quality Bar below:* lint/format/type errors the pre-commit gate flags
  get fixed regardless of who introduced them. In short: **surgical on behavior, clean on
  lint.**
- **Verify against a goal.** Turn the task into a checkable outcome before you start:
  "fix the bug" → "write a failing test that reproduces it, then make it pass"; "add
  validation" → "tests for the invalid inputs pass". For multi-step work, state the short
  plan and the check for each step, then loop until the checks pass.

## Quality Bar — Leave the Codebase Clean (REQUIRED)

After completing any code change, run the project's pre-commit suite and drive it
**fully green** before committing:

```bash
pre-commit run --all-files
```

Resolve **every** issue it reports — failures, lint errors, type errors, and
warnings — **including problems that pre-date your change and were not caused by
your edits**. The standing goal is a clean, working codebase with **no errors and
no warnings**. Do not silence checks (`# noqa`, `# type: ignore`, `SKIP=`,
`--no-verify`) to force green unless the exception is already documented in this
file as a known, unavoidable limitation. Only commit once `pre-commit run
--all-files` passes cleanly; if a check legitimately cannot pass, stop and explain
why rather than bypassing it.

## Working with Git Worktrees (multi-session)

Multiple agents/sessions work the `agent-packages/*` repos concurrently. **Do not
edit the canonical checkout** (`/home/apps/workspace/agent-packages/<repo>`) — a
background `repository-manager` sync can reset its working tree and discard
uncommitted edits. Take your own git worktree on your own branch instead:

```bash
# preferred — repository-manager MCP:
rm_worktree add <repo> <your-branch>      # -> /home/apps/worktrees/<repo>/<your-branch>

# raw-git fallback:
git -C agent-packages/<repo> checkout main
git -C agent-packages/<repo> worktree add /home/apps/worktrees/<repo>/<branch> -b <branch>
```

Work in the worktree and **commit often** (commits survive a working-tree reset).
Each session must use a **distinct branch** — git allows a branch in only one
worktree, which is what keeps concurrent sessions from colliding. Worktrees live
under `/home/apps/worktrees/` (outside the workspace scan, so the sync leaves them
alone).

**Finishing work in a worktree** — run this sequence before calling it done:
1. **Pre-commit green** — `pre-commit run --all-files`; resolve every issue per the
   Quality Bar above (including pre-existing), no `--no-verify`.
2. **Commit** in the worktree.
3. **Merge to main locally** — `rm_worktree merge <repo> <branch> --into main`
   (or `git merge --no-ff`). Push only when the user asks.
4. **Clean up** — remove the worktree and delete the merged branch:
   `rm_worktree remove <repo> <branch> --delete-branch`; `rm_worktree prune` clears
   stale entries. (Raw-git: `git worktree remove <path> && git branch -d <branch>`.)
