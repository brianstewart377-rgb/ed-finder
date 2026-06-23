# Stage 25 - Cockpit Product Shell Roadmap (Reset)

## Status

Stage 24 is closed.

Stage 25 is the new explicit post-Stage-24 product programme.

This document is the authoritative Stage 25 roadmap reset. It supersedes the
earlier Stage 25A baseline roadmap wording while keeping the Stage 25A baseline
document itself as a frozen historical record.

Programme status after this reset:

- Stage 25A is complete.
- Stage 25B is complete and merged.
- Stage 25C Slice 1 is in progress and pending review.
- Stage 25D, Stage 25E, Stage 25F, Stage 25G, and Stage 25H are unstarted.

The original roadmap-reset PR was documentation, roadmap authority, static
tests, and guardrails only. Stage 25C runtime implementation now begins
separately with Slice 1: product shell, navigation hierarchy, minimal selected-
system context scaffolding, and visual foundation framing only.

## Stage 25B Status Correction

Stage 25B is no longer `implemented_in_this_pr_pending_review`.

Stage 25B is complete and merged:

- merged via PR #259 (`Add Stage 25B evidence and visual-system primitives`);
- merged into `origin/main` on 2026-06-20;
- present at `origin/main` merge commit `e528c51`.

Stage 25A is complete and merged via PR #258 (merge commit `7c48474`).

No manual visual verification is claimed here beyond what the merged Stage 25B
record itself documents.

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

> Turn ED-Finder from a collection of capable but fragmented workspaces into one
> coherent, provenance-backed Elite Dangerous colony-planning product, by
> establishing a product shell, a persistent selected-system context, a clear
> Explore/Plan/Review hierarchy, and a restrained cockpit-oriented visual
> system - while preserving the live Colony Planner runtime, keeping the map as
> a secondary Explore surface, and authorizing no database or operational write
> lane.

## Product-Level Journey

The product-level player journey is:

`Explore → Inspect → Plan → Review / Export`

Within those phases:

- Explore: Finder, goal-led presets, candidate discovery, optional map, and
  saved candidates.
- Inspect: System Detail, concise explanation, system comparison, evidence
  summary, and a clear hand-off into planning.
- Plan: the future canonical Colony Cockpit - build planning, body/slot
  decisions, facilities/roles, sequence/CP, projected outcomes, and explainable
  next actions.
- Review / Export: evidence and validation review, provenance disclosure, plan
  comparison, and shareable review/export outputs.

This is a product-level hierarchy. It does not require every phase to become a
top-level route immediately.

## Future Top-Level Hierarchy

The likely future top-level navigation model is:

```text
Explore
Plan
Review
```

Principles:

- Inspect remains contextual System Detail, not a competing primary workspace.
- Plan becomes the primary serious colony-planning workspace.
- Review owns comparison, evidence review, validation, exports, and saved
  decision context where appropriate.
- the map remains a secondary Explore surface until its player value is proven.
- operator/admin surfaces remain separate from normal player navigation.
- profile, saved data, and sync require a separate current-product audit before
  final placement; this roadmap does not assume they belong in Admin, Settings,
  or Review without live evidence.

The current live navigation still exposes ten top-level tabs (Finder, Watchlist,
Pins, Compare, Advanced Search Tuning, FC Planner, Colony Tracker, Map, Admin,
Operator). Re-homing those tabs into the future hierarchy is Stage 25C contract
work and later implementation, not part of this reset.

## Product Inventory Baseline

The current inventory status is:

- Colony Planner: `canonical_live`
- simulation-preview: `reusable_but_unwired`
- map: `canonical_live` as a secondary Explore surface

System Detail is a contextual Inspect surface and the live hand-off into the
Colony Planner; it is not a competing primary planning workspace.

Colony Planner is the canonical live planning workspace and is the basis for the
future Plan cockpit.

simulation-preview is reusable implementation inventory but remains unwired to
live routes; it is not wired here and must not be wired before Stage 25D.

This reset does not wire simulation-preview into live routes.

This reset does not redesign the map.

This reset does not alter Colony Planner runtime behaviour.

## Map Product Decision

The map remains live because PR #257 recovered baseline interaction safety after
manual Firefox verification.

