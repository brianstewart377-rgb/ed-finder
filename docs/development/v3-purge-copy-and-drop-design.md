# V3 purge by copy-and-drop (option B)

**Status: Accepted by the owner on 2026-10-24** with the answers recorded in
§8. Acceptance authorizes building and rehearsing it; it grants no production
authority. Nothing runs in production until migration `019`, the operator
modes and a passing 1% rehearsal exist, and each production dispatch still needs
its own owner approval. Until then the
[governed purge design](v3-governed-derived-purge-design.md) and its
[runbook](../operations/v3-governed-derived-purge.md) remain the recorded
authority for the parts B reuses (§4).

A/B/C are the owner's 2026-10-24 options: **A** leave the old data in place
(chosen for now), **B** copy the live rows to fresh tables and drop the old
tables whole (this document), **C** add disk (priced separately). They are not
the purge design's approaches A–D. Option B is that design's approach C (shadow
tables), done one relation at a time without partitioning.

## 0. Why

The 1% rehearsal (run 40074011789,
[receipt](../operations/evidence/2026-10-24-v3-derived-purge-rehearsal-receipt-run-40074011789.json),
`content_sha256` `94a522dd…73dd`, gate 10 passed) projects purge P at
production scale:

| Relation | Delete time | Rewrite peak ×1.5 | Notes |
|---|---:|---:|---|
| `system_search` | ~12.6 h | 167.8 GB | survivor rewrite ~15,240 s (4.2 h) under `ACCESS EXCLUSIVE` |
| `economy_opportunity` | ~43 h | 224.8 GB | 740 M rows at ~4,795 rows/s |
| `body_mechanics` | ~52 h | 216.9 GB | 577.7 M rows at ~3,087 rows/s |
| `system_rating_vector` | ~39 h | 134.5 GB | 198.5 M + p4 rows at ~1,397 rows/s |

At ≤ 1,800 s per delete dispatch
(`scripts/operator/v3_production_purge_workflow.py:76-80`), that is about 300
approvals. The Search rewrite also has three problems:

- it takes the live Finder offline for about 4.2 h;
- it exceeds the 7,200 s rewrite cap
  (`.github/workflows/v3-production-derived-purge.yml:91-94`);
- it needs 267.8 GB free (the 100 GB floor included), against an estimated
  ~105 GB.

## 1. Mechanism (per relation)

### 1.1 New table: catalog-derived, then proven equal

- **Replaying migration DDL** is unsafe because the live shape was built up over
  several migrations. `system_search` came from `004` (`004:22-54`). Then `006`
  replaced its triggers (`006:127-206`), `010` added 18 columns and 18
  `NOT VALID` checks (`010:17-75`), and `016` replaced `product_delete`
  (`016:379-382`).
- **`LIKE … INCLUDING ALL`** copies, exactly as live: the column order, types,
  `NOT NULL` (named constraints in PG 18), named `CHECK`s, defaults, storage,
  statistics and comments.
- It does **not** copy FKs, triggers, grants, reloptions or the owner.
- It also auto-names indexes, while the F2d probe requires exact names
  (`scripts/v3_archetype_plan_probe.py:28-31,286-287`).

**Proposal:**

1. `CREATE TABLE v3_purge_staging.<rel> (LIKE v3_derived.<rel> INCLUDING ALL
   EXCLUDING INDEXES)`.
2. A fixed definer function (relation taken only from 016's enum,
   `016:151-161`) generates indexes, FKs, triggers, reloptions and grants from
   the live catalog (`pg_get_indexdef`/`…constraintdef`/`…triggerdef`). Indexes
   keep their **canonical names**: index names are unique per schema, and the
   staging table sits in a separate schema.
3. Before any swap, a **catalog fingerprint** must equal the live table's. It
   covers columns, constraints (definition, deferrability, validity), indexes
   and predicates, triggers, reloptions, ACL, owner and comments. One difference
   is allowed: a constraint `NOT VALID` live may be valid on the copy.
4. A CI test proves that the generator reproduces a fresh 001–016 database.

Facts the generator honours:

- No generated or identity columns exist, so no sequences move.
- All FKs are `DEFERRABLE INITIALLY DEFERRED`:
  - vector → `build_chunk` (`003:123-124`);
  - body → vector (`003:161-162`);
  - opportunity → body (`003:183-184`);
  - Search → vector (`004:44-45`);
  - `system_archetype` → vector (`011:87-90`);
  - `cluster_member` → vector (`004:146-147`).
