# Repository Instructions for Coding Agents

## Purpose

This repository implements an evidence-grounded pipeline that extracts antenna architecture and reported results from one scientific paper at a time.

Final consumer-facing outputs:

- `antenna_architecture.json`
- `antenna_results.json`

Intermediate reports, manifests, raw responses, traces, validation reports, and failure records are audit artefacts.

## Sources of truth

Use this authority order:

1. Code and tests merged into `main` define implemented behaviour.
2. `00_ARCHITECTURE_V3.md` defines the intended architecture and fixed decisions.
3. `01_IMPLEMENTATION_ROADMAP_V3.md` defines phase scope and completion gates.
4. Scientific benchmark requirements define acceptance when added.
5. Chats, old plans, and the V2 repository are supporting context only.

If these sources disagree materially, report the divergence. Do not silently reconcile it or treat planned behaviour as implemented.

## Working model

The repository owner is the lead developer. User implementation is the default whenever the owner chooses to write the code directly. Do not assume that every agreed change should be implemented by the agent.

Before editing:

1. Inspect the current branch, HEAD, working tree, relevant code, tests, and artefacts.
2. Read the relevant V3 architecture and roadmap sections.
3. State the current behaviour and the smallest coherent implementation increment.
4. Identify affected files, tests, acceptance evidence, and material open decisions.

Work on one implementation increment at a time. Keep changes small, coherent, reviewable, and within the current roadmap phase.

Do not create placeholders, speculative abstractions, unused configuration, future adapters, or unrelated refactors.

## Architecture guardrails

Follow `00_ARCHITECTURE_V3.md` and the current phase of `01_IMPLEMENTATION_ROADMAP_V3.md`.

Unless those documents are deliberately revised, do not introduce parallel model execution, RAG or vector databases, automatic retries or fallback/reviewer models, unrestricted tool loops, general agent frameworks, unsupported engineering defaults, or later-phase work.

Deterministic code must remain mechanical. Missing, ambiguous, or unsupported scientific information must remain explicit rather than being converted into plausible facts.

## Implementation conventions

- Use Python 3.12 and `uv`.
- Keep importable code under `src/antenna_paper_extraction`.
- Use `pathlib` for filesystem paths.
- Use strict Pydantic models at stable validation boundaries.
- Keep timestamps timezone-aware. Current run manifests use `Europe/Lisbon`.
- Preserve established atomic persistence where durable artefacts require it.
- Keep code, identifiers, comments, commit-message proposals, and implementation prompts in English.
- Explain project concepts and implementation decisions to the repository owner in European Portuguese.

## Testing

Add or update tests with the behaviour they verify.

Use fake or scripted model clients in normal local tests. Default tests must never contact institutional model endpoints. Remote probes must be explicit and opt-in.

Run the relevant repository checks before handoff:

```bash
uv run pytest
uv run ruff check .
```

Run additional checks required by the current `pyproject.toml` or roadmap. Inspect representative generated artefacts when applicable.

## Git and GitHub ownership

The repository owner exclusively controls all Git and GitHub state-changing operations.

Agents may use read-only Git commands such as `git status`, `git diff`, `git log`, `git show`, and `git branch --show-current`.

Agents must not stage files, create or switch branches, commit, pull, push, merge, rebase, create or modify pull requests, tag releases, delete branches, rewrite history, or use destructive cleanup commands.

Preserve unrelated user changes. The normal agent handoff is a tested local working-tree diff for owner review.

## Completion

Before declaring an implementation increment complete:

1. Compare it with the applicable roadmap completion gate.
2. Inspect the final diff for unrelated or future-phase changes.
3. Run affected tests, the broader local suite, and lint checks as applicable.
4. Inspect generated artefacts when relevant.
5. Report files changed, checks performed, limitations, unresolved decisions, and deferred work.
6. Leave all Git and GitHub state-changing operations to the repository owner.