That recovery does not make the map a primary planning surface.

The map is therefore retained only as a secondary Explore surface until its
value is proven by later evidence (see Stage 25G).

This roadmap does not authorize:

- map redesign;
- Candidate Systems Map implementation;
- new map overlays;
- map-led planning workflows;
- deeper planner-map integration;
- renderer replacement;
- PixiJS, deck.gl, MapLibre, Leaflet, D3, WebGL, or a new map library.

The current custom canvas renderer remains the default until measured evidence
demonstrates a real capability or performance problem.

## Visual Redesign Decision

Stage 25 authorizes a substantial product-shell and visual-system redesign.

This is not a cosmetic reskin. It is not permission for decorative styling. The
redesign must improve player orientation, task hierarchy, selected-system
continuity, workspace ownership, evidence comprehension, next-action clarity,
long-session planning readability, and the distinction between player choices,
projections, observations, and report-only evidence.

The redesign must not merely add gradients, blur, badges, panels, or new tabs
over the existing fragmented structure.

Stage 25 adopts a restrained cockpit-oriented visual-system refresh.

Glass or translucency is limited to workspace chrome, high-level workspace
framing, overlays, or modal shell only, or absent entirely.

Glass is not authorized on dense evidence cards, tables, planning canvases, map
labels, or technical provenance surfaces.

The visual baseline must keep the product readable, operationally serious, and
compatible with evidence-heavy review surfaces. Dense content remains non-glass
by default.

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
- planned, projected, observed, inferred, canonical, bounded, unavailable,
  unknown, and not-evaluated states must remain distinguishable;
- text labels must accompany colour;
- evidence must remain explicit rather than atmospheric;
- dense evidence surfaces must stay legible before decorative chrome;
- review posture must remain compatible with provenance-heavy planning work;
- current-state statements must not overclaim certainty or readiness.

## Revised Stage 25 Programme

