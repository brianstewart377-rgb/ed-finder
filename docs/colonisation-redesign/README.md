# ED-Finder Spatial Platform Documents

This directory contains the current V3 spatial product and architecture
contracts plus historical design and delivery evidence. Start at the repository
[`README.md`](../../README.md), then use [`docs/ROADMAP.md`](../ROADMAP.md) for
current programme order and decision gates.

## Current authority

Normal V3 spatial work should need only this chain:

1. [`../ROADMAP.md`](../ROADMAP.md) — current programme, execution order, and
   unresolved decision gates.
2. [`../development/v3-application-stack-decision.md`](../development/v3-application-stack-decision.md)
   — Svelte/SvelteKit application and fresh Babylon renderer target.
3. [`spatial-platform-product-contract.md`](./spatial-platform-product-contract.md)
   — product journey, features, spatial semantics, and truth requirements.
4. [`spatial-platform-architecture-decision.md`](./spatial-platform-architecture-decision.md)
   — renderer-neutral ownership, contracts, and technical boundaries.
5. [`../development/v3-browser-validation-lanes.md`](../development/v3-browser-validation-lanes.md)
   — separate Product E2E/Visual Acceptance and Review Lab browser authority.
6. [`../operations/infrastructure-status.md`](../operations/infrastructure-status.md)
   — current production and runtime boundary.

The current authorities above always win. Older stage documents in this folder
never authorize current work or override the roadmap, even when their filenames
say “contract”, “roadmap”, “active”, or “production”.

## Supporting evidence

- `stage-27a-stage26-inheritance-matrix.md` records behaviour and test migration
  evidence from Stage 26.
- `stage-27a-spatial-capability-inventory.md` records the earlier capability and
  ownership audit.
- `stage-27a-system-map-data-readiness.md` records body identity, provenance,
  exposure, and coverage findings.
- Stage 25 and 26 documents preserve product-shell, R3F bakeoff, capability,
  accessibility, visual, and cutover history. In particular, R3F won Stage 26;
  that fact is historical evidence, not V3 architecture or production authority.
- [`../reference/colonisation/README.md`](../reference/colonisation/README.md) is
  the committed source-authority entry point for mechanics-heavy research.

See [`../archive/README.md`](../archive/README.md) for the repository-wide rule
for archived and historical documents. This fast authority cleanup does not
physically move the older files; they remain evidence only.
