# V3 Browser Validation Lanes

**Status:** current browser validation authority

**Application under test:** `apps/web/` (Svelte/SvelteKit) with the fresh
Babylon renderer

## Current integration status

PR #601 is the active V3 integration lane. Known exact head
`12eebac48ca9286e0fd8c180cc5f552dc922d07e` contains the real
Explore/Finder -> fresh Babylon -> canonical Inspect product slice and the
Review Lab rebase to `apps/web/` plus Babylon. Validation for that exact head is
still red/stabilizing. It is not a green or complete checkpoint.

Every claim is SHA-scoped. A newer push invalidates older check and screenshot
claims until the required lanes run against the new exact head.

## Two separate map lanes

| Lane | Responsibility | Data/environment |
|---|---|---|
| **Product E2E / Visual Acceptance** | Prove real user journeys, browser integration, interaction, accessibility and intended visual output for the V3 product. | Production-shaped application contracts and accepted test fixtures; never production credentials or live production mutation. |
| **Review Lab** | Give reviewers deterministic, failure-diagnosable coverage of the same V3 journeys and edge cases. | Isolated disposable services and synthetic deterministic data. |

Both lanes run the same `apps/web/` Svelte application and fresh Babylon
renderer. Review Lab changes only synthetic data and environment. It is not a
parallel product, a React/R3F compatibility lane, or a substitute for Product
E2E/Visual Acceptance. Product E2E success likewise does not substitute for the
Review Lab check when both are required.

## Protected browser tooling

Cypress is the V3 browser/E2E, accessibility and screenshot authority.
Chromium-family and Firefox are the initial protected browser classes. Edge may
represent the production Chromium family; WebKit/Safari remains an explicit
compatibility target rather than a hidden requirement.

Playwright is historical migration evidence only. It is not active V3 tooling,
a required V3 check, or authority for new test coverage. Historical results may
inform parity without making their harness current.

Vitest and Testing Library own fast component/unit behaviour. Browser-lane
tests should assert user-visible outcomes through stable roles, labels and
product identities rather than renderer implementation details.

## Required shared assertions

Both map lanes preserve these invariants where their scenario applies:

- Explore/Finder can search, choose a result, fly to and pick a stable target,
  then open canonical Inspect without a parallel detail implementation.
- **Search From Here** and **Systems Within...** expose explicit
  viewport/reference/region/radius scope and explicit count, bounds and
  truncation state.
- selected, highlighted and reference targets survive wide, regional, local and
  System LOD transitions.
- overlapping targets have keyboard-accessible disambiguation, and every
  pickable item has an equivalent semantic DOM path.
- keyboard, focus, screen-reader naming, colour independence and reduced motion
  remain usable.
- planned, schematic, derived, ambient and authoritative representations cannot
  be mistaken for one another.
- empty, stale, bounded/truncated and error responses are honest; no partial
  result is presented as complete.
- resize/DPR change and renderer recovery preserve restorable camera and
  selection state.

Visual evidence uses deterministic viewport, device-pixel ratio, fixture and
animation/reduced-motion settings. Intentional visual changes update accepted
evidence only with reviewer-visible rationale. Failure artifacts must be
sanitized and contain no credentials or private commander data.

## Lane-specific coverage

Product E2E / Visual Acceptance owns the production-shaped journey across
application routing and real service boundaries: Explore -> Finder -> Babylon
selection/fly-to -> canonical Inspect, plus subsequent Plan and Review handoffs
as those slices land. It also owns supported-browser and representative visual
acceptance evidence.

Review Lab owns deterministic scenario breadth: dense/overlapping systems,
empty and truncated search, missing/uncertain truth, schematic System data,
planned contributions, browser/backend fallback, and stable diagnostics. Its
seed data may make rare states easy to reproduce but may not change product
semantics or introduce Lab-only UI behaviour.

## Exact-head acceptance

A lane is green only when its required checks and artifacts identify the exact
latest PR head SHA and all substantive findings are dispositioned under the
pull-request acceptance policy. Partial success, an older SHA, one browser
class, or one of the two lanes cannot be generalized into a completed V3
checkpoint.

The active #601 head named above remains red/stabilizing until fresh evidence
proves otherwise. This document records the boundary; it does not waive or
predict check results.
