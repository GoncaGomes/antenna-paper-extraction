# Experimental MCP execution trace summary

This summary accompanies the [report excerpt](architecture-report.md) from
`run_20261007T111320+0100_e4875a37`. It uses the persisted MCP architecture
execution, two visual-inspection diagnostics, run metadata and the server store.
No new extraction was run.

## Provenance

The source is John and Ammann, *Optimization of Impedance Bandwidth for the
Printed Rectangular Monopole Antenna*,
[DOI: 10.1002/mop.21109](https://doi.org/10.1002/mop.21109).
The title, authors and DOI are present on physical cover pages 1-2 in the stored
PDF text. The overview reports 11 physical pages and spells the title
"Optimisation", as does the paper body. All page references below count covers.

`manifest.json` identifies
`input/playground_optimization-of-impedance-bandwidth-for-the-printed.pdf`.
Its recorded SHA-256 matches the preserved PDF; the server overview, store and
execution have that same document fingerprint. The original report exactly
matches the execution record's `final_text`.

| Inspected local artefact | SHA-256 |
| --- | --- |
| Preserved PDF | `18521638bd4896a8c6bc3a0f3d69fdbffb794a9e7d40ad8622c083d5ae325cd9` |
| Original complete report | `9d97b3f652cb4efb0d1baa528ee7fc4170a1cac7f175b4e1e4a8f4a323d0ac15` |
| MCP execution JSON | `797931598751a0f3e31de19b4c149a6f4cb88dbb6193b291738371e1e45f0840` |

**Neither producing revision is confirmed.** The run metadata, execution and
inspection diagnostics do not record client/server commits or working-tree
state; the store records extractor version 34 and PyMuPDF 1.28.2, not a Git SHA.
The saved client instructions and task exactly match
[`74402b83f273a8fc6d11a3b060692510a5611678`](https://github.com/GoncaGomes/antenna-paper-extraction/commit/74402b83f273a8fc6d11a3b060692510a5611678),
committed at 12:01 on 7 October, after this execution ended at 11:20.
This establishes instruction correspondence, not a producing commit.

Both saved visual system prompts exactly match the server's
[`145808d6cf3f308c5b3b46d767d036a253df9a4e`](https://github.com/GoncaGomes/mcp-pdf-ingestion/commit/145808d6cf3f308c5b3b46d767d036a253df9a4e),
dated 6 October. That is a possible historical match and the inspected setup
reference, not confirmed executable provenance. The launch command, installed
package revision and complete historical environment were not recorded.

## Recorded execution

The version-2 execution reports `succeeded`, termination `final_answer` and
passing structural diagnostics. It spans `2026-10-07T11:13:53.075656+01:00` to
`2026-10-07T11:20:46.866207+01:00`: **413.79 seconds calculated from those
timestamps**, not a recorded overall-duration field or a performance benchmark.
`status.json` marks MCP architecture succeeded while all baseline preprocessing
and baseline architecture phases remain pending.

| Parameter | Recorded value |
| --- | --- |
| Principal requested/returned model | `qwen3.8-27b` |
| Visual requested/returned model, both inspections | `qwen3.8-27b` |
| Principal / visual / MCP session timeouts | 900 / 600 / 660 seconds |
| Agent turn budget | 80 |
| Principal / MCP retries | 0 / 0; visual diagnostics also record zero retries |
| Parallel tool calls / function-tool concurrency | `false` / 1 |
| SDK tracing | Disabled |
| Visual image settings | Longest side 1280 pixels; renderer format 1; RGB, no alpha |

No principal temperature is set in the saved effective requests. Model names
identify service deployments, not verified weight revisions.

The ledger and `accounting` confirm **six principal model requests/responses**,
**six MCP calls** and **two confirmed visual model calls**, both with successful
observations and zero unknown visual calls. MCP calls include the runtime's
startup overview; the two visual calls occur inside `get_asset`, not as extra
MCP exchanges.

| Order | Recorded MCP call and result |
| --- | --- |
| 1 | Runtime `get_paper_overview({})`: document identity, title and outline |
| 2 | Agent `read_pages(first_page=3, last_page=6)`: abstract, geometry, measurements, conclusions and captions |
| 3 | `list_assets({})`: five figure entries; `segment:2/figure:1` points to its caption on page 6 with `region_available=false` |
| 4 | `get_asset(asset_id="page:6", question=...)`: visual inspection finds captions and references only, not the requested geometry drawing |
| 5 | `read_pages(first_page=7, last_page=11)`: drawing labels on page 7 and subsequent figures |
| 6 | `get_asset(asset_id="page:7", question=...)`: visual inspection of Figure 1, retaining gap-meaning and centering uncertainty |

The questions in calls 4 and 6 include the original geometry text with its
physical-page reference. These are explicit full-page requests, not automatic
crop replacement. The final principal response ends with `finish_reason="stop"`.
The resulting report and record are at
`mcp/architecture/architecture_evidence_report.md` and
`mcp/architecture/architecture_execution.json`.

Inspection `31b94211956c457bad0425a8e906420a` covers `page:6`;
`38f41a3b7ae541988db4f4f10cb7e4d7` covers `page:7`. Both diagnostics are under
`mcp/inspections/`, with matching single-page provenance and received completions.
Images are retained under `mcp/images/<document-fingerprint>/`; the store is
`mcp/store/18521638bd4896a8/paper.sqlite`. These local files are not bundled here.

## Interpretation and reuse

The excerpt keeps every original reconstruction gap and completion assumption.
H001-H003 are model-proposed construction choices. The report's centering claim
is stronger than the inspection's approximate reading; its adopted gap meaning
also narrows an uncertainty the inspection leaves open. The model's conclusion
that its working configuration has no blocking gaps is not independent approval.
See the retained [evaluation record](../../PLAN.md#task-2---bounded-prompt-evaluation-2026-10-07).

The [current quick start](../../README.md#setup-and-usage) and
[environment example](../../.env.example) describe a fresh execution. Their
600-second principal timeout is a sample value, differing from the historical
900 seconds; the visual timeout and derived session timeout match numerically.
Recorded deployment names are not prerequisites or guarantees of availability.
Hashes, excerpt correspondence, metadata, command/configuration names and local
links were checked. Installation, server startup and live model access were not
retested, so full reproducibility and scientific accuracy remain unverified.
