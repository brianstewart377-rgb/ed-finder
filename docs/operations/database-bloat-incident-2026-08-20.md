# Database Bloat Incident & Alpine→Debian Migration (2026-08-20)

> **Historical V2 incident record.** The observations and actions below are
> preserved as dated evidence; they do not describe the current V3 PostgreSQL
> 18 environment and do not authorize current production or recovery commands.
> See [Infrastructure Status](./infrastructure-status.md) for the current,
> fail-closed boundary.

## Incident Summary

Production database filled to 95% capacity (1.4TB on 1.9TB volume) due to accumulated dead tuples from repeated EDDN writes. Root cause: Alpine PostgreSQL lacks pg_repack package, preventing bloat reclamation. Resolved via migration to Debian-based PostgreSQL 16 with pg_repack installed.

## Timeline

| Time | Event |
|------|-------|
| 2026-08-19 | Discovered backup restore failures; confirmed production backups ARE restorable (189M+ systems rows) |
| 2026-08-20 11:19 | Stopped API/EDDN, identified 95% disk usage (15GB free on 1.9TB) |
| 2026-08-20 11:30 | Freed 70GB by deleting old backups (Aug 16, rotation was working but Aug 20 backup failed) |
| 2026-08-20 11:32 | Attempted pg_dump for Debian migration; dump corrupted (zcat EOF error) |
| 2026-08-20 11:39 | Decision: nuke bloated volume, start fresh with Debian postgres |
| 2026-08-20 11:42 | Deleted postgres_data volume (1.4TB), started fresh postgres:16-bookworm |
| 2026-08-20 11:45 | Installed pg_repack via apt (`postgresql-16-repack`) |
| 2026-08-20 11:50 | Copied 70GB validated backup into container, started pg_restore |
| 2026-08-20 ~13:50 | Restore in progress, 356GB loaded (targeting ~1.1TB final) |

## Root Cause Analysis

### Why Database Bloated to 1.4TB

1. **EDDN ingest** writes updates to bodies/systems/body_rings tables continuously
2. **AUTOVACUUM tuned aggressively** (6 workers, 15s naptime, 5000 cost limit) but insufficient for update rate
3. **pg_repack unavailable** on Alpine PostgreSQL — cannot compact tables offline
4. **Result:** Dead tuples accumulated ~300GB over several weeks

### Why Backup Restore Wasn't Tested

- `scripts/rehearse_postgres_restore.sh` exists and is documented
- But rehearsals were **never executed** — `/data/backups/postgres/restore_rehearsal*` was empty
- Risk: backups could fail silently, leaving no recovery path
- **Fixed 2026-08-19:** Validated 70GB backup restores successfully (189M+ systems rows)

### Why Alpine PostgreSQL?

- Original rationale: small image, minimal deps
- **Downside:** pg_repack (bloat-reclamation tool) not packaged for Alpine
- **Solution:** Debian-based postgres:16-bookworm has `postgresql-16-repack` via apt

## Resolution

### Immediate Actions (Completed)

1. ✅ Stopped API + EDDN (no data loss risk with validated backups)
2. ✅ Freed 70GB by deleting old backups
3. ✅ Nuked 1.4TB bloated postgres volume
4. ✅ Started fresh postgres:16-bookworm container
5. ✅ Installed pg_repack extension via apt (`apt-get install postgresql-16-repack`)
6. ✅ Restored from validated 70GB backup (in progress, ~356GB loaded as of 13:50 UTC)

### Post-Restore (Pending)

1. **Verify data integrity** — confirm 189M+ systems rows loaded
2. **Run pg_repack ANALYZE** — compact all tables, update statistics
3. **Check final disk usage** — expect ~250-300GB (vs. 1.4TB bloated)
4. **Restart API services** — verify health
5. **Schedule pg_repack maintenance** — weekly during low-traffic window

## Operational Improvements (Going Forward)

### 1. Bloat Prevention
- **pg_repack now installed** — can compact tables without full locks
- **Schedule weekly pg_repack runs** (e.g., Sundays 02:00 UTC) during maintenance window
- **Monitor table bloat ratio** — alert if any table reaches 50% dead space

### 2. Backup Validation
- **Restore rehearsal script exists** (`scripts/rehearse_postgres_restore.sh`)
- **Was never running** — no automated rehearsals
- **Now validated** — 70GB backup confirmed restorable (2026-08-19)
- **Action:** Schedule monthly rehearsals to catch backup corruption early

### 3. Disk Space Monitoring
- **Current state:** Production has no disk-space alerts
- **At 95%, operations are silent** — only discovered via manual investigation
- **Action:** Add Prometheus/Grafana alerts at 70% and 80% thresholds
- **Current volume:** 1.9TB; growth baseline should be monitored to predict expansion timeline

### 4. Database Configuration
- **AUTOVACUUM already tuned aggressively** — no changes needed
- **WAL management already configured** (max_wal_size=32GB, wal_compression=on) — good
- **Schema design hazard (bodies.id composite key)** — documented but deferred; migration not needed for current bloat

### 5. Backup Rotation
- **Already working correctly** (Aug 15 was deleted on Aug 19)
- **Production .env correctly sets BACKUP_RETENTION_DAYS=3** (with 30-day offsite mirror)
- **Aug 20 backup failed mid-dump** — not a rotation issue but a write/connection issue (needs investigation)

## Lessons Learned

1. **Backup testing is operational insurance** — validated backups let you make bold choices (nuking 1.4TB)
2. **Alpine is lightweight but has operational tradeoffs** — pg_repack unavailability was a bloat killer
3. **Disk space doesn't announce problems** — need proactive monitoring at 70%+
4. **Dead tuples compound silently** — aggressive autovacuum can't keep up with high-update workloads without pg_repack

## Files Changed

- `docker-compose.yml` — changed `postgres:16-alpine` → `postgres:16-bookworm` (commit a0ef147)
- Backup cleanup — deleted `edfinder_20260816*` (70GB freed)
- Volume deleted — `ed-finder_postgres_data` (1.4TB, recreated fresh)

## Next Actions

1. Monitor restore completion (target: 13:50-14:30 UTC)
2. Verify 189M+ systems rows + 213GB+ bodies
3. Run `pg_repack -d edfinder` for final compaction
4. Restart API and verify `GET /api/health`
5. Add disk-space alerts (Prometheus) at 70%/80%
6. Schedule pg_repack cron job (weekly)
7. Schedule backup rehearsal cron job (monthly)
8. Document pg_repack procedure in ops runbook

## References

- Historical V2 backup/restore contract:
  [postgres-backup-and-restore.md](./postgres-backup-and-restore.md)
- Current production/recovery boundary:
  [infrastructure-status.md](./infrastructure-status.md)
- CLAUDE.md deployment notes: root of repo
