---
name: scholarx-development
skill_type: skill
domain: development
description: >-
  Develop, test, gate, and release the scholarx connector. Use this skill
  when changing paper provider mappings, MCP tools, storage, packaging,
  documentation, or repository gates.
license: MIT
tags: [scholarx, development, connector, test, gates]
tier: repository
metadata:
  author: Genius
  version: '0.1.0'
---

# scholarx development

This repository owns the ScholarX paper-provider clients, deduplication and
storage behavior, MCP tools, packaged connector content, and agent entry
points. Shared connector contracts and transports belong to
`agent-connector-sdk`; admission, serving, and durable graph state belong to
their owning repositories. Read `AGENTS.md` before changing code and keep
provider credentials, paper paths, and endpoints out of source, logs, and
skill content.

## Rapid delivery: the 5-minute contract

Specs are already designed. Deliver small, reviewable slices and cite the
owning spec row in the commit trailer.

- Find the owning row first with `git grep -n "<term>" -- specs` and extend
  that spec before adding new requirement text.
- Reuse the existing `ScholarXClient`, provider rate limits, deduplication,
  storage, and SDK tool surface. Do not create a second implementation of a
  connector capability.
- Keep changes scoped to this connector. A change owned by the SDK, Arbora, or
  the knowledge graph belongs in that repository instead.
- Every delivered requirement needs a bound test. Generated `status.json`
  files are produced by `pipelines-hook spec-status`; never hand-edit them.
- Mock external paper-provider calls and keep download tests within the
  existing queue and timeout seams; never use live credentials in a local gate.
- One logical change per commit, with `Spec: <ID>` and the assisting agent
  trailer adjacent in the final paragraph.

## Setup and gates

Use the pinned environment from `uv sync --locked`. Run the repository gate:

```bash
uvx pre-commit run --all-files
```

For focused feedback, run the smallest affected test file with the locked
environment, for example:

```bash
uv run --all-extras pytest tests/test_operation_tools.py -q
uv run --all-extras pytest tests/test_action_discovery.py -q
```

The canonical `.pre-commit-config.yaml` delegates connector-standard, secrets,
spec, tests-fast, and dependency-readiness checks to `Knuckles-Team/pipelines`
at `rev: main`. Do not replace those shared hooks with local copies or bypass a
failing check.

## Connector-specific checks

- Keep provider fan-out, rate limiting, deduplication, storage, and MCP tool
  surfaces aligned with the SDK.
- Use mocked arXiv, PMC, bioRxiv, OSF, and Semantic Scholar responses in tests;
  never call live providers from a local gate.
- Keep `scholarx/skills/`, ontology, prompts, and connector manifests in
  package data when adding content.
- Documentation lives under `docs/` and is published by the shared Pages
  workflow; source status records live under `specs/`.

## Delivery discipline

Work in a real Git worktree based on `origin/main`. Inspect the complete diff,
stage only reviewed paths, and verify `git status --short` after every gate.
Do not use `git stash`, `git add -A`, or `git add .`; do not claim Pages
publication until a successful exact-source workflow run and the public page
are both observed.
