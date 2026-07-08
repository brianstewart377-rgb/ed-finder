# Stage 24A - Read-only Evidence Adoption Implementation Contract

## Status

Stage 24A is complete as a contract-only checkpoint.

Stage 24B implementation is not performed here.

## Purpose

Stage 24A defines the exact implementation contract for adopting the completed
Stage 23 read-only planner evidence baseline across planner and adjacent
read-only surfaces.

This checkpoint exists to make Stage 24B reviewable, bounded, and testable
before any broader adoption work begins.

## Relationship To Stage 24 Roadmap

Stage 24A is the first executable checkpoint named in
`docs/ROADMAP.md`.

It does not replace the Stage 24 roadmap. It narrows that roadmap into one
reviewable implementation contract so the next slice can stay small and
consistent.

## Stage 23 Baseline Being Adopted

Stage 23 is closed and is not being extended.

The Stage 23 baseline being adopted is:

- `warehouse_planner_evidence/v1` as the dedicated selected-system evidence
  endpoint;
- additive `evidence_envelope` status, source classes, and source semantics;
- bounded Stage 19BB staging provenance as report-only review context;
- planner workspace adoption of explicit available, unavailable,
  not-evaluated, and unknown states;
- explicit non-canonical and non-full-coverage wording for bounded staging.

## Surfaces Inventory

Stage 24A classifies the current and adjacent read-only evidence surfaces as
follows.

### In Scope For Stage 24B

- Primary planner workspace evidence surface:
  `frontend/src/features/colony-planner/ColonyPlannerWorkspace.tsx`
- Planner evidence presentation component:
  `frontend/src/features/colony-planner/WarehouseEvidenceCard.tsx`
- Frontend mapping layer from dedicated endpoint to planner view model:
  `frontend/src/features/colony-planner/warehouseEvidenceBridge.ts`
- Type-level contract surface:
  `frontend/src/types/api.ts`
- Documentation/readme discoverability for the read-only evidence baseline.

### Candidate For Stage 24C

- System-detail review surfaces that can reference planner evidence posture
  without turning system detail into a second planner workspace.
- Simulation and export-readiness surfaces that need consistent evidence-state
  explanation or review posture comparisons.
- Adjacent API consumers that should compare evidence status and source
  semantics consistently with planner surfaces.
- Cross-surface consistency guidance for provenance fallback wording where the
  dedicated endpoint is unavailable.

### Out Of Scope For Stage 24

- Operator-facing execution, ingestion, or activation surfaces.
- Canonical-apply controls or review surfaces that imply authorization.
- Rebaseline planning or execution surfaces.
- Scheduler/service/timer activation surfaces.
- Source acquisition surfaces.
- Broad planner product redesign.
- New warehouse ingestion or write-capable lanes.

## Ownership Map

Stage 24A assigns ownership at the contract level.

| Concern | Primary ownership |
| --- | --- |
| API evidence envelope shape and semantics | `apps/api/src/warehouse_planner_evidence.py`, `apps/api/src/warehouse_planner_evidence_models.py`, `apps/api/src/warehouse_planner_evidence_provider.py` |
| Frontend contract mapping from API to UI view model | `frontend/src/features/colony-planner/warehouseEvidenceBridge.ts` |
| Planner evidence card copy and user-facing state language | `frontend/src/features/colony-planner/WarehouseEvidenceCard.tsx` |
| Dedicated-endpoint preference vs provenance fallback behavior | `frontend/src/features/colony-planner/ColonyPlannerWorkspace.tsx` plus the bridge |
| Bounded staging warnings and review-only limits | dedicated contract + planner evidence card |
| Unavailable / not_evaluated / unknown wording | evidence envelope contract + planner evidence card |
| Fixtures and regression tests | `tests/test_docs_roadmap.py`, `frontend/src/features/colony-planner/WarehouseEvidenceCard.test.tsx`, `frontend/src/features/colony-planner/ColonyPlannerWorkspace.test.tsx` |

## Evidence-State Language Contract

Stage 24 surfaces should use stable user-facing language for evidence status.

### Status Terms

- `available`:
  `Available. Selected-system evidence is present as read-only review context only.`
- `unavailable`:
  `Unavailable. No approved bounded staging evidence is linked to this selected system.`
- `not_evaluated`:
  `Not evaluated in this runtime. The staging boundary was not safely queryable for this request.`
- `unknown`:
  `Unknown. Selected-system evidence has not been established.`

### Source Class Terms

- `canonical`:
  `Canonical evidence`
- `observed_facts`:
  `Observed facts`
- `bounded_staging`:
  `Bounded staging evidence`
- `derived_report`:
  `Derived report`
- `unavailable`:
  `Unavailable`

### Source Semantics Terms

- `canonical_truth`:
  `Canonical truth remains separate`
