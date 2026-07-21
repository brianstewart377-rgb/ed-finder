# ED-Finder Colonisation Redesign Docs

This folder contains the active contracts, closeout records, architecture notes,
and historical implementation docs for ED-Finder's colonisation, planner,
evidence, and enrichment work.

## Active Stage 26 Control

The prior **Active Stage 25 Control** is complete and remains the settled
product-shell and selected-system context baseline for this new lane.

- [`../ROADMAP.md`](../ROADMAP.md) is the single authoritative roadmap and the
  default answer to "what next?".
- [`stage-26a-next-generation-map-foundation-contract.md`](./stage-26a-next-generation-map-foundation-contract.md)
  is the authorization and implementation-boundary contract for the active
  Stage 26B next-generation desktop map lane. Its accepted research bundle is
  retained under `../../artifacts/map-foundation/stage-26b/`.
- [`stage-26b-renderer-bakeoff-decision.md`](./stage-26b-renderer-bakeoff-decision.md)
  records the completed equal-renderer matrix, its limitations, and the
  Three.js/R3F selection for the isolated Stage 26C foundation.
- [`stage-25c-product-shell-shared-context-contract.md`](./stage-25c-product-shell-shared-context-contract.md)
  remains the settled shell and selected-system context baseline.

## Read This First

Use this order before changing planner, evidence, or enrichment behaviour:

1. [`../ROADMAP.md`](../ROADMAP.md)
2. [`stage-26a-next-generation-map-foundation-contract.md`](./stage-26a-next-generation-map-foundation-contract.md)
   for map work, or
   [`stage-25c-product-shell-shared-context-contract.md`](./stage-25c-product-shell-shared-context-contract.md)
   for shell and planner-context work
3. [`stage-25b-evidence-language-visual-primitives.md`](./stage-25b-evidence-language-visual-primitives.md)
   and [`stage-25a-current-state-map-product-visual-baseline.md`](./stage-25a-current-state-map-product-visual-baseline.md)
4. [`stage-17p-current-state-forward-plan.md`](./stage-17p-current-state-forward-plan.md)
5. [`../reference/colonisation/README.md`](../reference/colonisation/README.md)
6. Specific historical stage docs only when they directly apply to the task.

If an older document's recommended next step conflicts with
[`../ROADMAP.md`](../ROADMAP.md), the roadmap wins.

## Active Docs

