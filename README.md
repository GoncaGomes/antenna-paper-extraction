# Antenna Paper Extraction

Antenna Paper Extraction is a research-oriented Python project for extracting evidence-grounded antenna architecture and reported results from scientific papers.

The project is being developed as a small, sequential pipeline. Its final consumer-facing outputs will be:

- `antenna_architecture.json`
- `antenna_results.json`

The complete extraction pipeline is not implemented yet. The current code provides the initial run lifecycle: it creates an isolated run, preserves the source PDF, computes its SHA-256 identity, and writes a traceable manifest.

## Project status

Development is currently in Phase 1, Run Lifecycle and Source Preservation. The roadmap status metadata still says that implementation has not started and must be aligned with the merged code before the Phase 1 completion gate is assessed.

Available on `main`:

- Python 3.12 project managed with `uv`
- Isolated run creation for one PDF at a time
- Source PDF preservation and SHA-256 hashing
- Run manifests validated with Pydantic
- Portugal-local creation timestamps
- Atomic JSON persistence
- An `antenna-extract init-run` command
- Local tests and Ruff checks

Not yet implemented:

- Ordered PDF page rendering
- Structured phase status and failure records
- NuExtract3 document conversion
- Visual asset inspection
- Architecture and results agents
- Canonicalization and final JSON generation

## Intended pipeline

The accepted V3 architecture defines the following sequential flow:

1. Initialize a traceable run and render the PDF pages in source order.
2. Convert the complete paper into a loss-preserving `DocumentPackage` with NuExtract3.
3. Produce independent architecture and results evidence reports.
4. Canonicalize the grounded claims into a shallow validated contract.
5. Split the validated response into the two final JSON documents.

Model execution remains sequential. Missing or ambiguous scientific information must stay explicit and must never be replaced with plausible engineering defaults.

## Setup

Requirements:

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/)

Create the environment and install the project dependencies:

```bash
uv sync
```

## Usage

Create a traceable run from a local PDF:

```bash
uv run antenna-extract init-run path/to/paper.pdf
```

By default, run artefacts are written under `runs/`. This directory is excluded from version control.

The command currently initializes the run only. It does not yet render pages or call a model.

## Development checks

Run the test suite:

```bash
uv run pytest
```

Run lint checks:

```bash
uv run ruff check .
```

## Repository guidance

The project sources of truth are, in order:

1. Code and tests merged into `main` for implemented behaviour
2. [`00_ARCHITECTURE_V3.md`](00_ARCHITECTURE_V3.md) for intended architecture
3. [`01_IMPLEMENTATION_ROADMAP_V3.md`](01_IMPLEMENTATION_ROADMAP_V3.md) for phase scope and completion gates
4. Scientific benchmark requirements for acceptance, once introduced

Development rules for coding agents are defined in [`AGENTS.md`](AGENTS.md).

The previous V2 repository remains available as [historical context and a regression baseline](https://github.com/GoncaGomes/antenna_extraction/tree/feat/antenna-pipeline-v2). Its architecture and code are not normative for this repository.

## Scope

The initial baseline processes one scientific paper per run. It does not include CST integration, simulation, optimization, semantic RAG, automatic retries, fallback models, parallel execution, or a general-purpose agent framework.
