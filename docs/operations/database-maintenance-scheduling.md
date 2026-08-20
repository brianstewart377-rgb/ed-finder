# Database Maintenance Scheduling

PostgreSQL autovacuum is the primary dead-tuple maintenance mechanism.
`pg_repack` is retained as a measured, table-scoped recovery tool for physical
bloat that autovacuum cannot return to the filesystem. It is not a weekly
rewrite job.

## Committed Steady-State Schedule

The maintenance sidecar runs these relevant jobs in UTC:

- daily `02:10`: custom-format backup
- daily `03:15`: `ANALYZE` and materialized-view maintenance
- Sunday `04:00`: targeted concurrent reindex plus `VACUUM (ANALYZE)`
- Wednesday `01:30`: read-only dead-tuple pressure report

The pressure report is written by
`apps/maintenance/scripts/run_bloat_check.sh` to
`/data/logs/bloat-check.log`. It uses `pg_stat_user_tables` and labels large,
high-dead-tuple tables for operator review. Those statistics indicate tuple
pressure; they are not a direct measurement of physical bloat.

There is deliberately no scheduled `pg_repack` command. Repacking every table
on a timer duplicates autovacuum work, creates avoidable I/O and WAL, can
overlap backups, and may require hundreds of gigabytes of temporary disk.

## Durable pg_repack Installation

Production PostgreSQL is built from `apps/postgres/Dockerfile`, based on
`postgres:16-bookworm`, with the PGDG `postgresql-16-repack` package installed.
This keeps the CLI and server library present after container recreation.

The normal application deployment deliberately does not recreate PostgreSQL.
After this image change is merged, activate it once in an approved database
maintenance window, after a verified backup and with application writers
stopped:

```bash
cd /opt/ed-finder
docker compose build postgres
docker compose up -d --no-deps postgres
docker compose exec -T postgres pg_repack --version
```

The named `postgres_data` volume is retained across the container recreation.
Do not perform this activation during a restore or ordinary application deploy.

The `pg_repack` extension is database-local. The operator wrapper checks for
it and runs `CREATE EXTENSION pg_repack` only as part of an explicitly
confirmed table rewrite. A read-only check never creates the extension.

## Read-Only Operator Check

From the production host:

```bash
cd /opt/ed-finder
bash scripts/operator/run_pg_repack.sh
```

The default mode only prints the largest public tables, live/dead tuple
estimates, and recent autovacuum/analyze timestamps.

## Explicit Table Repack

First confirm all of the following:

1. a current restore-rehearsed backup exists
2. no restore, importer, or application rebuild is active
3. the target has measured physical bloat worth reclaiming
4. PostgreSQL-volume free space is sufficient
5. the maintenance window does not overlap backups or other heavy work

Then run exactly one named table:

```bash
cd /opt/ed-finder
bash scripts/operator/run_pg_repack.sh \
  --run \
  --table public.ratings \
  --confirm
```

The wrapper:

- requires the production-host operator guard
- accepts only one unquoted `public.<table>` identifier
- refuses to run while `pg_restore` or importer/rebuild containers are active
- prevents overlapping wrapper runs
- verifies the packaged CLI
- installs the database extension only inside the confirmed run when absent
- requires free space equal to twice the table-plus-index size by default
- runs `pg_repack --dry-run` before the rewrite
- uses `--no-kill-backend` and a finite wait timeout
- records pre/post relation sizes in `/data/logs/pg_repack.log`

`--allow-low-disk` exists for a separately reviewed exception where measured
live data is far smaller than the bloated relation. It must not be used merely
to get past the guard.

The upstream CLI and operational requirements are documented in the
[pg_repack documentation](https://github.com/reorg/pg_repack/blob/master/doc/pg_repack.rst).

## Fresh Restore Policy

Do not run `pg_repack` after a fresh logical restore. A new restore has already
rewritten its tables and indexes without the old dead-tuple bloat. Run staged
`ANALYZE` for planner statistics, resume autovacuum, and collect a new baseline
before considering any physical rewrite.

## Backup Rehearsal Scheduling

Restore rehearsals remain host-orchestrated through
`scripts/rehearse_postgres_restore.sh`, because they create a separate database
and require the Docker Compose host boundary. The former maintenance-sidecar
cron wrapper was removed: the sidecar does not have the Docker CLI, repository
mount, or socket needed by that wrapper.

Do not add Docker socket access to the maintenance container. A future
unattended rehearsal must be implemented as a dedicated fail-closed workflow
with core-data row thresholds and durable receipts. Until then, use the manual
path in `docs/operations/postgres-backup-and-restore.md`.
