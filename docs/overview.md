# Technical overview

This document describes the baseline implemented in `main`. For setup,
configuration and commands, see the [README](../README.md). The baseline stops
at an architecture evidence report; results extraction, canonicalization, final
consumer JSON generation and complete orchestration remain planned.

## Processing stages

### Source preservation and page rendering

`init-run` creates a separate directory for one source PDF. It copies the source
under `input/`, records its filename, size and SHA-256 in `manifest.json`, and
initializes `status.json`. Document identity uses `sha256:<full-hash>`; run IDs
combine a timestamp with a unique suffix. The default parent is `runs/`.

`render-pages` requires successful source preservation and a pending rendering
phase. It verifies the preserved PDF against the manifest before rendering all
physical pages in order. `pages/pages.json` records document identity, rendering
settings, page numbers, asset IDs, dimensions, sizes and checksums. PNG names
follow `page_0001.png`, `page_0002.png`, and so on.

The current CLI passes **300 DPI** when `--dpi` is omitted. The importable
`render_pdf_pages` function defaults to 170 DPI. Set `--dpi 170` explicitly to
use the resolution described in earlier development records.

### Document conversion

`convert-document` requires successful page rendering. Before contacting the
endpoint, it checks run/status identity and the page manifest's document
identity. Each requested page image is checked against its recorded size and
SHA-256 before being included in a model request.

NuExtract3 receives every rendered page, with no relevance filtering. Batches
contain at most eight consecutive pages and execute sequentially. A successful
conversion makes `ceil(page_count / 8)` model calls. The request asks for prose,
tables, equations and captions to be preserved in Markdown; this instruction
does not guarantee conversion fidelity.

The parser requires a successful HTTP response, exactly one choice,
`finish_reason="stop"` and non-empty Markdown. It reads
`choices[0].message.content` and joins successful batches with two newlines.
It inserts no page markers. Page identity remains in `pages/pages.json`, and
the combined Markdown does not provide reliable claim-to-page mapping.

For each received batch, the raw response is saved before parsing. A trace is
saved only after parsing succeeds, with request settings, HTTP status, finish
reason, usage when available and measured model latency. Batch filenames use
one-based, four-digit numbering. `document_conversion/document.md` is written
only after all batches succeed. The first failure stops conversion; a transport
failure can occur before any raw response exists.

### Figure preparation

`extract-figures` requires successful document conversion, a pending figure
phase and no existing `figures/` entry. It reads the complete converted Markdown
and verifies the preserved PDF. Docling detects picture regions; numeric figure
labels from `<figcaption>` content associate Markdown captions with candidates.
Conservative same-page geometric recovery can recover a missing association.

PDFium renders crops from the preserved PDF, once per required page. Docling
image generation is disabled. `--scale` controls PDFium rendering, and
`--margin-pt` adds a crop margin bounded by the page. The current CLI defaults
are **scale 4.0** and **margin 2.0 points**; the importable extraction function
defaults to scale 3.0. The CLI's scale help text still says 3.0, so supply
`--scale 3.0` explicitly if that is the intended setting.

`figures/manifest.json` records document identity, tool versions, settings,
timings, caption associations, candidate positions and unresolved reasons.
PNGs are written only for renderable associations. A figure identifier does
not guarantee a crop: `relative_path` may be null. A successful phase can
contain unresolved figures or no PNGs at all.

Label uniqueness does not establish semantic caption equivalence or crop
quality. Docling may merge neighbouring content or split a compound figure.
The current implementation does not automatically repair those layouts;
manual review remains necessary.

### Architecture extraction

`extract-architecture` requires successful figure extraction, a pending
`architecture_extraction` phase and no existing `architecture/` entry. The
agent receives the complete `document_conversion/document.md`, a minimal
visual catalog and focused architecture instructions through the Agents SDK.

It has at most two model turns and one `get_visual_assets` execution. A direct
answer uses one model call. Retrieval uses two calls and one tool execution,
including when all requested assets are unavailable. Model and tool execution
are sequential; additional asset requests are rejected. Automatic retries and
SDK tracing are disabled. The same principal model interprets retrieved images.

The CLI's `--max-assets` defaults to six and must be positive. This bounds the
number of requested identifiers, not image bytes or endpoint capacity.
`ARCHITECTURE_AGENT_TIMEOUT_SECONDS` applies to each model request, not the
whole execution. The model must support the tool-call and image-continuation
interaction used by this baseline.

## Evidence access and report format

The visual catalog is built from `figures/manifest.json` and `pages/pages.json`.
Each figure has an exact `figure_id`, an availability status and a nullable
`page_id`; the page catalog lists declared IDs. It exposes no images initially.
Catalog availability describes manifest declarations rather than verified
image readability or quality.

The resolver accepts exact, unique catalog identifiers, enforces the count
limit and checks path containment. It returns images in request order or
explicit unavailability reasons. Figures and full pages may be requested
together, including an explicit page request when a figure crop exists.
It performs no automatic substitution, image-content validation or additional
visual-asset hash verification at retrieval time.

The architecture prompt focuses on the source-supported selected design,
components, materials, geometry, dimensions, relationships and feeding.
It asks the agent to distinguish observations from inferences and preserve
missing information or conflicts. It does not authorize engineering defaults
to fill source gaps or produce a final architecture JSON or CAD specification.

The requested English Markdown report has five sections:

1. Selected antenna
2. Components, materials and layers
3. Geometry, dimensions and feeding
4. Derivations and conflicts
5. Reconstruction gaps

Technical claims use identifiers such as `A001`, a `Reported`, `Visual` or
`Derived` classification, and an indented `Evidence:` line. Text references
can identify sections, tables, equations or faithful excerpts. Visual claims
should cite exact assets actually received. Captions and generated image
descriptions are not evidence that an image was inspected.

