> Read-only study, 2026-10-21.
> Evidence, not execution authority.

# How V3 galaxy data could be refreshed: a comparison of approaches

Read-only study, written 2026-10-21 and revised the same day. No branches, commits, PRs or
production access were used. Repo state read: `main` at `c396eb21`. This answers the owner's
request of 2026-10-21 for a plan (decision D8 in the earlier scoping report
[`2026-10-21-eddn-v3-scoping.md`](2026-10-21-eddn-v3-scoping.md), Part E).

Every figure marked **(estimate)** is my arithmetic, not a measurement. Everything else cites the
file and line it comes from.

> **Correction 2026-10-21.** The first version said Spansh's small daily files carry no planets.
> That is true only of the `systems_*` files. The owner verified on https://spansh.co.uk/dumps
> (2026-10-21) that Spansh also publishes **full-detail delta files** in the same galaxy schema as
> `galaxy.json.gz`, with bodies and stations:
>
> | File | Size | Covers |
> |---|---|---|
> | `galaxy_1day.json.gz` | 1.1 GiB | "Only systems where any information within that system was updated in the last 24 hours" |
> | `galaxy_7days.json.gz` | 2.8 GiB | last 7 days |
> | `galaxy_1month.json.gz` | 5.1 GiB | last 32 days |
> | `galaxy_populated.json.gz` | 4.3 GiB | — |
> | `galaxy_stations.json.gz` | 4.2 GiB | systems with a station, carriers included, "updated at least every hour" |
> | `galaxy.json.gz` | 109.9 GiB | the full galaxy |
>
> The `systems_*` files (1day 2.6 MiB, 1week 18.2 MiB, 2weeks, 1month 86.2 MiB, 6months
> 596.6 MiB) are system-only.
>
> This changes the conclusion. Option B is now split in two:
>
> - **B1 (change the published data in place):** still rejected.
> - **B2 (nightly add-on layers that never change the published snapshot):** new, and now
>   recommended.
>
> Sections 3–9 were rewritten. Section 2 (the full rebuild) is unchanged apart from cross-references.

---

## Plain-language summary

1. Today the galaxy data never updates. It is a copy of Spansh's full file dated **2026-08-24**, so it is about two months old.
2. **Recommendation:** leave that big copy alone, and each night add a small "changes" layer built from Spansh's daily file. The app reads the big copy plus the layers, and the newest wins.
3. **Each layer is a complete, checked, separately published build** for the systems it covers: ratings, Search and Archetype included. Undoing a bad night means switching that one layer off.
4. Only systems whose planets or stations really changed go into a layer. Daily faction changes are skipped, because V3 does not store faction data.
5. Expected cost per night: a few hundred thousand systems at most, under about 2 hours of work and a few GB of disk. (estimate)
6. **One-time catch-up:** the daily files only reach back 32 days and our copy is 58 days old. So once, we read the full 110 GiB file and keep only systems updated since 2026-08-24. That needs tens of GB, not the 1.5 TB of a full second copy. (estimate)
7. A full second copy (option A) stops being needed for freshness. It is only needed when the scoring rules or the table layout change, or when the layers grow very large. The disk upgrade can wait.
8. **Stations:** the daily file already includes stations, so the separate station store and the live EDDN listener can wait. Downloading the hourly 4.2 GiB station file would mean about 100 GiB a day and is not worth it now.
9. **Changing the published data in place (B1) is still rejected.** It breaks the rule that published data never changes, and there would be no way back.
10. Before anything runs:
    - new tooling, built and rehearsed at 1% scale;
    - an update to the data-design document;
    - your decision on whether the nightly job may publish on its own.
11. **Nothing starts in production before the Finder go-live and the purge.** Every production step is marked **[OWNER GO]**.

---

## 1. What exists today: the facts every option depends on

### 1.1 The current snapshot

**The Spansh source file**

- `galaxy.json.gz` is **116,027,020,549 bytes**.
- Spansh dated it ("effective") `2026-08-24T05:32:35Z`.
- It was downloaded `2026-08-24T21:24:56Z`.
- Source: `tests/fixtures/ratings_v4_sources/source-metadata.json:1`.

**The canonical import**

- The run went from `2026-08-27T12:05:58Z` to `2026-08-28T18:46:38Z`, which is **30 h 41 min** (same file).
- The generation was published as sequence 4 at 2026-08-28 19:05 UTC
  (`docs/operations/evidence/2026-10-10-v3-derived-lifecycle-status-receipt.json:3-21`).

**Size of the canonical data**

- About **615 GB**: bodies 266, body_composition 136, body_parent_evidence 124, systems 57,
  rings 28, small tables ≈ 5 (same receipt, `relations`).
- That is **≈ 3.1 KB per system** on average (estimate).

