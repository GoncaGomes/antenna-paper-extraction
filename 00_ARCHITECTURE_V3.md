# Antenna Extraction v3 - Architectural Decision

**Status:** draft; Phase 2 implementation is complete on its feature branch and pending merge

**Version:** 3.1-draft

**Date:** 2026-09-04

**Scope:** extraction of antenna architecture and reported results from one scientific paper

**Supersedes:** the v2 pipeline design as the intended architecture

## 1. Role of this document

This document is the architectural source of truth for the new repository. It
defines the system boundaries, the responsibilities of each model call, the
artefacts exchanged between phases, and the decisions that must remain stable
while the first implementation is built.

It deliberately does **not** define the complete JSON fields, Pydantic models,
class hierarchy, package tree, or every function. Those details belong to the
implementation phase in which they become necessary. The architecture should
constrain the system without forcing an untested data model too early.

The companion document `01_IMPLEMENTATION_ROADMAP_V3.md` divides this
architecture into one development phase per chat, with small, reviewable
commits and explicit completion gates.

This document describes intended behaviour. It must never be used as evidence
that a phase has already been implemented. The repository on `main` remains
the authority for current executable behaviour.

## 2. Architectural decision

The v3 pipeline will replace the previous attempt to ask one model to extract,
interpret, reconcile, and serialize almost the entire paper into a large strict
schema.

The new system is a **small, sequential, evidence-first, bounded-agentic
pipeline**:

1. NuExtract3 converts the complete ordered page sequence into a
   loss-preserving `DocumentPackage` through sequential batches.
2. An architecture agent reads the complete Markdown and requests only the
   visual assets it needs.
3. A results agent independently reads the same package and requests only the
   visual assets it needs.
4. A canonicalization model organizes the two evidence reports into a shallow,
   flexible final contract.
5. Deterministic code validates the contract and splits it into two final JSON
   documents.

The difficult scientific tasks are separated by purpose. The architecture
agent does not have to enumerate every reported result, and the results agent
does not have to reconstruct the geometry. The final model does not reread the
paper or reinterpret figures; it organizes already grounded claims.

## 3. Why the v2 direction is being abandoned

The central v2 difficulty was not merely model quality. It was the combination
of several independent burdens in the same call:

- understanding a full scientific document;
- interpreting text, tables, equations, captions, and figures;
- choosing the relevant fabricated or final antenna;
- reconstructing topology, geometry, materials, dimensions, and feeds;
- inventorying all simulated, measured, and analytical results;
- associating every claim with evidence;
- resolving ambiguity without inventing information;
- satisfying a large, deeply strict output schema at the same time.

A response could therefore be syntactically valid while being scientifically
incomplete. It could also fail schema generation even when the model had
understood the source. Enlarging the schema or prompt would increase the
competition between reasoning, evidence coverage, and serialization.

The v3 decision separates three kinds of work:

- **document preservation:** produce a faithful textual and visual package;
- **scientific interpretation:** create focused, evidence-grounded reports;
- **data organization:** convert those reports into stable consumer files.

This separation gives each phase a narrower context, an inspectable output,
and a failure that can be diagnosed without repeating the entire pipeline.

## 4. Core principles

### 4.1 Preserve before interpreting

The first phase must preserve the paper, not summarize it. Information should
be removed only when there is a deliberate, testable reason.

### 4.2 One scientific responsibility per agent

Architecture and results are related but different extraction problems. They
receive the same source package and operate independently.

### 4.3 Evidence is part of every claim

A useful extraction is not only an answer. It must show where the answer came
from and whether the source is explicit, visually inferred, derived, ambiguous,
or missing.

### 4.4 Intermediate outputs may be expressive

The architecture and results reports may use Markdown and a stable reporting
template. They are not forced directly into the final exhaustive JSON schema.
This preserves nuance and lowers serialization pressure during scientific
reasoning.

### 4.5 Strictness belongs at stable boundaries

