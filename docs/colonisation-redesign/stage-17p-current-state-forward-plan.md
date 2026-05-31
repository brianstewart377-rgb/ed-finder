# Stage 17P — Current State / Forward Plan Baseline

Stage 17P is a documentation-control stage. It does not implement app behaviour, change backend mechanics, alter scoring, change CP formulas, add ingestion, change persistence, or redesign the Colony Planner UI.

## Purpose

The colonisation roadmap has grown through many implementation and recovery stages. Older documents are still valuable, but several of their "next stage" recommendations are now historical because later work has already landed.

This document is the current planning baseline for future Colony Planner, colonisation intelligence, trust, slot, enrichment, and Raven-style planner work.

Future implementation prompts should read this file first, then inspect the specific historical stage document only when it is relevant evidence for the work being planned.

## Current Baseline

The project has moved beyond the original Stage 17A sequence of:

1. trust/rationale fixes,
2. surface slot prediction,
3. structure picker expansion,
4. validity hardening,
5. visual planner feasibility,
6. durable persistence feasibility,
7. ingestion feasibility.

That sequence remains useful as historical intent, but it has been partly superseded by later merged work.

Current merged direction, based on the latest roadmap trail:

- Stage 16E/16F/16G added inferred, declared, and declared-vs-observed role review concepts while keeping roles advisory and non-mechanical.
- Stage 17B rescued Suggested Builds error handling and usefulness filtering.
- Stage 17G introduced canonical validated slot prediction and a whole-system slot/economy planning map.
- Stage 17M moved the dedicated planner toward a two-region Raven-style canvas plus telemetry/context model.
- Stage 17N tightened the docked telemetry/context region and read-only projection comparison.
- Stage 17N.1 repaired and refined Raven canvas add flows, picker compatibility, lane handling, prerequisite warnings, and canvas clarity.
- Stage 17N.2c recovered trust around unknown coordinates, unknown distances, stale/saturated ratings, and legacy rationale language.
- Stage 17N.2d/17N.2d-H moved existing-infrastructure awareness and station/body association toward backend-backed trust metadata.
- Stage 17N.2d-P and the enrichment roadmap introduced a safer offline/staging warehouse direction for repeatable enrichment evidence and report-only reconciliation.

## Read-Order For Future Work

Use this order before starting new colonisation work:

1. `docs/colonisation-redesign/README.md`
2. This file.
3. `docs/colonisation-redesign/engine-roadmap.md` for broad engine history and delivered stage summaries.
4. `docs/colonisation-redesign/enrichment-roadmap.md` for station/body/ring enrichment, warehouse, and operator-roadmap work.
5. Specific stage docs only when they directly apply to the task.
6. For mechanics-heavy or source-sensitive work, read `docs/reference/colonisation/README.md`, `docs/reference/colonisation/source-priority.md`, and `docs/reference/colonisation/source-inventory.md`.

If this file conflicts with an older "recommended next stage" section, treat this file as newer planning control unless the older doc is being used only for historical context.

## Source Authority Rule

The source-pack issue from Stage 17A remains important, but Stage 17Q now adds
the committed reference entry point:

- `docs/reference/colonisation/README.md`
- `docs/reference/colonisation/source-priority.md`
- `docs/reference/colonisation/source-inventory.md`
- `docs/reference/colonisation/codex-reference-prompt-snippet.md`

The committed path records the source hierarchy, conflict rules, and inventory
placeholders. It does not commit restricted guide files, spreadsheets, PDFs,
screenshots, or third-party assets unless their redistribution status is
explicitly safe.

Future mechanics-heavy implementation prompts must read the committed reference
docs first, then explicitly state whether direct source verification used
committed docs, attached files, external sources, or local/operator-only files.
Do not claim direct source verification from files that are not committed or
attached.

## Non-Negotiable Product Boundaries

These boundaries continue to apply unless a future stage explicitly changes them:

