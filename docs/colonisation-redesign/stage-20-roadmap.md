# Stage 20 - Provenance-Backed Planning Cockpit Roadmap

## Purpose

Stage 20 turns the completed Stage 19 test-environment safety foundation into a
user-visible planning programme. Its job is to make ED-Finder better at
explaining source evidence, warehouse status, map context, and build-sequence
decisions inside the colonisation planner without silently activating deferred
production or canonical paths.

Stage 20 planning is authorized by Stage 19AY. Stage 20 implementation is not
yet executed by this roadmap PR.

## Background From Stage 19

Stage 19 proved the safety foundation needed before planning could move
forward:

- strict project-state authority and invalid-state rejection;
- DB isolation guardrails and secret redaction tests;
- Test Fortress/local CI parity recovery;
- disposable PostgreSQL constraint coverage for the pilot path;
- operator-script contract coverage;
- safe-target enforcement;
- bounded staging-only EDSM source-run loading;
- Stage 19AR 25-row baseline;
- Stage 19AS-AU 100-row controlled expansion;
- Stage 19AU read-only verification;
- Stage 19AV 250-row expanded source-run staging pilot;
- Stage 19AX read-only AV verification;
- Stage 19AY test-environment and safety-programme closeout.

The verified Stage 19AV/AX evidence remains:

- AV source run:
  `stage19av-expanded-source-run-staging-pilot-48688d9d46067867`;
- AV bridge:
  `source_runs:stage19av-expanded-source-run-staging-pilot-48688d9d46067867`;
- AV artifact checksum:
  `09652a1c6e6ad661415f535a713432b0d3a76aef5b8c931c0b1874e1c52604f4`;
- AV artifact path:
  `/home/brian/.local/share/ed-finder/operator-artifacts/stage-19av/stage19av_edsm_import_20260615T062102Z.json`;
- row counts: `250` read, `250` staged, `0` rejected, `0` skipped;
- staging prerequisite source run:
  `7fe4382fbde60752e026b576d92e0352c01d85799613884d2b2e7ee57cd3f5f3`;
- canonical writes performed: `false`.

Stage 19 remains paused. Stage 19 production activation, canonical apply,
rebaseline, scheduler/service activation, production-like DB execution, and any
next Stage 19 write lane remain deferred and separately gated.

## Primary Objective

Stage 20 has exactly one primary objective:

> Build a provenance-backed colonisation planning cockpit that lets users and
> operators understand source evidence, warehouse freshness, map context, and
> build-sequence tradeoffs through typed, reviewable, read-only contracts before
> any production activation or canonical promotion is considered.

This objective is meaningful because it connects the completed evidence chain
to the product surface. It is achievable without Stage 19 production
activation because the first work uses contracts, fixtures, read-only
snapshots, and frontend/API boundaries rather than canonical writes. It is
testable because every checkpoint must preserve explicit no-write boundaries
and add contract/static/integration coverage.

## In Scope

- Typed API and UI contracts for source-run, artifact, warehouse-status, and
  planner-evidence summaries.
- Runtime validation at API/UI boundaries where it protects against drift.
- Read-only operator/source-run status surfaces that explain evidence and
  safety state.
- Map architecture hardening around projection, viewport, layers, hit testing,
  overlays, and performance.
- Planner data model work for CP curve, build sequence, body slot assignment,
  materials/unlocks summaries, and explicit user actions.
- Export/operator packs that summarize a plan and its evidence as Markdown,
  JSON, CSV, or shareable snapshots.
- Static guardrails, fixture-backed tests, and integration tests that prove
  Stage 20 does not start deferred Stage 19 production actions.

## Out Of Scope Unless Separately Approved

- Stage 19 canonical apply.
- Stage 19 rebaseline.
- Stage 19 production activation.
- Production scheduler, timer, or service enablement.
- Production-like DB execution.
- Direct host `5432` targets.
- Unbounded source ingestion.
- Broad source acquisition or staging-loader expansion.
- Migrations unless a later Stage 20 checkpoint explicitly authorizes a
  schema-design PR.
- Canonical promotion of staged or warehouse rows.
- Silent planner mutation from imported, observed, projected, inferred, or
  warehouse evidence.
- Automatic Simulation Preview execution.
- Automatic Suggested Build generation, loading, or ranking changes.
- Broad unrelated refactors or speculative rewrites.

## Workstream Ranking

