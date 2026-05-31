# ED-Finder Colonisation Redesign Docs

This folder contains the planning, architecture, forensic-review, and implementation-history documents for ED-Finder's colonisation and Colony Planner work.

## Read This First

Start here for any new colonisation work:

1. [`stage-17p-current-state-forward-plan.md`](./stage-17p-current-state-forward-plan.md) — current roadmap baseline and next work queue.
2. [`engine-roadmap.md`](./engine-roadmap.md) — broad engine history and delivered stage summaries.
3. [`enrichment-roadmap.md`](./enrichment-roadmap.md) — station/body/ring enrichment, warehouse, and operator-roadmap work.
4. Specific historical stage docs only when the task directly touches that feature.

If an older document's "recommended next stage" conflicts with Stage 17P, follow Stage 17P unless intentionally researching historical context.

## Current Control Document

[`stage-17p-current-state-forward-plan.md`](./stage-17p-current-state-forward-plan.md) is the active planning baseline.

It supersedes the old assumption that the project should simply continue from Stage 17A's original sequence. Later work has already delivered or changed large parts of that path, including validated slot prediction, Raven-style canvas planning, projection comparison, trust recovery, existing infrastructure awareness, and enrichment warehouse foundations.

## Active / Living Docs

| Document | Status | Purpose |
|---|---|---|
| [`stage-17p-current-state-forward-plan.md`](./stage-17p-current-state-forward-plan.md) | Active control | Current state, source-authority warning, non-negotiable boundaries, and next work queue. |
| [`../reference/colonisation/README.md`](../reference/colonisation/README.md) | Source authority entry point | Committed source hierarchy, inventory placeholders, and future Codex prompt snippet for mechanics-heavy work. |
| [`engine-roadmap.md`](./engine-roadmap.md) | Living historical roadmap | Broad colonisation engine evolution and delivered stage summaries. |
| [`enrichment-roadmap.md`](./enrichment-roadmap.md) | Active for enrichment | Guarded station enrichment, body/ring enrichment, offline warehouse, reconciliation, and operator-status roadmap. |
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
