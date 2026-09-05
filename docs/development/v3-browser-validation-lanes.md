# V3 Browser Validation Lanes

**Decision date:** 2026-09-05  
**Status:** authoritative V3 validation boundary  
**Tracking:** PR #601  

## Purpose

ED-Finder has two separate browser-validation lanes. They may both use Cypress, but they do not have the same responsibility and must not be collapsed into one another.

The two lanes are:

1. **V3 Product E2E / Visual Acceptance** — normal application behaviour and user-visible regression protection.
2. **Review Lab** — an isolated deterministic proving environment for synthetic edge cases and controlled failure/fallback conditions.

Normal code-quality CI is outside both browser lanes.

The fact that Review Lab uses Cypress as a browser driver is an implementation detail. It does **not** make Review Lab the normal E2E or visual-regression lane.

## Fresh Babylon map rule

The V3 map is a **fresh design** in `apps/web/` using **Babylon.js** for the spatial renderer. It is not a visual port of the retained React/R3F map and the old React map is not the visual oracle for the new product.

Retained React behaviour, domain expectations and useful journeys may be consulted as migration evidence, but new Babylon map appearance, interaction, camera behaviour, picking/selection behaviour and spatial presentation are accepted against newly approved V3 contracts and V3 visual baselines.

Both browser-validation lanes must exercise the **same V3 frontend and renderer stack** for any map checkpoint they claim to validate:

- normal Product E2E / Visual Acceptance runs the normal `apps/web` + Babylon product runtime;
- Review Lab runs that same `apps/web` + Babylon frontend against its isolated synthetic backend/data/runtime.

Review Lab may change the **data and environment** to create deterministic scenarios. It must not substitute a different frontend framework or renderer. A React/R3F Review Lab therefore cannot gate a Babylon V3 map checkpoint.

## Lane 1 — V3 Product E2E / Visual Acceptance

### Authority

- Primary application target: `apps/web/`.
- Spatial renderer for the new map: Babylon.js.
- Browser authority: Cypress.
- Workflow: `.github/workflows/cypress-parity.yml` while the migration/branch-protection compatibility naming remains in place.
- Runtime: the normal application/API contract, not `review_main.py` and not review-only routes or fixtures.

### Owns

- normal user journeys;
- navigation, mouse and keyboard interaction;
- Finder, Inspect and later product-surface behaviour;
- Babylon map interaction including stable user-facing camera, picking/selection and spatial presentation contracts;
- accessibility checks that describe normal product behaviour;
- browser console and network failures encountered during normal journeys;
- cross-browser acceptance for the protected browser classes;
- **visual regression and approved screenshot/assertion baselines**;
- checkpoint browser acceptance before a live deployment.

### Does not own

- review-only synthetic routes;
- deliberate review-only API failures/fallbacks;
- disposable Review Lab database/container lifecycle;
- Review Lab containment and teardown proof;
- code linting, formatting, type checking, unit tests or general static analysis.

### Migration rule

The retained `frontend/` Cypress coverage is migration evidence only while equivalent V3 coverage is being established. It must not become the architecture target or regain authority over new V3 product behaviour.

The retained React/R3F map is not a screenshot-baseline source for the fresh Babylon design. V3 map baselines are established from explicitly accepted V3 states after the new design is coherent enough to review.

The `apps/web/` suite now includes Chrome/Firefox coverage of the explicitly non-product Babylon foundation: canvas readiness, bounded backend status, resize, navigation/remount stability, uncaught-failure protection, and a deterministic diagnostic screenshot retained as evidence only. This remains foundation/smoke coverage, not an approved product visual baseline. Before the first meaningful Finder/Inspect/map live checkpoint it must grow into real product E2E and visual acceptance, including meaningful screenshots/assertions for stable user-visible Babylon states.

## Lane 2 — Review Lab

### Authority

- Workflow: `.github/workflows/review-lab.yml`.
- Wrapper authority: `scripts/dev/review_environment.py` and `scripts/dev/review_lab/`.
- Runtime: isolated `edfinder-review` resources, the dedicated review database, synthetic fixtures and review-only API handling.
- Frontend/renderer for V3 map scenarios: the same `apps/web/` + Babylon implementation used by the normal product lane.
- Cypress may be invoked by the Review Lab browser runner as its controlled browser driver/collector.

### Owns

- deterministic synthetic scenarios that cannot be reliably produced in the normal product lane;
- review-only fallback/error/posture cases;
- controlled large/partial/optional data states;
- review-only route-contract behaviour;
- deterministic Babylon map scenarios driven by synthetic Review Lab data where normal product data cannot guarantee the required state;
- containment of review credentials/data/resources;
- disposable stack lifecycle and teardown;
- Docker/process baseline restoration;
- environment-readiness and product-observation reporting for the selected synthetic scenarios;
- failure screenshots/videos and sanitised browser evidence for diagnosing a Review Lab run.

### Does not own

- the normal product E2E suite;
- normal visual-regression baselines;
- a separate React/R3F rendering path for V3 acceptance;
- generic application smoke tests as a substitute for the product E2E lane;
- normal lint/format/type/unit/security/code-review responsibilities;
- production or live-checkpoint data;
- public/external data acquisition.

**Review Lab screenshots are diagnostic evidence, not approved product visual baselines.** Approved visual baselines belong only to the V3 Product E2E / Visual Acceptance lane.

## Normal CI — outside both browser lanes

Normal CI/Codex review owns implementation correctness that does not require a real browser journey, including:

