# Database Recovery Incident (2026-08-20)

## Status

Recovery is still in progress. This document corrects the earlier version,
which incorrectly described the production backup as fully restore-validated
before the original PostgreSQL volume was deleted.

The original approximately 1.4 TB PostgreSQL volume is gone. Recovery is from
the retained nightly custom-format backups. The latest archive is being
restored into the isolated `test_restore` database on PostgreSQL 16 Debian
Bookworm. Table data, including `systems`, has loaded; the restore is currently
building indexes and constraints. The systems index reported 186,589,826
tuples. Final independent integrity checks and production promotion remain
pending.

## What Happened

1. Production disk usage had grown close to capacity.
2. PostgreSQL was moved from the Alpine image to Debian Bookworm so packaged
   `pg_repack` tooling could be used.
3. A backup rehearsal was reported as successful without verifying completion
   and core data counts.
4. The original database volume was deleted on the strength of that report.
5. A later check of an incomplete restore found zero `systems` rows and was
   incorrectly interpreted as proof that the archives contained no systems.
6. A partial Spansh import and a chained application rebuild were started
   against the incomplete database. Both were stopped before promotion.
7. Direct archive inspection confirmed all three retained backups contain a
   `public.systems` data entry, and real system rows were extracted from the
   latest archive.
8. A clean restore of the latest archive was started in `test_restore` and is
   being validated before any production cutover.

The custom archive restores `systems` near the end of its table-data order.
Checking the row count before `pg_restore` reached that entry was the immediate
cause of the false “backups have no systems” conclusion.

## Root Causes

### Destructive action preceded adequate verification

The deletion decision relied on a rehearsal that checked archive structure and
generic schema presence, not a completed restore with credible core row counts.
The repository helpers also accepted any non-empty public schema as a restored
database. Those checks were insufficient for a production data-loss decision.

### Restore state was misread

The restore order was not checked before interpreting `systems = 0`. The
launcher also piped `pg_restore` through `tail` without `pipefail`, so its shell
success path could mask a `pg_restore` failure. Independent validation is
required regardless of the launcher result.

### Recovery workflows overlapped

The backup restore, partial Spansh import, and derived-data rebuild waiter were
allowed to coexist. The rebuild guard accepted only 100,000 systems, so the
143,547-row populated-system import would have passed despite representing far
less than one percent of the galaxy.

### Alpine was an operational limitation, not the incident cause

The Alpine image did not delete or corrupt the database. It made packaged
extension installation awkward. Debian Bookworm is the better operational
base for this deployment because PGDG provides `postgresql-16-repack`, but the
data-loss event was caused by inadequate verification and destructive
sequencing.

The precise historical source of physical bloat has not been proven by this
incident. Dead-tuple statistics, autovacuum behavior, relation growth, indexes,
and retained artifacts must be measured before assigning a single cause.

## Recovery Guardrails

- Keep API and EDDN writers stopped until the isolated restore passes.
- Do not run Spansh importers, application rebuilds, or `pg_repack` during the
  restore.
- Validate core counts, known systems, migrations, constraints, and indexes
  independently after `pg_restore` exits.
- Obtain explicit owner approval before renaming `test_restore` to `edfinder`
  or restarting services.
- Preserve nightly archives until the recovered application has passed smoke
  tests and a new backup has itself been restore-rehearsed.

## Post-Recovery Maintenance Policy

Autovacuum remains the primary tuple-maintenance mechanism. A fresh logical
restore must not be repacked: its tables and indexes have already been
rewritten without historical dead-tuple bloat.

The committed maintenance design is:

- weekly read-only dead-tuple pressure reporting
- explicit bloat investigation when thresholds are crossed
- table-scoped `pg_repack` only after operator review and confirmation
- no scheduled all-table repack
- durable `pg_repack` packaging in the PostgreSQL image

See `docs/operations/database-maintenance-scheduling.md`.

## Backup Rehearsal Follow-up

The old maintenance-sidecar rehearsal wrapper was not executable in that
container: it expected a repository mount, Docker CLI, Compose, and the Docker
socket, none of which were present. It has been removed from the sidecar cron.

Before unattended rehearsals are reintroduced, the canonical rehearsal must
fail closed on at least:

- `pg_restore` exit status
- a credible systems threshold and known-system probes
- substantial core relations (`bodies`, `ratings`, and `stations`)
- migration-ledger presence
- zero unvalidated constraints
- zero invalid or not-ready indexes
- a durable receipt that contains those results

Archive listing with `pg_restore --list` remains useful corruption screening,
but it is not a restore rehearsal.
