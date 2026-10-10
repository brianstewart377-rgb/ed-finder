# Finder rollout — capacity decision (2026-10-10)

**Status:** decided 2026-10-10 — owner approved **A + B** (purge deferred, new
ranking identity accepted); recorded in `v3-finder-production-rollout-state.md`.
Questions 5–6 (explanation version rule, wide-row index layout) were added
after review and **answered yes by the owner on 2026-10-10 (23:12 BST, in
chat: “yes yes”, after the index layout had been revised to the partial
form)** — recorded below; the ROADMAP lists these recorded answers as the
prerequisite of step 4′, which is therefore satisfied. Numbers come
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
| wide-row `system_archetype` (F2d design: one row per system, no stored explanation; PK + weighted index + 8 **partial** `(generation, <key>_score DESC, system_id64) WHERE <key>_score >= 60` indexes, synthetic distribution with 16.9 % ≥ 60) | 186 B table + 149 B index | **≈ 66 GB** (rises with the real ≥ 60 fractions; ceiling ≈ 132 GB) |
| the same wide row with full `(generation, <key>_score DESC, system_id64)` indexes (= the ceiling) | 186 B table + 480 B index | ≈ 132 GB |
| the same wide row with deduplicating `(generation, <key>_score DESC)` indexes (the 2026-10-10 evening draft — rejected after review: it cannot bound the F4 slice 1c probe without a tie sort) | 186 B table + 142 B index | ≈ 65 GB |

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
tiers and confidences live in one row (measured 186 B incl. header and
alignment), with the summary columns (`primary_archetype`,
`secondary_archetype`, `best_colony_potential`, `best_tier`,
`archetype_confidence`, `weighted_potential`) folded into the same row and the
summary table replaced by a view. Indexes: the primary key
`(generation, system_id64)` (the picked-archetype join now uses it — one row per
system, no key lookup), the `weighted_potential` index for the default no-pick
ordering, and one **partial** `(generation, <key>_score DESC, system_id64)
WHERE <key>_score >= 60` index per archetype. The partial index serves the
`min_development_score` / tier-floor range path and, decisively, the F4 slice 1c
bounded probe, which reads the first 10,001 rows of a key in exact
`score DESC, system_id64` order and stops; integer scores tie heavily, so an
index without `system_id64` would need to sort the boundary score group
(size unknown until the calibration probe reports the real distribution). The
picked ordering itself is the computed product `score × confidence ×
completeness` applied to that bounded window. Index cost: 49.8 B per indexed
row, but only rows with that key's score ≥ 60 are indexed — every floor F4
exposes (S/A/B) lies inside the predicate — so the size is 49.8 B × (fraction
≥ 60): 8.4 B/row (≈ 1.7 GB per key) on a bell-shaped synthetic sample, 49.8
B/row (≈ 9.9 GB per key) at the ceiling. The step 6 calibration probe's
per-key tier histogram sizes it for real before the build. (Probe experiment:
`scripts/dev/measure_wide_archetype_probe_indexes.py`, output
`evidence/2026-10-10-wide-archetype-probe-index-experiment.json` — partial
index: index-only scan, 10,001 rows, 2.2 ms warm at 1M rows.)
The per-archetype `explanation` is **not stored**: the fit model
(`scripts/v3_system_archetype_model.py`) is pure and deterministic, so the API
recomputes one system's explanations on demand from its rating vector and
economy opportunities (one indexed read; the data is already read for the
Inspect panel). Because that model is a single implementation whose version
has been advanced in place before, explanations are served only when the
deployed model version equals the product's pinned `archetype_version`;
otherwise the API fails closed (HTTP 409) rather than describing an old
product with new logic. After a later model change the old product's
explanations are unavailable until it is rebuilt — accepted instead of
keeping a versioned replay registry (owner question 5).

