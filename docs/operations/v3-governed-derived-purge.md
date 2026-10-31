# V3 governed derived purge (through P2d; copy-and-drop route)

This runbook covers the P2a entry fences and installed backup wrapper, the
P2b1 read-only and single-transaction purge action, the P2c protected dispatch
workflow, the P2d disposable rehearsal, and — since migration 019 — the
**copy-and-drop route** (`preflight-R`, `copy-R`, `swap-R`, `swap-back-R`,
`drop-R`, `abandon-R`, `complete`) that replaces 016's bounded deletes and
`VACUUM FULL` rewrites. The
[governed purge design](../development/v3-governed-derived-purge-design.md)
remains the execution-gate authority for everything the copy route reuses
(gates 1–10, the host lease, the ledger-driven fences, `restore-services`), and
the owner-accepted [copy-and-drop design](../development/v3-purge-copy-and-drop-design.md)
is the authority for the route itself. The approximately 1% disposable PostgreSQL
18 rehearsal must pass and be reviewed; the protected workflow does not itself satisfy
the design's owner execution gates. No production operation follows from merging
this code.

**016's `delete-R` and `rewrite-R` modes are disabled** (owner answer 6 of the
copy-and-drop design). The protected workflow no longer offers them, the
workflow helper refuses them before approval or SSH, and the action refuses
them with `delete_rewrite_modes_disabled_by_copy_and_drop_design`. Their
sections below are retained as the description of what the recovery paths
(`restore-services`, `abort-relation-R`) still resolve, not as dispatchable
phases.

## Copy-and-drop route (migration 019)

### Preconditions (all of them, before step 1 below)

1. Migration `019` is applied (production: 2026-10-26, apply run 40338736148),
   migration `020` (the swap lock order) is applied (production: 2026-10-27,
   apply run 40551173291), migration `021` (the long-phase bounds) is
   applied (production: 2026-10-28, apply run 40654201809), and the installed backup wrapper is the committed one that reads
   `v3_meta.purge_copy_backup_skip()` (re-run `v3-backup-wrapper-install`
   after this code merges; the installer now refuses unless 019 is applied).
2. **A full pgBackRest backup immediately before step 1**, reviewed as
   `status: ok`, and **another full backup after `COMPLETED`**. Scheduled
   backups SKIP from each relation's `COPY_STARTED` until its `DROPPED` or
   abandonment (owner answer 8), so the pre-copy full backup is the recovery
   point for the whole route; WAL archiving continues throughout.
3. **A backup heartbeat alert exists** that pages the owner when no successful
   pgBackRest backup has completed for a reviewed interval: the hourly
   `edfinder-v3-backup-heartbeat.timer` (36 hours; installed by the
   `v3-backup-heartbeat-install` operation, see
   `deploy/v3-production/backup/README.md` "Backup heartbeat"). Without it a stalled copy would skip backups silently
   (F16). `status` reports `backup_age_hours` and `copy_state_hours` as well.
   Production: installed 2026-10-29 (install run 40873385526, first run
   healthy).
4. **`GRANT SET ON PARAMETER temp_file_limit TO v3_derived_purge_executor`**
   has been applied by the owner. `temp_file_limit` is a superuser-set
   parameter and 019 does not grant it; every long phase sets
   `SET LOCAL temp_file_limit` (32 GiB; 64 GiB for verify since 2026-10-30) and refuses with
   `temp_file_limit_privilege_missing` until the grant exists. This is a
   production catalog change that needs its own reviewed step (a migration
   `020` or an owner-run statement recorded in evidence). Production: applied
   by the owner on 2026-10-29 and verified with `has_parameter_privilege`
   (`docs/operations/evidence/2026-10-29-v3-purge-temp-file-limit-grant-owner-run.json`).
5. **WAL archiving keeps up with the long phases**: background parallel
   archiving is on (`deploy/v3-production/backup/README.md` "WAL archive
   speed"). The index builds and `VACUUM (FREEZE)` write 55–108 GB of WAL per
   relation at production scale and the watchdog cancels a long phase at
   2 × `max_wal_size` in `pg_wal`; one-segment-at-a-time archiving would not
   drain it fast enough. Production: turned on by the owner on 2026-10-30
   (`docs/operations/evidence/2026-10-30-v3-pgbackrest-async-archive-owner-run.json`).

   **After a backup, archive one fresh segment before a relation's first
   `copy-R`.** The copy route's archive-lag query (`WAL_LAG_SQL` in
   `v3_purge_copy.py`) reads `pg_stat_archiver.last_archived_wal` with
   `pg_split_walfile_name`, which refuses a backup history file name such as
   `00000001000003E000000009.00000028.backup` (PostgreSQL 18: `invalid WAL file
   name`; checked 2026-10-30). Every pgBackRest backup leaves that name there
   until the next WAL segment is archived, which can take hours on this quiet
   database; both plans of 2026-10-29 still saw it three and four hours after the full
   backup finished.
   A `copy-R` would then stop at its first throttle check, before `prepare`
   writes anything. Backups skip while a relation is between `COPY_STARTED`
   and `DROPPED`, so only a relation's first `copy-R` after a scheduled backup
   (02:30 UTC daily) has run between relations is exposed. Before that
   dispatch the owner runs this command in a terminal on **ed-finder-prod**
   (the backup README's "WAL archive speed" step 4): it forces a WAL switch
   and waits for that segment to be archived, and must end with
   `check command end: completed successfully`.

   ```
   docker exec -u postgres edfinder-v3-phase4c-full-20260827_r5-postgres pgbackrest --stanza=edfinder_v3 --log-level-console=info check
   ```

   The query is in a file the accepted rehearsal pins, so it is not changed
   during this purge.
6. The owner has read the 2026-10-26 external review's findings as reflected
   here: the operator sets every timeout (F5), the swap stall is bounded by the
   operator's 8 s statement cap and not by 019's 2 s lock timeout (F4), and
   the retired table is the only undo until `drop-R`.

### What each mode does (one owner approval each)

| Mode | What runs | Locks held |
| --- | --- | --- |
| `preflight-R` | Read-only (owner session for the catalog reads 019 revoked from the executor): exact dependents equal the fixed children/views, no disabled or commented live trigger, no dependent view with options, no `indisclustered` live index, live shape inside the generator contract, `age(relfrozenxid)` of all four live heaps/TOAST under 80% of `autovacuum_freeze_max_age`, and for Search one scan of the published survivors counting rows that violate each of 010's `NOT VALID` checks (the staging copy enforces them). Any failure refuses. Runs on its own and again automatically before `copy-R` starts a relation (the survivor scan only before `prepare`). | host lease |
| `copy-R` | Resumable. From the ledger: `prepare` → bounded chunk loop (≤ 100,000 rows per transaction, one chunk per transaction, `wall_clock_seconds` 1–9000 budget) → `build_indexes` → `VACUUM (FREEZE, ANALYZE)` → `verify`. Before **every** chunk gate 2 is re-measured (free bytes ≥ 100 GB + 1.5 × the largest measured per-chunk growth, archiver not failing, no slot retaining WAL, `pg_wal` on the data filesystem, named workers stopped) and the loop throttles while the WAL written since the latest checkpoint's REDO point ≥ 0.9 × `max_wal_size` or the archiver lags more than 256 segments. The REDO point comes from `pg_controldata` in the pinned container (run as the server's OS user, like the data-directory read): the `pg_wal` directory itself keeps recycled segments up to about `max_wal_size` after a write burst and an idle server skips checkpoints, so a directory-size throttle could wait forever. Before `prepare` the free bytes must also cover the plan's `copy.relations[R].required_free_bytes_before_copy` (floor + 1.5 × the copy peak the reviewed copy-route rehearsal measured and extrapolated; design §1.6). Each long phase waits for the archiver to be within 16 segments, re-checks gate 2 counting expected index size, temp space and `max_wal_size`, runs under the root-owned watchdog with `pg_stat_progress_create_index`/`pg_stat_progress_vacuum` polling, and only starts when the remaining dispatch budget (19,800 s) covers its statement timeout (7,200 s; verify 19,200 s) plus a 300 s margin; otherwise the receipt says `copy_long_phase_deferred_to_next_dispatch` and the next `copy-R` resumes there. The VACUUM is throttled (`vacuum_cost_delay 10ms`, `vacuum_cost_limit 1000`). F12: after the VACUUM the staging `age(relfrozenxid)` must not exceed the XIDs consumed during the VACUUM plus 10,000, and never 1,000,000; a resumed dispatch whose freeze aged out freezes again. | host lease, backup schedule lock |
| `swap-R` | `purge_copy_swap` with up to 12 attempts (backoff 2,4,8,15,30,30,60… s), each attempt capped by an 8 s statement timeout and retried only on lock/statement timeout; then `purge_copy_validate_fks` (long phase, watchdog); then a read-only Finder smoke through the active origin (`/api/health`, one ranked `/api/archetypes/rankings`, one ranked `/api/local/search`); for `economy_opportunity` the F7 recalibration (count rows and distinct `system_id64` on the new live table, `ALTER TABLE … SET (n_distinct = -(distinct/rows))` as the owner, `ANALYZE … (system_id64)`, then `EXPLAIN` of the archetype chunk read must show a Nested Loop over `economy_opportunity_pkey`). Before the `ALTER` the restore value (the live and retired tables' `system_id64` attribute options) is written to the root-owned host state `/var/lib/ed-finder/v3-production/derived-purge-copy-statistics.json` and travels in the receipt (`n_distinct_recalibration.host_state`); 019's ledger has no event for a statistics option. Idempotent: a re-dispatch after a swap repeats only the post-swap steps — a committed swap whose FK validation or smoke was lost resumes there (`swap_resumed: true`, `status` names `swap-R`), and a recalibration whose option is already set re-runs only `ANALYZE` and the plan proof. The receipt records every attempt's duration and `measured_stall_seconds`. | host lease, backup schedule lock |
| `drop-R` | Requires VERIFIED, SWAPPED, FK_VALIDATED; the Finder smoke must pass again immediately before; then `purge_copy_drop` (`RESTRICT`, same retry/cap as the swap). Records freed bytes and WAL bytes. A drop whose response was lost has committed: a re-dispatch reports `retired_relation_already_dropped` and changes nothing. The next mode is the next relation's `copy-R` (or `complete`). | host lease, backup schedule lock |
| `swap-back-R` | The undo between swap and drop: `purge_copy_swap_back` (same retry/cap), `purge_copy_validate_fks`, Finder smoke. For `economy_opportunity` the swap-back runs in **one owner transaction** that first restores the retired table's `system_id64` attribute options on the copy (019's swap-back compares attribute options exactly with the retired table, and swap-R recalibrated them), then calls the executor's `purge_copy_swap_back`; both commit or neither does (`n_distinct_restore` before/after in the receipt). Resumable: a committed swap-back whose FK validation was interrupted (`staged`, `SWAPPED_BACK`, child FKs `NOT VALID`; `status` names `swap-back-R`) skips the physical swap-back and finishes validation and the smoke (`swap_back_resumed: true`); `copy-R` refuses to re-verify until then (`swap_back_fk_validation_pending`). The relation returns to `staged`; the owner then re-verifies through `copy-R` or abandons. | host lease, backup schedule lock |
| `abandon-R` | Drops an unswapped staging copy (`FAILED_STOP` with `abandoned: true`); live data untouched; the relation can restart. | host lease, backup schedule lock |
| `complete` | Reads 019's state: every relation DROPPED, nothing staged or retired, zero target rows, pointers and survivors unchanged; appends 019's `COMPLETED`. **016's own ledger never reaches COMPLETED on this route** (it has no `REWRITE_VERIFIED`); `status` reports the copy request's `completed`. | host lease, backup schedule lock |

