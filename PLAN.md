# MCP Architecture Experiment Plan

This plan applies only to `exp/architecture-mcp`. The approved design and current
comparison baseline are described in [README.md](README.md). Implement one task
at a time; future file names are indicative until the relevant implementation
has been inspected. Results extraction, canonicalization, final consumer JSON
generation and general pipeline orchestration are outside this branch's scope.

## MCP-01 - Connect a preserved run to the external MCP

- **Status:** implemented and tested;
- **Objective:** Verify a run-bound PDF server connection without LLM calls.
- **Narrow scope:** Add a small explicitly invoked connection probe with a
  current caller. Read and verify the preserved PDF, launch the configured
  external server through stdio, pass its document/run-directory environment,
  discover the six tools and call `get_paper_overview` to compare document
  identity.
- **Acceptance checks:** Matching and mismatching document identity, discovery
  of the six documented tools, process cleanup on success/failure, Windows
  paths with spaces and zero LLM calls.
- **Implemented:** `scripts/probe_mcp_connection.py` checks the strict run
  manifest/status, contained preserved PDF and actual SHA-256 before starting
  the external executable with caller-supplied paths. It uses Agents SDK stdio,
  a 600-second session timeout, no retries, a credential-free child environment,
  exact six-tool discovery and one empty-argument overview call. It compares
  validated fingerprints without changing stored identities, and leaves run
  lifecycle files unchanged. No models, visual requests or execution trace.
- **Verification (2026-10-01):** Scripted connections and the installed SDK's
  in-memory transport cover identity/tool/response failures, paths with spaces,
  safe environment/output and cleanup on success, failure and cancellation
  during startup or overview. Symlink escape tests are present but skipped when
  Windows does not grant symlink creation. One explicit real connection passed
  on an existing run, created the expected store, made zero model calls and
  preserved manifest/status bytes; the external repository remained unchanged.
  Repository lint/format checks passed. The broader local suite has seven
  unrelated failures: CLI DPI/scale expectations and conversion temperature
  expectations differ from existing defaults. These remain outside MCP-01.
- **Suggested commit:** `feat(mcp): verify a run-bound PDF server connection`

## MCP-02 - Record MCP calls incrementally

- **Status:** implemented and tested;
- **Objective:** Make each probe tool exchange inspectable as it occurs.
- **Narrow scope:** Extend the connection probe with ordered records of
  arguments, identifiers, complete responses, timing and failures. Persist
  before and after calls using established atomic persistence; exclude
  credentials and image payloads.
- **Acceptance checks:** Ordered, linked records survive partial execution and
  failed calls; persistence occurs before continuation, and credentials/image
  payloads are absent.
- **Implemented:** The probe creates a fresh
  `mcp/probe_connection_<unique-id>.json` after local preflight and prints its
  path. `QuietStdioServer.call_tool` preserves the installed public signature,
  including `meta`, and atomically saves locally identified, ordered calls
  before execution and complete aliased responses before returning to identity
  validation. The existing writer is reused. Trace identity, Europe/Lisbon
  timestamps, elapsed tool durations and controlled diagnostics distinguish
  call outcomes from overall success after cleanup. Known credential values
  from credential-related environment entries and image payloads are excluded;
  ordinary evidence and response structure remain. Required persistence failures
  stop execution and retain the last valid trace; diagnostic write failures
  preserve the original error/cancellation. Run lifecycle files, model behaviour,
  external server settings and dependencies are unchanged.
- **Verification (2026-10-01):** Focused scripted tests verify persistence before
  tool execution and return, extra overview fields, two distinct linked calls,
  separate invocations, failure/cancellation cleanup through the installed SDK's
  in-memory transport, initial/call/result/final write failures, last-valid-trace
  preservation and credential/image exclusions. Manifest/status byte and zero
  model checks remain. Focused tests: 52 passed, three Windows symlink skips.
  Full local suite: 333 passed, six symlink skips and the same seven unrelated
  CLI DPI/scale and conversion temperature baseline failures recorded in MCP-01.
  Repository lint, format and `git diff --check` passed. No real server, model
  inference, dependency synchronization or MCP-03 work.
- **Suggested commit:** `feat(tracing): persist MCP calls and responses incrementally`

## MCP-03 - Run a narrow sequential agent with model tracing

- **Status:** implemented and tested; owner acceptance pending
- **Objective:** Exercise iterative acquisition on a small geometry-evidence task.
- **Narrow scope:** Extend the probe using the Agents SDK, expose all six tools,
  enforce sequential execution, disable automatic retries and apply configurable
  finite `max_turns`. Persist model requests and raw received responses before
  interpretation; record final output, usage when available and termination
  reason.
