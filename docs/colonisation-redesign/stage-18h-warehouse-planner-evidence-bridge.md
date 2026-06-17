# Stage 18H — Warehouse-to-Planner Evidence Bridge (Read-Only)

Stage 18H lets the Colony Planner *see* selected warehouse/report-only evidence
as **evidence, not truth**. It is strictly read-only. It does not mutate planner
state, Build Plans, scoring, CP, economy/service, buildability, Simulation
Preview, optimiser output, roles, observed evidence, validation, or canonical
data.

## Current State

Stage 18H no longer sits only in a placeholder state.

The planner now has a live, read-only warehouse bridge through the sanitized
provenance cockpit route:

- `frontend-v2/src/features/colony-planner/ColonyPlannerWorkspace.tsx`
- `frontend-v2/src/features/colony-planner/warehouseEvidenceBridge.ts`
- `frontend-v2/src/features/system-detail/simulation-preview/provenance/ProvenanceCockpitPanel.tsx`

This bridge reuses the existing non-admin provenance cockpit endpoint and
surfaces warehouse status as report-only evidence inside the main planner
workspace. It does not mutate Build Plans, roles, scoring, Preview,
optimisation, or canonical data.

What it still does **not** claim is a dedicated per-system warehouse artifact
contract. The bridge remains conservative: it surfaces sanitized warehouse
status already approved for the provenance cockpit rather than inventing a new
artifact join.

## Decision Gate Outcome

Stage 18H reached the architectural decision gate defined in the stage brief and
took the **conservative placeholder path**. The reasons are concrete and come
from the existing Stage 18G implementation, not from caution alone:

1. **Warehouse evidence is admin-gated.** The only published warehouse evidence
   surface is the Stage 18G Admin panel, served by
   `GET /api/admin/enrichment/warehouse-status`, which requires the admin token
   (`apps/api/src/routers/admin.py`). The Colony Planner is a normal
   user-facing workspace. Reusing the admin-gated artifact in the planner would
   leak operator-only data to non-admin users.
2. **The artifact is aggregate-only.** `sanitize_warehouse_status`
   (`apps/api/src/enrichment_operator_status.py`) returns *counts and
   distributions* only — `systems_with_station_evidence`,
   `unresolved_stations`, `blocked_conflicts`, `risky_conflicts`,
   `stale_records`, etc. It contains **no `system_id64`** and no per-system
   evidence rows. There is no key on which to join warehouse evidence to the
   planner's current system.
3. **The runbook forbids planner coupling.** `docs/operations/enrichment-warehouse-runbook.md`
   ("What Not To Do") explicitly says: *"Do not change planner, search, scoring,
   optimiser, Simulation Preview, Suggested Build, or role behavior from
   warehouse report output."*

The stage brief is explicit: *"If warehouse evidence cannot be safely linked by
system ID or artifact metadata, show a safe unavailable state instead of
guessing"* and *"Do not force full planner UI integration if the access boundary
is not safe."*

Therefore Stage 18H implements:

- a typed, read-only planner evidence model (`PlannerWarehouseEvidence`),
- a compact, pure, read-only planner card that **defaults to a safe
  unavailable/report-only state**,
- a shared mapper from provenance cockpit warehouse status into the planner
  evidence model,
- a live planner-workspace bridge that reuses the sanitized provenance cockpit
  route,
- tests proving the unavailable state, the source-labelled report-only labels,
  the stale/risky/blocked wording, source separation, and the absence of any
  mutation, and
- this design document plus a clear future integration path.

It does **not** add a new dedicated planner-facing warehouse API endpoint and
does not claim a true per-system warehouse artifact link, because no safe
per-system artifact contract exists yet.

## What the Planner Card Shows

The card is a presentation-only React component
(`frontend-v2/src/features/colony-planner/WarehouseEvidenceCard.tsx`). It takes
an optional `evidence?: PlannerWarehouseEvidence` prop and renders:

- A persistent source-boundary line:
  *"Planner is using canonical data; warehouse evidence is report-only."*