| Rank | Workstream | Value | Dependencies | Risk | DB writes? | Depends on deferred Stage 19 production activation? | Independent delivery | Estimated checkpoint size |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | API/UI contract and runtime validation | Prevents drift between backend, frontend, operator status, and planner evidence before implementation spreads. | Stage 19AY, existing API models, operator visibility docs. | Medium: over-modeling or stale fixtures. | No. | No. | Yes. | Medium. |
| 2 | Read-only source-run and warehouse status integration | Turns Stage 19 proof into understandable operator and user status without SSH or artifact spelunking. | Stage 19AO/AQ patterns, Stage 19AV/AX proof, warehouse runbook. | Medium: accidental DB/query scope creep. | No writes; read-only only if separately approved. | No. | Yes. | Medium. |
| 3 | Map architecture and performance foundation | Makes the map a central planning surface without a renderer rewrite. | Current canvas map, Stage 19X accepted package direction. | Medium/high: visual regressions and interaction drift. | No. | No. | Yes. | Large. |
| 4 | Planner data model and build-sequence UX | Gives users a coherent CP curve, sequence, slot, material, unlock, and tradeoff model. | Stage 17P boundaries, Stage 17M/N planner shell, facility catalogue. | High: hidden mechanics or auto-mutation. | No. | No. | Yes. | Large. |
| 5 | Export/operator pack builder | Makes plans reviewable outside the UI and prepares future operator workflows. | Planner data model and evidence contracts. | Medium: leaking private paths or treating evidence as truth. | No. | No. | Yes. | Medium. |
| 6 | Data freshness and source scheduling preparation | Defines eventual freshness and automation surfaces. | Read-only status contract; future operator approval. | High: could blur into scheduler enablement. | No writes in Stage 20 planning; scheduler disabled. | Partly. | Only as design/prep. | Medium. |
| 7 | Canonical promotion preparation | Keeps future production paths reviewable. | Separate Stage 19 production decision. | High: canonical scope creep. | Not in Stage 20 without new approval. | Yes. | No for this Stage 20 baseline. | Deferred. |
| 8 | Broad user-facing search/discovery retuning | Useful later, but less directly connected to the completed Stage 19 proof chain. | Search advisories and performance evidence. | Medium: ranking drift and DB query load. | No writes, but may need DB-backed integration tests later. | No. | Later. | Medium/large. |

## Checkpoint Plan

Stage 20 should use five substantial checkpoints rather than many micro-gates.

| Checkpoint | Purpose | Deliverables | Acceptance criteria | Dependencies | Risk | DB access required? | Write capability required? | Expected PR shape |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage 20A - Provenance cockpit implementation contract | Establish typed contracts, fixture data, and guardrails before feature code spreads. | Stage 20 contract doc; API/Pydantic and UI/Zod contract inventory or fixture plan; static tests proving no write authority; first route/component ownership map. | One primary contract set is named; fixtures are non-secret; Stage 19 deferred work remains false; no DB/operator commands; first implementation slices are reviewable. | Stage 19AY and this roadmap. | Medium: contract too broad or too abstract. | No. | No. | Docs/static-test with optional schema/type files only if explicitly scoped. |
| Stage 20B - Read-only evidence and status surfaces | Implement the first user/operator-visible read-only status path from source-run, artifact, and warehouse evidence contracts. | API read-model or fixture-backed endpoint; UI surface; redacted artifact/source display; no-action safety state. | Status is visible, bounded, redacted, and read-only; no import, staging, canonical, scheduler, or DB write path exists. | Stage 20A. | Medium: query scope and artifact-path leakage. | Maybe read-only in a later approved checkpoint; no writes. | No. | Focused API/UI/tests PR. |
| Stage 20C - Map planning surface foundation | Refactor the current canvas map around projection, viewport, layers, hit-test, overlays, and performance without renderer replacement. | Layer ownership model; regression tests; LOD/batching plan or implementation; no planner mutation side effects. | Current interactions remain stable; map can carry evidence/planner overlays; performance has measurable guardrails. | Stage 20A, current map code. | Medium/high: UI regression. | No. | No. | Frontend architecture and tests PR. |
| Stage 20D - Planner sequence and CP curve cockpit | Make build sequence, CP curve, body-slot assignment, materials/unlocks summaries, and tradeoffs explicit in the planner. | Planner data model; CP curve/timeline UI; explicit edit controls; evidence labels. | Users can understand sequence/tradeoffs; no automatic Preview, generation, load, role mechanics, or hidden scoring changes. | Stage 20A and existing planner shell. | High: mechanics drift or silent mutation. | No. | No. | Frontend/API contract and tests PR. |
| Stage 20E - Export/operator pack and closeout readiness | Produce reviewable planning outputs and close Stage 20 when the cockpit is coherent. | Markdown/JSON/CSV/share snapshot contract; export UI; closeout doc/tests. | Exports separate planned, projected, observed, inferred, and warehouse evidence; no private paths or secrets; Stage 19 deferred production work remains deferred. | Stage 20B-D. | Medium. | No. | No. | Feature plus closeout PR. |

## First Executable Checkpoint

The first executable checkpoint is:

`Stage 20A - Provenance cockpit implementation contract`

Purpose:

- define the typed API/UI contract for the first provenance-backed planning
  cockpit surface;
- identify the exact fixture and validation strategy;
- map ownership between operator/source-run status, warehouse evidence,
  planner evidence, and frontend presentation;
- add static tests that prove Stage 20 planning does not authorize DB writes,
  Stage 19 operator commands, canonical apply, rebaseline, scheduler/service
  work, production activation, or Stage 20 feature implementation outside the
  checkpoint scope.

