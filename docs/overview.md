# Technical overview

This document describes the implementation in `exp/architecture-mcp`. The
[README](../README.md) contains the project summary and MCP setup. This branch
retains the baseline workflow and adds progressive evidence acquisition through
the external `mcp-pdf-ingestion` server. Neither path generates the planned final
architecture or results JSON, and no complete pipeline command is implemented.

## Execution prerequisites

Use the [README quick start](../README.md#setup-and-usage) to select
`exp/architecture-mcp` and install the client with `uv sync`. Python 3.12 is the
client target in `.python-version`; `pyproject.toml` declares a minimum of 3.12.
Git and `uv` are required, along with access to dependency downloads.

Install the external [mcp-pdf-ingestion repository](https://github.com/GoncaGomes/mcp-pdf-ingestion)
in a separate checkout and virtual environment. The inspected server reference
is `145808d6cf3f308c5b3b46d767d036a253df9a4e`:

```bash
git clone https://github.com/GoncaGomes/mcp-pdf-ingestion.git
cd mcp-pdf-ingestion
git switch --detach 145808d6cf3f308c5b3b46d767d036a253df9a4e
```

Follow that revision's [installation instructions](https://github.com/GoncaGomes/mcp-pdf-ingestion/blob/145808d6cf3f308c5b3b46d767d036a253df9a4e/README.md#installation-and-launch)
to create its environment and install the package, which requires Python 3.12
or later. This reference exposes the six tools expected by the client and its
visual system prompt matches both saved inspections in the
[published example](examples/trace-summary.md#provenance). These checks establish
interface and prompt correspondence; the run does not confirm the exact server
revision, and live compatibility has not been retested for this documentation.

Return to the client repository before configuring [.env.example](../.env.example)
and running the quick start. Set `MCP_PDF_SERVER_CWD` to the absolute server
checkout directory and `MCP_PDF_SERVER_EXECUTABLE` to its installed console
executable: `.venv/bin/mcp-pdf-ingestion` on POSIX or
`.venv/Scripts/mcp-pdf-ingestion.exe` on Windows. Quote paths containing spaces.
Use the executable file itself, not `uv run`, a shell command or the server's
Python interpreter. There is no separate manual server-start step: the client
launches and cleans up a stdio process bound to the run's preserved PDF.

Supply your provider's `SKYNET_BASE_URL`, `SKYNET_API_KEY` and deployed principal
and visual model identifiers in the client's `.env`. Both models use the same
service URL and credential. Satisfy the provider's network and authentication
requirements; this project does not provision model access. The server does
not load a `.env` of its own during this launch. The sample file's two
`DOCUMENT_EXTRACTOR_*` settings are optional and only used by baseline conversion.

The example file sets both model timeouts to 600 seconds as sample configuration,
giving a 660-second MCP session timeout. They are not application defaults.
The historical run used a 900-second principal timeout and a 600-second visual
timeout; see its [trace](examples/trace-summary.md#recorded-execution). Recorded
model identifiers are not a promise of current service availability. Installation,
server startup and model execution were not repeated for these docs; the quick
start describes a fresh execution path, not verified byte-for-byte replay.

## Connection and runtime configuration

Both workflows start with `init-run`, which preserves one PDF under `input/`,
records its SHA-256 document identity in `manifest.json` and initializes
`status.json`. `extract-architecture-mcp` needs only successful source
preservation and a pending `architecture_mcp_extraction` phase. Baseline
rendering, conversion and figure phases need not have run.

Before external execution, the client validates its required settings and
server paths, strict run/status metadata, matching run identity, preserved PDF
path and SHA-256, and containment of MCP storage within the run. It then
exclusively reserves `mcp/architecture/` and saves the initial execution record.
An existing output entry or invalid local preflight is rejected before server
startup or lifecycle changes.

The runtime launches the configured executable directly through stdio, with
the configured working directory and no shell command parsing. The external
server stays in its own repository and environment. The client does not
install its dependencies or load that repository's `.env`.

The child receives `PDF_INGESTION_PDF` bound to the verified preserved PDF and
`PDF_INGESTION_RUN_DIR=<run_dir>/mcp`. These values come from run identity,
not caller-supplied document binding. Selected launch variables and explicit
endpoint/visual settings are forwarded; the whole parent environment is not.

The MCP CLI loads the current working directory's `.env`, with process values
taking precedence. It requires all eight variables listed in the README.
Principal and visual timeouts must be positive and finite. The principal
timeout applies per model request; the server receives the visual timeout
for each child visual-model request. The MCP session/tool timeout is the
visual timeout plus 60 seconds. All three effective timeouts are recorded.

The CLI accepts `RUN_DIR` and `--max-turns`, defaulting to 80 positive agent
iterations. It has no model, timeout or server-path overrides. This budget is
not a whole-run deadline. Execution is sequential, model and MCP retries are
disabled, tool concurrency is one and SDK tracing is disabled. CLI logging
is suppressed during execution and restored afterwards; errors use controlled
diagnostics rather than raw third-party exception messages.

## Progressive evidence acquisition

After starting the server, the runtime requires exactly these six tool names:

| Tool | Evidence access |
| --- | --- |
| `get_paper_overview` | Document context and outline |
| `read_pages` | Physical PDF page text |
| `read_section` | Text for an exact returned section ID |
| `search_paper` | Textual phrase/prefix search |
| `list_assets` | Asset identifiers and source pages |
| `get_asset` | Asset content or requested visual inspection |

The runtime calls `get_paper_overview` once and verifies its fingerprint against
the preserved PDF. The complete received overview becomes initial model
evidence only after that check passes. The agent can request the overview later,
but does not need another call merely for initialization.

The agent chooses subsequent requests to resolve specific architecture
questions, rather than receiving complete locally converted Markdown up front.
Instructions prioritize selected-design descriptions, parameter tables,
geometry figures and construction details. They require exact returned IDs
and unchanged pagination cursors with their original query/filter context.
Physical page numbering starts at one. Zero search matches do not prove
that a detail is absent from the paper.

A nonblank `get_asset(asset_id=..., question=...)` question requests visual
inspection inside the server. Question-free asset access is a different
operation. The principal agent receives the returned observation and
provenance; the configured child visual model performs the inspection.
Captions and catalog metadata alone do not establish that inspection occurred.

When a crop is unavailable, incomplete or unsuitable, the agent may explicitly
inspect its physical source page with `asset_id="page:N"`. This is another
requested evidence operation, not an automatic substitution. Questions should
be focused and neutral; relevant original construction text and its physical
page reference are supplied when already available.

Returned visual observations are model-generated evidence rather than original
paper statements. Partial coverage, unreadable features and unsupported
interpretations remain limitations. The prompt asks the agent to separate
paper content, visual observations, semantic interpretations and assumptions.
These instructions are not a guarantee of model compliance.

## Architecture report and assumptions

The MCP prompt focuses on components, materials, geometry, reported dimensions,
placement and electrical connections for the selected design. It excludes
performance extraction, calculations, coordinate generation and simulation
setup. Reported values should be preserved rather than changed to fit an
assumed arrangement.

Unlike the baseline prompt, the MCP prompt allows compatible completion
assumptions for necessary details the paper leaves open. Each adopted choice
uses an `H001`, `H002`, ... identifier, records the omission, working choice,
basis, uncertainty and affected component or relationship, and remains marked
where used. Assumptions are neither reported facts nor visual evidence, and
do not establish the authors' exact implementation.

Both architecture paths in this branch request these six Markdown sections:

1. Selected antenna
2. Components, materials and layers
3. Geometry, dimensions and feeding
4. Semantic interpretations and conflicts
5. Reconstruction gaps
6. Final architecture

The MCP report uses A-series evidence claims with `Reported` or `Visual`
classifications and an indented `Evidence:` line. Visual claims should identify
the exact asset, inspection ID and available physical page provenance. The
MCP prompt excludes `Derived` claims and calculations; semantic interpretations
remain ordinary prose referencing sourced claims. Section 5 contains the
completion-assumption table. Section 6 consolidates the adopted configuration
and identifies remaining details that block sizing, placement or connection.

The retained baseline still allows `Reported`, `Visual` and `Derived` claims
and prohibits engineering defaults to fill source gaps. Its six-section report
format therefore does not imply the MCP assumption policy. The report-format
extension in this branch also differs from the five sections currently in `main`.

`architecture_report.py` owns both prompts and the shared structural validator.
The validator checks the six headings, non-empty sections, claim identifier
uniqueness, supported classifications and evidence-line presence. It accepts
`Derived` for the baseline and does not enforce the MCP-specific prohibition,
validate assumption choices or resolve cited sources. It does not judge
scientific correctness or construction completeness.

A non-empty report can be published with structural errors. The runtime
records those errors and preserves the final text without semantic repair.
Operational `succeeded` is separate from structural and scientific acceptance.

## Execution artefacts and accounting

The [README output table](../README.md#current-outputs) lists the main paths.
Server-managed stores, images and inspection diagnostics remain under `mcp/`;
binding the document does not itself create SQLite. Store creation or reuse
occurs when a server tool opens it, including the startup overview request.

Persisted MCP architecture executions write directly to
`mcp/architecture/architecture_execution.json`, with no duplicate agent-probe
JSON. New executions use `format_version=2`:

- Identity, execution state, termination reason and configuration precede
  `operation_summary` and detailed `operations`.
- Each compact summary references a detailed record by stable `id`. Both
  lists follow recorded start-event order through `event_order`, independent
  of tied or backwards timestamps. The `events` ledger preserves chronology.
- Detailed records retain tool arguments, effective principal-model requests,
  received responses, timing, outcomes and correlation IDs. Startup calls have
  `origin=runtime`; agent-requested MCP calls have `origin=agent`.
- Final text, publication metadata and structural diagnostics accompany
  instructions, task and provenance. `accounting` separates principal-model,
  MCP and visual-model activity.

An operation's start is saved before dispatch. Received model and MCP responses
are saved before validation or SDK continuation. Truncated or unusable
principal responses remain inspectable but cause failure. Unfinished operations
can retain null finish times and durations in partial records.

The recorder omits headers and image payloads and redacts known environment
credential values. Received content is otherwise preserved subject to those
omissions. After a `get_asset` response is durable, an additional visual
provenance record links asset identity, inspection identity, source/rendered
pages, coverage and limitations before model continuation.

When a matching inspection ID exists, the client reads only its contained
`mcp/inspections/<inspection_id>.json` diagnostic. Identity, asset, question
and outcome must match. Missing, unreadable or mismatched diagnostics remain
explicit limitations. Relevant model, outcome, duration and available usage
are retained; the diagnostic's prompt, raw visual response and images are not
copied into the principal execution record.

Principal requests, received responses and MCP calls are counted separately;
MCP counts include the startup overview. A visual question or `get_asset` call
does not prove a visual-model call occurred. Confirmed visual calls require
received-completion evidence from the public server outcome or a validated
diagnostic. Unavailable evidence and configuration failures can establish zero
calls; timeouts or interrupted inspection without completion evidence can
leave call occurrence unknown. Successful observations are another count.

Repeated inspection IDs count once; inconsistent reuse is flagged. Principal
and visual token usage remain separate, with coverage limited to responses or
validated diagnostics that actually supply usage. Confirmed subtotals and
unknown cases must not be presented as an exact combined inference total.

Version 2 replaces the persisted MCP `calls` and `model_requests` arrays with
`operations`, and moves counts and usage into `accounting`. Historical
executions are not migrated. Ordinary connection/agent probes retain their
earlier layout, and the baseline execution JSON retains its own `schema_version`
format. Select the reader by the execution format rather than assuming every
file named `architecture_execution.json` has the same fields.

## Lifecycle, publication and failure boundaries

The two independent architecture prerequisites are:

```text
source_preservation -> architecture_mcp_extraction
source_preservation -> page_rendering -> document_conversion
    -> figure_extraction -> architecture_extraction
```

Either architecture path can run first, sequentially in the same run. Neither
marks unexecuted preprocessing phases as successful. Existing status files
without the MCP phase load with it pending, without eager rewriting or a schema
version change. Phase and run timestamps use timezone-aware `Europe/Lisbon`.

After the initial trace is durable, the MCP phase becomes `running` before
server startup. Publication requires usable final text and successful model
and server cleanup. Structural diagnostics are saved before atomic Markdown
publication at `mcp/architecture/architecture_evidence_report.md`. The published
Markdown equals the saved, redacted `final_text`. Global success follows durable
publication and execution success metadata.

Operational failure or budget exhaustion marks the started MCP phase `failed`
when persistence is available. Cancellation records `cancelled` in execution
JSON and `failed` with a cancellation reason in the global phase. The CLI exit
codes are 0 for success, 1 for operational/configuration failure, 2 for invalid
arguments and 130 for interruption/cancellation.

JSON and binary writers use temporary files, flush and sync, then atomically
replace each target. Execution and status files are separate writes, not a
cross-file transaction. Required trace-write failure stops continuation and
preserves the last valid record. Failure updates are attempted independently.
If finalization fails after publication, removal of only that execution's
report is attempted. An unavailable writer can leave a running phase or trace;
failed cleanup can leave a report without durable global success.

Every existing `mcp/architecture` entry is rejected, including an empty
directory, file or broken symlink. The MCP phase must be pending. Failed
executions retain their reservation; no overwrite, retry, reset or resume is
implemented. Existing stores, images, inspections, probe traces and separate
baseline architecture artefacts are allowed and preserved.

## Retained baseline

The baseline remains explicitly invocable in this branch:

```bash
uv run antenna-extract init-run "path/to/paper.pdf"
uv run antenna-extract render-pages "runs/run_<id>"
uv run antenna-extract convert-document "runs/run_<id>"
uv run antenna-extract extract-figures "runs/run_<id>"
uv run antenna-extract extract-architecture "runs/run_<id>"
```

Rendering verifies the source PDF and writes ordered page PNGs and
`pages/pages.json`, with dimensions, sizes and checksums. Conversion checks
run/page identity and requested page bytes, then sends every page to NuExtract3
in sequential batches of up to eight. Raw batch responses are saved before
parsing, with traces after successful parsing. Final Markdown is joined with
two newlines only after all batches succeed, without reliable page markers.

Figure preparation reads that Markdown and the preserved PDF. Docling detects
regions and associates numeric caption labels, with conservative same-page
recovery; PDFium renders the final crops. The figure manifest records settings,
provenance, timing and unresolved entries. A successful phase or figure ID does
not guarantee a usable crop. Docling performs local inference and may download
weights on first use; no endpoint configuration is required for that command.

Baseline conversion requires the README's `SKYNET_BASE_URL` and `SKYNET_API_KEY`,
plus `DOCUMENT_EXTRACTOR_MODEL` and positive
`DOCUMENT_EXTRACTOR_TIMEOUT_SECONDS`. Baseline architecture uses those endpoint
settings and the README's principal architecture model/timeout. Both commands
load the current directory's `.env`, preserving process precedence.
For baseline architecture, that model must also accept images in the tool
continuation; MCP principal text/tool support alone is insufficient.

The baseline agent requires successful figures and a pending architecture phase.
It receives complete Markdown and a catalog from figure/page manifests, then
uses zero or one `get_visual_assets` execution. A direct report takes one model
call; retrieval takes two, with the same model interpreting images. Requests
use exact catalog IDs and explicit availability results. There is no automatic
page substitution, additional retrieval round or automatic retry.

| Option | Current CLI default |
| --- | ---: |
| `render-pages --dpi` | 300 |
| `extract-figures --scale` | 4.0 |
| `extract-figures --margin-pt` | 2.0 |
| `extract-architecture --max-assets` | 6 |

Importable rendering and figure extraction default to 170 DPI and scale 3.0.
The CLI's scale help still says 3.0 despite passing 4.0; use explicit flags for
comparisons with older runs. Six assets is a count limit, not measured endpoint
capacity. The resolver checks identifiers and path containment, but does not
validate image contents, additional visual-asset hashes or byte-payload limits.

Baseline report/execution files remain under `architecture/`, with independent
`architecture_extraction` tracking. Its execution record stores model/tool
events, received model responses, counts, final text and structural diagnostics;
it does not record the complete effective requests and per-operation timing
available in MCP execution. Both execution formats are audit artefacts, not
the planned final antenna schema.

## Development probes

`scripts/probe_mcp_connection.py` is an explicit development tool. A connection
check needs only an initialized run and the separately installed server:

```powershell
uv run --no-sync python scripts/probe_mcp_connection.py `
  --run-dir "runs/run_<id>" `
  --mcp-executable "path/to/external-server/.venv/Scripts/mcp-pdf-ingestion.exe" `
  --mcp-cwd "path/to/external-server"
```

Connection mode verifies identity and the six-tool interface, calls only the
startup overview and records a fresh `mcp/probe_connection_<unique-id>.json`.
It loads no `.env`, forwards no model credentials, makes no model calls and
leaves manifest/status bytes unchanged. The server may still create or reuse
its document store.

Agent mode requires explicit `--agent-model` plus endpoint URL/key. It loads
the client's `.env`, defaults to `--agent-task geometry` and a positive budget
of eight turns, and writes `mcp/probe_agent_<unique-id>.json`. The geometry task
investigates one example rather than producing a full architecture report.
`--agent-task architecture` selects the full architecture instructions.

`--persist-architecture` additionally requires the architecture task and a
nonblank model. It publishes the MCP report/execution files and tracks the MCP
phase through the same runtime as the CLI. Without that flag, probes remain
status-neutral. The development probe's principal and MCP session timeouts are
600 seconds; optional visual model/timeout settings are forwarded when supplied.
Missing visual configuration remains an inspection limitation if requested.
Selecting architecture does not change the probe's default eight-turn budget.

`scripts/probe_multimodal.py` is a separate opt-in baseline protocol check. It
uses `ARCHITECTURE_AUTHOR_MODEL`, distinct from the architecture CLI setting.
Protocol compatibility does not establish scientific quality or model selection.

## Development and evaluation

Normal local checks use fake/scripted model clients and mocked Docling
conversion, without endpoints, model inference or weight downloads:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

[PLAN.md](../PLAN.md) retains the branch's implementation tasks and evaluation
record. Its [one-paper prompt evaluation](../PLAN.md#task-2---bounded-prompt-evaluation-2026-10-07)
records bounded live work and a selected candidate, with owner review pending.
The MCP-09 heading still says pending; the record does not establish closure of
all pilot acceptance checks. The six-case comparison remains planned. No general
scientific validity, endpoint capacity or end-to-end benchmark follows from that
pilot, scripted tests, structural checks or operational success.

The historical baseline
[architecture](https://github.com/GoncaGomes/antenna-paper-extraction/blob/main/00_ARCHITECTURE_V3.md)
and [roadmap](https://github.com/GoncaGomes/antenna-paper-extraction/blob/main/01_IMPLEMENTATION_ROADMAP_V3.md)
remain on `main`. They describe baseline design rationale and future stages,
with older status snapshots; they are not the iterative MCP implementation plan.
Current code and tests define executable behaviour. Repository development
rules remain in [AGENTS.md](../AGENTS.md).
