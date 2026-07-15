# ED-Finder — Phase B Storage Recovery Receipt

**Date:** 2026-07-15
**Operator:** Claude (DeepSeek)
**Runbook:** `docs/operations/storage-recovery-runbook-2026-07-12.md`

## Context

A 6-day zombie importer container (`ed-finder-importer-run-86d07f046124`) was found
running `build_ratings.py --rebuild --workers 2 --chunk 5000`. It had frozen on
2026-07-08 after reaching 0.3% progress (195K / 74M systems) when Postgres killed
its connections. The container was stopped and removed before Phase B began.

## Baseline

| Metric | Value |
|--------|-------|
| DB size | **885 GB** |
| Disk free | **408 GB** (1.9T total, 78% used) |
| `idx_rat_dirty` size | 8,171 MB (~8 GB) |
| `ratings` table size | 392 GB (400 GB total with indexes) |
| `ratings` approx rows | ~190M |

## Step 1: DROP `idx_rat_dirty`

```sql
DROP INDEX CONCURRENTLY IF EXISTS idx_rat_dirty;
```

- Size dropped: 8,171 MB
- Disk free after: 416 GB

## Step 2: NULL `score_breakdown`

### Approach
PK keyset pagination — iterates through actual `system_id64` values (not gap-filled
ranges) to avoid the 40-billion-empty-batch problem with `BETWEEN` on sparse 64-bit
IDs:

```sql
-- Per batch: find the 500,000th system_id64 after the last processed ID
SELECT MAX(system_id64) FROM (
    SELECT system_id64 FROM ratings
    WHERE system_id64 > $last_id
    ORDER BY system_id64 LIMIT 500000
) sub;

-- Then update the batch by PK range
UPDATE ratings SET score_breakdown = NULL
WHERE system_id64 > $last_id
  AND system_id64 <= $batch_max
  AND score_breakdown IS NOT NULL;
```

### Result
- Batches processed: **375** (~187.5M rows)
- **Every batch returned `UPDATE 0`** — `score_breakdown` was already entirely NULL
- The zombie `build_ratings.py --rebuild` had likely cleared it before freezing
- DB size after: **877 GB** (only idx_rat_dirty savings reflected)

## Step 3: pg_repack

### Installation
`pg_repack` is not packaged for Alpine Linux (postgres:16-alpine container).
Built from source inside the container:

```bash
apk add --no-cache git make gcc musl-dev postgresql16-dev zlib-dev gawk
cd /tmp && git clone --depth 1 https://github.com/reorg/pg_repack.git
cd pg_repack && make && make install   # v1.5.3
```

Extension created: `CREATE EXTENSION IF NOT EXISTS pg_repack;`

### Execution
```
pg_repack -U edfinder -d edfinder --table ratings --wait-timeout 30
```

| Phase | Duration | Query |
|-------|----------|-------|
| Data copy | ~10 min | `INSERT INTO repack.table_17196 SELECT ...` |
| PK index build | ~2 min 30 sec | `CREATE UNIQUE INDEX index_17219 ON repack.table_17196 (system_id64)` |
| Partial index build | ~3 sec | `CREATE INDEX index_972816 ON repack.table_17196 (score) WHERE score >= 65` |
| Table swap + drop old | instant | — |

Total pg_repack runtime: ~75 minutes.

### Notes
- First attempt at pg_repack died when the screen session was killed, but
  the docker compose exec process survived inside the container (PID 3247670).
  No re-run needed — the process completed normally.
- The `LOCK TABLE public.ratings IN SHARE UPDATE EXCLUSIVE MODE` waited
  ~19 minutes (idle in transaction) while the data copy and index builds
  completed, then acquired instantly for the swap.
- Disk headroom was adequate: 416 GB free vs 392 GB table. The shadow table
  only consumed ~55 GB (live data without dead tuples).

## Post-Repack Results

| Metric | Before | After | Reclaimed |
|--------|--------|-------|-----------|
| ratings table (`pg_relation_size`) | 392 GB | **39 GB** | 353 GB |
| ratings total (`pg_total_relation_size`) | 400 GB | **43 GB** | 357 GB |
| DB size (`pg_database_size`) | 885 GB | **519 GB** | **366 GB** |
| Disk free | 408 GB | **749 GB** | +341 GB |
| Disk usage | 78% | **58%** | -20 pts |

## Verification

### EXPLAIN plans (all healthy, using proper indexes)

**Spatial query** — `Index Scan using idx_sys_coords` ✓
```
EXPLAIN SELECT id64, name FROM systems
WHERE x BETWEEN -50 AND 50 AND y BETWEEN -50 AND 50
  AND z BETWEEN -50 AND 50 LIMIT 20;
```

**Trigram similarity** — `Bitmap Index Scan on idx_sys_name_trgm` ✓
```
EXPLAIN SELECT id64, name FROM systems
WHERE name % 'sol' ORDER BY similarity(name,'sol') DESC LIMIT 10;
```

**Prefix search** — `Index Scan using idx_sys_name_lower_pattern` ✓
```
EXPLAIN SELECT id64, name FROM systems
WHERE lower(name) LIKE 'sol%' ORDER BY name LIMIT 20;
```

### API smoke test
```
curl http://localhost/api/systems/10477373803
→ score_breakdown present: False
```
Expected: column is NULL in DB, omitted from JSON. API consumers reconstruct
it from score columns at read time.

## Errors Encountered

1. **Original null script (Step 2.1):** `COUNT(*) WHERE score_breakdown IS NOT NULL`
   caused a full table scan of 392 GB and hit the 5-minute statement timeout.
   **Fix:** Switched to PK keyset pagination using `ORDER BY system_id64 LIMIT`
   which uses the PK index.

2. **Range-based batching (Step 2.2, attempt 2):** `system_id64 BETWEEN lo AND hi`
   produced 40 billion empty batches because Elite Dangerous 64-bit IDs are sparse.
   **Fix:** Keyset pagination — walk only IDs that actually exist.

3. **pg_repack not in Alpine repos:** postgres:16-alpine has no `pg_repack` package.
   **Fix:** Built from source (git, gcc, make, musl-dev, zlib-dev, gawk).

4. **Screen session killed during pg_repack:** The docker compose exec process
   (PID 3247670) survived inside the container and completed normally.

5. **Monitor tool runs locally, not on production:** Cannot use Monitor for
   production process-watching. Tracked manually via periodic checks.
