# V3 Spatial Density Pyramid Decoupling — Design

**Date:** 2026-09-16
**Status:** current implementation design, **not** programme or product authority.
**Supersedes the data-foundation model of:** `docs/development/v3-spatial-density-pyramid-design.md` (#2a). The
pyramid's purpose, cell semantics, reconciliation truth-gate, and map role are
unchanged; only the **generation coupling, lifecycle, and publication** change.
**Target:** `sql/v3/` (new migration), `scripts/` (builder), a governed operator
workflow (build + publish), `apps/api/` (map API).

Authority chain still governs (see `CLAUDE.md`). Where this conflicts with the
roadmap, product contract, spatial-platform architecture, or the ratings-v4
freeze, they win. This document does **not** authorize production deployment or
production DB writes from a coding task: the builder is developed and validated
on fixtures/a bounded subset, and the full-catalogue production build + publish
is a separate owner-dispatched governed step.

## Problem

The merged #2a pyramid (`docs/development/v3-spatial-density-pyramid-design.md`,
PR #735) modelled the density pyramid as a `v3_meta.derived_product` of the
**ratings `derived_generation`**, with `v3_spatial.cell_summary` keyed to
`derived_generation_id` and frozen by that generation's immutability guard.

That coupling has a fatal sequencing trap, hit in production on 2026-09-16: the
ratings derived generation `ratings_v4_prod_p4_parallel_v1` (canonical
`a7076522-54cd-52f3-a291-4e5406bea230`, seq 4, 198,528,286 systems, VERIFIED)
was **published at 08:38Z before any spatial_pyramid product was built**.
Migration `006`'s `v3_meta.guard_derived_product()` forbids inserting *any*
product while the owning generation is not `BUILDING`/`VALIDATING`/`READY`. A
`PUBLISHED` generation is frozen, so the pyramid **can never be attached to
`parallel_v1`**. The design assumed the pyramid would always be built to READY
*before* the ratings generation publishes; once that ordering is lost, the only
recoveries under the old model are an expensive full ratings rebuild or
republishing a superseded generation.

The density pyramid is fundamentally about **where the stars are** — a property
of the canonical star catalogue, not of ratings. Coupling it to the ratings
generation lifecycle is the root cause.

## Goal

Re-model the spatial density pyramid as an **independently-published spatial
artifact keyed to the canonical generation**, with its own lifecycle and
compare-and-swap go-live pointer, decoupled from the ratings `derived_generation`
lifecycle. A pyramid can then be built and published **any time after a canonical
generation is published**, in any order relative to ratings — the timing trap is
removed by construction.

Non-goals (YAGNI): clusters (`v3_spatial.cluster_*`) remain a separate future
product and are untouched; ratings-derived aux counters
(landable/station/biologicals/terraformable) are **not** part of the base
density pyramid (they can become a separate overlay product later); the map
client cross-fade (#2b) is separate downstream work.

## Decisions (from brainstorming, 2026-09-16)

1. **Source of truth: pure canonical density.** The base pyramid's per-cell
   `system_count` comes from the canonical `{gen}.systems` catalogue only. No
   ratings-derived aux counters in the base pyramid. This is exactly the
   "density swirl → real stars" base layer.
2. **Go-live: explicit spatial publish pointer (CAS + audit).** A dedicated
   `v3_spatial.current_spatial_generation` pointer and
   `v3_spatial.publish_spatial_pyramid(actor, reason)` CAS function + audit row,
   mirroring how canonical/derived generations already publish. Build to READY
   (validated), then a **separate** owner-dispatched governed publish flips it
   live; rollback = publish a prior READY spatial generation.
3. **Scope: clean replace, pyramid only.** The new migration replaces the
   derived-keyed `cell_summary` + `spatial_pyramid` derived-product path (empty
   and unused on prod) with canonical-keyed spatial tables + lifecycle +
   publish pointer, and rewires the map API, builder, and governed workflow.
   `v3_spatial.cluster_*` is left untouched and out of scope.

## Architecture

The pyramid is a **spatial generation**: a self-contained, validated,
independently-published artifact built from one canonical generation.

```
v3_meta.canonical_generation (star catalogue, {gen}.systems)
        │  canonical_generation_id
        ▼
v3_spatial.spatial_generation   ── lifecycle: BUILDING→VALIDATING→READY→PUBLISHED→RETIRED / FAILED
        │  spatial_generation_id (+ pyramid_version)
        ├──────────────► v3_spatial.cell_summary   (per-cell density, frozen when spatial_generation is PUBLISHED/RETIRED)
        │                (pyramid_version, level) ──► v3_spatial.cell_level
        ▼
v3_spatial.current_spatial_generation (singleton CAS pointer)
        │  ▲ v3_spatial.publish_spatial_pyramid(...)  + spatial_publication_audit
        ▼
apps/api map: /api/map/heatmap → published spatial pyramid (or legacy fallback)
```

The immutability freeze is keyed to the **spatial** lifecycle, so the ratings
generation's publish state is irrelevant to whether a pyramid can be built.

## Schema — migration `011_v3_spatial_pyramid_decouple.sql`

### Clean replacement of the derived-keyed path

- `DROP TABLE v3_spatial.cell_summary` (derived-keyed; empty/unused on prod).
  Its generation-guard triggers (created by migration `004`'s trigger loop) drop
  with the table.
- Remove the `spatial_pyramid` product from any expected-product logic. No
  `spatial_pyramid` row is ever written to `v3_meta.derived_product` after this
  migration; the pyramid no longer lives in the derived-product model.
- **Keep** `v3_spatial.cell_level` (`PRIMARY KEY(spatial_pyramid_version, level)`)
  — it is version/level-keyed and generation-agnostic; reused unchanged.
- **Do not touch** `v3_spatial.cluster_run` / `cluster` / `cluster_member`.

### `v3_spatial.spatial_generation` (build envelope)

```sql
CREATE TABLE v3_spatial.spatial_generation (
    spatial_generation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_generation_id uuid NOT NULL
        REFERENCES v3_meta.canonical_generation(generation_id),
    pyramid_version text NOT NULL
        CHECK(pyramid_version ~ '^[a-z][a-z0-9_]{0,62}$'),
    lifecycle_state text NOT NULL DEFAULT 'BUILDING'
        CHECK(lifecycle_state IN
              ('BUILDING','VALIDATING','READY','PUBLISHED','RETIRED','FAILED')),
    expected_systems bigint NOT NULL CHECK(expected_systems > 0),
    validation_receipt jsonb
        CHECK(validation_receipt IS NULL OR jsonb_typeof(validation_receipt)='object'),
    validation_sha256 bytea CHECK(validation_sha256 IS NULL OR octet_length(validation_sha256)=32),
    created_at timestamptz NOT NULL DEFAULT now(),
    validated_at timestamptz,
    published_at timestamptz,
    failed_at timestamptz,
    failure text,
    UNIQUE(canonical_generation_id, pyramid_version),
    CHECK(lifecycle_state <> 'READY' OR
          (validation_receipt IS NOT NULL AND validation_sha256 IS NOT NULL
           AND validated_at IS NOT NULL)),
    CHECK((lifecycle_state='FAILED')=(failed_at IS NOT NULL))
);
```

### `v3_spatial.cell_summary` (canonical-keyed, pure density)

```sql
CREATE TABLE v3_spatial.cell_summary (
    spatial_generation_id uuid NOT NULL REFERENCES v3_spatial.spatial_generation,
    spatial_pyramid_version text NOT NULL,
    level smallint NOT NULL,
    cell_key text NOT NULL,               -- deterministic "ix:iy:iz" of floor(coord/size)
    system_count bigint NOT NULL CHECK(system_count > 0),
    representative_system_id64 bigint NOT NULL,  -- system nearest the cell centroid
    origin_x double precision NOT NULL,   -- cell min corner (ly)
    origin_y double precision NOT NULL,
    origin_z double precision NOT NULL,
    centroid_x double precision NOT NULL,
    centroid_y double precision NOT NULL,
    centroid_z double precision NOT NULL,
    PRIMARY KEY(spatial_generation_id, level, cell_key),
    FOREIGN KEY(spatial_pyramid_version, level)
        REFERENCES v3_spatial.cell_level(spatial_pyramid_version, level)
);
CREATE INDEX cell_summary_gen_level
    ON v3_spatial.cell_summary(spatial_generation_id, level);
```

`representative_system_id64` is the density→real-star handoff hook the #2b client
uses when a cell resolves to an individual star on zoom. `cell_key` and cell
geometry are deterministic from the level's size and the cell indices.
`cell_summary.spatial_pyramid_version` holds the same value as its
`spatial_generation.pyramid_version`; it is denormalized on the cell row solely
to satisfy the existing `cell_level(spatial_pyramid_version, level)` foreign key
(migration `004`), which keeps its column name unchanged.

### Pointer, audit, and immutability

```sql
CREATE TABLE v3_spatial.current_spatial_generation (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
    spatial_generation_id uuid NOT NULL REFERENCES v3_spatial.spatial_generation,
    publication_sequence bigint NOT NULL,
    published_at timestamptz NOT NULL
);

CREATE TABLE v3_spatial.spatial_publication_audit (
    publication_sequence bigint PRIMARY KEY,
    previous_spatial_generation_id uuid,
    published_spatial_generation_id uuid NOT NULL,
    canonical_generation_id uuid NOT NULL,
    published_at timestamptz NOT NULL,
    actor text NOT NULL,
    reason text NOT NULL
);
```

- A `v3_spatial.guard_spatial_generation()` trigger enforces valid lifecycle
  transitions and receipt presence (mirroring `guard_derived_product`). Allowed
  transitions: `BUILDING→{VALIDATING,READY,FAILED}`, `VALIDATING→{READY,FAILED}`,
  `READY→{PUBLISHED,RETIRED}`, `PUBLISHED→RETIRED`, `RETIRED→PUBLISHED` (the last
  two enable pointer swap + rollback); any other transition is rejected. READY
  requires a VERIFIED `validation_receipt`+`validation_sha256`+`validated_at`;
  FAILED requires `failure`. Pointer integrity for the PUBLISHED/RETIRED
  transitions is enforced by `publish_spatial_pyramid` under the shared advisory
  lock (the trigger validates the transition shape, the function validates the
  CAS); `published_at` is set only when entering PUBLISHED.
- A `v3_spatial.guard_cell_summary()` statement trigger (INSERT/UPDATE/DELETE/
  TRUNCATE) freezes `cell_summary` rows once the owning `spatial_generation` is
  not in `BUILDING`/`VALIDATING`/`READY` — i.e. cells are insert-only during the
  build and immutable once PUBLISHED/RETIRED/FAILED.
- Both guards take `pg_advisory_xact_lock` on a dedicated spatial key so
  registration/finalization cannot race a pointer swap.

## Build & reconciliation — `scripts/v3_spatial_pyramid.py` (rewritten)

- **`PYRAMID_VERSION`** and **`CELL_LEVELS`** (levels 0–6, 2560→40 ly) retained
  from #2a. `register_cell_levels` unchanged (writes `cell_level`).
- **Source:** the canonical `{gen}.systems` catalogue for the pinned canonical
  generation. `resolve_source` returns the canonical systems relation for that
  generation's schema (no `system_search` dependency).
- **`build_level`:** `SELECT floor(x/size), floor(y/size), floor(z/size),
  COUNT(*) AS system_count, <nearest-centroid system_id64> FROM {gen}.systems
  GROUP BY 1,2,3`. Representative system = the one minimizing distance to the
  cell centroid, deterministic tiebreak `min(system_id64)`. Cell geometry
  derived from level size + indices.
- **`reconcile` (truth-gate):** `Σ system_count` at **every complete level**
  must equal the canonical generation's system count (its
  `expected_systems`/manifest). Missing level, empty level, or Σ mismatch →
  `ReconciliationError`, fail closed, nothing marked READY. No procedural or
  random fill; empty input → no cells (not a synthetic substitute).
- **`build_receipt`:** canonical generation id + sequence, pyramid_version,
  per-level cell counts, reconciliation result, coverage timestamp, source path
  (`canonical-catalogue`), content hash.
- **`mark_pyramid_ready`:** writes the VERIFIED receipt + `validation_sha256`
  and flips the `spatial_generation` `READY` in one transaction. Idempotent: a
  READY spatial generation for `(canonical_generation_id, pyramid_version)`
  short-circuits (`already-ready`).

## Publish — `v3_spatial.publish_spatial_pyramid(...)`

```sql
v3_spatial.publish_spatial_pyramid(
    target_ uuid,                 -- candidate spatial_generation_id
    expected_current_ uuid,       -- current pointer for CAS
    expected_sequence_ bigint,
    expected_canonical_ uuid,     -- must equal the live canonical pointer
    actor_ text, reason_ text
) RETURNS bigint                  -- new publication_sequence
```

CAS contract, mirroring `v3_meta.publish_derived_generation`:

1. Require non-empty `actor_`/`reason_`; take the spatial advisory lock.
2. Read `v3_meta.current_canonical_generation`; fail if it ≠ `expected_canonical_`
   (can't publish a pyramid for a superseded catalogue).
3. Read `current_spatial_generation FOR UPDATE`; fail on CAS mismatch vs
   `expected_current_`/`expected_sequence_`.
4. Load the candidate `spatial_generation FOR UPDATE`; require
   `lifecycle_state IN ('READY','RETIRED')`, `validation_receipt->>'status'='VERIFIED'`,
   and **`canonical_generation_id = ` the live canonical generation**.
5. `sequence := current+1`; retire the previous (`→RETIRED`), set candidate
   `→PUBLISHED, published_at=now()`, upsert the singleton pointer, insert the
   audit row.

**Rollback** = call the function again targeting a prior READY/RETIRED spatial
generation for the current canonical. No cell rewrite is ever needed.

## Governed workflow — build + publish

`.github/workflows/v3-spatial-pyramid.yml` + `scripts/operator/actions/
v3-spatial-pyramid.sh` rewritten:

- Pin the **canonical** generation (id + publication sequence + expected system
  count) instead of a ratings `generation_key`. Update the migration-hash
  preconditions to the new `011` migration (and drop the `006` product-lifecycle
  pin, which no longer governs the pyramid).
- Two governed operations, both manual-only and target-confirmed
  (`ed-finder-prod/nb79a3d.mevnode.com`), fail-closed on host/context/API-slot
  identity as today:
  - **build-to-READY:** resolve the pinned canonical generation, run
    `register_cell_levels → build_all_levels → reconcile → mark_pyramid_ready`
    in one transaction; idempotent short-circuit if already READY.
  - **publish:** call `publish_spatial_pyramid(...)` with the CAS parameters
    read inside the same governed session (owner-supplied actor/reason). Never
    performs canonical writes; never publishes automatically after a build.
- Preserve the trust separation: no push credential in the build environment,
  pinned known-hosts, no runtime `ssh-keyscan`, no broadened allowlist.

Against production **today** this targets the currently published canonical
generation (`a7076522…` seq 4) — no ratings rebuild, no waiting on any ratings
lifecycle.

## API — `apps/api/src/routers/map.py`

- `_current_spatial_pyramid` rewired to
  `current_spatial_generation → spatial_generation (PUBLISHED) → cell_summary`,
  selecting the level by frustum/bounds + target budget as today.
- `/api/map/heatmap` when a spatial pyramid is published:
  `source:"pyramid"`, `generation_id` = the **canonical** generation id,
  `spatial_generation_id`, `pyramid_version`, `source_system_count`, coverage
  timestamp, bounds, returned count, truncation flag; each cell carries
  `system_count`, centroid, and `representative_system_id64`.
- When no spatial pyramid is published → `source:"legacy-fallback"` (existing
  legacy rated-MV/live-aggregate path, clearly labelled), unchanged behaviour.
- This is the stable interface the #2b client consumes.

## Testing & validation

- **Builder unit/contract (fixtures):** deterministic cell output; exact Σ ==
  canonical reconciliation at every complete level; empty input → no cells (no
  procedural substitute); representative-system determinism; cell_key/geometry
  determinism; ban on random/procedural inputs.
- **Reconciliation validator** as a first-class fail-closed gate.
- **Lifecycle/publish (disposable PG18):** guarded state transitions;
  publish CAS (canonical-match gate, READY/VERIFIED gate, pointer swap, audit
  row, rollback); immutability (cannot insert cells into a PUBLISHED spatial
  generation; cannot publish a pyramid whose `canonical_generation_id` ≠ the
  live canonical).
- **API contract:** pyramid path response shape + coverage metadata;
  bounds/level/budget selection; truncation honesty; legacy-fallback labelling.
- **End-to-end subset:** build→validate→publish→API read on a small fixture
  canonical generation.
- Gates for touched surfaces: `make state-check`; backend focused tests;
  migration/script-contract lane. `apps/web` unaffected (client is #2b).

## Boundaries & safety

- Branch → PR; `main` protected; **no production DB writes from this coding
  task**. Full-catalogue production build + publish is the owner-dispatched
  governed workflow only.
- Parameterised SQL; fail-closed validation; follow
  `docs/development/bulk-database-write-safety.md`; disposable/test DBs for tests.
- No secrets in code, arguments, or logs.

## Acceptance criteria

1. `v3_spatial.cell_summary` is keyed to a `spatial_generation` (canonical
   generation) with `Σ system_count` reconciling exactly to the canonical
   system count at every complete level.
2. A pyramid can be built to READY for a canonical generation **regardless of
   any ratings `derived_generation` lifecycle state** (the timing trap is gone).
3. A validation receipt records reconciliation, coverage, and source path
   (`canonical-catalogue`); no rating-weighted or procedural density.
4. `v3_spatial.publish_spatial_pyramid` performs an auditable, reversible CAS
   go-live gated on the candidate matching the live canonical generation.
5. `/api/map/heatmap` serves the published, canonical-pinned pyramid with honest
   coverage metadata, and the labelled legacy fallback when none is published.
6. The derived-keyed `cell_summary`/`spatial_pyramid` product path is removed;
   `cluster_*` untouched. Production build + publish is a separate governed
   owner step (not done in this PR).

## Follow-ups (not this spec)

- Correct `docs/ROADMAP.md` #2a line to reflect the decoupled model and the
  paused-`opt1` / published-`parallel_v1` production reality.
- Optional future: a ratings-derived aux-counter overlay product (landable,
  stations, biologicals, terraformable) as a separate spatial artifact.