Every mode is a separate owner-approved `v3-production` environment run of
the protected workflow, holds its locks for its whole life, and the job stays
attached until the remote action exits (no detached work, exactly as before).

**A still-running earlier backend refuses the next dispatch.** 019 serializes
copy operations with `pg_try_advisory_xact_lock(764019001)` and raises `P0001`
(`competing purge copy operation`) while another transaction holds it; reduced
to its SQLSTATE that would read as an integrity failure. Every mutating copy
dispatch and `complete` therefore first refuses with
`competing_purge_copy_backend_active` (retryable; `next_admissible_mode:
status`) while any other backend holds that lock or runs a mutating
`purge_copy_*` function — for example the orphaned backend of an interrupted
dispatch, which keeps running until its statement ends (a chunk within 300 s).
Wait and re-dispatch; nothing was written.

**Timeouts are the operator's (F5).** Measured on PostgreSQL 18.4: a
function-level `SET statement_timeout` does **not** bound the function's own
call (the timer is armed when the statement starts, before the function's
settings apply), so 019's `SET statement_timeout='60s'` clauses bound nothing.
Every 019 call therefore runs inside a transaction that first sets
`SET LOCAL statement_timeout` and `SET LOCAL lock_timeout` from the reviewed
table in `scripts/operator/lib/v3_purge_copy.py` (`PHASES`): prepare 60 s,
chunk 300 s, swap/swap-back/drop/abandon 8 s with a 400 ms lock request,
record-failure 60 s, complete 300 s, and 7,200,000 ms (the workflow's reviewed
envelope) for index build, VACUUM FREEZE, FK validation and the opportunity
statistics count. Verify has 19,200,000 ms (320 minutes) and a 64 GiB
temp-file limit: owner decision 2026-10-30, after the Search verify took 4,247 s
and wrote about 19 GB of temp files; scaled by the one_percent rehearsal's
relative verify times, `economy_opportunity` needs about 3.7 hours and
`body_mechanics` about 2.9. `tests/test_v3_purge_copy_operator_pg18.py`
proves on PG 18 that the bound comes from the caller.

**The swap stall (F4).** Also measured on PG 18.4: 019's function-level
`SET lock_timeout='2s'` **wins** over the caller's `SET LOCAL lock_timeout`,
so each of the vector swap's lock acquisitions may still wait 2 s. What bounds
one attempt is the operator's 8 s statement timeout: an attempt that stalls
longer is cancelled, rolls back, releases its locks and is retried with
backoff, so Finder reads queue behind a swap attempt for at most about 8 s
(under the API's 15 s read timeout). The receipt's `swap_attempts` and
`measured_stall_seconds` record what happened; the rehearsal must record the
measured stall. **Required 019 change (not made here — 019 is applied and its
bytes are pinned in the schema identity):** drop or lower the `SET
lock_timeout='2s'` on `purge_copy_swap`, `purge_copy_swap_back`,
`purge_copy_drop` and `purge_copy_abandon` so the operator's sub-second
`SET LOCAL lock_timeout` governs; the 019 closing comment that says bulk
phases "inherit the operator's per-dispatch statement_timeout" and that
timeouts are "pinned on each public entry point" is misleading for
`statement_timeout` and must be corrected in that same future migration.

**Resumability (F2).** 019's `build_indexes` and `verify` are single calls, so
a phase cannot resume mid-way without SQL changes (a per-index
`purge_copy_build_index(purge, relation, index_name)` and a per-chunk-range
verify would be needed). The operator therefore resumes at phase granularity:
a long phase that is cancelled, times out or loses its backend rolls back and
leaves the ledger phase unchanged, and the next `copy-R` dispatch re-enters
it; only an integrity failure (SQLSTATE `P0001`, `23514`, `23502`, `23503`,
`23505`) records `FAILED_STOP` through `purge_copy_record_failure`, after which
only `swap-back-R` and `abandon-R` remain for that relation.

**Long-phase bounds (021).** The one_percent rehearsal (run 40571954621)
cannot authorize production: its extrapolated `body_mechanics` and
`economy_opportunity` verification and `system_search` index build exceed the
7,200 s envelope (`rehearsal_long_phase_exceeds_reviewed_timeout`). 019's
`verify` re-read each copied chunk with a range whose btree scan ran on to the
end of the survivor generation, so its time grew with the square of the table
size; migration `021` re-reads each chunk with the copy's own keyset read (low
key, primary-key order, `LIMIT` the ledgered rows). The Search index build is
dominated by the GiST index on `position_ly`; `021`'s `prepare` creates the
live GiST indexes on the empty staging table, so the bounded, resumable chunk
inserts fill them and `build_indexes` builds only the rest
(`docs/development/v3-purge-copy-and-drop-design.md` §1.3). `021` must be
applied before `plan`, and the one_percent rehearsal must be re-run with it.

**Production host speed (2026-10-28).** The re-run with `021` (run
40704251158, main `065d1e56`) passed every check except the gate: verification
of `body_mechanics` (about 7,077 s) and `economy_opportunity` (about 8,900 s)
extrapolated from the rehearsal host. The 7,200 s statement cap dates from the
purge design (#822); the "twice the estimate" margin was added with
copy-and-drop (#894). Neither was an owner requirement, and both were measured
against the rehearsal host. An owner-run, read-nothing benchmark of the same
row-text, md5 and ordered-aggregate work
(`docs/operations/evidence/2026-10-28-v3-purge-host-speed-benchmark.json`)
took 5.56–5.63 s on production and 17.77–18.48 s on the rehearsal host (same
result on both). Owner decision (2026-10-28): no further rehearsal; the gate
judges verification at production speed. Production authority now requires
twice `max(index build, VACUUM FREEZE, verify × 0.31695, FK validation)` to be
within 7,200 s, scaling only verification and only for receipts measured in
the benchmarked rehearsal image; the statement timeouts themselves are
unchanged. Run 40704251158's longest phase is then about 2,821 s
(`economy_opportunity` verification; its VACUUM FREEZE, unscaled, about
2,818 s). Because that run predates this gate, the receipt module pins it
(`ACCEPTED_REHEARSALS`: its content seal, its action identity and the SHA-256
of every file that identity covers). It stays production authority only while
every one of those files except the receipt module itself, the harness and the
migration set are byte-for-byte as rehearsed; a change to any purge file
before the purge runs requires a new one_percent rehearsal, and a static test
fails until the pinned entry is removed.

**Owner-accepted amendment (2026-10-30).** After `authorize` (run
40971335172) the Search `preflight` (run 41034514200) stopped read-only with
`bounded_command_failed`: production validated all 18 Search checks on
2026-10-18, and with none left NOT VALID the survivor scan
(`SEARCH_VIOLATIONS_SQL`) generated a statement over every survivor and
failed (`SQLSTATE 2200M`, reproduced on PostgreSQL 18). The rehearsal fixture
kept 010's checks NOT VALID, so it never ran that case. `HAVING count(*)>0`
now makes the scan answer `{}` without reading a row when no NOT VALID check
exists; with checks present it is unchanged. The owner accepted this one
change without a new rehearsal: the pin's `amended_files` records
`v3_purge_copy.py`'s rehearsed and accepted SHA-256, the pinned receipt stays
authority while the file equals the accepted digest, and every other file must
still be as rehearsed. The authorized plan is unaffected: phases after
`authorize` do not re-read the pin.

**Second owner-accepted amendment (2026-10-30), same file.** `copy-system-search`
copied every survivor (runs 41050714814 and 41070830382), then the second
run stopped before the index build at gate 2 (`filesystem_free_space_floor`:
221.8 GB free, 232.0 GB required). The requirement counted every live index,
but 021's `prepare` had already built the Search GiST index on the staging
table (17.5 GB of the 70.3 GB copy), and `build_indexes` skips it. `STAGING_SQL`'s
`live_index_bytes` now counts only the live indexes whose name is not already
on the staging table, so it equals `pg_indexes_size(live)` before `prepare`
and for every relation without a prepared index; the floor, the 1.5 × growth
margin, the temp-file allowance and the `max_wal_size` allowance are unchanged
(Search then requires about 206 GB). A read-only host inventory the same day
(`v3-host-storage-detail` run 41088164473, `v3-disk-inventory` run 41088246411)
found about 11.6 GB outside the database in total, so freeing the shortfall
on the host was not possible. The owner accepted this change too; the pin's
`amended_files` entry now carries the new accepted digest.

**Third owner-accepted amendment (2026-10-30), `v3_generation_purge.py`.** The
Search verify (copy run 41102817187) was cancelled about a minute in by the
watchdog (`wal_archiver_failure`, `observe:wal_directory_bytes_unavailable`,
SQLSTATE `57014`, retryable): a checkpoint was removing or recycling the
segments the index build and VACUUM had written, and the `pg_wal` probe failed
three times back to back. `measure_wal` now keeps re-measuring for up to 60 s
(see the watchdog paragraph). The owner accepted this change; `amended_files`
records `v3_generation_purge.py`'s rehearsed and accepted digests. That file is
also in `deploy/v3-production/f2d-operator-code.txt`, so the F2d operator
identity on `main` no longer equals the `1e748c9d` release attestation: the
F2d build and status operations refuse until the next application release
attests it. The purge does not use them.

**Fourth owner-accepted amendment (2026-10-30), verify bounds.** The Search
verify (run 41104549088) took 4,247 s against a production-speed estimate of
about 905 s and wrote about 19 GB of temp files. Scaled by the rehearsal's
relative verify times (`economy_opportunity` 3.1 ×, `body_mechanics` 2.5 ×,
`system_rating_vector` 1.05 × Search), the two larger relations would exceed
the 7,200 s statement timeout and probably the 32 GiB temp-file limit. Verify
alone now has 19,200 s and 64 GiB; the dispatch budget is 19,800 s and the job
360 minutes. The verify space gate becomes 100 GB + 64 GiB + `max_wal_size`
(about 203 GB), which the `economy_opportunity` copy is expected to meet with
about 30 GB to spare. If a verify still does not finish, the dispatch stops
retryably and `abandon-R` remains. `amended_files` carries the new digests of
`v3_purge_copy.py` and `v3_purge_copy_dispatch.py`.

**Fifth owner-accepted amendment (2026-10-31), keyset start (migration 022).**
Under the same 9,000 s budget `copy-economy-opportunity` run 41140926027
copied 267.9 million rows (2.92 s per 100,000-row chunk) and run 41155213939
only 123.5 million (6.85 s per chunk); the Search copy had shown the same
slope (3.32 s, then 5.25 s). 019's chunk read and 021's verification re-read
paired a row comparison led by `derived_generation_id` with a separate
equality on it, so every chunk's btree scan started at the first survivor
entry and walked every entry before the chunk's low key: the cost is
quadratic in the relation. The rest of the copy would have taken about five
more dispatches, and its verification (7,401 chunks) about 40,000–55,000 s,
which can never fit its 19,200 s bound. Migration 022 moves the start:
`v3_meta.purge_copy_keyset` bounds the generation with `<=` so the row
comparison is the scan's start key (same rows; measured flat on PostgreSQL 18,
1,335 buffers per chunk at the first and last positions where 019's grew from
1,930 to 18,596), and `purge_copy_chunk` and `purge_copy_verify` use it.
Because `authorize` (run 40971335172) froze the through-021 ledger, 016's
`purge_assert_request` also accepts the live ledger minus exactly 022's own row;
any other ledger difference still refuses, and recovery steps never compared
the ledger. Governed migration apply refuses while any relation is staged or
swapped, so the owner approved this order: let copy run 3 (41166416358)
finish; `abandon-economy-opportunity` (drops only the staging copy; the live
table and the Finder are untouched, and scheduled backups resume); merge and
apply 022 through the governed migration workflow; then `copy-economy-opportunity`
again from `prepare`. No operator file changes, so the rehearsal pin is
unaffected; the plan and authorization stay as they are.

**Watchdog (F3).** Every long phase runs under the same root-owned
`systemd-run` watchdog as the 016 rewrite (unit
`edfinder-v3-purge-copy-<relation>-<phase>-<pid>`), pinned to the container,
PID and `backend_start`. It cancels on the free-space requirement of that
phase, WAL placement, both archiver predicates, slot health, controller loss,
and a WAL ceiling of 2 × `max_wal_size` on disk. 019 provides no cancel definer, so the
copy watchdog cancels through the owner session's authenticated
`pg_cancel_backend` (exact PID and `backend_start`, this database, the owner's
active client backend running one of the fixed phase statements); it records
the condition beside its config (`<unit>.json.condition`) and the controller
copies it into the receipt (`copy_phase_failures[].monitor_condition`). Any
check that cannot complete (a failed probe, a timeout) also cancels and is
recorded as `wal_archiver_failure`, because 016's cancel definer accepts only
fixed conditions; the watchdog therefore also records what latched the
condition (`<unit>.json.detail`, copied as `monitor_detail`: `observe:<code>` or
`backend:<code>`) and logs it to the unit's journal. The `pg_wal` size probe
(`du`) re-measures at once up to three times, because a checkpoint can remove or
recycle a segment mid-scan and `du` then exits 1 (one_percent rehearsal run
40654125745 stopped on such a cancel with no other recorded cause). At
production scale one checkpoint removes or recycles thousands of segments in
a row, and three back-to-back failures cancelled the Search verify (copy run
41102817187, `observe:wal_directory_bytes_unavailable`, 2026-10-30); since then
it keeps re-measuring every 0.5 s for up to 60 s before it fails closed. The
free-space check runs before the probe on every pass, so a burst delays the
watchdog's next pass by at most that window. The
controller's own watch callback (stop requests, controller liveness, progress
polling) runs only once the phase backend has been set up and yielded: the
identity and session set-up queries run without it.

