# Antenna Extraction v3 - Implementation Roadmap

- **Status:** active execution plan
- **Version:** 3.1-draft
- **Date:** 2026-09-04
- **Architectural authority:** `00_ARCHITECTURE_V3.md`
- **Current implementation phase:** Phase 3 - Bounded asset inspection

## 1. Purpose

This roadmap turns the v3 architectural decision into a controlled development
sequence. It is designed for:

- one ChatGPT Project chat per phase;
- one short-lived Git branch per phase;
- several small commits inside a phase when necessary;
- one implementation and review cycle per commit;
- manual approval and commit control by the repository owner;
- enough separation to understand and learn the code as it is introduced.

The roadmap is intentionally detailed about outcomes, tests, evidence, and
completion gates. It is intentionally **not** a pre-generated codebase design.
Exact modules, classes, functions, and schema fields are chosen only when their
phase begins and the current repository has been inspected.

## 2. Authority and conflict rules

Use the following order when sources disagree:

1. The code and tests merged into the new repository's `main` branch describe
   what is currently implemented.
2. `00_ARCHITECTURE_V3.md` describes the intended system and fixed
   architectural decisions.
3. This roadmap describes sequencing, current phase, and implementation gates.
4. A future benchmark-requirements document describes scientific acceptance.
5. Chats, old plans, and the v2 repository provide supporting evidence but are
   not normative for v3.

Never hide a contradiction. If executable behaviour differs from the
architecture, stop and decide whether to change the code or amend the
architecture. Record the decision explicitly.

The old `implementation_plan(3).md` and the branch
`feat/antenna-pipeline-v2` remain historical material. They must not be copied
into the v3 Project Sources as active instructions.

## 3. Repository strategy

### 3.1 Start from a new repository

Create a new repository for v3 rather than transforming the long-lived v2
feature branch in place. The old repository remains available as:

- a failure and regression baseline;
- a source of individual proven utilities;
- an audit record of why the architecture changed;
- material for the dissertation or technical report.

Do not delete the v2 repository or its chats merely to make the new project
look clean.

### 3.2 Port capabilities, not the old tree

Code is copied from v2 only after the current phase proves that the capability
is needed. Candidate capabilities that may be ported and simplified include:

- safe input PDF copy and hashing;
- run identifiers and provenance;
- atomic artefact writes;
- page rendering in source order;
- secret redaction and inspectable failure records;
- a minimal OpenAI-compatible client;
- request, response, latency, and usage tracing;
- dependency injection used by local tests.

Do not port the old repository wholesale. In particular, do not port as active
v3 code:

- the monolithic `PaperExtraction` contract;
- the large architecture schema created for direct model authorship;
- the prompt that asks one model to perform several scientific roles;
- old RAG, lexical retrieval, or evidence-index paths;
- the old canonicalization tool loop;
- a 20-phase orchestrator or per-design workflow graph;
- page classifiers or relevance ranking;
- automatic fallback, repair, or review calls;
- placeholder scripts, empty directories, unused configuration, or future
  adapters.

### 3.3 Keep `main` stable

For every phase:

1. Start from the latest accepted `main`.
2. Create the phase branch named in this roadmap.
3. Implement one small commit at a time.
4. Review the diff and run the relevant gates before each manual commit.
5. Complete the full phase gate.
6. Merge the phase branch into `main`.
7. Delete the short-lived branch after the merge.
8. Create the next branch from the updated `main`.

Tags preserve important milestones. Long-lived feature branches should not be
used as substitutes for tags or documentation.

### 3.4 No placeholder policy

Do not create a directory, module, class, script, command, schema, or interface
only because a later phase may need it. A new artefact must have:

- a current caller or consumer;
- a test or verification path;
- a clear reason for existing in the current phase.

Do not add `.gitkeep` files to speculative trees. The repository grows from
working vertical slices.

## 4. Chat, branch, and phase map

| Phase | Chat title | Suggested branch | Result merged to `main` |
| ---: | --- | --- | --- |
| 0 | `00 - Foundation and project rules` | `chore/foundation` | Clean, governed development baseline |
| 1 | `01 - Run lifecycle and source preservation` | `feat/run-lifecycle` | Deterministic run and ordered page artefacts |
| 2 | `02 - NuExtract3 DocumentPackage` | `feat/document-package` | Combined Markdown, ordered page assets, and per-batch diagnostics |
| 3 | `03 - Bounded asset inspection` | `feat/asset-inspection` | Consumer-specific package validation, safe asset resolution, and one-round interaction control |
| 4 | `04 - Architecture agent` | `feat/architecture-agent` | `architecture_evidence_report.md` |
| 5 | `05 - Results agent` | `feat/results-agent` | `results_evidence_report.md` |
| 6 | `06 - Canonicalization and final contracts` | `feat/canonicalization` | Two validated final JSON documents |
| 7 | `07 - End-to-end runner` | `feat/end-to-end` | One sequential end-to-end command |
| 8 | `08 - Scientific benchmark and baseline` | `test/scientific-benchmark` | Measured baseline and release tag recommendation |

One phase is one principal discussion boundary. If a phase proves too large,
split the implementation work into commits inside the same chat before
creating another architectural phase. If chat context becomes genuinely
unmanageable, use a clearly named continuation such as `04B`, carry forward
the handoff record, and remain on the same branch and phase.

## 5. Rules for every phase chat

At the start of every phase chat:

1. Name the repository, branch, phase, and intended first commit.
2. Ask the chat to read both v3 source documents completely.
3. Inspect the actual branch, current HEAD, working tree, imports, tests, and
   relevant artefacts.
4. Confirm which earlier phase gates are present in code rather than assuming
   roadmap status is current.
5. Discuss unresolved decisions that belong to this phase.
6. Agree on the smallest coherent commit before editing.
7. State which files are expected to change and why.
8. State the tests and human evidence needed to accept the commit.

During implementation:

- explanations and discussion are in European Portuguese;
- code, identifiers, comments where appropriate, commit messages, and Codex
  implementation prompts are in English;
- Codex does not commit automatically;
- no destructive Git command is used to clean the workspace;
- unrelated user changes are preserved;
- no work from a future phase is pulled forward for convenience;
- the pipeline remains sequential;
- remote model commands are explicit and opt-in;
- one commit is reviewed before the next begins.

At the end of every commit:

1. Inspect the diff.
2. Run directly affected tests.
3. Run the relevant broader local suite.
4. Run lint and static checks used by the repository.
5. Inspect representative generated artefacts when applicable.
6. Compare the result with the commit gate.
7. Record limitations and deferred work.
8. Commit manually only after acceptance.

## 6. Commit design rules

A good commit in this project:

