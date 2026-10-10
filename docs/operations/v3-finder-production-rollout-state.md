# V3 Finder production rollout — actual state & honest remaining path

**As of 2026-10-04.** This document exists because the roadmap and delivery plan
described the Finder production rollout as further along, and with more tooling,
than actually exists. It is **verified evidence** of what is really true in
production (from a direct read-only inspection of the production database and the
committed operator tooling), and what is really left to do.

**Authority note:** `docs/ROADMAP.md` remains the programme authority (per the
repository authority chain); this operations file does not override it. Where
they diverge, that is a signal to **correct the roadmap to match this verified
evidence**, not to follow this file instead. The controlling sequence lives in
the roadmap.

**Updates after 2026-10-04:** the additions below, including the PR #792
registration facts, are repository/workflow facts, not a new production
inspection.

## Verified production state (read-only inspection, 2026-10-04) and current repository status

Derived generations and the registered migrations:

| Item | Lifecycle / repository status | Published / applied? | Finder products / effect |
|---|---|---|---|
| `ratings_v4_prod_p4_parallel_v1` | PUBLISHED (current) | yes (seq 1) | **none** |
| `ratings_v4_prod_p4_opt1` | VALIDATING | no (superseded) | `system_search: READY` (**pre-010**) |
| `ratings_v4_prod_p4` | BUILDING | no | none |
| `014_v3_watchlist.sql` | registered 2026-10-06 | **not applied** | none; it now follows `012` in the desired lineage |
| `010_v3_system_search_body_type_counts.sql` | rewritten with `NOT VALID` checks and registered by PR #792 | **not applied** | none; it follows `014` in the desired lineage |
| `011_v3_system_archetype.sql` | registered by PR #792 | **not applied** | none; it follows `010` in the desired lineage |
| `013_v3_system_search_parallel.sql` | registered by PR #792 | **not applied** | none; it follows `011` in the desired lineage |

At the 2026-10-04 inspection,
**`010_v3_system_search_body_type_counts.sql` and
`011_v3_system_archetype.sql` were NOT applied to production** (verified: the
`system_search` body-type columns and the `system_archetype` relations did not
exist), and `013_v3_system_search_parallel.sql` was also unapplied and
unregistered at that time. PR #792 has since registered the rewritten `010`,
then `011` and `013`, after `014`; none of `014`, `010`, `011`, or `013` has
been applied.

No **governed** production workflow has run since 2026-09-25:
`v3-production-schema-migration.yml` last ran on 2026-09-23,
`v3-production-application-deploy.yml` last ran on 2026-09-25, and
`chatgpt-ed-new-ops.yml` last ran on 2026-09-22. However,
`ratings-v4-generation.sh` and `v3-system-search-f1.sh` launch detached worker
containers with `docker run -d`; workers dispatched by an earlier workflow may
have continued committing chunks and changing generation or product lifecycle
state after that workflow finished. The 2026-10-04 inspection is therefore the
last **verified** production state, not a guarantee of the current state.
Migration `014` is registered but has not been applied by a governed workflow;
after PR #792, the production pending set is `[014, 010, 011, 013]` in that
order.

PR #782 (`abaf3f5`) registered `014_v3_watchlist.sql` after `012` on 2026-10-06.
The resulting intermediate lineage was `through-012-014`, with migration-set identity
`sha256:7511a66d438a6413153be3d5515622e007c58ee722c2c5ae39d6ed2adc3e6684`.
It transitions from the installed `through-012` identity
`sha256:17263a9748eb936d3c6a7f3e3f75224a40d5e48e011276aedf511946abfff4fe`.
The V3 lineage is an exact-prefix, append-only ledger, enforced by
`scripts/operator/v3_production_migrate.py::plan_migrations`. PR #792 appends
the rewritten `010`, then `011` and `013`, after `014`. The current lineage is
`through-012-014-010-011-013`, with migration-set identity
`sha256:1c390ac27a34261ca0aad0e411cf260fe99a30896a45926381a87e5516ae32d9`.
PR #780 was based on `main` at `5fbb978`; its manifest, authority JSON, and
lineage tests are stale and the PR is superseded by PR #792. Registering `013`
makes the code-only parallel chunk-range rebuild available; it does not
authorize or execute that rollout.

## Migration 010 has been rewritten in PR #792 before application

Migration `010` in its prior form **could not be applied by the bounded runner**.
`scripts/operator/v3_production_deploy.py` sets `COMMAND_TIMEOUT = 120`, which
kills the `psql` apply after 120 seconds. That prior form added 18 `CHECK`
constraints inline; PostgreSQL validates the new checks with a
whole-table scan while holding `ACCESS EXCLUSIVE`.