Strict validation is retained for identifiers, provenance, references,
required top-level sections, and mechanical invariants. Domain details remain
flexible until the benchmark shows that a stricter representation is both
useful and reliable.

### 4.6 Agentic behaviour is bounded

An agent may decide whether it needs visual evidence and which declared assets
to inspect. It does not receive an unrestricted tool loop, browse arbitrary
files, call unknown models, or retry itself indefinitely.

### 4.7 Deterministic code does mechanical work

Python may copy, hash, render, route, validate, split, and persist information.
It must not decide what geometry a figure represents, which result is most
important, or how to repair missing scientific information.

### 4.8 Sequential execution is the baseline

There is no parallel model execution in v3. Sequential execution makes traces,
resource use, debugging, and learning easier to follow.

### 4.9 Missing information is a valid outcome

The pipeline must distinguish between a failed extraction and an honestly
incomplete source. It must not turn plausible engineering defaults into facts.

### 4.10 Implement only current needs

No empty packages, speculative adapters, placeholder scripts, generic workflow
engine, or future-phase abstractions are created in advance.

## 5. System boundary

### 5.1 Input

The initial product processes one scientific paper in PDF form per run.

### 5.2 Final consumer-facing outputs

The run produces exactly two final domain documents:

- `antenna_architecture.json`
- `antenna_results.json`

All Markdown reports, manifests, request traces, raw responses, validation
reports, and failure records are internal audit artefacts.

### 5.3 Initial non-goals

The first v3 baseline does not include:

- CST or another solver integration;
- automatic simulation or optimization;
- geometry repair;
- reviewer or critic models;
- automatic retry or fallback models;
- semantic RAG or a vector database;
- corpus-wide search;
- general graph digitization;
- multi-paper scheduling;
- parallel execution;
- a web application;
- a general-purpose agent framework.

These features require a reproducible failure, a measured benefit, and a new
architectural decision before implementation.

## 6. Conceptual flow

```text
Scientific PDF
    |
    v
Deterministic run initialization and page rendering
    |
    v
NuExtract3 document-conversion phase
  - B = ceil(page_count / 8) sequential model calls
  - consecutive batches of up to 8 pages
    |
    v
DocumentPackage
  - source PDF
  - source manifest and lifecycle status
  - pages/pages.json
  - complete document.md
  - ordered page images as visual fallback
  - per-batch raw responses
  - per-batch traces for successful parses
    |
    +------------------------------+
    |                              |
    v                              v
Architecture agent run            Results agent run
  reads Markdown and package        reads Markdown and package
  metadata                          metadata
  may request exact assets           may request exact assets
  writes evidence report             writes evidence report
    |                              |
    +---------------+--------------+
                    |
                    v
Canonicalization call
  reads both reports + identity metadata
  organizes, does not reinterpret source
                    |
                    v
Deterministic validation and split
        |                           |
        v                           v
antenna_architecture.json   antenna_results.json
```

The two agent phases are independent in meaning but run sequentially in the
baseline. A failure in one does not erase the successful artefacts of the
other. Canonicalization starts only after both reports satisfy their phase
gates.

## 7. Phase A - deterministic run initialization

This phase makes the run reproducible before any model is called.

It is responsible for:

- copying the input PDF into an isolated run;
- computing document and artefact hashes;
- recording model-independent run metadata;
- rendering every PDF page in source order;
- rendering PNG page images at 170 DPI by default;
- preserving one-based source page identity;
- creating a place for phase status, traces, reports, and failures.

It performs no document interpretation and no page selection. Ordered full-page
renders are the current visual assets. They provide the visual fallback for
compound figures, scanned papers, and content that Markdown cannot represent.

## 8. Phase B - NuExtract3 document conversion

### 8.1 Responsibility

NuExtract3 is used as a document converter, not as the final scientific data
extractor. Its task is to create a faithful Markdown representation from all
rendered pages.

### 8.2 Input