`architecture_report.py` defines the prompt and structural validator. Checks
cover the required headings and non-empty sections, claim identifier
uniqueness, supported classifications and evidence-line presence. They do not
resolve references or judge scientific accuracy, completeness or reconstructibility.
A non-empty report may be published despite structural errors, with those
diagnostics preserved in the execution JSON.

## Artefacts and persistence

The [README output table](../README.md#current-outputs) lists the run paths.
The architecture stage publishes:

- `architecture/architecture_evidence_report.md`: the final model text for
  human review, with claims, source references and gaps.
- `architecture/architecture_execution.json`: a versioned execution record
  containing run/document identity, configuration, instructions, ordered
  model/tool events, received model responses, counts, final text, structural
  diagnostics, timing, report path and failure information.

The execution record is updated incrementally at model/tool event boundaries.
Received model responses are recorded before SDK normalization and truncation
checks. A response ending with `finish_reason="length"` is retained but causes
failure instead of report publication. Asset result events record identifiers
and availability metadata rather than embedded image bytes.

Final text and structural diagnostics are saved before Markdown publication.
The report and final execution metadata are written before the global phase is
marked `succeeded`. That state means execution and persistence completed; it
does not mean structural or scientific acceptance.

Shared JSON and binary writers use temporary files in the destination
directory, flush and sync them, then replace the target atomically. Run and
lifecycle timestamps use timezone-aware `Europe/Lisbon` values. Strict Pydantic
models validate run, lifecycle, page-manifest and catalog boundaries.
The figure manifest and architecture execution record are persisted JSON;
neither is the planned final antenna contract.

Atomicity applies to individual files. Report, execution and status updates
are separate writes rather than a transaction across the whole run. Inspect
both `status.json` and execution diagnostics after a failure.

## Execution lifecycle and failure boundaries

Commands enforce this prerequisite sequence:

```text
source_preservation -> page_rendering -> document_conversion -> figure_extraction -> architecture_extraction
```

Phases progress from `pending` to `running`, then `succeeded` or `failed`, with
timestamps and inspectable failure records. Older status files can omit the
later baseline phases; loading supplies pending defaults. This lifecycle
supports explicit stage commands, not a complete orchestration engine.

Existing page output, conversion output files, figure output and architecture
output are rejected rather than silently replaced. Figure and architecture
preflight rejections leave their phase unchanged. Page rendering marks its
phase running before validating its PDF and output, so later validation errors
are recorded as failures. The commands expose no reset, retry or resume path.

Architecture reserves its output directory before model execution. Failures
retain the directory and the last successfully persisted diagnostic data. If
finalization fails after publishing a report, the handler attempts to remove
only that execution's report and record both local and global failure. Write or
cleanup failures can leave incomplete records or a residual report. The
baseline handler catches `Exception`; interruption is not guaranteed to be
finalized as a failed phase and can leave the last persisted state running.

Inspect the failure and retained artefacts before deciding how to proceed.
Creating a new run is available; automated recovery is not implemented.

## Relationship to the MCP experiment

The separate
[`exp/architecture-mcp` branch](https://github.com/GoncaGomes/antenna-paper-extraction/tree/exp/architecture-mcp)
retains the baseline commands and adds `extract-architecture-mcp`. Its agent
acquires evidence progressively through the external `mcp-pdf-ingestion`
server, rather than receiving a locally converted complete Markdown document
and making a single visual request.

The experimental command requires an initialized run with successful source
preservation and separately installed server/model configuration. It launches
the server through stdio, bound to the verified preserved PDF. No baseline
page rendering, NuExtract3 conversion or Docling figures are prerequisites.
The server stays in its own repository and environment.

The interface provides `get_paper_overview`, `read_pages`, `read_section`,
`search_paper`, `list_assets` and `get_asset`. Targeted visual questions use
`get_asset(..., question=...)`. Agent iterations have a configurable finite
budget, defaulting to 80 in the experimental CLI, with sequential execution
and no automatic retries.

MCP architecture outputs use `mcp/architecture/architecture_evidence_report.md`
and `mcp/architecture/architecture_execution.json`, with independent
`architecture_mcp_extraction` tracking. Both workflows can execute sequentially
in the same run in that branch, preserving their separate outputs. These are
experimental execution artefacts, not final consumer JSON. Use that branch's
[README](https://github.com/GoncaGomes/antenna-paper-extraction/blob/exp/architecture-mcp/README.md)
and [PLAN](https://github.com/GoncaGomes/antenna-paper-extraction/blob/exp/architecture-mcp/PLAN.md)
for its configuration and evaluation status.

## Development and evaluation

Normal local checks use fake or scripted model clients and mocked Docling
conversion. They must not contact institutional endpoints, run model inference
or download weights:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

`scripts/probe_multimodal.py` is a separate opt-in endpoint protocol probe.
Protocol compatibility, local tests and a successful execution do not establish
scientific extraction quality or justify a model for all papers. Scientific
acceptance requires reviewing claims against source evidence; endpoint payload
capacity, inspection latency and end-to-end performance remain unmeasured.

The existing [architecture](../00_ARCHITECTURE_V3.md) and
[implementation roadmap](../01_IMPLEMENTATION_ROADMAP_V3.md) retain design
rationale, historical observations, phase gates and future evaluation work.
Their status summaries still describe the architecture agent as future work;
the current code implements it and is the authority for executable behaviour.
This overview does not revise those development plans or claim their broader
scientific completion gates have been met. Repository contribution rules are
in [AGENTS.md](../AGENTS.md).