**Hard rule (F16): any relation left `staged` or `swapped` for more than 24
hours must be finished, swapped back or abandoned.** `status` reports
`copy_state_hours` (with `over_24h_rule: true` when breached) and
`backup_age_hours`; while `purge_copy_backup_skip()` is true no scheduled
backup runs.

### Order and approvals

Children before parents, each DROP funding the next copy (design §1.6):

1. `plan` (with the reviewed **copy-route** rehearsal receipt, schema v3) → 2. `authorize` →
3. `verify-system-archetype-empty` — as before.
4. `system_search`: `preflight-` → `copy-` (2–3 dispatches expected; each
   re-dispatch resumes) → `swap-` → `drop-` (same day, once the Finder answers
   and every re-pointed FK validated).
5. `economy_opportunity`: the same four (its `swap-` also recalibrates
   `n_distinct`).
6. `body_mechanics`: the same four.
7. `system_rating_vector`: the same four.
8. `complete`.

That is **about 14–20 approvals** (3 + 4 × 4 + 1, plus extra `copy-R`
dispatches for Search and any `swap-back-R`/`abandon-R`), not about 300.

### What the owner sees

Each receipt carries `copy_state` (before), `copy_state_after`, `copy_steps`,
`copy_gate`/`copy_phase_gates`, `copy_progress` (the last progress-view
sample), `wal_phase_bytes` (WAL bytes per phase, F8), `phase_timeouts`,
`copy_preflight`, `swap_attempts`/`measured_stall_seconds`, `finder_smoke`,
`n_distinct_recalibration` (before/after, `host_state`), `n_distinct_restore`
(swap-back), `swap_resumed`/`swap_back_resumed`, `competing_copy_backends`,
`wal_throttle` (`wal_since_checkpoint_bytes`, `wal_directory_bytes`),
`staging_freeze`,
`temp_file_limit_privilege`, `skipped_scheduled_backups`, and
`next_admissible_mode`. `status` adds `copy_status` (019's
`purge_copy_status()`), `copy_state_hours` and `backup_age_hours`.

Governed production mutators, except the fixed host clean-up described below,
first read the operating database's purge ledger and non-blockingly probe
`/run/lock/edfinder-v3-derived-purge.lock`.
An open `BATCH_STARTED`, `REWRITE_STARTED`, `SERVICES_QUIESCED`,
`WRITER_FENCE_ENABLED`, or `AUTOVACUUM_DISABLED`, an integrity-failed
`FAILED_STOP`, a held lease, missing ledger, or failed probe refuses the action
before operation locks or mutations. JSON receipts name the unresolved kinds.
The fixed SQL uses migration 016's `purge_open_event`; writer restoration counts
only with JSON boolean `verified: true`. A dead backend frees no ledger fence.
Only the purge recovery paths may resolve these records. Option (b), the
read-only writer fence, is selected. The API stays running throughout; the
quiesce path remains refused until a future owner decision selects option (a).

The sole missing-ledger exception belongs to schema **apply**: its live ledger
must exactly equal the authenticated plan's recorded `applied_before`, including
hashes, and the plan's complete pending suffix must end in
`016_v3_governed_derived_purge.sql`. This supports the entire pending set,
including the pre-014 prefix. A progressed prefix needs a fresh plan when the
relation is still absent. Once 016 is recorded, absence always refuses. A held
purge lease refuses even this bootstrap. Read-only migration `plan` remains
available for diagnosis.

