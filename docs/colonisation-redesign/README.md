# ED-Finder Colonisation Redesign Docs

This folder contains the planning, architecture, forensic-review, and implementation-history documents for ED-Finder's colonisation and Colony Planner work.

## Read This First

Start here for any new colonisation work:

1. [`stage-21-roadmap.md`](./stage-21-roadmap.md) - active post-20 roadmap and current control baseline.
2. [`stage-21b-to-21f-stage17-stage18-burn-down.md`](./stage-21b-to-21f-stage17-stage18-burn-down.md) - Stage 21 progress record showing how Stage 17 and Stage 18 backlog items were burned down or reclassified.
3. [`stage-21-closeout.md`](./stage-21-closeout.md) - Stage 21 completion record and validation summary.
4. [`stage-20-roadmap.md`](./stage-20-roadmap.md) - completed Stage 20 roadmap and checkpoint plan.
5. [`stage-20a-provenance-cockpit-implementation-contract.md`](./stage-20a-provenance-cockpit-implementation-contract.md) - Stage 20A implementation-contract checkpoint for the first provenance cockpit slice.
6. [`stage-20b-readonly-evidence-status-surfaces.md`](./stage-20b-readonly-evidence-status-surfaces.md) - Stage 20B read-only provenance cockpit implementation slice in the Evidence Workspace.
7. [`stage-20c-map-planning-surface-foundation.md`](./stage-20c-map-planning-surface-foundation.md) - Stage 20C planner map foundation and timeline-layer ownership.
8. [`stage-20d-planner-sequence-cp-curve-cockpit.md`](./stage-20d-planner-sequence-cp-curve-cockpit.md) - Stage 20D planner sequence and CP tradeoff cockpit.
9. [`stage-20e-export-operator-pack-closeout-readiness.md`](./stage-20e-export-operator-pack-closeout-readiness.md) - Stage 20 export pack, closeout readiness, and completion record.
10. [`stage-17p-current-state-forward-plan.md`](./stage-17p-current-state-forward-plan.md) - current Colony Planner baseline and continuing product boundaries.
11. [`engine-roadmap.md`](./engine-roadmap.md) - broad engine history and delivered stage summaries.
12. [`enrichment-roadmap.md`](./enrichment-roadmap.md) - station/body/ring enrichment, warehouse, and operator-roadmap work.
13. Specific historical stage docs only when the task directly touches that feature.

If an older document's "recommended next stage" conflicts with Stage 17P, follow Stage 17P unless intentionally researching historical context.

## Current Control Documents

[`stage-21-roadmap.md`](./stage-21-roadmap.md) is the active post-20 control document. It reconciles what remains open after Stage 20, carries forward the unfinished planner trust work, and keeps Stage 19 production activation, canonical apply, rebaseline, and scheduler/service work deferred.

[`stage-21b-to-21f-stage17-stage18-burn-down.md`](./stage-21b-to-21f-stage17-stage18-burn-down.md) records how the first Stage 21 implementation pass burned down the remaining Stage 17 planner backlog and reconciled which Stage 18 items were already delivered as warehouse/operator groundwork.

[`stage-21-closeout.md`](./stage-21-closeout.md) records that Stage 21 is complete and captures the final validation state plus the new live Stage 18H planner bridge.

[`stage-20-roadmap.md`](./stage-20-roadmap.md) is the completed Stage 20 planning baseline. It records the provenance-backed planning cockpit objective, five Stage 20 checkpoints, and the boundaries preserved while that work landed.

[`stage-20a-provenance-cockpit-implementation-contract.md`](./stage-20a-provenance-cockpit-implementation-contract.md) is the active Stage 20A contract checkpoint. It names the first provenance cockpit contract set, fixture payloads, and concrete backend/frontend ownership without starting feature delivery.

