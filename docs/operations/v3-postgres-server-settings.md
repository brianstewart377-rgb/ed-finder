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
| `checkpoint_timeout` | 5 min | 30 min | fewer full-page images in WAL; crash recovery stays bounded by PITR |
| `wal_compression` | off | zstd | smaller WAL for the archive stream to the Storage Box |

## Planned (needs a restart; after the complete read, before the builds)

`shared_buffers = 32GB` and `dynamic_shared_memory_type = mmap` (the 64 MB
`/dev/shm` would otherwise bound parallel-query scratch space). The restart
is about thirty seconds; the complete read resumes from its checkpoint and the
API reconnects. Record the outcome here when done.

## Reverting

`ALTER SYSTEM RESET <name>` followed by `SELECT pg_reload_conf()` restores a
default; `postgresql.auto.conf` holds every override.
