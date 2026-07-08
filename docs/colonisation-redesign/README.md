# ED-Finder Colonisation Redesign Docs

This folder contains the active contracts, closeout records, architecture notes,
and historical implementation docs for ED-Finder's colonisation, planner,
evidence, and enrichment work.

## Read This First

Use this order before changing planner, evidence, or enrichment behaviour:

1. [`../ROADMAP.md`](../ROADMAP.md)
2. [`stage-25c-product-shell-shared-context-contract.md`](./stage-25c-product-shell-shared-context-contract.md)
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
| [`stage-25c-product-shell-shared-context-contract.md`](./stage-25c-product-shell-shared-context-contract.md) | Active implementation contract for the current slice. |
| [`stage-25b-evidence-language-visual-primitives.md`](./stage-25b-evidence-language-visual-primitives.md) | Current evidence-language and visual-system baseline. |
| [`stage-25a-current-state-map-product-visual-baseline.md`](./stage-25a-current-state-map-product-visual-baseline.md) | Current-state audit and map posture baseline. |
| [`stage-17p-current-state-forward-plan.md`](./stage-17p-current-state-forward-plan.md) | Planner truth, source authority, and hard product boundaries. |
| [`stage-24d-readonly-evidence-adoption-closeout.md`](./stage-24d-readonly-evidence-adoption-closeout.md) | Closeout for the read-only evidence adoption programme. |
| [`stage-24a-readonly-evidence-adoption-contract.md`](./stage-24a-readonly-evidence-adoption-contract.md) | Contract for evidence-surface ownership, language, and test expectations. |
| [`stage-23e-readonly-evidence-closeout.md`](./stage-23e-readonly-evidence-closeout.md) | Closeout for the read-only planner evidence baseline. |
| [`stage-23a-first-live-per-system-evidence-provider.md`](./stage-23a-first-live-per-system-evidence-provider.md) | First live selected-system evidence provider record. |
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
