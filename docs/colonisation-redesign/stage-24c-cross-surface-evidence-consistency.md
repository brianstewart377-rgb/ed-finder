# Stage 24C - Cross-surface Evidence Consistency

## Status

Stage 24C is complete.

This checkpoint implements one narrow adjacent read-only consistency slice.

## Candidate Surface Inventory

| Surface | Current evidence / review posture | Governed endpoint today? | Expected user value | Implementation size | Duplicate-planner risk | Stage 24C suitability |
| --- | --- | --- | --- | --- | --- | --- |
| System-detail Evidence mode `ProvenanceCockpitPanel` | Already shows read-only source-run, warehouse, planner, and guardrail review context, and already reuses the warehouse evidence card through provenance fallback semantics. | Related context only before Stage 24C. | High: users already review evidence posture here and can benefit from the same governed status/source semantics. | Small. | Low. | Best fit. |
| Simulation/export-readiness `ExportReadinessWorkspaceView` | Shows readiness, operator review, provenance references, and governance context, but not a dedicated selected-system evidence surface. | Related context only. | Medium: useful later for export consistency. | Medium. | Medium. | Candidate later, but larger than necessary for Stage 24C. |
| Adjacent API consumers / export payload builders | Consume provenance-oriented review data for downstream display or export artifacts. | Related context only. | Medium later value. | Medium/high. | Low UI risk but higher contract-spread risk. | Not the smallest first cross-surface slice. |

## Selected Surface

Stage 24C selects the system-detail Evidence mode
`frontend/src/features/system-detail/simulation-preview/provenance/ProvenanceCockpitPanel.tsx`
as the primary adjacent read-only surface.

## Selection Rationale

This was the smallest useful Stage 24C slice because:

- it already presents read-only warehouse and planner review context;
- it already reuses the planner-side warehouse evidence card;
- it can adopt dedicated-endpoint preference without inventing a new product
  surface;
- it stays clearly distinct from a second planner workspace;
- it leaves export-readiness and other adjacent consumers for later only if
  needed.

## Scope

Stage 24C applies the completed Stage 23/24 evidence semantics to the selected
system-detail review surface only.

The delivered slice:

- prefers `warehouse_planner_evidence/v1` for the warehouse-evidence subsection
  of the provenance cockpit panel;
- falls back to provenance-only warehouse evidence when the governed endpoint
  cannot be read;
- preserves the existing read-only provenance cockpit summary, warnings, and
  guardrail areas;
- reuses the Stage 24A/24B evidence-state language and source semantics.

## Reused Evidence Semantics

Stage 24C preserves the existing governed evidence contract.

### Evidence statuses

- `available`
- `unavailable`
- `not_evaluated`
- `unknown`

### Source classes

- `Canonical evidence`
- `Observed facts`
- `Bounded staging evidence`
- `Derived report`
- `Unavailable`

### Semantics and limitations

- `Report-only review context`
- `Canonical truth remains separate`
- `Not canonical truth`
- `Not full EDSM coverage`
- `Limited to approved Stage 19BB row-cap evidence`

## Consistency Guarantees

Stage 24C preserves all of the following across planner and adjacent read-only
review surfaces:

- canonical evidence remains distinct from observed facts;
- canonical evidence remains distinct from bounded staging evidence;
- bounded staging remains review-only context;
- bounded staging never becomes canonical truth;
- selected-system evidence never implies full EDSM coverage;
- unavailable, not_evaluated, and unknown remain distinct user-facing states.

## Dedicated Endpoint And Fallback Rule

If the governed endpoint responds, its evidence envelope owns the user-facing
state in the selected Stage 24C surface.

Provenance fallback is only used when the governed endpoint cannot be read.

Provenance fallback does not overwrite explicit governed `unavailable`,
`not_evaluated`, or `unknown` responses.

## Boundaries Left For Later Controls

Stage 24C does not implement:

- export-generation behavior changes;
- simulation-calculation changes;
- system-detail redesign beyond the selected provenance cockpit panel;
- adjacent API consumer rollout beyond this surface;
- operator-facing execution or activation surfaces;
- canonical-apply controls;
- rebaseline controls;
- scheduler, service, or timer activation controls.

## Safety Boundaries

Stage 23 remains closed.

Stage 19 remains separately gated.

This checkpoint does not:

- rerun Stage 19BB;
- create any new Stage 19 execution lane;
- perform DB writes;
- perform canonical apply;
- perform rebaseline;
- enable scheduler, service, or timer activation;
- introduce source acquisition;
- commit source files;
- commit runtime artifacts.

## Next Checkpoint

Stage 24D is the next checkpoint:

`Stage 24D - Closeout or next-control decision`

