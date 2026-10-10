# Antenna Paper Extraction

Scientific antenna papers distribute construction details across prose, tables,
equations and figures. Antenna Paper Extraction produces an architecture report
for one PDF per run, with source references, explicit assumptions and remaining
reconstruction gaps for human review.

This branch, `exp/architecture-mcp`, experiments with acquiring evidence
progressively through MCP. Results extraction and final structured consumer
outputs remain planned.

## How the MCP workflow operates

1. **Preserve the source.** `init-run` copies the PDF into an isolated run and
   records its SHA-256 identity.
2. **Connect the evidence source.** The runtime verifies the preserved PDF,
   launches the external `mcp-pdf-ingestion` server through stdio and checks its
   tool interface and document identity.
3. **Acquire evidence progressively.** An Agents SDK agent reads relevant
   pages or sections, searches text and requests assets as questions arise.
   Targeted visual questions are handled by the server's configured visual model.
4. **Publish the architecture report.** Save the final Markdown and incremental
   execution record, then update the independent MCP lifecycle phase.

The MCP path needs an initialized run; it does not require baseline page
rendering, NuExtract3 conversion or Docling figure extraction. The retained
baseline instead supplies complete converted Markdown and a local figure/page
catalog, with at most one visual retrieval request. Both paths remain available
for comparison. See the [technical overview](docs/overview.md).

## Implementation status

- **Implemented experimental functionality:** `extract-architecture-mcp`,
  progressive evidence acquisition, incremental model/tool recording, report
  publication and independent `architecture_mcp_extraction` tracking. Connection
  and evidence-agent development probes are also available.
- **Retained baseline:** source preservation, rendering, conversion, figure
  preparation and `extract-architecture`, with separate artefacts and lifecycle.
- **Planned:** results extraction, canonicalization, final
  `antenna_architecture.json` and `antenna_results.json` outputs, and complete
  pipeline orchestration.

[PLAN.md](PLAN.md#task-2---bounded-prompt-evaluation-2026-10-07) records a prompt
evaluation on one paper. Owner review and the planned six-case comparison remain
pending. This does not establish general scientific validity. Report structure
checks are diagnostic; a non-empty report can be published with structural errors.

## Setup and usage

Use Python 3.12 and [`uv`](https://docs.astral.sh/uv/) for this client:

```bash
uv sync
uv run antenna-extract --help
```

Install `mcp-pdf-ingestion` separately in its own repository and environment.
The client needs its existing executable and working directory, plus access to
an OpenAI-compatible endpoint with deployed principal and visual models.
It does not install or synchronize the server's dependencies.

All eight settings below are required by `extract-architecture-mcp`. Put them
in the process environment or a local `.env` in the current working directory:

| Variable | Purpose |
| --- | --- |
| `SKYNET_BASE_URL` | Endpoint base URL |
| `SKYNET_API_KEY` | Endpoint credential |
| `ARCHITECTURE_AGENT_MODEL` | Deployed principal model identifier |
| `ARCHITECTURE_AGENT_TIMEOUT_SECONDS` | Positive finite timeout per principal-model request |
| `VISUAL_INSPECTION_MODEL` | Deployed visual model identifier for the server |
| `VISUAL_INSPECTION_TIMEOUT_SECONDS` | Positive finite timeout per visual-model request |
| `MCP_PDF_SERVER_EXECUTABLE` | Existing server executable file |
| `MCP_PDF_SERVER_CWD` | Existing server working directory |

Timeouts are in seconds. Process values take precedence over `.env`.
The client derives document binding from the verified run; do not configure
`PDF_INGESTION_PDF` or `PDF_INGESTION_RUN_DIR` manually. Keep credentials local
and do not commit `.env`, source PDFs or large run artefacts.

Replace `runs/run_<id>` with the directory printed by `init-run`:

```bash
uv run antenna-extract init-run "path/to/paper.pdf"
uv run antenna-extract extract-architecture-mcp "runs/run_<id>" --max-turns 80
```

Runs use `runs/` by default; `init-run --runs-root PATH` selects another parent.
`--max-turns` must be positive and defaults to 80. It bounds agent iterations,
not the total runtime. Quote paths containing spaces. The
[overview](docs/overview.md#connection-and-runtime-configuration) explains timeouts
and server launch behaviour, and includes [baseline usage](docs/overview.md#retained-baseline)
and [development probes](docs/overview.md#development-probes).

## Current outputs

Paths are relative to the run directory. Server assets and diagnostics depend
on the evidence requested; failed runs may retain partial records.

| Path | Purpose |
| --- | --- |
| `manifest.json`, `status.json`, `input/<original-filename>.pdf` | Run identity, lifecycle and preserved source |
| `mcp/architecture/architecture_evidence_report.md` | Architecture evidence, working assumptions and reconstruction gaps |
| `mcp/architecture/architecture_execution.json` | Incremental execution JSON; new MCP executions use `format_version=2` |
| `mcp/store/<sha256[:16]>/paper.sqlite` | Server-managed document store |
| `mcp/images/...`, `mcp/inspections/...` | Server image assets and visual inspection diagnostics |
| `mcp/probe_connection_<unique-id>.json`, `mcp/probe_agent_<unique-id>.json` | Development-probe traces when publication is not selected |
| `architecture/architecture_evidence_report.md`, `architecture/architecture_execution.json` | Separate baseline report and execution record |

Execution JSON records operations and diagnostics; it is not a final antenna
schema. Neither `antenna_architecture.json` nor `antenna_results.json` is generated.
See the [overview](docs/overview.md#execution-artefacts-and-accounting) for version
boundaries and interpretation of call counts.

## Limitations and further documentation

- MCP observations are model-generated evidence. Assumed construction choices
  are explicitly marked and do not establish the authors' exact implementation.
- Report structure checks do not verify source fidelity, scientific correctness
  or reconstruction completeness.
- Execution is sequential with no automatic retries, overwrite, reset or resume.
  An existing `mcp/architecture/` entry or a non-pending MCP phase is rejected.
- Report, execution and status writes are individually atomic. Persistence or
  cleanup failures can leave partial records; recovery is not automated.

Read the [technical overview](docs/overview.md) for evidence access, report format,
persistence, lifecycle and baseline differences. [PLAN.md](PLAN.md) retains this
branch's development and evaluation record; some status labels predate later
work. Code and tests define current executable behaviour.
[AGENTS.md](AGENTS.md) records repository development rules and local checks.