- **Acceptance checks:** Scripted clients exercise multiple tool rounds, budget
  exhaustion and failures; traces survive, execution remains sequential and
  retries are absent. A live probe is explicit.
- **Implemented:** `--agent-model` explicitly selects the narrow geometry task;
  `--max-turns` is a positive integer, default 8. Initialized runs need no other
  baseline artefacts. The existing PDF preflight, recorded stdio server and
  atomic writer are reused; shared trace code now lives in `mcp_agent.py`.
  Agent mode loads `.env` before credential redaction, preserving process
  precedence, requires SKYNET endpoint settings and forwards only explicit
  visual settings. Connection-only mode retains zero model calls and its
  credential-free child environment. OpenAI-compatible Chat Completions uses
  600-second client/session timeouts, zero client/SDK/MCP retries, disabled SDK
  tracing and both provider parallel-call disabling and SDK tool concurrency one.
  The public `chat.completions.create` adapter, including `with_options` clones,
  saves effective requests before dispatch and complete raw responses before
  normalization/validation. Fresh `probe_agent_<unique-id>.json` traces retain
  ordered events, linked local model/MCP IDs and SDK tool-call IDs, timings,
  usage/coverage, final text and termination after cleanup. Truncation, budget
  exhaustion and operational failures retain evidence without success; required
  write failures stop continuation and preserve the last valid trace. Headers,
  known credentials and image payloads are excluded. Tool errors remain distinct
  from an honest final answer reporting insufficient evidence. Manifest/status
  bytes, the external MCP repository and MCP-04 scope remain unchanged.
- **Verification (2026-10-01):** Installed Agents SDK 0.22.2 and OpenAI 3.6.0
  boundary tests use scripted Chat Completions and in-memory MCP transport with
  the real Runner. They cover multiple rounds, all six advertised tools, multiple
  same-response tool requests executing sequentially, effective pre-dispatch
  requests, raw responses before tool execution/interpretation, truncation,
  budget exhaustion, model/transport errors, cancellation and cleanup, required
  write failures preventing subsequent tools/models, `.env` redaction and
  precedence, missing visual configuration, trace preservation and unchanged
  lifecycle bytes. Focused suite: 77 passed, three Windows symlink skips. Full
  local suite: 363 passed, six symlink skips and the same seven unrelated CLI
  DPI/scale and conversion temperature baseline failures. Lint and formatting
  passed. `git diff --check` reports only two pre-existing trailing spaces in the
  owner's MCP-01/MCP-02 status edits, preserved as requested; MCP-03 changes pass
  whitespace checks. No live inference or dependency synchronization was run.
- **Owner-requested test alignment (2026-10-01):** Updated CLI and conversion
  test expectations to the existing 300 DPI, scale 4.0 and temperature 0.2 defaults.
  Focused tests: 44 passed. Full local suite: 370 passed, six symlink skips,
  no failures. Runtime defaults are unchanged; lint and formatting passed.
- **Suggested commit:** `feat(mcp): run a sequential evidence acquisition agent`

## MCP-04 - Link visual observations to diagnostics and counts

- **Status:** implemented and tested
- **Objective:** Make visual evidence and actual inference counts traceable.
- **Narrow scope:** Extend the running probe's trace with visual statuses,
  inspection IDs, coverage and diagnostic references. Distinguish tool calls,
  principal-model requests and visual-model requests. Do not change the MCP
  server or duplicate its image/diagnostic files.
- **Acceptance checks:** Question-free access, successful inspection and
  unavailable evidence retain the correct diagnostics and counts. A `get_asset`
  call or question is not automatically counted as a successful model request;
  unavailable/configuration failures may make zero visual-model calls.
- **Implemented:** The existing call path persists the raw MCP response before
  enriching `get_asset` records with returned visual provenance and run-relative
  inspection references. Strict local validation checks the server's diagnostic
  ID/path and inspection/document/asset/question/outcome identity, without copying
  diagnostics or modifying server files. Separate visual accounting retains
  confirmed calls, unknown occurrence, successful observations and reported usage;
  repeated IDs are deduplicated and inconsistent reuse is flagged. No dispatch
  marker exists in the external diagnostic contract, so ambiguous failures remain
  unknown. Principal counts/usage, execution order and required-write guarantees
  are preserved; extraction instructions and lifecycle/report outputs are unchanged.
