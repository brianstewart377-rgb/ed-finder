# V3 spatial density pyramid (builder + API) — implementation design

> **SUPERSEDED (2026-09-19).** This describes the original **derived-keyed**
> `#2a` model (`v3_spatial.cell_summary` scoped to the ratings
> `derived_generation`). PR #743 replaced it with an **independently-published,
> canonical-keyed** pyramid (own `v3_spatial.spatial_generation` lifecycle + CAS
> publish pointer, migration `012_v3_spatial_pyramid_decouple`). For the current
> design see
> [spatial pyramid decoupling design](../superpowers/specs/2026-09-16-v3-spatial-pyramid-decoupling-design.md)
> and its [plan](../superpowers/plans/2026-09-16-v3-spatial-pyramid-decoupling.md).
> This document is retained as historical/behaviour evidence only.

**Status:** superseded implementation design (see banner above); **not**
programme or product authority.
**Date:** 2026-09-16
**Target:** `apps/api/` (map API), `scripts/` + a governed operator workflow (builder/publish), `sql/v3/` (existing schema).
**Scope:** Piece **#2a** of the density-swirl→real-stars map programme (#2a data foundation → #2b client cross-fade + `adapter.ts` split).

Obeys `CLAUDE.md`, the authority chain, the
[V3 Babylon map delivery plan](v3-babylon-map-delivery-plan.md) M3/M4, and the
[search/spatial/derived-data decision](v3-search-spatial-derived-data-decision.md).
Where it conflicts with those, they win. It does not authorize production
deployment or production DB writes from a coding task; the builder is developed
and validated on fixtures/a subset, and publishing the full pyramid to
production is a separate owner-dispatched governed step.

## Problem (verified)

The galaxy map should show an aggregate density field (a swirl derived from real
system coordinates) at wide zoom, resolving to individual real stars as the
camera closes in. The individual-star lane (`/api/map/systems`) is already
production-real (reads the canonical `{gen}.systems` catalogue by viewport). The
**aggregate density lane is not**: `v3_spatial.cell_summary` (multi-resolution
pyramid schema, migration `004_v3_search_spatial_clusters.sql:58-92`) exists but
has **no builder**, and `/api/map/heatmap` (`apps/api/src/routers/map.py:172`)
currently serves a legacy V2 rated-density MV stopgap (rated systems only; MVs
unpopulated on V3 → falls back to bounded real-star samples). That is neither
the contracted reconciled pyramid nor a truthful full-catalogue density.

## Goals

- Populate `v3_spatial.cell_summary` from the **complete** canonical catalogue as
  a reconciled, generation-scoped, multi-resolution density pyramid.
- **Scope B:** truthfully compute all four aux counters per cell — `landable_count`,
  `station_count`, `biological_system_count`, `terraformable_system_count` — in
  addition to `system_count` + `centroid`.
- Repoint `/api/map/heatmap` at the reconciled pyramid, generation-pinned, with
  honest coverage metadata.

## Non-goals (this piece)

