# V3 Browser Validation Lanes

**Decision date:** 2026-09-05  
**Status:** authoritative V3 validation boundary  
**Tracking:** PR #601

## Purpose

ED-Finder has two separate browser-validation lanes. They may both use Cypress,
but they do not have the same responsibility and must not be collapsed into
one another.

1. **V3 Product E2E / Visual Acceptance** proves normal application behaviour,
   user interaction, accessibility, and approved visual regression baselines.
2. **Review Lab** proves isolated deterministic synthetic edge/failure states,
   containment, and disposable-environment lifecycle.

Normal code-quality CI is outside both browser lanes.

The fact that Review Lab uses Cypress as a browser driver is an implementation
detail. It does **not** make Review Lab a second E2E or visual-regression suite.

## Fresh Babylon map rule

The V3 map is a **fresh design** in `apps/web/` using **Babylon.js** for the
spatial renderer. It is not a visual port of the retained React/R3F map and the
old React map is not the visual oracle for the new product.

Both browser lanes exercise the same `apps/web` + Babylon frontend when a
browser is required. Review Lab may vary **data, isolated runtime, and explicit
review-only failure conditions**. It must not substitute another frontend or
renderer.

## Lane 1 — V3 Product E2E / Visual Acceptance

### Authority

- Primary application target: `apps/web/`.
- Spatial renderer: Babylon.js.
- Browser authority: Cypress.
- Workflow: `.github/workflows/cypress-parity.yml` while migration compatibility
  naming remains in place.
- Runtime: the normal application/API contract, never `review_main.py`.

### Owns

- normal user journeys and navigation;
- mouse and keyboard interaction;
- Finder, Inspect, and later product-surface behaviour;
- normal Babylon camera/picking/selection/spatial behaviour;
- normal accessibility acceptance;
- browser console/network failures encountered during ordinary journeys;
- cross-browser acceptance;
- **approved screenshots and visual-regression baselines**;
- checkpoint browser acceptance before live deployment.

### Does not own

- review-only synthetic routes or failure controls;
- deliberate Review Lab API failures/fallbacks;
- disposable Review Lab database/container lifecycle;
- Review Lab containment/teardown proof;
- generic source-code CI.

The retained `frontend/` Cypress coverage is migration evidence only. It does
not regain authority over new V3 behaviour.

## Lane 2 — Review Lab

### Authority

- Workflow: `.github/workflows/review-lab.yml`.
- Wrapper: `scripts/dev/review_environment.py` and `scripts/dev/review_lab/`.
- Runtime: isolated `edfinder-review` resources, dedicated review database,
  synthetic fixtures, and guarded `review_main.py` handling.
- Frontend/renderer: the same `apps/web` + Babylon implementation used by the
  product lane.
- Cypress: controlled browser driver/collector only.

### Owns

- deterministic synthetic states that normal Product E2E cannot reliably
  produce;
- deliberate review-only API failure/empty/partial/oversized states;
- renderer fault/recovery conditions that need explicit injection;
- containment of review credentials/data/resources and external network access;
- disposable stack/process lifecycle and teardown;
- Docker/process baseline restoration;
- environment-readiness and synthetic-scenario reporting;
- failure screenshots/videos and sanitised diagnostic browser evidence.

A **minimal synthetic wiring proof** is allowed: enough to prove the Review Lab
fixture reaches the real `apps/web` + Babylon runtime. It must stop there. It
must not become a duplicate normal journey.

### Does not own

- normal Explore -> Inspect acceptance journeys;
- normal keyboard/mouse interaction regression;
- normal accessibility acceptance;
- ordinary resize/remount acceptance already covered by Product E2E;
- approved visual-regression baselines;
- product-acceptance readiness;
- a separate React/R3F rendering path;
- normal lint/format/type/unit/security/code-review responsibilities;
- production or live-checkpoint data;
- public/external data acquisition.

**Review Lab screenshots are diagnostic evidence, not approved product visual
baselines. Approved visual baselines belong only to the V3 Product E2E / Visual
Acceptance lane.**