On PostgreSQL 18.4, a measured 10,000,000-row, 1.35 GB cached table took 1.46
seconds to add two inline checks and scan the table. Adding the same columns
without checks took 1.2 ms; adding the checks as `NOT VALID` took 0.4 ms.
Production `v3_derived.system_search` contains the superseded `opt1` product,
about 198.5 million wide rows on VPS disk. Applying that prior form
would scan for minutes under a lock that blocks every Finder search, then the
runner would kill it at 120 seconds and the transaction would roll back.

PR #792 rewrites `010` before step 2 below: it adds the 18 columns as `NOT NULL
DEFAULT 0` (metadata-only on PostgreSQL 18), then adds the 18 checks as `NOT
VALID` with the same names PostgreSQL would have generated,
`system_search_<column>_check`. It keeps the view recreation and uses `014`'s
`SET LOCAL lock_timeout = '5s';` /
`SET LOCAL statement_timeout = '30s';` pattern.
`NOT VALID` checks are enforced for every subsequent `INSERT` and `UPDATE`.
Every existing row satisfies them by construction: the new columns read as the
default `0`, and migration `004` already enforces `landable_count >= 0`, so
`walkable_count BETWEEN 0 AND landable_count` also holds. The repository already
uses the `NOT VALID` then `VALIDATE` pattern for large constraints in
`001_v3_baseline.sql` near line 1520.

## The drift this corrects (the audit)

The same failure mode — *a document asserting readiness/tooling that reality does
not back* — appeared in several places:

1. **"F1 rebuild currently running"** (ROADMAP) — stale. `opt1`'s `system_search`
   is READY, not running; and `opt1` is itself the *superseded* candidate.
2. **"F1 v2 with body-type counts"** (delivery plan) conflates *code merged* with
   *prod data built*. The code (migration `010` + builder) has body-type counts;
   the only built `system_search` in prod (`opt1`) is the **pre-`010`** version,
   because `010` was never applied. A merged migration that production never ran
   was treated as done.
3. **No clean generation to ship from.** The published generation
   (`parallel_v1`) has no Finder products and, being PUBLISHED, cannot accept them
   (006 lifecycle gate); the only generation with a `system_search` (`opt1`) is
   superseded and pre-`010` and cannot be upgraded in place (the builder treats a
   READY product as terminal). Neither the roadmap nor the plan acknowledged this.
4. **The "governed production run" is an outcome, not tooling.** The plan says
   "build the product to READY, then publish the owning generation" and names
   `v3_meta.publish_derived_generation` — but **no operator action exists** to
   build `system_archetype` or to publish a derived generation. Only
   `v3-system-search-f1.sh` (system_search) and `v3-spatial-pyramid.sh` (a
   *different* publish path) exist.

## Honest remaining path (owner-dispatched; full-rebuild decision, 2026-10-04)

The owner chose the complete Finder (full `010`-aware rebuild on a fresh
generation) over a reduced-scope launch on `opt1`.

| # | Step | Tooling status |
|---|---|---|
| 0 | Run a new read-only governed inspection and confirm every relevant detached worker (`edfinder-ratings-v4-prod-p4`, `edfinder-ratings-v4-prod-p4-opt1`, `edfinder-ratings-v4-prod-p4-parallel-v1`, `edfinder-v3-system-search-p4-opt1`) has stopped; record `v3_meta.derived_generation` and `v3_meta.derived_product` lifecycle states and the current canonical/derived/spatial pointers before dispatching any migration apply. | **Action built, not yet run:** `scripts/operator/actions/v3-derived-lifecycle-status.sh`, allowlisted in `.github/workflows/chatgpt-ed-new-ops.yml` as `v3-derived-lifecycle-status` (this PR). Its receipt records the four worker states, the migration ledger, and the canonical/derived/spatial pointers; step 0 is complete only when a dated run receipt is recorded here. |
| 1 | Register the rewritten `010`, then `011` and `013`, after `014` in the V3 manifest + authority. | **DONE (PR #792); not applied.** PR #780 is superseded. `013` creates only two new empty scheduler tables; it adds no constraint to or scan of an existing populated table. Registration makes the [parallel rebuild](../development/system-search-parallel-rebuild.md) available but does not authorize or execute it |
| 2 | Run the governed migration `plan`, review it, and apply the pending migrations. | tooling exists (`v3-production-schema-migration.yml`). With step 1 complete in PR #792, the production pending set is `[014, 010, 011, 013]` in that order |
| 3 | Run a separate governed `VALIDATE CONSTRAINT` operation for all 18 deferred `system_search` checks. | **NO governed action — must be built.** Run it before the fresh build so the full-table scan covers about 198.5M retained `opt1` rows instead of about 397M rows after the second product. The `NOT VALID` checks still enforce every subsequent builder insert automatically |
| 4 | Create a fresh, non-published, `010`-aware derived generation. | **needs new tooling/decision** — `ratings-v4-generation.sh:174-177` always derives `ratings_v4_prod_p${sequence}` and `ratings_v4_prod_p4` already exists BUILDING, so dispatching it *resumes `p4`*, it does not create a fresh key. Either adopt `p4` as the candidate or add fresh-key/retarget support |
| 5 | Build `system_search` with body-type counts on that generation. | `v3-system-search-f1.sh` exists but is **pinned to `opt1`** AND verifies only migration `006` (not `010`), while the v2 builder writes `010`'s columns — so it needs **both** a retarget to the fresh generation **and** to pin+verify exact `010`, or it passes preflight then fails on the first body-count write. After step 2, `013` makes the code-only parallel chunk-range builder available |
| 6 | Run the authorized read-only coefficient-calibration probe and record the coefficient decision. | **NO governed action — must be built.** The probe can read the already-published `parallel_v1` ratings vectors and does not wait for the fresh generation, so it may run earlier once the step 0 state is reconfirmed. The decision must precede `system_archetype` registration because coefficients are hashed into the product manifest and a `READY` product cannot be rewritten |
| 7 | Build `system_archetype` on the same generation. | **NO governed action — must be built** (model on `f1`) |
| 8 | Validate both products to `READY`. | **NO governed action — must be built:** the step 5 and step 7 build actions must expose and receipt the validation path (search: inline in `run()`; archetype: `--validate`) so READY is reached through a reviewed route |
| 9 | Publish the owning generation with `v3_meta.publish_derived_generation`. | **NO governed action — must be built** (model on the pyramid publish) |
| 10 | Revise and review the application-release gate for the newly published generation. | **PENDING** — `v3-production-application-release.md:292-330` still requires publishing against the now-PUBLISHED/immutable `ratings_v4_prod_p4_parallel_v1`; following the fresh-generation sequence would violate that gate until it is updated for the new generation |
| 11 | Run the governed application release and promote `main`. | release tooling exists, but step 10 is a hard prerequisite |

Retaining `opt1`'s roughly 198.5-million `system_search` rows is currently the
**only executable path**: migration `006_v3_derived_product_lifecycle.sql`
installs statement-level `DELETE` and `TRUNCATE` triggers that reject mutation
with `system_search rows and receipts are insert-only`, and no reviewed governed
purge migration/action exists. Purge is therefore not an available branch.
Before step 4, the owner must either accept retention after measuring the
complete candidate footprint of `system_rating_vector`, `body_mechanics`, and
`economy_opportunity`, including their primary-key indexes, on a disposable
PostgreSQL 18 sample and extrapolating those relations and indexes to full scale,
and confirm disk headroom for the complete fresh Ratings V4 generation: roughly
198.5 million `system_rating_vector` rows plus `body_mechanics` (one row per
physical body) and `economy_opportunity` (one row per eligible body/economy
pair), which can be far larger than the system-level rows, and their primary-key
indexes (step 4), roughly 198.5 million fresh `system_search` rows with 18 new
count columns (step 5), roughly 1.59 billion fresh `system_archetype` rows plus
roughly 198.5 million fresh `system_archetype_summary` rows (step 7), and all
associated ratings, search, archetype, and summary indexes, including
`system_archetype_key_score` and `system_archetype_summary_weighted`; or add
**design and review a governed purge path** as a prerequisite before step 4.
The step 0 action `v3-derived-lifecycle-status` now reports measured live
relation and index sizes, the data volume's free space, and proportional
chunk-receipt system-count attribution per generation (the
`measured_footprint_attribution` section). These are **inputs** to the disk
decision; they do **not** replace the required disposable PostgreSQL 18 sample
measurement and full-scale extrapolation of the post-`010` `system_search` row
width or the `system_archetype` and `system_archetype_summary` relations and
indexes.

### Disposable-sample footprint measurement (2026-10-10, PostgreSQL 18.4)

Measured by Claude on the disposable local PostgreSQL 18.4 service, not on
production. Method: the committed Ratings V4 fixture (12 systems, 3 chunks) was
built into a real generation with the repository's own builders
(`scripts/v3_system_search.py` with the rewritten migration `010` from PR #792
applied, and `scripts/v3_system_archetype.py`, archetype version
`v3-archetype-3`); the resulting real rows were then replicated into scratch
tables created with `LIKE … INCLUDING ALL` (same columns, constraints and
indexes) to about 200,000 rows each, shifting `system_id64` so keys stay unique,
then `VACUUM ANALYZE`d and sized with `pg_table_size` / `pg_indexes_size`. Bytes
per row therefore include real page fill and index overhead. Extrapolation uses
198.5 M systems and 8 archetype rows per system (1,588 M rows). Caveat: the
replicated rows repeat the same 12 systems' content, so name lengths and body
counts carry no real-world variation; the per-row widths are structural
(fixed columns plus the `explanation` jsonb, which averages about 410 bytes per
`system_archetype` row in the sample) and should be read as order-of-magnitude.

| Relation | sample rows | table B/row | index B/row | prod rows | table GB | index GB | total GB |
|---|---:|---:|---:|---:|---:|---:|---:|
| `system_rating_vector` | 199,992 | 328 | 47 | 198.5 M | 65 | 9 | **74** |
| `body_mechanics` | 199,800 | 109 | 69 | n/a (scales with bodies / eligible body-economy pairs) | n/a (scales with bodies / eligible body-economy pairs) | n/a (scales with bodies / eligible body-economy pairs) | n/a (scales with bodies / eligible body-economy pairs) |
| `economy_opportunity` | 199,908 | 95 | 94 | n/a (scales with bodies / eligible body-economy pairs) | n/a (scales with bodies / eligible body-economy pairs) | n/a (scales with bodies / eligible body-economy pairs) | n/a (scales with bodies / eligible body-economy pairs) |
| `system_search` | 199,992 | 273 | 164 | 198.5 M | 54 | 33 | **87** |
| `system_archetype` | 199,968 | 422 | 194 | 1,588.0 M | 670 | 307 | **978** |
| `system_archetype_summary` | 199,992 | 96 | 79 | 198.5 M | 19 | 16 | **35** |

Sum of the four system-level relations for one complete fresh generation: about
**1,174 GB**, of which `system_archetype` alone is about
978 GB (422 B/row table + 194 B/row for its
primary key and `system_archetype_key_score`). `body_mechanics` (178 B/row
including its primary key) and `economy_opportunity` (188 B/row including its
primary key) scale with bodies and eligible body/economy pairs, not systems;
multiply 178 B/row by the published generation's `ratings_physical_bodies` and
188 B/row by its `ratings_eligible_opportunities` from `rows_by_generation`,
then add both results to the sum above. Retention means the superseded `opt1`
`system_search` rows (about 198.5 M, pre-`010` width) and the `p4`/`opt1` ratings
rows also stay on disk. Compare the total against
`footprint.host_disk.avail_bytes` from the step 0 receipt before approving step
4. The dominant term is the per-archetype
`explanation` jsonb; if headroom is short, the honest options are to shrink or
externalise that column (a product/schema decision, requiring a new archetype
version) or to design and review the governed purge path — not to proceed.

The governed actions for steps 7, 8, and 9 are unbuilt. They can only be finalized
**after** step 4 creates the fresh generation, because the governed action
pattern pins the exact target generation identity (canonical UUID / key /
sequence) as a fail-closed safety property — it cannot be pinned to a generation
that does not yet exist. Build the separate step 3 table-level constraint
validation tooling alongside those actions; it runs outside the migration
runner and does not depend on a generation pin. The step 6 calibration action is
also unbuilt, but it reads the published `parallel_v1` ratings vectors, does not
depend on the fresh generation, and may run earlier once step 0 reconfirms state.

## Where else this pattern can bite (watch-list)

- **Three distinct states — don't conflate them.** (1) *Committed*: a
  `sql/v3/migrations/*` file exists. (2) *Registered/desired*: it is listed in
  `migration-manifest.txt` — a production-promotion gate, NOT an application
  receipt. (3) *Applied*: it has a row in the live `v3_meta.schema_migration`
  ledger. The **live ledger is the only source of truth for "applied"** (the
  migration `plan` reads it and separates `applied_before` from `pending`). After
  PR #792, `010`/`011`/`013` are registered after `014` but the `apply` has not
  been dispatched, so they are committed + registered but **not applied** —
  reading the manifest as "applied" would be exactly the drift this document
  corrects. (`013` is registered after `011` by PR #792.)
- **"Product built / rebuild running" claims**: verify against
  `v3_meta.derived_product.lifecycle_state` + the actual columns/rows, not the
  roadmap. A READY product built before a later additive migration is stale.
- **Operator actions named in runbooks**: before presenting a governed sequence,
  confirm each `scripts/operator/actions/*.sh` it depends on actually exists.
  (Dangling historical references also exist in archived docs and in
  `v3-live-checkpoint-infrastructure.md` — residue, not current gaps.)
- **"Governed run" / "publish" described as outcomes**: a doc naming a SQL
  function or an end-state is not evidence that an executable, reviewed operator
  path to reach it exists.