- introduces one coherent capability;
- includes its tests in the same commit;
- leaves the branch runnable and understandable;
- does not mix a large refactor with new behaviour;
- does not add unused abstractions;
- does not change model prompts, contracts, and orchestration simultaneously
  unless the capability cannot be tested otherwise;
- has a message that describes observable behaviour.

Suggested commit messages in this roadmap are starting points, not commands.
Change them when the actual diff has a more accurate scope.

## 7. Global engineering constraints

These constraints apply to all phases:

- one paper per run;
- synchronous and sequential model calls;
- no parallelism;
- no semantic RAG, embeddings, or vector database;
- no automatic retry, fallback model, repair model, or reviewer model;
- no hidden model inside the asset tool;
- no unrestricted agent loop;
- at most one asset-tool round per scientific agent;
- no solver-specific commands;
- no scientific decisions in deterministic code;
- no table or equation crops;
- complete Markdown is the initial scientific-agent context;
- raw model output is persisted before strict parsing;
- failures and partial successes remain inspectable;
- exact source values and units are not silently normalized away;
- missing information is explicit;
- tests use fake clients by default and never contact the institutional server
  unless an opt-in command is deliberately run.

## 8. Phase 0 - foundation and project rules

- **Chat:** `00 - Foundation and project rules`
- **Branch:** `chore/foundation`
- **Model calls:** none
- **Status:** Completed

### 8.1 Objective

Create a new, minimal repository with unambiguous authority, reproducible local
tooling, and no inherited pipeline implementation.

### 8.2 Questions to decide in this chat

- final repository name and visibility;
- Python version supported by the institutional environment;
- dependency and environment manager, based on what the user already uses;
- test, lint, and formatting commands;
- whether the canonical documentation files live at the repository root or in
  `docs/`;
- exact Project Instructions and `AGENTS.md` wording;
- license and handling of paper fixtures.

Do not discuss architecture schema fields or model prompts in this chat.

### 8.3 Candidate commit 0A - adopt the source of truth

Suggested message:

```text
docs: adopt the v3 architecture and roadmap
```

Scope:

- add `00_ARCHITECTURE_V3.md` and `01_IMPLEMENTATION_ROADMAP_V3.md` as the
  canonical decision documents;
- add a concise README that states the product goal, current phase, and
  non-goals without claiming that the pipeline exists;
- add repository guidance that preserves the language, commit, testing, and
  no-placeholder rules;
- link to the old v2 repository only as historical context.

Verification:

- links resolve;
- both documents agree about phase names and call semantics;
- the README says “not implemented” where appropriate;
- there is no copied v2 code.

### 8.4 Candidate commit 0B - establish real development tooling

Suggested message:

```text
chore: initialize the Python development baseline
```

Scope:

- configure only the chosen Python and dependency tooling;
- configure test, lint, and formatting commands that will actually be used;
- create the lock file if the chosen workflow uses one;
- add only necessary ignore rules;
- document exact setup and verification commands.

Do not create an empty application package, fake CLI, placeholder test, or
future directory tree merely to make the repository appear complete. The first
source package and tests may be created in Phase 1 together with real run
behaviour.

Verification:

- a clean checkout can install the declared development environment;
- configured lint and test discovery commands exit predictably even before the
  first functional test, using the chosen tool's documented convention;
- there are no unused runtime dependencies.

### 8.5 Phase 0 completion gate

- the new repository exists and v2 remains untouched;
- `main` contains the two authoritative documents;
- source priority and working rules are explicit;
- local tooling is reproducible;
- no placeholder implementation exists;
- the branch is merged and deleted;
- the accepted merge SHA is recorded in this roadmap or the handoff log.

### 8.6 Learning outcome

The user should be able to explain how the repository is governed, how a phase
branch becomes stable `main`, and why no code was copied before a concrete
consumer existed.

## 9. Phase 1 - run lifecycle and source preservation

- **Chat:** `01 - Run lifecycle and source preservation`
- **Branch:** `feat/run-lifecycle-completion`
- **Model calls:** none
- **Status:** completed
- **Accepted squash merge SHA:** 9691dd69e622be0b3606028819308f240c00dd12

### 9.1 Objective

Implement the smallest reliable run that accepts one PDF, preserves its
identity, renders ordered pages, records status, and leaves inspectable
failures. This is the deterministic base used by every later phase.

### 9.2 Questions to decide in this chat

- run identifier convention;
- minimum provenance required for reproducibility;
- atomic-write strategy supported by the target filesystem;
- PDF rendering resolution and image format;
- exact failure-state vocabulary;
- whether repository fingerprinting is required immediately or can wait until
  end-to-end provenance.

Prefer the smallest convention that can be tested. Do not recreate a workflow
engine.

### 9.3 Candidate commit 1A - preserve run input and identity

Suggested message:

```text
feat(run): create traceable PDF extraction runs
```

Behaviour:

- accept an existing PDF path;
- create an isolated run location;
- copy the PDF without modifying it;
- compute and persist its checksum;
- record creation time and source identity;
- write artefacts atomically;
- reject invalid input safely.

Tests:

- valid PDF copy and checksum;
- identical source bytes produce the expected document identity;
- missing or non-file input fails without a half-valid run;
- repeated runs do not overwrite one another;
- paths with spaces are handled;
- metadata writes are deterministic except for declared time and run identity.

### 9.4 Candidate commit 1B - render pages in source order

Suggested message:

```text
feat(document): render ordered PDF page assets
```

Behaviour:

- render every page;
- use globally one-based page identity in user-facing metadata;
- preserve source order;
- record page count, image dimensions, and checksums;
- make pages addressable as later visual fallback assets;
- fail clearly on an unreadable or encrypted PDF.

Tests:

- one-page and multi-page fixtures;
- page order and one-based labels;
- stable checksums under the same renderer settings;
- failure does not mark rendering complete;
- rendered artefacts match their metadata.

### 9.5 Candidate commit 1C - make failures inspectable

Suggested message:

```text
feat(run): preserve structured phase failures
```

Behaviour:

- record phase start, success, and failure states;
- preserve completed artefacts after a later failure;
- preserve structured error type and message;
- prevent a handled exception from leaving a phase marked as running;
- expose concise human-readable CLI failures.

The Phase 1 baseline deliberately omits skipped states and attempt counters
because it has no branching or retry execution. Secret redaction is deferred to
Phase 2, where model-client traces and credential-bearing errors are introduced.
These capabilities must be added with their first concrete consumers.

Tests:

- controlled rendering failure;
- completed input artefacts survive failure;
- invalid transitions are rejected;
- failure records identify the correct phase and error;
- modified preserved inputs are rejected before rendering.

### 9.6 Phase 1 completion gate