- No automatic Simulation Preview execution.
- No automatic Suggested Build generation.
- No automatic Suggested Build loading.
- No silent Build Plan mutation from imported, observed, projected, or inferred data.
- No hidden scoring, CP, economy, service, buildability, or optimiser-ranking changes.
- No role-aware optimiser scoring/ranking without a dedicated scope.
- No primary-port truth invented from user intent.
- No Architect Slot Survey truth unless backed by an explicit evidence/import workflow.
- No RavenColonial visual clone, asset copy, API mutation, or logistics clone.
- Existing infrastructure is not a Build Plan placement.
- Projected Suggested Build structures are ghost/projection-only until explicitly loaded.
- Unknown data must stay unknown; do not coerce missing coordinates, distances, slot counts, rings, or body associations to zero/false.

## Current Information Model

The planner should keep these concepts visibly separated:

| Source | Meaning | Mutates Build Plan? | Trust handling |
|---|---|---:|---|
| Existing | Infrastructure already present in system/station data | No | Confirmed, inferred/verify, or unresolved based on backend association metadata. |
| Planned | User Build Plan placements | Yes | Local project/user plan state. |
| Projected | Selected Suggested Build ghost placements | No | Read-only comparison until explicitly loaded. |
| Observed Evidence | Manual/imported evidence records | No by default | Used for review/validation; does not mutate mechanics. |
| Inferred Planning Signals | ED-Finder advisory hints from topology/plan shape | No | Conservative guidance only. |
| Declared Strategy | User-declared body roles | No mechanics mutation | Local project intent, not game truth. |
| Unknown/Unresolved | Missing/ambiguous data | No | Display compactly and conservatively. |

## Recommended Next Work Queue

### Stage 17Q — Source Pack Commit / Source Authority Lock

Purpose: make the mechanics/source hierarchy available in-repo so future mechanics-heavy work has a committed reference baseline.

Scope:

- Add `docs/reference/colonisation/README.md`.
- Add `docs/reference/colonisation/source-priority.md`.
- Add the future implementation prompt snippet.
- Add permitted source references, inventories, or placeholders.
- Document licensing/redistribution limits where source files cannot be committed.

Non-goals:

- No app behaviour changes.
- No mechanics changes.
- No scoring changes.

Acceptance:

- Future Codex/AI prompts can start from committed source-priority docs.
- The repo no longer points only at a local ZIP path for the reference pack.

### Stage 17R — Planner Trust Audit

Purpose: verify the current Raven-style planner and trust-recovery work behaves honestly on real awkward systems before adding more intelligence.

Scope:

- Audit current Raven canvas behaviour against systems with known existing stations, predicted slots, unresolved associations, and projected Suggested Builds.
- Remove any temporary slot/debug console logs.
- Confirm unknown coordinates/distances never render as real zero values.
- Confirm stale/saturated rating caveats and legacy-rationale safety copy are still present where needed.
- Confirm predicted slots never appear as known/confirmed slots.
- Confirm existing infrastructure never silently becomes planned infrastructure.
- Add focused regression tests around representative awkward systems/fixtures.

Non-goals:

- No new planner features.
- No scoring changes.
- No automatic preview/generation/load.

Acceptance:

- Trust language is consistent between result cards, system detail, planner canvas, and telemetry.
- Ambiguous station/body/lane associations render as unresolved or verify, not confirmed.
- Capacity calculations clearly separate predicted, existing, planned, projected, and unknown states.

### Stage 17S — Existing Infrastructure UX Hardening

Purpose: make existing infrastructure and occupied-slot reasoning understandable to the user.

Scope:

- Improve display for confirmed existing, inferred/verify existing, unresolved, and unknown-lane infrastructure.
- Add compact explanations/tooltips for association source and confidence.
- Make capacity math visible per lane: predicted slots, existing occupied, planned occupied, projected occupied, remaining, unknown/unresolved.
- Ensure disabled add controls explain the exact reason.

Non-goals:

- No Build Plan mutation from existing infrastructure.
- No canonical write path.
- No new enrichment ingestion.

Acceptance:

- A user can tell why a slot is unavailable.
- A user can tell whether ED-Finder knows, infers, or cannot resolve an existing station's body/lane.

### Stage 17T — Suggested Builds Strategy Advisor V1

Purpose: make Suggested Builds more strategically useful using the planner context already available.

Scope:

- Improve candidate explanation around body choice, existing infrastructure, slot pressure, economy intent, sparse-data warnings, and declared roles.
- Keep deterministic candidate families such as main station candidate, industrial/refinery starter, extraction support, tourism/agriculture, security/military, balanced expansion, and support-body plan.
- Use Raven canvas projection to make candidate impact clearer.
- Keep load explicit and preview explicit.

Non-goals:

- No LLM planning.
- No automatic generation/load/preview.
- No hidden optimiser-ranking mechanics change unless separately scoped.

Acceptance:

- Suggested Builds explain why they exist and what tradeoff they are making.
- Trivial candidates stay filtered.
- Projected structures remain ghost-only until explicit load.

### Stage 17U — Role + Strategy Integration

Purpose: connect declared/inferred/observed role work to Suggested Builds and planner guidance without making roles mechanics truth.

Scope:

- Show which declared roles a candidate supports or conflicts with.
- Surface role gaps such as declared Industrial Core with no industrial placement, Main Station Body with no station/port, or observed Tourism Focus conflicting with declared Industrial Core.
- Keep source labels visible: inferred, declared, observed.

Non-goals:

- No role-aware optimiser ranking.
- No role-driven Simulation Preview mechanics.
- No automatic declared-role assignment from Suggested Builds.

Acceptance:

- Roles improve guidance and review.
- Roles still do not change CP, economy, service, scoring, optimiser ranking, or validation semantics.

### Stage 18A — Enrichment Operator Dashboard / Status Integration

Purpose: make enrichment status observable without SSH/log spelunking.

Scope:

- Surface `station_enrichment_status.py --json` in an operator/admin dashboard.
- Display latest run, checkpoint progress, fetch/rate-limit failures, safety-gate failures, and batch status.
- Keep the dashboard read-only.

Non-goals:

- No production writes from dashboard.
- No live API crawling from dashboard.

Acceptance:

- Operator can inspect progress and failures through ED-Finder UI/admin tooling.
- Status is read-only and safe.

### Stage 18B — Warehouse Reconciliation Hardening

Purpose: mature the offline enrichment warehouse path before any canonical writes are considered.

Scope:

- Broaden read-only reconciliation across staged station, body, and ring evidence.
- Improve confidence/risk explanations.
- Improve source coverage summaries, colonisation signals, and mission-density signals.
- Keep output report-only.

Non-goals:

- No canonical station/body/system writes.
- No production live API crawl.
- No scoring changes.

Acceptance:

- Warehouse reports are boring, deterministic, and explainable.
- Any future canonical write path can be designed from stable report evidence rather than live API behaviour.

## Historical Docs Status

Older docs should not be deleted by default. They contain useful context, rationale, boundaries, and acceptance criteria. Treat them as historical/reference unless this file points to them as active.

| Doc | Status | Use |
|---|---|---|
| `stage-17a-colony-planner-intelligence-forward-plan.md` | Partly superseded | Source alignment and original trust/slot/picker roadmap. Do not follow its next-stage order blindly. |
| `stage-16-colony-role-model-plan.md` | Historical/reference | Role terminology, source separation, declared/inferred/observed boundaries. |
| `stage-15-planner-workspace-redesign-plan.md` | Historical/reference | Topology-first workspace rationale and UI architecture intent. |
| `simulation-preview-ui-architecture.md` | Historical/reference plus current architecture notes | Component ownership and delivered Stage 16/17 architecture notes. |
| `engine-roadmap.md` | Living historical roadmap | Broad engine history and delivered stage summaries. This Stage 17P file controls immediate next work. |
| `enrichment-roadmap.md` | Active for enrichment/operator work | Station enrichment, body/ring enrichment, warehouse, and operator roadmap. |
| Stage 5-14 docs | Historical/reference | Use only for the specific feature or regression they describe. |

## Final Recommendation

Do not add another large planner feature immediately. The healthiest next sequence is:

1. Stage 17Q source pack commit.
2. Stage 17R planner trust audit.
3. Stage 17S existing infrastructure UX hardening.
4. Stage 17T Suggested Builds Strategy Advisor V1.
5. Stage 17U role/strategy integration.
6. Stage 18A enrichment operator dashboard.
7. Stage 18B warehouse reconciliation hardening.

This keeps ED-Finder moving toward a genuinely intelligent colony planner while protecting the trust boundaries that make the tool useful.