Stage 20A is not another empty decision checkpoint. It should leave the repo
with an implementation contract that the next API/UI PR can execute against.

Stage 20A contract checkpoint output:

- `docs/colonisation-redesign/stage-20a-provenance-cockpit-implementation-contract.md`
- fixture payloads under `tests/fixtures/stage20a/`
- static guardrails proving the contract remains docs/static-only and does not
  authorize deferred Stage 19 production work

Stage 20B read-only status surface output:

- `docs/colonisation-redesign/stage-20b-readonly-evidence-status-surfaces.md`
- one fixture-backed aggregation route for the provenance cockpit
- one Evidence Workspace provenance panel
- focused backend/frontend tests proving the slice remains read-only

Stage 20C map foundation output:

- `docs/colonisation-redesign/stage-20c-map-planning-surface-foundation.md`
- planner `Map` workspace mode built on the existing map primitives
- timeline-layer ownership and summary in the shared `MapTab`
- focused frontend/static tests proving the map surface remains read-only

Stage 20D sequence cockpit output:

- `docs/colonisation-redesign/stage-20d-planner-sequence-cp-curve-cockpit.md`
- planner `Sequence` workspace mode
- explicit build-order list plus CP summary/timeline/repair reuse after manual preview
- focused frontend/static tests proving the cockpit remains explicit and read-only

Stage 20E export and closeout output:

- `docs/colonisation-redesign/stage-20e-export-operator-pack-closeout-readiness.md`
- planner `Export` workspace mode
- Markdown/JSON/CSV review pack builders with separated evidence sections
- final closeout readiness/completion record proving Stage 19 deferred production work remains deferred

## Acceptance Criteria For Stage 20

Stage 20 is complete when:

- users can inspect provenance-backed evidence/status in the planning cockpit
  without treating report-only evidence as canonical truth;
- the map can act as a stable planning surface with layered overlays and
  bounded performance expectations;
- the planner can explain build sequence, CP curve, body-slot assignment,
  materials/unlocks summaries, and tradeoffs through explicit user actions;
- exported/operator packs preserve source separation and avoid secrets/private
  runtime paths;
- API and UI contracts are typed and covered by static/fixture tests;
- integration tests cover the user-visible happy path and at least one
  missing/stale/unknown evidence path;
- no Stage 19 production activation, canonical apply, rebaseline,
  scheduler/service activation, production-like DB execution, or unbounded
  ingestion is claimed complete;
- any DB access introduced by a later checkpoint is read-only unless a separate
  explicit approval authorizes otherwise;
- authority docs record the final Stage 20 status and any remaining deferred
  work.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Stage 20 accidentally reopens Stage 19 production activation. | Keep Stage 19 production activation, canonical apply, rebaseline, scheduler/service work, and next write lanes false in authority and tests. |
| Contracts become abstract documents that do not guide implementation. | Stage 20A must name routes, models, fixtures, validation points, ownership, and test assertions. |
| Read-only status work grows into live DB/operator work. | Require explicit checkpoint approval before any DB access and keep write capability false. |
| Map work becomes a renderer rewrite. | Keep the current canvas path first; refactor projection, viewport, layers, hit-test, overlays, LOD, and batching before evaluating PixiJS. |
| Planner work silently changes mechanics. | Preserve Stage 17P boundaries: no automatic Preview, no automatic Suggested Build generation/load, no hidden scoring or CP changes. |
| Evidence leaks secrets or private host paths. | Use redacted paths, fixture data, and tests for secret/path handling. |

## Authority Model

Stage 20 authority is planning-only at kickoff:

- Stage 20 planning baseline prepared: `true`;
- Stage 20 implementation started: `false`;
- first executable checkpoint:
  `Stage 20A - Provenance cockpit implementation contract`;
- Stage 19 remains paused: `true`;
- Stage 19 production activation complete: `false`;
- canonical apply complete: `false`;
- rebaseline complete: `false`;
- scheduler enabled: `false`;
- DB writes authorized by this roadmap: `false`;
- Stage 19 operator commands authorized by this roadmap: `false`.

Future Stage 20 checkpoints must update authority when they materially change
scope, implementation status, or safety state.

## Relationship To Deferred Stage 19 Production Activation

Stage 20 planning may proceed because Stage 19AY closed the
test-environment/safety programme as complete for planning. That does not
complete or authorize Stage 19 production activation.

Stage 20 may design and build read-only product surfaces that display
provenance-backed evidence, freshness, and safety state. Stage 20 may not
promote staged rows, run canonical apply, run rebaseline, enable scheduler or
service units, acquire new source data, or perform production-like DB execution
without a separate explicit approval.

## Completion Definition

Stage 20 is complete when the provenance-backed planning cockpit is coherent
enough to use for planning decisions, the map and planner surfaces are covered
by typed contracts and tests, evidence/export output is reviewable, and
authority explicitly records that deferred Stage 19 production actions remain
separate unless a later approved lane changes that state.
