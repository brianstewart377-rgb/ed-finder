# Finder rollout — capacity decision (2026-10-10)

**Status:** decided 2026-10-10 — owner approved **A + B** (purge deferred, new
ranking identity accepted); recorded in `v3-finder-production-rollout-state.md`. Numbers come
from the step 0 receipt
(`evidence/2026-10-10-v3-derived-lifecycle-status-receipt.json`) and the
disposable-sample measurement in
[`v3-finder-production-rollout-state.md`](v3-finder-production-rollout-state.md).

## 1. The facts

| Measured on production (2026-10-10) | Value |
|---|---:|
| PostgreSQL data volume (`/dev/md1`) | 1,948 GB total, 1,557 GB used, **292 GB free** |
| Database `edfinder_v3_phase4c_full_20260827_r5` | 1,345 GB |
| Ratings relations of one complete generation (`parallel_v1`, attributed by chunk receipts) | rating vectors 78 GB + body mechanics 104 GB + economy opportunities 131 GB = **313 GB** |
| Superseded data still on disk | `opt1` ratings ≈ 313 GB, `opt1` `system_search` 80 GB, partial `p4` ≈ 8 GB ⇒ **≈ 400 GB** |

| Measured on a disposable PostgreSQL 18.4 sample (replicated to ~200k rows, same DDL and indexes) | Per row | At production scale |
|---|---:|---:|
| `system_search` after migration `010` (198.5 M rows) | 273 B table + 164 B index | **≈ 87 GB** |
| `system_archetype` as migration `011` defines it (8 rows per system = 1,588 M rows; ≈ 410 B of each row is the `explanation` JSON) | 422 B table + 194 B index | **≈ 978 GB** |
| `system_archetype_summary` (198.5 M rows) | 96 B + 79 B | **≈ 35 GB** |

## 2. Why the plan as written cannot run

The controlling sequence (ROADMAP steps 4–9) builds a **fresh** ratings
generation and then both Finder products on it:

```text
ratings 313 GB + search 87 GB + archetype 978 GB + summary 35 GB  ≈ 1,413 GB needed
                                                                   292 GB free
```

Even a governed purge of `p4` and `opt1` (≈ 400 GB back) leaves ≈ 690 GB free,
less than half of what the fresh generation needs. PostgreSQL also needs working
room for WAL, temporary files and vacuum (budget 10–15 % of the data written).
**Step 4 must not be dispatched on this design**, and applying migration `011`
as written would commit production to the 1.59-billion-row layout.

Two facts make this fixable without heroics: migration `011` has never been
applied in production (it can still be rewritten, exactly as `010` was), and the
published generation `ratings_v4_prod_p4_parallel_v1` already holds complete,
validated ratings relations that the Finder products only need to read.

## 3. The options

### A. Redesign the archetype product for scale (rewrite `011` before applying it)

*What changes.* One row per system instead of eight: the eight scores (`smallint`),
tiers and confidences live in one row (≈ 150 B incl. header), with one B-tree
index per archetype score for the picked-archetype ordering (8 × ≈ 6 GB) and the
summary columns (`primary_archetype`, `secondary_archetype`,
`best_colony_potential`, `best_tier`, `archetype_confidence`,
`weighted_potential`) folded into the same row. The per-archetype `explanation`
is **not stored**: the fit model (`scripts/v3_system_archetype_model.py`) is pure
and deterministic, so the API recomputes one system's explanations on demand
from its rating vector and economy opportunities (microseconds; the data is
already read for the Inspect panel).

*Disk.* ≈ 30 GB table + ≈ 50 GB indexes ≈ **80 GB** instead of 978 + 35 GB.

*Effort.* A new `011` (migration text), the F2b model/builder/validator and their
tests adapted to the wide row, the F2c/F3 ranking SQL re-pointed at the new
columns, the step 6 probe unchanged (it reads vectors, not the product). Code-only
until the governed build; roughly four Codex PRs plus my PostgreSQL verification.
The Review Lab and Cypress fixtures apply `011` too and follow the rewrite.

*Risk.* Moderate, all pre-production: the ranking profile contract (`ranking_version`)
changes shape, so it is a new ranking identity. Behaviour is preserved (same
scores, same tiers).

