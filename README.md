# Antenna Paper Extraction

Evidence-grounded extraction of antenna architecture and reported results from
one scientific PDF per run. The eventual consumer outputs are
`antenna_architecture.json` and `antenna_results.json`; neither the current
workflow nor this architecture experiment generates them.

## Current behaviour and comparison baseline

The implemented extraction path remains the comparison baseline:

1. `init-run` preserves the source bytes under `input/` and records SHA-256
   document identity in an isolated run.
2. `render-pages` verifies the preserved PDF and renders every physical page in
   source order, with page metadata and checksums.
3. `convert-document` sends all rendered pages to the configured NuExtract3
   endpoint in sequential batches of up to eight pages, making
   `ceil(page_count / 8)` calls on success. It requests preservation of tables,
   equations and captions, then joins successful Markdown batches with two
   newlines in `document.md` without inserting page markers.
4. `extract-figures` uses Docling layout inference and Markdown figure labels
   to associate captions with regions, including conservative same-page caption
   recovery. PDFium renders crops from the preserved PDF. The figure manifest
   records provenance, timings and unresolved associations.
5. `extract-architecture` uses the Agents SDK with the complete Markdown and a
   minimal figure/page catalog. The agent may request exact assets through
   `get_visual_assets` once; the same model interprets the returned images.
   It persists an English Markdown evidence report and execution JSON.

Architecture execution requires successful figure extraction, a pending
`architecture_extraction` phase and no existing `architecture/` directory.
It uses one model call without asset retrieval, or two calls and one tool
execution with retrieval, including wholly unavailable asset requests. The
current limit is two model turns and six requested assets by default; six is a
configured limit, not measured endpoint capacity. Model and tool execution are
sequential, retries are disabled, additional asset requests
are rejected, and SDK tracing is disabled in favour of local execution records.

The scientific prompt focuses on the selected design, source provenance and
reconstruction-critical detail. Claims use identifiers and `Reported`, `Visual`
or `Derived` classifications with evidence; uncertainty, conflicts and missing
information remain explicit. Scientific instructions live in the extraction
prompt in `architecture_report.py`.

Report structure checks are diagnostic: a non-empty report can be published and
the phase marked `succeeded` despite structural errors. Operational success
establishes execution and persistence, not scientific acceptance. Results
extraction, canonicalization, final consumer JSON generation and general
pipeline orchestration remain unimplemented and outside this branch's scope.

## Approved MCP experiment - not yet implemented

The `exp/architecture-mcp` branch will compare iterative MCP evidence acquisition
with the existing extraction path. Its implementation tasks are in
[PLAN.md](PLAN.md).

- Reuse `init-run` to preserve one PDF and establish run identity, then launch
  an external MCP server through stdio, bound to that preserved PDF.
- Keep the server in its own repository and environment. Server-derived data
  belongs under `<run_dir>/mcp/`; its source tree is not copied here.
- Let the architecture agent acquire evidence iteratively through all six MCP
  tools using the Agents SDK. Use a finite, configurable turn budget, initially
  proposed as 80, with sequential model/tool execution and no automatic retries.
- Allow explicitly requested visual inspection inside the MCP. Persist tool
  and model traces incrementally and produce the existing architecture evidence
  report, retaining the baseline path for comparison.

The current external MCP interface has exactly six tools:
`get_paper_overview`, `read_pages`, `read_section`, `search_paper`, `list_assets`
and `get_asset`. `get_asset(asset_id, question=...)` requests visual inspection;
question-free asset access is distinct from an inspection request. `page:N`
addresses a physical PDF page. Original paper content and learned visual
observations must remain distinguishable through source and diagnostic references.

Binding configures and validates the document. Store creation or reuse occurs
when a tool opens the store; binding itself does not create SQLite. Planned
run-relative artefacts are:

| Planned MCP artefact | Purpose |
| --- | --- |
| `mcp/store/<sha256[:16]>/paper.sqlite` | Server document store |
| `mcp/images/...` | Server image assets |
| `mcp/inspections/...` | Visual inspection diagnostics |
| `architecture/architecture_evidence_report.md` | MCP-derived evidence report |
| `architecture/architecture_execution.json` | MCP execution and incremental trace |

The architecture filenames already exist in the baseline; producing them through
MCP is planned. There is currently no local MCP connection probe, execution path,
CLI command or MCP configuration surface. Server launch/model settings and the
turn-budget configuration will be documented when implemented. Tool calls,
principal-model requests and visual-model requests will be counted separately;
a `get_asset` call or supplied question does not prove a visual-model request
occurred, particularly for unavailable evidence or configuration failures.

## Setup and current configuration

Use Python 3.12 and `uv`:

```bash
uv sync
uv run antenna-extract --help
```

`convert-document` and `extract-architecture` load `.env` from the current
working directory; existing process environment values take precedence.

| Environment variable | Used by |
| --- | --- |
| `SKYNET_BASE_URL` | Both commands: OpenAI-compatible endpoint base URL |
| `SKYNET_API_KEY` | Both commands: endpoint credential |
| `DOCUMENT_EXTRACTOR_MODEL` | Conversion: deployed NuExtract3 identifier |
| `DOCUMENT_EXTRACTOR_TIMEOUT_SECONDS` | Conversion: positive timeout in seconds |
| `ARCHITECTURE_AGENT_MODEL` | Architecture: deployed model identifier |
| `ARCHITECTURE_AGENT_TIMEOUT_SECONDS` | Architecture: positive finite timeout in seconds |

