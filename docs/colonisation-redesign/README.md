# ED-Finder Colonisation Redesign Docs

This folder contains the planning, architecture, forensic-review, and implementation-history documents for ED-Finder's colonisation and Colony Planner work.

## Read This First

Start here for any new colonisation work:

1. [`stage-22-roadmap.md`](./stage-22-roadmap.md) - active post-18/20/21 roadmap and current control baseline.
2. [`stage-22b-current-state-planner-evidence-hardening.md`](./stage-22b-current-state-planner-evidence-hardening.md) - completed Stage 22B planner/provenance/warehouse evidence hardening slice.
3. [`stage-22c-operator-artifact-review-and-audit-surfaces.md`](./stage-22c-operator-artifact-review-and-audit-surfaces.md) - completed Stage 22C operator artifact review and export audit surface slice.
4. [`stage-22d-export-and-documentation-governance-consolidation.md`](./stage-22d-export-and-documentation-governance-consolidation.md) - completed Stage 22D export-pack governance and documentation-consolidation slice.
5. [`stage-21-closeout.md`](./stage-21-closeout.md) - Stage 21 completion record and validation summary.
6. [`stage-21-roadmap.md`](./stage-21-roadmap.md) - completed post-20 roadmap and trust/operationalisation plan.
7. [`stage-21b-to-21f-stage17-stage18-burn-down.md`](./stage-21b-to-21f-stage17-stage18-burn-down.md) - Stage 21 progress record showing how Stage 17 and Stage 18 backlog items were burned down or reclassified.
8. [`stage-20-roadmap.md`](./stage-20-roadmap.md) - completed Stage 20 roadmap and checkpoint plan.
9. [`stage-20a-provenance-cockpit-implementation-contract.md`](./stage-20a-provenance-cockpit-implementation-contract.md) - Stage 20A implementation-contract checkpoint for the first provenance cockpit slice.
10. [`stage-20b-readonly-evidence-status-surfaces.md`](./stage-20b-readonly-evidence-status-surfaces.md) - Stage 20B read-only provenance cockpit implementation slice in the Evidence Workspace.
11. [`stage-20c-map-planning-surface-foundation.md`](./stage-20c-map-planning-surface-foundation.md) - Stage 20C planner map foundation and timeline-layer ownership.
12. [`stage-20d-planner-sequence-cp-curve-cockpit.md`](./stage-20d-planner-sequence-cp-curve-cockpit.md) - Stage 20D planner sequence and CP tradeoff cockpit.
13. [`stage-20e-export-operator-pack-closeout-readiness.md`](./stage-20e-export-operator-pack-closeout-readiness.md) - Stage 20 export pack, closeout readiness, and completion record.
14. [`stage-17p-current-state-forward-plan.md`](./stage-17p-current-state-forward-plan.md) - Colony Planner product-boundary baseline and continuing mechanics constraints.
15. [`engine-roadmap.md`](./engine-roadmap.md) - broad engine history and delivered stage summaries.
16. [`enrichment-roadmap.md`](./enrichment-roadmap.md) - station/body/ring enrichment, warehouse, and operator-roadmap work.
17. Specific historical stage docs only when the task directly touches that feature.

If an older document's "recommended next stage" conflicts with Stage 17P, follow Stage 17P unless intentionally researching historical context.

## Current Control Documents

[`stage-22-roadmap.md`](./stage-22-roadmap.md) is the active post-18/20/21 control document. It resets the active roadmap after the completed Stage 18/20/21 sequence, ranks the next read-only planner/operator-review work, and keeps any future Stage 19 production reactivation as a separate gated decision.

[`stage-22b-current-state-planner-evidence-hardening.md`](./stage-22b-current-state-planner-evidence-hardening.md) records the completed Stage 22B slice: runtime fixtures are isolated behind explicit dev/test providers, selected-system evidence stays separate from authority/safety state, and freshness is conservative instead of inferred.

[`stage-22c-operator-artifact-review-and-audit-surfaces.md`](./stage-22c-operator-artifact-review-and-audit-surfaces.md) records the completed Stage 22C slice: the export workspace now includes explicit operator-review and audit surfaces with sanitized references, review focus items, safeguards, and section-coverage checks.

[`stage-22d-export-and-documentation-governance-consolidation.md`](./stage-22d-export-and-documentation-governance-consolidation.md) records the completed Stage 22D slice: export packs now include explicit governance language, exclusions, authority-scope reminders, and committed document references so review context is easier to interpret without competing with current control documents.

