# Postgres Backup And Restore

This runbook defines the committed in-repo backup path for ED-Finder.

It is intentionally the smallest real safety improvement:

- nightly custom-format `pg_dump` archives
- local retention under `/data/backups/postgres`
- archive validation with `pg_restore --list`
- optional offsite mirror via `rclone`
- guarded restore into a disposable database by default

This is still a stopgap, not the end state. It removes "no backup path in repo"
while keeping the operational path boring. WAL archiving and point-in-time
recovery remain future hardening work.

## Backup Path

The scheduled backup path runs in the existing maintenance sidecar:

- script: `apps/maintenance/scripts/run_backup.sh`
- schedule: `apps/maintenance/scripts/crontab`
- compose wiring: `docker-compose.yml`

Current defaults:

- destination: `/data/backups/postgres`
- format: `pg_dump --format=custom --compress=6`
- schedule: daily at `02:10 UTC`
- retention: `14` days
- logs: `/data/logs/backup.log`
- offsite: optional `BACKUP_OFFSITE_REMOTE` mirror when configured

Each run writes:

- `edfinder_<timestamp>.dump`
- `edfinder_<timestamp>.dump.sha256`
- `edfinder_<timestamp>.dump.json`
- `latest.dump` symlink
- `latest.json` symlink

When `BACKUP_OFFSITE_REMOTE` is set, the sidecar also copies the archive,
checksum, and metadata JSON to that `rclone` remote, then updates a remote
`latest.json` pointer. Example remote values:

- `s3:ed-finder-prod/postgres`
- `storagebox:ed-finder/backups/postgres`

The run still creates and validates the local archive first. A failed offsite
sync makes the backup job fail loudly rather than pretending the mirror exists.

## Manual Backup

Run an on-demand backup on the server:

```bash
cd /opt/ed-finder
docker compose exec maintenance /usr/local/bin/run_backup.sh manual
```

Or from a Windows workstation with the configured SSH alias:

```powershell
ssh ed-finder-prod "cd /opt/ed-finder && docker compose exec maintenance /usr/local/bin/run_backup.sh manual"
```

## Verify A Backup Exists

```bash
ls -lh /data/backups/postgres
tail -n 50 /data/logs/backup.log
```

The backup script already validates the archive with `pg_restore --list`, so a
successful run means PostgreSQL can parse the archive structure.

## Restore Path

Use the committed restore helper:

- script: `scripts/restore_postgres_backup.sh`

The safe default restores into `edfinder_restore`, not the live `edfinder`
database.

Example on a Docker host:

```bash
cd /opt/ed-finder
bash scripts/restore_postgres_backup.sh \
  --backup-file /data/backups/postgres/latest.dump \
  --target-db edfinder_restore_20260708
```

The script:

1. checks the archive exists
2. refuses to target live `edfinder` unless `--allow-live-db` is supplied
3. drops and recreates the target database
4. pipes the custom-format archive into `pg_restore`
5. runs a basic public-table smoke check

## Restore Rehearsal

Preferred rehearsal path:

```bash
cd /opt/ed-finder
bash scripts/rehearse_postgres_restore.sh \
  --receipt-file /data/backups/postgres/restore_rehearsal_latest.json
```

The helper:

1. runs a manual backup through the maintenance sidecar unless `--skip-backup` is supplied
2. restores into `edfinder_restore_rehearsal` by default
3. verifies both public-table visibility and `schema_migrations` presence
4. drops the disposable rehearsal database again unless `--keep-db` is supplied
5. optionally writes a small JSON receipt for the ops log

Finish-state helper:

- script: `scripts/check_restore_rehearsal_status.sh`

Use it for either a light pulse or a wait-until-finished probe that immediately
checks the receipt plus any surviving restore database:

```bash
cd /opt/ed-finder
bash scripts/check_restore_rehearsal_status.sh \
  --target-db edfinder_restore_rehearsal \
  --receipt-file /opt/ed-finder/artifacts/restore-rehearsals/production-restore-receipt-2026-07-11.json
```

```bash
cd /opt/ed-finder
bash scripts/check_restore_rehearsal_status.sh \
  --wait \
  --poll-seconds 60 \
  --target-db edfinder_restore_rehearsal \
  --receipt-file /opt/ed-finder/artifacts/restore-rehearsals/production-restore-receipt-2026-07-11.json
```

The status helper stays read-only. It:

1. checks whether a matching `pg_restore` is still running
2. confirms whether the target rehearsal database still exists
3. runs the same public-table and `schema_migrations` smoke checks after the
   restore process has finished, if the target DB still exists
4. prints the receipt file when present so the operator can compare the final
   outcome against the observed runtime state

For the canonical local Windows/disposable stack, point the helper at
`docker-compose.local.yml`. That stack has no `maintenance` service, so the
script automatically falls back to a direct `pg_dump` via the `postgres`
service and writes the default archive under `artifacts/restore-rehearsals/`.
If the normal local `edfinder` DB was created by historical raw init scripts
and does not yet expose `schema_migrations`, prefer a disposable source
database that you seeded through the manifest-ledger path first.

Example local rehearsal:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/run-bash.ps1 -Script scripts/rehearse_postgres_restore.sh -ScriptArgs @('--compose-file', 'docker-compose.local.yml', '--source-db', 'edfinder_restore_source', '--receipt-file', 'artifacts/restore-rehearsals/local-restore-receipt.json')
```

Equivalent Git Bash invocation:

```bash
bash scripts/rehearse_postgres_restore.sh \
  --compose-file docker-compose.local.yml \
  --source-db edfinder_restore_source \
  --receipt-file artifacts/restore-rehearsals/local-restore-receipt.json
```

Equivalent manual rehearsal flow:

```bash
cd /opt/ed-finder
docker compose exec maintenance /usr/local/bin/run_backup.sh manual
bash scripts/restore_postgres_backup.sh \
  --backup-file /data/backups/postgres/latest.dump \
  --target-db edfinder_restore_rehearsal
docker compose exec -T postgres psql -U edfinder -d edfinder_restore_rehearsal -At \
  -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';"
docker compose exec -T postgres dropdb -U edfinder --if-exists edfinder_restore_rehearsal
```

Record the rehearsal in the ops log or roadmap notes with:

- backup filename
- start/end time
- restore target database
- smoke-check results
- schema-migration count
- any operator surprises

Recorded local disposable rehearsal:

- date: `2026-07-09`
- compose target: `docker-compose.local.yml`
- source DB: `edfinder_restore_source`
- target DB: `edfinder_restore_rehearsal`
- receipt: `artifacts/restore-rehearsals/local-restore-receipt-2026-07-09.json`
- result: `public_tables = 68`, `schema_migrations = 35`, restored target
  dropped after verification

## Current Limits

- Offsite sync is optional and must be explicitly configured with an `rclone`
  remote plus remote-side retention/lifecycle policy.
- There is no WAL archiving or point-in-time recovery yet.
- Retention is finite and local to the server.
- A backup is only operationally trusted once the restore rehearsal has been
  executed and recorded.
