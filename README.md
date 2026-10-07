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

## Approved MCP experiment

The `exp/architecture-mcp` branch will compare iterative MCP evidence acquisition
with the existing extraction path. Its implementation tasks are in
[PLAN.md](PLAN.md). The deterministic connection probe, narrow geometry evidence
task, MCP architecture report persistence and its independent run lifecycle are
implemented. The explicit development probe can publish the report and incremental
execution trace. The experimental `extract-architecture-mcp` CLI is implemented;
live scientific evaluation remains pending.

- Reuse `init-run` to preserve one PDF and establish run identity, then launch
  an external MCP server through stdio, bound to that preserved PDF.
- Keep the server in its own repository and environment. Server-derived data
  belongs under `<run_dir>/mcp/`; its source tree is not copied here.
- Let the architecture agent acquire evidence iteratively through all six MCP
  tools using the Agents SDK. Use a finite, configurable turn budget, defaulting
  to 80 in the production CLI, with sequential model/tool execution and no
  automatic retries.
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
when a tool opens the store; binding itself does not create SQLite. The probe's
overview call can create or reuse the store below, and the probe writes a local
trace. Agent tool requests may also produce server image/inspection artefacts.
The implemented MCP paths are:

| MCP artefact | Purpose |
| --- | --- |
| `mcp/store/<sha256[:16]>/paper.sqlite` | Server document store |
| `mcp/images/...` | Server image assets |
| `mcp/inspections/...` | Visual inspection diagnostics |
| `mcp/probe_connection_<unique-id>.json` | Incremental deterministic connection-probe trace |
| `mcp/probe_agent_<unique-id>.json` | Geometry or architecture probe: ordered model/MCP trace and `final_text` |
| `mcp/architecture/architecture_evidence_report.md` | MCP-derived evidence report, published by the MCP CLI or probe `--persist-architecture` |
| `mcp/architecture/architecture_execution.json` | Versioned chronological execution trace, with structural diagnostics and publication metadata |

Baseline architecture artefacts remain under `architecture/`, tracked by
`architecture_extraction`. MCP publication uses `architecture_mcp_extraction`
and `mcp/architecture/`. Both approaches can run sequentially in the same run,
in either order, preserving each other's phase and artefacts. The baseline still
requires successful figure extraction; the MCP path requires successful source
preservation and its own pending phase. The probe accepts
explicit server executable and working-directory paths and optional geometry or
architecture agent tasks. The production CLI loads validated server/model settings
from the environment and always publishes the architecture report. Tool calls,
principal-model requests and confirmed visual-model calls are counted separately;
a `get_asset` call or supplied question does not prove a visual-model request
occurred, particularly for unavailable evidence or configuration failures.

## Setup and current configuration

Use Python 3.12 and `uv`:

```bash
uv sync
uv run antenna-extract --help
```

`convert-document`, `extract-architecture`, `extract-architecture-mcp` and the
probe's agent mode load `.env` from the current working directory; existing process environment values take
precedence.

| Environment variable | Used by |
| --- | --- |
| `SKYNET_BASE_URL` | Conversion, architecture and agent probe: OpenAI-compatible endpoint base URL |
| `SKYNET_API_KEY` | Conversion, architecture and agent probe: endpoint credential |
| `DOCUMENT_EXTRACTOR_MODEL` | Conversion: deployed NuExtract3 identifier |
| `DOCUMENT_EXTRACTOR_TIMEOUT_SECONDS` | Conversion: positive timeout in seconds |
| `ARCHITECTURE_AGENT_MODEL` | Baseline and MCP architecture: deployed principal model identifier |
| `ARCHITECTURE_AGENT_TIMEOUT_SECONDS` | Baseline and MCP architecture: positive finite timeout per principal-model request in seconds |
| `VISUAL_INSPECTION_MODEL` | MCP architecture CLI: required deployed visual model identifier |
| `VISUAL_INSPECTION_TIMEOUT_SECONDS` | MCP architecture CLI: required positive finite timeout per child visual-model request in seconds |
| `MCP_PDF_SERVER_EXECUTABLE` | MCP architecture CLI: existing external server executable file |
| `MCP_PDF_SERVER_CWD` | MCP architecture CLI: existing external server working directory |

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