- a local command or tested entry point creates one traceable run from a PDF;
- all pages are rendered exactly once in order;
- document, page, and metadata hashes resolve;
- failure behaviour is visible and non-destructive;
- there is no model client, NuExtract prompt, or future-agent code yet;
- local tests and lint pass;
- the branch is merged and deleted.

### 9.7 Learning outcome

The user should understand the run lifecycle, why artefact identity precedes
model work, how atomic persistence is tested, and how phase state differs from
a workflow engine.

## 10. Phase 2 - NuExtract3 DocumentPackage

- **Chat:** `02 - NuExtract3 DocumentPackage`
- **Branch:** `feat/document-package`
- **Normal model calls:** `B = ceil(page_count / 8)`
- **Status:** implementation complete and merged

### 10.1 Objective

Convert every rendered page into one human-reviewable `document.md`. Preserve
the run artefacts, page identity, lifecycle state, and per-batch diagnostics
needed for inspection. Phase 2 does not perform scientific extraction.

### 10.2 Implemented capability findings

- The endpoint accepts ordered PNG page images.
- It returns an OpenAI-compatible response envelope.
- Markdown is read from `choices[0].message.content`.
- `finish_reason` and token usage are available in the response.
- One request per document can reach the endpoint context limit on larger
  papers.
- Reducing the rendering default from 200 DPI to 170 DPI helped but did not
  solve every larger-paper failure.
- Fixed consecutive batches contain at most eight pages.
- Batches run sequentially and cover the complete page sequence exactly once.
- Batch conversion completed larger papers that had previously ended with
  `finish_reason="length"`.
- Model-generated page ID markers are not reliable enough to use.
- The implementation does not produce separate figure binaries.

These findings describe observed behaviour. The repository does not record
timings, token counts, quality scores, or formal content-quality acceptance for
the manual runs.

### 10.3 Implemented work

The completed Phase 2 increment includes:

- PNG page rendering at 170 DPI by default;
- `pages/pages.json` with ordered page metadata and checksums;
- endpoint settings loaded from the environment and an optional local `.env`;
- `SKYNET_BASE_URL`, `SKYNET_API_KEY`, `DOCUMENT_EXTRACTOR_MODEL`, and
  `DOCUMENT_EXTRACTOR_TIMEOUT_SECONDS` validation;
- a minimal OpenAI-compatible raw-response client with SDK retries disabled;
- validation of run identity, pages identity, and lifecycle prerequisites;
- one logical document-conversion phase with `B` sequential calls;
- consecutive batches of up to eight pages with no relevance filtering;
- raw response persistence before Markdown parsing;
- traces written only for successfully parsed batch responses;
- mechanical Markdown assembly with two newline characters between batches;
- final `document.md` persistence only after every batch succeeds;
- lifecycle transition to `failed` at the first failed batch;
- CLI exposure through `convert-document`;
- fake-client tests for request construction, response parsing, batching,
  lifecycle behaviour, diagnostics, failures, and overwrite protection;
- manual conversion of representative larger papers.

The implementation has no retries, fallback models, parallel batch calls, or
configurable `max_tokens`.

### 10.4 Phase 2 artefact contract

The current `DocumentPackage` is the set of existing run artefacts:

```text
run_<id>/
├── manifest.json
├── status.json
├── input/
│   └── <source>.pdf
├── pages/
│   ├── pages.json
│   ├── page_0001.png
│   └── ...
└── document_conversion/
    ├── document.md
    ├── nuextract3_raw_response_batch_*.json
    └── nuextract3_trace_batch_*.json
```

`manifest.json` is the source and run manifest. `status.json` records lifecycle
state. `pages/pages.json` maintains page identity and source order. Phase 2 does
not create a second unified package manifest.

For each endpoint response received, the raw response is written before
parsing. A trace is written only after that response parses successfully. A
transport failure may leave no raw response because the endpoint returned
nothing. Conversion stops at the first failure and does not write
`document.md`. Outputs from earlier successful batches remain available.

### 10.5 Deliberately deferred scope

Separate figure materialization, a new unified package manifest, and a
dedicated immutable-package validator are not part of the Phase 2 completion
gate. Rendered full-page images and the existing manifests are sufficient for
the next implementation phase.

Phase 3 should introduce safe asset resolution and consumer-specific package
validation when its concrete consumer is defined. Separate figures should be
added only if evidence shows that full-page assets are insufficient.

### 10.6 Human and remote evidence

Manual work established the endpoint route, response envelope, context-limit
failure mode, and the larger-paper batching result listed above. Batch
boundaries and combined Markdown still require manual review. No formal
content-quality gate or score is recorded.

The source papers used for model capability work must be legally usable in the
development environment. Institutional credentials must not enter the
repository or documentation.

### 10.7 Phase 2 completion gate

- all rendered pages are processed once and in source order;
- one combined `document.md` is produced after all batches succeed;
- raw response files exist for batch responses received from the endpoint;
- trace files exist for successfully parsed batches;
- no final Markdown exists when any batch fails;
- conversion stops at the first failed batch;
- no architecture or results interpretation occurs;
- automated tests and lint pass;
- representative larger papers complete through manual batch conversion;
- the repository owner reviews and merges the feature branch.

Formal content-quality acceptance is deferred until reproducible scientific
assertions exist.

### 10.8 Learning outcome

The user should understand the observed NuExtract3 protocol, why the context
limit required source-ordered batching, how diagnostic artefact timing supports
failure analysis, and why page images plus existing manifests are the current
package boundary.

## 11. Phase 3 - bounded asset inspection

- **Chat:** `03 - Bounded asset inspection`
- **Branch:** `feat/asset-inspection`
- **Model calls:** none in deterministic tool tests; up to two in an integration agent run
- **Status:** not started

### 11.1 Objective

Define the consumer-specific package validation boundary and implement the
controlled mechanism by which a scientific agent can request exact full-page
assets declared in `pages/pages.json` and receive them in a second model turn.

### 11.2 Fixed decisions for this phase

- agents initially receive `document.md` and the minimum accepted package
  metadata defined in this phase;
- the requesting agent chooses exact asset identifiers;
- the tool is deterministic and contains no model;
- returned images are interpreted by the same scientific model;
- one scientific agent run has at most one tool round;
- no semantic search, similarity ranking, or automatic page selection occurs.

### 11.3 Questions to decide in this chat

- exact tool name and concise model-facing description;
- minimum request information: asset identifiers plus focused visual questions;
- maximum assets and payload per one round based on the endpoint probe;
- how the endpoint represents image tool results;
- how invalid, oversized, or duplicate requests are reported;
- whether evidence justifies separate figure assets in addition to the current
  full-page assets.

### 11.4 Candidate commit 3A - validate and resolve package assets safely

Suggested message:

```text
feat(tools): resolve manifest-backed visual assets
```

Behaviour:

- define and validate the package boundary required by this consumer;
- load only package artefacts that satisfy that boundary;
- accept exact declared identifiers;
- enforce count and payload limits;
- preserve requested order or apply one documented stable ordering rule;
- reject unknown, duplicate, or unsafe references;
- return image data and source metadata;
- trace identifiers and hashes without logging large encoded payloads.

Tests:

- full-page resolution;
- unknown and duplicate identifiers;
- path traversal attempts;
- payload and count limits;
- deterministic ordering;
- altered asset hash;
- no file access outside the package.

Do not add separate figure files or a broader package schema unless a concrete
Phase 3 case demonstrates that the existing page assets and manifests are
insufficient.

### 11.5 Candidate commit 3B - enforce one tool round

Suggested message:

```text
feat(agents): add a bounded visual tool interaction
```

Behaviour:

- invoke the model with Markdown, accepted package metadata, role prompt, and
  tool definition;
- accept either a final report or one valid asset request;
- execute the deterministic asset tool;
- invoke the same model again with the returned images;
- require a final report after the tool result;
- reject a second tool request;
- record model-call and tool-execution counts explicitly.

Tests with a scripted fake model:

- one-turn final response with no tool;
- valid tool request followed by final response;
- invalid tool arguments;
- unknown assets;
- attempted second tool round;
- model failure before and after the tool;
- exactly one or two model calls as appropriate;
- exactly zero or one deterministic tool execution;
- all raw responses and tool traces survive failure.

### 11.6 Candidate commit 3C - verify the real multimodal protocol

Suggested message:

```text
test(models): verify multimodal tool-result handling
```

Scope:

- add an opt-in, minimal endpoint probe that uses a harmless visual fixture;
- verify that the candidate model can emit the tool request;
- verify that the next request can include the returned image;
- verify that the same conversation context is preserved;
- record observed protocol, image limits, latency, and call count;
- keep production selection open until Phase 4.

The user runs the probe manually against the institutional endpoint. The repo
contains the reproducible probe and redacted observations, not credentials or
unreviewed output dumps.

### 11.7 Phase 3 completion gate

- a fake-model integration proves both one-call and two-call paths;
- the real endpoint protocol is measured for at least one eligible multimodal
  candidate;
- the tool never interprets assets or invokes a model;
- a second tool round is impossible in the baseline;
- exact asset and model-call traces are preserved;
- the implementation is a small explicit controller, not a general agent
  framework;
- the branch is merged and deleted.

### 11.8 Learning outcome

The user should be able to trace the complete conversation from first model
turn, through deterministic tool execution, to the second model turn and
explain why this is one logical agent run but potentially two model calls.

## 12. Phase 4 - architecture agent

- **Chat:** `04 - Architecture agent`
- **Branch:** `feat/architecture-agent`
- **Normal model calls:** one or two
- **Status:** not started

### 12.1 Objective

Produce a human-reviewable, evidence-grounded architecture report from the
complete Markdown and only the visual assets the agent requests.

### 12.2 Questions to decide in this chat

- the minimum stable report sections and claim-identifier convention;
- how a text, table, equation, caption, or page reference is expressed;
- what distinguishes reported, visually interpreted, derived, ambiguous,
  missing, and proposed information;
- which architecture features are critical to reconstruction;
- what evidence makes final/fabricated design selection acceptable;
- whether Gemma 4, Qwen 3.6, or another endpoint-proven multimodal candidate
  should be benchmarked first;
- scoring and human-review criteria for model selection.

Do not define a universal block/CAD schema in this phase. The output is
Markdown.

### 12.3 Candidate commit 4A - define the architecture report boundary

Suggested message:

```text
docs(architecture): define evidence report requirements
```

Scope:

- define a concise report template and examples using synthetic evidence;
- define resolvable claim and evidence conventions;
- define how ambiguity, missing information, conflicts, and unapplied proposals
  are represented;
- define objective report validation that does not judge antenna meaning;
- list the initial scientific assertions used in model evaluation.

Verification:

- every example claim resolves to Markdown or an accepted package asset;
- unsupported information cannot be presented as reported fact;
- the template remains readable without a generated JSON schema;
- a valid incomplete report is representable.

### 12.4 Candidate commit 4B - implement the architecture agent run

Suggested message:

```text
feat(architecture): generate an evidence-grounded report
```

Behaviour:

- validate the Phase 3 consumer boundary before calling the model;
- send complete Markdown, accepted package metadata, the focused role, and the
  asset tool;
- execute the bounded one-round interaction from Phase 3;
- require selection evidence or explicit selection ambiguity;
- preserve materials, components, geometry, dimensions, relationships, feeds,
  derivations, conflicts, and missing information at report level;
- persist `architecture_evidence_report.md`, raw responses, tool traces, and a
  validation report;
- never request or emit the final architecture JSON.

Tests with fake clients:

- report without visual tool use;
- report after exact visual asset requests;
- missing evidence reference;
- unsupported claim classification;
- honest incomplete report;
- attempted second tool request;
- model and tool failures preserve all prior artefacts;
- one or two model calls are recorded accurately.

### 12.5 Candidate commit 4C - benchmark the candidate scientific models

Suggested message:

```text
test(architecture): compare candidate multimodal agents
```

Method:

1. Freeze the same document packages, prompts, tool limits, and model settings.
2. Run candidates sequentially.
3. Do not allow one output to influence the next.
4. Apply deterministic evidence/reference checks.
5. Review scientific assertions blind to model identity where practical.
6. Compare unsupported additions, missing features, tool requests, call count,
   truncation, and latency.
7. Record the decision and the exact endpoint identifiers.

Initial scientific checks should include:

- correct final or fabricated design selection, or explicit ambiguity;
- topology and additive/subtractive intent;
- layer stack and material fidelity;
- symbol-to-dimension associations;
- source-supported derivations;
- feeds, ports, vias, grounds, and important relationships;
- no invented numerical or material defaults;
- no false claim of reconstruction completeness.

Model selection is a development decision, not a runtime ensemble. If no
candidate passes the minimum gate, improve the prompt, report boundary, asset
interface, or document package before adding more calls.

### 12.6 Phase 4 completion gate

- an accepted package produces `architecture_evidence_report.md`;
- every material claim has resolvable evidence or an explicit non-factual
  state;
- one tool round is sufficient on the accepted baseline cases, or the phase
  reports a blocking measured limitation;
- a candidate model is selected by evidence, not assumption;
- the report is useful to a human without the final JSON;
- no results inventory or final-schema pressure has entered the prompt;
- local tests, lint, and reviewed model runs pass;
- the branch is merged and deleted.

### 12.7 Learning outcome

