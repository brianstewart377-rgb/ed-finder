# Review Lab V3 redo — audit + design

**Status:** Phase 2 steps 1-3 are implemented (#787, #789, and this PR), and Review Lab now uses `tests/fixtures/review_lab_v3_sources`.

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
- `review-postgres` is already
  `public.ecr.aws/docker/library/postgres:18-alpine`, so the engine matches prod;
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

## Phase 2 design

**Design base:** this design was written from actual `origin/main`
`0ddd4d10ab3aa38a3c2e01cdb0c2928e6c7172cf` on 2026-10-08. That is the expected
#785 workflow-only revert on top of the Phase 1 merge, so the conditional
post-`fe033a2` stop did not apply.

In this section, a **fixture** is a small committed test dataset. An **id64** is
Elite's 64-bit system identifier. **CAS** means compare-and-swap: publication
succeeds only if the current pointer still has the identity and sequence the
publisher observed, preventing a concurrent publication from being silently
overwritten. A **spatial pyramid** is the same system data aggregated at several
cell sizes for different map zoom levels; the current Review seed registers and
builds every configured level before publication
(`scripts/dev/seed_review_v3_generation.py:83-105`).

### Current coupling inventory

The following is the complete Review Lab coupling found by tracing the requested
files and then searching Review Lab-owned scripts, API modules, browser code,
tests, fixtures and workflows.

| Place | Current coupling to the Cypress corpus |
|---|---|
| Scenario registry | `synthetic_wiring` names all three Cypress systems and Achenar in its journey; `renderer_recovery` says it uses the interim Cypress systems (`scripts/dev/review_lab/scenarios.py:6-15`, `scripts/dev/review_lab/scenarios.py:42-50`). |
| Review seed entry point | The Review seed describes itself as an interim Cypress proof, imports `seed_cypress_v3_generation`, calls it before the spatial build and prints an interim result (`scripts/dev/seed_review_v3_generation.py:1-6`, `scripts/dev/seed_review_v3_generation.py:18-20`, `scripts/dev/seed_review_v3_generation.py:108-125`). This is the only runtime edge from Review Lab into the Cypress publisher. |
| Cypress publisher | Its default source is `tests/fixtures/cypress_v3_sources`; it loads that source, bootstraps canonical data, builds and verifies `system_search` and `system_archetype`, then CAS-publishes the derived generation (`scripts/dev/seed_cypress_v3_generation.py:36-36`, `scripts/dev/seed_cypress_v3_generation.py:84-133`). Corpus size and bodies also determine chunk input and validation receipt counts (`scripts/dev/seed_cypress_v3_generation.py:65-68`, `scripts/dev/seed_cypress_v3_generation.py:101-123`). |
| Cypress fixture builder and artifacts | The builder selects source systems, rewrites Sol to Achenar `10477373803000`, rewrites Alioth to V3 Lossless Reach `9007199254740993`, and retains HD 38179 `158872029` (`scripts/dev/build_cypress_v3_fixture.py:33-48`). It filters and rewrites systems, bodies, extra relations and raw source members (`scripts/dev/build_cypress_v3_fixture.py:79-135`), then writes `canonical.json`, `source-metadata.json`, `spansh-system-dumps.zip` and a checksum manifest under the Cypress directory (`scripts/dev/build_cypress_v3_fixture.py:152-181`). Those four committed artifacts are therefore the data Review Lab currently publishes indirectly. |
| Review API identity data | `REVIEW_SYSTEMS`, the fallback id64, all warehouse contracts and all provenance contracts are keyed to the three Cypress identities; their human-readable messages repeat those names (`apps/api/src/review_environment_fixtures.py:5-13`, `apps/api/src/review_environment_fixtures.py:51-225`, `apps/api/src/review_environment_fixtures.py:229-389`). |
| Review API consumers | The in-memory contract store looks up the identity-keyed warehouse and provenance payloads by id64 (`apps/api/src/review_contract_store.py:5-29`). The dedicated warehouse route special-cases the lossless id64 and names V3 Lossless Reach in its synthetic 503 response (`apps/api/src/review_warehouse_planner_evidence.py:23-43`). `review_main.py` includes those Review-only routers while normal search reaches the genuinely published V3 generation (`apps/api/src/review_main.py:18-21`, `apps/api/src/review_main.py:159-161`, `apps/api/src/review_main.py:206-216`). |
| Review contract and preflight | The Review contract re-exports the required names from the API fixture module (`scripts/dev/review_lab/contract.py:10-12`). The Finder API check requires every configured name in a V3-sourced response (`scripts/dev/review_lab/api_contracts.py:23-56`), and preflight reports the same names (`scripts/dev/review_lab/lifecycle.py:428-449`). |
| Browser collector | It hardcodes Achenar and its Cypress id64 as the selected Review system (`apps/web/cypress/e2e/review-lab.cy.ts:32-35`), requires that pair in the normal Finder result (`apps/web/cypress/e2e/review-lab.cy.ts:186-205`), and uses the same id64 for the API-failure selection-preservation assertion (`apps/web/cypress/e2e/review-lab.cy.ts:209-235`). Renderer recovery loads the normal seeded scene, so it depends indirectly on the corpus being nonempty (`apps/web/cypress/e2e/review-lab.cy.ts:264-335`). |
| Review Lab unit/contract tests | The fixture test reads the Cypress canonical file directly and requires API identities, bodies, support contracts and the browser constant to match the entire three-system corpus (`tests/test_review_lab_v3.py:177-187`). Other tests monkeypatch the imported Cypress publisher (`tests/test_review_lab_v3.py:218-257`), require every configured identity in Finder (`tests/test_review_lab_v3.py:526-535`), require support contracts for every identity (`tests/test_review_lab_v3.py:570-581`), and embed the current count of three in spatial assertions (`tests/test_review_lab_v3.py:262-340`). |
| Shared PostgreSQL regression | The Cypress seed regression requires the three exact identities and count, READY/VERIFIED derived products, a three-system spatial publication, per-level sums of three, valid representatives and idempotent second publication (`tests/test_seed_cypress_v3_generation.py:39-123`). This currently doubles as Review spatial evidence and must be split so Cypress and Review fixtures have separate ownership. |
| Cypress-owned lane that must remain unchanged | Product E2E invokes `seed_cypress_v3_generation.py` directly (`.github/workflows/cypress-parity.yml:125-138`), while its own fixture tests deliberately assert Achenar, the lossless id64, exact coordinates and body inventory (`tests/test_cypress_v3_fixture.py:14-51`). Those are Product E2E obligations, not Phase 2 files to repurpose. |

Repository-wide search also finds the three names/id64s in Product E2E, Ratings
V4 fixtures/tests, the preview SQL seed, generic bigint tests and historical
documents. None is a Review Lab dependency. Phase 2 must not change those
surfaces merely to remove Review Lab coupling; the browser-lane authority keeps
normal product journeys and lossless product acceptance in Product E2E
(`docs/development/v3-browser-validation-lanes.md:31-60`,
`docs/development/v3-browser-validation-lanes.md:90-119`).

### Proof obligations and minimum fixture data

The API phase always checks health. It checks Finder only for scenarios that
declare `finder`, and checks the guarded control route for scenarios that
declare `review_control` (`scripts/dev/review_lab/api_contracts.py:10-74`,
`scripts/dev/review_lab/scenarios.py:8-50`). The browser evaluator separately
requires the named check flags for each flow
(`scripts/dev/review_lab/browser_runner.py:28-58`).

| Scenario | What it proves today | Minimum fixture data after decoupling |
|---|---|---|
| health | `GET /api/health` must return HTTP 200 and a JSON object (`scripts/dev/review_lab/api_contracts.py:14-21`). The live handler probes the database with `SELECT 1` and reports a connected result (`apps/api/src/routers/meta.py:40-70`). | No system, body, name or id64 row. It needs only the isolated API and database connection. **Unverified:** the Review evaluator does not assert the response's `status` or `database` fields; it asserts only 200 plus object shape. |
| `synthetic_wiring` | Normal mode must use the real V3 Finder, return 200, expose the configured system in the real Svelte result list, and reach Babylon's ready state (`scripts/dev/review_lab/scenarios.py:8-18`, `apps/web/cypress/e2e/review-lab.cy.ts:186-205`). Today the API phase additionally requires all three configured names and a `v3:` source (`scripts/dev/review_lab/api_contracts.py:23-56`). | One dedicated system returned by the default 24-row query, with a stable name/id64, finite `x/y/z`, at least one matching body and a matching raw source member so the real canonical, Ratings, Search and Archetype validators can pass (`scripts/dev/seed_cypress_v3_generation.py:94-128`). The proposed fixture has three systems, but the proof itself needs only this one anchor. **Unverified:** the current browser check does not assert that this result becomes a nonzero Babylon scene target. |
| `api_failure` | The guarded backend, not Cypress, returns a tagged 503; Explore shows the bounded error; the saved selection id64 is unchanged (`scripts/dev/review_lab/scenarios.py:19-29`, `apps/api/src/review_main.py:136-148`, `apps/web/cypress/e2e/review-lab.cy.ts:209-238`). Only a 503 with the exact review header is treated as expected (`apps/web/cypress/e2e/review-lab.cy.ts:118-130`). | No canonical row is read because middleware intercepts search. One stable fixture-owned id64 token is sufficient for the persistence assertion. **Unverified:** the current browser check proves exact string preservation, not that the stored id64 resolves to a fixture system. |
| `empty_results` | The guarded backend returns the contract-shaped empty response; Explore shows the empty state; Babylon is ready with zero scene targets (`apps/api/src/review_main.py:149-158`, `apps/web/cypress/e2e/review-lab.cy.ts:240-262`). | No scenario-specific row is read. The overall seed still needs at least one system because spatial seeding rejects an empty canonical source (`scripts/dev/seed_review_v3_generation.py:74-81`). |
| `renderer_recovery` | Normal mode loads Babylon, attempts WebGL context loss/restore when supported, otherwise remounts by reload, and must finish ready, usable and without an uncaught page error (`scripts/dev/review_lab/scenarios.py:41-51`, `apps/web/cypress/e2e/review-lab.cy.ts:264-335`). Its declared Finder contract currently also requires every configured name (`scripts/dev/review_lab/scenarios.py:46-47`, `scripts/dev/review_lab/api_contracts.py:23-56`). | One default-query-visible, pipeline-valid system is sufficient to create a populated normal scene; it needs the same coordinates/body/raw-source consistency as `synthetic_wiring`. **Unverified:** the current flow neither waits for search nor asserts a positive scene-target count. **Unverified:** if `WEBGL_lose_context` is unavailable, reload is accepted as lifecycle coverage, so actual context loss is not guaranteed. |

Every browser flow also records external resource origins, and the collector
requires that set to remain empty (`apps/web/cypress/e2e/review-lab.cy.ts:84-99`,
`apps/web/cypress/e2e/review-lab.cy.ts:338-344`). Unexpected console/page errors
and untagged failing API calls remain failures
(`scripts/dev/review_lab/network_policy.py:6-61`).

### Proposed fixture and publisher boundary

Create `tests/fixtures/review_lab_v3_sources/` containing the same four formats
the proven loader already consumes: `canonical.json`, `source-metadata.json`,
`spansh-system-dumps.zip` and checksum-locking `manifest.json`. Add
`scripts/dev/build_review_lab_v3_fixture.py`, mirroring the deterministic
subset/rewrite, filtered-relation, fixed-zip-timestamp and checksum pattern in
the Cypress builder (`scripts/dev/build_cypress_v3_fixture.py:50-68`,
`scripts/dev/build_cypress_v3_fixture.py:79-168`). Build from the pipeline-valid
`tests/fixtures/ratings_v4_sources` template, never from
`tests/fixtures/cypress_v3_sources`; commit the output so CI reads it rather
than fetching or generating external data. The current pattern already proves
why canonical bodies and raw source inventories must be kept consistent
(`scripts/dev/build_cypress_v3_fixture.py:90-135`,
`tests/test_cypress_v3_fixture.py:40-51`).

Use exactly three fictional, Review-Lab-only systems:

1. **Review Wiring** is the browser anchor. It has a fixed positive id64, finite
   coordinates, a retained main-star body and enough matching source/body data
   for the real derived builders.
2. **Review Aggregate** has distinct nearby coordinates chosen to share some
   coarse pyramid cells with Review Wiring and split at finer levels. This makes
   seven-level reconciliation exercise aggregation rather than mere table
   existence.
3. **Review Fallback** is spatially separated and owns the existing synthetic
   unavailable/not-evaluated support-route case, replacing the lossless-system
   special case.

Three remains tiny enough for the permitted minimal wiring proof, fits the
current size-24 Finder request, preserves the available/unavailable/not-evaluated
in-memory support profiles, and gives the spatial pyramid non-degenerate input
without importing a normal product journey. The current request size is 24
(`scripts/dev/review_lab/api_contracts.py:23-33`), the three support profiles are
encoded separately today (`apps/api/src/review_environment_fixtures.py:51-225`),
and the lane contract limits Review Lab to minimal wiring plus synthetic states
(`docs/development/v3-browser-validation-lanes.md:62-88`). No old Cypress name,
id64 or coordinate is retained. A JavaScript-unsafe id64 is not required here
because that product-acceptance case remains Cypress-owned
(`tests/test_cypress_v3_fixture.py:16-37`).

Extract the generic publication body from
`scripts/dev/seed_cypress_v3_generation.py` into
`scripts/dev/seed_v3_fixture_generation.py`. It takes an explicit fixture path,
generation-key prefix, publication actor and publication note. Keep
`seed_cypress_v3_generation` as the Product E2E compatibility wrapper and make
`seed_review_v3_generation.py` call the neutral helper with only the dedicated
Review path and Review metadata. This preserves the current canonical bootstrap,
real Search/Archetype builders, VERIFIED receipts and derived CAS arguments
(`scripts/dev/seed_cypress_v3_generation.py:84-133`) while removing imports of
the Cypress wrapper and reads of the Cypress directory from Review-owned code.
A change confined to `tests/fixtures/cypress_v3_sources` can then affect Product
E2E but cannot alter Review Lab inputs.

After the derived generation publishes, keep the spatial step unchanged. It
resolves the published canonical schema, counts through `LIMIT 1001`, rejects
zero or more than 1,000 systems, builds every registered level, reconciles the
receipt, marks READY and CAS-publishes against the observed empty pointer and
pinned canonical id in one transaction
(`scripts/dev/seed_review_v3_generation.py:52-105`). The three-system fixture is
therefore inside the existing cap; the cap is a safety ceiling, not a target
size.

### Gates that must not weaken

| Gate | Phase 2 preservation rule |
|---|---|
| PostgreSQL loopback only | Do not change Compose. The sole host database mapping stays `127.0.0.1:55433:5432` (`docker-compose.review.yml:9-11`). The parser must continue rejecting external resources, wildcard/5432/6379 bindings, any alternate PostgreSQL tuple and host ports on other services (`scripts/dev/review_lab/lifecycle.py:144-187`; `tests/test_review_lab_v3.py:412-455`). |
| No Review Redis port | `review-redis` continues to have no `ports` entry (`docker-compose.review.yml:23-34`), enforced by lifecycle validation and its regression test (`scripts/dev/review_lab/lifecycle.py:181-187`; `tests/test_review_lab_v3.py:452-455`). |
| No DSN overrides | Lifecycle continues to supply only the pinned Review DSN (`scripts/dev/review_lab/lifecycle.py:346-355`). The seed continues accepting only an exact PostgreSQL URI for `127.0.0.1:55433/edfinder_local_review` with no query or fragment, which blocks `hostaddr`, `service` and `dbname` overrides (`scripts/dev/seed_review_v3_generation.py:23-49`; `tests/test_review_lab_v3.py:190-215`). |
| Connected database identity | Keep `SELECT current_database()` before any publisher call and reject any value other than `edfinder_local_review` (`scripts/dev/seed_review_v3_generation.py:108-118`; `tests/test_review_lab_v3.py:218-259`). |
| Derived CAS publication | The neutral helper must preserve validation of the Ratings generation plus Search and Archetype as VERIFIED, then call `v3_meta.publish_derived_generation` with expected prior pointer `(None, 0)` and the pinned canonical id/sequence (`scripts/dev/seed_cypress_v3_generation.py:111-133`). No direct pointer update or lifecycle shortcut is allowed. |
| Spatial CAS publication | Keep the single transaction, published-canonical validation, level reconciliation, READY transition and `publish_spatial_pyramid` call with expected `(None, 0)` plus pinned canonical id (`scripts/dev/seed_review_v3_generation.py:52-105`). Existing tests already prove ordering, rollback, argument order, idempotent short-circuit and source bounds (`tests/test_review_lab_v3.py:262-377`). |
| Idempotent re-seed | Preserve migration probe-before-apply and the early return of an existing derived publication sequence (`scripts/dev/seed_cypress_v3_generation.py:71-92`), plus the early return of an existing spatial sequence (`scripts/dev/seed_review_v3_generation.py:60-64`). The dedicated Review PostgreSQL regression must call both a second time and prove no second generation or audit row, matching current evidence (`tests/test_seed_cypress_v3_generation.py:118-122`). |
| 60-second seed budget | Keep `TIMEOUTS.stack_readiness` at exactly 60 seconds and continue using it for the host seed (`scripts/dev/review_lab/timeouts.py:6-16`, `scripts/dev/review_lab/lifecycle.py:346-355`). Tighten the current loose `<= 120` assertion to exact equality (`tests/test_review_lab_v3.py:482-490`). |
| Complete teardown | Keep `docker compose down -v --remove-orphans` with the 60-second teardown budget (`scripts/dev/review_lab/lifecycle.py:490-496`). Verification must always stop owned processes, compare the non-Review Docker baseline, and reject any Review container, volume or network (`scripts/dev/review_environment.py:225-287`). The workflow's independent always-run teardown and label-filtered zero-resource checks remain unchanged (`.github/workflows/review-lab.yml:90-114`). |

### Implementation plan

Each PR must satisfy every branch-protected check and both exact-head reviewers,
not only the checks named below
(`docs/development/pull-request-acceptance-policy.md:3-45`). **Unverified:** the
exact remote branch-protection context list is not stored in this checkout. The
repository does establish Review Lab as required and says required checks come
from branch protection/current workflows (`CLAUDE.md:181-200`).

1. **Add the independent fixture without selecting it at runtime.** Touch only
   `scripts/dev/build_review_lab_v3_fixture.py`,
   `tests/fixtures/review_lab_v3_sources/canonical.json`,
   `tests/fixtures/review_lab_v3_sources/source-metadata.json`,
   `tests/fixtures/review_lab_v3_sources/spansh-system-dumps.zip`,
   `tests/fixtures/review_lab_v3_sources/manifest.json`, and
   `tests/test_review_lab_v3.py`. Add tests that rebuild to a temporary directory
   and byte-compare all four artifacts, load the committed fixture through the
   real source loader, require exactly three unique systems with matching
   canonical/raw body inventories and finite coordinates, and reject all three
   old names/id64s. `Backend unit tests + compose validate` supplies Ruff and
   non-DB unit coverage (`.github/workflows/ci.yml:33-70`); `Review Lab` runs the
   changed focused test directly (`.github/workflows/review-lab.yml:69-75`).

2. **Extract the corpus-neutral publisher while retaining the Cypress wrapper.**
   Touch only `scripts/dev/seed_v3_fixture_generation.py`,
   `scripts/dev/seed_cypress_v3_generation.py`,
   `tests/test_seed_cypress_v3_generation.py`, and
   `tests/test_review_lab_v3.py`. Add unit assertions for explicit fixture path
   and publication metadata, unchanged migration/validation/CAS ordering and
   unchanged idempotency; keep the disposable PostgreSQL regression proving the
   Cypress wrapper still publishes its three product-journey systems and READY/
   VERIFIED products (`tests/test_seed_cypress_v3_generation.py:39-84`). CI proof
   is `Backend unit tests + compose validate`, required `Review Lab`, and Svelte
   Web E2E, whose workflow calls that compatibility wrapper directly
   (`.github/workflows/cypress-parity.yml:125-138`).

3. **Cut Review Lab over atomically and remove old identity coupling.** Touch
   only `scripts/dev/seed_review_v3_generation.py`,
   `scripts/dev/review_lab/scenarios.py`,
   `apps/api/src/review_environment_fixtures.py`,
   `apps/api/src/review_warehouse_planner_evidence.py`,
   `apps/web/cypress/e2e/review-lab.cy.ts`,
   `tests/test_review_lab_v3.py`,
   `tests/test_seed_cypress_v3_generation.py`, and new
   `tests/test_seed_review_v3_generation.py`. Switch the Review seed to the
   neutral helper and dedicated path; replace every API/browser/scenario identity;
   move Review-specific full-lineage, spatial reconciliation and second-seed
   assertions out of the Cypress test into the new Review seed test; and add a
   scan of Review-owned paths that rejects `cypress_v3_sources`,
   `seed_cypress_v3_generation` and all former identities. Do not change Compose
   or the workflow. `Review Lab` proves real PostgreSQL derived/spatial
   publication plus all browser scenarios (`.github/workflows/review-lab.yml:77-88`),
   `Backend unit tests + compose validate` proves Python contracts, `Svelte web
   checks` proves type/lint/format/unit/build for the collector
   (`.github/workflows/ci.yml:381-417`), and Svelte Web E2E proves the untouched
   Product E2E wrapper/corpus still works. CodeQL, Semgrep and every other
   protected check remain mandatory under the acceptance policy; the two
   security workflows are defined at `.github/workflows/codeql.yml:1-17` and
   `.github/workflows/semgrep.yml:1-18`.

### Risks and owner questions

- **Yes/no:** Keep exactly three fictional Review systems so the three existing
  support-data states and non-degenerate spatial input survive? Recommended:
  **yes**.
- **Choose one:** Build the dedicated committed fixture by deterministic
  subset/rewrite of `ratings_v4_sources`, or hand-author it from scratch?
  Recommended: **subset/rewrite**, because it preserves the already-proven
  canonical/raw body inventory shape.
- **Choose one:** Extract one corpus-neutral publisher with thin Cypress and
  Review wrappers, or duplicate the pipeline in the Review seed? Recommended:
  **one neutral publisher**, to avoid two security-sensitive publication
  implementations.
- **Yes/no:** Keep a Review-only id64 above JavaScript's exact-integer limit even
  though Product E2E already owns that acceptance case? Recommended: **no**; this
  keeps Review Lab from duplicating a normal product obligation.
- **Yes/no:** Strengthen `renderer_recovery` to require a positive scene-target
  count before fault injection, closing the currently unverified populated-scene
  assumption? Recommended: **yes**, provided the owner accepts that as a proof
  clarification rather than new product acceptance.
- **Yes/no:** Make the unit contract assert an exact 60-second seed timeout rather
  than the present `<= 120` bound? Recommended: **yes**.
- **Yes/no:** Keep the available, unavailable and not-evaluated warehouse/
  provenance profiles mapped one-to-one to the three new identities?
  Recommended: **yes**; otherwise their continued Review Lab purpose should be
  decided before implementation.


### Owner decisions (2026-10-08)

The owner accepted every recommendation above. Three systems was re-examined and
kept: more systems would add only product-style coverage (paging, ranking,
variety) that Product E2E owns, while costing fixture upkeep and seed time
against the fixed 60-second budget.

| # | Question | Decision |
|---|---|---|
| 1 | Exactly three fictional Review systems | Yes |
| 2 | Build the fixture by deterministic subset/rewrite of `ratings_v4_sources` | Subset/rewrite |
| 3 | One corpus-neutral publisher with thin Cypress and Review wrappers | One neutral publisher |
| 4 | Review-only id64 above the JavaScript exact-integer limit | No |
| 5 | `renderer_recovery` requires a positive scene-target count | Yes |
| 6 | Exact 60-second seed-timeout assertion instead of `<= 120` | Yes |
| 7 | Warehouse/provenance profiles mapped one-to-one to the three new systems | Yes |

Implementation proceeds as the three PRs in the plan above, one at a time, each
merged before the next is dispatched.

## Sequencing note
This branch builds on the V3 watchlist work in PR #782 (it removes #782's interim
shim). Base/rebase on `main` after #782 merges.
