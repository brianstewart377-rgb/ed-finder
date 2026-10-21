# V3 live galaxy data: changes layers, weekly fold, EDDN and station sightings

**Status:** design for owner acceptance, 2026-10-21. Not implemented. Nothing
in this document authorizes a production step; every production step below is
marked **[OWNER GO]** and needs the owner's explicit go.
**Authority:** the owner decisions of 2026-10-21 recorded in
[`docs/ROADMAP.md`](../ROADMAP.md) and in the
[amendment of the derived-data decision](v3-search-spatial-derived-data-decision.md#amendment-2026-10-21-owner-changes-layers-and-weekly-fold).
That amendment says implementation must not start until this design is
accepted.
**Evidence (not authority):**
[`evidence/2026-10-21-v3-canonical-refresh-study.md`](evidence/2026-10-21-v3-canonical-refresh-study.md)
("the refresh study") and
[`evidence/2026-10-21-eddn-v3-scoping.md`](evidence/2026-10-21-eddn-v3-scoping.md)
("the scoping report"). File and line citations below come from those studies,
read at `main` `c396eb21`.

## Plain-language summary

1. Today V3 gets **no new galaxy data**. Its data is Spansh's file of 2026-08-24, loaded 2026-08-27, live since 2026-08-28.
2. **Every night** we download Spansh's "changed in the last 24 hours" file and build a small **changes layer** from it.
3. A layer holds full, checked copies of only the systems that really changed, with their ratings, Search and Archetype rows.
4. The app shows the big base data plus the layers. **The newest copy of a system wins.**
5. A bad night is undone by **switching that one layer off**. Nothing is deleted.
6. **Once a week** the week's layers are **folded** into the base in one controlled step. The old rows are kept in a **history table**, so the fold can be undone.
7. **Once, first:** a catch-up layer from the full Spansh file, because our copy is about two months old and the daily files only go back 32 days.
8. A **live EDDN listener** is built at the same time. It gives minutes-fresh sightings; Spansh stays the safety net.
9. A small **station sightings store** keeps station changes over time (Spansh first, then EDDN; no fleet carriers; no uploader IDs).
10. **Order:** Finder go-live first, then the purge, then this work. Every production step needs your go.

## 1. Owner decisions (2026-10-21)

These are recorded exactly as decided and are the authority for this design.

1. **Today:** V3 production receives no new galaxy data (no EDDN listener, no
   Spansh refresh). Canonical data is Spansh `galaxy.json` of 2026-08-24,
   imported 2026-08-27, published 2026-08-28.
2. **Nightly source:** Spansh `galaxy_1day.json.gz`, which is full-detail:
   bodies and stations for every system changed in the last 24 hours. Verified
   by the owner on spansh.co.uk/dumps on 2026-10-21: `galaxy_1day` 1.1 GiB,
   `galaxy_7days` 2.8 GiB, `galaxy_1month` 5.1 GiB (32 days),
   `galaxy_stations` 4.2 GiB hourly including fleet carriers, `galaxy.json`
   109.9 GiB. The `systems_*` files are system-only.
3. **Middle path:** nightly changes are published as small, separately
   validated changes layers (base ∪ layers, newest wins; a bad night is undone
   by switching its layer off). Once a week the week's layers are folded into
   the base canonical data in one controlled, undoable step, with the replaced
   row versions kept in a history table so the fold can be reversed. This
   relaxes "published data never changes" to "the base changes only through
   the weekly fold, in one undoable, receipted step". A full new canonical
   generation is still used when scoring rules or table layout change.
4. **One-time catch-up first:** the snapshot is about 58 days old and
   `galaxy_1month` covers only 32 days, so the full `galaxy.json` is filtered
   once to systems updated since 2026-08-24. This runs after the governed
   purge.
5. **Live EDDN listener** is built at the same time as nightly Spansh, with
   Spansh as the safety net. EDDN carries no colonisation events (verified from
   the EDDN schema README); its live value is minutes-freshness of systems,
   bodies and stations (`Docked` `StationEconomies` / `StationServices`).
6. **Station sightings store:** Spansh first, then EDDN (both built
   concurrently, per decision 5); after the purge; fleet carriers excluded;
   change-only rows kept indefinitely (alert at 1 GB, review at 5 GB); a
   restricted NOLOGIN role reached by `SET ROLE` on the existing credentials;
   no uploader IDs ever stored; no need to ask Spansh before scheduled
   downloads (owner decision) — at most daily, off-peak, using delta files
   where Spansh offers them; journal-upload observations stay separate in
   `v3_private`.
7. **Ordering:** Finder go-live (step 9′ publish) first; the F2d operator-code
   files (`deploy/v3-production/f2d-operator-code.txt`) are frozen until then;
   then the governed purge P; then the live-data work. Every production step
   needs the owner's explicit go.
8. **Not decided:** whether nightly layers publish automatically or wait for
   the owner's manual approval. The recommendation is manual approval for the
   first weeks, then automatic.

Where these decisions differ from the refresh study's recommendation, the
decisions win. The study recommended a base that never changes (weekly
compaction into one cumulative layer), deferring EDDN, dropping the separate
station store and asking Spansh first. The owner chose the weekly fold, EDDN
now, the station store, and no prior request to Spansh.

## 2. Data sources

| Source | What it gives | How often | Used for |
|---|---|---|---|
| Spansh `galaxy_1day.json.gz` (1.1 GiB) | Every system with any change in the last 24 h, in the full galaxy schema (bodies and stations) | Once a night, off-peak | Nightly changes layer; Spansh station sightings |
| Spansh `galaxy_7days` (2.8 GiB) / `galaxy_1month` (5.1 GiB, 32 days) | The same, over a longer window | Only after missed nights | Recovery of up to 32 missed days with one download |
| Spansh `galaxy.json.gz` (109.9 GiB) | The whole galaxy | **Once**, for the catch-up | Catch-up layer; Spansh station baseline |
| EDDN relay (`journal/1`) | Live player sightings: `Docked`, `FSDJump`/`Location`, `Scan`, `SAASignalsFound` | Continuous | Station sightings store; minutes-fresh sightings shown as observations |
| Spansh `galaxy_stations` (4.2 GiB, hourly) | Stations including fleet carriers | **Not used** | Hourly downloads would be ≈ 100 GiB a day and break "at most daily" |

Rules for every Spansh download (owner decision 6): at most daily, off-peak,
delta files where offered; record the artifact's size, SHA-256 and Spansh
effective date in `v3_source.source_artifact`; verify end-of-file before use.
The full file is fetched once for the catch-up and again only for a full new
generation.

EDDN facts (scoping report B0): the journal schema lists no `Colonisation*`
event, so EDDN gives only indirect colonisation evidence (construction-depot
station types, changing station economies and services). `Docked` carries no
body ID, so EDDN cannot place a station on a body; Spansh can where it nests
the station under a body.

## 3. The changes-layer model

### 3.1 What a layer is

- **Base:** the published canonical generation `phase4c_full_20260827_r5`,
  its published derived generation `ratings_v4_prod_p4_parallel_v1`, and the
  published Finder products on it.
- **Layer:** one night's (or the catch-up's) admitted systems, each as a
  **complete replacement record** — the system row and *all* its bodies,
  rings, signals, compositions, parent evidence and stations — plus that
  layer's own Ratings V4, Search and Archetype rows for exactly those systems.
  A body or station that vanished from a system is handled correctly, because
  the whole system is replaced.
