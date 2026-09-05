# Colonisation and spatial documentation

## Current authority

Read the [V3 roadmap](../ROADMAP.md) first. This directory has two primary
authority documents:

- [`spatial-platform-product-contract.md`](spatial-platform-product-contract.md)
  — product journey, spatial requirements, truth classes, and feature ownership.
- [`spatial-platform-architecture-decision.md`](spatial-platform-architecture-decision.md)
  — renderer-neutral contracts, runtime boundaries, and fresh Babylon target.

They are part of the small authority chain in the
[root README](../../README.md). They do not independently authorize deployment,
database work, or production operations.

## Supporting audit and evidence

The Stage 27A files below are retained evidence inputs. They describe what was
known at the audit date; they are not the current roadmap or authorization gate:

- [`stage-27a-stage26-inheritance-matrix.md`](stage-27a-stage26-inheritance-matrix.md)
- [`stage-27a-spatial-capability-inventory.md`](stage-27a-spatial-capability-inventory.md)
- [`stage-27a-system-map-data-readiness.md`](stage-27a-system-map-data-readiness.md)
- [`stage-27a-production-data-coverage-queries.sql`](stage-27a-production-data-coverage-queries.sql)

Mechanics-heavy work should also use the committed
[colonisation reference index](../reference/colonisation/README.md). Other files
in this directory are focused design, implementation, or historical evidence;
their old “next” language cannot override the current roadmap.

## Historical stages and map plans

Completed Stage 25 and Stage 26 roadmap/contracts are archived under
[`../archive/stage-25/`](../archive/stage-25/) and
[`../archive/stage-26/`](../archive/stage-26/). The archive preserves the fact
that the equal Stage 26 bakeoff selected R3F and the subsequent cutover
completed on the retired V2 era. React/R3F/Three is migration and behavioural
evidence only for V3; it is not the current renderer authority.

Superseded R3F split, exploration-layer, real-star streaming, glow/thumbnail,
LOD, and narrow Babylon plans live under
[`../archive/superpowers-map/`](../archive/superpowers-map/). See the
[archive policy](../archive/README.md) before using any dated plan.
