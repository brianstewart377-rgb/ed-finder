# V3 production PostgreSQL server settings

This note records the owner-applied server settings of the retained production
PostgreSQL 18 container `edfinder-v3-phase4c-full-20260827_r5-postgres` on
`ed-finder-prod`, so the repository matches the server. Settings live in the
container's `postgresql.auto.conf` (written by `ALTER SYSTEM`); the host has
192 GB RAM, 32 logical CPUs, no container memory cap, and a 64 MB `/dev/shm`.

## Found on 2026-10-19

Every memory and checkpoint setting was at the PostgreSQL default for a 1.25 TB
database: `shared_buffers` 128 MB, `effective_cache_size` 4 GB, `work_mem`
4 MB, `maintenance_work_mem` 64 MB, `max_wal_size` 1 GB, `checkpoint_timeout`
5 min, `wal_compression` off. The 2026-09-15 autoanalyze of
`v3_derived.economy_opportunity` had also sampled `n_distinct` for
`system_id64` as 133,851 (true value about 200 million), which made every
chunk read of the opportunity join a 1.5 billion-row hash join and cancelled
the calibration probe at its 60 s statement timeout (runs 39155668281 and
39159487598).

## Applied by the owner, 2026-10-19 (no restart)

Planner statistics, before the probe re-run that succeeded (run 39186678592):

```sql
ALTER TABLE v3_derived.economy_opportunity ALTER COLUMN system_id64 SET STATISTICS 1000;
ANALYZE v3_derived.economy_opportunity (system_id64, derived_generation_id);
ALTER TABLE v3_derived.economy_opportunity ALTER COLUMN system_id64 SET (n_distinct = -0.13);
ANALYZE v3_derived.economy_opportunity (system_id64);
```

Server settings, applied with `ALTER SYSTEM` and `pg_reload_conf()` while the
complete read was running; confirmed active with `pending_restart = f`:

| Setting | Before | After | Why |
|---|---|---|---|
| `effective_cache_size` | 4 GB | 128 GB | the planner should prefer index paths on a 187 GB host |
| `work_mem` | 4 MB | 32 MB | sorts and hashes in the Finder reads and builders |
| `maintenance_work_mem` | 64 MB | 2 GB | VACUUM (ANALYZE) after the builds, index maintenance |
| `max_wal_size` | 1 GB | 32 GB | fewer checkpoints during the ~87 GB + ~66 GB insert-only builds |
| `checkpoint_timeout` | 5 min | 30 min | fewer full-page images in WAL; **trade-off:** after a crash, PostgreSQL replays WAL from the last checkpoint, so crash recovery can now take up to tens of minutes instead of a few (PITR is a separate restore path and does not shorten this) |
| `wal_compression` | off | zstd | smaller WAL for the archive stream to the Storage Box |

## Applied by the owner, 2026-10-19 20:35 (one restart)

After the complete read finished: `shared_buffers = 32GB` (was 128 MB) and
`dynamic_shared_memory_type = mmap` (the 64 MB `/dev/shm` would otherwise
bound parallel-query scratch space), then `docker restart --time 120` of the
database container. `pg_isready` reported accepting connections within a
minute, `pg_settings` showed both values active with `pending_restart = f`,
and `/opt/ed-finder-v3-runtime/health-check.sh` passed.

## Applied by the owner, 2026-10-20 09:30 (statistics only, Search build running)

The step 8′ Search build (started 2026-10-19 21:37 UTC, run 39328946864)
had completed only 5,617 of 198,529 chunks by 07:52 UTC — about 9 chunks a
minute, a ~15-day projection. `pg_stat_activity` showed each chunk spending
~4–6.5 s in the per-chunk guard query (`SELECT count(*) FROM
v3_derived.system_search s JOIN v3_derived.system_rating_vector v … WHERE
s.derived_generation_id=$1 AND v.chunk_ordinal=$2`). `EXPLAIN (ANALYZE,
BUFFERS)` showed why: `system_search` had last been analysed on 2026-09-21,
when it held only the one older generation's rows (`ratings_v4_prod_p4_opt1`;
`ratings_v4_prod_p4` never had Search rows — see the 2026-10-10 lifecycle
receipt), so the planner estimated **one**
row for the new generation `cfc25d36…`, drove the nested loop from
`system_search` (5.7 M rows and growing) and probed `system_rating_vector`
once per row (28.7 M buffer hits). Autoanalyze would not have fired until
~20 M rows had changed (10 % of 204 M), so the build was slowing down as the
table grew.

Owner-run at the host shell, same boundary as the 2026-10-19 operations:

```sql
ANALYZE VERBOSE v3_derived.system_search;
```

(1.2 s; 30,000 of 4,830,135 pages sampled.) The same `EXPLAIN` then started
from `system_rating_chunk_idx` (1,000 rows) with 1,000 primary-key lookups
into `system_search`: 6,510 ms → 5 ms. Because the builders force custom
plans (`plan_cache_mode = force_custom_plan`, #854), the running worker
picked the new plan up immediately: 2,289 chunks between 08:50:57 and
09:00:19 UTC (≈244 chunks/min, 27× faster), projecting completion around
21:40 UTC on 2026-10-20.

**Carry-forward for the Archetype build (8′, second product):**
`v3_derived.system_archetype` starts empty and has the same guard-query shape
against `system_rating_vector`, so run `ANALYZE v3_derived.system_archetype;`
once a few thousand chunks are in, rather than waiting for autoanalyze.
Before repeating it, check `greatest(last_analyze, last_autoanalyze)` in
`pg_stat_user_tables` — a manual `ANALYZE` is recorded in `last_analyze`, not
`last_autoanalyze` — and only re-run when neither is newer than the build's
start. A
code-side fix (an explicit `ANALYZE` early in the build, or rewriting the
guard to drive from the chunk index) belongs in the operator builders and
therefore waits for the post-publish operator-code release — it must not be
patched while the F2d identity is frozen.

## Changing or reverting these settings

There is no allowlisted operator action for PostgreSQL server settings; the
changes above were made by the owner at the host shell as an owner-authorised
production operation, not by the repository. Any change or reversal is likewise
an owner decision made the same way and recorded here afterwards (the
overrides live in the container's `postgresql.auto.conf`). Agents and
workflows must stop rather than mutate these settings.

## After the governed purge (ROADMAP step P)

`n_distinct = -0.13` is a fraction of the table's current row count. The
purge removes two of the three generations held in `economy_opportunity`
(about 1.5 billion rows today), so after it the same fraction would understate
the roughly 200 million distinct systems by about half. The purge's closing
steps must recalibrate the column from fresh counts, never a hard-coded
fraction: `n_distinct = -(distinct system_id64 / row count)` measured after
the purge (the retained generation holds about 49% of today's rows per the
2026-10-10 lifecycle receipt, so roughly 746 M rows and 198.5 M systems,
about -0.27, but measure it), or reset the option and re-ANALYZE with the
1000-row-per-bucket target; then confirm the chunk-read join still plans as a
nested loop over `economy_opportunity_pkey`.
