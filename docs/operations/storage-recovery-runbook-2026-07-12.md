# ED-Finder — Production Storage Recovery Runbook (V1)

**Objective:** reduce the production database from ~960 GB to ~660 GB by removing dead indexes and eagerly-stored score explanations, without deleting a single fact and without downtime.

**Status of evidence:** all findings below were derived from live production statistics (`pg_class`, `pg_stat_user_indexes`, `EXPLAIN` plans, column-width sampling) cross-referenced against the query layer at `c233095` (`apps/api/src/local_search.py`, `routers/systems.py`, `routers/archetypes.py`, `routers/simulation.py`, `apps/importer/src/build_ratings.py`).

**Context:** run after the 2026-07 disk-exhaustion incident. Current state: 1.9 TB volume, 1.3 TB used, 518 GB free, **0 B reclaimable Docker slack**. There is no cleanup cushion left; this runbook restores the cushion.

---

## 0. Findings that justify the operation

### 0.1 The Finder query is spatial-first
`local_search.py:295-310` — every non-galaxy-wide search anchors on a reference system and filters:
```sql
s.x BETWEEN ? AND ? AND s.y BETWEEN ? AND ? AND s.z BETWEEN ? AND ?
AND ((s.x-rx)² + (s.y-ry)² + (s.z-rz)²) BETWEEN ? AND ?
```
`ratings` is then reached by `LEFT JOIN ratings r ON r.system_id64 = s.id64` — i.e. **always by primary key, never as a driving predicate.** No query in the codebase filters or sorts on a ratings score column as the leading condition.

**Consequence:** every `idx_rat_*` score index is unreachable by the planner. Confirmed by owner: these date from a retired per-economy scoring model.

### 0.2 The composite coordinate index is the one that works
`EXPLAIN` on a bounding-box query chose `idx_sys_coords` (x,y,z composite). The single-column `idx_sys_x/y/z` cannot serve a 3-dimensional range predicate better than the composite and are never chosen.

### 0.3 Name search uses trigram only
`local_search.py:910` uses `WHERE lower(name) LIKE $1`; `:919` uses `WHERE name % $1 ORDER BY similarity(...)`. **`idx_sys_name_trgm` is load-bearing — keep it.** The plain `idx_sys_name` btree serves nothing.

### 0.4 `score_breakdown` is 84% of the ratings table
Sampled: 1,058 bytes average, × 186.6M rows ≈ **~197 GB**. Read only for a single system at a time. The Finder list query does not select it. It is a JSON re-encoding of columns already present in the same row.

### 0.5 Statistics caveat
`idx_scan = 0` on production reflects an app with one non-searching user over 34 days. Every drop below is justified by **code analysis**, not usage counters.

---

## 1. Preconditions (run before anything)

```bash
# 1. Confirm free space and that no importer is mid-run
df -h /
docker ps --format '{{.Names}}' | grep importer   # must be empty

# 2. Take a fresh backup and verify it
docker exec ed-maintenance /app/scripts/run_backup.sh
ls -lh /data/backups/postgres/
docker exec -i ed-postgres pg_restore --list /data/backups/postgres/latest.dump | head

# 3. Record the starting position
docker exec -i ed-postgres psql -U edfinder -d edfinder -c \
  "SELECT pg_size_pretty(pg_database_size('edfinder'));"
```

**Do not proceed if the backup did not verify.**

---

## 2. Phase A — Drop dead indexes (~115 GB, zero risk, instantly reversible)

`DROP INDEX CONCURRENTLY` takes no exclusive lock and can be cancelled safely. Run **one at a time**, checking `df -h /` between the large ones. Each drop is reversible by re-running the `CREATE INDEX` from `sql/002_indexes.sql`.

### 2.1 Invalid reindex debris (0 B, do first)
```sql
SELECT indexrelid::regclass AS idx, indisvalid, indisready
FROM pg_index WHERE indexrelid::regclass::text LIKE '%_ccnew%';
```
Drop each with `indisvalid = false`:
```sql
DROP INDEX CONCURRENTLY IF EXISTS idx_sys_name_lower_pattern_ccnew;
DROP INDEX CONCURRENTLY IF EXISTS idx_sys_name_lower_pattern_ccnew1;
DROP INDEX CONCURRENTLY IF EXISTS idx_sys_name_lower_pattern_ccnew2;
DROP INDEX CONCURRENTLY IF EXISTS idx_sys_name_lower_pattern_ccnew3;
DROP INDEX CONCURRENTLY IF EXISTS idx_sys_name_lower_pattern_ccnew4;
DROP INDEX CONCURRENTLY IF EXISTS idx_sys_name_lower_pattern_ccnew5;
DROP INDEX CONCURRENTLY IF EXISTS idx_sys_name_lower_pattern_ccnew6;
DROP INDEX CONCURRENTLY IF EXISTS idx_sys_name_lower_pattern_ccnew7;
DROP INDEX CONCURRENTLY IF EXISTS idx_sys_name_lower_pattern_ccnew8;
```