- lint and formatting;
- type and compile checks;
- unit/component tests;
- API/backend tests;
- migration/script contracts;
- security/static analysis;
- repository and architecture guardrails.

A browser workflow must not become a dumping ground for these checks merely because it is required by branch protection.

Review Lab may run focused tests of **Review Lab infrastructure itself** when needed to prove containment, lifecycle or its own contracts. That exception does not make Review Lab a general code-quality lane.

## Routing rule for every new test

Use this decision order:

1. **Does the check require a synthetic review-only state, review-only route, deliberate failure/fallback, or Review Lab lifecycle/containment?**  
   Put it in **Review Lab**.
2. **Can the check run against the normal V3 application and does it describe what a user sees or does?**  
   Put it in **V3 Product E2E / Visual Acceptance**.
3. **Does it primarily validate source code, contracts, formatting, types, units, scripts or security without requiring a browser journey?**  
   Put it in **normal CI**.

When a check could fit more than one lane, prefer the narrowest owner and do not duplicate the same acceptance contract across lanes.

## Hard non-overlap rules

These rules are test-enforced:

- the normal E2E workflow must not invoke `review_environment.py`, set the Review Lab browser marker, boot `review_main.py`, or depend on `edfinder-review` resources;
- Review Lab must not invoke the normal product E2E command or normal release-gate product specs as a substitute for its dedicated collector;
- Review Lab browser specs must require the trusted Review Lab handshake and must fail closed outside Review Lab;
- normal E2E specs must not depend on review-only routes or synthetic Review Lab fixtures;
- for every V3 map checkpoint, both lanes must render through `apps/web` + Babylon; Review Lab may vary data/environment, not frontend/renderer technology;
- visual-regression baseline ownership remains exclusively with normal V3 Product E2E;
- Review Lab visual artifacts remain diagnostic/failure evidence;
- code-quality checks belong in normal CI, except focused tests of Review Lab's own containment/lifecycle contracts.

Shared helper code is allowed when it reduces duplication, but shared helpers do not transfer ownership of a scenario from one lane to the other.

## Checkpoint operating model

Browser failures are stabilised in **one batched pass before a meaningful live checkpoint**, not by opening a microscopic repair cycle for every selector, keyboard timing issue or telemetry interaction.

For each failure, first ask which contract failed:

- normal product behaviour/appearance -> Product E2E / Visual Acceptance;
- deterministic synthetic edge case or Lab containment -> Review Lab;
- source/code contract -> normal CI.

A green Review Lab cannot compensate for missing normal V3 E2E/visual acceptance, and a green normal E2E run cannot compensate for a broken Review Lab scenario required by the checkpoint.

For the fresh Babylon map, a checkpoint cannot claim Review Lab coverage unless the Lab is running the actual V3 Babylon renderer. Passing synthetic scenarios through the old React/R3F frontend is legacy evidence only.

## Current migration state and required re-base

As of PR #601:

- normal Cypress E2E already exercises both retained React migration evidence and the new `apps/web/` foundation;
- `apps/web/` coverage now proves the isolated Babylon runtime lifecycle in Chrome and Firefox, but remains smoke/foundation-level and does not yet provide Finder/Inspect/product-map visual acceptance;
- the new V3 map is being designed fresh around Babylon rather than copied visually from the retained React/R3F map;
- Review Lab is structurally separate, but its browser collector is still wired to the retained `frontend/` React application and old Planner-heavy scenario matrix;
- the Review Lab workflow still carries some general resolver/project-state/stage checks and a formatting check from its history as a broad required gate. Those checks are also migration debt: they must move to normal CI where appropriate, leaving only tests that directly prove Review Lab containment/lifecycle/contracts.

Those last two points are **migration debt, not the target design**. Until Review Lab is retargeted to `apps/web/` and uses the Babylon renderer for V3 map scenarios, a green Review Lab run proves the isolated legacy review environment only and must not be treated as V3 live-checkpoint browser acceptance. The existing generic checks must not be used as precedent for adding more code-review responsibility to Review Lab.

The non-product foundation screenshot is a run artifact for executable-renderer evidence only. It is not a V3 map visual baseline, makes no map design decision, and does not reduce the later Finder/Inspect or Review Lab re-base requirements.

Before the first meaningful Finder/Inspect/Babylon live checkpoint, PR #601 must:

1. make `apps/web/` + Babylon the normal product E2E/visual authority for the checkpoint journeys;
2. add meaningful Finder -> map/results -> Inspect user journeys and newly approved V3 visual assertions;
3. retarget the Review Lab browser collector to that same `apps/web/` + Babylon frontend for the synthetic Finder/Inspect/map scenarios relevant to the checkpoint;
4. move general code-quality/project-state checks out of Review Lab unless they directly prove Review Lab containment/lifecycle/contracts;
5. keep Review Lab synthetic data/routes/lifecycle separate from normal E2E;
6. remove or explicitly archive legacy React/R3F Review Lab assumptions once equivalent V3 coverage is accepted;
7. run one batched stabilisation pass across the two browser lanes before promotion.

A lane re-base is complete only when **both** browser workflows target their intended V3 responsibilities independently: normal Product E2E/Visual Acceptance proves ordinary `apps/web` + Babylon user behaviour and pixels, while Review Lab proves selected synthetic scenarios through that same `apps/web` + Babylon stack inside its isolated environment. Sharing Cypress does not merge those authorities.

## Live checkpoint terminology

Contabo is the **live-checkpoint environment**, not the production server. The deployment mechanism exercised against it should be production-grade and immutable, but Review Lab, normal CI and normal E2E must not use Contabo as their test environment.