- **Verification (2026-10-01):** Scripted SDK/MCP tests and synthetic referenced
  diagnostics cover question-free access, success and partial coverage, pre-model
  failures, unusable received completions, ambiguous dispatch, broken/mismatched
  diagnostics, invalid IDs/escaping symlinks, ID reuse and independent inspections
  of reused images. Tests verify raw-before-enrichment and enriched-before-SDK
  persistence, required-write failures stopping continuation, redaction and
  unchanged principal counters/usage. Focused suite: 124 passed, five Windows
  symlink skips. Full local suite: 417 passed, eight symlink skips, no failures.
  Lint, formatting and `git diff --check` passed. No live inference or external
  server execution was run; the external repository was only read.
- **Suggested commit:** `feat(tracing): link MCP visual inspection diagnostics`

## MCP-05 - Adapt architecture instructions to MCP evidence

- **Status:** implemented and tested
- **Objective:** Exercise the existing scientific/report conventions through MCP.
- **Narrow scope:** Adapt instructions for iterative acquisition, pagination,
  textual search, exact asset IDs and explicit physical-page inspection.
  Preserve report sections and claim conventions; distinguish original paper
  content from learned visual observations and define traceable evidence
  references without redesigning the final schema. Explicit H-series completion
  assumptions may supply missing reconstruction details, with origin,
  justification and uncertainty, separately from supported A-series claims.
- **Acceptance checks:** Exercise the instructions through the existing agent
  probe; verify report conventions, paginated acquisition and evidence links
  that distinguish textual sources from visual diagnostics.
- **Implemented:** `architecture_report.py` defines the agreed independent MCP
  instructions and task, reusing `REPORT_SECTIONS` without changing the baseline
  prompt or structural validator. The probe-only `--agent-task` selector defaults
  to `geometry`; `architecture` requires an explicit principal model before any
  startup or trace creation. One selected instruction/task pair is persisted and
  used by the Agent and Runner, with task identity in trace configuration.
  The configurable turn budget still defaults to 8. Report text stays unchanged
  in the probe's `final_text`; there is no runtime report rejection, scientific
  validation, automatic correction or new final schema. Existing sequential
  execution, zero retries, timeouts, tracing and MCP-04 provenance are preserved.
- **Verification (2026-10-01):** Scripted Chat Completions and in-memory MCP transport use the
  installed SDK Runner to exercise selection/persistence, model-free connection
  mode, pre-startup model requirements, pagination with unchanged cursors and
  original query/filter/section context, exact catalog IDs, deterministic assets,
  linked partial visual inspection and explicit unavailable page inspection.
  Representative reports with A-series claims and an H001 table, no assumptions,
  or unavailable inspection pass the unchanged structural validator and remain
  unmodified in `final_text`. Turn exhaustion retains partial traces and cleanup;
  manifest/status bytes remain unchanged and no separate architecture files are
  created. Existing regression tests cover termination, redaction and required
  persistence boundaries. Focused probe/report suite: 148 passed, five Windows
  symlink skips. Full local suite: 426 passed, eight symlink skips, no failures.
  Ruff lint, formatting checks and `git diff --check` passed, using the existing
  environment with `uv run --no-sync`.
- **Limitations and deferred work:** Scripted reports demonstrate integration and
  structural compatibility, not live policy compliance or correct geometry.
  Live scientific evaluation remains pending. Separate report/execution artefacts
  remain MCP-06; lifecycle, production CLI and final JSON are outside this task.
  No live inference, real server startup, dependency synchronization/upgrades or
  external repository changes were performed. No correction to the agreed
  runtime wording was needed.
- **Suggested commit:** `feat(architecture): define MCP evidence acquisition instructions`

## MCP-06 - Produce the architecture report and execution artefact

- **Status:** implemented (local scripted verification; scientific acceptance pending)
- **Objective:** Turn the exercised MCP agent into architecture-report execution.
- **Narrow scope:** Persist `architecture_evidence_report.md` and
  `architecture_execution.json`, retaining diagnostic structural validation and
  raw responses. Reject silent output replacement. Do not require NuExtract3
  conversion or Docling figure extraction.
- **Acceptance checks:** Scripted clients verify report generation, structural
  diagnostics, existing-output rejection and failure preservation from an
  initialized run without converted Markdown or baseline figure artefacts.
