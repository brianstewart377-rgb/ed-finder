# Database Maintenance Scheduling

After the Alpine→Debian migration and pg_repack installation (2026-08-20), production now has the tools to prevent bloat. This runbook documents the maintenance schedule.

## Weekly pg_repack (Bloat Reclamation)

**Purpose:** Compact tables and reclaim dead tuple space without full locks.

**Schedule:** Sundays 02:00 UTC (low-traffic maintenance window)

**Add to production crontab** (or maintenance container's `crontab.d` if applicable):

```bash
# Sunday 02:00 UTC: pg_repack all tables
0 2 * * 0 cd /opt/ed-finder && docker compose exec -T postgres psql -U edfinder -d edfinder -c "SELECT pg_repack(t.oid) FROM pg_class t INNER JOIN pg_namespace n ON (n.oid = t.relnamespace) WHERE n.nspname = 'public' AND t.relkind = 'r' AND t.reltuples > 0 ORDER BY t.relpages DESC;" > /data/logs/pg_repack.log 2>&1
```

**Alternative (simpler, less aggressive):**

```bash
# Sunday 02:00 UTC: vacuum and analyze
0 2 * * 0 cd /opt/ed-finder && docker compose exec -T postgres vacuumdb -U edfinder -d edfinder -z > /data/logs/vacuum.log 2>&1
```

**Monitoring:**
- Check `/data/logs/pg_repack.log` (or `vacuum.log`) for errors
- Verify disk space freed via `df /dev/mapper/vg0-root` after completion
- Expected result: 5-15GB freed on each run (depending on EDDN write rate)

## Monthly Backup Rehearsal

**Purpose:** Validate that production backups can actually be restored (catch corruption early).

**Schedule:** First Monday of each month, 01:00 UTC

**Procedure:**

```bash
# Run manual restore into edfinder_restore_rehearsal, then drop it
cd /opt/ed-finder
bash scripts/rehearse_postgres_restore.sh \
  --backup-file /data/backups/postgres/latest.dump \
  --target-db edfinder_restore_monthly_$(date +%Y%m%d) \
  --receipt-file /data/backups/postgres/restore_rehearsal_$(date +%Y-%m-%d).json
```

**Verification steps (included in script):**
1. Backup file exists and is readable
2. pg_restore succeeds (full data load)
3. `schema_migrations` table has correct count (should be ≥35 for current schema)
4. Sample row count checks pass (systems, bodies, ratings non-zero)

**Output:**
- Receipt file at `/data/backups/postgres/restore_rehearsal_YYYY-MM-DD.json`
- Contains: timestamp, target DB name, row counts, success/failure

**Cleanup:**
- Script automatically drops `edfinder_restore_monthly_*` database after verification
- Keep receipt files in git history for audit trail

## Disk Space Monitoring (Manual Until Prometheus/Grafana Setup)

**Check weekly:**

```bash
ssh ed-finder-prod "df -h /dev/mapper/vg0-root"
```

**Alert thresholds:**
- 70% full: investigate growth rate, consider expansion timeline
- 80% full: expand volume or clear old backups immediately
- 95%+ full: emergency (what we hit on 2026-08-20)

**Add Prometheus alert** (if monitoring stack enabled):

```yaml
- alert: PostgresVolumeFull
  expr: node_filesystem_avail_bytes{mountpoint="/",fstype="ext4"} / node_filesystem_size_bytes{mountpoint="/"} < 0.2
  for: 5m
  annotations:
    summary: "Postgres volume {{ $value | humanizePercentage }} free"
```

## Monitoring Table Bloat

**Ad-hoc check (run monthly):**

```bash
ssh ed-finder-prod "docker compose exec -T postgres psql -U edfinder -d edfinder -c \"
SELECT 
  schemaname, 
  tablename, 
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
  ROUND(100.0 * (pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) / pg_total_relation_size(schemaname||'.'||tablename)) as index_pct
FROM pg_tables 
WHERE schemaname = 'public' 
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC 
LIMIT 15;
\""
```

**Expected output after fresh restore + pg_repack:**
- Large tables (systems, bodies) should have low index overhead (10-30%)
- If any table > 50% index bloat: prioritize pg_repack run

## Post-Migration Baseline (2026-08-20)

After restore completes and pg_repack runs:

```bash
docker compose exec -T postgres psql -U edfinder -d edfinder -c "
SELECT COUNT(*) as systems FROM systems;
SELECT COUNT(*) as bodies FROM bodies;
SELECT COUNT(*) as ratings FROM ratings;
SELECT pg_size_pretty(pg_database_size('edfinder')) as total_size;
"
```

**Expected:**
- Systems: ~189M rows
- Bodies: ~213GB (largest table)
- Ratings: ~43GB
- Total DB: ~250-300GB (vs. 1.4TB bloated)

## Maintenance Container Integration

If running in `maintenance` sidecar (preferred):

Add to `apps/maintenance/scripts/crontab`:

```cron
# pg_repack weekly
0 2 * * 0 /app/scripts/pg_repack.sh

# Backup rehearsal monthly
0 1 1 * * /app/scripts/backup_rehearsal.sh
```

And commit wrapper scripts:
- `apps/maintenance/scripts/pg_repack.sh` — calls `pg_repack` via docker
- `apps/maintenance/scripts/backup_rehearsal.sh` — calls `rehearse_postgres_restore.sh`

## Automation Readiness Checklist

- [ ] pg_repack installed on production (✅ 2026-08-20)
- [ ] Backup rehearsal script exists (`scripts/rehearse_postgres_restore.sh`) (✅)
- [ ] Cron jobs scheduled (pg_repack weekly, rehearsal monthly)
- [ ] Disk space alerts configured (70%/80% thresholds)
- [ ] Receipt files committed to git for audit trail
- [ ] Prometheus/Grafana monitoring stack running (optional but recommended)

## References

- Incident that triggered this: `docs/operations/database-bloat-incident-2026-08-20.md`
- Backup & restore runbook: `docs/operations/postgres-backup-and-restore.md`
- Monitoring setup: `docs/operations/monitoring.md`