The input is the complete ordered sequence declared in `pages/pages.json`.
Consecutive batches contain at most eight PNG pages. Batches are processed
sequentially, and every rendered page is processed exactly once in source
order. Batching is a context-limit control. It is not relevance selection.

For `page_count` pages, the number of document-conversion calls is:

```text
B = ceil(page_count / 8)
```

### 8.3 Required output

The current `DocumentPackage` is the set of run artefacts produced by Phases 1
and 2:

- `manifest.json`, which records source and run identity;
- `status.json`, which records lifecycle state;
- `pages/pages.json`, which records ordered page identity and metadata;
- ordered rendered page images;
- `document_conversion/document.md`;
- one raw response for each batch response received;
- one trace for each successfully parsed batch response.

There is no additional unified package manifest in Phase 2.

### 8.4 Markdown policy

`document.md` is the canonical textual representation for the two scientific
agents. Each batch requests preservation of:

- headings and prose;
- tables as Markdown or embedded HTML when that is the faithful form;
- equations in a readable textual or LaTeX form;
- figure and table captions;
- labels, symbols, units, footnotes, and references.

Tables and equations remain in the Markdown. The baseline does **not** create
table crops or equation crops. NuExtract3's representation is preferred over a
second OCR or parsing path that could introduce disagreement.

The implementation reads Markdown from `choices[0].message.content` in an
OpenAI-compatible response envelope. It joins successful batch Markdown
mechanically in source order with two newline characters between batches. It
does not insert page ID markers. Page identity remains in `pages/pages.json`.

### 8.5 Figure policy

The current phase does not materialize separate figure files. Rendered
full-page images are the available visual fallback. Separate figure
materialization remains deferred until evidence shows that a concrete consumer
needs it.

### 8.6 Manifest policy

Phase 2 retains the existing source manifest and nested pages manifest. It does
not create a new unified `DocumentPackage` manifest. The source manifest ties
the run to the preserved PDF. The pages manifest records ordered page
identifiers, paths, dimensions, sizes, checksums, and rendering settings.

Safe asset resolution and consumer-specific package validation belong in Phase
3, when the first concrete asset consumer is implemented. That phase should
build on the existing manifests and add only the boundary its consumer needs.

### 8.7 Completion condition

The conversion succeeds only after every batch response is parsed and one
combined `document.md` is written. For each response received, the raw response
is written before parsing. The trace is written only after parsing succeeds.
Conversion stops at the first failed batch, writes no final `document.md`, and
marks the lifecycle phase as failed. A transport failure can occur before a raw
response exists.

The implementation has no retry, fallback, parallel batch calls, or
configurable `max_tokens`.

## 9. Phase C - bounded visual-asset inspection

### 9.1 Why a tool is used

Passing every page image to every agent increases context pressure and makes it
harder to know which visual evidence influenced the answer. Passing no images
would make geometry and graph interpretation unreliable.

The compromise is to give each agent the complete Markdown and the package
metadata required by its consumer, then let it request specific full-page
assets when the text is insufficient. Separate figure assets may be added only
if Phase 3 evidence justifies them.

### 9.2 Tool responsibility

The asset tool is deterministic. It:

- receives exact page asset identifiers declared in `pages/pages.json`;
- checks that the request is valid and within configured limits;
- loads the corresponding full pages, plus separate figures only if a later
  evidence-based increment adds them;
- returns the images with their source metadata in stable order;
- records the request, selected assets, and hashes.

The tool does not search semantically, rank figures, infer relevance, interpret
pixels, or call another model in the baseline.

### 9.3 Bounded interaction

Each scientific agent may use at most one visual-inspection tool round in the
initial architecture. During that round it can request one or more exact assets
and state a focused question for each request.

After the assets are returned, the same scientific model interprets them and
must finish its report. It cannot open an unbounded observe-act loop.

