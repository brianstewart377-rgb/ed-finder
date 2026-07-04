# Stage 25C - Product Shell, Shared Context And Cockpit Visual Foundation (Implementation Contract)

## Status

Stage 25C is active and not complete.

- Slice 1 — product shell and navigation hierarchy: `complete_merged` in PR #262.
- Slice 2 — selected-system context spine: `contract_defined_pending_implementation`.
- Later Stage 25C slices remain separately gated and are not complete merely because
  Slice 1 or bounded follow-on Plan work has merged.

This document remains the parent Stage 25C contract. The detailed controlling
contract for Slice 2 is
[`stage-25c-selected-system-context-slice.md`](./stage-25c-selected-system-context-slice.md).

The earlier `slice_1_in_progress_pending_review` wording is historical and must not
be used as current runtime status. Defining either contract does not by itself
authorize runtime implementation.

## Product Problem

The problem is not simply the number of top-level tabs.

The current live navigation exposes ten top-level tabs (Finder, Watchlist, Pins,
Compare, Advanced Search Tuning, FC Planner, Colony Tracker, Map, Admin,
Operator). Reducing that count alone would not fix the product.

The real problems are:

- fragmented player intent: navigation follows feature ownership rather than
  player jobs, so the player must remember where tools live instead of being
  guided to the next action;
- duplicate planning concepts: the live Colony Planner and the
  `reusable_but_unwired` simulation-preview capability encode overlapping
  planning, sequence, evidence, and role concepts that risk becoming parallel
  competing products;
- unclear selected-system continuity: the selected system is treated as
  ephemeral or route-specific and does not travel cleanly across Finder,
  System Detail, and the planner;
- weak workspace hierarchy: the current workspace, the active task, the selected
  system, the current status, and the next action are not consistently legible;
- technical evidence language appearing without enough player-context framing:
  provenance, report-only, bounded, and freshness language can appear before the
  player understands what it means for their plan.

Stage 25C exists to fix product structure and continuity, not to add surface
decoration over the existing fragmentation.

## Stage 25C Objective

Stage 25C has exactly one objective:

> Establish the product shell, selected-system context spine, workspace
> hierarchy, and visual-system foundation needed for ED-Finder to behave as one
> coherent desktop-first colony-planning product.

## Required UX Decisions

Stage 25C implementation must resolve these decisions explicitly:

### Explore, Inspect, Plan, Review/Export relationships

- the product journey is `Explore → Inspect → Plan → Review / Export`;
- Explore owns discovery (Finder, goal-led presets, candidate discovery,
  optional map, saved candidates);
- Inspect is contextual System Detail and the hand-off into planning, not a
  competing primary workspace;
- Plan is the primary serious colony-planning workspace and the basis of the
  future Colony Cockpit;
- Review/Export owns evidence/validation review, provenance disclosure, plan
  comparison, and shareable outputs.

### Future top-level navigation principles

- the future top-level model is `Explore`, `Plan`, `Review`;
- this contract defines the principles and target home for each current tab; it
  does not force every phase to become a top-level route in the first slice;
- operator/admin surfaces remain separate from normal player navigation;
- profile, saved data, and sync placement is an explicit unresolved discovery
  decision (see below) and must not be assumed into Admin, Settings, or Review
  without live-flow evidence.

### System Detail as contextual inspect hand-off

- System Detail remains a contextual surface reached from Explore;
- it must present a concise explanation, an evidence summary, and a clear,
  explicit hand-off action into Plan;
- it must not duplicate the full planning workspace.

### Selected-system context contract

- there must be a persistent selected-system context that the player can see and
  trust while moving between Explore, Inspect, and Plan;
- the context must show the current system identity and a short evidence-posture
  summary without overemphasising raw ID64;
- the contract must define when the context changes, when it persists, and how
  it is represented in deep links and direct routes;
- it must avoid stale or misleading state when the player returns via bookmark or
  direct route;
- when the selected system has no active plan, the context must still show the
  system plus evidence summary and offer an explicit start-planning action.

Slice 2 defines the exact selected-system state, route, transition, failure, and
no-active-plan rules for this parent requirement.

### Distinction between selected system, saved candidate, compared system, and active plan

- selected system: the system currently in focus for inspect/plan;
- saved candidate: a system the player has kept (the current Watchlist
  cloud-synced and Pins device-local concepts must be distinguished by their
  persistence model, not by implementation accident);
- compared system: a system placed into a comparison set;
- active plan: a plan in progress for a system;
- these four must be conceptually distinct and must not be silently conflated.

### Profile/sync as an explicit unresolved discovery decision

- profile and sync are currently reachable under operator/admin-style surfaces;
- their final placement requires current live-flow evidence and is explicitly
  unresolved in this contract;
- Stage 25C may not assume profile/sync belongs in Admin, Settings, or Review
  without that evidence.

### Player/operator boundary

- operator and admin functionality must not appear inside normal player
  navigation;
- the player shell and the operator surfaces remain separated.

### Desktop-first planning requirements

- planning is a desktop/laptop task;
- the product shell and planner must work well at desktop widths.

### Finder/basic inspection mobile requirements

- Finder and basic System Detail inspection are the intended phone-width use
  cases and must remain functional at narrow widths.

### Planner mobile resilience-only requirement

- planner phone-width access is resilience-only: no crash, no lost context, no
  trapped navigation, a clear exit/back path, and no misleading product promise;
- this contract does not authorize a mobile-first planner redesign.

## Visual-System Foundation