[`stage-21-roadmap.md`](./stage-21-roadmap.md) is the completed post-20 control document. It reconciled what remained open after Stage 20, carried forward the unfinished planner trust work, and kept Stage 19 production activation, canonical apply, rebaseline, and scheduler/service work deferred.

[`stage-21b-to-21f-stage17-stage18-burn-down.md`](./stage-21b-to-21f-stage17-stage18-burn-down.md) records how the first Stage 21 implementation pass burned down the remaining Stage 17 planner backlog and reconciled which Stage 18 items were already delivered as warehouse/operator groundwork.

[`stage-21-closeout.md`](./stage-21-closeout.md) records that Stage 21 is complete and captures the final validation state plus the new live Stage 18H planner bridge.

[`stage-18h1-per-system-warehouse-evidence-contract.md`](./stage-18h1-per-system-warehouse-evidence-contract.md) captures the next follow-on contract review for a dedicated per-system warehouse evidence shape that remains read-only, report-only, and separate from planner truth.

[`stage-18h2-readonly-backend-warehouse-evidence-endpoint.md`](./stage-18h2-readonly-backend-warehouse-evidence-endpoint.md) records the read-only backend endpoint scaffold that serves `warehouse_planner_evidence/v1` while still returning conservative unavailable/fallback states whenever no safe per-system evidence is published.

[`stage-18h3-planner-warehouse-fetch-fallback.md`](./stage-18h3-planner-warehouse-fetch-fallback.md) records the planner integration step that prefers the dedicated warehouse evidence contract while preserving the Stage 18H provenance bridge as a read-only fallback.

[`stage-18h4-warehouse-evidence-ux-clarification.md`](./stage-18h4-warehouse-evidence-ux-clarification.md) records the final Stage 18H UX clarification step that makes warehouse evidence freshness, review status, warnings, and source posture explicit in the planner card without changing planner truth.

[`stage-18i-canonical-write-design-review.md`](./stage-18i-canonical-write-design-review.md) records the Stage 18I design-only review for any future canonical apply path. It explicitly does not authorize writes, recommends exact station type promotion as the first narrow future pilot, and requires Stage 18I.5 to settle the database boundary first.

[`stage-18i5-warehouse-database-boundary-review.md`](./stage-18i5-warehouse-database-boundary-review.md) records the Stage 18I.5 boundary decision and preferred Option B direction: a separate `edfinder_enrichment` database on the same Postgres stack if feasible, while staying documentation-only.

[`stage-18j-station-type-canonical-pilot-plan.md`](./stage-18j-station-type-canonical-pilot-plan.md) records the next follow-on pilot plan: a strict station-type-only canonical path that begins with dry-run artifacts and approval/audit/rollback contracts rather than immediate apply.

[`stage-18j-station-type-canonical-pilot-closeout.md`](./stage-18j-station-type-canonical-pilot-closeout.md) records the current repo state for Stage 18J: the bounded station-type-only canonical pilot is implemented, remains tightly scoped, and does not imply general production apply authorization.

[`stage-18t-canonical-safety-test-environment.md`](./stage-18t-canonical-safety-test-environment.md) records the delivered canonical safety environment around the Stage 18J-class write path: dedicated CI coverage, explicit test dependencies, a local one-command runner, and disposable Postgres rehearsal with permission-boundary tests.

[`stage-18j-q-production-reconciliation-artifact-readiness.md`](./stage-18j-q-production-reconciliation-artifact-readiness.md) records the next follow-on checkpoint after 18T: determine whether a suitable read-only/report-only production reconciliation artifact exists before any future production dry-run planning can proceed.

[`stage-18j-q2-readonly-production-reconciliation-plan.md`](./stage-18j-q2-readonly-production-reconciliation-plan.md) records the next follow-on after 18J-Q: the exact later operator command path and pre-run safety checks for generating that report-only reconciliation artifact, still without running it.