- **Keying:** layers replace whole systems, keyed by system `id64`. Inside a
  system, rows keep the canonical body and station keys of the base model.
- **Layer record:** layer id, sequence number, kind (`CATCH_UP`, `NIGHTLY`,
  `RECOVERY`), the Spansh artifact (size, SHA-256, effective date), the source
  run, admitted-system count, per-relation row counts, content seals,
  validation receipt, the code identity that built it, and a state:
  `BUILDING → VALIDATING → READY → ACTIVE`, then `DISABLED`, `FOLDED` or
  `FAILED`.

### 3.2 Change-only admission

A system from the Spansh file enters a layer only if its **V3-relevant
content** differs from the version the app shows now (newest active layer,
otherwise base).

- The comparison is a SHA-256 over the normalised V3 rows the importer would
  write for that system: bodies, rings, signals and fixed stations.
- Faction, population and influence churn is ignored, because V3 canonical
  data has no such columns (refresh study 1.3 rule 13).
- The "currently shown" hash is computed on demand for the systems in the
  file, not stored for all 198.5 M systems.
- Whole-system deletions in Spansh cannot be seen in a delta file. They are
  handled only by a full new generation.
- **Open (D-C below):** whether carrier-only changes are ignored. The
  recommendation is yes, matching the station store's carrier exclusion.

### 3.3 Read path: newest active layer wins