### 2.2 Unreachable indexes — retired scoring model (~55 GB)
Note: idx_ratings_confidence_high is included here not because
it indexes a per-economy column, but because ratings.confidence
is never used as a filter or sort key by any live query path
(verified 2026-07-12). It is defined in sql/004_ratings_v31.sql,
not sql/002_indexes.sql — see §6 Rollback.
```sql
DROP INDEX CONCURRENTLY IF EXISTS idx_ratings_confidence_high;
DROP INDEX CONCURRENTLY IF EXISTS idx_rat_econ_score;
DROP INDEX CONCURRENTLY IF EXISTS idx_rat_score;
DROP INDEX CONCURRENTLY IF EXISTS idx_rat_body_quality;
DROP INDEX CONCURRENTLY IF EXISTS idx_rat_agriculture;
DROP INDEX CONCURRENTLY IF EXISTS idx_rat_military;
DROP INDEX CONCURRENTLY IF EXISTS idx_rat_slots;
DROP INDEX CONCURRENTLY IF EXISTS idx_rat_refinery;
DROP INDEX CONCURRENTLY IF EXISTS idx_rat_industrial;
DROP INDEX CONCURRENTLY IF EXISTS idx_rat_hightech;
DROP INDEX CONCURRENTLY IF EXISTS idx_rat_tourism;
DROP INDEX CONCURRENTLY IF EXISTS idx_rat_gas_giant;
DROP INDEX CONCURRENTLY IF EXISTS idx_rat_terraformable;
DROP INDEX CONCURRENTLY IF EXISTS idx_rat_neutron;
DROP INDEX CONCURRENTLY IF EXISTS idx_rat_ammonia;
DROP INDEX CONCURRENTLY IF EXISTS idx_rat_bio;
DROP INDEX CONCURRENTLY IF EXISTS idx_rat_elw;
DROP INDEX CONCURRENTLY IF EXISTS idx_rat_geo;
```

### 2.3 Redundant coordinate singles (~32 GB)
```sql
DROP INDEX CONCURRENTLY IF EXISTS idx_sys_x;
DROP INDEX CONCURRENTLY IF EXISTS idx_sys_y;
DROP INDEX CONCURRENTLY IF EXISTS idx_sys_z;
-- KEEP idx_sys_coords — the planner uses it.
```

### 2.4 Redundant name index (~14 GB)
```sql
DROP INDEX CONCURRENTLY IF EXISTS idx_sys_name;
-- KEEP idx_sys_name_trgm — used by similarity search.
```

### 2.5 Verify before and after each batch
```sql
-- planner still uses the right indexes after drops
EXPLAIN SELECT id64, name FROM systems
 WHERE x BETWEEN -50 AND 50 AND y BETWEEN -50 AND 50
 AND z BETWEEN -50 AND 50 LIMIT 20;
-- expect: Index Scan using idx_sys_coords

EXPLAIN SELECT id64, name FROM systems
 WHERE name % 'sol' ORDER BY similarity(name,'sol') DESC LIMIT 10;
-- expect: Bitmap Index Scan on idx_sys_name_trgm
```

**Expected after Phase A: ~845 GB (from ~960 GB).**

---

## 3. Phase B — Reclaim `score_breakdown` (~180 GB)

**This requires a code change first.** Do not run the backfill before changing the writer.

### 3.1 Measure the retention decision
```sql
SELECT count(*) FILTER (WHERE score >= 50) AS keep_50,
       count(*) FILTER (WHERE score >= 60) AS keep_60,
       count(*) FILTER (WHERE score >= 70) AS keep_70,
       count(*) AS total
FROM ratings;
```

### 3.2 Change the writer first
`build_ratings.py` writes `score_breakdown` for every row. Change it to reconstruct the breakdown in Python from existing columns at read time — the API consumers (`systems.py:59`, `archetypes.py:751`, `simulation.py:406`) read one row at a time and can compute it on demand. Stop writing the column entirely.

### 3.3 API must handle NULL gracefully
Each consumer must handle `score_breakdown = NULL` by reconstructing from columns, not returning an empty response.

### 3.4 Backfill (batched, with finite timeouts)
```sql
-- run via repair script harness, NOT direct psql
-- dry-run first, then --apply
UPDATE ratings SET score_breakdown = NULL
WHERE system_id64 IN (
  SELECT system_id64 FROM ratings
  WHERE score_breakdown IS NOT NULL
  LIMIT :batch_size
);
```
Use finite `lock_timeout` (10s) and `statement_timeout` (5 minutes). Never 0.

### 3.5 Reclaiming disk space
Batched NULLing makes space reusable but does NOT return it to the filesystem.
Run `pg_repack ratings` after Phase A to get the disk back.
Requires free space ≈ table size — do Phase A first to create headroom.

**Expected after Phase B: ~660 GB.**

---

## 4. Indexes to verify before dropping

### 4.1 `idx_sys_name_lower_pattern` (14 GB) — verify first
```sql
EXPLAIN SELECT id64, name FROM systems
 WHERE lower(name) LIKE 'sol%' ORDER BY name LIMIT 20;
```
If plan uses this index: **keep it.**
If plan uses trigram or seq scan: droppable.

### 4.2 `idx_rat_dirty` (~8 GB) — grep first
```bash
grep -rn "idx_rat_dirty" apps/ scripts/ sql/
```
If nothing references it by name outside sql/: droppable.

---

## 5. Phase C — Follow-ups

1. **Disk alerting at 80%.** Do this regardless of everything else.
2. **Retire dead score columns.** `score_agriculture` etc. are still selected and written. Separate stage, separate review.
3. **Restore rehearsals off production host.** Use a disposable Hetzner VM.
4. **Offsite backups.** `BACKUP_OFFSITE_REMOTE` unset, `rclone` missing from maintenance image.

---

## 6. Rollback

- **Phase A:** re-run `CREATE INDEX CONCURRENTLY` from the relevant
  sql/ migration file. Most indexes are defined in `sql/002_indexes.sql`
  but note `idx_ratings_confidence_high` is defined in
  `sql/004_ratings_v31.sql`. Check the correct source file before
  recreating any dropped index.
- **Phase B:** re-run the scorer for affected systems via dirty-flag pipeline. Nothing unrecoverable.

---

## 7. Receipts

Commit a dated receipt to `artifacts/storage-recovery/` recording:
starting DB size, per-index sizes dropped, post-Phase-A size,
rows nulled, post-Phase-B size, and verification EXPLAIN outputs.
