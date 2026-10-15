# V3 purge fences and backup wrapper installation (P2a)

This is the P2a entry-fence and installed-backup-wrapper runbook. The
[governed purge design](../development/v3-governed-derived-purge-design.md)
remains the execution-gate authority. This change provides no purge action,
protected purge workflow, rehearsal, or authorization to delete or rewrite data
(P2b–P2d remain separate).

All governed production mutators first read the operating database's purge
ledger and non-blockingly probe `/run/lock/edfinder-v3-derived-purge.lock`.
An open `BATCH_STARTED`, `REWRITE_STARTED`, `SERVICES_QUIESCED`,
`WRITER_FENCE_ENABLED`, or `AUTOVACUUM_DISABLED`, an integrity-failed
`FAILED_STOP`, a held lease, missing ledger, or failed probe refuses the action
before operation locks or mutations. JSON receipts name the unresolved kinds.
The fixed SQL uses migration 016's `purge_open_event`; writer restoration counts
only with JSON boolean `verified: true`. A dead backend frees no ledger fence.
Only the later purge recovery paths may resolve these records. Option (b), the
read-only writer fence, is selected; P2a does not enable it.

The sole missing-ledger exception belongs to schema **apply**: its live ledger
must exactly equal the authenticated plan's recorded `applied_before`, including
hashes, and the plan's complete pending suffix must end in
`016_v3_governed_derived_purge.sql`. This supports the entire pending set,
including the pre-014 prefix. A progressed prefix needs a fresh plan when the
relation is still absent. Once 016 is recorded, absence always refuses. A held
purge lease refuses even this bootstrap. Read-only migration `plan` remains
available for diagnosis.

## Installation order

After the required code has merged and execution gates permit the operation:

1. Use the [protected schema migration workflow](v3-production-schema-migration.md)
   to plan, review, then apply the complete pending set through 016. Commit its
   receipt. This is a prerequisite for installing the wrapper: an earlier
   installation would make every scheduled backup fail on the missing ledger.
2. Dispatch the existing protected operations workflow
   `.github/workflows/chatgpt-ed-new-ops.yml` on trusted `main`, selecting
   `v3-backup-wrapper-install`. It pins `ed-finder-prod` /
   `nb79a3d.mevnode.com` and replaces only
   `/opt/ed-finder-v3-runtime/pgbackrest-operation.sh`, using the committed source
   SHA and SHA-256. No timer or unit changes.
3. Review and commit its retained JSON receipt. Require `status: passed`, equal
   `source_sha256` and `installed_sha256`, `wrapper_temp_written: true`,
   `wrapper_installed: true`, and `installed_hash_verified: true`. Database,
   service, timer and unit write flags must remain false. The installer refuses
   while the schedule lease is held or backup/verify processes are active, and
   holds the schedule lease through the atomic rename and installed hash check.
4. Only then obtain and commit the later purge plan. That plan and each
   destructive phase must verify the installed wrapper hash against the pinned
   source. P2a does not add those later commands.

The standalone installed wrapper uses pinned local `psql` credentials by role
name, never a password argument or environment file. Before backup/verify it
skips only for an open destructive record whose recorded PID **and**
`backend_start` still match `pg_stat_activity` in the operating database. It logs
that record. Dead backends do not suppress backups; missing ledger or query
failure exits non-zero before starting pgBackRest. See the
[backup boundary](../../deploy/v3-production/backup/README.md).

## Entry-point classification

| Entry point / modes | Classification | Reason |
| --- | --- | --- |
| `v3_production_deploy.py promote`, `v3-production-promote.sh promote` | Mutator, fenced | Pulls images and changes application containers and release state. |
| `v3-publish-derived-products.sh run` | Mutator, fenced | Publishes products and writes publication receipts. |
| `v3_production_migrate.py apply` via `v3-production-migrate.sh` | Mutator, fenced | Applies DDL and migration ledger; exact-plan bootstrap only. |
| `v3-spatial-pyramid.sh build/publish` | Mutator, fenced | Builds or publishes database spatial state. |
| `ratings-v4-generation.sh start` | Mutator, fenced | Starts a database-writing ratings worker. |
| `v3-system-search-f1.sh start/finalize` | Mutator, fenced | Starts builds or performs validation/maintenance and final receipts. |
| `v3-system-archetype.sh start/finalize` | Mutator, fenced | Starts builds or performs validation/maintenance and final receipts. |
| `v3-system-search-validate-constraints.sh start` | Mutator, fenced | Launches SQL validation that changes catalog state. |
| `v3-archetype-calibration-complete.sh start` | Mutator, fenced | Launches a worker and writes durable host checkpoints. |
| `v3-archetype-calibration-probe.sh run` | Worker launcher, fenced | Database reads are read-only, but launches a container and writes host run/env/receipt state. |
| `v3-archetype-plan-probe.sh run` | Worker launcher, fenced | Database reads are read-only, but launches a container and writes host run/env/receipt state. |
| `v3-finder-capacity-gate.sh run` | Worker launcher, fenced | Database reads are read-only, but launches a container and writes host run/env/receipt state. |
| `octopus-qdrant-healthcheck-repair.sh` | Mutator, fenced | Changes Compose and recreates/starts services. |
| `v3-backup-wrapper-install.sh` | Mutator, fenced | Atomically replaces the installed backup runtime file. |
| `host-status` (inline) | Read-only | Host and container inventory. |
| `octopus-edge-status.sh` | Read-only | Inspects edge state. |
| `recover-v3-runtime-contract` (`recover_v3_runtime_contract.py`) | Read-only | Inspects runtime metadata and streams an archive; artifact writes are on the runner. |
| `v3-app-status.sh` | Read-only | Inspects application state. |
| `v3-spatial-status.sh` | Read-only | Inspects spatial state. |
| `v3-derived-lifecycle-status.sh` | Read-only | Inspects pointers, workers and derived lifecycle. |
| `v3-disk-inventory.sh` | Read-only | Inspects filesystem and relation inventory. |
| All `status` modes above; migration `plan`/`authority-gate`; deployment `authority-gate`/`preflight` | Read-only operation | No production build, publication, DDL or service change. |

The three probe/gate launchers above are deliberately fenced under the task's
worker-launch rule despite their read-only database queries. Pure status,
inventory and probe inspection paths stay unfenced. This distinction is about
host worker launch and state, not whether a query writes rows.

## Design and implementation boundaries

016's resolver accepts closing kinds as an argument. Its own rewrite recovery
calls omit `FAILED_STOP`; the P2a callers supply the design's
`REWRITE_VERIFIED/REWRITE_ROLLED_BACK/FAILED_STOP` set. An integrity-failed stop
independently continues to fence every non-purge mutator, including after a
recovery acknowledgement. P2a changes no migration or purge recovery function.

The F2d code identity includes the new shared helpers and modified actions.
Existing accepted-release attestations are not silently regenerated: the normal
reviewed attestation gate remains required before executing those changed
workers. None of this adds a PostgreSQL restore/PITR recovery route.