| Document | Why it matters |
|---|---|
| [`../ROADMAP.md`](../ROADMAP.md) | Single source for current priorities, boundaries, and next work. |
| [`stage-26a-next-generation-map-foundation-contract.md`](./stage-26a-next-generation-map-foundation-contract.md) | Active map authorization, research artifacts, renderer bake-off, integration boundary, and staged cutover contract. |
| [`stage-25c-product-shell-shared-context-contract.md`](./stage-25c-product-shell-shared-context-contract.md) | Settled shell and selected-system context baseline. |
| [`stage-25b-evidence-language-visual-primitives.md`](./stage-25b-evidence-language-visual-primitives.md) | Current evidence-language and visual-system baseline. |
| [`stage-25a-current-state-map-product-visual-baseline.md`](./stage-25a-current-state-map-product-visual-baseline.md) | Current-state audit and map posture baseline. |
| [`stage-17p-current-state-forward-plan.md`](./stage-17p-current-state-forward-plan.md) | Planner truth, source authority, and hard product boundaries. |
| [`stage-24-roadmap.md`](./stage-24-roadmap.md) | Historical completed post-Stage-23 control baseline for read-only evidence adoption. |
| [`stage-24d-readonly-evidence-adoption-closeout.md`](./stage-24d-readonly-evidence-adoption-closeout.md) | Closeout for the read-only evidence adoption programme. |
| [`stage-24a-readonly-evidence-adoption-contract.md`](./stage-24a-readonly-evidence-adoption-contract.md) | Contract for evidence-surface ownership, language, and test expectations. |
| [`stage-23-roadmap.md`](./stage-23-roadmap.md) | Historical roadmap for the first live selected-system evidence lane. |
| [`stage-23e-readonly-evidence-closeout.md`](./stage-23e-readonly-evidence-closeout.md) | Closeout for the read-only planner evidence baseline. |
| [`stage-23d-planner-evidence-ux-follow-through.md`](./stage-23d-planner-evidence-ux-follow-through.md) | UX follow-through for the read-only planner evidence surface. |
| [`stage-23c-evidence-envelope-governance.md`](./stage-23c-evidence-envelope-governance.md) | Governance contract for the read-only planner evidence envelope. |
| [`stage-23b-readonly-per-system-warehouse-join.md`](./stage-23b-readonly-per-system-warehouse-join.md) | Safe bounded expansion of the per-system warehouse evidence join. |
| [`stage-23a-first-live-per-system-evidence-provider.md`](./stage-23a-first-live-per-system-evidence-provider.md) | First live selected-system evidence provider record. |
| [`stage-22-roadmap.md`](./stage-22-roadmap.md) | Historical Stage 22 roadmap for the active post-18/20/21 control baseline transition. |
| [`stage-21-roadmap.md`](./stage-21-roadmap.md) | Historical roadmap for the Stage 21 trust and authority lane. |
| [`stage-22e-deferred-stage19-decision-gate-and-closeout.md`](./stage-22e-deferred-stage19-decision-gate-and-closeout.md) | The clearest closeout for the deferred Stage 19 decision gate. |
| [`stage-21-closeout.md`](./stage-21-closeout.md) | Closeout for the earlier planner trust and operationalisation pass. |
| [`stage-19-bounded-production-staging-activation.md`](./stage-19-bounded-production-staging-activation.md) | Separate bounded production-staging dependency contract. |
| [`stage-19bb-first-production-staging-activation.md`](./stage-19bb-first-production-staging-activation.md) | Stage 19BB authorization record. |
| [`stage-19bb-production-staging-execution-closeout.md`](./stage-19bb-production-staging-execution-closeout.md) | Stage 19BB bounded execution closeout. |
| [`simulation-preview-ui-architecture.md`](./simulation-preview-ui-architecture.md) | Architecture reference for planner and preview ownership. |
| [`../operations/enrichment-warehouse-runbook.md`](../operations/enrichment-warehouse-runbook.md) | Operational runbook for guarded enrichment and warehouse work. |
| [`../reference/colonisation/README.md`](../reference/colonisation/README.md) | Source-authority entry point for mechanics-heavy work. |

Completed Stage 24A contract: see the completed Stage 24A contract checkpoint in
`stage-24a-readonly-evidence-adoption-contract.md`.

Completed Stage 24B implementation record: see the completed Stage 24B slice in
`stage-24b-planner-evidence-discoverability.md`.

Completed Stage 24C implementation record: see the completed Stage 24C slice in
`stage-24c-cross-surface-evidence-consistency.md`.

Completed Stage 24D closeout record: see the completed Stage 24D closeout in
`stage-24d-readonly-evidence-adoption-closeout.md`.

Completed Stage 24 control: see the completed post-Stage-23 control baseline in
`stage-24-roadmap.md`.

The completed Stage 20 roadmap and follow-on checkpoints are:
`stage-20-roadmap.md`,
`stage-20a-provenance-cockpit-implementation-contract.md`,
`stage-20b-readonly-evidence-status-surfaces.md`,
`stage-20c-map-planning-surface-foundation.md`,
`stage-20d-planner-sequence-cp-curve-cockpit.md`, and
`stage-20e-export-operator-pack-closeout-readiness.md`.

Stage 19 deferred-production boundaries remain documented in
`stage-19-data-warehouse-utopia-roadmap.md`.

The active post-18/20/21 roadmap and current control baseline now live in
`docs/ROADMAP.md`, with `stage-22-roadmap.md` preserved as the historical
handoff into that single-roadmap model.

The completed post-18/20/21 roadmap and prior control baseline remain available
in `stage-22-roadmap.md`.

The completed post-20 roadmap and trust/operationalisation plan remain
available in `stage-21-roadmap.md`.

The active post-22 roadmap and current control baseline now live in
`docs/ROADMAP.md`.

The latest completed Stage 23 control document remains available in
`stage-23-roadmap.md`.

Completed Stage 18H.1 contract review: see the per-system warehouse evidence
contract in `stage-18h1-per-system-warehouse-evidence-contract.md`.

