# MCP Architecture Experiment Plan

This plan applies only to `exp/architecture-mcp`. The approved design and current
comparison baseline are described in [README.md](README.md). Implement one task
at a time; future file names are indicative until the relevant implementation
has been inspected. Results extraction, canonicalization, final consumer JSON
generation and general pipeline orchestration are outside this branch's scope.

## MCP-01 - Connect a preserved run to the external MCP

- **Status:** implemented and tested; owner acceptance pending
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

- **Status:** pending
- **Objective:** Make each probe tool exchange inspectable as it occurs.
- **Narrow scope:** Extend the connection probe with ordered records of
  arguments, identifiers, complete responses, timing and failures. Persist
  before and after calls using established atomic persistence; exclude
  credentials and image payloads.
- **Acceptance checks:** Ordered, linked records survive partial execution and
  failed calls; persistence occurs before continuation, and credentials/image
  payloads are absent.
- **Suggested commit:** `feat(tracing): persist MCP calls and responses incrementally`

## MCP-03 - Run a narrow sequential agent with model tracing

- **Status:** pending
- **Objective:** Exercise iterative acquisition on a small geometry-evidence task.
- **Narrow scope:** Extend the probe using the Agents SDK, expose all six tools,
  enforce sequential execution, disable automatic retries and apply configurable
  finite `max_turns`. Persist model requests and raw received responses before
  interpretation; record final output, usage when available and termination
  reason.
- **Acceptance checks:** Scripted clients exercise multiple tool rounds, budget
  exhaustion and failures; traces survive, execution remains sequential and
  retries are absent. A live probe is explicit.
- **Suggested commit:** `feat(mcp): run a sequential evidence acquisition agent`

## MCP-04 - Link visual observations to diagnostics and counts

- **Status:** pending
- **Objective:** Make visual evidence and actual inference counts traceable.
- **Narrow scope:** Extend the running probe's trace with visual statuses,
  inspection IDs, coverage and diagnostic references. Distinguish tool calls,
  principal-model requests and visual-model requests. Do not change the MCP
  server or duplicate its image/diagnostic files.
- **Acceptance checks:** Question-free access, successful inspection and
  unavailable evidence retain the correct diagnostics and counts. A `get_asset`
  call or question is not automatically counted as a successful model request;
  unavailable/configuration failures may make zero visual-model calls.
- **Suggested commit:** `feat(tracing): link MCP visual inspection diagnostics`

## MCP-05 - Adapt architecture instructions to MCP evidence

- **Status:** pending
- **Objective:** Exercise the existing scientific/report conventions through MCP.
- **Narrow scope:** Adapt instructions for iterative acquisition, pagination,
  textual search, exact asset IDs and explicit physical-page inspection.
  Preserve report sections and claim conventions; distinguish original paper
  content from learned visual observations and define traceable evidence
  references without redesigning the final schema.
- **Acceptance checks:** Exercise the instructions through the existing agent
  probe; verify report conventions, paginated acquisition and evidence links
  that distinguish textual sources from visual diagnostics.
- **Suggested commit:** `feat(architecture): define MCP evidence acquisition instructions`

## MCP-06 - Produce the architecture report and execution artefact

- **Status:** pending
- **Objective:** Turn the exercised MCP agent into architecture-report execution.
- **Narrow scope:** Persist `architecture_evidence_report.md` and
  `architecture_execution.json`, retaining diagnostic structural validation and
  raw responses. Reject silent output replacement. Do not require NuExtract3
  conversion or Docling figure extraction.
- **Acceptance checks:** Scripted clients verify report generation, structural
  diagnostics, existing-output rejection and failure preservation from an
  initialized run without converted Markdown or baseline figure artefacts.
- **Suggested commit:** `feat(architecture): generate reports from MCP evidence`

## MCP-07 - Integrate architecture execution with run lifecycle

- **Status:** pending
- **Objective:** Track the MCP architecture path using existing run status.
- **Narrow scope:** Allow execution from an initialized run and integrate the
  existing status mechanism locally to this path. Do not mark unexecuted
  baseline phases as succeeded or build a workflow engine.
- **Acceptance checks:** Success, failure, cancellation and turn-budget
  exhaustion produce inspectable lifecycle outcomes; unrelated phase states
  and prior artefacts are preserved.
- **Suggested commit:** `feat(runs): track MCP architecture extraction lifecycle`

## MCP-08 - Expose the experimental CLI command

- **Status:** pending
- **Objective:** Make the existing MCP architecture path explicitly invocable.
- **Narrow scope:** Expose an experimental CLI command with server/model
  settings and `max_turns`. Document the actual implemented configuration and
  commands; retain the baseline command and reuse orchestration outside the CLI.
- **Acceptance checks:** Verify CLI success/error reporting, settings and budget
  validation, baseline retention and documentation matching the implemented
  interface, without duplicated orchestration.
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