The user should understand how the prompt narrows the scientific task, how
claims link to evidence, how visual requests are chosen, and why an incomplete
grounded report is safer than a complete-looking reconstruction.

## 13. Phase 5 - results agent

- **Chat:** `05 - Results agent`
- **Branch:** `feat/results-agent`
- **Normal model calls:** one or two
- **Status:** not started

### 13.1 Objective

Produce a complete, evidence-grounded inventory of reported results without
requiring the agent to reconstruct antenna geometry or satisfy the final JSON
contract.

### 13.2 Questions to decide in this chat

- minimum report sections and claim identifiers for results;
- representation of design variants, setups, conditions, traces, and result
  origins;
- handling of scalar, range, tabular, curve, radiation-pattern, and image-only
  evidence;
- how to represent values that are visually approximate versus explicitly
  reported;
- criteria for distinguishing a conflict from simulated/measured difference;
- whether to reuse the Phase 4 model or benchmark role-specific candidates;
- what completeness assertions can be checked deterministically and what
  requires expert review.

### 13.3 Candidate commit 5A - define the results report boundary

Suggested message:

```text
docs(results): define evidence report requirements
```

Scope:

- define a readable report template using synthetic examples;
- define result claim and evidence conventions;
- preserve exact values, units, trace labels, origins, designs, and setups;
- define image-only and partially numeric outcomes;
- define explicit ambiguity and missing associations;
- add objective validation that does not decide scientific correctness.

Verification:

- measured and simulated results remain distinct;
- variant results can be represented without attaching them to the primary
  design by default;
- graph-only results can remain useful without fabricated samples;
- every example result resolves to source evidence.

### 13.4 Candidate commit 5B - implement the results agent run

Suggested message:

```text
feat(results): generate an evidence-grounded report
```

Behaviour:

- load only the package accepted through the Phase 3 consumer boundary, not the
  architecture report;
- send complete Markdown, accepted package metadata, focused role, and asset
  tool;
- use the same bounded interaction protocol;
- inventory all reported result categories, designs, variants, setups, and
  conditions;
- preserve exact reported values and uncertainty;
- persist `results_evidence_report.md`, raw responses, tool traces, and a
  validation report;
- never emit the final results JSON.

Tests with fake clients:

- text/table-only result report without tool use;
- graph inspection through an exact full-page asset request;
- measured and simulated trace separation;
- multiple variants and setup associations;
- image-only result preservation;
- missing evidence and design reference;
- attempted second tool request;
- one or two model calls recorded accurately;
- architecture report is never read.

### 13.5 Candidate commit 5C - benchmark result coverage

Suggested message:

```text
test(results): evaluate exhaustive result coverage
```

Method:

- freeze representative packages and assertions;
- run candidates sequentially with identical inputs;
- count expected result claims and associations;
- inspect omissions, unsupported numeric readings, origin errors, and variant
  mistakes;
- record visual requests, call count, latency, and truncation;
- select a role model only after scientific review.

The benchmark must include at least:

- a table-heavy paper;
- a paper with equations that define a reported metric or condition;
- a graph-heavy paper;
- simulated and measured comparisons;
- multiple design variants or optimization steps;
- a case with an image-only result that must not be digitized implicitly.

### 13.6 Candidate commit 5D - share only proven mechanics, if justified

Suggested message:

```text
refactor(agents): share proven report-run mechanics
```

This commit is optional. It exists only if the working architecture and results
agents now contain demonstrably identical orchestration code. It may share
mechanical input assembly, trace handling, and bounded tool execution. It must
not merge the prompts, report semantics, validators, or scientific roles into
a generic agent framework.

If the duplication is small or the abstraction is unclear, skip this commit.

### 13.7 Phase 5 completion gate

- an accepted package produces `results_evidence_report.md` independently of
  architecture;
- expected variants, setups, origins, and result types are preserved on the
  benchmark set;
- exact reported numeric values are not silently changed;
- graph-only evidence remains graph-grounded;
- every result claim has resolvable evidence or explicit uncertainty;
- a model is selected or a measured blocker is documented;
- no premature final schema or architecture context is present;
- local tests, lint, and reviewed model runs pass;
- the branch is merged and deleted.

### 13.8 Learning outcome

The user should understand why result extraction is an exhaustive inventory
problem, how it differs from architecture reconstruction, and how visual graphs
can be preserved without pretending to have precise numeric samples.

## 14. Phase 6 - canonicalization and final contracts

- **Chat:** `06 - Canonicalization and final contracts`
- **Branch:** `feat/canonicalization`
- **Normal model calls:** one
- **Status:** not started

### 14.1 Objective

Organize the two accepted evidence reports into a shallow combined response,
prove that no report claim disappeared silently, and split the response
mechanically into the two final JSON documents.

### 14.2 Fixed decisions for this phase

- the canonicalizer receives both reports and the minimum package identity
  metadata needed for reference validation;
- it does not receive `document.md`, the PDF, figures, or pages;
- it organizes rather than reinterprets scientific evidence;
- the model-facing schema is small and flexible;
- strictness is reserved for stable boundaries and references;
- every input claim has an explicit disposition;
- one model response contains architecture and results sections;
- deterministic code writes exactly two final domain JSON files;
- Python does not repair or reinterpret model content.

### 14.3 Questions to decide in this chat

- the smallest useful final consumer contract, based on the real reports now
  available;
- which top-level fields are genuinely stable enough to require;
- where flexible attributes are preferable to enumerated variants;
- the claim-disposition representation and merge rules;
- how exact source values coexist with optional normalized presentation;
- how incomplete, unresolved, and conflicting information appears in final
  files;
- which candidate text model best preserves claims and follows the shallow
  contract;
- whether the first baseline should reuse the scientific model to reduce
  variables.

Do not revive the large v2 schema. Any field without a current report example
and consumer need should be deferred.

### 14.4 Candidate commit 6A - define the shallow final boundary

Suggested message:

```text
feat(contracts): define flexible final extraction contracts
```

Scope:

- derive the minimal contract from accepted architecture and results reports;
- define the stable combined envelope and the two final sections;
- define document identity, evidence-reference, provenance, uncertainty, and
  claim-disposition invariants;
- allow flexible domain attributes where the benchmark is not mature;
- generate model-facing schema from one executable source of truth;
- include synthetic complete and incomplete examples.

Tests:

- valid minimal and representative rich outputs;
- unknown content survives through designated extension points;
- missing stable boundaries fail;
- invalid evidence references fail;
- unresolved content remains representable;
- the schema is materially smaller and shallower than the abandoned direct
  extraction schema.

### 14.5 Candidate commit 6B - implement report canonicalization

Suggested message:

```text
feat(canonicalization): organize evidence reports
```

Behaviour:

- validate both reports and package identity;
- send only the two reports, required package identity metadata, role prompt,
  and shallow contract;