[`stage-20b-readonly-evidence-status-surfaces.md`](./stage-20b-readonly-evidence-status-surfaces.md) records the first implemented provenance cockpit surface: a fixture-backed read-only endpoint and Evidence Workspace panel that preserve all deferred-production guardrails.

[`stage-20c-map-planning-surface-foundation.md`](./stage-20c-map-planning-surface-foundation.md) records the planner-facing map foundation: a dedicated `Map` workspace mode plus timeline-layer ownership on top of the existing map primitives.

[`stage-20d-planner-sequence-cp-curve-cockpit.md`](./stage-20d-planner-sequence-cp-curve-cockpit.md) records the dedicated `Sequence` workspace mode that exposes build order and CP tradeoffs without auto-running preview or mutating the plan.

[`stage-20e-export-operator-pack-closeout-readiness.md`](./stage-20e-export-operator-pack-closeout-readiness.md) records the dedicated `Export` workspace mode, reviewable Markdown/JSON/CSV pack builders, and the final Stage 20 closeout state.

[`stage-17p-current-state-forward-plan.md`](./stage-17p-current-state-forward-plan.md) remains the active Colony Planner product-boundary baseline.

It supersedes the old assumption that the project should simply continue from Stage 17A's original sequence. Later work has already delivered or changed large parts of that path, including validated slot prediction, Raven-style canvas planning, projection comparison, trust recovery, existing infrastructure awareness, and enrichment warehouse foundations.

## Active / Living Docs

| Document | Status | Purpose |
|---|---|---|
| [`stage-21-roadmap.md`](./stage-21-roadmap.md) | Active Stage 21 control | Post-20 roadmap reconciliation, active work queue, checkpoints, and preserved deferred-production boundaries. |
| [`stage-21b-to-21f-stage17-stage18-burn-down.md`](./stage-21b-to-21f-stage17-stage18-burn-down.md) | Active Stage 21 progress record | Records how Stage 17 planner backlog and Stage 18 warehouse/operator backlog were reduced, reclassified, or marked delivered groundwork. |
| [`stage-21-closeout.md`](./stage-21-closeout.md) | Completed Stage 21 closeout record | Records Stage 21 completion, validation state, and the live read-only Stage 18H warehouse bridge outcome. |
| [`stage-20-roadmap.md`](./stage-20-roadmap.md) | Completed Stage 20 control | Planning baseline, primary objective, workstreams, checkpoints, and Stage 19 deferred-production boundaries for the completed cockpit. |
| [`stage-20a-provenance-cockpit-implementation-contract.md`](./stage-20a-provenance-cockpit-implementation-contract.md) | Completed Stage 20A contract | First provenance cockpit contract set, fixture plan, route/component ownership, and Stage 20B handoff. |
| [`stage-20b-readonly-evidence-status-surfaces.md`](./stage-20b-readonly-evidence-status-surfaces.md) | Completed Stage 20B implementation record | First read-only provenance cockpit route and Evidence Workspace surface, still bounded away from DB writes and operator execution. |
| [`stage-20c-map-planning-surface-foundation.md`](./stage-20c-map-planning-surface-foundation.md) | Completed Stage 20C implementation record | Planner `Map` workspace mode, timeline-layer ownership, and shared map-surface reuse without planner mutation. |
| [`stage-20d-planner-sequence-cp-curve-cockpit.md`](./stage-20d-planner-sequence-cp-curve-cockpit.md) | Completed Stage 20D implementation record | Dedicated `Sequence` workspace mode for build order, CP timeline, and repair guidance without auto-running preview. |
| [`stage-20e-export-operator-pack-closeout-readiness.md`](./stage-20e-export-operator-pack-closeout-readiness.md) | Completed Stage 20E completion record | Dedicated `Export` workspace mode, reviewable pack builders, and final Stage 20 closeout readiness/completion. |
| [`stage-17p-current-state-forward-plan.md`](./stage-17p-current-state-forward-plan.md) | Active Colony Planner control | Current state, source-authority warning, non-negotiable boundaries, and next work queue. |
| [`../reference/colonisation/README.md`](../reference/colonisation/README.md) | Source authority entry point | Committed source hierarchy, inventory placeholders, and future Codex prompt snippet for mechanics-heavy work. |
| [`engine-roadmap.md`](./engine-roadmap.md) | Living historical roadmap | Broad colonisation engine evolution and delivered stage summaries. |
| [`enrichment-roadmap.md`](./enrichment-roadmap.md) | Active for enrichment | Guarded station enrichment, body/ring enrichment, offline warehouse, reconciliation, and operator-status roadmap. |
| [`stage-19ar-canonical-baseline.md`](./stage-19ar-canonical-baseline.md) | Active guardrail | Canonical Stage 19AR baseline identity, fresh project DB recovery failure mode, rejected substitute, and Stage 19AS-AU gate. |
| [`simulation-preview-ui-architecture.md`](./simulation-preview-ui-architecture.md) | Architecture reference | Simulation Preview / Colony Planner component ownership and delivered UI architecture notes. |

