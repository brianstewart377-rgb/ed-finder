# Stage 22B - Current-State Planner Evidence Hardening

## Purpose

Stage 22B hardens the read-only planner evidence path so it remains useful
without letting runtime fixtures, historical authority snapshots, or global
project safety state masquerade as live per-system evidence.

This checkpoint keeps the Stage 18H bridge architecture:

- the dedicated `warehouse_planner_evidence/v1` endpoint remains the preferred
  planner source;
- the provenance cockpit remains the safe read-only fallback;
- the planner still runs on canonical truth, not on warehouse/provenance
  evidence.

## What This Checkpoint Changes

- Runtime per-system fixture data is isolated behind explicit development/test
  providers rather than being returned automatically in normal runtime paths.
- Unknown systems remain unknown by default; missing safe evidence does not
  silently collapse into fabricated `available` states.
- Historical authority JSON now contributes only conservative global safety
  status, not live-looking selected-system source-run or artifact details.
- The planner warehouse evidence bridge no longer mixes global safety statements
  like `DB writes remain unauthorized` into selected-system evidence items.
- Freshness now uses an explicit conservative vocabulary:
  `fresh`, `stale`, `unknown`, `not_evaluated`.
- Missing timestamps no longer imply `fresh`.
- The provenance panel keeps authority/safety status in its own explicit
  section.

## Boundaries Preserved

- Read-only only.
- No planner mutations.
- No DB writes.
- No Stage 19 operator execution.
- No canonical apply.
- No rebaseline.
- No scheduler/service activation.
- No production-like DB execution.

## Implementation Notes

### Backend

- `apps/api/src/provenance_cockpit.py`
  - runtime fixture access now goes through an explicit development/test
    provider;
  - missing or malformed authority JSON fails safely and keeps guardrails
    conservative;
  - current safety status is derived from the latest active authority section
    (`stage22`, then `stage21`, then `stage20`);
  - historical proof snapshots are no longer surfaced as live selected-system
    source-run evidence.

- `apps/api/src/warehouse_planner_evidence.py`
  - runtime fixture access is isolated behind an explicit development/test
    provider;
  - unavailable or not-yet-linked systems remain `unavailable`;
  - freshness returns `not_evaluated` when a warehouse artifact exists but no
    safe per-system evidence evaluation has occurred.

### Frontend

- `warehouseEvidenceBridge.ts`
  - dedicated endpoint remains preferred;
  - provenance fallback remains preserved;
  - global authority/safety state is no longer injected into selected-system
    evidence items.

- `WarehouseEvidenceCard.tsx`
  - supports `not_evaluated` freshness.

- `ProvenanceCockpitPanel.tsx`
  - labels the global safety section as `Authority / safety status`.

## Acceptance

Stage 22B is complete when:

- runtime fixtures are not returned by default;
- unknown systems stay unknown/unavailable unless an explicit dev/test provider
  is enabled;
- the dedicated warehouse endpoint remains preferred and provenance fallback
  still works safely;
- missing timestamps never imply `fresh`;
- global safety state is visible separately from selected-system evidence;
- all changes remain read-only and keep Stage 19 deferred.
