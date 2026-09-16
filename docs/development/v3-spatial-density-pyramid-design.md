# V3 spatial density pyramid (builder + API) — implementation design

**Status:** current implementation design, **not** programme or product authority.
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

- Lifecycle `BUILDING → VALIDATING → READY → PUBLISHED` with an atomic active
  spatial-generation pointer (mirroring the derived-product/ratings/search
  publication pattern); rollback to the prior published pyramid; no in-place mutation.
- Runs as a **governed operator workflow** (mirroring `v3-system-search-*` /
  ratings jobs). Builder + validators are developed and proven locally on a
  **fixture and a bounded subset**; the full-catalogue production build+publish is
  an **owner-dispatched governed step** (same posture as the deploy).

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

- **`system_search` completeness/current-ness** for the target generation
  (first task; determines source path — reconciliation gate enforces truth either way).
- **Pyramid level ladder** — propose + benchmark exact sizes/levels.
- **Legacy `/api/map/heatmap` MV path** — remove vs. explicit fallback.
- **`cell_key` encoding** — exact text scheme (must satisfy the `^[A-Za-z0-9_.-]{1,64}$` CHECK).
- **Build scale/runtime** at 198M — chunking/resumability, mirroring existing derived builders.

## References

- `sql/v3/migrations/004_v3_search_spatial_clusters.sql` (`cell_level`/`cell_summary`/`system_search`)
- `sql/v3/migrations/001_v3_baseline.sql` (canonical `systems`/`bodies`/`stations`)
- `scripts/v3_system_search.py` (per-system projection builder + aux-field policy)
- `apps/api/src/routers/map.py` (`map_heatmap` @172, `map_systems` @361), `apps/api/src/edfinder_api/v3_schema.py`
- `docs/development/v3-babylon-map-delivery-plan.md` (M3/M4), `docs/development/v3-search-spatial-derived-data-decision.md`