Each command requires all its listed variables. Keep credentials local; do not
commit `.env`, PDFs or large run artefacts. `extract-figures` requires no
institutional endpoint configuration, but Docling performs local inference and
may download model weights on first use.

## Current usage

Run the baseline steps explicitly, replacing `runs/run_<id>` with the directory
printed by `init-run`. Quote paths containing spaces:

```bash
uv run antenna-extract init-run "path/to/paper.pdf"
uv run antenna-extract render-pages "runs/run_<id>"
uv run antenna-extract convert-document "runs/run_<id>"
uv run antenna-extract extract-figures "runs/run_<id>"
uv run antenna-extract extract-architecture "runs/run_<id>"
```

`init-run` accepts `--runs-root` (default `runs/`). Other available options and
current defaults are:

| Command option | Effective CLI default | Importable function default |
| --- | ---: | ---: |
| `render-pages --dpi` | 300 | 170 |
| `extract-figures --scale` | 4.0 | 3.0 |
| `extract-figures --margin-pt` | 2.0 | 2.0 |
| `extract-architecture --max-assets` | 6 | 6 |

`--scale` controls PDFium crop rendering, not Docling settings. The CLI help for
`--scale` still says 3.0, and default assertions in `tests/test_cli.py` still
expect 170 DPI and scale 3.0. These code/test discrepancies need a separate
implementation review. Use explicit `--dpi 170` and `--scale 3.0` when comparing
with runs made using those settings; these are not universally validated defaults.

Visual inspection is also importable through `run_visual_inspection` in
`visual_inspection.py`, using `InspectionChatCompletionsModel`. Its caller owns
the client and must disable retries; the result contains final text, requested
asset IDs and counts. Persistence belongs to the architecture caller.
`scripts/probe_multimodal.py` is a separate opt-in synthetic protocol probe using
`SKYNET_BASE_URL`, `SKYNET_API_KEY` and `ARCHITECTURE_AUTHOR_MODEL`; the latter is
not the architecture CLI setting. Owner-reported successful probes for
`gemma-4-26b-a4b` and `qwen3.8-27b` establish protocol compatibility only, not
scientific quality or production model selection.

## Audit artefacts and failures

A completed baseline run contains:

```text
run_<id>/
  manifest.json
  status.json
  input/<original-filename>.pdf
  pages/pages.json
  pages/page_0001.png ...
  document_conversion/document.md
  document_conversion/nuextract3_raw_response_batch_0001.json ...
  document_conversion/nuextract3_trace_batch_0001.json ...
  figures/manifest.json
  figures/figure_<number>.png ...
  architecture/architecture_evidence_report.md
  architecture/architecture_execution.json
```

The strict manifests record run/document identity, ordered page assets and phase
states (`pending`, `running`, `succeeded`, `failed`). Lifecycle timestamps use
`Europe/Lisbon`; durable JSON and binary writes use atomic replacement.

Conversion writes each received raw response before parsing, then a trace with
request settings, HTTP status, finish reason, usage when available and model
latency. It stops at the first failed batch; final Markdown is written only after
all batches parse successfully. Earlier diagnostics survive; transport failures
may produce no raw response.

Architecture execution atomically saves each event before continuing, including
received model responses before SDK interpretation, linked tool requests and
availability results without image payloads. Its JSON also records instructions,
configuration, counts, total duration, final text, structural diagnostics and
errors. Current model-request events record the occurrence, not complete request
bodies or per-event timing; richer MCP tracing is planned. Truncation or execution
failure preserves prior events without publishing a report. If finalization
fails, the report created by that execution is removed while diagnostics remain.
Existing conversion, figure and architecture outputs are protected against silent
replacement. No automatic retry or rerun/reset command is available.

## Material limitations

- Markdown has no reliable page markers, and batch boundaries need review;
  physical page identity remains in `pages/pages.json`.
- Figure-label uniqueness does not establish semantic caption equivalence or
  crop quality. Docling may merge neighbouring content or split compound
  figures. A figure ID can have no PNG; manifest availability does not guarantee
  readability. Historical manual evidence includes one owner-confirmed caption
  recovery, not universal layout validation.
- Baseline asset resolution validates IDs, count limits and path containment,
  including symlinks, but not image contents, additional visual-asset hashes or
  byte-payload limits. These extra checks are outside its accepted scope.
  There is no automatic page substitution; declared pages can be requested.
- Scientific completeness, endpoint payload capacity and end-to-end performance
  are not established by structural checks, protocol probes or preprocessing
  timings. The MCP pilot and six-case comparison remain pending.

## Development

[AGENTS.md](AGENTS.md) governs coding-agent work; [PLAN.md](PLAN.md) defines this
branch's implementation increments. Code and tests define implemented behaviour;
README describes the approved direction. Report discrepancies explicitly rather
than treating planned behaviour as available.

For implementation changes, the local verification commands are:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Normal tests use fake/scripted clients and mocked Docling conversion; they must
not contact model endpoints, perform inference or download weights. Live probes
and scientific reviews are explicit. Documentation-only changes require diff,
reference and executable-behaviour consistency checks, including `git diff --check`.
