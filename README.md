# Antenna Paper Extraction

Scientific antenna papers distribute construction details across prose, tables,
equations and figures. Antenna Paper Extraction prepares this evidence and
generates an architecture report for one PDF per run, with source references
and explicit reconstruction gaps for human review.

The project also aims to extract reported results and produce structured
consumer outputs. Those stages remain planned. The workflow described here is
the baseline implemented in `main`.

## How the workflow operates

Run the available stages explicitly and in order:

1. **Preserve the source.** Create an isolated run, copy the PDF and record its
   SHA-256 identity.
2. **Render pages.** Verify the preserved PDF and render every physical page as
   an ordered PNG asset with metadata and checksums.
3. **Convert the document.** Send all page images to NuExtract3 in sequential
   batches of up to eight pages and combine the returned Markdown.
4. **Prepare figures.** Use Docling to detect regions and associate them with
   Markdown captions, then render figure crops from the preserved PDF.
5. **Extract architecture.** Give an Agents SDK agent the complete Markdown and
   a figure/page catalog. It can retrieve exact visual assets once before
   producing a Markdown evidence report and an execution record.

The [technical overview](docs/overview.md) explains evidence access, artefacts,
persistence and failure behaviour.

## Implementation status

- **Implemented in `main`:** run preservation, page rendering, document
  conversion, figure extraction, bounded visual inspection and the baseline
  architecture agent, including report persistence and lifecycle tracking.
- **Experimental in
  [`exp/architecture-mcp`](https://github.com/GoncaGomes/antenna-paper-extraction/tree/exp/architecture-mcp):**
  progressive evidence acquisition through the external `mcp-pdf-ingestion`
  server. Its `extract-architecture-mcp` command starts from an initialized run
  without baseline conversion or figure extraction. The baseline is retained
  there for comparison; the MCP command is unavailable in `main`.
- **Planned:** results extraction, canonicalization, final
  `antenna_architecture.json` and `antenna_results.json` outputs, and complete
  pipeline orchestration.

Implementation, passing local tests and successful execution do not establish
general scientific validity. Report structure checks are diagnostic and can
fail even when an architecture execution is marked `succeeded`.

## Setup and usage

Use Python 3.12 and [`uv`](https://docs.astral.sh/uv/):

```bash
uv sync
uv run antenna-extract --help
```

Conversion requires access to an OpenAI-compatible endpoint with a deployed
NuExtract3 model. Architecture extraction requires a deployed model that
supports the baseline tool and multimodal interaction. Configure these settings
in the process environment or a local `.env` in the current working directory:

| Variable | Required by | Purpose |
| --- | --- | --- |
| `SKYNET_BASE_URL` | Conversion and architecture | Endpoint base URL |
| `SKYNET_API_KEY` | Conversion and architecture | Endpoint credential |
| `DOCUMENT_EXTRACTOR_MODEL` | Conversion | Deployed NuExtract3 identifier |
| `DOCUMENT_EXTRACTOR_TIMEOUT_SECONDS` | Conversion | Positive request timeout in seconds |
| `ARCHITECTURE_AGENT_MODEL` | Architecture | Deployed principal model identifier |
| `ARCHITECTURE_AGENT_TIMEOUT_SECONDS` | Architecture | Positive finite request timeout in seconds |

Both model commands load `.env`; existing process values take precedence.
Keep credentials local. Do not commit `.env`, source PDFs or large run artefacts.
Figure extraction needs no endpoint settings, but Docling performs local
inference and may download model weights on first use.

Replace `runs/run_<id>` with the directory printed by `init-run`. Quote paths
containing spaces:

```bash
uv run antenna-extract init-run "path/to/paper.pdf"
uv run antenna-extract render-pages "runs/run_<id>"
uv run antenna-extract convert-document "runs/run_<id>"
uv run antenna-extract extract-figures "runs/run_<id>"
uv run antenna-extract extract-architecture "runs/run_<id>"
```

Runs use `runs/` by default; `init-run --runs-root PATH` selects another parent.
Rendering accepts `--dpi`; figure extraction accepts `--scale` and `--margin-pt`.
Architecture accepts `--max-assets`, defaulting to six assets in one request.
See the [overview](docs/overview.md#processing-stages) for current rendering
defaults and stage prerequisites.

## Current outputs

Paths below are relative to the run directory and appear as their stages
complete. Failed runs may contain partial diagnostics.

| Path | Purpose |
| --- | --- |
| `manifest.json`, `status.json` | Source identity and phase lifecycle |
| `input/<original-filename>.pdf` | Preserved source bytes |
| `pages/pages.json`, `pages/page_0001.png`, ... | Ordered page metadata and images |
| `document_conversion/document.md` | Combined converted Markdown |
| `document_conversion/nuextract3_raw_response_batch_0001.json`, ... | Received conversion responses |
| `document_conversion/nuextract3_trace_batch_0001.json`, ... | Parsed batch diagnostics and timings |
| `figures/manifest.json`, `figures/figure_<number>.png` | Caption associations, unresolved entries and available crops |
| `architecture/architecture_evidence_report.md` | Architecture claims, evidence and reconstruction gaps |
| `architecture/architecture_execution.json` | Model/tool events, final text, counts and structural diagnostics |

`architecture_execution.json` is an execution artefact, not the planned final
architecture schema. Neither final consumer JSON file is generated today.

## Limitations and further documentation

- Converted Markdown has no reliable page markers; batch boundaries are
  mechanical and may need review.
- Caption association and crop availability do not establish visual quality.
  Docling can merge or split regions; unresolved figures remain explicit.
- Visual retrieval allows one request and no automatic page substitution.
  Six assets is a configured limit, not measured endpoint capacity.
- Execution is sequential, with no automatic retries or supported reset/resume
  command. Scientific correctness and end-to-end performance need evaluation.

Read the [technical overview](docs/overview.md) for the current system and
[local development checks](docs/overview.md#development-and-evaluation).
The existing [architecture](00_ARCHITECTURE_V3.md) and
[implementation roadmap](01_IMPLEMENTATION_ROADMAP_V3.md) remain available for
design rationale and future phases. Their phase-status text predates the
implemented architecture agent; code and tests define current behaviour.
[AGENTS.md](AGENTS.md) records repository development rules.