**One derived set**

| Product | Size | Source |
|---|---|---|
| Ratings relations | 313 GB | `docs/operations/v3-finder-capacity-decision-2026-10-10.md:39` |
| Search | ≈ 87 GB | `docs/ROADMAP.md:390-392` |
| Archetype | ≈ 66 GB at the measured Σ_all of 0.5895 (estimate) | `docs/ROADMAP.md:382-384, 490-491` |
| Pyramid | 15 GB | — |

- Total **≈ 480 GB**, or **≈ 2.4 KB per system** (estimate).

**The disk**

- The data volume is `/dev/md1`: 1,948 GB total
  (`docs/operations/v3-finder-capacity-decision-2026-10-10.md:37`).
- Its size equals one 2 TB drive, so the two NVMe drives are almost certainly mirrored
  (inference from the size).

**Free space** (all estimates)

- About **270 GB** at the 7′ gate. The gate reported 96 GB of headroom after its 15% reserve
  (`docs/ROADMAP.md:500`; `scripts/v3_finder_capacity_gate.py:262-277`).
- About **120 GB** after both Finder builds.
- About **500–520 GB** after purge P, if its rewrites return the modelled ≈ 400 GB
  (`v3-finder-capacity-decision-2026-10-10.md:40`).
- Up to about **660 GB** if the ≈ 142 GB host clean-up has not already run (`docs/ROADMAP.md:584`).

### 1.2 Measured build rates

| Step | Measured | Rate per system (estimate) | Source |
|---|---|---|---|
| Canonical import, full file | 30.7 h | ≈ 108k systems/min | `source-metadata.json:1` |
| Ratings V4 build, 8 workers | ≈ 19.7 h | ≈ 168k/min | lifecycle receipt `:82, :93`; `docs/development/ratings-v4-parallel-validation-design.md:190-197` |
| Ratings validation, parallel | 10.5 h | ≈ 315k/min | same |
| Ratings validation, serial (the version in the repo) | ≈ 90 h | ≈ 36k/min | `ratings-v4-parallel-validation-design.md:13-17` |
| Search build | ≈ 13.6 h at 244 chunks/min | ≈ 244k/min | `docs/ROADMAP.md:501-505`; `docs/operations/v3-postgres-server-settings.md:79-83` |
| Archetype build | ≈ 23.6 h at ≈ 140 chunks/min (figure from the brief) | ≈ 140k/min | — |
| Complete read (archetype histogram) | ≤ 8.2 h | — | `docs/ROADMAP.md:487-491` |
| Full backup at 1.25 TB | 5 h 6 min | ≈ 245 GB/h | `deploy/v3-production/backup/README.md:115` |

- One chunk holds ≈ 1,000 systems: 198,529 chunks for 198,528,286 systems.
- These rates come from whole-galaxy runs, where most systems are sparsely explored. Systems in a
  daily delta are probably heavier, so I multiply by **3–5×** for delta work (estimate).
- The backup README also says "roughly three hours" (`:129`), which conflicts with the measured
  5 h 6 min at `:115`.

### 1.3 The rules a refresh has to live with

**1. Published data never changes.**

- Canonical schemas are "immutable after publication" (`sql/v3/migrations/001_v3_baseline.sql:1022-1023`).
  This is a convention; no trigger enforces it.
- Derived tables reject writes after `BUILDING` through triggers
  (`003_ratings_v4_derived.sql:196-214`). The Finder products are insert-only (`006:130-204`).
- Changes must flow through "a derived rebuild and atomic publication"
  (`docs/development/v3-search-spatial-derived-data-decision.md:12, 57-61, 336-352`).
- "A partial/failed derived build can never become current" (`:24`).
- The previous compatible generation is kept for rollback (`:350`).

**2. Derived data can only be published for the current canonical generation.**

- `003:244-258`; `015_v3_derived_product_publication.sql:618-645`.
- The app views do not check that canonical and derived match (`015:325-376`). Inspect reads
  canonical data through the live pointer (`apps/api/src/edfinder_api/v3_schema.py:16-24`).
- So every pointer has to move in **one transaction**. The database functions allow it
  (`001:1662-1760`; `015:590-700`; `012:199-215`; the deferred checks at `015:556-565`), but **no
  action does it**.

**3. Today's builders only target the published snapshot.**

- The ratings bridge refuses anything but the published current generation, and only accepts a
  complete-snapshot source run (`scripts/ratings_v4/canonical_stream.py:220-252`).
- The Search, Archetype and publish actions hard-code `ratings_v4_prod_p4_parallel_v1`
  (`v3-system-search-f1.sh:56`, `v3-system-archetype.sh:56`, `v3-publish-derived-products.sh:28`).