- The client density contribution + zoom cross-fade + `adapter.ts` split (that is **#2b**).
- Clusters (`v3_spatial.cluster_*`) — a separate owned product.
- Any procedural/generated density, and any rating-weighted density (truth gate).

## Truth gate (release-blocking)

- Every occupied cell and every count originates from **real** system records with
  exact `x_ly/y_ly/z_ly`. No spiral equations, noise, textures, or random points.
- At every complete pyramid level, `Σ system_count` **must reconcile exactly** to
  the complete canonical system count for the pinned generation. This reconciliation
  is a hard build gate — and it is what makes the source choice below self-verifying.
- Ratings are neither an input nor a filter to the base density. The four aux
  counters are **physical facts** (bodies/stations/signals), not ratings, so they
  are truth-gate-clean.

## Design

### 1. Source of truth for the aggregation

Investigation (2026-09-16) established:

- Canonical `{gen}.systems` (`sql/v3/migrations/001_v3_baseline.sql:1026-1057`)
  carries `x_ly/y_ly/z_ly` but **no** aux flags — the four aux metrics would need
  joins to `bodies`/`stations`/`body_signal_current` (~1B body rows).
- **`v3_derived.system_search`** (`004:22-46`) already materialises **one row per
  system** (~198M) with `x_ly/y_ly/z_ly` **and** `landable_count`, `station_count`,
  `has_biologicals`, `has_terraformable` as **flat columns** (built by
  `scripts/v3_system_search.py`). `v3_spatial.cell_summary`'s counters map to these
  exactly.

**Decision:** build the pyramid with a **single-pass `GROUP BY` over
`v3_derived.system_search`** for the target derived generation — `SUM(landable_count)`,
`SUM(station_count)`, `COUNT(*) FILTER (WHERE has_biologicals)`,
`COUNT(*) FILTER (WHERE has_terraformable)`, `COUNT(*)` → `system_count`,
`AVG(x/y/z)` → centroid. This makes scope B **cheap** (no billion-row body joins).

**Self-verifying truth gate:** `system_count` must reconcile to the complete
canonical `{gen}.systems` count. If `system_search` is not complete/current for the
target generation, reconciliation **fails closed** and the build stops; the
fallback is to source `system_count`+`centroid` from canonical `systems` directly
(aux counters then via canonical child joins or deferred with a coverage flag).
The **first implementation task** confirms `system_search` build state + completeness
for the target generation, so we know which path runs before building.

### 2. Pyramid levels (`cell_level` registry)

- Register a versioned `spatial_pyramid_version` (e.g. `pyramid_v1`) in
  `v3_spatial.cell_level`: a power-of-two `cell_size_ly` ladder mapped to the
  wide/regional/local semantic scales, each with `intended_scale` and target
  cell-count bounds.
- Propose an initial ladder and **benchmark** the exact sizes/level count on real
  data (the delivery plan forbids freezing cell size by intuition). Level choice at
  query time comes from semantic scale + visible volume + target budget.
- `cell_key` = deterministic text encoding of the integer triple
  `floor(x/size), floor(y/size), floor(z/size)`; `origin_*_ly = key * size`. Bounds
  and origin are stored so readers never re-derive them.

### 3. Builder

- Python, exact CPython 3.14, **Psycopg 3** (sync/importer path per `CLAUDE.md`),
  following `docs/development/bulk-database-write-safety.md`.
- Creates/uses a `v3_meta.derived_generation` row (the pyramid is a derived product
  of the canonical generation; shares the generation envelope with `system_search`).
- Per level: set-based `INSERT INTO v3_spatial.cell_summary (…) SELECT …
  FROM v3_derived.system_search WHERE derived_generation_id = $1 GROUP BY <cell>`.
  `cell_summary` is immutable once written (migration triggers) — build then freeze.
- Resumable/chunked if needed at 198M scale (mirror the `system_search` /
  phase4c import chunking patterns); parameterised SQL only.
- `representative_system_id64` (nullable): a deterministic per-cell pick (e.g.
  min id64) so the client can anchor a cell to a real system.

### 4. Reconciliation + validation receipt

Hard gates, emitting a sanitized receipt (like the migration/deploy receipts):
- `Σ system_count` per complete level == canonical `{gen}.systems` count (exact);
- every cell `system_count > 0` (CHECK) and centroid within cell bounds;
- deterministic output (same source → identical cells); no procedural/random input;
- per-level cell counts within `cell_level` target bounds;
- receipt records: canonical generation, derived generation, pyramid version,
  per-level counts, reconciliation result, coverage timestamp, source-system count,
  timings, and source path taken (`system_search` vs canonical fallback).

### 5. Publication (governed) + rollback

- **Corrected model (2026-09-16, from build investigation):** derived *products*
  (`v3_meta.derived_product`) only have `BUILDING`/`READY`/`FAILED` states and
  never self-publish — like `system_search`, the pyramid builds its product to
  **READY** (storing the validation receipt). `PUBLISHED` and the atomic active
  pointer are **generation-level**: `v3_meta.current_derived_generation`, swapped
  by `v3_meta.publish_derived_generation(actor, reason)`, which is gated on **all**
  products for the generation being READY. So the "active pyramid" is whichever
  belongs to the current published derived generation; there is no per-pyramid
  PUBLISHED state or pointer. `cell_summary` is never mutated in place.
- Runs as a **governed operator workflow** (mirroring `v3-system-search-*` /
  ratings jobs) that builds the pyramid product to READY. Publishing the whole
  generation (the `publish_derived_generation` cutover) is the existing
  owner-dispatched governed step. Builder + validators are developed and proven
  locally on a **fixture and a bounded subset**; the full-catalogue production
  build is an **owner-dispatched governed step** (same posture as the deploy).

#### Owner run sequence (governed build workflow)

The build-to-READY step is `.github/workflows/v3-spatial-pyramid.yml`
(`scripts/operator/actions/v3-spatial-pyramid.sh`), authored and validated
(YAML/shell only) as its own task; it is **not** run against any host as part
of authoring it, and it never runs on push/PR — `workflow_dispatch` only.

1. **Preconditions** (checked by the action script itself, fail-closed): the
   pinned target generation (`ratings_v4_prod_p4_opt1`, same canonical
   generation/sequence the `v3-system-search-*` family pins) must be `READY`,
   and its `system_search` derived product must already be `READY` — the
   builder's canonical-catalogue fallback is deliberately unimplemented
   (`NotImplementedError`), so an incomplete `system_search` is a stop, not a
   silent slow path. Migration `004_v3_search_spatial_clusters.sql` (schema)
   and `006_v3_derived_product_lifecycle.sql` (product lifecycle) are hash-
   verified against both the staged trusted source and the live migration
   ledger before anything runs.
2. **Dispatch.** An owner runs the workflow via `workflow_dispatch` on `main`,
   typing the literal `target_confirmation: ed-finder-prod/nb79a3d.mevnode.com`
   safety input. The job only proceeds for the `main` ref of this repository,
   re-verifies `main` has not moved since dispatch, and executes under the
   `ed-new-operator` GitHub Environment using the `ED_NEW_OPERATOR_*`
   credential boundary and pinned SSH known-host trust (same boundary as
   `chatgpt-ed-new-ops.yml` / `v3-system-search-*`) — no new credential surface.
3. **Build.** Trusted `main` is staged to the host over SSH; the action script
   resolves the pinned generation, runs `register_cell_levels` →
   `resolve_source` → `build_all_levels` → `build_receipt` (which re-runs
   `reconcile`) → `mark_pyramid_ready` inside a single transaction (any
   failure, including a reconciliation mismatch, rolls the whole attempt
   back — no partially-built `cell_summary` rows are left behind). The build
   is idempotent: if the `spatial_pyramid` product is already `READY` for the
   pinned generation, the action short-circuits and reports `already-ready`.
4. **Receipt.** The build's `build_receipt` output (reconciliation result,
   per-level counts, source path, coverage timestamp) is uploaded as the
   `v3-spatial-pyramid-build` workflow artifact, the same way
   `v3-system-search-*` / ratings jobs publish their receipts.