To run experimental MCP architecture extraction, only `init-run` is required.
Configure all eight MCP CLI settings in the process environment or the current
working directory's `.env`, for example:

```dotenv
SKYNET_BASE_URL=https://your-endpoint/v1
SKYNET_API_KEY=your-local-credential
ARCHITECTURE_AGENT_MODEL=your-deployed-principal-model
ARCHITECTURE_AGENT_TIMEOUT_SECONDS=600
VISUAL_INSPECTION_MODEL=your-deployed-visual-model
VISUAL_INSPECTION_TIMEOUT_SECONDS=600
MCP_PDF_SERVER_EXECUTABLE='C:\dev\reviewer-mcp\.venv\Scripts\mcp-pdf-ingestion.exe'
MCP_PDF_SERVER_CWD='C:\dev\reviewer-mcp'
```

The command is `antenna-extract extract-architecture-mcp RUN_DIR [--max-turns N]`.
`RUN_DIR` is required; `--max-turns` must be a positive integer and defaults to 80.
This is an opt-in example, not part of local verification:

```powershell
uv run --no-sync antenna-extract extract-architecture-mcp `
  "C:\dev\antenna-paper-extraction\runs\run_<id>" `
  --max-turns 80
```

Process environment takes precedence over `.env` (`override=False`). The CLI
validates every required setting and both server paths before output reservation,
lifecycle changes or external calls. Quote paths containing spaces. It launches
the configured executable directly through stdio with the configured working
directory; it does not parse shell command strings, load the server repository's
`.env`, install the server or synchronize its dependencies. There are no CLI
model, timeout or server-path overrides.

The principal timeout applies to each model request, not the entire run;
`max_turns` bounds agent iterations. The child receives the configured visual
model and visual timeout. The MCP session/tool timeout is the visual timeout plus
60 seconds for rendering and transport, without another environment setting.
Execution JSON records all three effective timeouts. Execution is sequential,
automatic retries and SDK tracing are disabled. Logs are suppressed during this
command and restored afterwards; errors exclude raw third-party exception bodies.

The verified run supplies `PDF_INGESTION_PDF` and
`PDF_INGESTION_RUN_DIR=<run_dir>/mcp`; binding values from `.env` are ignored.
Only established launch variables and endpoint/visual settings are forwarded.
The CLI always runs the architecture task with publication and independent
`architecture_mcp_extraction` tracking; the baseline `extract-architecture`
command and `architecture_extraction` phase retain their behaviour. No rendering,
NuExtract3 conversion or Docling figures are prerequisites.

Outputs are `mcp/architecture/architecture_evidence_report.md` and
`mcp/architecture/architecture_execution.json`, alongside server stores, images
and inspection diagnostics. Any existing `mcp/architecture` entry is rejected,
and the MCP phase must be pending. Failed executions retain their reservation;
there is no overwrite, retry, reset or resume. Exit codes are 0 for success,
1 for operational/configuration failure, 2 for invalid command arguments and
130 for interruption/cancellation. Structural validation remains diagnostic;
scientific validation and live evaluation are pending. The publication and
failure-persistence limitations described below apply to both callers.

To verify only the external MCP connection, use an existing initialized run and
the separately installed server. Supply all paths explicitly:

```powershell
uv run --no-sync python scripts/probe_mcp_connection.py `
  --run-dir "runs/run_<id>" `
  --mcp-executable "path/to/external-server/.venv/Scripts/mcp-pdf-ingestion.exe" `
  --mcp-cwd "path/to/external-server"