*Disk (measured on the disposable PostgreSQL 18.4 sample with the design's
DDL, 200,000 rows, extrapolated to 198.5 M; script
`scripts/dev/measure_wide_archetype_footprint.py`, output
`evidence/2026-10-10-wide-archetype-footprint-200k.json`).* 37 GB table + 8 GB primary key +
8 GB weighted index + ≈ 13 GB partial score indexes (synthetic distribution)
≈ **66 GB** instead of 978 + 35 GB, with a hard ceiling of ≈ 132 GB if every
system scored ≥ 60 on every key. (The first draft's 80–90 GB guess undercounted
the primary key and weighted index; the measurement replaces it, and the
calibration probe's histogram fixes the partial-index term before the build.)

*Effort.* A new `011` (migration text), the F2b model/builder/validator and their
tests adapted to the wide row, the F2c/F3 ranking SQL re-pointed at the new
columns, the step 6 probe unchanged (it reads vectors, not the product). Code-only
until the governed build; roughly four Codex PRs plus my PostgreSQL verification.
The Review Lab and Cypress fixtures apply `011` too and follow the rewrite.

*Risk.* Moderate, all pre-production: the ranking profile contract (`ranking_version`)
changes shape, so it is a new ranking identity. Behaviour is preserved (same
scores, same tiers).

*Alone it still does not fit:* a fresh generation would be 313 + 87 + 66 = **466 GB**
against 292 GB free — so A needs B or C as well.

### B. Attach the Finder products to the already-published generation (no ratings rebuild)

*What changes.* Migration `006`'s guard allows product registration/build only
while the base generation is BUILDING, VALIDATING or READY
(`006_v3_derived_product_lifecycle.sql:53`); PUBLISHED is excluded. A reviewed
migration (`015`) would permit products to be **added** to a PUBLISHED generation
while keeping every other guard (insert-only rows, READY requires a validation
receipt, manifests immutable). The same base-state rule is enforced in four
places, and all four must change together or registration succeeds and the
first chunk insert fails: `v3_meta.guard_derived_product` (registration and
state transitions), `v3_derived.guard_system_search_insert` (search rows and
receipts), the `011` archetype insert guard (archetype rows and receipts), and
the base-state checks in both Python builders (`scripts/v3_system_search.py`
and `scripts/v3_system_archetype.py` reject PUBLISHED in code today). The
product-state rule (writes only while the product is BUILDING) and the
insert-only triggers stay exactly as they are. Publication of a *product* then needs an explicit
gate: today the API serves the Finder as soon as both products are READY on the
published generation (`local_search.py:620-640`), so `015` should also add a
`product_published_at` column that the `v3_app.*` views and the API check, with a
small governed "publish product" action — the moment Finder goes live stays a
reviewed decision, not a side effect of validation.

*Disk.* Removes the 313 GB ratings rebuild entirely. New data = search 87 GB +
archetype (978 GB as-is, or ≈ 66 GB with A; ≤ 132 GB ceiling).

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

*Disk.* Up to ≈ **400 GB** — but not from `DELETE` + ordinary `VACUUM`: on these
unpartitioned relations a plain `VACUUM` only marks the freed pages reusable
*inside* the same table, so the space would be available to future rows of
`body_mechanics`/`economy_opportunity`/`system_rating_vector`, **not** to the
new archetype or search tables and not to the filesystem. Returning it to
`/dev/md1` needs a table rewrite (`VACUUM FULL`, `CLUSTER` or `pg_repack`),
which holds a full copy of the table in temporary space — impossible for a
265 GB table with 292 GB free — or a partition-per-generation redesign so a
generation can be dropped as a whole relation. Deleting 1.5 billion rows also
takes hours and must not run while anything else is building.

*Effort/risk.* Moderate-to-high effort (a reclamation mechanism, not just a
delete), the highest operational risk of the three (it is the only option that
destroys data), and on its own it does not make the fresh-generation plan fit
or free filesystem space for the Finder relations. Worth designing later for
hygiene, most plausibly as per-generation partitioning for future generations.

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
new data written:  search 87 GB + archetype ≈ 66 GB (measured; ≤ 132 GB ceiling)  ≈ 153 GB
free today:        292 GB   →  ≈ 139 GB headroom for WAL/temp/vacuum (≥ 73 GB at the ceiling)
```

The production gate before the archetype build repeats the measurement with
the final migration text and stops if search + archetype + working room do not
fit the free space reported by the step 0 receipt at that time.

Design **C** afterwards as hygiene, knowing that it reclaims filesystem space
only through a table rewrite or partition drop (see C); a plain delete would
not make room for anything but future ratings rows.

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
5. Accept the exact-version rule for on-demand explanations (served only when
   the deployed model version equals the product's pinned `archetype_version`;
   HTTP 409 otherwise; no versioned replay registry)?
   **Owner: yes (2026-10-10).**
6. Adopt the wide-row index layout of primary key + weighted index + eight
   **partial** `(generation, <key>_score DESC, system_id64) WHERE <key>_score
   >= 60` indexes (≈ 66 GB on the synthetic sample, sized for real from the
   calibration probe's tier histogram, ceiling ≈ 132 GB)? This replaces the
   deduplicating variant proposed earlier the same evening, which review showed
   cannot bound the F4 slice 1c probe without a distribution-dependent tie
   sort.
   **Owner: yes (2026-10-10), given with the partial-index form in view.**

Once recorded, the next dispatches are: the `011` rewrite + model/builder
adaptation (code), the `015` migration + API gate (code), and the amended
registration PR — all verified on disposable PostgreSQL 18 before anything
touches production.
