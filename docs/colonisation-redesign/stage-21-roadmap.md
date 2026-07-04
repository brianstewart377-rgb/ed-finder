# Stage 21 - Planner Trust And Operationalisation Roadmap

> HISTORICAL / SUPERSEDED PLANNING RECORD — NOT CURRENT EXECUTION AUTHORITY
>
> This document is retained for provenance and post-20 planning history.
> It is not an active product-control point and cannot authorise implementation or override live GitHub state.
>
> For current work, read:
> 1. `docs/ai/CURRENT_STAGE.md`
> 2. `docs/DOCUMENTATION_INDEX.md`
> 3. `docs/colonisation-redesign/stage-25-roadmap.md`
> 4. live GitHub branch and PR state

## Purpose

Stage 21 begins after the completed Stage 20 planning cockpit. Its job is to
turn the new cockpit from a safe implementation achievement into a trustworthy,
operational, read-only planning surface while keeping deferred Stage 19
production work paused.

Stage 21 is a planning and implementation roadmap for post-20 work. It does
not reopen canonical apply, rebaseline, scheduler activation, production-like
DB execution, or any next Stage 19 write lane.

Stage 21 is also not a license to invent a fresh pile of unrelated scope. Its
main function is to gather the still-open work that already exists across the
Stage 17P queue and the post-Stage-20 cockpit follow-up into one clear active
plan.

## Why Stage 21 Exists

Stage 20 is complete. Users now have a provenance, map, sequence, and export
cockpit inside the planner. That closes the Stage 20 objective, but it does not
close the broader roadmap.

What remained unfinished at kickoff was:

- the planner trust and UX hardening work described in
  `stage-17p-current-state-forward-plan.md`;
- some Stage 20 surfaces that were still fixture-backed or bounded to
  static/read-only data contracts;
- the need to reconcile older Stage 17/18 queue language against code that had
  already delivered much of the warehouse/report-only path;
- Stage 19 production activation remaining deliberately deferred.

Stage 21 therefore creates one authoritative post-20 control point.

## Relationship To Earlier Stages

Stage 21 does not pretend that all historical stage labels were completed in
strict numeric order. It explicitly reconciles them:

- Stage 17Q is effectively complete through the committed source-authority docs
  in `docs/reference/colonisation/`.
- Stage 18A is effectively complete through the read-only enrichment operator
  status integration.
- Stage 17R, 17S, 17T, and 17U were the clearest planner-facing unfinished
  work and were resumed inside Stage 21 rather than left as orphaned backlog
  labels.
- Stage 18B-18G are substantially represented already in the
  warehouse/report-only/admin path and should be treated as delivered
  groundwork, not untouched future work.
- Stage 19 remains paused. Stage 21 must not silently convert warehouse or
  provenance work into production activation.

## Primary Objective

Stage 21 has exactly one primary objective:

> Turn the completed Stage 20 cockpit into a trustworthy, operational,
> provenance-aware planning surface by closing the highest-value planner trust
> gaps, replacing fixture-only read paths where safe, and reconciling the
> roadmap into one explicit post-20 control document without reopening deferred
> Stage 19 production lanes.

## In Scope

- Post-20 roadmap reconciliation and authority cleanup.
- Planner trust audit and user-facing trust-language hardening.
- Existing infrastructure and occupied-slot UX hardening.
- Suggested Builds explanation and strategy-advisor improvements.
- Role and strategy integration cleanup where roles remain advisory.
- Bounded replacement of fixture-backed Stage 20 read-only surfaces with real
  read-only sources where safe and already available.
- Read-only export/operator-pack hardening and artifact polish.
- Static and integration tests that prove Stage 21 does not reopen deferred
  Stage 19 production work.

## Out Of Scope Unless Separately Approved

- Stage 19 production activation.
- Stage 19 canonical apply.
- Stage 19 rebaseline.
- Scheduler, timer, or service enablement.
- Production-like DB execution.
- Direct host `5432` targets.
- Unbounded source acquisition.
- Broad staging-loader expansion.
- Silent planner mutation from imported, observed, projected, inferred, or
  warehouse evidence.
- Automatic Simulation Preview execution.
- Automatic Suggested Build generation or loading.
- Role-aware optimiser ranking or role-aware simulation mechanics.

## Workstream Ranking

| Rank | Workstream | Value | Dependencies | Risk | Write capability required? |
| --- | --- | --- | --- | --- | --- |
| 1 | Post-20 roadmap reconciliation and authority lock | Removes ambiguity about what is complete, what is deferred, and what is next. | Stage 20 completion, Stage 17P, current README/index. | Low. | No. |
| 2 | Planner trust audit and trust-language repair | Highest-value user-facing honesty work across planner surfaces. | Stage 17P boundaries, current planner shell. | Medium. | No. |
| 3 | Existing infrastructure and slot reasoning UX hardening | Makes availability and blockage states understandable. | Current planner slot/infrastructure surfaces. | Medium. | No. |
| 4 | Suggested Builds strategy advisor pass | Improves usefulness without reopening mechanics. | Existing deterministic candidate generation. | Medium/high. | No. |
| 5 | Role + strategy integration cleanup | Makes declared, inferred, and observed strategy easier to review. | Current role review surfaces. | Medium. | No. |
| 6 | Stage 20 read-only operationalisation | Replaces fixture-only status surfaces with bounded real read-only inputs where safe. | Stage 20 cockpit, current read-only evidence/status contracts. | Medium/high. | No writes; read-only only. |
| 7 | Warehouse/operator visibility expansion | Continues Stage 18B-18G with better operator evidence visibility. | Existing enrichment and warehouse docs. | Medium. | No writes. |
| 8 | Deferred Stage 19 production decision preparation | Keeps the future write lane reviewable without opening it now. | Separate approval only. | High. | Not in Stage 21 baseline. |