- The pyramid action hard-codes canonical `a7076522…` (`v3-spatial-pyramid.sh:13-15`).

**4. The builders work chunk by chunk over one derived generation.**

- Search and Archetype iterate the ratings `build_chunk` rows of one derived generation
  (`scripts/v3_system_search.py:241-258`; `scripts/v3_system_archetype.py:329-346`).
- They set `expected_rows` from that generation's `expected_systems`
  (`v3_system_search.py:116`; `v3_system_archetype.py:180`).
- **So they can already run over any set of systems that is its own derived generation**,
  including a small one. They do not need the whole galaxy.

**5. Scoring depends only on the system itself.**

- Ratings V4 raw scores are "absolute mechanics-based 0-100 values, not galaxy percentiles"
  (decision `:140`).
- Inheritance, links and local scores all work within one system
  (`docs/development/ratings-v4-freeze/README.md:11-15`).
- Archetype uses fixed anchors and coefficients (`v3_system_archetype.py:102-123`).
- Search is a per-system projection.
- **So recomputing only the changed systems gives exactly the result a full rebuild would give
  for them.** The exceptions are galaxy-wide aggregates: the spatial pyramid's density counts,
  clusters (not built yet), and the capacity gate's tier fractions.

**6. The ratings build re-reads its source file.**

- The ratings bridge streams the generation's own Spansh file for `subType`, and checks its size
  and SHA-256 exactly (`canonical_stream.py:88-148`; `ratings-v4-generation.sh:81, 95-131, 236`).
- A delta layer's source file (`galaxy_1day`, same schema) plays that role naturally.

**7. No repeatable full-galaxy import exists in the repo.**

- The recovered `v3_spansh` package still hashes to `b5bf4e0c…`, as pinned. I re-checked it.
- But it refuses a full run: `max_systems <= 5_000_000`, phases `4A`/`4B` only
  (`apps/importer/src/v3_spansh/pipeline.py:151-160`).
- It records `REPRESENTATIVE_SLICE` / `is_complete_snapshot false` (`pipeline.py:289`).
- The production run recorded `4C`, `FULL_GALAXY`, `is_complete_snapshot true` and
  `run_classification "FULL_REHEARSAL_NOT_PRODUCTION"` (`source-metadata.json:1`).
- **The driver that ran it is not in the repo.**
- No ops-workflow operation imports canonical data (`.github/workflows/chatgpt-ed-new-ops.yml:10-38`).

**8. The fast ratings validator is not in the repo.** It exists only in a `/var/tmp` bundle on the
host (`ratings-v4-parallel-validation-design.md:3-9, 165-185`).

**9. The F2d freeze is still on.**

- These are hash-locked until after the go-live (`deploy/v3-production/f2d-operator-code.txt:1-43`):
  - the Search and Archetype builders;
  - the publisher;
  - the capacity gate;
  - the purge libraries;
  - the migration manifest;
  - migrations 001/003/004/006/011.
- After the go-live, changes ship in a new attested release.

**10. Purge interaction.**

- Every build and publish refuses while a purge event is open (`docs/ROADMAP.md:594-596`).
- The purge's 100 GB floor covers WAL (`v3-governed-derived-purge-design.md:399`).
- Only never-published generations may be removed (`:404`).

**11. Backup.**

- WAL is archived to the Storage Box. `max_wal_size` is 32 GB and `wal_compression` is zstd
  (`v3-postgres-server-settings.md:40-42`).
- pgBackRest keeps 2 fulls and 4 diffs (`docs/operations/v3-storage-box-restoration.md:9`).
- The first full was 1,252.9 GB (`backup/README.md:115`).
- **The Storage Box size and the compression settings are not recorded in the repo.**
- No restore has ever been rehearsed (`README.md:122-129`).

**12. Journal enrichment.**

- Shared journal facts are applied only to a **never-published candidate**.
- A candidate that leaves out an eligible observation is refused
  (`docs/development/journal-commander-contributions.md:80-93`).
- A delta layer is a candidate until it is published, so it fits this design.

**13. V3 canonical data has no faction, population or influence columns.**

- `adapter.py` does not read them (grep finds none). See also scoping A2.
- So daily faction churn in populated systems changes **nothing** that V3 stores. That matters for
  delta volume (section 3.2).

---

## 2. Option A: a full new canonical generation each time (unchanged from version 1)

**What it is.**

1. Download `galaxy.json.gz`.
2. Import it into a new `v3_gen_<key>` schema next to the live one.
3. Build every derived product on it.
4. Move every pointer in one transaction.

### Wall time (estimate)

| Step | Hours |
|---|---|
| Download | 1–2 |
| Import | 31 |
| Ratings (needs the parallel validator; about 80 h more without it) | 30 |
| Pyramid (in parallel) | hidden |
| Complete read | 8 |
| Search | 14 |
| Archetype | 24 |
| Finishing, probes and publish | 3 |
| **Total** | **≈ 111 h machine time (≈ 4.6 days); 1–2 weeks calendar** |