[`stage-18j-q3-readonly-production-reconciliation-artifact.md`](./stage-18j-q3-readonly-production-reconciliation-artifact.md), [`../operations/stage-18j-q4-operator-access-packet.md`](../operations/stage-18j-q4-operator-access-packet.md), [`../operations/stage-18j-q4b-readonly-warehouse-dsn-operator-note.md`](../operations/stage-18j-q4b-readonly-warehouse-dsn-operator-note.md), [`../operations/stage-18j-q4c-readonly-warehouse-dsn-provisioning-plan.md`](../operations/stage-18j-q4c-readonly-warehouse-dsn-provisioning-plan.md), [`stage-18j-q5-nested-edsm-station-snapshot-support.md`](./stage-18j-q5-nested-edsm-station-snapshot-support.md), [`stage-18j-q6-memory-safe-warehouse-station-load.md`](./stage-18j-q6-memory-safe-warehouse-station-load.md), [`stage-18j-q7-reconciliation-json-serialization-fix.md`](./stage-18j-q7-reconciliation-json-serialization-fix.md), [`stage-18j-q8-compact-reconciliation-summary.md`](./stage-18j-q8-compact-reconciliation-summary.md), and [`stage-18j-q9-compact-summary-review-station-type-dry-run-readiness.md`](./stage-18j-q9-compact-summary-review-station-type-dry-run-readiness.md) together record the rest of the Stage 18J-Q chain: the guarded Q3 stop, operator access and DSN prep, nested-station loader support, memory-safe staging, reconciliation JSON hardening, compact artifact summarization, and the `Ready only with strict filter` verdict that hands off to `stage-18j-p-filter-strict-station-type-dry-run-filter.md`.

[`stage-18j-p-filter-strict-station-type-dry-run-filter.md`](./stage-18j-p-filter-strict-station-type-dry-run-filter.md), [`stage-18j-p-dryrun-operator-safe-wrapper.md`](./stage-18j-p-dryrun-operator-safe-wrapper.md), and the later Stage 18J-P closeouts (including [`stage-18j-p7-external-identity-schema-production-apply-closeout.md`](./stage-18j-p7-external-identity-schema-production-apply-closeout.md), [`stage-18j-p15-identity-load-production-closeout.md`](./stage-18j-p15-identity-load-production-closeout.md), [`stage-18j-p18m-dodec-and-bounded-station-type-write-closeout.md`](./stage-18j-p18m-dodec-and-bounded-station-type-write-closeout.md), and [`stage-18j-p18n-final-state-snapshot.md`](./stage-18j-p18n-final-state-snapshot.md)) record the strict-filter dry-run hardening, external identity proof chain, and bounded station-type write batch that completes Stage 18 for the reviewed scope.

[`stage-20-roadmap.md`](./stage-20-roadmap.md) is the completed Stage 20 planning baseline. It records the provenance-backed planning cockpit objective, five Stage 20 checkpoints, and the boundaries preserved while that work landed.

[`stage-20a-provenance-cockpit-implementation-contract.md`](./stage-20a-provenance-cockpit-implementation-contract.md) is the active Stage 20A contract checkpoint. It names the first provenance cockpit contract set, fixture payloads, and concrete backend/frontend ownership without starting feature delivery.

[`stage-20b-readonly-evidence-status-surfaces.md`](./stage-20b-readonly-evidence-status-surfaces.md) records the first implemented provenance cockpit surface: a fixture-backed read-only endpoint and Evidence Workspace panel that preserve all deferred-production guardrails.

[`stage-20c-map-planning-surface-foundation.md`](./stage-20c-map-planning-surface-foundation.md) records the planner-facing map foundation: a dedicated `Map` workspace mode plus timeline-layer ownership on top of the existing map primitives.

[`stage-20d-planner-sequence-cp-curve-cockpit.md`](./stage-20d-planner-sequence-cp-curve-cockpit.md) records the dedicated `Sequence` workspace mode that exposes build order and CP tradeoffs without auto-running preview or mutating the plan.

[`stage-20e-export-operator-pack-closeout-readiness.md`](./stage-20e-export-operator-pack-closeout-readiness.md) records the dedicated `Export` workspace mode, reviewable Markdown/JSON/CSV pack builders, and the final Stage 20 closeout state.

[`stage-17p-current-state-forward-plan.md`](./stage-17p-current-state-forward-plan.md) remains the active Colony Planner product-boundary baseline, but it is no longer the active post-21 roadmap.

It supersedes the old assumption that the project should simply continue from Stage 17A's original sequence. Later work has already delivered or changed large parts of that path, including validated slot prediction, Raven-style canvas planning, projection comparison, trust recovery, existing infrastructure awareness, and enrichment warehouse foundations.

