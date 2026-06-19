# Stage 24 - Read-only Evidence Adoption And Governance Roadmap

## Status

Stage 24 planning baseline is prepared.

Stage 24A is complete as a contract-only checkpoint.

Stage 24B is complete as the first narrow discoverability implementation slice.

Stage 24C is the next implementation checkpoint.

## Background From Stage 23

Stage 23 is closed.

The completed Stage 23 sequence delivered a read-only planner evidence
baseline:

- `warehouse_planner_evidence/v1` exists as the dedicated endpoint;
- selected-system evidence can be exposed through a governed
  `evidence_envelope`;
- bounded Stage 19BB staging provenance is visible as report-only context;
- the planner UI now renders explicit available, unavailable, not-evaluated,
  and unknown evidence states;
- bounded staging remains visibly non-canonical and not full EDSM coverage.

Stage 23 is not being extended. Stage 24 is the new explicit post-Stage-23
control document.

## Primary Objective

Stage 24 has exactly one primary objective:

> Turn the completed Stage 23 read-only planner evidence baseline into a
> discoverable, explainable, and consistently governed product surface without
> authorizing Stage 19 execution, DB writes, canonical apply, rebaseline, or
> scheduler/service activation.

## Why This Is The Next Control

Stage 23 solved the baseline evidence problem, but not the full adoption
question.

The repo now has a stable read-only evidence contract and visible planner
surface. The next highest-value control is therefore to make that baseline
easier to understand, navigate, compare, and safely consume across planner and
related read-only review surfaces before any future write-capable planning is
considered.

This keeps the next control useful while preserving the strongest default
safety posture:

- planning baseline only;
- no implementation started;
- no write-capable lane authorized;
- no Stage 19 execution authorized.

## Candidate Workstream Summary

| Candidate | Value | Dependencies | Risk | DB writes required? | Stage 19 reauthorization required? |
| --- | --- | --- | --- | --- | --- |
| Read-only planner evidence hardening after Stage 23 | Medium/high. Improves trust and consistency on top of the completed baseline. | Completed Stage 23 endpoint, envelope, and planner UI. | Medium: could blur into feature creep if not bounded. | No. | No. |
| Canonical promotion / canonical apply planning | High later value, but operationally sensitive. | Separate canonical boundary review, write-lane design, approval flow, audit model. | High: easily blurs into write authorization. | Yes for any real lane. | Yes. |
| Production-staging expansion beyond 10,000 rows | Useful only for later warehouse scale-up. | Separate Stage 19 control, target approval, operator lane, artifact policy. | High: operational and write-capable. | Yes. | Yes. |
| Scheduler/service activation planning | High later operational value. | Source-run automation contracts, runtime target, failure/alerting design. | High: easily misread as production enablement. | Not necessarily for planning, but operationally sensitive. | Yes. |
| UX/product adoption of the read-only evidence baseline | High immediate value for users and reviewers. | Completed Stage 23 read-only baseline and existing planner UI. | Low/medium: stays read-only if kept narrow. | No. | No. |
| Data-quality/source-governance control | High strategic value for source trust and future ingestion rules. | Source matrix, provenance rules, artifact governance, later warehouse scope. | Medium/high: can sprawl into ingestion or write governance. | No for planning, yes for later execution lanes. | Possibly later, not for planning. |

## Selected Workstream

The selected Stage 24 workstream is:

`UX/product adoption of the read-only evidence baseline`

This is the best next control because it:

- directly builds on the completed Stage 23 baseline;
- has clear user and reviewer value now;
- remains compatible with a planning-only, no-write posture;
- does not require Stage 19 reauthorization;
- does not blur into canonical promotion, staging expansion, or scheduler work.

## In Scope

- Read-only planner evidence discoverability and explanation planning.
- Evidence-status, source-class, and source-semantics adoption planning across
  planner-facing surfaces.
- Read-only UX and contract-governance planning for how bounded staging is
  presented and compared.
- Static tests and authority updates that keep Stage 24 reviewable and safe.
- Defining the first executable checkpoint for later repo work.

## Out Of Scope Unless Separately Approved

- Stage 19 execution.
- Any new Stage 19 execution lane.
- Source acquisition.
- DB writes.
- Canonical writes.
- Canonical apply.
- Rebaseline.
- Scheduler, service, or timer activation.
- Production activation planning that implies authorization.
- Production-staging expansion beyond the recorded Stage 19BB ladder.
- Broad unrelated product redesign.
- Implementation of Stage 24 feature work in this planning PR.

## Safety Boundaries

Stage 24 planning is docs/static-only at kickoff.

The Stage 24 baseline does not authorize:

- Stage 19 operator commands;
- Stage 19BB rerun;
- DB mutation;
- canonical apply;
- canonical writes;
- rebaseline;
- scheduler/service/timer enablement;
- source-file commits;
- runtime-artifact commits.

Private paths, DSNs, secrets, and runtime artifact contents remain excluded from
Git.

## First Executable Checkpoint

The first executable checkpoint is:

`Stage 24A - Read-only evidence adoption implementation contract`

Purpose:

- define the exact planner and adjacent read-only surfaces that should consume
  the Stage 23 evidence baseline next;
- name the contract ownership, copy expectations, and evidence-state comparison
  rules;
- define fixture/test expectations before any Stage 24 implementation begins;
- prove Stage 24A still does not authorize Stage 19 execution, DB writes,
  canonical apply, rebaseline, or scheduler/service activation.

Stage 24A is now recorded in
`docs/colonisation-redesign/stage-24a-readonly-evidence-adoption-contract.md`.

That contract document:

- names the in-scope Stage 24B surfaces;
- separates candidate Stage 24C surfaces from out-of-scope work;
- defines ownership seams;
- defines evidence-state language and source-semantics expectations;
- defines fixture and test expectations;
- keeps Stage 24A contract-only.

## Proposed Checkpoint Plan

| Checkpoint | Purpose | Deliverables | Acceptance criteria |
| --- | --- | --- | --- |
| Stage 24A - Read-only evidence adoption implementation contract | Define exact Stage 24 contract scope before implementation spreads. | Stage 24A contract doc, fixture/test plan, ownership map, guardrail assertions. | Complete. One primary contract set is named; no write-capable lane is authorized; the next implementation slice is reviewable. |
| Stage 24B - Planner evidence discoverability surfaces | Apply read-only evidence explanation patterns to the most important planner surfaces. | Narrow planner/doc/test slice only. | Complete. Users can locate and interpret evidence posture more easily without implying canonical truth. |
| Stage 24C - Cross-surface evidence consistency | Align wording and review posture between planner evidence surfaces and adjacent read-only views. | Narrow contract/UI/doc/test slice only. | Source semantics remain consistent, explicit, and non-canonical across read-only surfaces. |
| Stage 24D - Closeout or next-control decision | Close Stage 24 or explicitly hand off to a later control if needed. | Closeout or handoff doc, authority updates, tests. | Stage 24 ends without silently authorizing writes or reopening Stage 19. |

## Acceptance Criteria

Stage 24 planning baseline is acceptable when:

- Stage 23 remains closed;
- Stage 24 exists as the new explicit post-Stage-23 control document;
- Stage 24 has one primary objective;
- the selected workstream is explicit and ranked above the rejected candidates;
- the first executable checkpoint is named;
- Stage 19 execution remains unauthorized;
- DB writes remain unauthorized;
- canonical apply remains unauthorized;
- rebaseline remains unauthorized;
- scheduler/service activation remains disabled;
- bounded staging remains report-only and non-canonical unless a later control
  explicitly changes that state.

Stage 24B is now recorded in
`docs/colonisation-redesign/stage-24b-planner-evidence-discoverability.md`.

That implementation slice:

- stays inside the Stage 24A in-scope planner surfaces;
- improves discoverability in the primary planner workspace and evidence card;
- keeps the dedicated endpoint preferred;
- keeps provenance fallback fallback-only;
- leaves Stage 24C as future cross-surface work.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Stage 24 gets treated as a hidden write-planning lane. | Keep planning-only status explicit and keep all write-capable authorizations false in docs and tests. |
| Stage 24 silently reopens Stage 23 instead of succeeding it. | State explicitly that Stage 23 is closed and Stage 24 is the new control. |
| Read-only adoption planning grows into broad product redesign. | Keep the selected workstream limited to evidence adoption and governance. |
| Bounded staging is mistaken for canonical truth. | Preserve explicit report-only, non-canonical, not-full-coverage language in the control document and tests. |
| Candidate options are forgotten and later reintroduced informally. | Record the candidate workstream summary and why the chosen workstream won. |

## Authority Model

Stage 24 authority is planning-only at kickoff:

- implementation started: `false`
- write-capable lane authorized: `false`
- Stage 19 execution authorized: `false`
- canonical apply authorized: `false`
- rebaseline authorized: `false`
- scheduler/service activation enabled: `false`

## Relationship To Stage 19BB

Stage 19BB remains a completed bounded staging-only evidence dependency.

Its evidence may continue to appear inside read-only planner evidence surfaces,
but Stage 24 does not authorize:

- rerunning Stage 19BB;
- widening the Stage 19BB ladder;
- using bounded staging as canonical truth;
- treating bounded staging as full EDSM coverage.

## Relationship To Canonical Apply

Stage 24 does not authorize canonical apply.

Any future canonical promotion or canonical-apply control must begin under a
separate explicit control document.

## Relationship To Rebaseline

Stage 24 does not authorize rebaseline.

## Relationship To Scheduler/Service Activation

Stage 24 keeps scheduler, service, and timer activation disabled.

## Closeout Criteria

Stage 24 can close only when:

- the selected read-only adoption workstream is either completed or explicitly
  handed off;
- Stage 23 remains historical/closed;
- Stage 19 remains separately gated unless another later control explicitly
  changes that state;
- no write-capable lane has been silently authorized by Stage 24 planning or
  implementation checkpoints.