## Checkpoint Plan

Stage 21 should use six checkpoints.

| Checkpoint | Purpose | Deliverables | Acceptance criteria |
| --- | --- | --- | --- |
| Stage 21A - Post-20 roadmap reconciliation and authority lock | Create one clear post-20 control baseline. | Stage 21 roadmap; README updates; authority entries; static tests. | Stage 21 becomes the active roadmap; Stage 20 is clearly complete; 17Q and 18A are classified; 17R/17S/17T/17U are explicitly carried forward. |
| Stage 21B - Planner trust audit | Verify the planner still behaves honestly on awkward systems and mixed evidence states. | Audit doc, trust issue list, focused UI/test fixes. | Unknown stays unknown; evidence categories remain visibly separate; stale or unresolved states do not render as confirmed truth. |
| Stage 21C - Existing infrastructure and slot reasoning hardening | Make slot occupancy and blockage states understandable. | UX updates, explanatory copy/tooltips, tests. | Users can tell why a slot is unavailable and whether existing infrastructure is confirmed, inferred, unresolved, or unknown. |
| Stage 21D - Suggested Builds strategy advisor pass | Improve candidate usefulness and explanation quality. | Candidate explanation and strategy-context improvements. | Suggested Builds explain tradeoffs clearly and remain explicit/manual. |
| Stage 21E - Role and strategy integration cleanup | Make declared, inferred, observed, and planner strategy easier to compare. | Planner role-review refinements and tests. | Roles improve guidance without changing mechanics, scoring, CP, or ranking. |
| Stage 21F - Read-only cockpit operationalisation and closeout | Replace safe fixture-only surfaces with bounded real read-only sources where appropriate and close Stage 21. | Closeout doc, updated tests, operationalisation notes. | The cockpit is more operational without opening write lanes; deferred Stage 19 production work remains explicitly false. |

## First Executable Checkpoint

The first executable checkpoint is:

`Stage 21A - Post-20 roadmap reconciliation and authority lock`

Purpose:

- declare Stage 20 complete and historical rather than still-active planning;
- define the post-20 objective, checkpoints, and boundaries;
- classify Stage 17Q and Stage 18A as effectively complete;
- carry Stage 17R, 17S, 17T, and 17U into the active work queue;
- keep Stage 19 production activation, canonical apply, rebaseline, scheduler,
  and write-lane work deferred in authority and tests.

## Recommended Execution Order

The best order after Stage 21A is:

1. Stage 21B - Planner trust audit
2. Stage 21C - Existing infrastructure and slot reasoning hardening
3. Stage 21D - Suggested Builds strategy advisor pass
4. Stage 21E - Role and strategy integration cleanup
5. Stage 21F - Read-only cockpit operationalisation and closeout

This order prioritises user trust and planner clarity before broader warehouse
visibility or any future production-lane decision.

## Acceptance Criteria For Stage 21

Stage 21 is complete when:

- the repo has one explicit post-20 control document;
- the planner communicates uncertainty, provenance, and evidence separation
  consistently;
- existing infrastructure and slot reasoning are understandable from the UI;
- Suggested Builds explain strategy and tradeoffs more clearly;
- role/strategy review is clearer without changing mechanics truth;
- safe Stage 20 read-only surfaces use bounded real data where appropriate;
- no Stage 19 production activation, canonical apply, rebaseline,
  scheduler/service activation, production-like DB execution, or write-lane
  authorization is claimed complete.

## Authority Model

Stage 21 starts as planning-authorized only:

- Stage 21 planning baseline prepared: `true`;
- Stage 21 implementation started: `false`;
- first executable checkpoint:
  `Stage 21A - Post-20 roadmap reconciliation and authority lock`;
- Stage 20 complete: `true`;
- Stage 19 remains paused: `true`;
- Stage 19 production activation complete: `false`;
- canonical apply complete: `false`;
- rebaseline complete: `false`;
- scheduler enabled: `false`;
- DB writes authorized by this roadmap: `false`;
- Stage 19 operator commands authorized by this roadmap: `false`.

## Completion Definition

Stage 21 is complete when the planner is substantially more trustworthy and
operational than the raw Stage 20 cockpit, the roadmap is internally
reconciled, the remaining planner backlog from the Stage 17P queue is
explicitly advanced, and authority still records that deferred Stage 19
production actions remain separate unless a later approved lane changes that
state.

## Current Stage 21 Progress

The completed Stage 21 execution pass:

- reconciled Stage 21 as the active post-20 control document;
- advanced Stage 17R/17S through planner trust and slot/infrastructure clarity
  fixes;
- advanced Stage 17T through Suggested Builds review-focus improvements;
- advanced Stage 17U through clearer declared-vs-observed role review;
- operationalised one Stage 20 read-only evidence slice by merging live
  observed-fact totals into the provenance cockpit panel;
- advanced Stage 18H by wiring a live report-only warehouse bridge into the
  main planner workspace through the sanitized provenance cockpit route;
- recorded the Stage 17/18 backlog burn-down in
  `stage-21b-to-21f-stage17-stage18-burn-down.md`;
- closed Stage 21 in `stage-21-closeout.md`.
