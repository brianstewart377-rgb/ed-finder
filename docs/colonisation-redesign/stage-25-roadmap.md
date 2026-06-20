# Stage 25 - Cockpit, Map, And Visual-System Baseline

## Status

Stage 24 is closed.

Stage 25 is the new explicit post-Stage-24 control.

Stage 25A is prepared as the current-state audit, map product decision, and
visual-system baseline checkpoint.

Stage 25B remains unstarted.

Stage 25C remains unstarted.

Stage 25D remains unstarted.

Stage 25E remains unstarted.

## Current Product Recovery State

PR #257 fixed the Firefox map scroll/zoom crash.

Map status is `stable_after_pr257_manual_firefox_verification`.

The map is retained as a secondary Explore surface only.

Its current product value is low and must be proven before any deeper planner
integration is considered.

The map may later become a Candidate Systems Map, but that is not authorized or
implemented here.

## Primary Objective

Stage 25 has exactly one primary objective:

> Establish a restrained cockpit-oriented product and visual baseline for the
> canonical player journey while keeping the recovered map live only as a
> secondary Explore surface, preserving the current Colony Planner runtime, and
> authorizing no database or operational write lane.

## Canonical Player Journey

The canonical player journey is:

`Explore → Inspect → Plan → Simulate/Sequence → Review Evidence → Export/Share`

Stage 25 planning treats this journey as the product-ordering baseline for
later work.

## Product Inventory Baseline

The current inventory status is:

- Colony Planner: `canonical_live`
- simulation-preview: `reusable_but_unwired`
- map: `canonical_live` as a secondary Explore surface

This control does not wire simulation-preview into live routes.

This control does not redesign the map.

This control does not alter Colony Planner runtime behaviour.

## Map Product Decision

The map remains live because PR #257 recovered baseline interaction safety after
manual Firefox verification.

That recovery does not make the map a primary planning surface.

The map is therefore retained only as a secondary Explore surface until its
value is proven by later evidence.

No Stage 25A work authorizes:

- deeper planner-map integration;
- map-led planning workflows;
- renderer replacement;
- new map features, layers, or overlays;
- Candidate Systems Map implementation.

## Visual-System Direction

Stage 25 adopts a restrained cockpit-oriented visual-system refresh.

Glass or translucency is limited to workspace chrome only, or absent entirely.

Glass is not authorized on dense evidence cards, tables, planning canvases, map
labels, or technical provenance surfaces.

The visual baseline must keep the product readable, operationally serious, and
compatible with evidence-heavy review surfaces.

## Evidence Language Principles

Stage 25 preserves evidence-language discipline:

- evidence must be player-facing first: clear enough to support a planning
  decision, concise enough not to overwhelm normal use, and paired with an
  understandable next action;
- that simplification must remain technically honest and must never hide
  uncertainty, freshness, provenance, report-only status, bounded or incomplete
  coverage, unavailable data, unknown state, or non-canonical status;
- player-facing wording may progressively disclose technical provenance and
  implementation detail, but it must never convert a weak, unavailable,
  observed, bounded, or report-only signal into apparent canonical truth;
- evidence must remain explicit rather than atmospheric;
- dense evidence surfaces must stay legible before decorative chrome;
- review posture must remain compatible with provenance-heavy planning work;
- current-state statements must not overclaim certainty or readiness.

## Explicit Deferrals

Mission intelligence remains deferred and unauthorized in Stage 25A.

Ring/mining work remains deferred and unauthorized in Stage 25A.

Stage 25B, Stage 25C, Stage 25D, and Stage 25E remain unstarted.

## Relationship To Earlier Controls

Stage 24 is closed and remains historical.

Stage 19 remains separately gated.

No database or operational write lane is authorized by Stage 25A.

Stage 25A does not authorize:

- Stage 19 execution;
- database commands or database writes;
- canonical apply;
- rebaseline;
- scheduler, service, or timer activation;
- source acquisition;
- operator activity.

## Checkpoint Plan

| Checkpoint | Purpose |
| --- | --- |
| Stage 25A | Current-state audit, map product decision and visual-system baseline |
| Stage 25B | Evidence language and visual-system primitives |
| Stage 25C | Unified cockpit entry and shared context |
| Stage 25D | Selected planner and simulation integration |
| Stage 25E | Consolidation and closeout |

## Acceptance Boundaries

Stage 25A is acceptable only if:

- Stage 24 remains closed;
- PR #257 is recorded as the map recovery point;
- the map remains a secondary Explore surface only;
- the canonical player journey is explicit;
- the visual direction stays restrained and cockpit-oriented;
- dense content remains non-glass by default;
- mission intelligence remains deferred;
- ring/mining remains deferred;
- Stage 19 remains separately gated;
- no database or operational write lane is authorized.