### Disk peak (estimate)

| Item | GB |
|---|---|
| Live canonical | 615 |
| Live derived | 480 |
| New canonical | ≈ 630 |
| New derived | ≈ 490 |
| Source files | 0–236 |
| Other host use | ≈ 100 |
| 15% working room | ≈ 170 |
| Purge floor | 100 |
| **Total** | **≈ 2.6–2.8 TB** |

- The volume is **1.95 TB, so it does not fit**, even after the purge.
- Keeping the previous pair for rollback means two full pairs (≈ 2.2 TB) in steady state.
- It needs a ≥ 4 TB usable volume, or a second mirrored pair used as an alternating tablespace.
- It writes **≈ 1.1–1.5 TB of WAL per refresh**. The full backup would reach ≈ 2.3–2.5 TB at
  peak, and the Storage Box size is unknown.

### Risk, tooling and staleness

- **Risk: medium.** It is additive until the switch, and the switch is one transaction.
- **Hard part:** removing the old derived set means a purge-style `DELETE` plus `VACUUM FULL` of
  unpartitioned tables, which blocks Finder reads during each rewrite (`docs/ROADMAP.md:604-608`).
- **Staleness:** days to months, depending on cadence.

**Role in the revised plan:** a rare **rebase**. Use it only when scoring, mechanics or the table
layout change, or when the add-on layers grow too large (section 5). It is no longer the way to
keep data fresh.

---

## 3. Option B, re-evaluated with the full-detail daily files

### 3.1 B1: change the published canonical data in place (still rejected)

Updating rows in the published `v3_gen_*` schema and the derived tables:

- breaks immutability (`001:1022-1023`) and the derived write triggers (`003:196-214`, `006:130-204`);
- makes every content seal, validation receipt, product `validation_sha256` and the sealed
  complete-read receipt stale;
- contradicts "partial builds cannot publish" (decision `:24, :406`);
- removes rollback;
- refuses the journal-enrichment rule (`journal-commander-contributions.md:80-83`);
- causes the update churn that bloated V2 to 95% disk
  (`docs/operations/database-bloat-incident-2026-08-20.md:5, 22-27`).

The full-detail delta files do not change any of these points. **Rejected.**

### 3.2 B2: nightly add-on layers ("delta layers") beside an unchanged snapshot

**How it works.**

1. **The base never changes.** The published snapshot `phase4c_full_20260827_r5` and its derived
   set `parallel_v1` stay exactly as they are.
2. **Each night, a new layer is built.**
   - **Source.** It is built from that night's `galaxy_1day.json.gz`, which uses the same schema as
     the base file.
   - **Missed nights.** These are recovered from `galaxy_7days` (7 days) or `galaxy_1month`
     (32 days). This makes the pipeline robust to outages of up to a month.
   - **Contents.** The layer is a canonical delta: a small `v3_gen_<key>`-shaped schema holding
     only the **admitted** systems. Each admitted system is a **complete replacement record**
     (all its bodies and stations), so bodies or stations that vanished within a system are
     handled correctly.
   - **Derived products.** It gets its own derived generation: ratings, Search and Archetype for
     exactly those systems. These are built with the **existing chunked builders**, because they
     already work over "whatever systems this derived generation has" (1.3 rule 4).
3. **Change-only admission.** A system enters the layer only if its *V3-relevant* content differs
   from the version the app currently shows.
   - The comparison is a hash of the normalised V3 rows: bodies, rings, signals and fixed
     stations.
   - Faction and population churn is ignored, because V3 does not store it (1.3 rule 13).
   - **[OWNER DECISION]** Should carrier-only movements be ignored too?
4. **Publication.** In one transaction, the canonical delta, its derived generation and its products
   are added to an ordered **delta stack** keyed to the current base publication. Rollback
   **removes the top layer**: the previous state comes back exactly, with no extra disk.
5. **Reading.**
   - **Inspect** reads the newest layer that holds a system, otherwise the base.
   - **Finder views** become: base rows whose `id64` is not superseded, plus the newest delta
     rows.
   - The **map's density pyramid** stays on the base and is refreshed at rebase time, or an
     overlay pyramid is built later. Density changes by a fraction of a percent per month
     (estimate).
6. **Compaction (small).** Weekly, merge the daily layers into one cumulative layer (the latest
   version of each changed system), then publish it in place of the stack in one transaction.
   - The disk needed is about 2 × the cumulative layer, not 2 × the galaxy.