Since 019 the same fence also reads the copy-and-drop ledger: it refuses with
`purge_copy_backup_skip` while `v3_meta.purge_copy_backup_skip()` is true and
with `purge_copy_relation_staged`/`purge_copy_relation_swapped` while any
relation sits between `COPY_STARTED` and `DROPPED` or abandonment, so no
deploy, migration, publication or build can start mid-copy. An absent 019
relation or function refuses with `purge_copy_ledger_absent` everywhere except
the schema apply whose authenticated pending suffix ends in
`019_v3_purge_copy_and_drop.sql` (the same exact-prefix rule as 016's); in
production 019 is applied, so that bootstrap is historical.

## Installation order

After the required code has merged and execution gates permit the operation:

1. Use the [protected schema migration workflow](v3-production-schema-migration.md)
   to plan, review, then apply the complete pending set through 016. Commit its
   receipt. This is a prerequisite for installing the wrapper: an earlier
   installation would make every scheduled backup fail on the missing ledger.
2. Dispatch the existing protected operations workflow
   `.github/workflows/chatgpt-ed-new-ops.yml` on trusted `main`, selecting
   `v3-backup-wrapper-install`. It pins `ed-finder-prod` /
   `nb79a3d.mevnode.com` and replaces only
   `/opt/ed-finder-v3-runtime/pgbackrest-operation.sh`, using the committed source
   SHA and SHA-256. No timer or unit changes.
3. Review and commit its retained JSON receipt. Require `status: passed`, equal
   `source_sha256` and `installed_sha256`, `wrapper_temp_written: true`,
   `wrapper_installed: true`, and `installed_hash_verified: true`. Database,
   service, timer and unit write flags must remain false. The installer refuses
   while the schedule lease is held or backup/verify processes are active, and
   holds the schedule lease through the atomic rename and installed hash check.
4. Only then obtain and commit the later purge plan. That plan and each
   destructive phase must verify the installed wrapper hash against the pinned
   source. Dispatch the action only through the protected workflow described below.

The standalone installed wrapper uses pinned local `psql` credentials by role
name, never a password argument or environment file. Before backup/verify it
skips only for an open destructive record whose recorded PID **and**
`backend_start` still match `pg_stat_activity` in the operating database, and
— since 019 — whenever `v3_meta.purge_copy_backup_skip()` is true (a relation
between `COPY_STARTED` and `DROPPED`/abandonment, or a staging/retired table
present). It logs each skip. Dead backends do not suppress backups; missing
ledger or function, a query failure, or any value other than the exact
booleans exits non-zero before starting pgBackRest. See the
[backup boundary](../../deploy/v3-production/backup/README.md).

## Entry-point classification

| Entry point / modes | Classification | Reason |
| --- | --- | --- |
| `v3_production_deploy.py promote`, `v3-production-promote.sh promote` | Mutator, fenced | Pulls images and changes application containers and release state. |
| `v3-publish-derived-products.sh run` | Mutator, fenced | Publishes products and writes publication receipts. |
| `v3_production_migrate.py apply` via `v3-production-migrate.sh` | Mutator, fenced | Applies DDL and migration ledger; exact-plan bootstrap only. |
| `v3-spatial-pyramid.sh build/publish` | Mutator, fenced | Builds or publishes database spatial state. |
| `ratings-v4-generation.sh start` | Mutator, fenced | Starts a database-writing ratings worker. |
| `v3-system-search-f1.sh start/finalize` | Mutator, fenced | Starts builds or performs validation/maintenance and final receipts. |
| `v3-system-archetype.sh start/finalize` | Mutator, fenced | Starts builds or performs validation/maintenance and final receipts. |
| `v3-system-search-validate-constraints.sh start` | Mutator, fenced | Launches SQL validation that changes catalog state. |
| `v3-archetype-calibration-complete.sh start` | Mutator, fenced | Launches a worker and writes durable host checkpoints. |
| `v3-archetype-calibration-probe.sh run` | Worker launcher, fenced | Database reads are read-only, but launches a container and writes host run/env/receipt state. |
| `v3-archetype-plan-probe.sh run` | Worker launcher, fenced | Database reads are read-only, but launches a container and writes host run/env/receipt state. |
| `v3-finder-capacity-gate.sh run` | Worker launcher, fenced | Database reads are read-only, but launches a container and writes host run/env/receipt state. |
| `octopus-qdrant-healthcheck-repair.sh` | Mutator, fenced | Changes Compose and recreates/starts services. |
| `octopus-upgrade.sh apply` | Mutator, fenced | Changes the Octopus database, `.env` and containers; runs only between purge phases. |
| `octopus-upgrade.sh preflight` | Read-only | Reports upgrade readiness and the purge fence without changing services or database state. |
| `v3-backup-wrapper-install.sh` | Mutator, fenced | Atomically replaces the installed backup runtime file. |
| `v3-host-cleanup.sh` | Filesystem mutator, workflow-serialized and host-leased | Removes only four owner-approved unused directories; shares the `chatgpt-ed-new-ops` concurrency group with the purge job and holds the same host lease through receipt printing, with no database or service writes. See [operator boundary](operator-command-contexts.md#fixed-production-host-clean-up). |
| `host-status` (inline) | Read-only | Host and container inventory. |
| `octopus-edge-status.sh` | Read-only | Inspects edge state. |
| `recover-v3-runtime-contract` (`recover_v3_runtime_contract.py`) | Read-only | Inspects runtime metadata and streams an archive; artifact writes are on the runner. |
| `v3-app-status.sh` | Read-only | Inspects application state. |
| `v3-spatial-status.sh` | Read-only | Inspects spatial state. |
| `v3-derived-lifecycle-status.sh` | Read-only | Inspects pointers, workers and derived lifecycle. |
| `v3-disk-inventory.sh` | Read-only | Inspects filesystem and relation inventory. |
| `v3-host-storage-detail.sh` | Read-only | Inspects Docker storage and `/var/lib`, excluding production PGDATA from directory scans; no database access. |
| All `status` modes above; migration `plan`/`authority-gate`; deployment `authority-gate`/`preflight` | Read-only operation | No production build, publication, DDL or service change. |

The fixed `v3-host-cleanup` exception removes only the four unused directories
listed in its owner authorization. It reads no database ledger and changes no
services; the shared `chatgpt-ed-new-ops` concurrency group and a held
`/run/lock/edfinder-v3-derived-purge.lock` lease serialize it with an executing
purge, even after a runner or SSH failure. It independently rejects Docker
mounts/state, PostgreSQL data markers, and other mounts/filesystems. This exception supplies no authority for database
payload deletion, generic host cleanup, or any additional path.

The three probe/gate launchers above are deliberately fenced under the task's
worker-launch rule despite their read-only database queries. Pure status,
inventory and probe inspection paths stay unfenced. This distinction is about
host worker launch and state, not whether a query writes rows.

## Design and implementation boundaries

016's resolver accepts closing kinds as an argument. Its own rewrite recovery
calls omit `FAILED_STOP`; the P2a callers supply the design's
`REWRITE_VERIFIED/REWRITE_ROLLED_BACK/FAILED_STOP` set. An integrity-failed stop
independently continues to fence every non-purge mutator, including after a
recovery acknowledgement. P2a changes no migration or purge recovery function.

Migration 016 revokes the internal `purge_open_event` resolver from the
executor role. The shared P2a ledger query therefore uses the pinned connection
owner for its read-only admission probe, before action sessions enter
`v3_derived_purge_executor`. This is an explicit exception to the design's
every-session-first-statement rule; mutation SQL stays restricted to the
executor and the migration's public functions. The action does not grant the
resolver or alter 016. Likewise, the external canonical receipt seal identifies
the reviewed artifact, while 016 separately authenticates its nested plan using
PostgreSQL's JSONB text hash; the receipt carries both identities.
The action also follows gate 3b's narrower definer-owner rule: the application
role itself, or a `CREATEROLE` role with `ADMIN OPTION` on it. Although 016 can
be installed by a different superuser, that alone does not satisfy this plan
gate; the action reports and refuses such an owner.

The fixed read-only status progress query also uses the connection owner so
`pg_stat_activity` exposes the recorded backend's PID and `backend_start`
together; the executor's view can mask the start time. Payload probes remain
under the executor. Status observes workers through Docker alone, avoiding the
lifecycle action's additional relation-size probes during a rewrite.

The competing-writer observation also uses a fixed owner `BEGIN READ ONLY`
query: the executor lacks `pg_read_all_stats`, so other roles' session state
and backend classification are masked (PostgreSQL 18 exposes backend XIDs to
all callers). Treating those masked client sessions as idle would be
unsafe; interpreting them as writers would never admit an ordinary connected
application pool. The owner observation preserves 016's exact predicate and
016 rechecks it inside each mutation. WAL directory size is measured with a
fixed container filesystem command because the executor cannot call
`pg_ls_waldir`; it receives no additional monitoring or filesystem SQL grant.
The data directory is obtained from the pinned container's `PGDATA` and
`postmaster.pid`, because the executor also lacks permission to read the
`data_directory` server setting. The PID must still have that working directory,
and its recorded start epoch (line 3, the postmaster's whole-second start time)
must be at most **5 seconds before**, and never after,
`floor(pg_postmaster_start_time())` from the live SQL session. PostgreSQL writes
the file's epoch as the postmaster starts and records the SQL start time later
in start-up, so exact equality is not guaranteed: production read `1792438533`
from the file and `1792438534` from SQL (plan run 39963522021 then stopped on
`data_directory_unresolved`; the earlier exact-equality rule is superseded).
Receipts record `postmaster_start_binding` with both epochs, the gap and the
tolerance. A file epoch after the SQL value, a larger gap, or any other
inconsistency or missing path stops the placement proof.

### Published Finder product survivors

After go-live the published `parallel_v1` generation owns both Finder
products. Applied migration 016's `purge_snapshot()` freezes and rechecks the
survivor counts of the four rewrite relations only, so the published Search
rows (`survivors.system_search`) are already proven unchanged against the
reviewed plan's frozen non-zero count by 016 itself. The published wide
`v3_derived.system_archetype` product lies outside that snapshot. 016 is applied
and is not edited; the action instead runs one fixed read-only executor query
(`PUBLISHED_SURVIVORS_SQL`; the executor already holds `SELECT` on both
relations) for the exact `parallel_v1` archetype row count and both published
product manifests (version, state, manifest SHA-256, `expected_rows`,
`published_at`).

- `plan` freezes that result as `reviewed_plan.published_survivors`, sealed into
  the plan and into 016's immutable request. In production it also requires both
  products to be `READY` and published with exact survivor rows equal to each
  product's verified `expected_rows` (Search from 016's snapshot, archetype from
  this read); otherwise it stops with `published_survivor_product_count_unproven`.
  The disposable rehearsal fixture publishes both Finder products on its
  surviving generation (see "P2d rehearsal"), so its plan runs the same
  requirement.
- `authorize` and `complete` compare a fresh read with the frozen proof
  immediately before their write and again after it; `verify-system-archetype-empty`
  checks before and after its read-only count.
- Every `delete-` dispatch compares at its first and final boundary, exactly
  where it rechecks 016's survivor snapshot. Drift is an integrity failure: the
  loop records `FAILED_STOP` with `integrity_failed: true`, records no logical
  completion and keeps the writer fence for owner review.
- Every `rewrite-` dispatch compares before opening any fence and again after
  `VACUUM (FULL, ANALYZE)` returns, before `REWRITE_VERIFIED`. Drift there records
  `FAILED_STOP` with `rewrite_committed: true`, `integrity_failed: true` and the
  start event, the shape 016 accepts for owner-acknowledged writer restoration;
  the rewrite is not verified and writers stay fenced.
- Recovery of a **committed** rewrite (changed filenode) applies the same check
  before `REWRITE_VERIFIED`, whichever path resolves it: the dispatch's own
  trap (for example when `VACUUM` committed but its response was lost), a
  matching `rewrite-` re-dispatch, or `restore-services`. A refusal there is
  recovery's existing integrity `FAILED_STOP` with `rewrite_committed: true`, so
  the rewrite is never verified and writers stay fenced for owner review.

A plan without `published_survivors` cannot drive any of these phases
(`published_survivor_proof_missing`). Rolled-back rewrite recovery, batch
recovery, writer restoration and `abort-relation-` do not read it.

The F2d code identity includes the new shared helpers and modified actions.
Existing accepted-release attestations are not silently regenerated: the normal
reviewed attestation gate remains required before executing those changed
workers. None of this adds a PostgreSQL restore/PITR recovery route.

## Protected workflow dispatch runbook

Use [V3 production derived purge](../../.github/workflows/v3-production-derived-purge.yml)
on `main` for every governed phase. It accepts manual dispatch only and requires
the protected `v3-production` environment approval. After approval it re-fetches
`main` and refuses unless the dispatched commit is still the exact current head.
If `main` moves while approval is pending, start a new dispatch from its current
head and review the resulting source identity. Inputs never select a host, path,
SQL statement, or arbitrary relation.

The [operations workflow](../../.github/workflows/chatgpt-ed-new-ops.yml) also
offers `v3-derived-purge-plan` and `v3-derived-purge-status`. These invoke only
the read-only `plan` and `status` modes. An ops plan is diagnostic evidence;
later protected phases accept plan artifacts only from successful `plan` runs
of the dedicated purge workflow. No mutating purge mode is available in ops.

| Input | Meaning and admission |
| --- | --- |
| `mode` | One literal choice from the action's closed list: `plan`, `status`, `authorize`, `verify-system-archetype-empty`, the four each of `preflight-`, `copy-`, `swap-`, `swap-back-`, `drop-`, `abandon-` and `abort-relation-`, `restore-services`, or `complete`. Relation suffixes are only `system-search`, `economy-opportunity`, `body-mechanics`, and `system-rating-vector`. `delete-` and `rewrite-` are disabled and refused. |
| `confirm_target` | Must equal `ed-finder-prod/nb79a3d.mevnode.com` exactly. |
| `plan_run_id` | Digits-only ID of the successful dedicated-workflow `plan` run on `main`. Required for every mode except `plan` and `status`. |
| `plan_sha256` | The plan receipt's 64-character lowercase hexadecimal `content_sha256`, reviewed with that run's artifact. Required with `plan_run_id`; this is the external receipt seal, distinct from the nested database `plan_sha256`. |
| `verification_run_id` | Digits-only ID of the successful dedicated-workflow `verify-system-archetype-empty` run on `main`. Required for copy, swap, swap-back, drop, abandon, abort, `restore-services`, and `complete`; refused for `preflight-`. |
| `verification_sha256` | The successful exclusion-verification receipt's 64-character lowercase hexadecimal `content_sha256`. Required with `verification_run_id`. |
| `rehearsal_run_id` | Digits-only ID of the successful [V3 derived purge rehearsal](../../.github/workflows/v3-derived-purge-rehearsal.yml) `one_percent` run on `main`. **Required for `plan`** and refused for every other mode. |
| `rehearsal_sha256` | That run's reviewed `rehearsal-receipt.json` `content_sha256` (64 lowercase hex). Required with `rehearsal_run_id`. |
| `acknowledge_failed_stop` | Optional digits-only ledger event sequence, admitted only for `restore-services`. After owner review it acknowledges the exact integrity-failed stop for writer restoration; it authorizes no repair or continuation past that stop. |
| `wall_clock_seconds` | Required integer `copy-R` chunk-loop budget, 1–9000 seconds. Leave blank for every other mode. It is not a phase timeout or a maintenance-window estimate; long phases have their own reviewed bounds (7,200 s; verify 19,200 s) and start only when the 19,800 s dispatch budget still covers them. |

For each imported artifact the workflow authenticates GitHub's run identity,
the same repository and workflow, `main`, successful completion and producing
mode. The receipt's `source_git_sha` must equal that successful source run's
`head_sha`; its seal must equal the supplied SHA-256. A copied or
edited receipt, an ops-workflow artifact, a failed run, or the wrong producing
mode is refused. The fixed artifact names are `v3-derived-purge-plan` and
`v3-derived-purge-verification`, each containing `receipt.json`. Keep the reviewed
plan run ID and seal, then the verification run ID and seal, with the operator's
phase record.

The rehearsal receipt is authenticated the same way against the dedicated
rehearsal workflow: GitHub must report that run as a successful
`workflow_dispatch` on `main` of this repository, and the receipt's
`source_git_sha` must equal its `head_sha`. Its artifact is named
`v3-derived-purge-rehearsal-<run id>-<attempt>`, so the workflow downloads every
attempt's artifact and reads `rehearsal-receipt.json` only from the attempt
GitHub reports as the run's successful conclusion. The authentication step then
stages exactly those bytes, verifies the seal and the supplied SHA-256, and the
receipt module requires `status: success`, empty failures, `scale: one_percent`,
JSON boolean `gate_10_crash_rehearsal_passed: true`, verified clean-up, the
committed lifecycle proportions and the same action/harness/migration-set code
identity that will run the plan. Only those staged bytes travel to the host,
where the action repeats the same validation before copying the figures into
the plan and sealing it. Only `authorize` requires the plan's source SHA to equal the current
execution SHA. After authorization, later phases and recovery retain the
original immutable plan and exclusion proof even if `main` advances; each new
dispatch still executes exact current `main`. This preserves recovery access
without substituting a new plan for the existing ledger requests.

After installation and all design execution gates have passed, dispatch in this
order, reviewing each receipt before approving the next phase:

1. `plan` in the dedicated workflow, with the reviewed `rehearsal_run_id` and
   `rehearsal_sha256`. Review its complete sealed receipt, exact
   targets/source/schema identities, stopped workers, unchanged pointers,
   published counts (including `reviewed_plan.published_survivors`), the
   rehearsal figures, storage/WAL evidence and freeze-age horizon. Retain the run
   ID and `content_sha256`.
2. `authorize` with that `plan_run_id` and `plan_sha256`. Authorization requires
   a plan no older than one hour from the exact current execution head; an expired
   plan or a source change needs a fresh plan and review. Both the workflow
   (before SSH) and the action refuse a plan without the reviewed one-percent
   copy-route rehearsal binding (`plan_rehearsal_figures_required`):
   authorization binds the plan to every later phase, so a plan without the
   reviewed `copy` block (sourced `reviewed_rehearsal:<receipt sha>` for every
   relation) could authorize but never copy.
   This marks both immutable targets `FAILED` without deleting payload.
3. `verify-system-archetype-empty` with the same plan inputs. Review and retain
   its successful sealed artifact, run ID and `content_sha256`. An archetype or
   cluster target row stops the purge; there is no delete mode for those tables.
4. For each relation in order (Search, opportunity, mechanics, rating vector):
   `preflight-R`, then `copy-R` (re-dispatch until the receipt says
   `copy_verified_ready_for_swap`), then `swap-R`, then `drop-R` the same day.
   Supply both authenticated artifact pairs to every dispatch except
   `preflight-R` (plan only). See "Copy-and-drop route" above.
5. (The former `delete-`/`rewrite-` steps are disabled.)
6. `complete` with both artifact pairs. Review its completion receipt: zero
   target rows alone do not establish reclamation or completion; 019's
   `COMPLETED` does.

The reviewed **copy-route** rehearsal figures (receipt schema
`ed-finder/derived-purge-rehearsal/v3`) must be present in the sealed plan
**before** any copy dispatch can run. The protected workflow transports the
authenticated rehearsal receipt to the plan invocation as described above; a
plan without it is refused by the workflow, and `authorize` refuses a plan that
lacks the binding. The 2026-10-24 receipt (run 40074011789, schema v2) measured
the disabled delete/rewrite route and is refused (`rehearsal_schema_invalid`):
a new one-percent copy-route rehearsal is required. Do not bypass the protected
workflow or edit a downloaded plan. Per relation, review
`copy.relations[relation].required_free_bytes_before_copy`, `copy_peak_bytes`,
`copy_peak_source` and its `rehearsal` figures (`copy_rows_per_second`,
`long_phase_seconds_max`, `long_phase_fits_reviewed_timeout`); JSON relation
keys use underscores.

On interruption, inspect `status` first. An open writer/service fence requires
`restore-services`, using both artifact pairs, before a fresh destructive phase;
the action cancels and resolves any recorded batch or rewrite before restoring
writers. Supply `acknowledge_failed_stop` only after the owner's explicit review
of the exact integrity-failed event. To abandon an autovacuum fence, use the
matching `abort-relation-<relation>` with both artifact pairs after restoring any
orphan writer fence. Abort requires its rehearsal-derived release budget and
sufficient headroom; it leaves the relation unreclaimed and `complete` blocked.
Resume from fresh status/count evidence and a reviewed plan through the matching
delete or rewrite path. The detailed recovery rules below remain mandatory.

The workflow holds `v3-production-application-authority` concurrency and the
job's `chatgpt-ed-new-ops` concurrency with cancellation disabled. It polls and
waits for the remote action to exit, including budget expiry or `FAILED_STOP`,
so those fences remain held for the entire phase. The host purge lease and
durable ledger independently protect against runner or SSH loss. Only the
independent rewrite monitor may outlive the controller, as described below.
Every run tees its JSON receipt and attempts receipt upload even on failure;
missing receipt files fail the upload, and retention is 180 days. Retain and
review those receipts before proceeding. The general artifact is
`v3-derived-purge-receipt`, containing `receipt.json`; only successful plan and
exclusion-verification runs publish the corresponding reusable sealed artifact.

The job timeout is 360 minutes, GitHub's ceiling for a hosted job (180 until
2026-10-30). A `copy-R` dispatch admits at most 19,800 seconds of work (the
chunk loop up to `wall_clock_seconds`, then long phases that each start only
when the remaining budget covers their statement timeout — 7,200,000 ms, or
19,200,000 ms for verify — plus a 300 s margin), leaving at least 30 minutes
for set-up, cleanup and upload. Before SSH the workflow checks that every
statement the copy route executes (`v3_purge_copy.PHASES`) and every phase
timeout a plan seals (`copy.phase_timeouts`) fits its envelope: 19,200,000 ms
for verify, 7,200,000 ms for every other phase
(`copy_phase_timeout_outside_workflow_budget`). A plan's legacy
`rewrite[relation].statement_timeout_ms` (a `VACUUM FULL` estimate; the
2026-10-24 receipt's Search figure is 30,659,000 ms) no longer gates admission,
because the copy route never runs a `VACUUM FULL`; the one statement that could
still use it — the recovered `ANALYZE` for an open 016 rewrite during
`restore-services` — is refused by the action itself above 7,200,000 ms
(`rewrite_timeout_outside_workflow_budget`). These are controller limits, not
rehearsal throughput or outage estimates.

Delivery follows the schema migration workflow's bounded source-bundle precedent:
a bounded `git archive` of the committed operator/release helpers, production
authority and migrations, plus a credential-free `.git` tree, is sent as a tar
bundle over pinned SSH from trusted `main`. The action verifies the Git SHA and
committed backup-wrapper blob; the sealed JSON artifacts retain their separate
content authentication. The protected bundle is extracted into a root-owned
temporary `/run/edfinder-v3-purge-source.XXXXXXXX` tree; that tree remains until
reboot so an independent rewrite monitor can still verify and load its source
after controller loss. The ops read-only source tree is removed after its
action exits.
No repository credential is sent to the host. `GITHUB_RUN_ID` and the remote
controller PID/start identity bind action liveness to the polling controller.

## P2d rehearsal

Implementation base: `ebe88b78ec66f9eeacc1576a5d3b535a312be166` (merged P2c,
PR #822). Owner decision 2026-10-16 selects Contabo for a **disposable**
PostgreSQL 18 rehearsal. Contabo is not production. The rehearsal runs only on
the dedicated `purge-rehearsal` runner (its own `rehearsal` user, the only
`docker` group member, no default labels); the three Codex runners have no
Docker access and cannot receive the job. Use [V3 derived purge rehearsal](../../.github/workflows/v3-derived-purge-rehearsal.yml)
on current `main`, first with `scale: smoke` (300,000 systems, about 0.15%), then with
`scale: one_percent` (about 2 million systems). This is manual dispatch only;
merging the harness never dispatches it. It has no secrets, production target,
SSH transport, or deployment step. The workflow pins the dispatched main SHA
and refuses if main has advanced before source verification.

Before checkout, the runner must reach its local Docker daemon without privilege
elevation, have no existing rehearsal container (including stopped containers),
and have at least **150 GB** free on the Docker data root for smoke or
**175 GB** for one_percent. The real action keeps its production admission in
the fixture — the 100 GB floor, and before each long copy phase also the 32 GiB
`temp_file_limit` reservation and `max_wal_size` (about 135 GB here) — on top of
the fixture's own data; these minima refuse a runner that could never pass it.
They are admission minima, not proof that the complete dataset fits. Every
rehearsal has its own labeled container and volume. A global concurrency group
prevents overlapping dispatches; cancellation of an earlier run is disabled.
The 720-minute job limit bounds seeding, the measured copy-and-drop journey and
crash recovery. The final `if: always()` cleanup removes only this run's
labeled containers and volumes and verifies their absence. If a runner dies
before cleanup, a later dispatch refuses the leftover container; inspect its
run identity and evidence before removing it through a reviewed
runner-maintenance procedure. Cleanup does not touch unrelated Docker resources.

**Receipt schema v3 (copy-and-drop route, Codex 4379797621).** The harness
applies the **whole** committed migration manifest (016 and 019 included, as
production's ledger holds it), grants the executor `SET` on `temp_file_limit`
(the reviewed prerequisite in "Preconditions" above), and creates synthetic
BUILDING and VALIDATING targets plus a published survivor. It derives the four
payload relations' generation proportions from the committed
[2026-10-10 lifecycle receipt](evidence/2026-10-10-v3-derived-lifecycle-status-receipt.json),
records that receipt's SHA, and leaves archetype/cluster target tables empty.
Because 019's `verify` recounts copied rows per Ratings chunk, the seed records
each generation's `build_chunk` receipts from its rows while it is still
BUILDING (systems, physical bodies, eligible opportunities) and the published
Search product's `search_build_chunk` receipts before it is READY, exactly as
the builders do. It applies production's planner statistics to
`economy_opportunity.system_id64` (`STATISTICS 1000`, `n_distinct = -0.13`) so
the opportunity swap recalibrates them and a swap-back restores them, and it
completes one WAL segment so the archiver position the copy route reads exists.
v1 and v2 receipts measured the disabled delete/rewrite route and are refused.

**Published survivor population (since receipt schema v2, ROADMAP step P
reopened gate 1).** Production's surviving generation `ratings_v4_prod_p4_parallel_v1`
has held both published Finder products since go-live (publish run
39933842811): about 198.5 million `system_search` and 198.5 million
`system_archetype` rows, one per system, `READY`/`VERIFIED` with `published_at`
set. The 2026-10-10 receipt predates that, so its survivor Search count is
zero. The fixture now reproduces the published population at the same
proportion: after the survivor's ratings base is published, it registers
`system_search` (`v3-system-search-2`) and `system_archetype`
(`v3-archetype-4`) products with `expected_rows` equal to the survivor's
systems, inserts one synthetic row per system into each (all guards,
constraints and the 011 partial ranking indexes active), marks them
`READY`/`VERIFIED`, and publishes both in one transaction through 015's
`v3_meta.publish_derived_product`, which writes the publication audit rows.
The seed then proves both products, both audit rows and both `v3_app` views
before any action runs (`seed_survivor_publication_unproven` otherwise).
Because the fixture now has published products, the rehearsal `plan` runs the
production survivor proof (`published_survivors(..., require_published=True)`)
instead of freezing an empty state. The target generations' payload is
unchanged.

At `one_percent` (proportion 2,000,000 / 198,528,286) the journey fixture holds:

| Relation | `p4` (target) | `opt1` (target) | `parallel_v1` (survivor) |
| --- | ---: | ---: | ---: |
| `system_search` | 0 | 2,000,000 | 2,000,000 (published) |
| `system_archetype` | 0 | 0 | 2,000,000 (published) |
| `economy_opportunity` | 311,266 | 7,454,873 | 7,454,873 |
| `body_mechanics` | 247,406 | 5,819,919 | 5,819,919 |
| `system_rating_vector` | 49,746 | 2,000,000 | 2,000,000 |

Crash fixtures use the same rule at smoke scale (300,000 survivor Search and
archetype rows each). Smoke was 100,000 systems until 2026-10-27: at that size
the economy_opportunity swap's plan proof cannot hold, because a hash join over
the whole small opportunity table is cheaper than the nested loop over
`economy_opportunity_pkey` that the production-size chunk read needs (smoke run
40484503505 refused `n_distinct_recalibration_plan_unverified`; on PG 18 the
plan flips between 100,000 and 200,000 systems). The seed also analyses the
tables before each build-receipt join, which otherwise ran for more than 30
minutes at 200,000 systems.

**The journey.** After `plan`, `authorize` and `verify-system-archetype-empty`,
each relation runs in 019's order through the real action: `preflight-R`;
`copy-R` re-dispatched until `copy_verified_ready_for_swap`, every dispatch
sampled for data-volume free bytes and, through a read-only observer login
holding `pg_monitor`, the server's temporary files (`pg_ls_tmpdir()`); `swap-R`
while a second observer login repeatedly reads the Finder surface that the swap
locks (the published Search view, the published generation's opportunity or
mechanics rows, or the economy-rating view over the vector) and records each
read's latency; `drop-R`. Then `complete`, and the harness proves no target
row remains. Each sampler and the reader open their login before the action
starts and close it after it exits. The rehearsal's Finder smoke reads the
application views in the database (the fixture runs no API).

Per relation the receipt records raw: copied and target rows, live bytes
before, the staging copy's bytes after verification, the copy's free-space peak
(maximum drawdown across all of its copy dispatches, WAL included), the sampled
temporary-file peak and the bytes written to temporary files, freed bytes,
chunk statement seconds (copy rows per second), index-build, VACUUM FREEZE,
verify and FK-validation seconds, WAL bytes per phase (chunk, index build,
VACUUM FREEZE, verify, FK validation, drop), the swap statement's lock hold and
attempts, the worst Finder read latency during the swap and the read count,
and the drop's statement time. The `production` block divides whole-relation
work (seconds, bytes, WAL) by the recorded proportion, keeps rates and the
catalog-only swap figures raw, and sets `required_free_bytes_before_copy` =
100 GB + 1.5 × the extrapolated copy peak; `margin_applied` is kept for review
only (the controller applies the margin at admission, once).
`long_phase_fits_reviewed_timeout` is true only if twice the longest
extrapolated long phase is within the 7,200 s statement envelope at
rehearsal-host speed (it is part of the sealed maths and is not changed).

Production authority (`one_percent`, status success, cleanup verified, all
crash scenarios passed, current code identities or a pinned
`ACCEPTED_REHEARSALS` entry whose files are unchanged) additionally refuses a
long phase outside that envelope at production host speed — verification
scaled by the 2026-10-28 benchmark factor (0.31695) for receipts measured in the
benchmarked image, every other phase unscaled
(`rehearsal_long_phase_exceeds_reviewed_timeout`; the plan's `rehearsal` block
records `verify_speed_factor`, `production_long_phase_seconds` and
`accepted_before_gate_change` for review),
a Finder read stall above the API's 15 s read timeout
(`rehearsal_finder_stall_exceeds_api_timeout`), and a synthetic Search copy
narrower per row than production (`rehearsal_search_survivor_width_unrepresentative`:
the larger of the 2026-10-10 receipt's 405.6 and the owner-reported 2026-10-23
175 GB / 397,056,572 rows ≈ 440.7 bytes per row; the 2026-10-24 rehearsal's
compacted survivors measured about 514).

**Crash scenarios (gate 10).** Each runs on a fresh marked fixture at smoke
proportions (tiny in local checks), copies, swaps and drops `system_search`
through the real action, then interrupts `economy_opportunity` — the relation
whose swap also recalibrates statistics — and must then finish every relation
and `complete`, with published fingerprints and pointers unchanged and the
catalog agreeing with the ledger at every observation:

| Scenario | Interruption (observed first, then applied) | Must resume as |
| --- | --- | --- |
| `copy_chunk_client_killed` | the second chunk's statement paused after its 019 call, before commit; wrapper and psql killed | exactly one committed chunk; `copy-R` continues from the ledger |
| `copy_postgres_restart` | same pause; `docker restart --time 0` | postmaster restarted; one committed chunk; the first `copy-R` refuses `wal_archive_lag_unknown` (recorded as `restart_archive_refusal`), one WAL segment is completed, then `copy-R` continues |
| `index_build_backend_terminated` | index build paused after building; `pg_terminate_backend` | no `INDEXES_BUILT`; `copy-R` rebuilds |
| `verify_watchdog_cancel` | verify paused; the independent watchdog cancels on controller loss | receipt `copy_verify_interrupted` with `monitor_condition: controller_loss`, SQLSTATE 57014; `copy-R` verifies |
| `swap_committed_client_killed` | after the swap commits, before FK validation | `status` names `swap-R`; it resumes (`swap_resumed`) |
| `swap_back_committed_client_killed` | after the opportunity swap-back (with its statistics restore) commits | live table and options restored; `status` names `swap-back-R`; it resumes |
| `swap_back_and_reswap` | none: swap, swap-back, re-verify, swap | swap-back restores the original table and options; the re-swap equals the first |
| `abandon_and_recopy` | none: verified copy abandoned | staging gone; a fresh copy from `COPY_STARTED` |
| `drop_committed_client_killed` | after the drop commits | `drop-R` reports `retired_relation_already_dropped` |

**After a PostgreSQL crash or restart (production too).** A crash restart
discards the cumulative statistics, so `pg_stat_archiver` names no archived
segment and `copy-R` refuses `wal_archive_lag_unknown` (fail closed) until the
archiver has archived one. Nothing is changed by that refusal; re-dispatch once
the server's own WAL traffic has completed and archived a segment. The crash
rehearsal proves the refusal and then completes a segment itself (smoke run
40495068589 stopped here before the driver did).

Before any redispatch the driver waits until no backend still runs a copy
statement (the action itself refuses with `competing_purge_copy_backend_active`
while one does). Require JSON boolean `gate_10_crash_rehearsal_passed: true`.

Measurement and crash polling use a dedicated read-only observer login,
separate from the application role.
The real purge action runs in a separate disposable-marker override path;
ordinary invocation never enables that override. It requires both `--rehearsal-container` and a 64-hex-character
`--rehearsal-token`, and independently refuses production host identities. The
adapter accepts only the local default Unix Docker socket, a unique
`edfinder-purge-rehearsal-<32 hex>` name matching the container hostname,
`network=none`, no published ports, binds, devices or privileged mode, and a
single same-token dedicated `<container>-data` volume at `/var/lib/postgresql`.
Every execution is pinned to the inspected immutable container ID. The fixed
`edfinder_purge_rehearsal` database must carry the matching disposable-token
comment; arbitrary URLs and DSNs are not accepted. Rehearsal plans are marked
and cannot be consumed by the production adapter; their `copy` block is the
explicitly unmeasured `disposable_bootstrap_unmeasured` floor. A local
subprocess watchdog replaces systemd in this disposable environment, host
recovery state stays in the run's private directory, and the fault hooks change
only the named statement of the named scenario; all copy-route SQL is the real
action's. The **100 GB action floor remains unchanged**.

Review the uploaded artifact (retained **180 days**) for the source SHA, pinned
image digest, migration identities, production proportion, requested scale,
per-generation row counts, effective server settings (the synthetic
`archive_mode=on` with `archive_command=/bin/true` exercises the archive-health
checks without retaining an archive; autovacuum must remain enabled), every
action receipt, the per-dispatch free-byte, temporary-file and Finder-read
samples, the per-relation figures above, and every crash-scenario result.
Sampling is an empirical bound and may miss growth shorter than its interval.

Smoke is a harness check and never production planning authority. Only a
successful, reviewed `one_percent` receipt with all nine crash scenarios passed
can feed a production plan. Review the empirical estimates against fresh
production storage/WAL and writer-fence facts under the design's execution
gates. A rehearsal receipt does not authorize a production operation.

The plan-mode integration accepts both `--rehearsal-receipt <reviewed-path>` and
`--rehearsal-receipt-sha256 <content_sha256>` on
`scripts/operator/actions/v3-derived-generation-purge.sh plan`. These are an
integration contract for governed plan staging, not a manual production
invocation. The SHA is the sealed JSON's `content_sha256`, not a bytewise file
hash. The action verifies the `f2d_evidence.py` seal, explicit SHA, schema and
route, source and lifecycle identities, the executing action's script hash
plus the rehearsal harness hashes, the exact migration-set identity,
one-percent proportion, raw/derived arithmetic, the production bounds above
and the crash gate before sealing the plan's `copy` block
(`v3_purge_copy.plan_block`, every relation sourced
`reviewed_rehearsal:<content_sha256>`) and its `rehearsal` binding
(`route: copy_and_drop`). Missing arguments, stale identities, smoke receipts,
a false crash gate, changed bytes or inconsistent derived figures refuse
admission. The protected production workflow supplies these plan options from
its `rehearsal_run_id`/`rehearsal_sha256` inputs, preserving artifact
provenance as described under the dispatch runbook above. Do not supply an
edited plan or an unreviewed synthetic estimate. Because the recorded script and
migration-set identities must equal the code running the plan, the rehearsal
must be run on a `main` whose purge code identity is the one the plan will run.

## Action modes and receipt order

`scripts/operator/actions/v3-derived-generation-purge.sh` delegates fixed SQL
and receipt handling to `scripts/operator/lib/v3_generation_purge.py` and the
transaction adapter `scripts/operator/lib/v3_purge_transactions.py`, extended
by `scripts/operator/lib/v3_purge_delete.py` for delete/recovery orchestration,
`v3_purge_rewrite.py` and `v3_purge_rewrite_dispatch.py` for rewrite/recovery,
and `v3_purge_rewrite_monitor.py` for the independent watchdog. All three new
files participate in both the purge script hash and F2d operator-code identity.
Implemented modes are `plan`, `status`, `authorize`,
`verify-system-archetype-empty`, `complete`, `restore-services`, the four
relations' `preflight-`, `copy-`, `swap-`, `swap-back-`, `drop-` and `abandon-`
modes (`scripts/operator/lib/v3_purge_copy.py` and
`v3_purge_copy_dispatch.py`, both in the purge script hash), and the recovery
`abort-relation-` modes. `delete-` and `rewrite-` are refused with
`delete_rewrite_modes_disabled_by_copy_and_drop_design`. The four exact relation names
are `system-search`, `economy-opportunity`, `body-mechanics`, and
`system-rating-vector`. Every other mode is unknown and fails closed.
These are action contracts for the protected dispatch above, not an instruction
to run them manually against production.

After installation and execution prerequisites have been satisfied, the order
is:

1. `status` reports unresolved ledger state first. An open batch, rewrite,
   service, writer, or autovacuum fence remains durable even if its backend or
   runner has died. Use the recovery procedures below for an interrupted batch
   or writer fence, including an open rewrite. Unknown state
   refuses mutation. Recovery mode and
   recorded backend identity come from a metadata-only snapshot before any
   payload counts or sizes are probed. Each relation is then probed separately;
   a relation locked by a live recorded `REWRITE_STARTED` backend, or whose
   probe reaches the lock timeout, reports `null` with a reason. A live
   `VACUUM FULL` therefore cannot prevent recovery status from being reported.
2. `plan` takes fresh read-only evidence for the two exact rejected generations
   and the retained published generation. It checks worker quiescence,
   pointers, row counts, sizes, data/WAL/tablespace filesystem placement,
   archive and slot health, the 100 GB reserve, freeze ages, wrapper hash and
   the gate-3b writer-fence ownership precondition. Missing or mismatched proof
   stops the plan. Retain the sealed JSON receipt and its `content_sha256`.
3. `authorize --plan PATH --plan-sha256 SHA256` authenticates the sealed,
   bounded-age plan and rechecks live identities before calling migration
   016's `begin_derived_generation_purge` in one transaction. Both immutable
   requests and both `FAILED` transitions commit together; no payload is
   deleted. It then checks unchanged pointers and published counts.
4. `verify-system-archetype-empty --plan PATH --plan-sha256 SHA256` checks the
   three cluster relations and the wide `v3_derived.system_archetype` table
   again. A target row stops the purge with `FAILED_STOP` evidence; it never
   grants a deletion path for those relations. Retain its sealed successful
   receipt and `content_sha256` as the exclusion-verification proof.
   This and `complete` authenticate the original immutable receipt without
   expiring it during a multi-day purge; only `authorize` admits a plan no older
   than one hour. The verification receipt likewise has no freshness expiry;
   all live phase gates still run again.
5. Delete the four relations in dependency order: Search, opportunity,
   mechanics, rating vector. Migration 016 enforces that dependency order. Each
   relation still needs a separate verified physical rewrite and restored
   autovacuum fence before progressing to the next relation. Every destructive mode requires
   `--verification PATH --verification-sha256
   SHA256`, authenticating the sealed successful exclusion-verification
   receipt against the immutable reviewed-plan identity and both current
   ledger purge IDs. The delete and recovery procedures below apply.
6. `complete --plan PATH --plan-sha256 SHA256 --verification PATH
   --verification-sha256 SHA256` requires that same proof and refuses until every target
   payload count is zero, pointers and exact published counts match the plan,
   FKs are valid, fences are closed, and all four relations have
   `REWRITE_VERIFIED` evidence. It passes the completion receipt to migration
   016's `complete_derived_generation_purge`; zero rows alone never prove
   completion.

The action pins CPython 3.14, host/FQDN, Docker default context, container,
database and user, and verifies installed migration 016 against the committed
manifest. Sessions enter the restricted executor role and use fixed bounded
SQL with short lock timeouts. Mutating modes first check the shared P2a state
and hold the non-blocking host purge lease throughout the action. A bounded
wait for competing backend XIDs tolerates momentary background work; expiry
refuses the transaction and records the wait rather than weakening 016's
competing-writer check.

Receipts are JSON-only, use the canonical F2d content seal, and include the
design's source/migration identities, targets, pointers, workers, row counts,
storage/WAL/freeze facts, timeouts, transaction outcome and explicit write
flags. Unproven outcomes are `null`. `status` also reports the next admissible
mode, open-fence deadlines and observable backup skips. Its optional
`--verification PATH --verification-sha256 SHA256` inputs authenticate the
exclusion-verification proof against `reviewed_plan_sha256` and both purge IDs
in the current ledger requests. Without that proof,
`system_archetype_verification.status` is `not_proven`, and after authorization
the next admissible mode remains `verify-system-archetype-empty` rather than
advancing to deletion. Neither a receipt nor
a successful read-only mode substitutes for the remaining owner execution
gates, protected workflow, or disposable crash rehearsal.

P2b1 samples live XID/MultiXact rates over five seconds, retrying at most three
times if a vacuum moves a MultiXact baseline. Its conservative planning horizon
is 24 hours with ceilings at 80% of each effective freeze limit, including
TOAST. These are authorization evidence, not rehearsal-derived execution
budgets: execution must bind remaining dispatch/rewrite time to the reviewed
cadence
before opening a fence. Exact-count SQL is bounded at 45 minutes, the controller
at one hour, and the competing-writer grace at 30 seconds with one-second SQL
probes. The 016 function-local timeout settings are unchanged. Host gates are
refreshed after long count scans before a transaction writes. Backup skip
observations cover at most the latest 1,000 journal entries in seven days;
unavailable journal evidence is `null`.

016 has no dedicated exclusion-verification function or event kind suitable
for successful exclusion verification: its existing kinds represent failures,
recovery, or phases with their own mandatory verifiers. The action therefore
uses the sealed successful receipt above without modifying 016. It counts the
four exclusions directly and uses the public `purge_record_event` function for
authenticated `FAILED_STOP` records. The summary view is
`v3_app.system_archetype_summary`; 016 grants the executor no access to
`v3_app`, so the action omits the view count and retains the direct target-row
check against `v3_derived.system_archetype`. It never supplies an archetype or
cluster deletion capability. Completion relies on 016's `REWRITE_VERIFIED`
events, whose verifier already proves the rewritten filenode and trailing
`ANALYZE`; P2b1 does not synthesize those events.

## P2b2a delete dispatch and stopping (disabled mode; recovery description)

`delete-R` is disabled by the copy-and-drop design. This section remains
because `restore-services` and `abort-relation-R` still resolve the fences a
delete would have opened, and because the rehearsal harness of the superseded
route documents what it measured. It does not authorize a manual production
invocation.

A `delete-<relation>` dispatch requires both authenticated artifacts: `--plan
PATH --plan-sha256 SHA256` and `--verification PATH --verification-sha256
SHA256`. Its `--wall-clock-seconds` budget defaults to 300 seconds and accepts
1–1800 seconds. `--controller-pid` and `--controller-run-id` (matching `GITHUB_RUN_ID`)
bind its lifetime to the controller; the controller PID/start ticks must remain
alive. `--writer-mode=read-only` is the only accepted writer mode. The
launcher waits for the loop to exit. It holds the non-blocking purge lease
`/run/lock/edfinder-v3-derived-purge.lock` through cleanup, and also holds
`/run/lock/edfinder-v3-pgbackrest-schedule.lock`; a running pgBackRest backup or
verify process refuses admission. `authorize` and `complete` also use the
schedule lock/process gate. A scheduled backup that overlaps the lease uses
the installed wrapper's skip path; retain the skip observations in the receipt.

A matching unresolved `BATCH_STARTED` is resolved first from its durable key
range and database counts, after cancellation of its recorded live backend
through `v3_meta.cancel_purge_batch` and a bounded wait. PID reuse is checked
with `backend_start`. A different relation's open batch or autovacuum fence
refuses the dispatch. An open writer/service fence from an interrupted
controller requires `restore-services` before a new delete dispatch.

This restoration requirement applies even when no batch remains open, and to
every new mutating phase: `authorize`, `complete`, `delete-`,
`abort-relation-`, and new `rewrite-` phases. A new phase never adopts
a writer or service fence left by another dispatch. Restore the interrupted
dispatch first; aborting an autovacuum fence cannot leave application writes
disabled.

The action opens or adopts the relation's `AUTOVACUUM_DISABLED` fence through
016, preserving the ledgered prior heap and TOAST settings. Adoption remeasures
XID and MultiXact ages against the original ceilings; it never resets the
fence's clock. Before opening or adopting a fence, and before every batch, the
projected time to the nearer heap or TOAST XID/MultiXact ceiling must cover the
relation's **remaining target rows divided by
`reviewed_plan.delete[relation].rows_per_second`, plus its reviewed
`rewrite_allowance_seconds`**, and at least this dispatch's budget plus 65
seconds. The throughput must account for the planned cadence across dispatches.
The plan generator records a conservative fallback of one row per second with
`rows_per_second_source: conservative_fallback`; rehearsal may supply a measured
or configured cadence. It supplies no rewrite allowance: rehearsal must add that
relation's allowance before sealing and reviewing the plan. Missing or invalid
horizon fields refuse with `autovacuum_fence_horizon_not_reviewed`; the action
never invents a rewrite time. The receipt records the remaining horizon and each
scope's projected deadline. A horizon that does not fit refuses with
`autovacuum_fence_deadline_unsafe` and recommends `rewrite-<relation>` when fresh
counts prove the relation logically empty, otherwise `abort-relation-<relation>`.

It enables the selected writer fence with
`purge_set_writer_fence`, commits that change, recycles the application role's
other sessions with `purge_recycle_writer_sessions`, then probes a fresh login
and records `purge_verify_writer_fence`. An already verified fence for this
active dispatch may be reused. The API stays up, reads continue, and application
writes fail closed during the fence. The exact running write-capable container
set comes from `deploy/v3-production/target-authority.json`, including container
IDs, and is retained in root-owned host state. No containers are stopped under
option (b). An authority-listed API slot removed by the deployer or never created
at bootstrap counts as stopped only on Docker's exact name-specific
`No such object` exit. Other inspect failures, malformed or mismatched identities,
and running application containers outside the authority refuse execution.

Before every small batch, the action records and checks all of the following:

- Data-filesystem free bytes cover **100,000,000,000 bytes plus 1.5 times the
  relation's per-batch peak-growth reservation**. The authenticated plan may
  supply a rehearsal reservation; otherwise the receipt names the conservative
  fixed fallback of 900,000,000 bytes. The reviewed plan must supply each
  relation's batch limit; the plan generator proposes 1,000 rows. A missing
  reviewed bound refuses execution. That bound and 016's limit of 100,000 rows
  both apply. Both values are recorded in the receipt.
- `pg_wal` remains on that filesystem. No slot is inactive or has `wal_status`
  `extended`, `unreserved` or `lost`. The archiver's `failed_count` has not
  increased from the dispatch snapshot, and `last_failed_time` is no newer than
  `last_archived_time`. Delete and abort receipts measure physical `pg_wal`
  directory bytes for both `wal_before` and `wal_after`, using the same probe as
  plan/authorize; unavailable measurements refuse execution.
- Named workers are stopped, no autovacuum is running on the relation or its
  TOAST relation, and the recorded controller is alive.
- The bounded competing-writer wait finds no other backend with a
  `backend_xid`; the receipt records the wait. Read-only snapshots do not count
  as writers.

016's `purge_start_payload_batch` durably records the backend and deterministic
key range before `purge_derived_payload_batch` executes on that same session.
A batch monitor can cancel only that recorded backend through
`cancel_purge_batch` if free space crosses the floor. Every later iteration
rechecks the gates. A failed gate records `FAILED_STOP` with its measurements
and starts no further batch. Controller loss stops after at most the current
batch. A wall-clock stop also preserves all committed batches; the next
dispatch resumes from database counts. Published-survivor drift (including
the published archetype product's `published_archetype_survivor_count_drift`),
pointer change, retained-metadata drift, FK/index failure, or an unknown integrity or
FAILED_STOP recording outcome sets `integrity_failed: true`.

When target rows reach zero, the receipt recommends `rewrite-<relation>` and
leaves the autovacuum fence open. Dispatch the separately reviewed rewrite next. Zero rows reclaim no physical disk by
themselves and never satisfy `complete`.
Successful delete receipts include the final boundary's validated integrity
checks in `fk_check` and a fresh relation/index/TOAST size observation in
`relation_bytes_after`. An unavailable observation stops completion.

## Exit, signals and writer restoration

On normal exit, INT, TERM or HUP, cleanup asks the loop to stop after its
current batch and waits until it has exited. It resolves any open batch before
restoring the application role's writer default. Cleanup never releases the
host lease or restores writers while the loop is alive. After an
integrity-failed `FAILED_STOP`, cleanup restores nothing: the writer fence
remains open for owner review, while the durable ledger continues to block
other mutators after the process exits.
Cleanup also preserves the writer fence when local integrity evidence fails or
is unknown, even if recording FAILED_STOP errors. The receipt reports
`integrity_failed: true` and `failed_stop_recorded: null` when that commit is
unproven. A recording error after a non-integrity stop is likewise an unknown
outcome and refuses automatic restoration, including on INT, TERM or HUP.

Restoration uses the exact prior role value in `WRITER_FENCE_ENABLED`: set
`off`, or unset with `RESET`. `purge_set_writer_fence` commits that restoration
with an unverified record; only then does cleanup recycle the role's sessions,
probe a fresh role connection for `off`, and append the verification through
`purge_verify_writer_fence`. This second recycling step also replaces pooled
connections that reconnected while the fence was enabled. Only durable verified
restoration closes the fence. CPython 3.14 is mandatory; a missing exact runtime
returns the `python314_required` receipt before host/database access. Script
identity includes the committed pgBackRest wrapper so local drift refuses
admission. Each successful non-status receipt derives `wal_byte_delta` from its
before/after LSNs with `pg_wal_lsn_diff`; an unprovable delta fails closed.
After verified restoration, the receipt's canonical `writer_fence` reports the
restored state; `writer_restore` retains restoration details.

## Interrupted dispatch: restore-services

Inspect `status` and retain its evidence first. The idempotent
`restore-services` mode requires the authenticated plan and sealed exclusion
proof. It holds the same host and backup-schedule leases. It resolves any open
batch before restoring writers: cancel the exact recorded live backend through
016, wait until it is gone, then check the recorded key range and its closing ledger event. A successful
batch records `BATCH_COMMITTED` in the delete transaction itself; an open start
whose recorded backend has departed is therefore resolved as `BATCH_ROLLED_BACK`. It never assumes a missing client means
a rollback. An open `REWRITE_STARTED` is cancelled through
`cancel_purge_rewrite`, awaited until its exact backend is gone and neither
progress view shows the relation, then resolved by the rewrite procedure below
before writer restoration.

After an integrity-failed stop, restoration requires owner review and the exact
`--acknowledge-failed-stop=<event-sequence>`. Migration 016 (applied in
production on 2026-10-18, apply run 39113822236, with this amendment; the
earlier "amended, unapplied" wording is superseded) accepts the optional acknowledgement only on writer restoration. It must
name an existing `FAILED_STOP` with `integrity_failed: true` belonging to the
same plan (including a sibling request); missing, non-integrity, wrong-kind,
wrong-plan or enable-path acknowledgements refuse. The dedicated
`purge_set_writer_fence(uuid,boolean,bigint)` records it in
`WRITER_FENCE_RESTORED.operational_payload`; session recycling and fresh-login
verification preserve that payload. No synthetic failure or service event is
used. For a terminal failure after a committed rewrite, the acknowledgement
must also bind that relation's exact `start_event`; 016 proves its recorded
PID plus `backend_start` is gone and neither progress view shows maintenance
before permitting writer restoration. This resolves the earlier mismatch where
P2a treated `FAILED_STOP` as terminal but 016 still required rewrite verification
or rollback. It supplies no `REWRITE_VERIFIED` or autovacuum restoration and
keeps the original integrity stop intact. The trap never supplies owner
acknowledgement.

The original integrity `FAILED_STOP` remains untouched. P2a continues to refuse
other mutators on that event even after owner acknowledgement: an integrity
failure needs separately reviewed repair authority. Acknowledgement grants no
data repair or pointer-change authority, and the trap never supplies it
automatically. For restoration without an integrity failure, the two committed
steps and fresh-role verification above apply; already verified restoration is
a safe no-op. Under option (b) there are no stopped services to restart.
Quiesced-service restoration remains refused until a future owner decision and
implementation select option (a).

## Abandoning a relation: abort-relation

`abort-relation-<relation>` releases only that relation's autovacuum fence after
its authenticated plan/proof and recovery gates pass. The authenticated plan's
optional `reviewed_plan.delete[relation].autovacuum_budget_bytes` must carry a
valid rehearsal-derived measurement. The plan generator supplies no default: abort
is unavailable until P2d's rehearsal figures are included in the reviewed plan,
and missing evidence refuses with `autovacuum_budget_not_measured`. Invalid
values fail plan validation with `autovacuum_budget_invalid`. Measure free space
and the current heap-plus-index bytes first. Required headroom is the 100 GB floor plus
`max(autovacuum_budget_bytes, current heap-plus-index bytes)`. If that does not
fit, the receipt reports the shortfall and leaves the fence open; free space
must be added before retrying.

After that gate, the action restores the exact ledgered heap and TOAST
`autovacuum_enabled` states through `purge_set_relation_autovacuum` and appends
`AUTOVACUUM_RESTORED`. The preceding budgeted `FAILED_STOP` carries
`aborted: true` and measured headroom. The
relation remains physically unreclaimed. Fresh counts for both targets determine
the receipt's next mode: `delete-<relation>` when target rows remain,
`rewrite-<relation>` only when both counts are zero, and `status` when counts
are unproven. `complete` continues to refuse until verified physical rewrites
exist. Rewrite establishes a new autovacuum fence when adopting an aborted
relation, then verifies the physical rewrite before restoring it.


016 has two additional recovery constraints that this action preserves. Its
`AUTOVACUUM_RESTORED` function copies only the prior heap/TOAST options into
that event's payload, and its generic recorder refuses a caller-created
`AUTOVACUUM_RESTORED`; the design's abort/headroom evidence therefore lives in
the prerequisite `FAILED_STOP` instead of that closing event. Likewise,
`BATCH_COMMITTED` is appended only atomically by `purge_derived_payload_batch`;
recovery cannot invent it. A departed backend with a still-open start proves
that delete did not commit, and recovery records `BATCH_ROLLED_BACK`. The
recorded key range is checked before that resolution. Owner acknowledgement
uses only the dedicated 016 writer-restoration amendment described above; no
grant or data-mutation guard is broadened.


## Physical rewrite and recovery (disabled mode; recovery description)

`rewrite-R` is disabled by the copy-and-drop design; `restore-services` still
resolves an open `REWRITE_STARTED` exactly as described here.
Use the same authenticated plan and sealed exclusion proof as deletion. The
four relations follow the same FK order: Search, opportunity, mechanics,
rating vector. Both target counts must be zero, logical completion must be
ledgered, and no batch or different relation's autovacuum fence may remain open.
An existing autovacuum fence is adopted with its original age ceilings; an
aborted fence is re-established through 016 with exactly the delete age and
remaining-horizon checks. Writer mode remains option (b), verified read-only.
The host purge lease and pgBackRest schedule lock cover the entire dispatch,
backend, recovery and restoration. The persistent maintenance client inherits
both lock descriptors so they remain held if the wrapper disappears; the
monitor itself holds neither lock.

Before dispatch, P2d must supply and seal
`reviewed_plan.rewrite[relation].rewrite_peak_bytes` and
`statement_timeout_ms`. Relation keys use underscores. There is no default for
either field: missing peak refuses with `rewrite_peak_not_measured`, and missing
timeout with `rewrite_statement_timeout_not_measured`. The pre-start free bytes
must cover 100,000,000,000 plus 1.5 times that measured peak. The installed
wrapper hash and heap/index/TOAST/temp/WAL placement are rechecked. The plan's
existing delete `rewrite_allowance_seconds` must also cover the age horizon;
it does not substitute for the measured peak or statement timeout.

The physical phase has exactly three steps:

1. Commit `REWRITE_STARTED` through 016 on the maintenance backend, recording
   the relation OID, original filenode, heap/index/total sizes, PID and
   `backend_start`.
2. Start the independent monitor and wait for its readiness handshake, then
   issue the one fixed `VACUUM (FULL, ANALYZE)` command on that same backend
   under `v3_derived_purge_executor`. It runs outside a transaction, with a
   five-second lock timeout and the reviewed per-relation statement timeout.
3. After backend exit, verify changed filenode, `last_analyze` later than the
   start, exact published counts, pointers and retained metadata, valid FKs,
   indexes/triggers and measured sizes. Append `REWRITE_VERIFIED` through 016;
   its verifier restores the exact prior heap/TOAST autovacuum options.

A verified retry opens no new rewrite or autovacuum fence. An unresolved start
is observed through metadata before touching the heap. Re-dispatch refuses
while its recorded backend or either `pg_stat_progress_cluster` or
`pg_stat_progress_analyze` shows the relation. Once idle, an unchanged filenode
closes with `REWRITE_ROLLED_BACK` and permits a fresh normal rewrite. A changed
filenode causes recovered `ANALYZE`, verification that its timestamp trails the
start, and `REWRITE_VERIFIED` with `recovered: true`; it never runs a second
`VACUUM FULL`. A failed verification of a changed filenode records `FAILED_STOP`
with `rewrite_committed: true` and `integrity_failed: true`, preserving the
writer fence. Unknown integrity evidence likewise cannot reopen writes.

On INT, TERM or HUP, the trap cancels only the recorded backend through 016,
waits for it and both progress views to clear, and performs that same filenode
resolution before restoring writers. `restore-services` uses this identical
resolution. Existing orphan writer/service fences still require
`restore-services` before a new destructive phase. A matching `rewrite-R` may
first perform recovery only when its exact same-plan start and verified writer
fence remain open: it refuses an active backend, resolves an idle start and
restores the old writer fence before returning or starting any fresh phase.
Other relations, services and integrity stops cannot use that narrow recovery
entry. After an integrity stop,
automatic cleanup never restores writers; owner acknowledgement permits only
writer restoration, while P2a continues to block every other mutator pending
separately reviewed repair authority.

## Independent rewrite monitor

The action launches a transient root-owned `systemd-run` unit named
`edfinder-v3-purge-rewrite-<start-event>`, using exact CPython 3.14. Its config
and readiness handshake live under root-owned mode-0700
`/run/edfinder-v3-purge-monitors`; files are mode 0600. Source and its ancestors
must be root-owned and not group/world writable, and the unit verifies the
hashed script identity. A root-owned installed source tree is therefore an
execution prerequisite; this coding change installs nothing. The monitor is
pinned to the container ID, backend PID and `backend_start`, with PID/start-tick
identities for both wrapper and controller. It owns no lease and survives
controller disappearance.

Every 250 ms, with bounded database/host probes, it checks data-filesystem free
bytes against the 100 GB floor, physical `pg_wal` bytes and placement, slot
health, both archiver predicates (start `failed_count` must not rise, and
`last_failed_time` must not be newer than `last_archived_time`), and controller
liveness. No independent WAL-growth ceiling is imposed: WAL shares the monitored
filesystem and the owner floor applies. On a breach or controller loss it calls only
`v3_meta.cancel_purge_rewrite`; 016 authenticates the recorded backend and
appends `REWRITE_CANCEL_REQUESTED` with the condition. Cancellation is retried
until the backend exits, including the short pre-VACUUM idle window. Other
observations are read-only. The unit never signals another backend and exits
when the exact recorded backend disappears. It removes its config/handshake
on exit. Failure to establish readiness prevents VACUUM from starting.

The additional PG18 rewrite and monitor tests are isolated in
`tests/test_v3_purge_rewrite_pg18.py` and
`tests/test_v3_purge_rewrite_monitor_pg18.py` so their maintenance cost is visible rather
than hidden in the existing long purge module. They use disposable fixtures
and cover committed/rolled-back recovery, recovered ANALYZE and completion.
The fixture's catalog-maintenance suppression and bounded writer drain keep
background catalog autovacuum from racing 016's unchanged XID check.