- When no evidence model is supplied: a safe unavailable
  state — *"No warehouse evidence artifact is available."* — with an
  `unknown` source label.
- When an evidence model *is* supplied (future integration, and exercised by
  tests, and now used by the live provenance/planner bridge): conservative,
  source-labelled findings using only the approved
  vocabulary — `report-only`, `needs review`, `verify`, `unresolved`, `stale`,
  `blocked`, `unknown`.

The card never renders a button, toggle, form, or any control that could mutate
planner state. It has no callbacks.

## Typed Model

`frontend-v2/src/types/api.ts` adds a small read-only model:

```ts
type WarehouseEvidenceSource =
  | 'canonical'
  | 'observed'
  | 'warehouse_report_only'
  | 'unknown';

type WarehouseEvidenceAvailability =
  | 'unavailable'   // no artifact / not safely linkable -> stays unknown
  | 'report_only';  // a report-only evidence summary is present

type WarehouseEvidenceLabel =
  | 'report_only'
  | 'needs_review'
  | 'verify'
  | 'unresolved'
  | 'stale'
  | 'blocked'
  | 'unknown';

interface PlannerWarehouseEvidenceItem {
  label: WarehouseEvidenceLabel;
  source: WarehouseEvidenceSource;
  summary: string;          // short, human, no secrets/paths
}

interface PlannerWarehouseEvidence {
  availability: WarehouseEvidenceAvailability;
  // Always true in Stage 18H: warehouse evidence is never canonical truth.
  reportOnly: true;
  items: PlannerWarehouseEvidenceItem[];
}
```

`availability: 'unavailable'` is the default and means *unknown*, never
"no evidence exists" and never "false". Missing artifacts/status stay
unavailable/unknown.

## Boundaries Held

- Read-only only; no canonical writes; no planner/Build Plan/role/evidence/
  validation mutation.
- No automatic Suggested Build generation or load; no automatic Preview; no
  optimiser changes.
- No live EDSM/API crawl, no Docker invocation, no production scheduler/job
  wiring, no new dedicated backend endpoint.
- Report-only warehouse evidence is never treated as canonical truth and never
  overrides canonical app data or infrastructure counts.
- Missing artifact/status remains unavailable/unknown.
- Source labels (`canonical`, `observed`, `warehouse_report_only`, `unknown`)
  are always visible.
- No secrets, DSNs, file paths, or private operator details are exposed; the
  model carries only short human summaries chosen by the caller.

## Future Integration Path

To safely surface *per-system* warehouse evidence in the user planner later, a
future stage (after the Stage 18I canonical-write design review and the Stage
18I.5 database-boundary review) would need:

1. **A per-system, report-only artifact contract.** Operators would publish a
   sanitized JSON artifact keyed by `system_id64`, e.g.
   `warehouse_planner_evidence/v1`, derived from the read-only reconciliation
   report. It must carry source labels, freshness, and conservative labels, and
   must never include canonical write instructions, secrets, DSNs, or paths.
2. **A read-only, appropriately-gated endpoint.** Either a non-admin,
   read-only endpoint that serves only the sanitized per-system evidence
   summary, or an explicit product decision that this remains operator-only.
   The access boundary must be decided deliberately, not inherited from the
   admin token by accident.
3. **A safe-join key.** The planner would request evidence by the current
   system's `id64`. If the artifact has no entry for that system, the card
   stays `unavailable` (unknown), never `false`.
4. **Unchanged trust semantics.** Even fully wired, warehouse evidence remains
   `reportOnly` and source-labelled; it must not mutate Build Plans, roles,
   observed evidence, validation, scoring, Preview, or optimiser state.

Until that contract and boundary review exist, the planner bridge stays on the
sanitized provenance-cockpit path and does not pretend warehouse evidence is a
true per-system planner fact source.

## Validation

See the PR body for the exact commands. Stage 18H adds frontend component tests
for the unavailable state, report-only/source-labelled rendering, stale/risky/
blocked wording, source separation, and the no-control/no-mutation guarantee. It
changes no backend behaviour and no canonical data.