Stage 25C defines the restrained cockpit-oriented visual-system foundation. It
is a substantial product-shell and visual-system redesign, not a cosmetic
reskin, and it must not be decorative.

### Workspace shell

- a consistent product shell that frames every workspace with a clear workspace
  title, current task, status, and next action.

### Selected-system context bar

- a persistent context bar that shows the selected system and its evidence
  posture summary, consistent across Explore, Inspect, and Plan.

### Panel hierarchy

- one readable hierarchy: workspace context -> primary decision/action ->
  content -> evidence/supporting detail;
- consistent elevation and explicit panel ownership.

### Typography tiers

- a defined typography scale with distinct tiers for workspace title, section
  heading, body, and dense/technical detail.

### Spacing tiers

- a defined spacing scale that keeps dense planning content legible and keeps
  navigation and first-use surfaces uncluttered.

### Semantic status language

- one semantic status/evidence language system reused across surfaces;
- text labels must accompany colour; colour is never the only signal.

### Evidence-state visual rules

- planned, projected, observed, inferred, canonical, bounded, unavailable,
  unknown, and not-evaluated states must remain visually and semantically
  distinguishable.

### Planned/projected/observed/report-only distinction

- player choices, projected outcomes, observed facts, and report-only evidence
  must be visibly distinct;
- canonical planner truth must never be confused with report-only, bounded,
  observed, unavailable, unknown, fallback, or non-canonical evidence.

### Progressive disclosure rules

- dense technical detail uses progressive disclosure rather than disappearing;
- the first layer is readable body copy; technical provenance is revealed on
  demand and remains keyboard accessible.

### Limited workspace-chrome translucency rule

- any glass or translucency is limited to app chrome, high-level workspace
  framing, overlays, or modal shell only;
- glass is not applied to dense evidence cards, tables, planning canvases, map
  labels, technical provenance, or long-form decision content.

### Focus, contrast, reduced-motion, and keyboard requirements

- visible focus rings on actions and disclosure;
- sufficient contrast for dense content;
- reduced motion is respected;
- keyboard navigation is preserved.

### Visual regression expectations

- the foundation must be covered by visual regression and accessibility checks
  when implemented, with baselines for the shell, context bar, and evidence
  states.

## Explicitly Out Of Scope

Stage 25C implementation explicitly excludes:

- simulation-preview wiring into live routes;
- map redesign;
- map integration beyond existing entry points;
- renderer work or new map libraries;
- planner data, model, or rule changes;
- a facility browser;
- mission intelligence;
- mining/ring features;
- plan persistence, import, or collaboration;
- database or Stage 19 activity.

## Stage 25C Implementation Slices

1. **Product shell and navigation hierarchy** — complete and merged in PR #262:
   the shell and Explore/Plan/Review framing without removing existing capability.
2. **Selected-system context spine** — contract defined; implementation pending:
   persistent selected-system context and its exact persistence/deep-link rules.
   The detailed slice contract is `stage-25c-selected-system-context-slice.md`.
3. **Cockpit visual-system foundation and semantic evidence primitives** — pending:
   tokens, typography/spacing tiers, elevation, and the reused semantic status
   language.
4. **System Detail -> Plan hand-off and workspace continuity** — pending further
   bounded follow-through: make the inspect-to-plan hand-off explicit while keeping
   the planner canonical and live.
5. **Accessibility, responsive verification, and visual regression baseline** —
   pending: desktop-first verification, Finder/System Detail mobile checks, planner
   phone-width resilience, and regression/accessibility baselines.

## Acceptance Criteria

A future Stage 25C implementation is acceptable only if:

- the player can understand which workspace they are in;
- the selected system is visible and accurately scoped;
- the `Explore → Inspect → Plan` hand-off is explicit;
- the Colony Planner remains canonical and live;
- evidence remains technically honest and never presents report-only, bounded,
  observed, unavailable, unknown, or non-canonical evidence as canonical truth;
- no operator functionality appears in player navigation;
- the desktop shell works at 1440x900 and 1280x720;
- Finder and System Detail remain functional at 390x844;
- planner phone-width is resilience-only with no crash and a clear exit path;
- the map is not made central and no deeper map integration is introduced;
- no Stage 19 or write capability is introduced.

## Accessibility Criteria

- visible focus on all interactive shell and disclosure controls;
- colour is never the sole carrier of meaning;
- dense content meets contrast requirements;
- reduced-motion preference is respected;
- keyboard operation of the shell, context bar, and disclosure is preserved.

## Desktop And Mobile Criteria

- desktop-first targets: 1440x900 and 1280x720, with 1024x768 as a constrained
  diagnostic width;
- mobile target: 390x844 for Finder and basic System Detail inspection;
- planner at phone width is resilience-only: no crash, no lost context, no
  trapped navigation, and a clear exit/back path.

## Deferred Decisions

Stage 25C implementation must defer, not pre-empt:

- final profile/sync placement (requires live-flow discovery evidence);
- any map product expansion (Stage 25G);
- planner/simulation integration (Stage 25D);
- a standalone facility browser (Stage 25F);
- mission intelligence and mining/ring planning;
- plan persistence, import, accounts, OAuth, and collaboration.

## Authority Boundaries

Stage 24 remains closed.

Stage 19 remains separately gated.

PR #257 remains the map recovery point and does not authorize a map redesign.

This contract does not authorize:

- Stage 19 execution;
- database commands;
- database writes;
- canonical apply;
- rebaseline;
- scheduler, service, or timer activation;
- source acquisition;
- operator activity;
- runtime UI implementation merely by defining this contract.