## Synthetic-condition ownership

Review Lab conditions belong to the isolated Review Lab runtime, not to the
browser driver. Cypress may select a finite review-only mode and then drive the
real UI, but it must not manufacture the product API response with a stub as the
source of truth for the scenario.

For PR #601, failure/empty search conditions are selected through the guarded
review-only `/api/review/scenario/{mode}` control surface in `review_main.py`.
Normal `main.py` does not expose that control route.

This keeps the roles clear:

- Review Lab runtime creates the deterministic condition;
- the real `apps/web` frontend consumes it through its normal API facade;
- Cypress observes behaviour and records diagnostics.

## Normal CI — outside both browser lanes

Normal CI/Codex review owns implementation correctness that does not require a
real browser journey, including lint/formatting, type/compile checks,
unit/component/API tests, migration/script contracts, security/static analysis,
and repository/architecture guardrails.

Review Lab may run focused tests of **Review Lab infrastructure itself** to prove
containment, lifecycle, handshake, scenario routing, sanitisation, and teardown.
That exception does not make Review Lab a general code-quality lane.

## Routing rule for every new test

Use this order:

1. **Does the check require a synthetic review-only state, deliberate injected
   failure/fallback, renderer fault, or Review Lab lifecycle/containment?** Put
   it in **Review Lab**.
2. **Can the check run against the normal V3 application and does it describe
   what a user normally sees or does?** Put it in **V3 Product E2E / Visual
   Acceptance**.
3. **Does it primarily validate source, contracts, formatting, types, units,
   scripts, or security without requiring a browser journey?** Put it in
   **normal CI**.

When a check could fit more than one lane, prefer the narrowest owner and do not
duplicate the same acceptance contract across lanes.

## Hard non-overlap rules

These rules are test-enforced:

- normal E2E must not invoke `review_environment.py`, `review_main.py`, Review
  Lab markers, review-only control routes, or `edfinder-review` resources;
- Review Lab must not invoke normal product E2E commands/specs as a substitute
  for its dedicated collector;
- Review Lab must not duplicate normal Explore -> Inspect, keyboard, a11y, or
  visual-baseline acceptance;
- Review Lab may perform only a minimal synthetic wiring proof before exercising
  genuinely Lab-only states;
- Review Lab browser specs must require the trusted handshake and fail closed
  outside Review Lab;
- synthetic API conditions must be owned by guarded Review Lab backend/runtime
  behaviour rather than Cypress response stubs;
- normal E2E specs must not depend on review-only routes or fixtures;
- both lanes use `apps/web` + Babylon when they need the V3 browser surface;
- visual-regression baseline ownership remains exclusively with Product E2E;
- Review Lab visual artifacts remain diagnostic/failure evidence;
- code-quality checks belong in normal CI except focused Review Lab
  containment/lifecycle/contract tests.

Shared helper code is allowed when it reduces duplication, but shared helpers do
not transfer ownership of a scenario.

## Checkpoint operating model

Browser failures are stabilised in one batched pass before a meaningful live
checkpoint. First classify the failed contract:

- normal product behaviour/appearance -> Product E2E / Visual Acceptance;
- deterministic synthetic/failure/fault/containment condition -> Review Lab;
- source/code contract -> normal CI.

A green Review Lab cannot compensate for missing normal V3 E2E/visual
acceptance, and green Product E2E cannot compensate for a broken Review Lab
scenario required by the checkpoint.

For the first meaningful Finder/Inspect/Babylon checkpoint on PR #601:

1. Product E2E owns the real Explore/Finder -> Babylon -> Inspect journey,
   normal interaction/accessibility, resize/remount, and approved visual evidence.
2. Review Lab owns only synthetic fixture wiring plus selected failure/empty and
   renderer fault/recovery scenarios through the same `apps/web` + Babylon stack.
3. Review Lab containment, lifecycle, and teardown remain independent gates.
4. Legacy React/R3F Review Lab assumptions remain removed.

Sharing Cypress does not merge these authorities.