- require claim preservation and explicit disposition;
- preserve ambiguity and exact evidence links;
- persist raw response before parsing;
- validate the combined response;
- make one model call with no tools.

Tests with a fake client:

- valid combined response;
- invalid JSON and schema failure;
- unknown or missing evidence reference;
- unsupported newly invented claim;
- omitted claim;
- explicit merge of duplicate report claims;
- unresolved claim retained;
- no access to PDF, Markdown, figures, or pages;
- exactly one model call and no tool execution.

### 14.6 Candidate commit 6C - verify claim disposition and split outputs

Suggested message:

```text
feat(outputs): validate and split final extraction files
```

Behaviour:

- enumerate the claim identifiers in both reports;
- verify that each has exactly one acceptable disposition;
- reject silent omission or unexplained duplication;
- copy architecture content to `antenna_architecture.json`;
- copy results content to `antenna_results.json`;
- preserve common document identity and provenance;
- write atomically and emit an internal validation report;
- perform no semantic rewrite.

Tests:

- every claim represented exactly once or explicitly merged;
- missing, duplicated, and unknown disposition identifiers fail;
- the split is a lossless mechanical projection;
- one failed final file prevents presentation of a partially accepted pair
  under the chosen publication rule;
- exact values, units, and evidence references survive;
- deterministic ordering is stable where promised.

### 14.7 Candidate commit 6D - select the canonicalization model

Suggested message:

```text
test(canonicalization): compare contract fidelity
```

Use frozen real reports to compare eligible text models on:

- claim coverage;
- schema validity;
- unsupported additions;
- merge correctness;
- evidence-reference preservation;
- stable output across repeated controlled runs;
- latency and token use.

Correctness and zero silent loss outrank latency. A faster model does not win if
it drops difficult or unresolved claims.

### 14.8 Phase 6 completion gate

- one canonicalization call produces a valid combined envelope;
- every report claim has an auditable disposition;
- deterministic validation writes exactly two final JSON files;
- final contracts remain shallow, flexible, and evidence-bearing;
- canonicalization introduces no new scientific interpretation;
- intermediate reports remain available after any failure;
- local tests, lint, and reviewed model comparisons pass;
- the branch is merged and deleted.

### 14.9 Learning outcome

The user should understand why schema pressure was postponed, how a shallow
contract differs from an untyped blob, how claim accounting prevents silent
loss, and why deterministic splitting is safe while semantic repair is not.

## 15. Phase 7 - end-to-end runner

- **Chat:** `07 - End-to-end runner`
- **Branch:** `feat/end-to-end`
- **Normal model calls:** `B + 3` to `B + 5`
- **Status:** not started

### 15.1 Objective

Expose one clear sequential command that executes the accepted phases, reports
the actual call budget, preserves partial success, and produces the two final
outputs when all required gates pass.

### 15.2 Questions to decide in this chat

- exact CLI naming and output;
- whether phase-specific commands are exposed for learning and explicit rerun;
- dependency-aware continuation after one scientific agent fails;
- final publication rule when one of two outputs fails validation;
- non-zero exit status policy for incomplete but structurally valid reports;
- what summary is printed without hiding the detailed run artefacts.

### 15.3 Candidate commit 7A - orchestrate the sequential pipeline

Suggested message:

```text
feat(cli): run the sequential extraction pipeline
```

Normal order:

1. initialize the run and preserve the PDF;
2. render ordered pages;
3. make `B` sequential NuExtract3 batch calls and validate the package boundary
   accepted for downstream consumption;
4. execute the architecture agent;
5. execute the results agent;
6. canonicalize when both reports are valid;
7. validate and write the two final JSON files;
8. print run location, outputs, statuses, model calls, and tool executions.

The scheduler is sequential. Architecture and results are independent after the
document package: a failure in one may still allow the other to run, but
canonicalization waits for both. There is no concurrent call.

Tests:

- exact phase order;
- all no-tool path gives `B + 3` model calls;
- both agents using assets gives `B + 5` model calls and two deterministic tool
  executions;
- mixed tool-use path gives `B + 4` model calls;
- NuExtract failure skips all scientific phases;
- architecture failure does not erase the package and may still allow the
  results report;
- results failure preserves the architecture report;
- canonicalization failure preserves both reports;
- no handled failure leaves a phase running;
- no automatic retry occurs.

### 15.4 Candidate commit 7B - support explicit phase inspection or rerun

Suggested message:

```text
feat(cli): expose explicit phase execution
```

This commit is conditional. Implement it only if Phase 4-6 development shows a
real need to rerun one expensive phase without repeating NuExtract3.

If implemented, it must:

- require an accepted prerequisite artefact;
- compare input, prompt, model, and contract hashes;
- never reuse stale output silently;
- preserve the previous attempt or record explicit replacement policy;
- remain a small phase command, not become a workflow engine;
- require user intent and perform no automatic retry.

If the need is not yet demonstrated, skip this commit and use new runs for the
baseline.

### 15.5 Candidate commit 7C - add end-to-end fixtures and operator docs

Suggested message:

```text
test(pipeline): verify end-to-end artefact integrity
```

Scope:

- test the full pipeline with fake model responses;
- include no-tool, visual-tool, incomplete, and failure scenarios;
- verify all hashes and references across phase boundaries;
- document the command, environment variables, artefact meanings, and call
  budget;
- state clearly that valid extraction does not mean solver-ready geometry;
- provide only examples produced from synthetic or distributable sources.

### 15.6 Phase 7 completion gate

- one command runs the pipeline sequentially;
- the command reports `B + 3`, `B + 4`, or `B + 5` actual model calls
  correctly;
- no hidden or parallel model work occurs;
- valid partial artefacts survive later failure;
- final JSON files appear only after all relevant gates pass;
- operator documentation matches executable behaviour;
- local end-to-end tests and lint pass;
- the branch is merged and deleted.

### 15.7 Learning outcome

The user should be able to follow the state transition of an entire run,
identify every model and tool boundary, and explain why independent partial
reports survive without turning the runner into a complex workflow engine.

## 16. Phase 8 - scientific benchmark and baseline

- **Chat:** `08 - Scientific benchmark and baseline`
- **Branch:** `test/scientific-benchmark`
- **Model calls:** explicit, sequential, and reported per experiment
- **Status:** not started

### 16.1 Objective

Decide whether v3 is scientifically better than the archived approach, freeze
the first reproducible baseline, and identify the next improvement from
evidence rather than architectural intuition.

### 16.2 Benchmark corpus

Use a small reviewed set that covers different failure modes, not merely many
similar patch antennas. It should include, subject to access and licensing:

- the known v2 regression papers, used for assertions rather than copied
  pipeline expectations;
