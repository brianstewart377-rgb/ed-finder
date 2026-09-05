# Colonisation and Spatial Platform Documents

This directory contains current spatial contracts alongside historical stage
plans, closeouts, audits, and implementation evidence. Start with
[`../ROADMAP.md`](../ROADMAP.md) for current status and authorization.

## Current authority

- [`spatial-platform-product-contract.md`](spatial-platform-product-contract.md)
  defines the current spatial product journey, representation/truth rules, and
  domain ownership boundaries.
- [`spatial-platform-architecture-decision.md`](spatial-platform-architecture-decision.md)
  defines the current renderer-neutral architecture and fresh Babylon direction.
- [`../development/v3-application-stack-decision.md`](../development/v3-application-stack-decision.md)
  amends framework-specific wording for the V3 Svelte/SvelteKit application
  target.
- [`../development/v3-browser-validation-lanes.md`](https://github.com/Alien-alien/ed-finder/blob/12eebac48ca9286e0fd8c180cc5f552dc922d07e/docs/development/v3-browser-validation-lanes.md)
  on the active PR #601 integration lane defines current browser-validation
  lanes and evidence expectations.

The current implementation state and authorization always come from the
[`ROADMAP`](../ROADMAP.md). Status or authorization prose inside older documents
is historical whenever it conflicts with the roadmap or the current authorities
above.

## Supporting Stage 27A evidence

These audits inform current decisions but do not independently authorize work:

- [`stage-27a-stage26-inheritance-matrix.md`](stage-27a-stage26-inheritance-matrix.md)
- [`stage-27a-spatial-capability-inventory.md`](stage-27a-spatial-capability-inventory.md)
- [`stage-27a-system-map-data-readiness.md`](stage-27a-system-map-data-readiness.md)
- [`stage-27a-production-data-coverage-queries.sql`](stage-27a-production-data-coverage-queries.sql)

## Archive and history rule

Stage 25/26 contracts and closeouts, the R3F/Three Stage 26 result, Stage 17–26
plans, superpowers map plans, and other older map proposals are historical
evidence. They remain useful for provenance, parity, and lessons learned, but
they do not define the current target or authorize implementation, production
changes, or operations.

Preserve that history rather than mass-rewriting or moving it. Apply the common
archive rule in [`../archive/README.md`](../archive/README.md): when historical
material conflicts with a current authority, the current authority wins.
