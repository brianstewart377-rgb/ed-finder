# Review Lab V3 redo — audit + design

**Status:** proposed (2026-10-06). Branch `chore/review-lab-v3-redo`.

## Problem

Production (`ed-finder-prod`, PostgreSQL 18) runs **only** the V3 lineage in
`sql/v3/migrations/*` (ordered by `sql/v3/migration-manifest.txt`). The Review
Lab, however, still boots the **legacy V2 schema** and therefore validates a
schema production does not run. Every new V3 surface (watchlist → `v3_private`,
search/map → canonical `v3_gen_*.systems`, Finder → `v3_app.system_search` /
`v3_app.system_archetype`, journal → `v3_private.*`) either 500s in Review Lab
or needs a one-off shim. This is the root cause of the recurring false failures.

## Audit — current state (facts)

### Schema application
- `scripts/dev/review_lab/lifecycle.py:296-304` (`bootstrap_schema`) applies
  **`/workspace/sql/*.sql` top-level only** (non-recursive), skipping
  `seed_preview.sql`. It **never descends into `sql/v3/`** — no V3 migration is
  ever applied by the bootstrap.
- `sql/` is mounted read-only on **`review-postgres`** only
  (`docker-compose.review.yml:16`). The **`review-api` image does NOT copy
  `sql/`** (`apps/api/Dockerfile` copies only `apps/api/src/` + `shared_contracts/`),
  which is why the interim watchlist shim inlines DDL instead of reading the file.
- `review-postgres` is already `postgres:18-alpine`, so the engine matches prod;
  only the schema is wrong.

### What the app actually needs at request time
- **001** `v3_meta` + `v3_private` + canonical-generation factory
  (`v3_gen_*.systems` with `x_ly/y_ly/z_ly`; `.bodies`), `v3_meta.current_canonical_generation`.
- **003** `v3_derived` + `v3_app`, derived generation, `v3_meta.current_derived_generation`.
- **004 + 010** `v3_app.system_search`. **011** `v3_app.system_archetype[_summary]`.
- **006** `v3_meta.derived_product` lifecycle + `v3_meta.publish_derived_generation` CAS fn.
- **014** `v3_private.watchlist` (+ changelog).
- **005/008/009** journal `v3_private.*` (only if a journey touches journal/identity).
- `current_generation_schema` (`apps/api/src/edfinder_api/v3_schema.py`) resolves
  the live `v3_gen_*` schema; returns `None` when no canonical generation is published.

### Review Lab browser journeys (`scripts/dev/review_lab/scenarios.py`)
Four scenarios — `synthetic_wiring`, `api_failure`, `empty_results`,
`renderer_recovery` — all exercise the **Explore/Finder search surface**
(`/api/local/search` + Babylon), plus `health` and the review-only control route
`/api/review/scenario/{mode}`. **`/api/local/search` requires a PUBLISHED derived
generation with `system_search` + `system_archetype` READY** (enforced in
`local_search.py:611-635`). So the Review DB must have a real published generation,
not just empty tables.

### Proven reuse target
`scripts/dev/seed_cypress_v3_generation.py` already:
1. applies migrations `{001,003,004,006,010,011}` idempotently (probe-then-apply),
2. bootstraps + publishes a canonical generation from the committed fixture
   `tests/fixtures/cypress_v3_sources`,
3. registers + builds `system_search` and `system_archetype` to READY/VERIFIED,
4. publishes the derived generation via the `publish_derived_generation` CAS gate.
It runs **host-side** (needs `scripts/`, `domain/`, `tests/fixtures/`), reading
`sql/v3/migrations/*` from a repo checkout — not from inside the review-api image.

## Design

Make Review Lab boot the V3 schema and seed a minimal published generation by
**reusing the Cypress V3 seeding machinery**, run host-side in the Review Lab CI
job (the runner already has the full checkout + the `apps/api` venv per
`.github/workflows/review-lab.yml`).

> **Isolation constraint (hard):** `review_lab/lifecycle.py:validate_compose_text`
> forbids `review-postgres`/`review-redis` from publishing any host port
> (lines 153-172). This is a deliberate isolation guarantee and must NOT be
> weakened. Therefore the generation build cannot reach the DB from the host —
> it must run **inside the review compose network**.

1. **Schema** — replace the V2 `sql/*.sql` bootstrap loop (`bootstrap_schema`)
   with psql inside `review-postgres` over an explicit **ordered list of the full
   V3 lineage** (manifest + Finder `010/011/013`). The `./sql:/workspace/sql:ro`
   mount is already present, so this is pure psql in the DB container — no app
   code, no host port.
2. **Generation** — reuse the Cypress canonical+derived build/publish machinery
   (`seed_cypress_v3_generation`) run **inside `review-api`** via the existing
   `docker compose run --rm review-api …` path, with the build code
   (`scripts/`, `domain/`, `tests/`, `sql/`) added as **read-only compose mounts**
   so the **prod `apps/api/Dockerfile` image stays untouched** (no test code shipped
   to prod). This gives `/api/local/search` a published generation with
   `system_search` + `system_archetype` READY, over the internal network only.
   Open sub-task: the generation must contain the systems the review journeys
   expect — either convert the Review fixtures into a V3 canonical source, or
   repoint the journeys to the Cypress fixture systems.
3. **Review-only data** — keep the review control route and any review-specific
   fixtures; drop the obsolete V2 table seeding (`systems(x,y,z)`, V2 `ratings`,
   `mv_archetype_rankings`, archetype V2 tables) that no longer matches the app.
4. **Cleanup** — remove the interim `_ensure_v3_watchlist_relations` shim in
   `review_environment_seed.py` (014 now applied by the lineage).
5. **Isolation** — preserve full disposability: loopback-only port, review DSN
   guard, teardown leaving no resources (`review-lab.yml` tail assertions).

### Open decision for the owner
- **Migration breadth:** apply the *Finder-minimal* set `{001,003,004,006,010,011,014}`
  (what the journeys need) vs the *full* prod-faithful set (manifest
  `001,002,r1_v3/001,003,004,005,006,008,009,012,014` **plus** Finder `010,011,013`).
  Minimal is faster and matches the journeys; full is the truest prod mirror and
  future-proofs journal/identity journeys. Recommendation: **full**, since the
  whole point is to stop testing a schema prod doesn't run.

## Verification
CI `Review Lab` lane: `review_environment.py preflight` then
`verify --mode full --scenario all`. Local: same via `docker compose
-f docker-compose.review.yml`. The lane must go green against the V3 schema with
no weakened assertions.

## Sequencing note
This branch builds on the V3 watchlist work in PR #782 (it removes #782's interim
shim). Base/rebase on `main` after #782 merges.