*Alone it still does not fit:* a fresh generation would be 313 + 87 + 80 = **480 GB**
against 292 GB free — so A needs B or C as well.

### B. Attach the Finder products to the already-published generation (no ratings rebuild)

*What changes.* Migration `006`'s guard allows product registration/build only
while the base generation is BUILDING, VALIDATING or READY
(`006_v3_derived_product_lifecycle.sql:53`); PUBLISHED is excluded. A reviewed
migration (`015`) would permit products to be **added** to a PUBLISHED generation
while keeping every other guard (insert-only rows, READY requires a validation
receipt, manifests immutable). Publication of a *product* then needs an explicit
gate: today the API serves the Finder as soon as both products are READY on the
published generation (`local_search.py:620-640`), so `015` should also add a
`product_published_at` column that the `v3_app.*` views and the API check, with a
small governed "publish product" action — the moment Finder goes live stays a
reviewed decision, not a side effect of validation.

*Disk.* Removes the 313 GB ratings rebuild entirely. New data = search 87 GB +
archetype (978 GB as-is, or ≈ 80 GB with A).

*Effort.* One migration, API/view changes with tests, a publish action, and the
steps 4/5/7/8/9 tooling becomes simpler (no new generation key — everything
pins `ratings_v4_prod_p4_parallel_v1`, which is already the published pointer).

*Risk.* Moderate: it changes the lifecycle safety model, so it needs the same
review discipline as `010` (plan → apply, tested on disposable PostgreSQL 18).
The ratings data itself is untouched.

### C. A governed purge path for `p4` and `opt1`

*What changes.* The insert-only triggers reject DELETE and TRUNCATE on the derived
relations. A reviewed migration adds a purge function that only accepts
generations in a terminal, non-published state (`FAILED`/`RETIRED` after an
explicit retirement step), deletes their rows in bounded batches and records a
receipt; plus an operator action to drive it.

*Disk.* ≈ **400 GB** back — but deleting 1.5 billion rows from 200–265 GB tables
takes hours, leaves bloat until `VACUUM` reclaims it, and must not run while
anything else is building.

*Effort/risk.* Moderate effort, the highest operational risk of the three (it is
the only option that destroys data), and on its own it still does not make the
fresh-generation plan fit. Worth doing later for hygiene.

### D. Buy disk

Resizing `/dev/md1` on the mevnode host is a hosting change (cost, downtime
window, backup/PITR implications). Kept as the fallback if A/B are rejected.

## 4. Recommendation

**A + B**, in that order: rewrite `011` as the wide-row archetype product, add
`015` to attach and explicitly publish products on the published generation,
then register and apply `[014, 010, 011', 013, 015]`, build `system_search`
(post-`010`) and the new `system_archetype` on `parallel_v1`, validate, publish
the products, revise the release gate, promote.

```text
new data written:  search 87 GB + archetype ≈ 80 GB  ≈ 170 GB
free today:        292 GB   →  ≈ 120 GB headroom for WAL/temp/vacuum
```

Schedule **C** afterwards as hygiene (it also removes the 80 GB pre-`010`
`opt1` search product that the retention paragraph currently keeps).

What this changes in the controlling sequence: steps 4 ("fresh generation") and
the "retention" branch are replaced by "attach to published generation";
steps 5/7/8/9 keep their shape but pin `ratings_v4_prod_p4_parallel_v1`; the
step 6 probe is unchanged; `011` moves from "register" to "rewrite, then
register". The step 1 registration already merged (#792) would be amended to
replace `011` with the rewritten file — allowed, because `011` has not been
applied anywhere.

## 5. Decisions needed from the owner (yes/no)

1. Adopt **A** (wide-row archetype product; explanations computed on demand, not
   stored)?
2. Adopt **B** (products attached to the published generation behind an explicit
   product-publication gate; no ratings rebuild)?
3. Defer **C** (purge) until after the Finder ships?
4. Accept that the ranking identity (`ranking_version`) changes with A, so the
   Finder F2c/F3 contract and the F4 design cite the new identity?

Once recorded, the next dispatches are: the `011` rewrite + model/builder
adaptation (code), the `015` migration + API gate (code), and the amended
registration PR — all verified on disposable PostgreSQL 18 before anything
touches production.