7. **Rebase (rare, option A).** Fold base plus cumulative layer into a new full generation only
   when one of these happens:
   - the scorer, mechanics, adapter or table layout changes, which needs a full derived rebuild
     anyway;
   - the cumulative layer passes a threshold, for example 10% of systems or ≈ 150 GB
     **[OWNER DECISION]**;
   - the owner wants to handle systems deleted in Spansh. Deltas cannot signal a whole-system
     deletion.

**Daily volume (estimate).**

- **Raw file contents.** Bounds and a planning range for systems per night:
  - *Upper bound:* `galaxy.json.gz` is 109.9 GiB for ≈ 198.5 M systems, an average of
    **≈ 590 bytes compressed per system**. 1.1 GiB at that average is **≈ 2 M systems**.
    Changed systems are heavier than average (more bodies, stations and market data), so the
    real count is lower.
  - *Lower bound:* `systems_1day` (2.6 MiB at ≈ 44 bytes per record; Aug-2026 figure: 84,118
    records in 3.7 MB, `apps/importer/src/import_spansh.py:1700-1702`) suggests
    **≈ 60k systems** get system-level updates daily. `galaxy_1day` ("any information")
    should contain at least those.
  - *Planning range:* **≈ 100k–500k systems in the file per night**.
- **Admitted after the change-only filter.** Likely far fewer.
  - Most daily touches of populated systems are faction or market churn that V3 does not store.
  - Planning figure: **≈ 30k–150k admitted per night** (estimate; step S1 measures it).

**Daily compute (estimate)**, using the 1.2 rates with a 3–5× heavier-system factor:

| Step | 500k systems in the file | 150k admitted (estimate) |
|---|---|---|
| Download 1.1 GiB | ≈ 1 min | — |
| Parse and hash the file for admission | 5–25 min | — |
| Canonical rows | — | 4–7 min |
| Ratings (build + validate) | — | 4–7 min |
| Search | — | 2–3 min |
| Archetype | — | 3–5 min |
| `ANALYZE`, union plan probes, publish | 15–30 min fixed | — |
| **Total** | | **≈ 0.5–1.5 h a night** |

At the 2 M upper bound with nothing filtered out, it is ≈ 3–5 h, which still fits overnight.

**Daily disk (estimate).**

- About 3.1 KB canonical plus 2.4 KB derived per system on average, and 2–3× that for heavier
  systems: **≈ 11–17 KB per admitted system**.
- 150k admitted gives ≈ **1.6–2.5 GB a night**.
- Before weekly compaction, a week's stack is ≈ 10–18 GB. After compaction only the latest
  version of each system remains.
- The cumulative layer grows with **distinct** systems changed since the base. Assuming about
  30–80k new distinct systems a day, that is ≈ 120–500 GB a year (estimate).
- **That growth is what eventually triggers a rebase.**
- WAL is about the same size as the data: a few GB a night, which backups absorb easily.

### 3.3 B2 against the authority chain

**"Derived rebuild + atomic publication"** (decision `:12, :336-352`)

- **Kept, at layer level.** Each layer is a complete, EOF-verified, validated, immutable build of
  its declared scope.
- It publishes in one transaction, and the visible galaxy is reproducible from the base plus the
  ordered layer manifests.
- **Authority change needed:**
  - define a **delta generation kind** whose completeness means "every admitted system in its
    source file", not "the whole galaxy";
  - define the union read semantics;
  - amend `:24` ("partial build") so that a complete-for-scope layer is not a partial build.

**Rollback** (`:350`): **improved.** Removing a layer is exact and costs no extra disk. Compare
option A, which needs two full pairs.

**Immutability:** **kept.** No published row is ever changed. Layers are new schemas and new
derived generations.

**Ratings V4.0 freeze**

- **Compatible.** The same scorer `4.0.0` and mechanics `v4-mechanics-2026-09` run on new
  observations, which the freeze explicitly allows: "New observations can change a rebuilt
  generation without changing the coefficients" (`ratings-v4-freeze/README.md:64-66`).
- Scoring is per-system (1.3 rule 5), so delta scores are identical to what a full rebuild would
  give for those systems.
- **[OWNER DECISION]:** the new importer/delta driver identity enters each layer's lineage. Treat
  it like the PR #647 adapter repin?

**F2d attestation and Finder publication**

- **Changes needed:**
  - Finder envelopes must report base identity **plus delta sequence**;
  - the `015` views become union views;
  - the 24-pair bounded-plan proof of 9′ (`docs/ROADMAP.md:407-435`) must be re-proved for the
    union plans. Base index scan with an anti-join on superseded `id64`s, merged with a small
    delta index scan, should be boundable, because the superseded set is at most the cumulative
    layer.
- The ranking identity (coefficients) is unchanged.
- This all happens after the go-live, in a new attested release.

