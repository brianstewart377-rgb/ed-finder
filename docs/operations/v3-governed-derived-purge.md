# V3 governed derived purge (P2a / P2b1)

This runbook covers the P2a entry fences and installed backup wrapper, and the
P2b1 read-only and single-transaction purge action. The
[governed purge design](../development/v3-governed-derived-purge-design.md)
remains the execution-gate authority. This code provides no protected purge
workflow, rehearsal, or authorization to delete or rewrite data. Delete and
rewrite loops and recovery modes belong to P2b2, the protected workflow to P2c,
and the 1% rehearsal to P2d. No production operation follows from merging it.

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
   source. P2b1 supplies the action described below; workflow wiring remains P2c.

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

Migration 016 revokes the internal `purge_open_event` resolver from the
executor role. The shared P2a ledger query therefore uses the pinned connection
owner for its read-only admission probe, before action sessions enter
`v3_derived_purge_executor`. This is an explicit exception to the design's
every-session-first-statement rule; mutation SQL stays restricted to the
executor and the migration's public functions. The action does not grant the
resolver or alter 016. Likewise, the external canonical receipt seal identifies
the reviewed artifact, while 016 separately authenticates its nested plan using
PostgreSQL's JSONB text hash; the receipt carries both identities.
The action also follows gate 3b's narrower definer-owner rule: the application
role itself, or a `CREATEROLE` role with `ADMIN OPTION` on it. Although 016 can
be installed by a different superuser, that alone does not satisfy this plan
gate; the action reports and refuses such an owner.

The competing-writer observation also uses a fixed owner `BEGIN READ ONLY`
query: the executor lacks `pg_read_all_stats`, so other roles' session state
and backend classification are masked (PostgreSQL 18 exposes backend XIDs to
all callers). Treating those masked client sessions as idle would be
unsafe; interpreting them as writers would never admit an ordinary connected
application pool. The owner observation preserves 016's exact predicate and
016 rechecks it inside each mutation. WAL directory size is measured with a
fixed container filesystem command because the executor cannot call
`pg_ls_waldir`; it receives no additional monitoring or filesystem SQL grant.
The data directory is obtained from the pinned container's `PGDATA` and
`postmaster.pid`, because the executor also lacks permission to read the
`data_directory` server setting. The PID must still have that working directory
and its recorded start epoch must equal `pg_postmaster_start_time()` from the
live SQL session. Any inconsistency or missing path stops the placement proof.

The F2d code identity includes the new shared helpers and modified actions.
Existing accepted-release attestations are not silently regenerated: the normal
reviewed attestation gate remains required before executing those changed
workers. None of this adds a PostgreSQL restore/PITR recovery route.

## P2b1 action modes and receipt order

`scripts/operator/actions/v3-derived-generation-purge.sh` delegates fixed SQL
and receipt handling to `scripts/operator/lib/v3_generation_purge.py` and the
transaction adapter `scripts/operator/lib/v3_purge_transactions.py`. Its only
implemented modes are `plan`, `status`, `authorize`,
`verify-system-archetype-empty`, and `complete`. The four exact relation names
are `system-search`, `economy-opportunity`, `body-mechanics`, and
`system-rating-vector`. Their `delete-`, `rewrite-`, and `abort-relation-`
modes, plus `restore-services`, fail with
`mode_not_implemented_until_p2b2`; every other mode is unknown and fails closed.
These are action contracts for later governed dispatch, not an instruction to
run them manually against production.

After installation and execution prerequisites have been satisfied, the order
is:

1. `status` reports unresolved ledger state first. An open batch, rewrite,
   service, writer, or autovacuum fence remains durable even if its backend or
   runner has died. P2b1 cannot resolve those records; use the later reviewed
   P2b2 recovery modes. Unknown state refuses mutation.
2. `plan` takes fresh read-only evidence for the two exact rejected generations
   and the retained published generation. It checks worker quiescence,
   pointers, row counts, sizes, data/WAL/tablespace filesystem placement,
   archive and slot health, the 100 GB reserve, freeze ages, wrapper hash and
   the gate-3b writer-fence ownership precondition. Missing or mismatched proof
   stops the plan. Retain the sealed JSON receipt and its `content_sha256`.
3. `authorize --plan PATH --plan-sha256 SHA256` authenticates the sealed,
   bounded-age plan and rechecks live identities before calling migration
   016's `begin_derived_generation_purge` in one transaction. Both immutable
   requests and both `FAILED` transitions commit together; no payload is
   deleted. It then checks unchanged pointers and published counts.
4. `verify-system-archetype-empty --plan PATH --plan-sha256 SHA256` checks the
   three cluster relations, the wide `system_archetype` table and its summary
   view again. A target row stops the purge with `FAILED_STOP` evidence; it
   never grants a deletion path for those relations.
   This and `complete` authenticate the original immutable receipt without
   expiring it during a multi-day purge; only `authorize` admits a plan no older
   than one hour. All live phase gates still run again.
5. P2b2 must subsequently delete and verify the four relations in dependency
   order: Search, opportunity, mechanics, rating vector. Each relation needs a
   separate verified physical rewrite and restored fences. P2b1 deliberately
   refuses these modes.
6. `complete --plan PATH --plan-sha256 SHA256` refuses until every target
   payload count is zero, pointers and exact published counts match the plan,
   FKs are valid, fences are closed, and all four relations have
   `REWRITE_VERIFIED` evidence. It passes the completion receipt to migration
   016's `complete_derived_generation_purge`; zero rows alone never prove
   completion.

The action pins CPython 3.14, host/FQDN, Docker default context, container,
database and user, and verifies installed migration 016 against the committed
manifest. Sessions enter the restricted executor role and use fixed bounded
SQL with short lock timeouts. Mutating modes first check the shared P2a state
and hold the non-blocking host purge lease throughout the action. A bounded
wait for competing backend XIDs tolerates momentary background work; expiry
refuses the transaction and records the wait rather than weakening 016's
competing-writer check.

Receipts are JSON-only, use the canonical F2d content seal, and include the
design's source/migration identities, targets, pointers, workers, row counts,
storage/WAL/freeze facts, timeouts, transaction outcome and explicit write
flags. Unproven outcomes are `null`. `status` also reports the next admissible
mode, open-fence deadlines and observable backup skips. Neither a receipt nor
a successful read-only mode substitutes for the remaining owner execution
gates, protected workflow, or disposable crash rehearsal.

P2b1 samples live XID/MultiXact rates over five seconds, retrying at most three
times if a vacuum moves a MultiXact baseline. Its conservative planning horizon
is 24 hours with ceilings at 80% of each effective freeze limit, including
TOAST. These are authorization evidence, not rehearsal-derived execution
budgets: P2b2 must bind remaining dispatch/rewrite time to the reviewed cadence
before opening a fence. Exact-count SQL is bounded at 45 minutes, the controller
at one hour, and the competing-writer grace at 30 seconds with one-second SQL
probes. The 016 function-local timeout settings are unchanged. Host gates are
refreshed after long count scans before a transaction writes. Backup skip
observations cover at most the latest 1,000 journal entries in seven days;
unavailable journal evidence is `null`.

016 has no dedicated exclusion-verification function and does not include the
archetype summary view in its internal exclusion assertion. The action counts
all five exclusions itself and uses the public `purge_record_event` function
for authenticated `FAILED_STOP` records. It never supplies an archetype or
cluster deletion capability. Completion relies on 016's `REWRITE_VERIFIED`
events, whose verifier already proves the rewritten filenode and trailing
`ANALYZE`; P2b1 does not synthesize those events.
