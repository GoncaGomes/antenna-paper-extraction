# Antenna Paper Extraction

Antenna Paper Extraction is a research-oriented Python project for extracting evidence-grounded antenna architecture and reported results from scientific papers.

The project is being developed as a small, sequential pipeline. Its final consumer-facing outputs will be:

- `antenna_architecture.json`
- `antenna_results.json`

The complete extraction pipeline is not implemented yet. The current code provides the Phase 1 run lifecycle: it creates an isolated run, preserves and verifies the source PDF, records structured phase status, and renders ordered page assets with traceable metadata.

## Project status

The repository currently implements Phase 1, Run Lifecycle and Source Preservation. This phase provides traceable run creation, source PDF verification, ordered page rendering, and inspectable lifecycle status.

Currently implemented:

- Python 3.12 project managed with `uv`
- Isolated run creation for one PDF at a time
- Source PDF preservation and SHA-256 verification
- Run manifests validated with Pydantic
- Structured lifecycle status and failure records
- Ordered PDF page rendering with page metadata and checksums
- Portugal-local lifecycle timestamps
- Atomic JSON and binary persistence
- An `antenna-extract init-run` command
- An `antenna-extract render-pages` command
- Local tests and Ruff checks

Not yet implemented:

- NuExtract3 document conversion
- Visual asset inspection
- Architecture and results agents
- Canonicalization and final JSON generation

## Intended pipeline

The architecture defines the following sequential flow:

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

Verify that the command-line interface is available:

```bash
uv run antenna-extract --help
```

## Usage

Create a traceable run from a local PDF:

```bash
uv run antenna-extract init-run path/to/paper.pdf
```

By default, run artefacts are written under `runs/`. The command prints the path of the newly created run.

Render every page of an existing run:

```bash
uv run antenna-extract render-pages runs/run_<id>
```

Page rendering uses 200 DPI by default. A different resolution can be selected explicitly:

```bash
uv run antenna-extract render-pages runs/run_<id> --dpi 300
```

After successful rendering, the run contains:

```text
run_<id>/
├── input/
│   └── <original-filename>.pdf
├── pages/
│   ├── page_0001.png
│   └── ...
├── manifest.json
├── pages.json
└── status.json
```

`manifest.json` records the stable run and document identity. `pages.json` describes the ordered rendered assets. `status.json` records lifecycle timestamps and inspectable phase failures.

The commands currently stop after page rendering. They do not yet perform document conversion or call a model.

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