If benchmark evidence later shows that one round is systematically
insufficient, the limit may be revisited explicitly. It is not silently raised
by implementation code.

### 9.4 Meaning of a tool call versus a model call

This design has one **logical agent run** for architecture and one for results.
However, a tool-based run normally contains two model inference turns:

1. the model reads `document.md` and the accepted package metadata, then emits
   a tool request;
2. deterministic code executes the tool and returns the images;
3. the same model is invoked again with the tool result and emits the report.

The tool execution itself is not a model call. If the agent decides that no
image is required, its logical run finishes with one model call. Although an
SDK may expose this as one high-level run, the underlying model endpoint is
usually invoked again after the tool result.

Using a separate VLM inside the tool is not the v3 baseline. That alternative
would add another reasoning boundary and another model call. The selected
architecture or results model should itself be able to receive the returned
images.

## 10. Phase D - architecture agent

### 10.1 Initial input

The agent initially receives only:

- the complete `document.md`;
- the source and pages manifests, or the consumer-specific package view defined
  in Phase 3;
- a focused architecture role and reporting template;
- access to the bounded asset-inspection tool.

It does not receive the results report, the final JSON schema, or every image by
default.

### 10.2 Responsibility

The architecture agent determines what the paper supports about the antenna's
physical and electromagnetic construction, including at an appropriate level:

- the selected final, fabricated, or measured design and any ambiguity in that
  selection;
- components and their roles;
- geometry, dimensions, coordinate relationships, repetitions, and boolean
  intent;
- materials and reported material properties;
- feeds, ports, vias, grounds, substrates, layers, and environmental context;
- source-supported equations or derivations that determine geometry;
- missing or illegible reconstruction-critical information;
- conflicts between text, table, equation, caption, and figure evidence.

It must not invent conventional dimensions, material properties, layer
thicknesses, solver settings, or geometric details merely because they are
typical for an antenna family.

### 10.3 Output

The output is `architecture_evidence_report.md`, not the final architecture
JSON.

The report uses stable sections and claim identifiers, but it remains
expressive Markdown. Each material claim must carry evidence or be explicitly
marked as derived, ambiguous, missing, or proposed but unapplied.

The report should be understandable and reviewable without reading a large
schema. It should preserve disagreement and uncertainty rather than forcing a
premature construction.

### 10.4 Evidence

Evidence may refer to:

- a Markdown section and a short source-faithful excerpt;
- a table or equation label represented in the Markdown;
- a full-page asset identifier from `pages/pages.json`;
- a caption and source page;
- multiple sources when a claim depends on their combination.

The exact evidence syntax is defined and tested during the architecture-agent
phase. It must remain resolvable against the accepted package artefacts.

## 11. Phase E - results agent

### 11.1 Initial input

The results agent receives the same initial source interface as the
architecture agent:

- the complete `document.md`;
- the source and pages manifests, or the consumer-specific package view defined
  in Phase 3;
- a focused results role and reporting template;
- access to the bounded asset-inspection tool.

It does not receive or depend on `architecture_evidence_report.md`.

### 11.2 Responsibility

The results agent inventories and associates all reported outcomes, including:

- simulated, measured, and analytical results;
- the design or variant to which each result belongs;
- setup, conditions, frequency range, units, and representation;
- explicitly reported scalar values, ranges, points, and trends;
- graph-only or partially legible results without fabricating samples;
- comparisons, baselines, parameter sweeps, and prototype variants;
- discrepancies that the paper itself discusses;
- missing associations, ambiguity, or illegibility.

Measured and simulated traces are distinct observations, not contradictions by
default. A result that is visible only in a graph should remain graph-grounded
unless the source provides safe numeric values.

### 11.3 Output

The output is `results_evidence_report.md`.

Like the architecture report, it uses stable sections and claim identifiers
without being forced into the final strict JSON. Every reported result must be
associated with evidence and with its design or setup when the paper supports
that association.

## 12. Phase F - canonicalization call

### 12.1 Purpose

