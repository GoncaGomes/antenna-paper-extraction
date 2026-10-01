# Repository Instructions for Coding Agents

These instructions govern software development in this repository. The owner
is the lead developer and may choose to implement an agreed change directly.

## Scope and inspection

- Before editing, inspect the actual branch, HEAD, working tree, relevant code,
  tests and artefacts. Read the applicable parts of [README.md](README.md) and
  [PLAN.md](PLAN.md).
- Code and tests define implemented behaviour. Follow the approved design in
  README and implement one current PLAN task at a time. Report unresolved
  discrepancies rather than silently reconciling them or presenting plans as
  implemented features.
- State current behaviour, the smallest coherent increment, affected files,
  verification evidence and material open decisions before editing.
- Keep changes small and reviewable. Preserve unrelated user work and stay
  within the agreed scope. Do not create placeholders, unused abstractions,
  speculative configuration or unrelated refactors.
- Keep the external MCP server in its own repository/environment. Do not copy
  its source tree here or change it as part of local integration work. Leave
  read-only synced files under `sources/` untouched, if present.

## Implementation conventions

- Use Python 3.12 and `uv`; keep importable code under
  `src/antenna_paper_extraction`.
- Use `pathlib` and strict Pydantic models at stable validation boundaries.
- Preserve established atomic persistence for durable artefacts and
  timezone-aware timestamps; current runs use `Europe/Lisbon`.
- Explain work and decisions to the owner in European Portuguese. Write code,
  identifiers, comments, documentation, implementation prompts and suggested
  commit messages in English.

## Verification and handoff

Add or update tests for changed behaviour. Normal local tests use fake/scripted
model clients and mocked Docling conversion; they must not contact institutional
endpoints, perform inference or download weights. Live inference is explicit
and opt-in.

For implementation changes, run affected tests and the broader local suite,
plus lint and formatting checks as appropriate:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

For documentation-only changes, review consistency with executable behaviour,
check references and run `git diff --check`; do not add documentation-only tests
or run inference. Inspect representative generated artefacts when relevant.

Before handoff, compare the result with the current PLAN task's acceptance
checks and review the final diff for unrelated work. Report changed files,
checks and results, limitations, unresolved decisions and deferred work. Leave
a local working-tree diff for owner review.

## Git and GitHub ownership

The owner exclusively controls all Git/GitHub state-changing operations. Agents
may use read-only commands such as `git status`, `git diff`, `git log`,
`git show` and `git branch --show-current`.

Do not stage files, create or switch branches, commit, pull, push, merge, rebase,
create or modify pull requests, tag releases, delete branches, rewrite history
or use destructive cleanup commands.