5. **Publish (separate, existing, owner-dispatched step — not this
   workflow).** Building to READY does **not** make the pyramid live. The
   pyramid only becomes the one `/api/map/heatmap` serves once its owning
   derived generation is the current *published* generation — i.e. once an
   owner runs the existing `v3_meta.publish_derived_generation(actor, reason)`
   cutover for that generation (gated on **all** of that generation's derived
   products, including `spatial_pyramid`, being `READY`). This workflow never
   calls `publish_derived_generation` itself and performs no canonical writes.

### 6. API

- Repoint `/api/map/heatmap` off the legacy V2 rated MVs onto `cell_summary` for
  the **active published** spatial generation: select cells by frustum/bounds, level
  chosen from semantic scale + target budget.
- Response carries **generation id, source-system count, coverage timestamp,
  bounds, returned count, truncation** so the client (#2b) can label density
  honestly. This is the stable interface #2b consumes.
- Decide (spec step): remove the legacy MV/live-aggregate path, or retain it behind
  an explicit "no published pyramid yet" fallback flag. Lean: retain as an explicit,
  clearly-labelled fallback until the pyramid is published, then make pyramid the
  default.

## Testing & validation

- **Builder unit/contract tests on fixtures:** deterministic cell output; exact
  reconciliation; empty-data → no cells (no procedural substitute); aux-counter
  correctness (SUM vs COUNT-FILTER semantics); cell_key/origin/bounds determinism;
  ban on random/procedural inputs.
- **Reconciliation validator** as a first-class gate (Σ == canonical count).
- **API contract tests:** generation-pinned response shape + coverage metadata;
  bounds/level/budget selection; truncation honesty; fallback-path labelling.
- **Local subset build** end-to-end (small generation) proving builder→validate→
  publish→API read.
- Gates for touched surfaces: `make state-check`; backend focused tests;
  `apps/web` unaffected in #2a (client is #2b).

## Boundaries & safety

- Branch → PR; `main` protected; **no production DB writes from this coding task**.
  Full-catalogue production build+publish is owner-dispatched governed workflow only.
- Parameterised SQL; fail-closed validation; bulk-write-safety doc; disposable/test
  DBs for tests.
- No secrets in code/args/logs.

## Acceptance criteria

1. `cell_summary` is built for a generation with `Σ system_count` reconciling
   exactly to the canonical system count at every complete level.
2. All four aux counters populated truthfully (scope B) from real facts.
3. A validation receipt records reconciliation, coverage, and the source path.
4. `/api/map/heatmap` serves the reconciled, generation-pinned pyramid with honest
   coverage metadata; no rating-weighted or procedural density in the base layer.
5. Builder/validators pass on fixtures + a bounded subset; production publish is a
   separate governed owner step (not done in this PR).

## Open items / risks

- **`system_search` completeness/current-ness** for the target generation —
  resolved (2026-09-16): `scripts/v3_spatial_pyramid.py:resolve_source(conn,
  derived_generation_id)` compares the `v3_derived.system_search` row count for
  that generation against the canonical `{gen}.systems` count for the same
  generation's pinned `v3_meta.canonical_generation` (joined via
  `derived_generation.canonical_generation_id`, mirroring how
  `apps/api/src/edfinder_api/v3_schema.py` resolves a canonical relation
  schema, but pinned to the named generation rather than "whichever is
  currently published"). Exact equality selects the cheap `system_search`
  source; any mismatch (short build, stale rows, resumed/partial chunking)
  falls back to the canonical catalogue. This is a cheap pre-check only — the
  build's `Σ system_count == canonical count` reconciliation gate (Task 3) is
  the hard, self-verifying enforcement regardless of which source is chosen
  here, so a wrong guess here cannot silently ship an incomplete pyramid.
- **Pyramid level ladder** — resolved as the deterministic starting ladder in
  `scripts/v3_spatial_pyramid.py:CELL_LEVELS`, registered under
  `PYRAMID_VERSION='pyramid_v1'` via the idempotent `register_cell_levels`:
  power-of-two `cell_size_ly` from 2560 LY (whole-galaxy, level 0) down to 40
  LY (local, level 6), each tagged `wide`/`regional`/`local`. These are
  intentionally the initial values only — Task 7 benchmarks per-level cell
  counts against real data and may add/remove levels or resize before the
  ladder is treated as final; `pyramid_v1` stays stable as long as the set of
  `(level, cell_size_ly)` pairs is only extended (new levels, new version) and
  never mutated in place, since `cell_summary` rows key on `(spatial_pyramid_version, level)`.

  **Benchmark (Task 7, 2026-09-16).** Ran the real builder pipeline
  (`register_cell_levels` -> `resolve_source` -> `build_all_levels` ->
  `reconcile` -> `build_receipt` -> `mark_pyramid_ready`, then published the
  fixture generation as current and read it back both via
  `pyramid_for_current_generation` and a live `GET /api/map/heatmap`) against
  a bounded-subset fixture on the disposable test DB: 4,000
  `v3_derived.system_search` rows with real (uniform-random, including
  negative) coordinates over `x in [-9000, 7000]`, `y in [-1200, 1200]` (thin
  disc), `z in [-8000, 8000]` LY -- a ~16,000x16,000x2,400 LY box, chosen to
  span many cells at every registered level on both sides of the origin.
  Reconciliation passed (`Sum(system_count) == 4000` at every level); the
  live heatmap read served `"source": "pyramid"` for the published fixture
  generation. Observed occupied-cell counts:

  | level | cell_size_ly | scale    | occupied cells |
  |------:|-------------:|----------|----------------:|
  | 0     | 2560         | wide     | 111 |
  | 1     | 1280         | wide     | 366 |
  | 2     | 640          | regional | 2,035 |
  | 3     | 320          | regional | 3,634 |
  | 4     | 160          | local    | 3,949 |
  | 5     | 80           | local    | 3,995 |
  | 6     | 40           | local    | 4,000 (== system count; no collisions) |

  The ladder is structurally sane on this fixture: cell counts increase
  monotonically coarse-to-fine, each level partitions the same 4,000 systems
  exactly (the reconciliation gate passing at every level proves this), and
  the finest level (40 LY) resolves to one system per cell at this density --
  i.e. it has room to go finer before hitting the "one star per cell" floor
  on real (much denser) data. Caveat: this fixture's density (4,000 systems
  over ~6.1e8 LY^3, roughly 6.6e-6 systems/LY^3) is far sparser than the real
  ~198M-system canonical catalogue over the actual galactic disc, so these
  counts calibrate the *mechanics* (ladder plumbing, reconciliation,
  publish/read path), not real-world per-level cell/system-per-cell ratios --
  on production data, coarse levels (0-2) will hold far more systems per
  cell (galaxy-disc clustering, spiral arms) and even level 6 will not stay
  1:1. No ladder change is made here; a follow-up production-scale (or a
  denser, disc-shaped synthetic) benchmark is recommended before treating the
  ladder as final, particularly to check whether level 0's 2,560 LY cell size
  (which exceeds `/api/map/heatmap`'s `voxel_size` query cap of 2,000, though
  it remains reachable there as the nearest-match level for `voxel_size`
  near the cap) is ever actually the best "whole galaxy" fit at real scale.
- **Legacy `/api/map/heatmap` MV path** — remove vs. explicit fallback.
- **`cell_key` encoding** — exact text scheme (must satisfy the `^[A-Za-z0-9_.-]{1,64}$` CHECK).
- **Build scale/runtime** at 198M — chunking/resumability, mirroring existing derived builders.

## References

- `sql/v3/migrations/004_v3_search_spatial_clusters.sql` (`cell_level`/`cell_summary`/`system_search`)
- `sql/v3/migrations/001_v3_baseline.sql` (canonical `systems`/`bodies`/`stations`)
- `scripts/v3_system_search.py` (per-system projection builder + aux-field policy)
- `apps/api/src/routers/map.py` (`map_heatmap` @172, `map_systems` @361), `apps/api/src/edfinder_api/v3_schema.py`
- `docs/development/v3-babylon-map-delivery-plan.md` (M3/M4), `docs/development/v3-search-spatial-derived-data-decision.md`
