# Baseline execution trace summary

This summary accompanies the [report excerpt](architecture-report.md) from
`run_20260921T162507+0100_16771d1e`. It uses only the baseline artefacts in that
run. MCP artefacts added to the same run later are excluded.

## Provenance

The source is Fernandez et al., *Design of a Deployable Helix Antenna at L-Band
for a 1-Unit CubeSat: From Theoretical Analysis to Flight Model Results*,
[DOI: 10.3390/s22103633](https://doi.org/10.3390/s22103633).
`manifest.json` names `input/006_deployable_helix_cubesat.pdf`; its stored SHA-256
matches the preserved PDF's bytes. The baseline execution carries the same
document identity, and its `final_text` exactly matches the original report.

The following SHA-256 values identify the inspected local artefacts. The PDF
and full execution JSON are not published here.

| Artefact | SHA-256 |
| --- | --- |
| Preserved PDF | `b4f2774e9e964729eb2c3dc6346f56d81aac4dc1e192ee0452f56328bcb5658d` |
| Original complete report | `8a7c309e5896fb0017b9f6801922f6dfe4597a042b2d38adfe00f595d2893510` |
| Baseline execution JSON | `9e0ca9fc5e350a58185436a9c3b5083608706f4936d358d32d960131a2d199a7` |

**No producing commit is confirmed.** The inspected manifest, status, page and
figure manifests, conversion responses/traces and baseline execution JSON do
not record a Git revision or working-tree state. The saved combined architecture
instructions exactly match those built with `max_assets=6` from
[`fcf1041aa36425e69836160ad9face30980c363e`](https://github.com/GoncaGomes/antenna-paper-extraction/commit/fcf1041aa36425e69836160ad9face30980c363e)
and the baseline merge
[`e6d4fec92352d295ad200df4332c06ca286883d5`](https://github.com/GoncaGomes/antenna-paper-extraction/commit/e6d4fec92352d295ad200df4332c06ca286883d5).
Both commits are dated 23 September, after the recorded execution on
21 September. This confirms prompt correspondence only, not the checkout that
produced the output. It does not establish the conversion prompt or dependency
environment used in that run.

## Recorded execution

`status.json` records success for the five baseline stages. The architecture
record spans `2026-09-21T16:31:04.002822+01:00` to
`2026-09-21T16:35:37.652175+01:00`, with a recorded duration of **273.65 seconds**.
This is architecture-stage elapsed time, not total pipeline time or a benchmark.

| Stage | Evidence and recorded settings |
| --- | --- |
| Source preservation | PDF filename, size and identity in `manifest.json` |
| Page rendering | 19 physical pages; 300 DPI; PDFium 5.13.0 in `pages/pages.json` |
| Document conversion | Three numbered batch traces and responses identify `nuextract3`; temperature 0.2, `mode="markdown"`, `enable_thinking=false`; HTTP 200 and `finish_reason="stop"` in each trace |
| Figure preparation | Docling 2.126.0 / core 2.95.0, image scale 3.0; PDFium crop scale 4.0, margin 2.0 points in `figures/manifest.json` |
| Architecture extraction | Requested and returned model identifier `qwen3.8-27b`; client timeout `600.0`, zero retries, maximum six assets and two turns in the execution record |

The figure manifest contains 24 entries: 16 have crop paths and eight are
unresolved. Successful preparation therefore did not mean every entry had an
image. The three requested crops were recorded as available.

The architecture event sequence is:

1. Model request and response, ending with `finish_reason="tool_calls"`.
2. `get_visual_assets` with `asset_ids=["figure_1", "figure_12", "figure_14"]`.
   The result records success and availability for all three assets. The figure
   manifest associates them with physical PDF pages 4, 14 and 15 respectively.
3. A second model request and response, ending with `finish_reason="stop"`,
   producing the Markdown report.
4. Final text, passing structural diagnostics and successful state are present
   in `architecture/architecture_execution.json`; the report is present at
   `architecture/architecture_evidence_report.md`.

The ledger confirms two model requests/responses and one tool invocation/result.
It does not record an architecture temperature, the conversion client timeout,
the original CLI command line or the full environment. No values or historical
launch command have been reconstructed for those gaps.

## Interpretation and reuse

These are recorded model identifiers, not verified weight revisions. Structural
checks passed; source fidelity and scientific validity have not been independently
validated. The excerpt retains all original reconstruction gaps, including
unconfirmed geometry continuity, unidentified feed hardware and missing
deployment dimensions. Converted Markdown also contains generated image
descriptions; those are not original paper statements or proof of image access.

The [current quick start](../../README.md#setup-and-usage) describes a fresh run
using the baseline implementation and generic service configuration. Historical
model identifiers here are not prerequisites or guarantees of availability.
The [environment example](../../.env.example) supplies sample timeouts, not a
recovered historical configuration. Commands, configuration names, hashes and
excerpt correspondence were checked locally. Installation, service access and
a new execution were not tested, so exact replay has not been established.
