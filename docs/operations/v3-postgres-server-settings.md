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