Completed Stage 18H.2 backend scaffold: see the read-only endpoint checkpoint in
`stage-18h2-readonly-backend-warehouse-evidence-endpoint.md`.

Completed Stage 18H.3 planner fetch fallback: see the planner integration
checkpoint in `stage-18h3-planner-warehouse-fetch-fallback.md`.

Completed Stage 18H.4 UX clarification: see the warehouse evidence UX
checkpoint in `stage-18h4-warehouse-evidence-ux-clarification.md`.

Completed Stage 18I design review: see the canonical write design review in
`stage-18i-canonical-write-design-review.md`.

Completed Stage 18I.5 boundary review: see the warehouse database boundary
review in `stage-18i5-warehouse-database-boundary-review.md`.

Stage 18J pilot planning: see the station-type canonical pilot plan in
`stage-18j-station-type-canonical-pilot-plan.md`.

Completed and follow-on historical Stage 18J/T records include:
`stage-18j-station-type-canonical-pilot-closeout.md`,
`stage-18t-canonical-safety-test-environment.md`,
`stage-18j-q-production-reconciliation-artifact-readiness.md`,
`stage-18j-q2-readonly-production-reconciliation-plan.md`,
`stage-18j-q3-readonly-production-reconciliation-artifact.md`,
`stage-18j-q5-nested-edsm-station-snapshot-support.md`,
`stage-18j-q6-memory-safe-warehouse-station-load.md`,
`stage-18j-q7-reconciliation-json-serialization-fix.md`,
`stage-18j-q8-compact-reconciliation-summary.md`,
`stage-18j-q9-compact-summary-review-station-type-dry-run-readiness.md`,
`stage-18j-p-filter-strict-station-type-dry-run-filter.md`,
`stage-18j-p-dryrun-operator-safe-wrapper.md`,
`stage-18j-p2-station-type-identity-coverage-diagnostics.md`,
`stage-18j-p7-external-identity-schema-production-apply-closeout.md`,
`stage-18j-p15-identity-load-production-closeout.md`,
`stage-18j-p16a-readonly-reconciliation-integration.md`,
`stage-18j-p18m-dodec-and-bounded-station-type-write-closeout.md`,
`stage-18j-p18n-final-state-snapshot.md`,
`stage-18j-q4-operator-access-packet.md`,
`stage-18j-q4b-readonly-warehouse-dsn-operator-note.md`, and
`stage-18j-q4c-readonly-warehouse-dsn-provisioning-plan.md`.

## Historical Docs

These files are still useful as rationale and implementation history, but they
are not roadmap sources:

- `stage-24b-planner-evidence-discoverability.md`
- `stage-24c-cross-surface-evidence-consistency.md`
- `stage-23b-readonly-per-system-warehouse-join.md`
- `stage-23c-evidence-envelope-governance.md`
- `stage-23d-planner-evidence-ux-follow-through.md`
- `stage-22b-current-state-planner-evidence-hardening.md`
- `stage-22c-operator-artifact-review-and-audit-surfaces.md`
- `stage-22d-export-and-documentation-governance-consolidation.md`
- `stage-21b-to-21f-stage17-stage18-burn-down.md`
- `stage-20a-provenance-cockpit-implementation-contract.md`
- `stage-20b-readonly-evidence-status-surfaces.md`
- `stage-20c-map-planning-surface-foundation.md`
- `stage-20d-planner-sequence-cp-curve-cockpit.md`
- `stage-20e-export-operator-pack-closeout-readiness.md`
- `stage-18h*`, `stage-18i*`, `stage-18j*`, and `stage-18t*` docs for guarded
  warehouse and canonical-write history
- Stage 5-17 exploratory and forensic docs when investigating a regression or
  historical design choice

## Cleanup Rule

- Keep one roadmap: [`../ROADMAP.md`](../ROADMAP.md).
- Treat the rest of this folder as contracts, closeouts, architecture notes, or
  historical records.
- Prefer small index notes over large historical rewrites unless a document is
  actively misleading.

## Source Pack Reminder

The committed source-authority entry point lives under
[`docs/reference/colonisation/`](../reference/colonisation/).

It does not commit restricted guide files, spreadsheets, PDFs, screenshots, or
third-party assets. Mechanics-heavy work should cite committed reference docs
first, then state clearly whether any additional verification used attached,
external, or local-only material.