- A small **winner index** maps each `id64` that appears in any active layer
  to the newest active layer holding it. It is rewritten for the affected
  `id64`s in the same transaction that activates, disables or folds a layer.
- **Inspect** looks the system up in the winner index first; if present it
  reads that layer's rows, otherwise the base.
- **Finder views** (`v3_app.system_search`, `v3_app.system_archetype`, today
  defined by migration `015`) become **union views**: base rows whose `id64`
  is not in the winner index, plus the winning layer rows. The superseded set
  is at most the systems in active layers, which the weekly fold keeps small.
- **Map density pyramid** stays on the base pyramid (keyed to the canonical
  generation, migration `012`). Density changes by a fraction of a percent a
  month (refresh study, estimate). Rebuilding it on the folded base is a
  separate, later spatial publication (open item D-F).
- **Responses** report the base identity **plus** the fold sequence and the
  newest active layer sequence, so every answer says exactly what data it
  came from. Inspect can say "updated since snapshot" for systems served from
  a layer or changed by a fold.

### 3.4 Derived rows for changed systems only

Ratings V4 raw scores are absolute, per-system values, and Search and
Archetype are per-system projections with fixed coefficients (refresh study
1.3 rule 5). So building Ratings, Search and Archetype for **only** a layer's
systems gives exactly the rows a full rebuild would give for them. The
exceptions are galaxy-wide aggregates — the spatial pyramid, clusters (not
built yet) and the capacity gate's tier fractions — which stay on the base.

The existing Search and Archetype builders already iterate "whatever systems
one derived generation's ratings chunks hold" (refresh study 1.3 rule 4). What
they lack is targeting: the generation keys are hard-coded, and the ratings
bridge accepts only the published, complete-snapshot canonical generation
(1.3 rule 3; `scripts/ratings_v4/canonical_stream.py:220-252`). Section 9
lists the changes.

### 3.5 Where layer rows live

Layer rows must never be written into the shared, published `v3_derived`
tables, because removing them later would need `DELETE`s that the
insert-only triggers forbid and that leave bloat. The proposed shape, to be
confirmed in the tooling review:

- one new schema for layer data, with tables of the same columns as the base
  canonical and derived relations plus a `layer_id`, **partitioned by
  `layer_id`**;
- dropping a folded or failed layer is `DETACH` + `DROP` of its partitions:
  cheap, no `VACUUM FULL`, no long locks on the base.

### 3.6 Publishing and switching off a layer

- **Publish** (one transaction): check the layer is `READY` and its
  validation receipt and seals match; check no purge event is unresolved and
  no fold is running; set it `ACTIVE`; update the winner index for its
  `id64`s; run the bounded-plan probe on the union views (section 7) on the
  same connection before commit; write the publication receipt.
- **Switch off** (one transaction): set the layer `DISABLED`; recompute the
  winner index for its `id64`s (each falls back to the next-newest active
  layer or to the base); probe; receipt. No rows are deleted. A disabled
  layer can be re-enabled the same way, or dropped later.
- Switching off a middle layer is safe: every layer holds complete records,
  so the systems simply show an older, still-consistent version.

### 3.7 The weekly fold

The fold moves the week's active layers into the base so the overlay stays
small. It is one governed operation with one receipt, and readers see one
change, at one commit.

1. **Prepare (read-only):** pick the layers to fold (all `ACTIVE` layers up to
   a chosen sequence), compute the newest version of each system across them,
   and write a fold manifest (fold id, layer ids and seals, the `id64` list,
   expected row counts). Refuse if any purge event is unresolved or any
   nightly job is running.
2. **Rewrite the base under the layers (chunked, resumable).** For each chunk
   of `id64`s: copy the current base rows for those systems — canonical and
   derived — into the **history tables**, tagged with the fold id; record
   which `id64`s had no base row (new systems); delete those base rows; insert
   the layer's rows. While this runs the layers are still `ACTIVE`, so readers
   keep seeing the layer copy, which is the same content: **nothing visible
   changes**.
3. **Tidy:** `VACUUM (ANALYZE)` the touched base tables, so statistics are
   fresh and the visibility map is set (the step 9′ proof requires
   `Heap Fetches: 0`).
4. **Switch (one transaction):** mark the folded layers `FOLDED`, remove their
   `id64`s from the winner index, advance the base **fold sequence**, run the
   bounded-plan probe on the same connection before commit, and write the
   **fold receipt**: layers folded, systems changed and added, per-relation
   row counts, history rows kept, and a seal of the base before and after.