- **Implemented:** The development-only `--persist-architecture` probe flag
  requires the architecture task and an explicit nonblank model. After local
  preflight, exclusive reservation of `mcp/architecture/` rejects every existing
  entry, including empty directories and broken symlinks. `ProbeTrace` starts
  directly in `mcp/architecture/architecture_execution.json`, preserving the same
  incremental model/MCP records, raw responses, counts and relative diagnostics
  without a duplicate probe JSON. After successful execution and cleanup,
  structural diagnostics are saved before atomic publication of the redacted
  final text as `mcp/architecture/architecture_evidence_report.md`. Non-empty
  structurally invalid reports are published diagnostically; no scientific
  validation or repair is performed. Success requires durable publication
  metadata. Failures preserve the output reservation and last valid trace; final
  metadata failure attempts to remove only this invocation's published report.
- **Verification (2026-10-02):** Scripted Chat Completions, in-memory MCP
  transport and the installed SDK Runner cover valid/invalid report publication,
  unchanged H-series content, relative inspection references, initial null
  metadata, preflight before reservation, existing-output rejection, exclusive
  reservation races, preserved MCP/baseline data and failure retention. Model,
  tool, unusable/truncated completion, budget, cancellation, startup, discovery,
  identity, cleanup and required-write failures preserve evidence without durable
  report success. Final metadata failure removes only the new report when
  possible; removal/diagnostic failures return failure and retain the last valid
  JSON. Manifest/status bytes remain unchanged. Focused probe/report/persistence
  suite: 198 passed, eight Windows symlink skips. Full local suite: 462 passed,
  11 Windows symlink skips. Ruff lint, formatting and `git diff --check` pass.
  Representative synthetic reports and execution metadata were inspected;
  Markdown equals persisted `final_text`, including redaction.
- **Boundaries:** No rendering, conversion or baseline figure prerequisites;
  existing MCP and baseline architecture data are permitted. Default budget 8,
  instructions, six tools, sequential execution, zero retries and timeouts remain
  unchanged. Manifest/status and the external repository are untouched.
  Lifecycle and production CLI remain MCP-07/MCP-08; live scientific review is
  pending. No live inference, real server execution or dependency synchronization
  is part of this increment.
- **Suggested commit:** `feat(architecture): generate reports from MCP evidence`

## MCP-07 - Integrate architecture execution with run lifecycle

- **Status:** implemented
- **Objective:** Track the MCP architecture path using existing run status.
- **Narrow scope:** Allow execution from an initialized run and integrate the
  existing status mechanism locally to this path. Do not mark unexecuted
  baseline phases as succeeded or build a workflow engine.
- **Acceptance checks:** Success, failure, cancellation and turn-budget
  exhaustion produce inspectable lifecycle outcomes; unrelated phase states
  and prior artefacts are preserved.
- **Implemented:** Added independent `architecture_mcp_extraction` transitions
  requiring only successful source preservation to start. Legacy statuses default
  it to pending without rewriting or changing schema version. Existing rendering,
  conversion, figure and baseline architecture transitions preserve this phase.
  Baseline `architecture_extraction` still requires successful figures and retains
  its own artefacts under `architecture/`; both approaches can run sequentially in
  either order within one run.
- **Persisted probe:** Only `--persist-architecture` updates the MCP phase.
  Non-pending states and invalid configuration/output preflight are rejected before
  reservation or external calls. The phase starts after initial execution JSON
  persistence and before server startup; success follows durable publication and
  execution metadata under `mcp/architecture/`. Failure and budget exhaustion mark
  it failed; cancellation is failed globally and cancelled in the execution trace.
  Probes without persistence remain status-neutral. There is no automatic reset,
  retry or resume; the production CLI remains MCP-08.
- **Persistence boundaries:** Execution/status writes remain separately atomic.
  Both failure updates are attempted independently with controlled diagnostics.
  A failed global success write returns failure and attempts removal of only this
  invocation's report, clears available publication metadata and attempts global
  failure. Raw responses and the reserved directory remain. Unavailable writers
  can leave the last valid phase/trace running; failed removal can leave a report.
- **Verification (2026-10-02):** Scripted SDK/model and in-memory MCP tests cover
  independent success/failure transitions, legacy defaults without rewriting,
  upstream/baseline preservation, both execution orders, cancellation, budget
  exhaustion, structurally invalid report success, preflight/output neutrality and
  start/success/failure status-write errors. Failure tests verify retained raw
  responses, controlled diagnostics, independent failure updates, publication
  rollback and failed rollback without touching baseline reports. Affected files
  (`test_runs.py`, `test_mcp_connection.py`, `test_architecture.py`): 223 passed,
  eight Windows symlink skips. Full local suite: 474 passed, 11 Windows symlink
  skips. Ruff lint/format checks and `git diff --check` pass. All commands used the
  existing environment with `uv run --no-sync`; no live inference, real external
  server execution or dependency synchronization occurred.