- geometry with slots, notches, booleans, vias, multilayers, arrays, curved or
  non-rectangular features;
- multiple design variants and a clear fabricated/final candidate;
- table-heavy and equation-heavy sources;
- graph-heavy results;
- simulated and measured comparisons;
- at least one intentionally incomplete or ambiguous paper;
- at least one paper outside the dominant geometry family.

The benchmark set is versioned. Papers that cannot be redistributed are
referenced through checksums and local setup instructions, not committed
illegally.

### 16.3 Candidate commit 8A - define scientific acceptance assertions

Suggested message:

```text
test(benchmark): define v3 scientific acceptance cases
```

For each paper, record expected assertions at four boundaries:

**Document package**

- sections, tables, equations, and captions that must be present;
- required full-page visual evidence;
- page and asset traceability;
- known conversion limitations.

**Architecture report**

- correct selected design or expected ambiguity;
- critical components, topology, materials, dimensions, relationships, and
  feeds;
- required visual interpretations;
- forbidden unsupported assumptions;
- expected unresolved information.

**Results report**

- expected result inventory;
- design, variant, setup, and origin associations;
- exact values that must be preserved;
- graph-only results that must not be fabricated numerically.

**Canonical outputs**

- claim-disposition completeness;
- required architecture and result claims;
- evidence preservation;
- no unsupported additions or silent loss.

Separate deterministic assertions from expert-review questions. Do not encode
an expert visual judgement as a brittle string test.

### 16.4 Candidate commit 8B - run and record the frozen baseline

Suggested message:

```text
test(benchmark): record the first agentic extraction baseline
```

For each run record:

- document checksum and page count;
- exact endpoint and model identifiers;
- prompt, report-template, and contract hashes;
- model settings;
- requested asset identifiers;
- model-call and tool-execution count;
- latency and usage when available;
- structural checks;
- scientific assertions;
- expert-review outcome;
- unresolved and failed cases.

The comparison with v2 should focus on observable failure classes:

- omitted architecture features;
- wrong final-design selection;
- unsupported dimensions or materials;
- lost variants or results;
- incorrect simulated/measured association;
- schema failure despite useful reasoning;
- evidence that cannot be resolved;
- total calls and latency.

### 16.5 Candidate commit 8C - freeze the accepted baseline

Suggested message:

```text
docs: document the accepted v3 baseline
```

Scope:

- summarize what passed, failed, and remains unresolved;
- record the chosen model per role;
- record the normal observed call range;
- update README limitations and exact setup;
- update this roadmap's phase status and accepted SHAs;
- recommend a signed or annotated release tag only if all baseline gates pass;
- list the next evidence-backed architectural question without implementing it.

Suggested tag after manual acceptance:

```text
v3.0.0-baseline
```

Do not tag a baseline merely because every JSON file validates.

### 16.6 Phase 8 completion gate

- the benchmark corpus covers the named failure modes;
- each model role is justified by frozen evidence;
- scientific and structural acceptance are reported separately;
- actual call count and latency are transparent;
- comparisons with v2 use the same source cases where practical;
- no critical failure is hidden by aggregate scoring;
- limitations are documented in operator-facing language;
- a baseline tag is recommended only after manual review;
- the branch is merged and deleted.

### 16.7 Learning outcome

The user should understand how to distinguish a schema-valid run from a
scientifically useful run, how model selection is made reproducibly, and how a
measured failure becomes the input to the next architectural decision.

## 17. Test strategy across phases

### 17.1 Default local tests

Default tests do not contact remote models. They use deterministic fixtures and
scripted fake responses for:

- run identity and artefact persistence;
- page order and rendering metadata;
- model request construction;
- ordered document-conversion batches;
- OpenAI-compatible response parsing;
- raw-response, trace, and failure preservation;
- final Markdown assembly only after complete success;
- consumer-specific package validation when Phase 3 defines it;
- asset resolution and limits;
- one-round agent interaction;
- report-boundary validation;
- shallow final contracts;
- claim-disposition coverage;
- deterministic output splitting;
- end-to-end phase order and call counts.

### 17.2 Opt-in remote checks

Remote checks are narrow and versioned by endpoint, exact model, date, prompt,
contract, settings, and fixture hash. They verify only capabilities that cannot
be proven locally:

- PDF or multi-image input;
- Markdown fidelity;
- figure-output behaviour;
- context and payload limits;
- tool-call emission;
- image tool-result continuation;
- structured-output compliance;
- latency, usage, and finish reasons.

They run sequentially and never as part of ordinary test discovery.

### 17.3 Scientific review

Scientific review examines source papers and generated artefacts. It is not
replaced by Pydantic, JSON Schema, or snapshot tests.

Review should be claim-oriented: the reviewer verifies expected inclusions,
forbidden inferences, evidence resolution, and known ambiguity. A single
overall score must not conceal a missing critical feed, dimension, variant, or
measurement.

### 17.4 Test order for each commit

1. directly affected unit tests;
2. relevant integration slice;
3. complete local suite;
4. lint and static checks;
5. artefact inspection;
6. opt-in endpoint or scientific checks only when model-facing behaviour
   changed.

## 18. Model experiment rules

When comparing models:

- use identical frozen inputs;
- run sequentially;
- use the same prompt and limits;
- record exact deployed identifiers, not only family names;
- do not let one response become context for another;
- keep temperature and other settings controlled;
- report truncation and endpoint errors;
- score critical assertions individually;
- prefer correctness and evidence fidelity over speed;
- do not turn the losing model into an automatic fallback;
- stop and improve the boundary if no model satisfies the minimum gate.

The institutional model list is a candidate inventory. Capabilities must be
observed. In particular, a model is not treated as multimodal or tool-capable
because its family commonly supports those features elsewhere.

## 19. Phase and artefact dependency rules

The dependency structure is intentionally small:

```text
Run lifecycle
    -> DocumentPackage
        -> Architecture report
        -> Results report
            -> Canonical combined response
                -> Two final JSON files
```

Architecture and results share the document package but not one another. The
runner may execute the second scientific phase after the first fails because
their dependencies are independent, but it remains sequential.

Canonicalization requires both accepted reports. Final splitting requires one
valid combined response. A downstream phase never consumes a raw or unaccepted
upstream artefact.

## 20. Status and handoff record

After each accepted commit, append or update a concise handoff record outside
the generated artefacts:

```text
Phase:
Commit objective:
Branch:
Commit SHA:
Base SHA:
Files changed:
Tests run:
Lint/static checks:
Remote checks:
Model identifiers:
Prompt/template/contract hashes:
Representative artefacts inspected:
Decisions made:
Known limitations:
Deferred work:
Next proposed commit:
```

Do not write a SHA before the commit exists. The next phase chat verifies every
record against Git.