Canonicalization is an organization task. It converts two already grounded
reports into a predictable, shallow data envelope.

### 12.2 Input boundary

The canonicalizer receives:

- `architecture_evidence_report.md`;
- `results_evidence_report.md`;
- package identity and reference metadata defined by the consuming phases;
- a simple, flexible output contract.

It does not receive the source PDF, page images, figure assets, or the complete
`document.md`. This boundary prevents the last call from becoming another
scientific extraction pass.

### 12.3 Responsibility

The canonicalizer:

- preserves the reports' claims and evidence references;
- separates architecture content from results content;
- normalizes only agreed presentation conventions;
- retains unresolved, ambiguous, and missing information;
- records how every report claim was handled;
- produces one combined response suitable for deterministic splitting.

It must not add a new antenna interpretation, choose between conflicting
source claims, invent missing values, or discard a claim because it does not
fit a narrow field.

### 12.4 Contract strategy

The final model-facing contract is intentionally shallow. Strictness is used
for the stable envelope, document identity, claim accounting, evidence
references, and the presence of the architecture and results sections.

Domain content may use flexible attributes and typed categories that can evolve
from benchmark evidence. The initial contract is not intended to be a universal
CAD ontology or an exhaustive antenna-results standard.

A claim-disposition audit must make silent loss detectable: every claim in the
two reports is either represented, merged with an explicitly identified claim,
or retained as unresolved/rejected with a reason.

### 12.5 Output and deterministic split

The model returns one combined canonical envelope. Deterministic code then:

- validates the shallow contract;
- validates document and evidence references;
- verifies claim disposition coverage;
- copies the architecture section into `antenna_architecture.json`;
- copies the results section into `antenna_results.json`;
- writes a canonicalization validation report.

Python does not rewrite the scientific content during this split.

## 13. Model roles and selection

The institutional model list provides candidates, not guaranteed capabilities.
Exact model identifiers, multimodal input, tool-call syntax, context limits,
structured-output behaviour, and latency must be measured against the real
endpoint.

### 13.1 Document converter

`nuextract3` is the intended converter because it has shown strong preservation
of Markdown tables and equations. It is evaluated on document fidelity and
asset linkage, not on its ability to author the final antenna schema.

### 13.2 Architecture and results agents

Gemma 4 and Qwen 3.6 are the initial candidates discussed for the two
scientific roles. A candidate is eligible for the asset-tool design only if the
deployed endpoint can return tool calls and later accept image tool results.

The selection must use frozen inputs and scientific assertions. Model name,
size, or general reputation is insufficient. The same model may win both roles,
or different models may win if the benchmark justifies the operational cost.

Other available multimodal-capable models may be tested only after their actual
endpoint capability is established. A text-only model cannot be the baseline
scientific agent when visual assets are required.

### 13.3 Canonicalizer

The canonicalizer may use a smaller or faster text model if it demonstrates:

- faithful claim preservation;
- reliable shallow-schema compliance;
- no unsupported scientific additions;
- stable separation of architecture and results;
- acceptable latency.

Model choice is deferred to the canonicalization benchmark. Reusing the
winning scientific model is acceptable for the first baseline if it reduces
variables; optimization can follow measured correctness.

### 13.4 Embedding and coding models

The available embedding models are not part of the single-paper baseline,
because the full Markdown is supplied and no semantic retrieval layer is
planned. A coding-specialized model may assist development but is not assigned
a production scientific role without evaluation.

## 14. Normal call budget

The word “call” must be recorded precisely. The system distinguishes logical
phase execution, model inference calls, and deterministic tool executions.

For a paper with `page_count` rendered pages, define:

```text
B = ceil(page_count / 8)
```

| Logical phase | Normal model calls | Deterministic tool executions |
| --- | ---: | ---: |
| NuExtract3 document conversion | B | 0 |
| Architecture agent run | 1 if no image; 2 if assets are requested | 0 or 1 |
| Results agent run | 1 if no image; 2 if assets are requested | 0 or 1 |
| Canonicalization | 1 | 0 |
| **Normal total** | **B + 3 to B + 5** | **0 to 2** |