- **Suggested commit:** `feat(runs): track MCP architecture extraction lifecycle`

## MCP-08 - Expose the experimental CLI command

- **Status:** implemented; local working-tree diff ready for owner review.
- **Objective:** Make the existing MCP architecture path explicitly invocable.
- **Implemented:** `antenna-extract extract-architecture-mcp RUN_DIR
  [--max-turns N]` always selects architecture, publishes the report and tracks
  `architecture_mcp_extraction`; the positive budget defaults to 80. The baseline
  command and lifecycle are unchanged.
- **Runtime:** `mcp_runtime.py` owns the moved connection/agent orchestration,
  identity validation, transport, recording and publication/lifecycle handling.
  Both callers use it directly. The development script keeps its parser,
  explicit server/model arguments, budget 8, timeout defaults and controlled
  invocation diagnostics; callers load `.env`, with process values taking
  precedence.
- **Configuration:** The MCP CLI reuses principal architecture settings and
  additionally requires visual model/timeout and existing executable/cwd paths.
  Validation precedes reservation, lifecycle start and external calls. The
  principal timeout reaches `RecordedOpenAI`; visual settings reach the child;
  session/tool timeout is visual timeout plus 60 seconds. All effective timeouts
  are recorded. The executable launches directly without shell parsing; document
  binding comes from the verified run. Credentials remain excluded from settings
  repr and uncontrolled third-party errors/logs are suppressed.
- **Acceptance evidence:** Existing scripted SDK, lifecycle, publication and
  failure tests now patch the package runtime; parser tests remain against the
  development script. Compact CLI coverage verifies default/explicit budgets,
  settings/path validation, `.env` precedence, success/failure/cancellation and
  logging restoration. One scripted CLI/runtime execution verifies all three
  timeout settings, verified document binding and report publication. Existing
  baseline CLI coverage still passes. README documents configuration, command,
  output paths, independent phases, rejection behaviour and exit codes.
- **Verification:** `uv run --no-sync pytest tests/test_architecture_cli.py
  tests/test_mcp_connection.py tests/test_cli.py -q`: 246 passed, 8 skipped.
  `uv run --no-sync pytest -q`: 493 passed, 11 skipped. Skips require symlink
  creation unavailable on this Windows environment. `uv run --no-sync ruff
  check .`, `uv run --no-sync ruff format --check .` and `git diff --check`
  pass. CLI `--help` confirms the initialized-run prerequisite and default 80.
  All verification used the existing environment without dependency sync.
- **Limitations:** No live inference, real external server execution or dependency
  synchronization. Operational success remains distinct from scientific
  acceptance. No retry, resume, overwrite or recovery; independently atomic
  trace/status persistence and publication rollback retain existing limitations.
  Live pilot evaluation remains MCP-09.
- **Suggested commit:** `feat(cli): expose MCP architecture extraction`

## MCP-09 - Review one pilot paper

- **Status:** pending
- **Objective:** Assess the MCP report against one known source paper.
- **Narrow scope:** Run the pilot explicitly, follow critical claims through
  tool responses and visual diagnostics, and record concise findings,
  configuration, limitations and execution metrics in the active documents.
  Correct discovered defects in separate focused commits before continuing.
- **Acceptance checks:** Critical claims resolve against the PDF and diagnostics;
  findings distinguish operational success from scientific acceptance, identify
  limitations and record configuration and metrics.
- **Suggested commit:** `docs(architecture): record MCP pilot findings`

## MCP-10 - Compare the six existing cases

- **Status:** pending
- **Objective:** Decide whether to adopt or refine the MCP path using comparison
  evidence.
- **Narrow scope:** Freeze the post-pilot configuration, define critical
  assertions for the six existing cases using PDF hashes and permitted source
  references, then run sequentially and compare with previous reports. Record
  the adoption/refinement decision and update current status in the active
  documents.
- **Acceptance checks:** Review omissions, unsupported claims, dimension
  associations, provenance, calls, tokens when available and latency per case;
  record the frozen configuration and decision. Do not commit PDFs, credentials
  or large run artefacts.
- **Suggested commit:** `test(architecture): document the MCP comparison cases`