- Indexes copied: the Search GiST and two btrees (`004:52-54`), and the vector
  chunk index (`003:126`). Archetype (25 indexes, 24 of them partial tier
  indexes, `011:102-210`) holds survivors only (`016:198-211`) and is not copied.
- The only grants are 016's executor `SELECT` and `MAINTAIN`
  (`016:1095-1098`). The application role owns the tables.

The production guards would reject the copy itself, because they refuse inserts
for a `PUBLISHED` generation or a `READY` product (`003:192-205`,
`006:136-163`). The staging table therefore carries only a **copy guard**:

- `UPDATE`, `DELETE` and `TRUNCATE` are always rejected;
- `INSERT` is accepted only inside the copy function, checked through
  `PG_CONTEXT` (the 016 pattern, `016:323-335`).

The production triggers are created inside the swap.

### 1.2 Bulk copy

The copy runs `INSERT INTO staging SELECT … WHERE derived_generation_id =
<survivor> AND key > <last> ORDER BY <primary key> LIMIT n`:

- It works in resumable chunks of n ≤ 100,000 rows, one transaction each, which
  is 016's batch bound.
- Before every chunk it re-runs the existing gate 2: free space ≥ the 100 GB
  floor + 1.5 × measured chunk growth, the archiver not failing, and no slot
  retaining WAL.
- It is throttled so that `pg_wal` stays under production's 32 GB `max_wal_size`
  (`docs/operations/v3-postgres-server-settings.md:40`). The offsite archive ran
  at ~245 GB/h during the first full backup
  (`deploy/v3-production/backup/README.md:115`).
- Each chunk records its key range, row count and a source digest in the ledger.
- Autovacuum is off on the staging table.
- It does not use replica mode, disable triggers or use `COPY FREEZE`
  (`docs/development/bulk-database-write-safety.md:17-22`).

### 1.3 Indexes, maintenance, verification

1. Build the indexes. The GiST build dominates the Search time.
2. Run `VACUUM (FREEZE, ANALYZE)`. This avoids a later anti-wraparound pass over
   ~415 GB, and it sets the manual `last_vacuum`/`last_analyze` that the probe
   requires (`scripts/v3_archetype_plan_probe.py:529-564`).
3. Verify. Any mismatch stops the phase.
   - **Counts:** survivor counts equal 016's frozen `survivors`
     (`016:185-196`) and, for Search, the plan's frozen `published_survivors`.
   - **Chunk receipts:** counts per chunk equal the `build_chunk` receipts
     (`003:82-94`). Tests prove the column mapping.
   - **Content:** the per-range digests, recomputed, equal the digests recorded
     during the copy.
   - **Catalog:** the fingerprint matches.
   - **FK:** the staging table's FK to its live parent is added `NOT VALID`, then
     `VALIDATE`d.

### 1.4 Swap

The swap is one transaction with `lock_timeout = 2s`. It retries with backoff up
to a reviewed limit.

1. `ALTER TABLE … SET SCHEMA v3_retired` moves the live table, with its indexes,
   constraints and triggers. Its kept guard then refuses every `DELETE`, because
   016 admits only `v3_derived` (`016:350-353`).
2. The staging table moves into `v3_derived` with its canonical index names.
   Nothing is renamed. 016's enum resolves names at call time.
3. The copy guard is replaced by the production triggers.
4. Two views are recreated: `v3_app.system_search` (`015:328-337`) and
   `v3_derived.system_economy_rating` (`003:218-225`).
   `v3_app.system_economy_rating` reads the latter view, so it follows.
5. For a parent relation, each child FK is dropped and re-added with the same
   name, `NOT VALID`, against the new table. It is `VALIDATE`d after commit,
   which takes `SHARE UPDATE EXCLUSIVE` and does not block reads.
6. The executor is re-granted, and `SWAPPED` is appended to the ledger.

### 1.5 Drop

`DROP TABLE v3_retired.<rel>` runs in its own approved dispatch, never with
`CASCADE`. It requires:

- `VERIFIED` and `SWAPPED` in the ledger;
- every re-pointed FK validated;
- no `pg_depend` dependents.