**Purge and writer fences:** the nightly job is a governed mutator. It must refuse while a purge
event is open, like every other mutator (`docs/ROADMAP.md:594-596`).

**Daily governance**

- A nightly production write cannot wait for a manual go each night.
- **[OWNER DECISION]** Choose one:
  - (a) approve once a scheduled governed job (a host timer installed by a reviewed action, as the
    backup timers were, `backup/README.md:31-32`) that builds and validates nightly and publishes
    only if every gate passes;
  - (b) the job builds and validates, and the owner presses "publish".

### 3.4 Can the existing per-system builders run over a changed-system set?

**Yes, with targeting changes only.**

- **Search and Archetype** iterate one derived generation's ratings chunks and take
  `expected_rows` from it (1.3 rule 4). A delta derived generation whose ratings chunks hold
  150k systems makes them build and validate 150k rows.
- **What changes:** the hard-coded generation keys (1.3 rule 3), and the per-chunk guard query.
  It needs an early `ANALYZE` on new rows; the server-settings note already says so
  (`v3-postgres-server-settings.md:85-96`).
- **Ratings:** `canonical_stream.pin` must accept an explicit **unpublished delta canonical
  generation**, with the layer's own source file as its source, instead of only "published and
  complete" (`canonical_stream.py:220-252`).
- **Storage of delta derived rows.** In the shared `v3_derived` tables, compaction would need
  `DELETE`s that the current purge policy forbids for published generations. Two options:
  - put delta derived rows in **their own partitions or schema per layer**, so compaction drops
    them cheaply;
  - or, by an owner policy change, allow deleting superseded **delta** rows. Freed pages are then
    reused by later layers in the same tables, so no `VACUUM FULL` is needed
    (`v3-finder-capacity-decision-2026-10-10.md:186-190`).

---

## 4. The catch-up problem

- The base reflects Spansh's state at **2026-08-24 05:32 UTC**, about 58 days ago.
- `galaxy_1month` covers only the last 32 days, so changes made between about 2026-08-24 and
  2026-09-19 and **not touched since** are in no delta file.

**Option 1: one-time catch-up layer from the full file (recommended).**

- Stream the current `galaxy.json.gz` (109.9 GiB) once.
- Keep systems whose newest `updateTime` (system, body or station) is after 2026-08-24 05:32. The
  V3 adapter already reads `updateTime` (`adapter.py:251, 306-307, 424`).
- Then apply the same change-only admission against the base.
- Publish the result as the first delta layer. Nightly `galaxy_1day` layers follow from the file's
  own date.
- **Disk (estimate):**
  - the 110 GiB file, which never needs to be on the production disk. It can be streamed from
    the Storage Box mount, or filtered off-production down to a few GB of "changed systems only";
  - plus a catch-up layer of ≈ 1–3 M admitted systems × 11–17 KB = **≈ 10–50 GB**;
  - plus WAL of about the same size.
- **Wall time (estimate):** streaming and filtering ≈ 2–4 h, then ≈ 1–3 h of builds.
- **Fits?** After purge P or the host clean-up, yes, easily.
  - Before them there is only ≈ 120 GB free with a 100 GB floor, so wait for P (it is
    sequenced after the go-live anyway).
- **Risk:** some changes may not bump `updateTime`, for example Spansh reprocessing old data.
  Step S1 measures this by hashing a random sample of systems that were *not* flagged against the
  base.

**Option 2: a full rebuild (option A).** ≈ 1.4–1.5 TB of new data and a 2.6–2.8 TB peak. **Does not
fit.**

**Option 3: use `galaxy_1month` only and accept the 26-day gap.** This would leave an unknown
number of systems stale. **Not recommended**, because option 1 is cheap.

**After the catch-up, is a second full copy ever needed?**

- **Not for freshness.** Nightly layers plus weekly compaction keep the data within about a day
  of Spansh.
- **A full copy (rebase) is still needed for:**
  - scorer, mechanics or adapter version changes, which need a full derived rebuild (that alone
    is ≈ 480 GB, though it can reuse freed space inside the derived tables);
  - changes to the canonical table layout;
  - handling whole-system deletions;
  - a cumulative layer that has grown past the threshold (estimated about 1–3 years at
    120–500 GB a year; needs measurement).
- So the disk upgrade becomes something to plan before the first rebase, not a blocker for
  freshness.
- A later design could even avoid full copies: partition the base by `id64` range and rebase one
  range at a time. That is a deep redesign, so it is noted only.

---

## 5. Station sightings: hourly `galaxy_stations` vs EDDN `Docked`, revised

**`galaxy_1day` already carries stations.**

- Stations come in the same galaxy schema, nested under systems and bodies.
- So the nightly layers keep station type, economies, services and body association current to
  within a day, **in canonical form, with ratings and Search consistent**.