5. **Later:** drop the folded layers' partitions (cheap) once the fold has
   been checked.

**Undo a fold** (folds are undone newest first): in one transaction, delete
the base rows the fold inserted, re-insert that fold's history rows, delete
the systems the fold added, mark the fold `REVERSED`, write the undo receipt;
then `VACUUM (ANALYZE)` and run the plan probe. MVCC makes the transaction
atomic for readers. If the rehearsal shows that transaction is too long, the
alternative is to expose the fold's history partition as a temporary layer
first (instant), then restore the base underneath it, as in step 2. Layers
published after the fold stay valid, because they hold complete records.

**Write capability.** The base relations refuse writes today (derived triggers
in `003:196-214`; insert-only products in `006:130-204`; canonical immutability
by convention, `001:1022-1023`). The fold needs a dedicated, narrow capability
in a new migration, modelled on migration `016`'s payload-only purge
capability: usable only by the fold operation, only for the `id64`s in the
active fold manifest, and only while that fold's ledger row is open. The fold
does **not** use `shared_contracts.bulk_update_helper.bulk_update_replica_mode`:
the triggers that check the capability must stay active. Following
[`bulk-database-write-safety.md`](bulk-database-write-safety.md), the fold code
carries an adjacent comment saying so. The design also proposes adding the
same guard triggers to the canonical generation relations, so that the fold
is the only path that can write them, as the amendment requires.

**History retention (open, D-B):** recommendation: keep the history of the
last 4 folds (about a month), partitioned by fold id so expiry is a cheap
`DROP`.

**Bloat:** each fold leaves dead tuples about the size of the rows it
replaced. Ordinary `VACUUM` makes that space reusable by the next fold, so
steady-state bloat is about one week's replaced rows (estimate). No
`VACUUM FULL` is needed. This is the opposite of V2's continuous update churn
(`docs/operations/database-bloat-incident-2026-08-20.md`).

### 3.8 The one-time catch-up

- Stream the current `galaxy.json.gz` once; keep systems whose newest
  `updateTime` (system, body or station) is after 2026-08-24 05:32:35 UTC (the
  base file's Spansh effective time). The V3 adapter already reads
  `updateTime`.
- Apply the same change-only admission and publish the result as the first
  layer (kind `CATCH_UP`). Nightly layers follow from the catch-up file's own
  date; a gap is closed with `galaxy_7days` or `galaxy_1month`.
- The 110 GiB file need not sit on the production disk: it can be streamed, or
  filtered off-production down to the changed systems.
- Risk: some changes may not bump `updateTime`. The catch-up run hashes a
  random sample of *unflagged* systems against the base and reports the
  mismatch rate in its receipt.
- It runs after the purge P (owner decision 4); before P there is only
  ≈ 120 GB free over a 100 GB floor (refresh study, estimate).

### 3.9 Journal enrichment

Shared journal facts are applied only to a never-published candidate, and a
candidate that omits an eligible observation is refused
(`docs/development/journal-commander-contributions.md:80-93`). A layer is a
candidate until it is published, so enrichment applies to each layer before
publication; the fold only moves already-published layer rows. The tooling
review must confirm the enrichment guard accepts the layer kind.

### 3.10 When a full new generation is still needed

- scoring rules, mechanics or the adapter change (owner decision 3: a full new
  generation; at minimum a full derived rebuild);
- the canonical table layout changes;
- handling systems that Spansh has deleted.

A full generation needs ≈ 2.6–2.8 TB at peak and does not fit the 1.95 TB
volume (refresh study section 2, estimate), so the disk upgrade must be planned
before the first one. Layers and folds do not need it.

## 4. EDDN live listener

Design from the scoping report (B1, B2, T2), built at the same time as the
nightly Spansh work (owner decision 5):

- **One dedicated worker service**, as the locked stack decision requires
  (`docs/development/v3-application-stack-decision.md:115, 118, 226`), run
  from the same backend image with a different command. `pyzmq` is already a
  dependency.
- Deployed through the production compose authority and deployer as
  `eddn-blue`/`eddn-green`; only the active slot's worker runs; it starts
  after the public smoke passes and stops on rollback. This changes
  `deploy/v3-production/compose.yml`, `scripts/operator/v3_production_deploy.py`,
  `deploy/v3-production/target-authority.json` and the release runbook.
- Writes **only** the `v3_observe` schema, through the existing application
  credentials with `SET ROLE` to a NOLOGIN least-privilege role;
  `lock_timeout` 2 s, `statement_timeout` 15 s; a named `application_name`.
  It never writes `v3_gen_*`, `v3_derived`, `v3_app` or layers.
- **Bounds:** accept only `https://eddn.edcd.io/schemas/journal/1`; Live game
  versions only; capped message size and list lengths; finite proportions;
  timestamp window; bounded in-memory buffer that drops oldest and counts
  drops; batched parameterised inserts.
- **Failure handling:** the #864 breaker pattern (exit after N consecutive
  flush failures; Docker restarts it); hourly checkpoint rows; a heartbeat
  file for the container health check; the host health check extended to
  watch it.