## Historical / Reference Docs

These files are useful evidence and rationale, but they should not be treated as the current roadmap unless Stage 17P points to them.

| Document | Status | Use |
|---|---|---|
| [`stage-17a-colony-planner-intelligence-forward-plan.md`](./stage-17a-colony-planner-intelligence-forward-plan.md) | Partly superseded | Source alignment, original trust/slot/picker roadmap, RavenColonial boundary. Do not follow its old next-stage order blindly. |
| [`stage-16-colony-role-model-plan.md`](./stage-16-colony-role-model-plan.md) | Historical/reference | Role terminology and inferred/declared/observed role boundaries. |
| [`stage-15-planner-workspace-redesign-plan.md`](./stage-15-planner-workspace-redesign-plan.md) | Historical/reference | Topology-first workspace rationale and early dedicated-planner target architecture. |
| [`stage-10a-build-plan-structure-picker-body-layout-feasibility.md`](./stage-10a-build-plan-structure-picker-body-layout-feasibility.md) | Historical/reference | Earlier build-plan structure picker/body-layout feasibility. |
| [`stage-9b-dedicated-colony-planner-workspace-feasibility.md`](./stage-9b-dedicated-colony-planner-workspace-feasibility.md) | Historical/reference | Early dedicated workspace feasibility. |
| [`stage-8a-colony-planner-ux-prep.md`](./stage-8a-colony-planner-ux-prep.md) | Historical/reference | UX preparation for the planner flow. |
| [`stage-5-9-forensic-structural-ux-wiring-review.md`](./stage-5-9-forensic-structural-ux-wiring-review.md) | Historical/reference | Forensic review of earlier planner/search-tuning structure. |
| [`search-tuning-forensic-review.md`](./search-tuning-forensic-review.md) | Historical/reference | Search tuning analysis; separate from the Colony Planner optimiser path. |

## Cleanup Rule

Do not delete old stage docs by default. They are useful for reconstructing why a boundary, warning, or interaction exists.

Instead:

- Treat Stage 17P as the current roadmap.
- Treat older docs as history/reference.
- Add short superseded notes only when a stale doc is actively misleading future implementation.
- Prefer adding an index/status note over rewriting large historical docs.
- Keep behaviour-changing work out of documentation-only cleanup PRs.

## Source Pack Reminder

Stage 17A identified that the expected reference-pack path was missing from
`main` at the time of review. Stage 17Q adds the committed reference entry
point under [`docs/reference/colonisation/`](../reference/colonisation/),
including source priority, source inventory placeholders, and a Codex prompt
snippet.

The reference entry point does not commit restricted guide files, spreadsheets,
PDFs, screenshots, or third-party assets. Mechanics-heavy work should read the
committed reference docs first, then clearly state whether any direct source
verification used committed docs, attached files, external sources, or
local/operator-only files.
