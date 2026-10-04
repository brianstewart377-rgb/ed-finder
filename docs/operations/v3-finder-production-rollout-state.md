# V3 Finder production rollout — actual state & honest remaining path

**As of 2026-10-04.** This document exists because the roadmap and delivery plan
described the Finder production rollout as further along, and with more tooling,
than actually exists. It is the single source of truth for what is *really* true
in production and what is *really* left to do. Where the roadmap / delivery plan
disagree with this file, **this file is correct** (it was written from a direct
read-only inspection of the production database and the committed operator
tooling). Earlier prose is evidence, not current truth.

## Verified production state (read-only inspection, 2026-10-04)

Derived generations in the production database:

| generation_key | lifecycle | published? | Finder products |
|---|---|---|---|
| `ratings_v4_prod_p4_parallel_v1` | PUBLISHED (current) | yes (seq 1) | **none** |
| `ratings_v4_prod_p4_opt1` | VALIDATING | no (superseded) | `system_search: READY` (**pre-010**) |
| `ratings_v4_prod_p4` | BUILDING | no | none |

Migrations: **`010_v3_system_search_body_type_counts.sql` and
`011_v3_system_archetype.sql` are NOT applied to production** (verified: the
`system_search` body-type columns and the `system_archetype` relations do not
exist). `013_v3_system_search_parallel.sql` is also unapplied/undeclared.

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
| 1 | Register `010`/`011` in the V3 manifest + authority (PR #780) | **done, PR open** |
| 2 | Governed migration `plan` → `apply` of `010`/`011` | tooling exists (`v3-production-schema-migration.yml`) |
| 3 | Create a fresh non-published `010`-aware derived generation (ratings pass) | tooling exists (`ratings-v4-generation.sh`) |
| 4 | Build `system_search` **with** body-type counts on it (~198.5M, long pole) | `v3-system-search-f1.sh` exists but is **pinned to `opt1`** — needs retargeting to the fresh generation |
| 5 | Build `system_archetype` on it | **NO governed action — must be built** (model on `f1`) |
| 6 | Validate both products → READY | builder `--validate` modes exist |
| 7 | Publish the generation (`publish_derived_generation`) | **NO governed action — must be built** (model on the pyramid publish) |
| 8 | Governed app release + promote of `main` (ships the F3 code) | tooling exists |

Steps 5 and 7 are unbuilt governed tooling. They can only be written **after**
step 3/4 produce the fresh generation, because the governed action pattern pins
the exact target generation identity (canonical UUID / key / sequence) as a
fail-closed safety property — it cannot be pinned to a generation that does not
yet exist.

## Where else this pattern can bite (watch-list)

- **Migrations committed but undeclared** (`013` today): a `sql/v3/migrations/*`
  file that is not in `migration-manifest.txt` is NOT applied to prod. Treat the
  manifest, not the migrations directory, as the source of truth for "applied".
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