- **Refuses to start while a purge event is unresolved** (read-only query of
  the purge ledger through the shared library). Because the purge quiesces only
  `api-*` writers today, the worker must be stopped for any purge until the
  purge code learns to quiesce it (a frozen-file change; section 9).
- **What users get:** the live value is minutes-fresh sightings. Station
  state from `Docked` goes to the station sightings store (section 5).
  **Proposed, for acceptance (D-D):** change-only system and body sightings
  from `FSDJump`/`Location`/`Scan` in `v3_observe` too, shown in Inspect as
  labelled observations ("seen live at …"). In the first version EDDN never
  writes canonical data or layers: ratings, Search and Archetype change only
  through the Spansh layers, which already include EDDN-fed data a day later.
  That is what "Spansh is the safety net" means here.
- The V2 listener (`apps/eddn/`) and the API-lifespan simulation ingest are not
  reused: both write V2 relations. The simulation ingest stays disabled in
  production.

## 5. Station sightings store (`v3_observe`)

- **Schema:** a new `v3_observe` schema for public-source, non-canonical
  observations, using the existing `v3_source` ledger (`source`,
  `source_rights_policy`, `source_run` with `BULK_SNAPSHOT`/`DELTA`/
  `STREAM_WINDOW`, `source_checkpoint`). Sketch: scoping report appendix T1.
- **One append-only table** of station states. A row is inserted only when a
  station's research-relevant state hash is new for that source
  (`ON CONFLICT DO NOTHING`); no hot-row updates.
- **State hash covers:** station type, sorted economies with rounded
  proportions, sorted services, body, landing pads. It leaves out faction,
  government, allegiance and timestamps.
- **Fleet carriers excluded** (the adapter already identifies them).
- **Spansh first:** the station baseline comes from the catch-up pass over the
  full file, then nightly from the station content of each `galaxy_1day` (no
  extra download). Spansh gives body association where it nests the station
  under a body.
- **Then EDDN:** `Docked` rows from the live worker, told apart by
  `source_id`. Both are built concurrently; in production the Spansh baseline
  is loaded before the EDDN worker is enabled.
- **Retention:** change-only rows kept indefinitely; alert at 1 GB, review at
  5 GB; hourly checkpoint rows may be trimmed after 90 days (scoping
  recommendation).
- **Role:** a NOLOGIN role (`INSERT`/`SELECT` on `v3_observe`, and only its own
  `v3_source` run/checkpoint rows) reached by `SET ROLE` on the existing
  credentials. `edfinder_v3` is a superuser, so this is a guardrail against
  mistakes, not a security boundary.
- **Rights:** recorded as internal use, not redistributed. No request to Spansh
  is needed before scheduled downloads (owner decision 6).
- **Journal uploads stay separate:** commanders' own journal station
  observations are personal data and live in `v3_private` with a
  personal-data registry entry, never in `v3_observe`.

## 6. Privacy

- **Never read, store or log EDDN `header.uploaderID`.** Persist only
  `softwareName`, `softwareVersion`, `gatewayTimestamp`, `gameversion` and
  `gamebuild` from the header.
- Store only allowlisted message keys; drop `Taxi` and `Multicrew`; never keep
  the raw message.
- EDDN data is community data and is never used for player tracking.
- `v3_observe` holds no personal data, so it needs no entry in
  `sql/v3/governance/personal_data_registry.json`. Journal-upload
  observations do, and stay in `v3_private`.

## 7. Finder, ratings and attestation requirements

From the refresh study (3.3):

- **Ratings V4.0 freeze: compatible.** Same scorer `4.0.0` and mechanics
  `v4-mechanics-2026-09` on new observations, which the freeze allows
  (`docs/development/ratings-v4-freeze/README.md:64-66`). **Open (D-E):** the
  new importer/layer driver identity enters each layer's lineage; treat it
  like the PR #647 adapter repin?