| Checkpoint | Status | Purpose |
| --- | --- | --- |
| Stage 25A | complete | Current-state audit, map product decision and visual-system baseline |
| Stage 25B | complete (merged in PR #259) | Evidence language and visual-system primitives |
| Stage 25C | Slice 1 in progress and pending review | Product shell, shared selected-system context, and cockpit visual foundation |
| Stage 25D | unstarted | Canonical Colony Cockpit and planner/simulation integration |
| Stage 25E | unstarted | Review, evidence, validation and export coherence |
| Stage 25F | unstarted | Facility intelligence and explainable next actions |
| Stage 25G | unstarted | Explore and map product-value decision |
| Stage 25H | unstarted | Product consolidation, accessibility and closeout |

### Stage 25A - Current-State Audit, Map Product Decision and Visual-System Baseline

Status: complete. Historical baseline only. Its completed evidence is not
rewritten beyond minimal status/link corrections needed for roadmap continuity.

### Stage 25B - Evidence Language and Visual-System Primitives

Status: complete and merged (PR #259). Delivered the merged evidence-language
primitives and desktop-first review acceptance changes. It is not reopened for
broad polish.

### Stage 25C - Product Shell, Shared Context and Cockpit Visual Foundation

Status: Slice 1 in progress and pending review.

Primary objective: implement the first runtime slice of the coherent player
product shell, the Explore/Plan/Review hierarchy, truthful shared-context
scaffolding, and the cockpit-oriented visual-system foundation without
broadening into Stage 25D or later work.

Slice 1 implementation scope: player-facing product shell; Explore/Plan/Review
hierarchy; separate operator/admin lane; shell-level selected-system context
framing where existing route truth provides it; System Detail contextual hand-
off clarity; desktop-first workspace framing; Finder/mobile basic-inspection
compatibility; planner phone-width resilience-only handling.

Later Stage 25C slices remain pending for deeper selected-system continuity
rules, broader cockpit visual-system consolidation, and follow-through
verification.

Explicitly out of scope for Stage 25C implementation: simulation-preview
integration; map redesign or deeper map integration; planner rules/data changes;
facility browser; mission intelligence; mining/ring planning; new backend/API
contracts unless a read-only adapter is proven necessary; Stage 19 or data-write
activity.

The full Stage 25C implementation contract lives in
`stage-25c-product-shell-shared-context-contract.md`. Defining that contract
did not by itself authorize runtime implementation; this first runtime slice is
separately authorized and remains pending review.

### Stage 25D - Canonical Colony Cockpit and Planner/Simulation Integration

Status: unstarted.

Purpose: use the Stage 25C shell and context model to integrate the strongest
existing planner, sequence, simulation, validation, and evidence capabilities
into one coherent Plan workspace. This stage must prevent the live Colony Planner
and the reusable simulation-preview capability from becoming parallel competing
products. It must not start until Stage 25C's navigation, context, and visual
foundation are accepted.

### Stage 25E - Review, Evidence, Validation and Export Coherence

Status: unstarted.

Purpose: make Review/Export a coherent player flow for evidence, validation,
plan review, comparison, and shareable outputs without letting report-only
evidence become canonical planner truth.

### Stage 25F - Facility Intelligence and Explainable Next Actions

Status: unstarted.

Purpose: build a bounded Plan-context facility/role intelligence capability using
existing planner rules and models where data supports it. This is not permission
to create a broad standalone facility browser before the cockpit is coherent.

### Stage 25G - Explore and Map Product-Value Decision

Status: unstarted.

Purpose: test and define whether the map can materially improve candidate
discovery, regional/sector orientation, or system selection before any
substantial map product redesign is authorized. This stage may recommend no map
expansion if player value is not demonstrated.

### Stage 25H - Product Consolidation, Accessibility and Closeout

Status: unstarted.

Purpose: remove or alias obsolete secondary entry points, complete cross-surface
visual and evidence consistency, complete accessibility and visual regression
coverage, and close the Stage 25 programme.

## Explicit Deferrals

Mission intelligence remains deferred and unauthorized; there is insufficient
trustworthy data foundation.

Ring/mining work remains deferred and unauthorized; there is insufficient
player-actionable, fresh composition/hotspot/confidence evidence.

A broad standalone facility browser is deferred until the cockpit is coherent.

Plan import, persistence, accounts, OAuth, and collaboration are deferred pending
a separate proven user-value and safety model.

## Relationship To Earlier Controls

Stage 24 is closed and remains historical.

Stage 19 remains separately gated.

No database or operational write lane is authorized by this roadmap reset.

This roadmap does not authorize:

- Stage 19 execution;
- database commands or database writes;
- canonical apply;
- rebaseline;
- scheduler, service, or timer activation;
- source acquisition;
- operator activity.

## Do Not Build Yet

This reset explicitly does not build, and does not authorize building, the
following before their gating decisions are met:

- map redesign, renderer replacement, or speculative new map features;
- a Candidate Systems Map or map-led planning workflow;
- simulation-preview wiring into live routes (Stage 25D gate);
- a broad planner rewrite;
- a standalone facility browser (Stage 25F gate);
- mission intelligence or mining/ring planning surfaces;
- plan persistence, import, accounts, OAuth, or collaboration;
- a mobile-first planner rebuild;
- any database, Stage 19, canonical apply, rebaseline, or scheduler activity.

## Acceptance Boundaries

This Stage 25 roadmap reset is acceptable only if:

- Stage 24 remains closed;
- Stage 25A is recorded as complete and Stage 25B as complete/merged;
- Stage 25C is recorded as Slice 1 in progress and pending review rather than complete;
- Stage 25D through Stage 25H are recorded as unstarted;
- PR #257 is recorded as the map recovery point;
- the map remains a secondary Explore surface only and no deeper map integration
  is authorized;
- the product journey `Explore → Inspect → Plan → Review / Export` is explicit;
- the future top-level hierarchy `Explore`, `Plan`, `Review` is explicit;
- System Detail is recorded as contextual Inspect;
- Colony Planner is recorded as canonical live;
- simulation-preview is recorded as reusable but unwired;
- the visual redesign is framed as a substantial product-shell and
  visual-system redesign rather than a cosmetic reskin;
- the visual direction stays restrained and cockpit-oriented;
- dense content remains non-glass by default;
- mission intelligence remains deferred;
- ring/mining remains deferred;
- Stage 19 remains separately gated;
- no database or operational write lane is authorized;
- defining the Stage 25C contract does not by itself authorize runtime
  implementation.
