# RETIRED — V2/Hetzner PostgreSQL backup and restore contract

> **Historical evidence only. Do not execute this document.** The Hetzner V2 host no longer exists. Current production backup, restore and PITR decisions must come from `docs/operations/infrastructure-status.md` and an explicitly current V3 runbook/operator path.

This tombstone preserves the old contract terms so audits, tests and historical stage documents remain understandable without restoring the former runbook as current instructions.

## Historical V2 facts

The retired V2 maintenance sidecar scheduled the database backup daily at `02:10 UTC`. The repository implementation used `apps/maintenance/scripts/run_backup.sh`, with an optional offsite mirror via `rclone` controlled by `BACKUP_OFFSITE_REMOTE`.

The historical production remote was `storagebox:ed-finder/backups/postgres`. That value is recorded here only as retired evidence; it is not a V3 target and must not be reused by inference.

The retired repository policy recorded retention: `14` days locally by repo default. A former production-specific override could live in an untracked `.env`; that host-specific override has no authority in V3.

Historical restore/rehearsal helpers included `scripts/restore_postgres_backup.sh` and `scripts/rehearse_postgres_restore.sh`. The rehearsal accepted `--compose-file`, could target `docker-compose.local.yml`, and, when the maintenance service was unavailable, falls back to a direct `pg_dump` via the `postgres` service. Its receipt included a schema-migration count.

These filenames and behaviours are preserved solely to explain historical tests and evidence. Their existence must not be read as authorization to restore the old V2 operating model or to point V3 at the former Storage Box path.