- `observed_report`:
  `Observed report`
- `bounded_staging_evidence`:
  `Bounded staging evidence`
- `report_only_review_context`:
  `Report-only review context`
- `not_full_coverage`:
  `Not full EDSM coverage`

### Required Bounded Staging Guidance

When bounded staging is shown as available, Stage 24 surfaces should preserve
all of the following:

- `Bounded staging evidence`
- `Report-only review context`
- `Not canonical truth`
- `Not full EDSM coverage`
- `Limited to approved Stage 19BB row-cap evidence`

## Source Semantics Contract

Stage 24 surfaces must preserve the governed meaning of the Stage 23 baseline:

- canonical evidence is not the same thing as bounded staging evidence;
- observed-facts evidence is not the same thing as bounded staging evidence;
- derived-report context is still report-only;
- unavailable and unknown are distinct states;
- not-evaluated is not an error state and not a synonym for unavailable;
- selected-system evidence is never a full-coverage claim by default.

## Comparison Rules

Stage 24 surfaces should compare and combine evidence states consistently.

- Canonical evidence vs observed facts:
  show both when both exist; do not collapse observed facts into canonical truth.
- Canonical evidence vs bounded staging:
  canonical remains planner truth, bounded staging remains review-only context.
- Unavailable vs not_evaluated:
  unavailable means no approved bounded staging evidence is linked;
  not_evaluated means the staging boundary was not safely queryable.
- Unknown vs unavailable:
  unknown means selected-system evidence has not been established at all;
  unavailable means a bounded-staging lookup was meaningfully assessed and has
  no approved linked evidence.
- Selected-system evidence vs full coverage:
  any selected-system evidence panel must avoid implying full EDSM coverage.
- Provenance fallback vs dedicated contract:
  if the dedicated endpoint responds, its governed envelope owns the user-facing
  state; provenance fallback is only for endpoint-read failure, not for
  replacing explicit unavailable responses.

## Fixture And Test Plan

Before Stage 24B implementation is accepted, the fixture/test plan should cover:

- available canonical evidence;
- available observed-facts evidence;
- bounded staging available;
- bounded staging unavailable;
- bounded staging not_evaluated;
- unknown selected-system evidence;
- mixed source classes in a single envelope;
- explicit no-canonical-truth claim;
- explicit no-full-coverage claim;
- dedicated-endpoint preferred over provenance fallback when the governed
  contract is available;
- no wording that implies canonical promotion, scheduler activation, or write
  authorization.

Recommended test anchors:

- `tests/test_docs_roadmap.py`
- `frontend/src/features/colony-planner/WarehouseEvidenceCard.test.tsx`
- `frontend/src/features/colony-planner/ColonyPlannerWorkspace.test.tsx`

## Stage 24B Implementation Boundaries

The next implementation slice is:

`Stage 24B - Planner evidence discoverability surfaces`

Stage 24B should stay bounded to the in-scope Stage 24B surfaces listed above.

Stage 24B should not:

- broaden into cross-product redesign;
- introduce operator or write-capable controls;
- widen Stage 19 scope;
- authorize DB writes;
- authorize canonical apply;
- authorize rebaseline;
- enable scheduler/service/timer activation.

## Acceptance Criteria

Stage 24A is complete when:

- one contract document defines the adoption surfaces;
- Stage 24B is named as the next implementation slice;
- ownership seams are explicit;
- evidence-state language is explicit;
- source semantics are explicit;
- comparison rules are explicit;
- fixture/test expectations are explicit;
- Stage 23 remains closed;
- Stage 19 remains separately gated;
- no write-capable lane is silently authorized.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Stage 24A gets treated as Stage 24B implementation. | State repeatedly that Stage 24A is contract-only and Stage 24B is not implemented here. |
| Adjacent surfaces expand too fast. | Separate in-scope Stage 24B surfaces from candidate Stage 24C surfaces and out-of-scope surfaces. |
| Bounded staging is mistaken for canonical truth. | Preserve explicit report-only, non-canonical, and not-full-coverage wording in the contract and tests. |
| Dedicated endpoint vs provenance fallback becomes inconsistent. | Keep the dedicated governed envelope as the owner of visible state whenever it responds. |
| Unknown, unavailable, and not_evaluated collapse into one generic empty state. | Define stable comparison rules and copy expectations for each distinct state. |

## Safety Boundaries

Stage 24A is contract-only.

Stage 24B implementation is not performed here.

Stage 23 remains closed.

Stage 19 remains separately gated.

This checkpoint does not authorize:

- Stage 19 execution;
- Stage 19BB rerun;
- DB writes;
- canonical writes;
- canonical apply;
- rebaseline;
- scheduler, service, or timer activation;
- source acquisition;
- source-file commits;
- runtime-artifact commits.