The space is freed at commit.

### 1.6 Order and space

Children must go before parents. An old child still holds target rows that a new
parent lacks, so its FK could not validate. That leaves this order:

1. Search or opportunity first. **Search goes first** because it needs the least
   space.
2. Then body.
3. Then vector.

Each DROP funds the next step:

| Relation | Live | Survivor est. | Net freed | Copy peak (rehearsal) | ×1.5 | Free needed before |
|---|---:|---:|---:|---:|---:|---:|
| 1 `system_search` | 175 GB | 102.0 GB | 73 GB | 111.8 GB | 167.8 GB | **267.8 GB** |
| 2 `economy_opportunity` | 265 GB | ≈131 GB | ≈134 GB | 149.8 GB | 224.8 GB | 324.8 GB |
| 3 `body_mechanics` | 210 GB | ≈104 GB | ≈106 GB | 144.6 GB | 216.9 GB | 316.9 GB |
| 4 `system_rating_vector` | 158 GB | ≈78 GB | ≈80 GB | 89.7 GB | 134.5 GB | 234.5 GB |

Survivor sizes: Search from the receipt's survivor split; the others from the
dated model (`v3-governed-derived-purge-design.md:133`). "Copy peak" is the
receipt's survivor-only rewrite peak (`per_relation.*.production.rewrite_peak_bytes`),
the closest measured proxy for a copy until the rehearsal measures one (§6).

## 2. Writes during the copy

**No writer fence is needed.** The database already rejects writes to the
survivor generation:

- Vector, body and opportunity accept `INSERT`/`UPDATE` only for `BUILDING`
  generations, and `DELETE` only through 016 (`003:192-216`, `016:342-378`).
- Search accepts inserts only while its product is `BUILDING`, and rejects
  `UPDATE` and `TRUNCATE` (`006:136-206`).

Nothing in the application writes these tables either:

- The only writers are the build scripts (`scripts/ratings_v4/*`,
  `scripts/v3_system_search.py`, `scripts/v3_system_archetype.py`).
- EDDN ingest writes only canonical tables
  (`apps/api/src/ingest/eddn_client.py:169,443,487,670`).
- Both explanation endpoints only read: `apps/api/src/routers/ratings_v4.py:203-235`
  in a read-only transaction, and `apps/api/src/routers/archetypes.py:183-219`.

So the API and ingest stay up, and gate 3b does not arise.

**What must be fenced:**

- Lifecycle and product changes (publication, pointer, product). 016's
  `purge_assert_request` stops on that drift (`016:213-249`).
- Future builds, whose rows would land in the live table and not be copied.
- Schema migrations.
- The 016 delete/rewrite modes.

The host lease and the shared ledger query
(`docs/operations/v3-governed-derived-purge.md:13-24`) cover these once the
query also reads the copy ledger. The copy also refuses while any 016 event is
open, because those events hold the old OIDs. Verification also confirms that
the live table holds nothing beyond the survivors and the two targets' frozen
rows.

## 3. Outage: the swap only

| Swap | `ACCESS EXCLUSIVE` on | Readers blocked |
|---|---|---|
| Search | `system_search` | Finder search and ranking |
| Opportunity | `economy_opportunity` | archetype explanation |
| Body | body, opportunity (FK re-point) | ratings and archetype explanations |
| Vector | vector, body, Search, `system_archetype`, `cluster_member` | the whole Finder |

**How long:** the swap is catalog-only, estimated under 1 s, plus a lock wait of
at most 2 s per attempt. Reads queue behind it, so a request is delayed by at
most about 3 s.

**API behaviour:** only a read waiting beyond the 15 s statement timeout
(`apps/api/src/config.py:88`) fails, as a 503
(`apps/api/src/routers/archetypes.py:350-356`,
`apps/api/src/routers/search.py:90-105`); the 2 s lock timeout makes that
unlikely. The statement cache is off (`apps/api/src/main.py:165`), so no cached
plan holds an old OID. Content is identical across the swap, so a request that
spans it still gets one consistent answer.

The DROP locks only the retired table, which nothing reads.

## 4. Safety, undo, ledger, migration

