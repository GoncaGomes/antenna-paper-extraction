# Antenna Paper Extraction

Antenna Paper Extraction is a Python project for extracting evidence-grounded
antenna architecture and reported results from one scientific paper at a time.
The final consumer-facing outputs will be:

- `antenna_architecture.json`
- `antenna_results.json`

The complete extraction pipeline is not implemented. Phases 1 and 2 are merged
into `main`. The 03B figure-extraction increment is implemented on
`feat/asset-inspection` and is being prepared for owner review and an
intermediate merge. Phase 3 remains in progress.

## Project status

Documentation updated: 2026-09-10.

The available workflow creates an isolated run, preserves and verifies the
source PDF, renders every page in source order, and converts those rendered
pages into one Markdown document. A separate post-conversion step detects
figure regions with Docling, attempts conservative caption recovery, and
renders figure PNGs from the preserved PDF.

Currently implemented:

- Python 3.12 project managed with `uv`
- Isolated run creation for one PDF at a time
- Source PDF preservation and SHA-256 verification
- Strict run, lifecycle, and pages manifests
- Ordered PNG page rendering at 170 DPI by default
- Sequential NuExtract3 conversion in batches of up to eight pages
- OpenAI-compatible response handling
- Per-batch raw responses and traces
- Post-conversion figure extraction with label-based caption association
- Conservative same-page geometric recovery of missing caption associations
- `figures/manifest.json` with provenance, timings, and unresolved entries
- `figure_extraction` lifecycle support
- Structured phase status and failure records
- Timezone-aware lifecycle timestamps using `Europe/Lisbon`
- Atomic JSON and binary persistence
- Local tests and Ruff checks

Not yet implemented:

- Minimal visual catalogue, page fallback integration, and safe asset resolver
- Bounded tool interaction and real multimodal protocol validation
- Architecture and results extraction agents
- Canonicalization and final JSON generation
- An end-to-end pipeline command

## Intended pipeline

The architecture defines this sequential flow:

1. Initialize a traceable run and render the PDF pages in source order.
2. Convert the ordered page sequence into Markdown with NuExtract3.
3. Extract figures using converted Markdown captions and the preserved PDF.
4. Build a minimal visual catalogue and expose safe figure/page inspection
   through one tool round per agent (planned). Prepared figure and page files
   already exist; this catalogue, page fallback integration, and tool do not.
5. Produce independent, sequential architecture and results reports (planned).
6. Canonicalize the grounded claims into a shallow validated contract (planned).
7. Split the validated response into the two final JSON documents (planned).

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

Extract figures after document conversion has succeeded:

```bash
uv run antenna-extract extract-figures runs/run_<id>
uv run antenna-extract extract-figures runs/run_<id> --scale 3.0 --margin-pt 2.0
```

Extraction reads `document_conversion/document.md` and the preserved PDF under
`input/`. It reads `<figcaption>` content and associates numeric figure labels
with Docling candidates. PDFium renders each required page once for cropping.
`--scale` controls PDFium rendering, not Docling settings. The defaults are
scale 3.0 and a 2-point margin bounded by the page, with limited manual evidence.

Docling performs local model inference and may download model weights on first
use. This command does not require institutional model endpoint configuration.
Docling image generation is disabled; PDFium produces the final PNGs.

## Run artefacts

After document conversion and figure extraction complete, the run contains:

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
├── document_conversion/
│   ├── document.md
│   ├── nuextract3_raw_response_batch_0001.json
│   ├── nuextract3_trace_batch_0001.json
│   └── ...
└── figures/
    ├── manifest.json
    └── figure_<number>.png
```

`manifest.json` records stable run and source-document identity. `status.json`
records phase state, timestamps, and inspectable failures. `pages/pages.json`
records rendering settings and the ordered page assets with dimensions, sizes,
and checksums.

The `document_conversion` directory contains the combined Markdown and the
diagnostic artefacts for each batch. Batch numbers are one-based and
zero-padded to four digits.

`figures/manifest.json` records source identity, settings, timings, caption
associations, original candidates, and unresolved reasons. PNGs are written
only for renderable associations. A figure ID or label does not guarantee a
materialized PNG; `relative_path` can be null.

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

Figure extraction requires successful document conversion, a `pending`
`figure_extraction` state, and no existing `figures/` output. These preflight
rejections leave lifecycle state unchanged. Exceptions after the phase starts
record a failure, preserving existing partial artefacts. There is no automatic
retry or implemented rerun/reset command.

A completed extraction may contain unresolved entries, even without any PNGs.
`succeeded` means the operation and manifest persistence completed, not that
every crop has passed visual review.

## Current limitations

- `document.md` has no reliable page markers. Page identity remains in
  `pages/pages.json`.
- Batch boundaries are mechanical and may need manual review.
- Label matching checks uniqueness, not semantic caption equivalence or crop
  quality. Manual visual review remains necessary.
- Docling can merge regions containing neighbouring figures, text, or tables,
  or split a compound figure into uncaptioned subfigures. The implementation
  does not automatically repair these layouts or reject all problematic crops.
- The owner confirmed one real recovery case; this is not universal layout
  validation. Detailed evidence and limitations are recorded in the roadmap.
- Figure and page files are available, but the minimal catalogue, page fallback
  integration, safe resolver, and bounded inspection tool are still planned.
- Architecture extraction, results extraction, canonicalization, and final
  JSON generation are not implemented.

## Development checks

Run the complete local verification set:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Normal tests mock Docling conversion and remote model clients. They must not
trigger model inference, endpoint calls, or model-weight downloads.

## Repository guidance

The project sources of truth are, in order:

1. Code and tests merged into `main` for implemented behaviour
2. [`00_ARCHITECTURE_V3.md`](00_ARCHITECTURE_V3.md) for intended architecture
3. [`01_IMPLEMENTATION_ROADMAP_V3.md`](01_IMPLEMENTATION_ROADMAP_V3.md) for phase scope and completion gates
4. Scientific benchmark requirements for acceptance, once introduced

Development rules for coding agents are defined in [`AGENTS.md`](AGENTS.md).