This is four logical model-driven phases, not a promise of exactly four HTTP
requests. The later full-pipeline estimates are `B + 3` when neither
scientific agent uses visual assets, `B + 4` when one agent uses visual assets,
and `B + 5` when both use visual assets. Every run records the observed number
of model calls and tool executions.

No reviewer, repair, retry, fallback, or hidden visual-model call is included
in this budget.

## 15. Evidence, provenance, and auditability

The implemented Phase 2 trace records the requested model, temperature, mode,
thinking setting, HTTP status, `finish_reason`, usage when available, and model
latency. The raw response is a separate artefact and is persisted first. Phase
2 does not yet record prompt versions or input hashes in the per-batch trace.

Later model-driven phases should preserve enough information to reproduce and
inspect their own boundaries. The exact trace fields should be added with each
concrete consumer rather than claimed in advance.

Phase 2 refuses to overwrite existing conversion outputs. A later acceptance
boundary may define a package identity or immutability rule when a concrete
consumer requires it.

Evidence references must remain source-faithful. Normalizing a unit or name in
the final JSON must not erase the exact wording or value reported by the paper.

## 16. Failure and continuation policy

The baseline has no automatic retries.

- If run initialization or document conversion fails, both scientific agents
  and canonicalization are skipped.
- Document conversion stops at the first failed batch. It preserves raw
  responses already received and traces for successfully parsed batches, but
  it does not write the final `document.md`.
- If the architecture agent fails, its failure is preserved and the independent
  results agent may still run sequentially.
- If the results agent fails, a successful architecture report remains valid.
- Canonicalization is skipped until both reports have passed their gates.
- If canonicalization or final validation fails, the two evidence reports
  remain available and are not rewritten.

Re-execution of a failed phase must be explicit and must record whether its
model, prompt, inputs, or settings changed. A workflow engine and transparent
resume cache are not part of the first baseline.

## 17. Context-limit policy

The default is to send the complete `document.md` to each scientific agent. No
RAG, top-k selection, or relevance classifier precedes the agents.

Measured runs showed that one request per document can reach the endpoint
context limit on larger papers. Reducing the default rendering resolution from
200 DPI to 170 DPI helped but did not solve every case. Fixed, source-ordered
batches of up to eight pages completed larger papers that had previously ended
with `finish_reason="length"`.

Batching changes the request boundary, not the document scope. Every page is
still converted exactly once, in order, and no relevance classifier or page
selector precedes conversion.

## 18. Development phases and chat boundaries

Each phase below is intended to have its own ChatGPT Project chat and its own
short-lived Git branch. The phase chat may contain several small commits, but
only one commit is implemented and reviewed at a time.

| Phase | Suggested chat | Architectural outcome |
| --- | --- | --- |
| 0 | `00 - Foundation and project rules` | Clean repository, authority rules, and executable development baseline |
| 1 | `01 - Run lifecycle and source preservation` | Deterministic run, PDF identity, ordered page renders, and failures |
| 2 | `02 - NuExtract3 DocumentPackage` | Ordered page renders, combined Markdown, per-batch diagnostics, and lifecycle state |
| 3 | `03 - Bounded asset inspection` | Consumer-specific package validation, safe asset resolution, and one-round agent control |
| 4 | `04 - Architecture agent` | Evidence-grounded architecture Markdown report |
| 5 | `05 - Results agent` | Evidence-grounded results Markdown report |
| 6 | `06 - Canonicalization and final contracts` | Shallow combined response, claim accounting, and two JSON outputs |
| 7 | `07 - End-to-end runner` | One sequential command with clear phase and failure behaviour |
| 8 | `08 - Scientific benchmark and baseline` | Measured model decisions, regression evidence, documentation, and release tag |