## Active / Living Docs

| Document | Status | Purpose |
|---|---|---|
| [`stage-22-roadmap.md`](./stage-22-roadmap.md) | Active Stage 22 control | Post-18/20/21 control reset, current next-lane prioritisation, and preserved deferred-production boundaries. |
| [`stage-22b-current-state-planner-evidence-hardening.md`](./stage-22b-current-state-planner-evidence-hardening.md) | Completed Stage 22B implementation record | Records runtime fixture isolation, conservative freshness semantics, and the separation between selected-system evidence and global authority state. |
| [`stage-22c-operator-artifact-review-and-audit-surfaces.md`](./stage-22c-operator-artifact-review-and-audit-surfaces.md) | Completed Stage 22C implementation record | Records export-workspace operator review focus items, sanitized references, safeguards, and section-coverage checks for artifact inspection. |
| [`stage-22d-export-and-documentation-governance-consolidation.md`](./stage-22d-export-and-documentation-governance-consolidation.md) | Completed Stage 22D implementation record | Records export-pack governance language, exclusions, authority-scope reminders, and committed document references for review-safe historical context. |
| [`stage-21-roadmap.md`](./stage-21-roadmap.md) | Completed Stage 21 control | Post-20 roadmap reconciliation, trust/operationalisation queue, and preserved deferred-production boundaries. |
| [`stage-21b-to-21f-stage17-stage18-burn-down.md`](./stage-21b-to-21f-stage17-stage18-burn-down.md) | Active Stage 21 progress record | Records how Stage 17 planner backlog and Stage 18 warehouse/operator backlog were reduced, reclassified, or marked delivered groundwork. |
| [`stage-21-closeout.md`](./stage-21-closeout.md) | Completed Stage 21 closeout record | Records Stage 21 completion, validation state, and the live read-only Stage 18H warehouse bridge outcome. |
| [`stage-18h1-per-system-warehouse-evidence-contract.md`](./stage-18h1-per-system-warehouse-evidence-contract.md) | Active Stage 18H.1 contract review | Defines the future per-system `warehouse_planner_evidence/v1` contract without yet adding a live endpoint or planner fetch. |
| [`stage-18h2-readonly-backend-warehouse-evidence-endpoint.md`](./stage-18h2-readonly-backend-warehouse-evidence-endpoint.md) | Active Stage 18H.2 endpoint scaffold | Defines the read-only backend route that serves `warehouse_planner_evidence/v1` while preserving planner fallback semantics. |
| [`stage-18h3-planner-warehouse-fetch-fallback.md`](./stage-18h3-planner-warehouse-fetch-fallback.md) | Active Stage 18H.3 planner integration | Defines the planner-side fetch path that prefers the dedicated warehouse endpoint and falls back to provenance when needed. |
| [`stage-18h4-warehouse-evidence-ux-clarification.md`](./stage-18h4-warehouse-evidence-ux-clarification.md) | Active Stage 18H.4 UX clarification | Defines the planner-card freshness, review-status, warning, and source-posture clarification while staying read-only. |
| [`stage-18i-canonical-write-design-review.md`](./stage-18i-canonical-write-design-review.md) | Active Stage 18I design review | Defines the future canonical write boundary, recommended first pilot, banned writes, approval/audit/rollback rules, and the requirement that Stage 18I.5 complete first. |
| [`stage-18i5-warehouse-database-boundary-review.md`](./stage-18i5-warehouse-database-boundary-review.md) | Active Stage 18I.5 boundary review | Defines the preferred separate-warehouse-database boundary and keeps the decision documentation-only. |
| [`stage-18j-station-type-canonical-pilot-plan.md`](./stage-18j-station-type-canonical-pilot-plan.md) | Active Stage 18J pilot plan | Defines the strict station-type-only canonical pilot scope and makes dry-run-only first steps explicit. |
| [`stage-18j-station-type-canonical-pilot-closeout.md`](./stage-18j-station-type-canonical-pilot-closeout.md) | Active Stage 18J closeout | Records the implemented bounded station-type pilot and its still-conservative production boundary. |
| [`stage-18t-canonical-safety-test-environment.md`](./stage-18t-canonical-safety-test-environment.md) | Active Stage 18T safety environment | Records the delivered CI, local runner, dependency, and disposable Postgres rehearsal coverage for canonical-write-capable code. |
| [`stage-18j-q-production-reconciliation-artifact-readiness.md`](./stage-18j-q-production-reconciliation-artifact-readiness.md) | Active Stage 18J-Q readiness | Defines the next follow-on prerequisite for any later production station-type dry-run path. |
| [`stage-18j-q2-readonly-production-reconciliation-plan.md`](./stage-18j-q2-readonly-production-reconciliation-plan.md) | Active Stage 18J-Q2 plan | Defines the later operator command path and pre-run checks for report-only reconciliation generation. |
| [`stage-18j-q3-readonly-production-reconciliation-artifact.md`](./stage-18j-q3-readonly-production-reconciliation-artifact.md) | Active Stage 18J-Q3 record | Records the guarded pre-run stop when required read-only variables and DSN proof were missing. |
| [`../operations/stage-18j-q4-operator-access-packet.md`](../operations/stage-18j-q4-operator-access-packet.md) | Active Stage 18J-Q4 ops packet | Defines the operator variable checklist and redacted command template for a later Q3 retry. |
| [`../operations/stage-18j-q4b-readonly-warehouse-dsn-operator-note.md`](../operations/stage-18j-q4b-readonly-warehouse-dsn-operator-note.md) | Active Stage 18J-Q4b ops note | Records that the required read-only warehouse DSN is missing from repo config and must come from operator secrets. |
| [`../operations/stage-18j-q4c-readonly-warehouse-dsn-provisioning-plan.md`](../operations/stage-18j-q4c-readonly-warehouse-dsn-provisioning-plan.md) | Active Stage 18J-Q4c ops plan | Defines the provisioning plan for a dedicated read/report warehouse role without executing it. |
| [`stage-18j-q5-nested-edsm-station-snapshot-support.md`](./stage-18j-q5-nested-edsm-station-snapshot-support.md) | Active Stage 18J-Q5 implementation record | Records nested station snapshot loader support while keeping body support and production retries separately gated. |
| [`stage-18j-q6-memory-safe-warehouse-station-load.md`](./stage-18j-q6-memory-safe-warehouse-station-load.md) | Active Stage 18J-Q6 implementation record | Records streaming, batch-based station staging writes and compact write summaries for large offline snapshots. |
| [`stage-18j-q7-reconciliation-json-serialization-fix.md`](./stage-18j-q7-reconciliation-json-serialization-fix.md) | Active Stage 18J-Q7 implementation record | Records the JSON-safe reconciliation serialization fix after the first post-Q6 read-only attempt failed. |
| [`stage-18j-q8-compact-reconciliation-summary.md`](./stage-18j-q8-compact-reconciliation-summary.md) | Active Stage 18J-Q8 implementation record | Records the offline compact-summary tool for very large reconciliation artifacts. |
| [`stage-18j-q9-compact-summary-review-station-type-dry-run-readiness.md`](./stage-18j-q9-compact-summary-review-station-type-dry-run-readiness.md) | Active Stage 18J-Q9 review | Records the `Ready only with strict filter` verdict before any later Stage 18J-P retry. |
| [`stage-18j-p-filter-strict-station-type-dry-run-filter.md`](./stage-18j-p-filter-strict-station-type-dry-run-filter.md) | Completed Stage 18J-P-filter | Strict eligibility filter and rejection distribution rules for station-type dry-run planning. |
| [`stage-18j-p7-external-identity-schema-production-apply-closeout.md`](./stage-18j-p7-external-identity-schema-production-apply-closeout.md) | Completed Stage 18J-P7 closeout | Records the schema-only production apply for `station_external_identity` (no station-type writes). |
| [`stage-18j-p15-identity-load-production-closeout.md`](./stage-18j-p15-identity-load-production-closeout.md) | Completed Stage 18J-P15 closeout | Records the bounded 20-row confirmed identity load (no station-type writes). |
| [`stage-18j-p18m-dodec-and-bounded-station-type-write-closeout.md`](./stage-18j-p18m-dodec-and-bounded-station-type-write-closeout.md) | Completed Stage 18J-P18M closeout | Records Dodec enum support and the bounded 4-row station-type write chain. |
| [`stage-18j-p18n-final-state-snapshot.md`](./stage-18j-p18n-final-state-snapshot.md) | Completed Stage 18J-P18N closeout | Records the final post-write snapshot confirming the bounded batch completion. |
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