| Point | Undo |
|---|---|
| Before swap | Drop the staging table. Live data is untouched. |
| After swap, before DROP | `swap-back-R`: the swap in reverse. The retired table still holds every survivor, so FKs validate. |
| After DROP | None, as in today's design, where deletes are final at commit and no restore authority exists (`docs/operations/infrastructure-status.md:103-105`). B's point of no return comes later, after verification. |

**Reused from applied 016:**

- the request and `authorize`, which move both targets to `FAILED` and freeze the
  snapshot (`016:80-106`, `016:251-319`);
- `purge_snapshot`, `purge_assert_request` and `purge_assert_empty_exclusions`;
- the relation enum, the executor role and the definer pattern.

**Unused:** the delete guards, the autovacuum and writer fences, and
`VACUUM FULL`.

016's completion requires `REWRITE_VERIFIED` for every relation
(`016:1065-1071`), and its event kinds are a closed `CHECK` (`016:110-115`). A
**new migration** is therefore needed. It adds:

- the schemas `v3_purge_staging` and `v3_retired`;
- an append-only copy request/event ledger keyed to the 016 `purge_id`, with
  kinds `COPY_STARTED`, `CHUNK_COPIED`, `INDEXES_BUILT`, `VERIFIED`, `SWAPPED`,
  `SWAPPED_BACK`, `FK_VALIDATED`, `DROPPED`, `COMPLETED` and `FAILED_STOP`;
- definer functions for prepare, chunk, indexes, verify, swap, swap-back, drop
  and complete;
- the fingerprint function.

It must be applied **before** plan and `authorize`, because
`purge_assert_request` checks the schema-ledger hash (`016:242-246`).