- **Finder envelopes** carry base identity plus fold sequence and layer
  sequence. The ranking identity (coefficients) does not change.
- **Union views** replace the `015` views, and the step 9′ bounded-plan proof —
  all 24 archetype/floor pairs plus both no-pick requests, `Heap Fetches: 0` —
  must be **re-proved for the union shape**, at every layer publication,
  layer switch-off and fold. A base index scan with an anti-join on the
  superseded set, merged with a small layer index scan, is expected to be
  boundable because the weekly fold keeps the superseded set small; that is a
  design expectation, not yet proved.
- **Seals:** the base's original seals stay valid as the starting point; the
  current base is verified as "original seal + the ordered fold receipts".
  The F2d complete-read receipt and capacity-gate inputs remain historical
  build evidence; a future full build re-measures them.
- **New attested release:** all of this ships after go-live in a new release
  whose attestation records the new operator-code identity.
- **Fences:** the nightly job, layer publish/switch-off, the fold and its undo
  are governed mutators. Each refuses while a purge event is unresolved
  (`docs/ROADMAP.md`, purge fences), and they refuse while another of them is
  running.

## 8. Volumes, disk, WAL and backup

All figures are **estimates** from the refresh study unless marked
"this design's arithmetic" (derived from the study's figures). Steps L1 and
R1 below measure the real numbers.

| Item | Estimate |
|---|---|
| Systems in one `galaxy_1day` file | ≈ 100k–500k (upper bound ≈ 2 M) |
| Admitted per night after change-only filtering | ≈ 30k–150k |
| Size per admitted system (canonical + derived, heavier than average) | ≈ 11–17 KB |
| One nightly layer | ≈ 1.6–2.5 GB |
| One week of layers before the fold | ≈ 10–18 GB |
| Nightly work | ≈ 0.5–1.5 h (≈ 3–5 h at the 2 M upper bound) |
| Catch-up layer | ≈ 1–3 M systems, ≈ 10–50 GB; ≈ 3–7 h |
| History kept per fold | ≈ 2–10 GB (this design's arithmetic: ≈ 210k–560k distinct systems a week × 11–17 KB) |
| Dead space after a fold, reused by the next | about the same as the history kept |
| EDDN station rows stored (change-only) | under 1 GB a year (scoping report) |
| Spansh station baseline | at most ≈ 830k stations × a few hundred bytes, ≈ 0.2–0.4 GB (this design's arithmetic) |

**Disk.** Free space is about 120 GB after both Finder builds and about
500–520 GB after the purge P, if its rewrites return the modelled ≈ 400 GB
(refresh study 1.1). Steady state for this design (estimate): one week of
layers (≤ 18 GB) + 4 folds of history (≤ 40 GB) + one fold's reusable dead
space (≤ 10 GB) + the catch-up's one-off history (≤ 50 GB until it expires)
+ the station store (< 2 GB): under about 120 GB. This fits after P, not
before it, which is one reason for the ordering. Every job checks free space
against the 100 GB floor that the purge design keeps for WAL before it writes.

**WAL and backup.**

- WAL is archived to the Storage Box; `max_wal_size` is 32 GB and
  `wal_compression` is zstd (`docs/operations/v3-postgres-server-settings.md`).
- A nightly layer writes WAL of about its own size (a few GB).
- A fold writes the history copy, the deletes and the inserts: roughly 3× the
  folded rows plus index WAL, so ≈ 10–40 GB a week (this design's arithmetic;
  the rehearsal measures it). The undo costs about the same.
- pgBackRest keeps 2 full and 4 differential backups. Weekly folds make each
  differential larger by about the fold's size.
- **The Storage Box size and pgBackRest repository size are not recorded in
  the repo**, and no restore has been rehearsed. Step L1 records them before
  any write. Folds and nightly jobs are scheduled away from the backup timers.

## 9. Tools that do not exist yet

From the refresh study, plus what this design adds:

1. **Full-galaxy importer in repo form.** A governed driver around the
   recovered `v3_spansh` package, **without editing it** (its files are
   checksum-bound to canonical source recovery). It must handle full files,
   delta files with change-only admission, and the catch-up `updateTime`
   filter. The driver that produced today's base is not in the repo.
2. **Fast ratings checker.** The parallel ratings validator exists only in a
   `/var/tmp` bundle on the host; the repo's serial validator takes ≈ 90 h for
   the galaxy.
3. **Builders that accept an unpublished or layer generation.** The ratings
   bridge, Search, Archetype and publish actions are pinned to the published
   generation `ratings_v4_prod_p4_parallel_v1` or to the published canonical
   generation; they need an explicit target and an early `ANALYZE`.
4. **One-step pointer switch.** The database functions allow every pointer to
   move in one transaction, but no action does it; layers need the same for
   activate, switch-off and fold.
5. **Cheap delete of old copies.** Old layers, history and generations must be
   removable without `DELETE` + `VACUUM FULL` on shared tables (partitions per
   layer and per fold).
6. Added by this design: the layer and history migrations, union views and API
   reads, the fold/undo operation, the nightly job and its schedule install
   action, the EDDN worker and its deploy authority, the station store and its
   Spansh loader, and the measurement probe.

## 10. Ordered steps

Legend: **[repo]** = a reviewed pull request with no production access.
**[repo, after go-live]** = touches a file listed in
`deploy/v3-production/f2d-operator-code.txt` (or an authority file that goes
with it) and must wait until step 9′ is recorded; it then ships in a new
attested release. **[OWNER GO]** = a production step that needs the owner's
explicit go. Nothing in production starts before go-live 9′ **and** the
completed purge P.

### 10.1 Repo-only, safe before go-live (no frozen file)

- **R0 [repo].** This design and the decision amendment (this change). Owner
  acceptance of this design is recorded in `docs/ROADMAP.md` before R2 onward.
- **R1 [repo].** Measurement probe on a GitHub-hosted runner with no secrets
  and no database: for 7 nights download `galaxy_1day` (once a night,
  off-peak) and record systems per file, bodies and stations per system,
  carrier-only share, record sizes and `updateTime` spread; run once on
  `galaxy_1month`; and listen to the EDDN relay for N hours counting `Docked`
  per hour, carrier share, Live/Legacy split, distinct `MarketID`s and the
  change-hash rate, storing nothing.
- **R2 [repo].** Data-date label in the app ("Galaxy data as of 2026-08-24",
  later "updated to …"). A visual change: visual validation, then a governed
  release **[OWNER GO for promotion]**.
- **R3 [repo].** Land the parallel ratings validator in the repo (tool 2).
- **R4 [repo].** Importer driver (tool 1) with change-only admission hashing
  and the catch-up filter, tested on fixtures on disposable PostgreSQL 18;
  `apps/importer/src/v3_spansh/*` is imported, not edited.
- **R5 [repo].** Draft migrations under `sql/v3/proposals/` only, **not**
  registered: layer registry, partitioned layer tables, winner index, union
  view definitions, fold ledger, history tables, fold capability and guard
  triggers; and the `v3_observe` schema with its NOLOGIN role and `v3_source`
  seed rows. Tested on disposable PostgreSQL 18, including activate,
  switch-off, fold and undo.
- **R6 [repo].** Pure normalisers (EDDN envelope → observation rows; Spansh
  system record → station rows) and the EDDN worker module, default off,
  writing `v3_observe` only, with the purge-ledger refusal, breaker,
  checkpoints, heartbeat and bulk-write-safety comment; tested against a fake
  ZMQ publisher and a disposable database.
- **R7 [repo].** Spansh station-store loader CLI (streaming, bounded memory,
  artifact SHA-256, change-only inserts, resumable), tested on fixtures.

### 10.2 Repo-only, after go-live 9′ is recorded (frozen files)

- **A1 [repo, after go-live].** Register the new migrations: move them to
  `sql/v3/migrations/`, append to `sql/v3/migration-manifest.txt` (frozen),
  add the schema transition and compatibility attestation in
  `deploy/v3-production/target-authority.json`, pin the schema identity. This
  changes the F2d operator-code identity, so a new release must be promoted
  and recorded before any further F2d action.
- **A2 [repo, after go-live].** Retarget the builders to an explicit layer or
  unpublished generation and add the early `ANALYZE` (tool 3):
  `scripts/v3_system_search.py`, `scripts/v3_system_search_parallel.py`,
  `scripts/v3_system_archetype.py`,
  `scripts/operator/actions/v3-system-search-f1.sh`,
  `scripts/operator/actions/v3-system-archetype.sh`,
  `scripts/operator/actions/v3-publish-derived-products.sh` and
  `scripts/v3_publish_derived_products.py` (all frozen), plus the ratings
  bridge `scripts/ratings_v4/canonical_stream.py` (not frozen, but it ships
  with them).
- **A3 [repo, after go-live].** Union views and API reads, Finder envelope
  fields, Inspect "updated since snapshot", and the bounded-plan probe for the
  union shape (`scripts/v3_archetype_plan_probe.py` and
  `scripts/v3_plan_probe_statements.py` are frozen). Re-prove all 24 pairs
  plus both no-pick requests on disposable PostgreSQL 18 at representative
  layer sizes.
- **A4 [repo, after go-live].** Purge awareness: the purge quiesces the
  `eddn-*` worker and refuses while a nightly job or fold is open
  (`scripts/operator/lib/v3_purge_delete.py`, `v3_purge_state.py`,
  `v3-purge-state.sh` are frozen).
- **A5 [repo, after go-live].** Ops actions: catch-up; nightly layer
  (download, verify size/SHA-256/end-of-file, admit, import, build, validate,
  disk/WAL/backup gates, then publish or wait for approval per D-A); layer
  switch-off; fold; fold undo; layer and history drop; Spansh station load;
  the schedule install action (a reviewed host timer, like the backup timers).
- **A6 [repo, after go-live].** EDDN worker in the deploy authority:
  `deploy/v3-production/compose.yml`, `scripts/operator/v3_production_deploy.py`,
  `deploy/v3-production/target-authority.json`, the release runbook, and the
  host health check.
- **A7 [repo + OWNER GO for the dispatch].** A ≈ 1% disposable rehearsal:
  synthetic base, catch-up layer, 7 nightly layers, one switch-off, one fold,
  one undo, a fake EDDN feed; it measures disk, WAL and timings. The
  `purge-rehearsal` runner is reserved for the purge rehearsal, so using it
  needs the owner's go.

### 10.3 Production (each step [OWNER GO]; none before 9′ and the completed P)

- **L1 [OWNER GO].** Read-only checks: Storage Box quota and pgBackRest
  repository size; free space after P; a read-only admission dry run of one
  `galaxy_1day` against the base (the real admitted count).
- **L2 [OWNER GO].** Migration workflow `plan`, review, then `apply` for the
  A1 migrations.
- **L3 [OWNER GO].** Governed release carrying A2–A6 (EDDN worker may ship
  disabled); record its attestation and the new operator-code identity.
- **L4 [OWNER GO].** Catch-up: stream and filter the full file, import, build,
  validate, publish as the first layer; verify the live app; the layer stays
  switch-off-able.
- **L5 [OWNER GO].** Spansh station baseline load into `v3_observe`; then
  enable the EDDN worker; review its numbers after 24–72 h (rows a day, size,
  drops, failures).
- **L6 [OWNER GO].** Nightly layers, each published only on the owner's
  approval for the first weeks; review each receipt (counts, time, disk,
  WAL).
- **L7 [OWNER GO].** First weekly fold (it also folds the catch-up layer),
  with its receipt; confirm the undo path works on the rehearsal before this
  step.
- **L8 [OWNER GO].** Install the nightly schedule; switch to automatic
  publication only if the owner decides so (D-A).
- **Later [OWNER DECISION].** A full new generation when rules or the table
  layout change; plan the disk upgrade before it.

## 11. Decisions still open (for acceptance of this design)

- **D-A.** Nightly publication: automatic, or the owner's manual approval?
  Recommendation: manual for the first weeks, then automatic. The same
  question applies to the weekly fold; recommendation: manual for the first
  folds.
- **D-B.** History retention: recommendation, the last 4 folds.
- **D-C.** Ignore carrier-only changes in layer admission? Recommendation: yes.
- **D-D.** EDDN system and body sightings in `v3_observe`, shown in Inspect as
  labelled observations, and never written to canonical data or layers in the
  first version? Recommendation: yes.
- **D-E.** Treat the layer driver identity in ratings lineage like the PR #647
  adapter repin?
- **D-F.** When to rebuild the map density pyramid on the folded base.
- **D-G.** Layer storage shape (section 3.5): partitioned layer tables, or an
  alternative found in the tooling review.

## 12. Limits of this design

- Every nightly and catch-up volume is an estimate until R1 and L1 measure it.
- Whether `updateTime` flags every change since 2026-08-24 is unknown until the
  catch-up's sampled check runs.
- Bounded plans for the union views are expected, not proved (A3).
- The Archetype build rate used in the study comes from a brief, not a
  committed receipt.
- The base's source run is labelled `FULL_REHEARSAL_NOT_PRODUCTION` and the
  driver that produced it is not in the repo; R4 closes that gap.
