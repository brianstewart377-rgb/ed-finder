# Review Lab V3 redo — audit + design

**Status:** Phase 1 implemented; runtime/CI verification pending (2026-10-06). Branch `chore/review-lab-v3-redo`.

## Problem

Production (`ed-finder-prod`, PostgreSQL 18) runs **only** the V3 lineage in
`sql/v3/migrations/*` (ordered by `sql/v3/migration-manifest.txt`). The Review
Lab, however, still boots the **legacy V2 schema** and therefore validates a
schema production does not run. Every new V3 surface (watchlist → `v3_private`,
search/map → canonical `v3_gen_*.systems`, Finder → `v3_app.system_search` /
`v3_app.system_archetype`, journal → `v3_private.*`) either 500s in Review Lab
or needs a one-off shim. This is the root cause of the recurring false failures.

## Audit — pre-redo state (historical facts)

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

**Phase 1 is an INTERIM plumbing proof**, not the final Review Lab dataset or
product acceptance. Phase 2 will replace the Cypress source corpus with richer
purpose-built fixtures; it is outside this change.

**Isolation constraint:** allow only `127.0.0.1:55433:5432` for
`review-postgres`, while `review-redis` continues to publish no ports. Host
5432, wildcard/off-host binds, extra ports and external resources remain
forbidden. This supersedes the original proposal to build inside `review-api`:
the production image has no host test/build toolchain and remains unchanged.

1. **Schema**: `bootstrap_schema` already applies the full ordered V3
   prod+Finder lineage (`V3_LINEAGE_FILES`) through psql in `review-postgres`.
   Keep the manifest plus Finder `010/011/013`; do not restore the V2 glob or
   change production migration registration.
2. **Generation**: after bootstrap and before building/starting `review-api`,
   use the host test venv (`sys.executable`) to run
   `scripts/dev/seed_review_v3_generation.py`. Its `DATABASE_URL` targets the
   exact loopback port and `edfinder_local_review`. It reuses the shared review
   database-name constant and disposable-test guard, rejects DSN overrides,
   verifies `current_database()`, then delegates to
   `seed_cypress_v3_generation(connection)`. Search and Archetype reach
   READY/VERIFIED through real builders and the derived generation CAS publish
   gate. Successful re-seeding returns the existing publication sequence.
   Driver/build failures are reported without raw connection strings.
   After derived publication, the review-only `seed_review_spatial_pyramid`
   helper resolves the published canonical generation and builds all seven
   density levels through `scripts/v3_spatial_pyramid.py`. The canonical source
   is capped at 1,000 systems before aggregation. `build_receipt` reconciles
   every registered level, `mark_pyramid_ready` records VERIFIED evidence, and
   `publish_spatial_pyramid` CAS-publishes the candidate against the observed
   empty spatial pointer (`None`, sequence `0`) and pinned canonical id. This
   entire spatial step is one transaction on the autocommit connection; failure
   rolls it back. An existing spatial publication short-circuits the helper.
   `/api/map/heatmap` therefore uses genuine V3 density cells rather than absent
   legacy MVs. The Cypress seed remains unchanged.
3. **Journeys**: require every corpus system (Achenar, HD 38179, V3 Lossless
   Reach) through the normal V3 Finder route, with a V3 source marker. The
   browser wiring and saved-selection assertions use Achenar. Remove the
   normal-mode legacy-search middleware bypass. Preserve the tagged 503,
   contract-shaped empty response/zero-target scene, and renderer
   fault/recovery assertions and containment policy.
4. **Review-only data**: the scenario control is process-local. Retained
   warehouse/provenance support payloads stay bounded in-memory synthetic
   contracts keyed to those three fixture systems; they require no V2
   `app_meta` writes. The unused fourth historical profile is retired.
5. **Cleanup**: retire `review_environment_seed.py`, its compose mount, all
   V2 upserts and the watchlist DDL shim. Migration 014 supplies watchlist
   relations. The API image receives no test dependencies or tooling mounts.
6. **Disposability**: preserve failure codes, bounded subprocesses, baseline
   comparison and teardown, including the workflow's final assertion that no
   Review Lab containers, volumes or networks remain.

TODO(Phase 2): replace the shared Cypress corpus and identity assertions with a
purpose-built Review Lab fixture, retaining the same publication and isolation
gates and each scenario's existing proof obligations.

## Verification
CI `Review Lab` lane: `review_environment.py preflight` then
`verify --mode full --scenario all`. Local: same via `docker compose
-f docker-compose.review.yml`. The lane must go green against the V3 schema with
no weakened assertions.

Phase 1 local evidence (2026-10-06): CPython 3.14.4, `py_compile` and Ruff
(`--target-version py314`) passed on every touched Python file. The focused
Review Lab, timeout, isolation, body-writer and generation-seed tests passed
(85 passed; two PostgreSQL cases skipped without
`RATINGS_V4_VALIDATION_DATABASE_URL`). The browser collector passed Prettier
and ESLint, and `pnpm check` passed with no errors or warnings.
Preflight was attempted but could not reach the Docker Desktop Linux daemon;
no stack/image build, real PostgreSQL publication or full browser verification
was performed. CI green remains unproven until those run.

Spatial seed follow-up (2026-10-06): `py_compile` and Ruff (`--target-version
py314`) passed on all three changed Python files. Focused Review Lab, generation
seed and DB-isolation tests passed (88 passed; two PostgreSQL cases skipped
without `RATINGS_V4_VALIDATION_DATABASE_URL`). Contract coverage checks the
post-derived spatial invocation, CAS argument order, idempotency, bounded source
and fail-closed reconciliation. The full-lineage disposable PostgreSQL case now
also checks published canonical-keyed cells and all seven level sums. Docker
Review Lab and real PostgreSQL verification remain pending in CI.

Maintainer/CI commands from the repository root, after installing the frozen
host test environment and `apps/web` dependencies:

```bash
apps/api/.venv/bin/python scripts/dev/review_environment.py preflight
apps/api/.venv/bin/python scripts/dev/review_environment.py verify --mode full --scenario all --confirm-local-review-environment
# Always run after a failed verification too:
apps/api/.venv/bin/python scripts/dev/review_environment.py down --confirm-local-review-environment
docker ps -a --filter label=com.docker.compose.project=edfinder-review --format '{{.Names}}'
docker volume ls --filter label=com.docker.compose.project=edfinder-review --format '{{.Name}}'
docker network ls --filter label=com.docker.compose.project=edfinder-review --format '{{.Name}}'
```

The last three commands must return no Review Lab resources. To run both
publication regression cases, configure `RATINGS_V4_VALIDATION_DATABASE_URL`
through the environment for a guarded disposable PostgreSQL 18 service whose
role can create/drop disposable test databases, then run:

```bash
apps/api/.venv/bin/python -m pytest tests/test_seed_cypress_v3_generation.py -q
```

Expected journey outcomes: all three systems fit within the default 24-row,
galaxy-wide Finder query, so Achenar reaches the normal result list and Babylon
scene. API failure still comes from tagged review middleware and preserves the
Achenar selection key. Empty mode still bypasses search with the same empty
contract and zero-target scene. Renderer recovery still uses the normal populated
scene and the existing context-loss/restore or remount checks. These are traced
expectations, not a substitute for the pending browser run. The unchanged
60-second seed budget and availability of host port 55433 also require CI proof.

## Sequencing note
This branch builds on the V3 watchlist work in PR #782 (it removes #782's interim
shim). Base/rebase on `main` after #782 merges.
