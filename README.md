# Antenna Paper Extraction

Antenna Paper Extraction is a Python project for extracting evidence-grounded
antenna architecture and reported results from one scientific paper at a time.
The final consumer-facing outputs will be:

- `antenna_architecture.json`
- `antenna_results.json`

The complete extraction pipeline is not implemented. Phase 1 and the Phase 2
NuExtract3 document-conversion implementation are available on the current
`feat/document-package` feature branch. Phase 2 has been merged into
`main`.

## Project status

The available workflow creates an isolated run, preserves and verifies the
source PDF, renders every page in source order, and converts those rendered
pages into one Markdown document.

Currently implemented:

- Python 3.12 project managed with `uv`
- Isolated run creation for one PDF at a time
- Source PDF preservation and SHA-256 verification
- Strict run, lifecycle, and pages manifests
- Ordered PNG page rendering at 170 DPI by default
- Sequential NuExtract3 conversion in batches of up to eight pages
- OpenAI-compatible response handling
- Per-batch raw responses and traces
- Structured phase status and failure records
- Timezone-aware lifecycle timestamps using `Europe/Lisbon`
- Atomic JSON and binary persistence
- Local tests and Ruff checks

Not yet implemented:

- Bounded visual asset inspection
- Architecture and results extraction agents
- Canonicalization and final JSON generation
- An end-to-end pipeline command

## Intended pipeline

The architecture defines this sequential flow:

1. Initialize a traceable run and render the PDF pages in source order.
2. Convert the ordered page sequence into Markdown with NuExtract3.
3. Produce independent architecture and results evidence reports.
4. Canonicalize the grounded claims into a shallow validated contract.
5. Split the validated response into the two final JSON documents.

Missing or ambiguous scientific information must remain explicit. The
pipeline must not replace it with plausible engineering defaults.

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

## Document-conversion configuration

The `convert-document` command reads endpoint configuration from the process
environment. For local development, it also loads `.env` from the current
working directory. Existing process environment values take precedence over
values in `.env`.

The following variables are required:

- `SKYNET_BASE_URL`: base URL of the OpenAI-compatible endpoint
- `SKYNET_API_KEY`: endpoint credential
- `DOCUMENT_EXTRACTOR_MODEL`: deployed NuExtract3 model identifier
- `DOCUMENT_EXTRACTOR_TIMEOUT_SECONDS`: positive request timeout in seconds

A local `.env` can contain the non-secret settings below. It must also define
`SKYNET_API_KEY` locally, or that variable must exist in the process
environment. Never commit the API key or include its value in documentation,
logs, or shared examples.

```dotenv
SKYNET_BASE_URL=https://your-endpoint.example/v1
DOCUMENT_EXTRACTOR_MODEL=your-deployed-model-id
DOCUMENT_EXTRACTOR_TIMEOUT_SECONDS=600
```

## Usage

Create a traceable run from a local PDF:

```bash
uv run antenna-extract init-run path/to/paper.pdf
```

Run artefacts are written under `runs/` by default. Use `--runs-root` to select
another parent directory:

```bash
uv run antenna-extract init-run path/to/paper.pdf --runs-root path/to/runs
```

Render every page of an existing run as PNG:

```bash
uv run antenna-extract render-pages runs/run_<id>
```

Page rendering uses 170 DPI by default. Override it with `--dpi` when needed:

```bash
uv run antenna-extract render-pages runs/run_<id> --dpi 300
```

Convert the rendered pages to Markdown:

```bash
uv run antenna-extract convert-document runs/run_<id>
```

The command requires successful page rendering. It validates the run, status,
and pages manifest identities before contacting the endpoint.

## Run artefacts

After successful document conversion, the run has this structure:

```text
run_<id>/
├── manifest.json
├── status.json
├── input/
│   └── <original-filename>.pdf
├── pages/
│   ├── pages.json
│   ├── page_0001.png
│   └── ...
└── document_conversion/
    ├── document.md
    ├── nuextract3_raw_response_batch_0001.json
    ├── nuextract3_trace_batch_0001.json
    └── ...
```

`manifest.json` records stable run and source-document identity. `status.json`
records phase state, timestamps, and inspectable failures. `pages/pages.json`
records rendering settings and the ordered page assets with dimensions, sizes,
and checksums.

The `document_conversion` directory contains the combined Markdown and the
diagnostic artefacts for each batch. Batch numbers are one-based and
zero-padded to four digits.

## Batching and failure behaviour

Document conversion processes the complete ordered page sequence. It applies
no relevance filter before conversion. Consecutive batches contain at most
eight pages and are sent sequentially. For `page_count` rendered pages, the
number of NuExtract3 calls is:

```text
B = ceil(page_count / 8)
```

Every page is processed exactly once and in source order. The implementation
reads Markdown from `choices[0].message.content` in the OpenAI-compatible
response. Successful batch Markdown is joined mechanically with two newline
characters between batches. The conversion adds no page ID markers.

For each response received, the raw response is written before its Markdown is
parsed. A trace is written only after parsing succeeds. The trace records the
requested model, request settings, HTTP status, `finish_reason`, usage when
available, and measured model latency. The final `document.md` is written only
after every batch succeeds. Conversion stops at the first failed batch and the
lifecycle status becomes `failed`. A transport failure can occur before any
raw response exists.

There are no retries, fallbacks, parallel batch calls, or configurable
`max_tokens`. Fixed-size batching replaced one request per document after
larger papers reached the endpoint context limit. Reducing the default
resolution from 200 DPI to 170 DPI reduced the input size but did not solve
every larger-paper failure. Sequential batches completed larger papers that
had previously ended with `finish_reason="length"`.

## Current limitations

- `document.md` has no reliable page markers. Page identity remains in
  `pages/pages.json`.
- Batch boundaries are mechanical and may need manual review.
- Separate figure files are not produced.
- Rendered full-page images are the available visual assets.
- Safe asset resolution and consumer-specific package validation are deferred
  until Phase 3 has a concrete consumer.
- Architecture extraction, results extraction, canonicalization, and final
  JSON generation are not implemented.

## Development checks

Run the complete local verification set:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Default tests use fake clients and do not contact the institutional endpoint.

## Repository guidance

The project sources of truth are, in order:

1. Code and tests merged into `main` for implemented behaviour
2. [`00_ARCHITECTURE_V3.md`](00_ARCHITECTURE_V3.md) for intended architecture
3. [`01_IMPLEMENTATION_ROADMAP_V3.md`](01_IMPLEMENTATION_ROADMAP_V3.md) for phase scope and completion gates
4. Scientific benchmark requirements for acceptance, once introduced

Development rules for coding agents are defined in [`AGENTS.md`](AGENTS.md).