**Number:** propose **`019`**. `017` is claimed by the station-sightings design
(PR #874) and also cited for the colonisation journal events
(`docs/colonisation-redesign/in-game-experiment-recording.md:151-152`), so one
of those becomes `018`. Manifest order, not the number, controls application.

## 5. Disk feasibility (~105 GB free)

The ~105 GB is an estimate. 180.2 GB was free on 2026-10-21, before the ~73 GB
archetype build, and free space has not been measured since.

**In place:**

| Step | Needs | Today (~105 GB) | If starting at 268 GB |
|---|---:|---|---|
| 1 Search | 267.8 GB | **no**, 162.8 GB short | yes → 341 GB after |
| 2 Opportunity | 324.8 GB | — | yes → 475 GB after |
| 3 Body | 316.9 GB | — | yes → 581 GB after |
| 4 Vector | 234.5 GB | — | yes → 661 GB after |

**Nothing fits today.** Even the unmargined Search survivor (102 GB) plus the
floor exceeds 105 GB. Once step 1 has run, the rest follows. Option C in place
therefore means about 163 GB more on the main filesystem. That filesystem is a
1.948 TB volume (`v3-governed-derived-purge-design.md:119`), so the space would
come from larger disks.

**Update, 2026-10-24 (measured after the host clean-up):** `df -h /` reports
295 GiB free (about 317 GB in the decimal units of these tables), up from
109 GiB before the clean-up recorded in `docs/operations/infrastructure-status.md`.
That is above step 1's 267.8 GB with about 49 GB to spare, so the in-place
route fits without option C, provided free space still clears 267.8 GB when
step 1's gate is evaluated. Gate 2 re-measures before every chunk regardless;
this note does not replace that check.

**Backups borrow local disk.** The Storage Box mount caches every file pgBackRest
writes on `/` before uploading it, and the log records a peak of 77.9 GiB
(`deploy/v3-production/backup/README.md`, "Storage Box mount"). That is larger
than the ~49 GB margin above, so a copy phase must not overlap a backup: either
it holds the schedule lock for its whole duration, as 016's destructive phases
do, or gate 2 adds the cache peak to the floor. See question 8.

**Alternative: a temporary tablespace on an added disk.** Copy Search and
opportunity to the added disk; copy body and vector in place; then copy Search
and opportunity back, using the same mechanism.

| Step | Main free needed | Added disk used (peak) | Main free after |
|---|---:|---:|---:|
| 0 Mount the disk, `CREATE TABLESPACE` | — | — | 105 GB |
| 1 Search → added disk | ≈148 GB (floor + 1.5 × 32 GB WAL) | 102 (168) GB | 280 GB |
| 2 Opportunity → added disk | ≈148 GB | 233 (327) GB | 545 GB |
| 3 Body in place | 316.9 GB | 233 GB | 651 GB |
| 4 Vector in place | 234.5 GB | 233 GB | 731 GB |
| 5 Search back | 267.8 GB | 131 GB | 629 GB |
| 6 Opportunity back | 324.8 GB | 0 | 498 GB |

Caveats:

- Mounting the disk recreates the database container, which is a short full
  outage.
- Step 1 is still about 43 GB short today, unless `max_wal_size` is lowered for
  the duration or space is freed first.
- The added disk needs at least 400 GB, mirrored. Live Finder tables sit on it
  during steps 1–6, and no restore route exists.
- Gate 2's rule that every write lands on the floor's filesystem
  (`v3-governed-derived-purge-design.md:304`) needs an owner amendment to measure
  the floor per filesystem.

Either route ends at about 498 GB free on main, a net gain of about 393 GB.

## 6. Effort

| Work | Content |
|---|---|
| Migration `019` + PG 18 tests | Ledger, functions, fingerprint; similar in size to 016 (1,131 lines). Tests: copy-guard refusal; inserts refused after the swap; swap and swap-back are atomic; FK re-point + validate; views; probe index names; `DROP` refused with dependents; a crash at each step; lock-timeout retry under a concurrent reader; fence refusal per mutator. |
| Operator action + workflow | Modes `copy-R` (resumable; Search needs 2–3 dispatches within the 180-min job), `swap-R`, `swap-back-R`, `drop-R`. Plan, status and complete extended; the fence query and the backup-wrapper check extended. |
| 1% rehearsal | Extend `scripts/rehearsal/v3_derived_purge_rehearsal.py`. Measure per relation: copy rows/s, index time, verify time, peak bytes, WAL bytes, swap lock hold, and Finder latency during the swap. |
| Production | Apply `019` → plan → `authorize` → per relation one approval each for copy, swap and drop → `complete`. About 14–20 approvals, not about 300. Estimated machine time (to be measured): Search 4–8 h; the others 0.5–1.5 h each; plus verification. |

## 7. Other objects

- **F2d plan probe:** its index names and maintenance timestamps are preserved
  (§1.1, §1.3). Re-run it after the Search swap. A one-generation GiST should
  bring the speed-up that P was expected to bring (`docs/ROADMAP.md:117-130`).
- **`v3_app.*` views:** `system_search` is recreated, and `system_economy_rating`
  follows its `v3_derived` view. `system_archetype`, `system_archetype_summary`
  and `cluster_member` read no copied table.
- **Spatial pyramid:** keyed to the canonical generation since `012`
  (`012:1-16`), with no FK to these tables. Untouched.
- **Cluster tables:** zero target rows (`016:198-211`). Only `cluster_member`'s
  FK is re-pointed, at the vector swap.

## 8. Owner answers (2026-10-24)

1. **Disk:** in place on the main filesystem; no option C. The 2026-10-24
   clean-up left 295 GiB (≈317 GB) free (§5 update). Gate 2 still re-measures
   before every chunk.
2. **Free space:** measured after the clean-up (§5 update).
3. **Swap stall:** accepted. A stall of a few seconds per swap needs no
   maintenance window.
4. **Retired-table retention:** drop it the same day, once the swap has verified
   (the Finder answers and every re-pointed FK has validated). Each DROP funds the
   next relation; `swap-back-R` remains the undo until then.
5. **Migration number:** `019`.
6. **016 delete/rewrite modes:** disabled once B's operator modes land. The parts
   B reuses (§4) stay.
7. **Storage Box WAL headroom:** sufficient. Owner-measured `df -h
   /mnt/ed-storagebox` on 2026-10-24: 5.0 TiB size, 531 GiB used, 4.5 TiB
   available (the compressed repository after the 2026-10-18 full backup), far
   above the ~0.5 TB of extra WAL the copies are expected to archive.
8. **Backups during a copy:** scheduled pgBackRest backups skip from a
   relation's `COPY_STARTED` until its `DROPPED` (or its abandonment), through
   the backup wrapper's existing ledger-driven `SKIP`, and every copy dispatch
   also holds the schedule lock for its whole run. WAL archiving continues, so
   point-in-time recovery from the last full backup is not interrupted. Reason:
   the mount's write cache (77.9 GiB peak) exceeds the space margin, and the
   first diff after a copy would carry the whole new table.