At the end of a phase, update at least:

- phase status;
- accepted merge SHA;
- any changed decision;
- measured model capability;
- next phase entry conditions.

## 21. Template for starting a phase chat

Use a message like this, adapted to the actual phase:

```text
Estamos a trabalhar na Fase <N> - <nome> do Antenna Extraction v3, no novo
repositório, branch <branch>.

Lê por completo 00_ARCHITECTURE_V3.md e 01_IMPLEMENTATION_ROADMAP_V3.md.
Depois inspeciona o HEAD, working tree, código e testes reais. Não assumas que
o roadmap reflete o estado implementado sem o verificares.

Antes de editar, explica-me em português europeu:
1. o que já está implementado e é relevante para esta fase;
2. as decisões em aberto que pertencem a esta fase;
3. o menor commit coerente que propões agora;
4. os ficheiros que deverá alterar;
5. os testes e artefactos que teremos de rever para o aceitar.

Não implementes trabalho de fases posteriores, placeholders, paralelismo, RAG,
retries, fallback models, reviewer models ou um agent framework genérico. Não
faças commit; eu controlo o commit depois de rever o diff e os testes.
```

## 22. Template for a Codex implementation prompt

After the phase discussion agrees on one commit, generate a narrow English
prompt such as:

```text
Implement the agreed <commit objective> on branch <branch>.

Before editing, inspect the current HEAD, working tree, relevant code, and
tests. Preserve all unrelated user changes. Follow 00_ARCHITECTURE_V3.md and
the current phase of 01_IMPLEMENTATION_ROADMAP_V3.md.

Scope:
- <agreed behaviour>
- <agreed behaviour>

Out of scope:
- work from later phases
- speculative abstractions or placeholder files
- parallelism, RAG, retries, fallback/reviewer models, or hidden model calls

Verification:
- <direct tests>
- <integration checks>
- <artefacts to inspect>

Do not commit. After implementation, report the files changed, tests run,
observed artefacts, limitations, and whether the commit completion gate is
satisfied.
```

The prompt should contain the actual agreed details. Do not send the whole
roadmap back to Codex as a substitute for a precise task.

## 23. Review checklist before every manual commit

- Is the working tree free of unrelated accidental changes?
- Does the diff implement only the agreed commit?
- Does every new code path have a current caller?
- Are new dependencies necessary now?
- Are model calls synchronous and counted?
- Are raw responses preserved before parsing?
- Are secrets and large encoded payloads absent from traces?
- Does deterministic code remain mechanical?
- Are tables and equations still handled only through Markdown?
- Does the asset tool remain deterministic and bounded?
- Are uncertainty and missing information preserved?
- Do tests cover failure as well as success?
- Do representative artefacts look correct to a human?
- Does documentation avoid claiming unimplemented behaviour?
- Is the commit message an accurate English description of the diff?

## 24. Escalation rule for new complexity

Do not add a new stage, model call, tool round, retrieval layer, schema family,
or workflow abstraction because it seems generally useful. Require:

1. a reproducible paper or endpoint failure;
2. the exact boundary that failed;
3. evidence that prompt or local contract refinement is insufficient;
4. the smallest proposed change;
5. expected effect on calls, latency, maintenance, and auditability;
6. a new acceptance test;
7. an explicit amendment to `00_ARCHITECTURE_V3.md` if an invariant changes.

Examples:

- A second asset-tool round requires papers where one round repeatedly fails
  despite clear package metadata and a clear prompt.
- A separate visual model requires evidence that eligible scientific models
  cannot interpret returned images and that the added boundary improves
  accuracy.
- Changes to document-conversion batching require a measured endpoint failure
  or a reproducible quality problem.
- RAG requires a corpus-scale requirement or a new architectural use case, not
  merely a long paper.
- A reviewer requires reproducible false-complete outputs that cannot be
  controlled at the report or benchmark boundary.

## 25. Definition of implementation done

The first v3 baseline is complete only when all of the following are true.

### Repository

- the new repository contains one implemented architecture;
- `main` is stable and every completed phase branch was merged and deleted;
- no placeholder or unused future-phase code remains;
- v2 is preserved separately and is not imported as an active path;
- architecture, roadmap, README, and executable behaviour agree.

### Document preservation

- one paper produces the Phase 1 and Phase 2 `DocumentPackage` artefact set;
- the complete Markdown preserves prose, tables, equations, and captions;
- no table or equation crops exist;
- full-page visual assets and page identity are recorded in
  `pages/pages.json`;
- `B = ceil(page_count / 8)` sequential conversions cover every page exactly
  once and in source order;
- conversion traces and raw responses are inspectable;
- safe asset resolution and consumer-specific validation are added when Phase
  3 defines their consumer boundary.

### Scientific agents

- architecture and results operate independently from the same package;
- each initially receives complete Markdown and the accepted package metadata;
- each uses zero or one deterministic asset-tool execution;
- each produces a readable evidence report;
- every material claim has evidence or an explicit uncertainty state;
- selected models are justified by the frozen benchmark.

### Canonical outputs

- one canonicalization call receives only the two reports and required package
  identity metadata;
- the model-facing contract is shallow and flexible;
- every report claim has a disposition;
- deterministic code writes exactly
  `antenna_architecture.json` and `antenna_results.json`;
- no deterministic semantic repair occurs;
- exact values, evidence, ambiguity, and missing information survive.

### Reliability

- normal execution is sequential;
- actual model calls are reported as `B + 3`, `B + 4`, or `B + 5`;
- no automatic retries, fallbacks, reviewers, hidden VLM, or parallel work
  occur;
- completed artefacts survive later failures;
- local tests and lint pass;
- remote checks are opt-in, traceable, and redacted.

### Scientific acceptance

- the benchmark covers the known v2 failure classes and diverse geometry;
- document, architecture, results, and canonical boundaries have separate
  assertions;
- structural validity is not presented as scientific correctness;
- critical omissions and unsupported additions are visible individually;
- incomplete source evidence produces an explicit incomplete outcome;
- the accepted baseline and its limitations are documented before tagging.

## 26. Immediate next action

Phase 1 is complete and was integrated into `main` with squash merge
`9691dd69e622be0b3606028819308f240c00dd12`. Phase 2 implementation is complete
on `feat/document-package` and has been merged into `main` with squash merge `d88ba548f32254edd97ba10f7c90e4e74393d083`.

Next steps:

1. Finish the Phase 2 documentation and final repository checks.
2. Let the repository owner review and merge Phase 2.
3. Begin Phase 3 only after the Phase 2 contract is accepted.

Do not record an accepted Phase 2 merge SHA until the merge exists. Phase 3
must inspect the merged implementation and define safe asset resolution and
consumer-specific validation from a concrete consumer need.