```

The probe verifies the actual preserved PDF SHA-256 against the strict run
manifest before server startup, discovers exactly the six documented tools, and
calls only `get_paper_overview` with empty arguments to verify its fingerprint.
It requires successful source preservation, but no rendered pages, conversion
or figures. The child receives absolute `PDF_INGESTION_PDF` and
`PDF_INGESTION_RUN_DIR=<run_dir>/mcp` paths and launch-related environment settings;
model credentials are not forwarded and `.env` is not loaded. Session timeout is
600 seconds, automatic retries are disabled, and the SDK context closes the
connection on success, failure and cancellation. Exit code 0 means every check
passed; failures emit controlled diagnostics and return nonzero. There are zero
model calls or visual requests and no manifest/status changes. After local
preflight succeeds, each invocation creates a separate
`mcp/probe_connection_<unique-id>.json` and prints its path, including when the
connection subsequently fails. The trace records run/document identity,
Europe/Lisbon start/end timestamps, overall state and ordered calls with locally
generated identifiers, arguments, timing and complete received MCP responses.
Each call's `started` record is saved atomically before execution; its response
is saved before returning to overview identity validation. Response fields,
content blocks and aliases survive, excluding known environment credential
values, image content data and embedded image data URIs, with explicit omission
markers. Environments, headers, client configuration and raw exception messages
are not recorded.

Tool outcomes are separate from overall probe success: a received response can
still fail identity validation or connection cleanup. Transport errors, MCP
error responses and cancellation retain diagnostics when persistence is
possible. Required write failures stop the probe and preserve the last valid
trace; abrupt interruption can leave a call marked `started`. Overall success
is saved only after identity checks and connection cleanup pass.
The overview may create or reuse
`mcp/store/<sha256[:16]>/paper.sqlite`; the probe does not access SQLite directly.

To run the small geometry evidence task on an initialized run, explicitly select
the principal model. The agent does not need rendered pages, converted Markdown
or extracted figures. It chooses its own sequence from all six tools and may ask
targeted visual questions or explicitly inspect a source page (`page:N`). It
describes one example, with dimensions, associations, uncertainties and source
references; insufficient evidence is a valid honest final answer.

```powershell
$env:SKYNET_BASE_URL = "https://your-endpoint/v1"
$env:SKYNET_API_KEY = "your-local-credential"
$agentModel = "your-explicit-deployed-model"
uv run --no-sync python scripts/probe_mcp_connection.py `
  --run-dir "C:\dev\antenna-paper-extraction\runs\run_<id>" `
  --mcp-executable "C:\dev\reviewer-mcp\.venv\Scripts\mcp-pdf-ingestion.exe" `
  --mcp-cwd "C:\dev\reviewer-mcp" `
  --agent-model $agentModel `
  --max-turns 8
```

The probe-only selector `--agent-task {geometry,architecture}` defaults to
`geometry`, preserving the existing instructions and task. Architecture requires
`--agent-model`; selecting it without a model fails before server startup or trace
creation. It uses a separate complete MCP instruction set, with the same six
report headings and A-series `Reported`, `Visual` and `Derived` claims. Visual
claims cite the exact asset ID, returned inspection ID and available page
provenance, retaining inspection limitations. Proposed completion assumptions
use H-series IDs in a section 5 table, with justification and uncertainty, and
are explicitly marked as assumed wherever used in the working reconstruction.
They are ordinary report content, distinct from extracted evidence claims.
Both architecture paths use the six-heading format. Section 6, `Final architecture`,
consolidates the adopted configuration into a self-contained description for later
construction and ends with any remaining blocking reconstruction gaps. The format
extension leaves each path's extraction and assumption policies unchanged.

To opt into architecture investigation and report publication with a larger finite
budget, use an existing initialized run and an explicit deployed principal model
identifier:

```powershell
uv run --no-sync python scripts/probe_mcp_connection.py `
  --run-dir "C:\dev\antenna-paper-extraction\runs\<existing-initialized-run>" `
  --agent-model "<deployed-principal-model-id>" `
  --agent-task architecture `
  --persist-architecture `
  --max-turns 80 `
  --mcp-executable "C:\dev\reviewer-mcp\.venv\Scripts\mcp-pdf-ingestion.exe" `
  --mcp-cwd "C:\dev\reviewer-mcp"
```

Architecture selection does not increase the default budget of 8. Both tasks
persist their exact selected instructions, task and effective model inputs in the
probe trace. The runtime's complete startup overview response, including its
outline and available metadata, is supplied as initial evidence only after its
document identity matches the verified preserved PDF. It appears in the first
recorded model request as evidence, not instructions; no second initialization
call is made. The agent can still explicitly call `get_paper_overview`. When no
initial overview is supplied, the architecture instructions request it once.
The returned report is stored unchanged in its existing `final_text`
field, without runtime structural rejection, semantic validation or automatic
correction. Without `--persist-architecture`, the existing connection, geometry
and architecture-text probes retain their paths and behaviour.

`--persist-architecture` requires `--agent-task architecture` and a nonblank
explicit `--agent-model`. Local configuration and preserved-PDF/identity preflight
and a pending `architecture_mcp_extraction` check complete before exclusively
reserving `mcp/architecture/`. Invalid preflight or existing-output rejection
does not change `status.json` or start external calls. No rendered pages,
NuExtract3 conversion, `document.md`, Docling figures or successful baseline
preprocessing phases are required. Existing server stores, images, inspections,
probe traces and baseline architecture outputs are allowed. Any existing
`mcp/architecture` entry is rejected, including an empty directory, file or broken
symlink; outputs must remain contained in the run's MCP directory. Failed
executions retain their reservation and reject a later invocation. Running,
succeeded and failed MCP phases are rejected without automatic reset or resume.

The same recorder starts directly in `mcp/architecture/architecture_execution.json`
before external calls; it creates no duplicate `probe_agent` trace. After initial
trace persistence, the MCP phase enters `running` before server startup. If that
status write fails, no external execution starts and available diagnostics remain.
Its `structural_validation` and `report_path` initially contain null. After usable
final text and successful model/server cleanup, the existing structural validator
records `passed` and `errors` before atomic UTF-8 Markdown publication. Non-empty
structurally invalid reports are still published, with `passed=false`; operational
success does not imply scientific acceptance. The Markdown preserves the saved,
redacted `final_text`, including A-series claims and H-series assumptions, without
rewriting or repair. Success is persisted only after publication, with
`report_path=mcp/architecture/architecture_evidence_report.md`. Report-write
failures return failure with `termination_reason=persistence_failure` when
diagnostics can be saved. If final execution persistence fails, removal of only
the just-published report is attempted; the last valid JSON and other evidence
are preserved. The global MCP phase enters `succeeded` only after report publication
and execution success metadata are durable. If this final status write fails,
execution returns failure, removes only its own published report when possible,
clears `report_path` in available execution diagnostics and attempts to mark the
started phase `failed`. Operational failure and turn-budget exhaustion also mark
that phase `failed`, using controlled reasons. Cancellation marks it `failed` with
reason `cancellation`, while the execution trace remains `cancelled` and CLI
cancellation is re-raised.

Execution JSON and `status.json` remain separately atomic files. Failure updates
are attempted independently, preserving the original execution reason and available
raw responses. An unavailable writer can leave a running trace or phase; failed
report removal can leave Markdown without durable global success. Controlled
diagnostics report these limitations. No cross-file transaction, retry or recovery
is provided. The production CLI uses the same shared runtime and persistence policy.

Scripted local tests establish integration and structural compatibility, including
H-series tables; live model policy compliance and scientific accuracy remain
pending explicit evaluation.

Only agent mode loads the current directory's `.env`, with process values taking
precedence, before constructing the trace. It requires `SKYNET_BASE_URL` and
`SKYNET_API_KEY`; no principal model is inferred from environment variables.
`--agent-model` must be nonblank and `--max-turns` a positive integer (default 8).
For optional visual inspection, explicitly set `VISUAL_INSPECTION_MODEL` and
`VISUAL_INSPECTION_TIMEOUT_SECONDS`, in the process or `.env`. Agent mode forwards
only these four endpoint/visual settings in addition to the existing launch
environment. Missing visual configuration remains a server-reported limitation
if inspection is requested; no visual model is selected automatically.

The development probe uses OpenAI-compatible Chat Completions with a 600-second
principal timeout and 600-second MCP session timeout; its visual timeout is
forwarded from the optional environment setting. Model/client and MCP retries
are disabled. SDK tool concurrency is one,
including when a model returns multiple tool calls, and `parallel_tool_calls` is
false. SDK tracing is disabled. No live inference is part of local tests.

Each ordinary agent probe prints a fresh `mcp/probe_agent_<unique-id>.json` path and
preserves earlier traces. Publication mode prints its reserved
`mcp/architecture/architecture_execution.json` path. The shared atomic writer
persists effective messages/instructions,
advertised tool schemas and request settings before dispatch, and complete raw
Chat Completions responses before SDK normalization or tool execution. Records
include local model request IDs, ordered events, raw tool-call IDs/arguments,
finish reasons, usage when available and Lisbon timestamps/timing. MCP records
link the local request ID and SDK tool-call ID to their separate local call ID;
the preliminary identity-check overview has no model/tool-call ID. Credentials,
headers and image payloads are omitted from both model and tool records.

`state=succeeded` with `termination_reason=final_answer` means final text was saved
and client/session cleanup completed; publication mode additionally requires
durable report publication metadata. `state=failed` with `max_turns` means the
budget was exhausted; `model_failure`, `tool_failure` or `cleanup_failure` identify
other execution failures. Cancellation records `state=cancelled` and
`termination_reason=cancellation`. Counts distinguish principal model requests,
received responses and MCP calls (including the preliminary overview). Raw usage
is retained per response; totals include only responses reporting usage and state
their coverage. Tool outcomes remain separate from execution state. Required
persistence failure stops continuation and returns nonzero; because the writer is unavailable,
the last valid trace can retain `state=running`, a `started` record or final text
without a terminal state. The controlled CLI diagnostic identifies persistence
failure. Truncated/unusable responses are preserved and fail explicitly. Exit
codes are 0 for normal completion, 1 for failure and 130 for cancellation. Probes
without persistence remain byte-for-byte neutral for manifest/status files.
Publication mode changes only the MCP phase in `status.json`; `manifest.json` and
baseline phases remain unchanged.
Separate MCP architecture report/execution files are always published by the MCP
CLI; development probes require `--persist-architecture`.

New persisted MCP architecture executions use `format_version=2`. Compact
identity, state, termination reason and configuration precede `operation_summary`
and one detailed `operations` list. Each summary references its detailed record
by stable `id` and includes `type` (`model` or `mcp`), name, origin, start/finish
times, duration and state. Both lists follow recorded start-event order through
`event_order`, even when timestamps tie or move backwards. The compact `events`
ledger remains available for response chronology. Detailed payloads occur once,
retaining original arguments, effective requests, raw responses, errors, local
and SDK correlation IDs, parent model references and visual inspection references.
Startup MCP calls have `origin=runtime`; agent-requested calls have `origin=agent`.
Unfinished operations retain null finish time and duration in running or partial
traces. Recording still precedes execution, and raw responses still precede
validation, with sequential execution, zero retries and atomic writes.

Final text, publication metadata and diagnostics follow the operations.
`accounting.principal_model` holds request/response counts and usage;
`accounting.mcp_calls` counts all MCP calls, including startup;
`accounting.visual_model` preserves the separate visual counts, uncertainty and
usage coverage described below. Instructions, task and provenance remain saved.
Version 2 replaces the persisted `calls`/`model_requests` arrays with `operations`
and moves `counts`, `usage` and `visual_accounting` into explicit accounting.
Consumers of architecture execution JSON must select the layout by version.
Historical executions are not migrated; ordinary connection/agent probe JSON
and the baseline architecture execution format retain their existing layout.

After the complete `get_asset` response is durable, its call record gains a
`visual` summary, saved before SDK continuation. It retains returned asset ID,
status/reason, inspection ID, source pages, rendered pages, coverage and
limitations, plus whether the request contained a nonblank question. Malformed
JSON, missing/invalid visual fields and conflicting asset/document identity are
explicit provenance outcomes; the raw response and tool outcome remain intact.
Rendering alone establishes neither a received completion nor a successful
observation. Returned partial coverage remains partial.

Diagnostic references use `mcp/inspections/<inspection_id>.json`, relative to the
bound run. Only that file is read: IDs must match the server's 32 lowercase hex
characters, paths must remain inside the expected directory (including symlinks),
and diagnostic inspection, document, asset, question and outcome must match.
Lookup outcomes are `not_applicable`, `available`, `missing`, `unreadable`,
`invalid` or `mismatched`. Failed lookups remain limitations, without stopping
execution or creating files. Only reported model, outcome, duration and available
token counts are retained; diagnostic prompts, raw responses and image bytes
are not copied. Question-free access performs no diagnostic lookup.

The agent trace's separate `visual_accounting` counts requested inspections,
confirmed model calls, cases with unknown call occurrence and successful
observations. A **confirmed visual-model call** means the public server outcome
establishes a received completion (`success`, `truncated`, `refused`, `empty`,
`invalid_response`), or a validated diagnostic contains a received response or
`received` outcome. Each establishes one call, including unusable completions;
only `success` establishes an observation. Question-free access, unavailable
regions, configuration errors before dispatch and rendering/image-persistence
errors establish zero calls. Timeouts, model errors and diagnostic-persistence
errors without received-completion evidence remain unknown. Malformed responses
and interrupted requests also remain unknown when inspection was requested.
The diagnostic contract has no dispatch marker: settings or `response=null`
do not prove a request was sent or that no call occurred.

Each observation belongs to its local MCP call ID. Repeated inspection IDs count
once and link to the first call; inconsistent reuse is flagged on every linked
call and contributes one unknown case instead of a confirmed count. Distinct
inspection IDs count independently even when the rendered PNG was reused.
Visual usage is separate from principal usage, covers only validated diagnostics
for confirmed unique calls and omits missing token fields. The trace reports a
confirmed subtotal and unknown cases, without an exact combined inference total.

`init-run` accepts `--runs-root` (default `runs/`). Other available options and
current defaults are:

| Command option | Effective CLI default | Importable function default |
| --- | ---: | ---: |
| `render-pages --dpi` | 300 | 170 |
| `extract-figures --scale` | 4.0 | 3.0 |
| `extract-figures --margin-pt` | 2.0 | 2.0 |
| `extract-architecture --max-assets` | 6 | 6 |
| `extract-architecture-mcp --max-turns` | 80 | Shared probe: 8 |

`--scale` controls PDFium crop rendering, not Docling settings. The CLI help for
`--scale` still says 3.0 and needs a separate correction. Tests now expect the
current CLI defaults of 300 DPI and scale 4.0, and conversion temperature 0.2.
Use explicit `--dpi 170` and `--scale 3.0` when comparing
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
`Europe/Lisbon`; durable JSON and binary writes use atomic replacement. Legacy
status files without `architecture_mcp_extraction` load with that phase `pending`,
without eager migration or rewriting; schema version remains `1.0`.

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
bodies or per-event timing; the MCP agent probe records those separately.
Truncation or execution failure preserves prior events without publishing a report. If finalization
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
