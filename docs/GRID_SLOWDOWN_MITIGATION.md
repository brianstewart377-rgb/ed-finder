# Grid backfill slowdown — mitigation runbook

## Diagnosis

The `build_grid.py` backfill rate is drifting downward:

```
batch 98:  944 r/s
batch 99:  937 r/s
batch 100: 930 r/s
batch 101: 921 r/s
batch 102: 913 r/s
batch 103: 906 r/s
batch 104: 898 r/s
```

~5% decay across 6 batches. Classic **dead-tuple bloat**: 53 M
UPDATEs against a 186 M-row table accumulate dead tuples faster than
autovacuum reclaims them, so subsequent scans touch more pages per
useful row.

ETA at current trajectory: 40h+ (and increasing).

## Path A — let it finish, curb the bleed (recommended if you don't
want to restart)

Paste the SQL below into `psql` on the Hetzner host **while the
script keeps running** — it does not take exclusive locks.

```bash
sudo docker compose exec postgres psql -U edfinder -d edfinder
```

```sql
-- 1. Aggressive per-table autovacuum settings for `systems`.
--    Defaults are tuned for OLTP; a bulk-backfill workload needs
--    vastly more vacuum I/O budget.
ALTER TABLE systems SET (
  autovacuum_vacuum_scale_factor   = 0.01,   -- trigger at 1% dead (default 20%)
  autovacuum_vacuum_cost_delay     = 0,      -- never nap during vacuum
  autovacuum_vacuum_cost_limit     = 10000,  -- bigger I/O quantum per cycle
  autovacuum_analyze_scale_factor  = 0.02
);

-- 2. Reload config so new settings take effect immediately.
SELECT pg_reload_conf();

-- 3. Sanity-check: is autovacuum actually running on `systems`?
--    dead_ratio > 0.1 with stale last_autovacuum = autovac starved.
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    ROUND(n_dead_tup::numeric / GREATEST(n_live_tup,1), 4) AS dead_ratio,
    last_autovacuum,
    last_analyze
FROM pg_stat_user_tables
WHERE relname = 'systems';

-- 4. If last_autovacuum is hours old AND dead_ratio > 0.1, the autovac
--    workers are starved. Check `postgresql.conf` / edit docker-compose
--    to raise:
--      autovacuum_max_workers = 6
--      maintenance_work_mem   = 2GB
--    then: sudo docker compose restart postgres   (script will reconnect)
```

### After the run finishes

1. Recreate the 3 indexes that were dropped to speed up the backfill.
   Use `CONCURRENTLY` so `systems` stays queryable:
   ```sql
   CREATE INDEX CONCURRENTLY idx_sys_grid      ON systems (grid_cell_id);
   CREATE INDEX CONCURRENTLY idx_sys_grid_pop  ON systems (grid_cell_id)
       WHERE population > 0;
   CREATE INDEX CONCURRENTLY idx_sys_grid_null ON systems (grid_cell_id)
       WHERE grid_cell_id IS NULL;
   ```

2. Reset the per-table autovac settings back to defaults (OLTP-friendly):
   ```sql
   ALTER TABLE systems RESET (
     autovacuum_vacuum_scale_factor,
     autovacuum_vacuum_cost_delay,
     autovacuum_vacuum_cost_limit,
     autovacuum_analyze_scale_factor
   );
   ```

3. One-shot cleanup after indexes are back:
   ```sql
   VACUUM ANALYZE systems;
   ```

4. Run `build_clusters.py` to populate cluster_summary / convex hulls.

## Path B — CTAS rebuild (~4-6h total, faster than waiting 40h)

Only use if you have >250 GB free disk on the Postgres volume.

```sql
-- 1. Drop the backfill script (Ctrl-C the runner).

-- 2. Rebuild systems with grid_cell_id baked in from the start.
CREATE TABLE systems_new (LIKE systems INCLUDING ALL);
INSERT INTO systems_new
SELECT s.*,
       -- inline the exact expression from build_grid.py here
       ((FLOOR(s.x / 10)::int + 4000) * 800000 +
        (FLOOR(s.y / 10)::int + 4000) * 1000   +
        (FLOOR(s.z / 10)::int + 4000))   AS grid_cell_id
FROM systems s;

-- 3. Atomic swap.
BEGIN;
ALTER TABLE systems     RENAME TO systems_old;
ALTER TABLE systems_new RENAME TO systems;
COMMIT;

-- 4. Recreate indexes concurrently, verify row counts match.
--    Drop systems_old only after verifying application health.
```

## Why NOT to run VACUUM FULL

`VACUUM FULL` takes an ACCESS EXCLUSIVE lock (blocks ALL queries) and
rewrites the entire heap — on 186M rows this is hours of downtime.
Regular (autovac) VACUUM is online and sufficient once it's given
enough I/O budget.