- This removes the main reason for the separate `v3_observe` station store in the scoping plan.

**Hourly `galaxy_stations` (4.2 GiB, updated at least hourly).**

- Downloading it hourly would be ≈ 100 GiB a day of transfer and load on Spansh for intra-day
  freshness. **Not recommended now.**
- If faster station freshness is ever wanted, run it a few times a day through the **same delta
  machinery**, as station-only layers. The same change-only filter means only real station
  changes are admitted.

**EDDN `Docked` worker.**

- Its remaining value is **change timestamps finer than a day**, for the research engine's
  before/after colonisation studies.
- EDDN is also Spansh's own input, so it is not an independent source.
- **Defer it.** If kept, its scoping design (R5, R9–R11) still applies, but it is no longer step one.

**History.** Weekly compaction keeps only the latest version of each system. If the research engine
wants station history, have compaction write a slim, append-only **station-state history** table
(one row per real change) before dropping daily layers. This is the scoping report's T1 table,
fed from layers instead of EDDN.

**Revised recommendation.**

- Drop scoping steps R6/P4 (the separate Spansh station baseline). The catch-up layer plus nightly
  layers provide it.
- Keep the EDDN worker as an optional later step.

---

## 6. Side-by-side comparison

| | A: full generation | B1: change published data | **B2: nightly delta layers** | C (v1 hybrid): full on a cadence + sightings store |
|---|---|---|---|---|
| Freshness | days to months | ≈ 1 day | **≈ 1 day** | ratings months; stations ≈ 1 day |
| Work per refresh | ≈ 4.6 days machine (est.) | minutes | **≈ 0.5–1.5 h a night (est.)** | as A, plus small loads |
| One-time catch-up | is itself the catch-up | needs full file | **≈ 10–50 GB, 3–7 h (est.)** | as A |
| Disk peak | 2.6–2.8 TB: **does not fit** | small, but bloat | **few GB a night; ≈ 2× cumulative layer at compaction** | as A |
| Fits today's hardware? | No | on disk yes | **Yes, after purge P** | overlay yes, full no |
| Rollback | needs two full pairs | **none** | **remove a layer: exact and free** | as A |
| Fit with immutability / atomic publication | already designed | **breaks it** | **keeps it per layer; needs a written amendment for layer kind and union reads** | already designed |
| Ratings freeze | compatible | stale seals | **compatible (same scorer, per-system)** | compatible |
| New tooling | large | very large | **large: importer driver, delta kind, union views, nightly job** | large (A) + small |
| Risk | medium | **high** | **medium: union read path, nightly automation** | low / medium |

---

## 7. Recommendation: B2, nightly delta layers on an unchanged base

Use option A only as a rare rebase. Defer the EDDN worker.

**Why.**

- It is the only approach that makes ratings, Search, Archetype and Inspect fresh to within about
  a day on today's disk.
- It keeps every published row unchanged, with exact, free rollback.
- It reuses the existing per-system builders.

Legend for the step list:

- **[repo]** is a reviewed PR with no production access.
- **[OWNER GO]** needs your explicit go.
- **[OWNER DECISION]** is a question only you can answer.

### Stage 0: decisions

**D1 [OWNER DECISION].** Adopt B2 as the refresh direction (D8), with A only for rebases.
Record it in `docs/ROADMAP.md`, and amend `v3-search-spatial-derived-data-decision.md`:

- a delta-generation kind;
- completeness defined for the layer's own scope;
- union reads where the newest layer wins;
- rollback by removing a layer.

**D2 [OWNER DECISION].** Nightly governance: (a) a pre-approved scheduled job that publishes only
when all gates pass, or (b) a nightly build that waits for your "publish".

**D3 [OWNER DECISION].** Admission rules:

- ignore carrier-only changes?
- which fields count as "V3-relevant"? The default is everything V3 stores.

**D4 [OWNER DECISION].** Compaction cadence (default weekly), and the rebase threshold (for example
10% of systems or ≈ 150 GB).

**D5 [OWNER DECISION].** Spansh terms. Ask before **recurring** daily downloads (scoping D6).

**D6 [OWNER DECISION].** Keep a station-history table at compaction? Keep the EDDN worker on the
roadmap?

**D7 [OWNER DECISION].** Purge P's `VACUUM FULL` phases: still wanted?

- Delta layers need only tens of GB.
- In-table free space can be reused later by a rebase's derived rows.

### Stage 1: repo-only, safe now (touches no F2d-frozen file)

**S1 [repo].** A measurement probe that runs on a GitHub-hosted runner with no secrets and no
database. For 7 nights it downloads `galaxy_1day` and records:

- systems per file;
- bodies and stations per system;
- carrier-only share;
- record sizes;
- `updateTime` spread.

