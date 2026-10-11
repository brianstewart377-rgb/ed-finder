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
| 0 | Run a new read-only governed inspection and confirm every relevant detached worker (`edfinder-ratings-v4-prod-p4`, `edfinder-ratings-v4-prod-p4-opt1`, `edfinder-ratings-v4-prod-p4-parallel-v1`, `edfinder-v3-system-search-p4-opt1`) has stopped; record `v3_meta.derived_generation` and `v3_meta.derived_product` lifecycle states and the current canonical/derived/spatial pointers before dispatching any migration apply. | **Inspection run 2026-10-10; step 0 stays OPEN until the stopped-workers receipt is recorded.** First receipt recorded below (`evidence/2026-10-10-v3-derived-lifecycle-status-receipt.json`): pointers recorded, ledger unchanged, `edfinder-ratings-v4-prod-p4-opt1` **paused** (`ready_for_governed_plan: false`), data volume ≈292 GB free — see 'Disk decision (2026-10-10)'. The owner then killed the paused container on the host (`docker kill edfinder-ratings-v4-prod-p4-opt1`, 2026-10-10) and a second governed run (38081240686) exited 0; step 0 is DONE only when that second receipt is recorded here showing `all_named_workers_stopped: true` and `ready_for_governed_plan: true` |
| 1 | Register the rewritten `010`, then `011` and `013`, after `014` in the V3 manifest + authority. | **DONE (PR #792); not applied.** PR #780 is superseded. `013` creates only two new empty scheduler tables; it adds no constraint to or scan of an existing populated table. Registration makes the [parallel rebuild](../development/system-search-parallel-rebuild.md) available but does not authorize or execute it |
| 2 | Run the governed migration `plan`, review it, and apply the pending migrations. | tooling exists (`v3-production-schema-migration.yml`). With step 1 complete in PR #792, the production pending set is `[014, 010, 011, 013]` in that order. **Blocked (2026-10-10):** the runner applies every pending entry, so this step would apply the current eight-row `011`; it may run only after the rewritten `011` and `015` are registered (ROADMAP step 4′) |
| 3 | Run a separate governed `VALIDATE CONSTRAINT` operation for all 18 deferred `system_search` checks. | **Action built, not yet run:** `scripts/operator/actions/v3-system-search-validate-constraints.sh` (`start`/`status`), allowlisted in `.github/workflows/chatgpt-ed-new-ops.yml` as `v3-system-search-validate-constraints-start` / `-status` (this PR). It runs only after migration `010` is in the live ledger with hash `a042ccd1…`, validates each check in its own transaction under a detached runner, and `status` reports `pg_constraint.convalidated` for all 18 — the catalog is the receipt. Run it before the fresh build so the full-table scan covers about 198.5M retained `opt1` rows instead of about 397M rows after the second product. The `NOT VALID` checks still enforce every subsequent builder insert automatically |
| 4 | Create a fresh, non-published, `010`-aware derived generation. | **needs new tooling/decision** — `ratings-v4-generation.sh:174-177` always derives `ratings_v4_prod_p${sequence}` and `ratings_v4_prod_p4` already exists BUILDING, so dispatching it *resumes `p4`*, it does not create a fresh key. Either adopt `p4` as the candidate or add fresh-key/retarget support |
| 5 | Build `system_search` with body-type counts on that generation. | `v3-system-search-f1.sh` exists but is **pinned to `opt1`** AND verifies only migration `006` (not `010`), while the v2 builder writes `010`'s columns — so it needs **both** a retarget to the fresh generation **and** to pin+verify exact `010`, or it passes preflight then fails on the first body-count write. After step 2, `013` makes the code-only parallel chunk-range builder available |
| 6 | Run the authorized read-only coefficient-calibration probe and record the coefficient decision. | **Action built, not yet run:** `scripts/v3_archetype_calibration_probe.py` (read-only, bounded) run through `scripts/operator/actions/v3-archetype-calibration-probe.sh`, allowlisted as `v3-archetype-calibration-probe` (this PR). Its receipt (per-archetype score distributions, primary/secondary counts, tier histograms, mining/manufacturing/megacomplex separation) is the calibration evidence; the coefficient decision must be recorded in docs before step 7 registers the product. The probe can read the already-published `parallel_v1` ratings vectors and does not wait for the fresh generation, so it may run earlier once the step 0 state is reconfirmed. The decision must precede `system_archetype` registration because coefficients are hashed into the product manifest and a `READY` product cannot be rewritten |
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
The two wide-row lines were measured the same day with the F2d design's DDL
(section 3.1 of `docs/superpowers/specs/2026-10-10-v3-finder-f2d-wide-archetype-and-product-attachment-design.md`, PR #806;
foreign keys to other relations omitted) filled with 200,000 synthetic rows of
realistic shape by the committed script
`scripts/dev/measure_wide_archetype_footprint.py` (disposable loopback database
only); its output is
[`evidence/2026-10-10-wide-archetype-footprint-200k.json`](evidence/2026-10-10-wide-archetype-footprint-200k.json)
and the design is under review as PR #806. Each
per-key score index entry is unique when `system_id64` is a trailing column
(49.8 B/row each); without it, PostgreSQL's B-tree deduplication collapses the
101 distinct score values into posting lists (7.5 B/row each). The picked
ranking orders by the computed product `score × confidence × completeness`,
which no score index can serve, and the wide row is joined by its primary key,
so the trailing `system_id64` buys nothing; the deduplicating form keeps the
`min_development_score` / tier-floor range path at about 1.5 GB per key.

| Relation | sample rows | table B/row | index B/row | prod rows | table GB | index GB | total GB |
|---|---:|---:|---:|---:|---:|---:|---:|
| `system_rating_vector` | 199,992 | 328 | 47 | 198.5 M | 65 | 9 | **74** |
| `body_mechanics` | 199,800 | 109 | 69 | n/a (scales with bodies / eligible body-economy pairs) | n/a (scales with bodies / eligible body-economy pairs) | n/a (scales with bodies / eligible body-economy pairs) | n/a (scales with bodies / eligible body-economy pairs) |
| `economy_opportunity` | 199,908 | 95 | 94 | n/a (scales with bodies / eligible body-economy pairs) | n/a (scales with bodies / eligible body-economy pairs) | n/a (scales with bodies / eligible body-economy pairs) | n/a (scales with bodies / eligible body-economy pairs) |
| `system_search` | 199,992 | 273 | 164 | 198.5 M | 54 | 33 | **87** |
| `system_archetype` | 199,968 | 422 | 194 | 1,588.0 M | 670 | 307 | **978** |
| `system_archetype_summary` | 199,992 | 96 | 79 | 198.5 M | 19 | 16 | **35** |
| wide-row `system_archetype` (F2d design, one row per system, 42 columns, no explanation; PK + 8 `(generation, <key>_score DESC, system_id64)` indexes + weighted index — the spec's first draft) | 200,000 | 186 | 480 | 198.5 M | 37 | 95 | **132** |
| wide-row `system_archetype` (same table; PK + 8 deduplicating `(generation, <key>_score DESC)` indexes + weighted index — the recommended layout) | 200,000 | 186 | 142 | 198.5 M | 37 | 28 | **65** |

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
now built but not yet run; it reads the published `parallel_v1` ratings vectors,
does not depend on the fresh generation, and may run earlier once step 0
reconfirms state.

## Step 0 receipt (read-only governed inspection, 2026-10-10)

Run: `chatgpt-ed-new-ops.yml` run 38079894267, operation `v3-derived-lifecycle-status`
(request `20261010-v3-derived-lifecycle-status-step0-run2.json`), exit 0, `status: success`,
`failures: []`. Full receipt:
[`evidence/2026-10-10-v3-derived-lifecycle-status-receipt.json`](evidence/2026-10-10-v3-derived-lifecycle-status-receipt.json)
(GitHub masked the two-character SSH port and the SSH user name wherever they
occurred in the log; the file restores them from context — the canonical id is
`a7076522-…` and the key is `root_filesystem`.)

What it established:

- **Workers:** `edfinder-ratings-v4-prod-p4` exited (137, 2026-09-13),
  `edfinder-ratings-v4-prod-p4-parallel-v1` exited (0, 2026-09-16),
  `edfinder-v3-system-search-p4-opt1` exited (0, 2026-09-21), but
  **`edfinder-ratings-v4-prod-p4-opt1` is `paused`** (Docker `State.Running`
  true). `all_named_workers_stopped` is therefore **false** and
  `ready_for_governed_plan` is **false**. The paused container must be killed
  (not unpaused — unpausing would resume its writes) before any migration apply.
  No allowlisted operation does this yet; it is an owner action on the host.
  **Done by the owner on 2026-10-10** (`docker kill edfinder-ratings-v4-prod-p4-opt1`
  on the production host, after this receipt). A second governed
  `v3-derived-lifecycle-status` run (38081240686) exited 0 afterwards; its
  receipt is not yet recorded here, so step 0 stays open until it is.
- **Ledger:** 001, 002, r1_v3/001, 003, 004, 005, 006, 008, 009, 012 applied;
  **014, 010, 011, 013 not applied** (pending set unchanged).
- **Pointers:** canonical `phase4c_full_20260827_r5` PUBLISHED (seq 4); derived
  `ratings_v4_prod_p4_parallel_v1` PUBLISHED (seq 1); spatial `pyramid_v1`
  PUBLISHED (seq 1, 2026-09-23). Current pointers recorded.
- **Generations/products:** `ratings_v4_prod_p4` BUILDING (4.94 M of 198.5 M
  systems), `ratings_v4_prod_p4_opt1` VALIDATING with `system_search`
  `v3-system-search-1` READY (pre-`010`), `ratings_v4_prod_p4_parallel_v1`
  PUBLISHED with **no Finder products**.
- **Disk (the decisive number):** the PostgreSQL data volume `/dev/md1` is
  1,948 GB with **292 GB available** (1,557 GB used); the database is
  1,345 GB. Live derived relations: `system_rating_vector` 158 GB,
  `body_mechanics` 210 GB, `economy_opportunity` 265 GB,
  `system_search` 81 GB. Attributed to the one complete published
  generation (`parallel_v1`): rating vectors 78 GB + body mechanics 104 GB +
  economy opportunities 131 GB = **313 GB of ratings relations per
  generation**. The superseded `opt1` holds about 313 GB of ratings relations
  plus its 81 GB `system_search`; partial `p4` about 8 GB.

### Disk decision (2026-10-10): the fresh-generation plan does not fit

A complete fresh generation as the controlling sequence describes it needs the
ratings relations (313 GB measured live) plus post-`010` `system_search`
(≈87 GB), `system_archetype` (≈978 GB) and `system_archetype_summary` (≈35 GB)
from the disposable-sample measurement above: **≈1,413 GB against 292 GB
available.** Even after a governed purge of `p4` and `opt1` (≈401 GB
recoverable), only ≈693 GB would be free. Step 4 therefore **cannot be
dispatched as designed**. Before any further Finder production step the owner
must choose a path that fits; the realistic candidates are:

1. **Redesign the archetype product for scale before applying `011`** (it is
   not applied anywhere in production, so it can still change without
   migration debt): one wide row per system (eight scores/tiers/confidences,
   explanation not stored or stored compactly) is ≈198.5 M rows instead of
   1.59 B and removes the ≈978 GB term. This needs a new F2 schema/plan review.
2. **Attach Finder products to the published `parallel_v1` generation instead
   of rebuilding ratings** — removes the 313 GB ratings rebuild — but
   requires a reviewed change to migration `006`'s guard (products may only be
   inserted while the base generation is BUILDING/VALIDATING) and a product-level
   publication step; a design decision, not a tooling one.
3. **A governed purge path** for `p4`/`opt1` (insert-only triggers reject
   DELETE/TRUNCATE today), worth ≈401 GB, as a complement to 1 and 2.

Because applying `011` as written would commit production to the
1.59-billion-row layout — and the governed migration runner applies every
pending entry, `011` included — **step 2 (plan/apply) and step 3 are blocked
as well**, not only steps 4–9, until the rewritten `011` and `015` are
registered (ROADMAP step 4′). (An earlier draft of this paragraph said steps
1–3 remained allowed; that was wrong for the reason just given.)

The options, with numbers, effort and risk, are written up in
[`v3-finder-capacity-decision-2026-10-10.md`](v3-finder-capacity-decision-2026-10-10.md)
(recommendation: redesign the archetype product as one wide row per system and
attach the Finder products to the published generation; purge later).

**Owner decision (2026-10-10, recorded by Claude from the owner's approval in
chat):** A + B — rewrite `011` as the wide-row archetype product with
explanations computed on demand (model version pinned to the product), attach
the Finder products to the published `ratings_v4_prod_p4_parallel_v1` behind an
explicit product-publication gate (migration `015`), defer the purge path (C),
and accept the new ranking identity. Steps 4–9 of the controlling sequence are
superseded by the `v3-finder-capacity-decision-2026-10-10.md` sequence, and
`docs/ROADMAP.md` is amended in the same change so the programme authority
carries the decision. Two consequences recorded with the decision:

- **B touches every write path, not only registration.** Attaching a product
  to a PUBLISHED generation must relax, together and with the same
  product-state and insert-only enforcement kept: `v3_meta.guard_derived_product`
  (registration/transitions), `v3_derived.guard_system_search_insert`, the
  `011` archetype insert guard, and the base-state checks inside both Python
  builders (`scripts/v3_system_search.py`, `scripts/v3_system_archetype.py`);
  the API's `_current_derived_generation` then also requires the explicit
  product publication. Relaxing only the registration guard would let
  registration succeed and the first chunk insert fail.
- **On-demand explanations are served only under an exact version match.**
  The fit model is one mutable implementation whose `ARCHETYPE_VERSION` has
  been advanced in place before, so the API must refuse (HTTP 409, fail
  closed) to explain a product whose pinned `archetype_version` differs from
  the deployed model's; after a later model change the old product's
  explanations are unavailable until the product is rebuilt. No versioned
  replay registry is kept. This is a recorded owner question in the F2d
  design, not a silent default.

## Disk inventory (read-only, 2026-10-11)

The step 0 receipt accounts for 1,345 GB of the data volume's 1,557 GB used as
the operating database, leaving 212 GB unaccounted. The governed
`v3-disk-inventory` action is intended to locate that usage and identify
potentially reclaimable space by reporting the volume and root-filesystem
figures, **the largest directories on the whole filesystem that holds the data
directory** (not only the PostgreSQL volume subdirectory — the data directory is
a Docker-volume path on the same device as `/`, so a scan limited to it would
hide every sibling consumer such as Docker layers, logs and backups, which is
precisely the unaccounted usage being looked for), the largest databases, WAL usage and
retention signals (including replication slots and prepared transactions, which
can pin WAL), temporary-file and logging figures, the largest non-system
relations with heap/TOAST/index sizes, their indexes and scan counts **with the
statistics window** (`idx_scan` is cumulative since the last statistics reset,
so a recently reset counter must not be read as “never used”), dead-tuple
estimates, and derived-generation attribution, followed by an explicit
accounted-versus-unaccounted summary whose candidate directories exclude
**only** what an accounted figure genuinely covers — only what an accounted figure
genuinely covers: the **live database directories** inside `base/` (which is what
`pg_database_size` sums — it scans `base/<database OID>`, not the whole directory)
plus the measured temporary files, and `pg_wal` (`wal_bytes`). **Any remaining
`base/` bytes are reported separately** as an inside-PGDATA candidate — an
orphaned OID directory from a dropped database, or a stray file, is inside no
accounted figure and is among the most reclaimable things this receipt can find,
so it must not be dismissed as already counted. **`pg_xlog` is not
WAL-accounted on PostgreSQL 18**, where the WAL directory is `pg_wal`:
`pg_ls_waldir()` measures only the live directory, so a stale `pg_xlog` is
unexpected storage and is reported whole as an inside-PGDATA candidate. It is one
of the better things this receipt can surface — a leftover directory of old WAL
segments is genuinely reclaimable — so it must not be dismissed as already
counted. The
temporary directory is `base/pgsql_tmp`, inside `base`, so it needs no entry of
its own. The cluster-level statistics directories `pg_stat` and `pg_stat_tmp`,
`global`, `pg_xact`, `pg_multixact`, `pg_tblspc`, logs and replication-slot state
are **not** covered by any accounted figure, so they appear as candidates flagged
`inside_data_directory` — listed so the summary can locate every byte it reports
as unaccounted, **not** as reclaim suggestions: several of them must never be
deleted. pg_wal's own subdirectories are reported separately too, because
`pg_ls_waldir()` lists only its top-level ordinary files.

The directory scan is **fail-closed**: if it cannot run, the operation stops
rather than returning a receipt that looks complete while missing the only
host-level evidence that answers the question.

Five bounding, metric and windowing rules govern how the receipt may be read:

- **Bounded lists, unbounded totals.** `pg_database` and the generation
  attribution tables both grow without limit, so the receipt displays only the
  largest rows (`database_inventory_limit`, `generation_attribution_limit`, each
  with a `_truncated` flag). Every total that `accounted_bytes` depends on is
  computed **in SQL across all rows**, never by summing the displayed list:
  summing the bounded list would understate `accounted_bytes`, and
  `unaccounted_bytes` is `volume_used_bytes` minus `accounted_bytes`, so each
  omitted database would surface as apparently reclaimable space. The same rule keeps
  the **operating database** inside its own bound (it sorts ahead of size) and bounds
  the **tablespace refusal path** off a count rather than a row per tablespace — a
  fail-closed guard must not be the thing that fails to emit the stopped receipt.
  **Replication slots** follow it too, ordered by WAL *actually retained* rather than
  by name: the bound must never drop the slot that explains the WAL the receipt is
  accounting for. PostgreSQL's `wal_status` semantics invert the intuitive reading —
  `extended` means `max_wal_size` is exceeded but the files are **still retained** (the
  state that puts unexpected WAL on the volume), while `unreserved` means the slot *no
  longer* retains the required WAL and `lost` means it is unusable — so the sample is
  ordered `extended`, then `reserved`, then furthest behind by `restart_lsn`, and the
  counts report what retains WAL (`reserved`/`extended`) rather than what has stopped.
- **`base/pgsql_tmp` and every live database directory must survive the `base` cap.**
  Their bytes are already inside `accounted_bytes`, so an entry dropped by the
  size-based cap would be presented among the unaccounted candidates while still being
  subtracted as accounted — and the negative metric-difference term that follows can
  leave the closure flag `true`. The breakdown is refused when either was not observed
  (`live_database_directories_not_all_observed`, `temporary_directory_not_observed`).
- **Row caps emit an aggregate candidate, never a silent gap.** Where a `du` row cap
  drops entries — PGDATA's children or `base/`'s — their bytes are subtracted from the
  "files directly in this directory" remainder (so they are not mislabelled) **and**
  reported as their own candidate saying how many entries it covers and that the paths
  were not retained. Subtracting without adding back removed those bytes from the
  partition altogether, and a directory with thousands of entries is overwhelmingly
  the unexpected storage this inventory exists to find.
- **The published generation is always retained.** Generation keys carry no
  chronology, so lexicographic order can place the live generation past the
  bound. Both the SQL ordering and the receipt assembly therefore keep the
  generation named by `v3_meta.current_derived_generation`, and
  `generation_attribution_published_generation_retained` records that it was. A
  table in which every listed generation is superseded would otherwise read as
  a licence to reclaim all of them.
- **Two `df` windows, each paired with its own measurement.**
  `unaccounted_bytes` uses `volume_used_bytes`, the **closing** reading, because
  the database and WAL figures it subtracts are also closing figures.
  `filesystem_minus_directory_scan_bytes` uses
  `volume_used_bytes_at_directory_scan`, the reading taken immediately after the
  `du` scan it is subtracted from. Pairing the scan with the closing reading
  would charge every byte written or freed by the intervening SQL to the
  residual — and the residual's whole meaning is filesystem metadata and blocks
  held by deleted-but-open files, so that contamination cannot be told apart
  from the signal. Both readings appear in the summary.
- **`base/` is broken down in one metric, and orphans are named by path.** GNU `du`
  reports allocated filesystem blocks; `pg_database_size` sums each entry's `st_size`.
  Subtracting the latter from the former turned ordinary per-file block rounding,
  across tens of thousands of relation files, into a standing "orphaned storage under
  `base/`" candidate. `postgres_base_directory_breakdown` is instead a depth-1 `du`
  scan of `base/` that identifies live database directories **by OID**, so every entry
  that is not a live database is reported by its own path — actionable in a way a lump
  remainder never is. The residual difference between the two metrics is
  `database_size_metric_difference_bytes`, which is **not reclaimable**: it is two
  tools measuring the same files differently. When the breakdown is unavailable (its
  `reason` says why) **no `base/` candidate is emitted at all** and
  `candidates_partition_unaccounted_at_scan` is `null`. An unexplained gap in the
  partition is honest; a fabricated reclaim target is not. The breakdown is refused
  when its inputs cannot be trusted to describe one state: an unbounded or **changed**
  OID set (a database created between the OID query and the scan would have its live
  directory reported as orphaned — the most dangerous output this receipt could
  produce), an unmeasured `base` child, an exhausted scan budget, a failed scan, or
  `base/` itself drifting beyond tolerance between the PGDATA walk and the `base` walk.
  All of its figures, including `base/`'s own total, come from the `base` scan.
- **The dead-tuple inventory is ranked by estimated reclaimable bytes, then capped.**
  Not drawn from the largest relations: dead tuples *are* reclaimable space, and the
  table holding the most of it need not be among the largest by total size — a moderate
  table that is mostly dead outranks a huge one that is almost all live. Ranked by
  estimated dead bytes rather than dead tuple count, because the count says nothing
  about row width. `dead_tuple_inventory_scope` and `_truncated` record the scope.
- **The index inventory is ranked globally, then capped.** It is not drawn from the
  largest relations: the 21st relation can be mostly one very large index while the
  first 20 are larger only because of heap data, so that index was absent while
  `indexes_truncated` still said `false`. `index_inventory_scope` records the scope.
- **A negative remainder is a named signed term, never a dropped row.** Every remainder
  in the summary is a measured total minus figures measured by a different instrument
  or at a different moment, so each can come out negative — WAL recycled between the
  directory walk and `pg_ls_waldir()`, `base/` changing between the two walks. A
  negative cannot be a candidate (there is no negative storage to reclaim), and
  dropping it broke the closure; a shrink even turned already-recycled WAL into an
  "unlisted storage" candidate. These are listed in `closure_adjustments` and summed as
  `closure_adjustment_bytes`, which includes the **accepted** `base/` drift: the
  add-backs come from the `base` walk while the outer partition removed `base` as
  measured by the PGDATA walk, so any drift inside the tolerance shifts the candidate
  total by exactly that amount.
- **Database churn is never attributed to a sibling path.** The outside candidates
  subtract the data-directory size measured **beside the root walk**, not the closing
  one: `usage_full` holds the data directory as it was during that walk, so subtracting
  the closing figure charged the intervening database churn to an ancestor such as
  `/var/lib` — a shrink inflated that candidate by the removed database bytes and growth
  could drive it negative, pointing an operator at a sibling directory as reclaimable
  space that is actually the live database moving. The deliberate difference between the
  two sides is carried as a signed closure term.
- **`pg_wal`'s location is tested by device, not by path.** A separate volume or bind
  mount attached at `pg_wal`'s canonical destination is not a symlink, so `readlink -f`
  returns the expected pathname while `du -x` does not descend into it — the bytes are
  absent from the PGDATA total while `pg_ls_waldir()` is still subtracted from the
  volume. `stat -c %d` reads the same `st_dev` the kernel gives `du -x`, so it tests
  exactly the property the arithmetic depends on.
- **Each closing scan gets its own full allowance.** The reserve is opened once per
  closing scan rather than once for the phase, so the `base/` walk cannot start with
  whatever the PGDATA re-read and the intervening SQL left over — its failure is an
  optional unavailable breakdown, which would have dropped the base attribution
  silently.
- **The directory partition is exact across row-cap ancestor gaps.** The retained set is
  a bounded top-k and so is not ancestor-closed — the cap can keep a child while
  dropping its parent. Each row's exclusive size subtracts its reported descendants that
  have no *nearer* reported ancestor, rather than only its immediate children, so the
  exclusive sizes still sum to the scanned root's total exactly once.
- **Four terms in the summary are artefacts, not reclaimable space.**
  `post_scan_volume_drift_bytes` (sibling consumers moving between the root scan and
  the close), `database_size_metric_difference_bytes` (above), and
  `filesystem_minus_directory_scan_bytes` (`df` against `du`). The candidates partition
  **`unaccounted_bytes_at_directory_scan`**, not `unaccounted_bytes`, and the receipt
  asserts the identity explicitly as `candidates_partition_unaccounted_at_scan`, and
  **a `false` verdict fails the operation** (`candidate_partition_does_not_close:gap_N`,
  with the summary preserved for diagnosis). `null` is the separate "cannot be
  asserted" case where the optional `base/` breakdown is unavailable:

  ```
  candidate_total_bytes
    + database_size_metric_difference_bytes
    + filesystem_minus_directory_scan_bytes
    + closure_adjustment_bytes
    == unaccounted_bytes_at_directory_scan
  ```

  All four artefact terms belong in it (`closure_adjustment_bytes` is the fourth). Every candidate is a `du` measurement, so the
  candidates sum towards `directory_scan_root_bytes` while the figure they explain
  starts from a `df` reading — and the gap between those two *is* the residual. (An
  identity asserted without it would be false on any real filesystem, since `df` and
  `du` always differ; it would only hold in a fixture where they agree.) `df`, `du` and
  the SQL queries cannot be read atomically on a live multi-terabyte cluster, so each
  difference is named rather than absorbed into a candidate, where up to the whole
  reconciliation tolerance — several GiB here — could hide in a receipt reporting
  success. The paired `df` reading is taken **immediately** after the root scan, before
  the second full data-directory walk, so the pairing holds in time and not merely in
  name.

The action is read-only and reclaims nothing: it creates, modifies and deletes
nothing, and both interpreter invocations take `-B` so no bytecode is written. One
write it cannot avoid is reported rather than covered. The control plane pipes one
self-contained script to `bash -s` over SSH, and bash uses a pipe for a here-document
only while it fits the pipe buffer; this program is larger, so the shell spools it to
an unlinked temporary file before the interpreter starts (measured under bash 5.2.21:
a 126 KB here-document resolves stdin to `/tmp/sh-thd.* (deleted)` where a 62-byte one
resolves to a pipe). That file holds the program's own text, no host data, and does not
outlive the shell. `filesystem_writes_scope` in every receipt says so, because an
unqualified `filesystem_writes_performed: false` overclaimed. Any purge, index removal,
relation rewrite, or other reclamation remains a separate reviewed design and
operator action.

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