The detailed branches, commits, tests, and exit gates are defined in
`01_IMPLEMENTATION_ROADMAP_V3.md`.

## 19. Fixed decisions

The following decisions should not be reopened in an implementation chat
without new empirical evidence:

- create a new clean repository for v3 and retain v2 as an archive/baseline;
- process one paper per run;
- keep execution sequential;
- render every page as PNG at 170 DPI by default;
- divide the complete ordered page sequence into consecutive batches of up to
  eight pages;
- make `B = ceil(page_count / 8)` sequential NuExtract3 calls;
- join successful batch Markdown mechanically with two newline characters;
- keep tables and equations in `document.md`;
- do not create table or equation crops;
- use rendered full-page images as the current visual fallback;
- maintain page identity in `pages/pages.json`, not model-generated Markdown
  markers;
- persist each received raw response before parsing and write a trace only
  after a successful parse;
- write final Markdown only after all batches succeed;
- initially pass `document.md` and the required package metadata to each
  scientific agent;
- let each agent request exact visual assets through a deterministic tool;
- allow at most one asset-tool round per scientific agent in the baseline;
- use the same scientific model to interpret returned images;
- keep architecture and results interpretation independent;
- use Markdown evidence reports as intermediate outputs;
- canonicalize only after both reports exist;
- keep the final model-facing schema shallow and flexible;
- produce exactly two final JSON domain outputs;
- prohibit silent claim loss, unsupported scientific inference, automatic
  retry, fallback models, RAG, parallelism, and speculative framework code.

## 20. Decisions intentionally deferred

The following are decided in their named phase, from tests and benchmark
evidence:

- whether separate figure materialization provides enough value for a concrete
  consumer;
- the consumer-specific validation boundary for package artefacts;
- the minimal package view needed for safe asset routing;
- the endpoint's tool-call and image-result protocol;
- visual asset count and payload limits;
- the exact Markdown report templates and claim-reference notation;
- whether Gemma 4, Qwen 3.6, or another proven multimodal candidate fills each
  scientific role;
- which model canonicalizes most faithfully;
- the minimal shallow final JSON contract;
- the exact CLI surface;
- whether explicit single-phase rerun support is needed after baseline use.

Deferred does not mean “build an abstraction now.” The smallest implementation
is chosen when the relevant phase begins.

## 21. Architectural invariants

An implementation conforms to v3 only if all of the following remain true:

1. Document conversion processes every rendered page exactly once and in
   source order.
2. Tables and equations are not routed through a second crop/OCR path.
3. Architecture and results agents initially see the complete Markdown and
   the package metadata required by their accepted consumer boundary.
4. Visual asset selection is performed by the requesting agent using exact
   page asset identifiers.
5. The asset tool is deterministic and does not hide another model call.
6. Each scientific agent has at most one tool round in the baseline.
7. Scientific reports precede final JSON serialization.
8. Canonicalization organizes claims but does not reread or reinterpret the
   source paper.
9. Every report claim has an auditable disposition.
10. Deterministic code never repairs scientific meaning.
11. The runner is sequential and reports actual model-call counts using `B`.
12. Conversion failure preserves completed diagnostics and writes no final
    Markdown.
13. No missing value is silently replaced with an engineering default.
14. No future phase is represented by placeholder code.

## 22. Definition of architectural success

The v3 baseline is architecturally successful when a representative paper can
be processed into:

- a human-reviewable `DocumentPackage` made from the existing run artefacts;
- an architecture report whose claims resolve to text or requested visual
  evidence;
- a results report that preserves variants, setups, and result origins;
- two shallow, valid, consumer-facing JSON files with no silently lost claims;
- a complete trace showing which calls and assets produced each artefact.

Schema validity alone is not success. The scientific benchmark must also show
that important architecture features and reported results are preserved, and
that insufficient papers produce explicit uncertainty rather than plausible
fabrication.