Run it once on `galaxy_1month` too. This replaces the scoping report's R1 for Spansh.

**S2 [repo].** Show the data date: "Galaxy data as of 2026-08-24" (later: "updated to <date>").
Shipping it needs a governed release **[OWNER GO for promotion]**.

**S3 [repo].** Design note `docs/development/v3-delta-layer-design.md`, covering:

- the delta kind and stack pointer;
- admission hashing;
- union views;
- compaction and rebase;
- the nightly gates.

**S4 [repo].** Land the parallel ratings validator (needed for any rebase, and it speeds up
layers).

**S5 [repo].** A governed importer driver around the frozen `v3_spansh` package, **not edited**. It
supports:

- (a) full files, which closes the missing-4C-driver gap;
- (b) delta files with change-only admission;
- (c) the catch-up filter by `updateTime` after the base date.

Test it on fixtures on disposable PostgreSQL 18. Include the journal-reconciliation phase from
`scripts/dev/build_journal_galaxy.py`.

### Stage 2: repo-only, after the go-live (9′) is recorded

**S6 [repo].** A migration, after `016`, that adds:

- the delta-generation kind (base reference, scope receipt);
- an ordered delta-stack pointer with an audit row;
- functions that publish and pop a layer atomically (canonical delta + derived delta + products);
- per-layer partitions or schemas for delta derived rows, so compaction is a cheap drop.

Tested on disposable PostgreSQL 18, including the deferred pointer checks.

**S7 [repo].** Retarget the ratings bridge, Search, Archetype and publish actions to an **explicit
delta (or candidate) generation**, and bake in the early-`ANALYZE`. This changes the F2d identity,
so it needs a new attested release.

**S8 [repo].** Union `v3_app` views and API reads where the newest layer wins. The Finder envelope
carries base identity plus delta sequence. Re-prove all 24 bounded plans plus the no-pick plans for
the union shape. Inspect shows "updated since snapshot".

**S9 [repo].** Compaction action: daily layers into a cumulative layer, published atomically, then
old layers dropped. Optionally it appends station history (D6).

**S10 [repo].** Nightly job and ops actions:

- download;
- verify (size, SHA, EOF);
- admit;
- import the layer;
- build;
- validate;
- WAL/backup/disk gates (reusing the purge's gate-2 checks);
- publish according to D2.

It must refuse while a purge event is open.

**S11 [repo + OWNER GO for the rehearsal dispatch].** A ≈ 1% disposable rehearsal:

- a synthetic base;
- a catch-up layer;
- 7 nightly layers;
- compaction;
- pop and rollback.

It measures disk, WAL and timings. The `purge-rehearsal` runner is reserved for the purge
rehearsal, so using it needs your go.

### Stage 3: production (every step needs your go; none runs while purge P is unresolved)

**P1 [OWNER GO].** Read-only checks:

- Storage Box quota and pgBackRest repository size;
- free space after P;
- a read-only admission dry-run of one `galaxy_1day` against the base, which gives the real
  admitted count.

**P2 [OWNER GO].** Run the migration workflow `plan`, then `apply`, for the S6 migration.

**P3 [OWNER GO].** Governed release carrying S7–S8, then record its attestation.

**P4 [OWNER GO].** One-time catch-up layer: stream and filter the full file, then import, build,
validate and publish. Verify the live app, and keep the layer removable.

**P5 [OWNER GO].** First nightly layers run manually for a week. Review each receipt (counts, time,
disk, WAL).

**P6 [OWNER GO].** Install the nightly schedule by a reviewed install action, as decided in D2.

**P7 [OWNER DECISION, later].** Rebase (option A) when D4's threshold or a scorer change requires
it. Plan the disk upgrade before then.

---

## 8. Open questions and limits

- **Real nightly counts** (systems in `galaxy_1day`, admitted after filtering, carrier share) are
  unmeasured. The 100k–500k / 30k–150k figures are estimates. S1 and P1 measure them.
- **Whether `updateTime` reliably flags every change since 2026-08-24** needs the sampled audit in
  S5 and P4.
- **Union-view plan bounds** under the F2d bounded-plan rules are a design expectation, not yet
  proved (S8).
- **The pyramid and density map stay on the base** until a rebase or an overlay pyramid. Discovered
  systems will show in Inspect and Finder before they move the density map.
- **Storage Box size and pgBackRest compression** are not recorded in the repo.
- **Spansh's rights for recurring bulk downloads** are not recorded (D5).
- **The published base's source run is labelled `FULL_REHEARSAL_NOT_PRODUCTION`**, and the driver
  that produced it is missing from the repo. S5 closes this gap.
- **The Archetype rate** (≈ 140 chunks/min) comes from the brief, not from a committed receipt.
