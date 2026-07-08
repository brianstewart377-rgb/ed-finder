# Stage 25A Current-State Map Product Visual Baseline

## Purpose

Stage 25A records the real current-state audit, the map product decision, and
the visual-system baseline that follow the Stage 24 closeout.

Stage 25 is a new explicit post-Stage-24 control.

This checkpoint is docs/static-test-only and does not implement Stage 25B,
Stage 25C, Stage 25D, or Stage 25E.

## Preserved Prior State

Stage 24 is closed.

PR #257 fixed the Firefox map scroll/zoom crash.

Map status is `stable_after_pr257_manual_firefox_verification`.

The recovered map remains live, but only as a secondary Explore surface.

Its product value is currently low and must be proven before deeper planner
integration is considered.

The map may later become a Candidate Systems Map, but that is not authorized or
implemented here.

## Stage 25 Primary Objective

Stage 25 has exactly one primary objective:

> Define the restrained cockpit-oriented product baseline for the canonical
> player journey, preserve the recovered map as a secondary Explore surface,
> and keep all deeper planner integration, write-capable lanes, and operational
> work explicitly unauthorized.

## Canonical Journey

The canonical player journey is:

`Explore → Inspect → Plan → Simulate/Sequence → Review Evidence → Export/Share`

The map is retained only inside the `Explore` portion of that journey unless a
later control explicitly proves and authorizes more.

## Current Inventory Verdict

The current inventory status is:

- Colony Planner: `canonical_live`
- simulation-preview: `reusable_but_unwired`
- map: `canonical_live` as a secondary Explore surface

This means:

- Colony Planner remains the canonical live planning surface;
- simulation-preview is reusable implementation inventory, but is still
  unwired to live routes;
- the map stays live as a secondary Explore surface, not a primary planning
  cockpit.

## Map Product Decision

Stage 25A records a restrained product verdict:

`retain_as_secondary_explore_surface`

That verdict preserves the recovered map without turning it into the centre of
the product.

This checkpoint does not authorize:

- map redesign;
- renderer replacement;
- new map controls, layers, or product features;
- planner-map workflow coupling;
- Candidate Systems Map implementation.

## Visual-System Baseline

Stage 25A adopts a restrained cockpit-oriented visual-system refresh.

Any glass or translucency is limited to workspace chrome only or omitted
entirely.

Glass is explicitly disallowed for dense evidence cards, tables, planning
canvases, map labels, and technical provenance surfaces.

The visual system must stay legible, evidence-first, and operationally serious.

## Evidence-Language Principles

Stage 25A preserves evidence-language principles:

- evidence must be presented in player-facing language first: clear enough to
  support a planning decision, concise enough not to overwhelm normal use, and
  paired with an understandable next action;
- that simplification must remain technically honest and must never hide
  uncertainty, freshness, provenance, report-only status, bounded or incomplete
  coverage, unavailable data, unknown state, or non-canonical status;
- player-facing wording may progressively disclose technical provenance and
  implementation detail, but it must never convert a weak, unavailable,
  observed, bounded, or report-only signal into apparent canonical truth;
- evidence language must stay explicit and reviewable;
- decorative styling must not compete with technical provenance;
- dense evidence surfaces must prioritize clarity over ambience;
- product language must distinguish current state, deferred work, and future
  possibility without overclaiming.

## Explicit Deferrals

Mission intelligence remains deferred and unauthorized.

Ring/mining work remains deferred and unauthorized.

Stage 25B through Stage 25E remain unstarted and unimplemented.

## Safety Boundaries

Stage 19 remains separately gated.

No database or operational write lane is authorized.

This checkpoint does not authorize:

- Stage 19 execution;
- database commands;
- database writes;
- canonical apply;
- rebaseline;
- scheduler, service, or timer activation;
- source acquisition;
- operator activity.

## Checkpoint Table

| Checkpoint | Purpose |
| ---------- | -------------------------------------------------------------------- |
| Stage 25A  | Current-state audit, map product decision and visual-system baseline |
| Stage 25B  | Evidence language and visual-system primitives                       |
| Stage 25C  | Unified cockpit entry and shared context                             |
| Stage 25D  | Selected planner and simulation integration                          |
| Stage 25E  | Consolidation and closeout                                           |

## Outcome

Stage 25A establishes the baseline only.

It does not start Stage 25B, Stage 25C, Stage 25D, or Stage 25E.

It does not authorize any database, canonical, scheduler, source-acquisition,
or other operational write-capable lane.

