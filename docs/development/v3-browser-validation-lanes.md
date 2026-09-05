# V3 browser validation lanes

**Status:** current browser authority
**Application under acceptance:** `apps/web/` with the fresh Babylon renderer

## Purpose

ED-Finder has two distinct browser lanes. They answer different questions and
must not be collapsed into one green check:

1. **Product E2E / Visual Acceptance** proves the real V3 user journey and its
   visible, accessible behaviour.
2. **Review Lab** proves that the same V3 application works against a bounded,
   isolated, deterministic review environment.

Both V3 map lanes target `apps/web/` and Babylon. The React/R3F/Three application
and its Playwright/Cypress receipts are historical migration evidence only;
they are not the browser authority for the V3 product.

## Shared invariants

Both lanes must preserve:

- Explore/Finder → Babylon results → canonical Inspect hand-off;
- Finder ownership of query and ranking, with renderer-neutral result inputs;
- selected-system, camera, reference, and layer continuity where applicable;
- bounded and explicitly truncated/empty/error data states;
- search/fly-to, picking, overlap disambiguation, and keyboard/text equivalents;
- an accessible parallel DOM owned by Svelte/SvelteKit;
- reduced-motion behaviour and focus continuity;
- no Babylon types in application/domain contracts;
- no renderer-owned ranking, mechanics, persistence, or planning; and
- deterministic diagnostics sufficient to distinguish product failures from
  environment failures.

## Product E2E / Visual Acceptance

This lane validates the canonical user-facing V3 build and realistic API
contract. It owns release-facing journey, interaction, screenshot, responsive,
accessibility, and supported-browser evidence.

The minimum current journey starts in Explore/Finder, submits a real bounded
query, renders results in fresh Babylon, selects or picks a stable system
identity, and opens the canonical Inspect surface. Future accepted journeys are
added here as their product slices land.

Visual evidence must be deterministic enough for review while retaining
production-shaped layout, fonts, renderer settings, and route behaviour.
Browser/backend capability exclusions must be explicit; a skipped renderer or
browser is not silent acceptance.

## Review Lab

Review Lab is the isolated test-environment lane. It may use synthetic fixtures,
review-only support routes, and a topology or dataset different from Product
E2E, provided those differences are explicit and cannot leak into normal or
production runtime.

Its responsibilities are:

- deterministic fixture coverage for boundary and failure cases that are hard
  to reproduce safely with normal data;
- fail-closed environment setup, target checks, and teardown;
- clear separation of environment readiness from product observations;
- no production credentials, URLs, data, database, or service mutation; and
- sanitized, bounded review artifacts.

The current Review Lab implementation documentation and workflow may still
describe the retained frontend while migration is in progress. That is
implementation evidence to port, not authority to aim the V3 Review Lab at
React/R3F. Equivalent V3 coverage must exist before useful legacy coverage is
retired.

## Data and environment separation

| Concern | Product E2E / Visual Acceptance | Review Lab |
|---|---|---|
| Browser application | `apps/web/` | `apps/web/` |
| Spatial renderer | fresh Babylon | fresh Babylon |
| Primary question | Does the V3 product journey work and look correct? | Is it reproducible and diagnosable in an isolated review environment? |
| Data | production-shaped local/CI contract, bounded | deterministic synthetic fixtures allowed |
| Runtime | release-shaped local/CI build | disposable review topology |
| Evidence | journey, accessibility, browser, visual, rendering | readiness, scenarios, boundaries, sanitized observations |
| Production access | forbidden | forbidden |

## Migration and retirement rule

Existing React, R3F, Three, and Playwright checks may remain temporarily where
they carry unique behaviour or evidence. Label them as migration/historical,
port the durable assertion to the appropriate V3 lane, then retire the old
check deliberately. An old framework-specific test cannot redefine the target
application or make a historical renderer current.

The [pull-request acceptance policy](pull-request-acceptance-policy.md) governs
exact-head merge requirements. The [V3 roadmap](../ROADMAP.md) governs which
product slice comes next.
