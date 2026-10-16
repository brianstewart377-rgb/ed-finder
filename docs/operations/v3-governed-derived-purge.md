# V3 governed derived purge (through P2c)

This runbook covers the P2a entry fences and installed backup wrapper, and the
P2b1 read-only and single-transaction purge action, P2b2a bounded delete
and recovery phases, P2b2b physical rewrite and its independent monitor, and the
P2c protected dispatch workflow. The
[governed purge design](../development/v3-governed-derived-purge-design.md)
remains the execution-gate authority. The approximately 1% disposable PostgreSQL
18 rehearsal remains P2d, and the protected workflow does not itself satisfy
the design's owner execution gates. No production operation follows from merging
this code.

All governed production mutators first read the operating database's purge
ledger and non-blockingly probe `/run/lock/edfinder-v3-derived-purge.lock`.
An open `BATCH_STARTED`, `REWRITE_STARTED`, `SERVICES_QUIESCED`,
`WRITER_FENCE_ENABLED`, or `AUTOVACUUM_DISABLED`, an integrity-failed
`FAILED_STOP`, a held lease, missing ledger, or failed probe refuses the action
before operation locks or mutations. JSON receipts name the unresolved kinds.
The fixed SQL uses migration 016's `purge_open_event`; writer restoration counts
only with JSON boolean `verified: true`. A dead backend frees no ledger fence.
Only the purge recovery paths may resolve these records. Option (b), the
read-only writer fence, is selected. The API stays running throughout; the
quiesce path remains refused until a future owner decision selects option (a).

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
   source. Dispatch the action only through the protected workflow described below.

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

The fixed read-only status progress query also uses the connection owner so
`pg_stat_activity` exposes the recorded backend's PID and `backend_start`
together; the executor's view can mask the start time. Payload probes remain
under the executor. Status observes workers through Docker alone, avoiding the
lifecycle action's additional relation-size probes during a rewrite.

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

## Protected workflow dispatch runbook

Use [V3 production derived purge](../../.github/workflows/v3-production-derived-purge.yml)
on `main` for every governed phase. It accepts manual dispatch only and requires
the protected `v3-production` environment approval. After approval it re-fetches
`main` and refuses unless the dispatched commit is still the exact current head.
If `main` moves while approval is pending, start a new dispatch from its current
head and review the resulting source identity. Inputs never select a host, path,
SQL statement, or arbitrary relation.

The [operations workflow](../../.github/workflows/chatgpt-ed-new-ops.yml) also
offers `v3-derived-purge-plan` and `v3-derived-purge-status`. These invoke only
the read-only `plan` and `status` modes. An ops plan is diagnostic evidence;
later protected phases accept plan artifacts only from successful `plan` runs
of the dedicated purge workflow. No mutating purge mode is available in ops.

| Input | Meaning and admission |
| --- | --- |
| `mode` | One literal choice from the action's closed list: `plan`, `status`, `authorize`, `verify-system-archetype-empty`, the four `delete-`, four `rewrite-`, four `abort-relation-` choices, `restore-services`, or `complete`. Relation suffixes are only `system-search`, `economy-opportunity`, `body-mechanics`, and `system-rating-vector`. |
| `confirm_target` | Must equal `ed-finder-prod/nb79a3d.mevnode.com` exactly. |
| `plan_run_id` | Digits-only ID of the successful dedicated-workflow `plan` run on `main`. Required for every mode except `plan` and `status`. |
| `plan_sha256` | The plan receipt's 64-character lowercase hexadecimal `content_sha256`, reviewed with that run's artifact. Required with `plan_run_id`; this is the external receipt seal, distinct from the nested database `plan_sha256`. |
| `verification_run_id` | Digits-only ID of the successful dedicated-workflow `verify-system-archetype-empty` run on `main`. Required for delete, rewrite, abort, `restore-services`, and `complete`. |
| `verification_sha256` | The successful exclusion-verification receipt's 64-character lowercase hexadecimal `content_sha256`. Required with `verification_run_id`. |
| `acknowledge_failed_stop` | Optional digits-only ledger event sequence, admitted only for `restore-services`. After owner review it acknowledges the exact integrity-failed stop for writer restoration; it authorizes no repair or continuation past that stop. |
| `wall_clock_seconds` | Required integer delete-loop budget, 1–1800 seconds. Leave blank for every other mode. It is not a rewrite timeout or a maintenance-window estimate. |

For each imported artifact the workflow authenticates GitHub's run identity,
the same repository and workflow, `main`, successful completion and producing
mode. The receipt's `source_git_sha` must equal that successful source run's
`head_sha`; its seal must equal the supplied SHA-256. A copied or
edited receipt, an ops-workflow artifact, a failed run, or the wrong producing
mode is refused. The fixed artifact names are `v3-derived-purge-plan` and
`v3-derived-purge-verification`, each containing `receipt.json`. Keep the reviewed
plan run ID and seal, then the verification run ID and seal, with the operator's
phase record. Only `authorize` requires the plan's source SHA to equal the current
execution SHA. After authorization, later phases and recovery retain the
original immutable plan and exclusion proof even if `main` advances; each new
dispatch still executes exact current `main`. This preserves recovery access
without substituting a new plan for the existing ledger requests.

After installation and all design execution gates have passed, dispatch in this
order, reviewing each receipt before approving the next phase:

1. `plan` in the dedicated workflow. Review its complete sealed receipt,
   exact targets/source/schema identities, stopped workers, unchanged pointers,
   published counts, storage/WAL evidence and freeze-age horizon. Retain the run
   ID and `content_sha256`.
2. `authorize` with that `plan_run_id` and `plan_sha256`. Authorization requires
   a plan no older than one hour from the exact current execution head; an expired
   plan or a source change needs a fresh plan and review.
   This marks both immutable targets `FAILED` without deleting payload.
3. `verify-system-archetype-empty` with the same plan inputs. Review and retain
   its successful sealed artifact, run ID and `content_sha256`. An archetype or
   cluster target row stops the purge; there is no delete mode for those tables.
4. `delete-system-search`, repeating that same mode as needed until both target
   counts are zero; then `rewrite-system-search`. Supply both authenticated
   artifact pairs to every dispatch. Review verified physical reclamation and
   restored autovacuum before advancing.
5. `delete-economy-opportunity`, then `rewrite-economy-opportunity`; next
   `delete-body-mechanics`, then `rewrite-body-mechanics`; finally
   `delete-system-rating-vector`, then `rewrite-system-rating-vector`. Repeat
   bounded deletes where needed, always completing and reviewing one relation's
   rewrite before starting the next relation.
6. `complete` with both artifact pairs. Review its completion receipt: zero
   target rows alone do not establish reclamation or completion.

P2d's rehearsal figures must be present in the reviewed plan **before** any
delete, rewrite, or abort dispatch can run. The current plan producer supplies
no measured rewrite allowance, rewrite peak/timeout or autovacuum-release budget,
so these phases remain fail-closed until P2d integrates the rehearsal evidence
into plan generation before sealing. Per relation, review the cadence and
`delete[relation].rows_per_second`, `rewrite_allowance_seconds`, and
`autovacuum_budget_bytes`, plus `rewrite[relation].rewrite_peak_bytes` and
`statement_timeout_ms`; JSON relation keys use underscores. A conservative
throughput fallback is not a rehearsal measurement. Do not edit a downloaded
artifact: changing it invalidates its seal and authenticated run provenance.
P2c neither performs P2d nor supplies substitute production figures.

On interruption, inspect `status` first. An open writer/service fence requires
`restore-services`, using both artifact pairs, before a fresh destructive phase;
the action cancels and resolves any recorded batch or rewrite before restoring
writers. Supply `acknowledge_failed_stop` only after the owner's explicit review
of the exact integrity-failed event. To abandon an autovacuum fence, use the
matching `abort-relation-<relation>` with both artifact pairs after restoring any
orphan writer fence. Abort requires its rehearsal-derived release budget and
sufficient headroom; it leaves the relation unreclaimed and `complete` blocked.
Resume from fresh status/count evidence and a reviewed plan through the matching
delete or rewrite path. The detailed recovery rules below remain mandatory.

The workflow holds `v3-production-application-authority` concurrency and the
job's `chatgpt-ed-new-ops` concurrency with cancellation disabled. It polls and
waits for the remote action to exit, including budget expiry or `FAILED_STOP`,
so those fences remain held for the entire phase. The host purge lease and
durable ledger independently protect against runner or SSH loss. Only the
independent rewrite monitor may outlive the controller, as described below.
Every run tees its JSON receipt and attempts receipt upload even on failure;
missing receipt files fail the upload, and retention is 180 days. Retain and
review those receipts before proceeding. The general artifact is
`v3-derived-purge-receipt`, containing `receipt.json`; only successful plan and
exclusion-verification runs publish the corresponding reusable sealed artifact.

The job timeout is 180 minutes. A delete loop admits at most 1800 seconds
(30 minutes), its longest statement/batch allowance is 2700 seconds (45 minutes),
and the remaining 105 minutes allow preflight, cleanup and bounded recovery
queries. Rewrite plans are admitted only with per-relation
`statement_timeout_ms` at most 7,200,000 (120 minutes), leaving 60 minutes for
preflight, recovery and writer restoration. A larger reviewed rewrite timeout
is refused before SSH; it requires a reviewed workflow budget change, not a
free-text dispatch override. These are controller limits, not rehearsal throughput
or outage estimates.

Delivery follows the schema migration workflow's bounded source-bundle precedent:
a bounded `git archive` of the committed operator/release helpers, production
authority and migrations, plus a credential-free `.git` tree, is sent as a tar
bundle over pinned SSH from trusted `main`. The action verifies the Git SHA and
committed backup-wrapper blob; the sealed JSON artifacts retain their separate
content authentication. The protected bundle is extracted into a root-owned
temporary `/run/edfinder-v3-purge-source.XXXXXXXX` tree; that tree remains until
reboot so an independent rewrite monitor can still verify and load its source
after controller loss. The ops read-only source tree is removed after its
action exits.
No repository credential is sent to the host. `GITHUB_RUN_ID` and the remote
controller PID/start identity bind action liveness to the polling controller.

## Action modes and receipt order

`scripts/operator/actions/v3-derived-generation-purge.sh` delegates fixed SQL
and receipt handling to `scripts/operator/lib/v3_generation_purge.py` and the
transaction adapter `scripts/operator/lib/v3_purge_transactions.py`, extended
by `scripts/operator/lib/v3_purge_delete.py` for delete/recovery orchestration,
`v3_purge_rewrite.py` and `v3_purge_rewrite_dispatch.py` for rewrite/recovery,
and `v3_purge_rewrite_monitor.py` for the independent watchdog. All three new
files participate in both the purge script hash and F2d operator-code identity.
Implemented modes are `plan`, `status`, `authorize`,
`verify-system-archetype-empty`, `complete`, `restore-services`, and the four
relations’ `delete-`, `rewrite-` and `abort-relation-` modes. The four exact relation names
are `system-search`, `economy-opportunity`, `body-mechanics`, and
`system-rating-vector`. Every other mode is unknown and fails closed.
These are action contracts for the protected dispatch above, not an instruction
to run them manually against production.

After installation and execution prerequisites have been satisfied, the order
is:

1. `status` reports unresolved ledger state first. An open batch, rewrite,
   service, writer, or autovacuum fence remains durable even if its backend or
   runner has died. Use the recovery procedures below for an interrupted batch
   or writer fence, including an open rewrite. Unknown state
   refuses mutation. Recovery mode and
   recorded backend identity come from a metadata-only snapshot before any
   payload counts or sizes are probed. Each relation is then probed separately;
   a relation locked by a live recorded `REWRITE_STARTED` backend, or whose
   probe reaches the lock timeout, reports `null` with a reason. A live
   `VACUUM FULL` therefore cannot prevent recovery status from being reported.
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
   three cluster relations and the wide `v3_derived.system_archetype` table
   again. A target row stops the purge with `FAILED_STOP` evidence; it never
   grants a deletion path for those relations. Retain its sealed successful
   receipt and `content_sha256` as the exclusion-verification proof.
   This and `complete` authenticate the original immutable receipt without
   expiring it during a multi-day purge; only `authorize` admits a plan no older
   than one hour. The verification receipt likewise has no freshness expiry;
   all live phase gates still run again.
5. Delete the four relations in dependency order: Search, opportunity,
   mechanics, rating vector. Migration 016 enforces that dependency order. Each
   relation still needs a separate verified physical rewrite and restored
   autovacuum fence before progressing to the next relation. Every destructive mode requires
   `--verification PATH --verification-sha256
   SHA256`, authenticating the sealed successful exclusion-verification
   receipt against the immutable reviewed-plan identity and both current
   ledger purge IDs. The delete and recovery procedures below apply.
6. `complete --plan PATH --plan-sha256 SHA256 --verification PATH
   --verification-sha256 SHA256` requires that same proof and refuses until every target
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
mode, open-fence deadlines and observable backup skips. Its optional
`--verification PATH --verification-sha256 SHA256` inputs authenticate the
exclusion-verification proof against `reviewed_plan_sha256` and both purge IDs
in the current ledger requests. Without that proof,
`system_archetype_verification.status` is `not_proven`, and after authorization
the next admissible mode remains `verify-system-archetype-empty` rather than
advancing to deletion. Neither a receipt nor
a successful read-only mode substitutes for the remaining owner execution
gates, protected workflow, or disposable crash rehearsal.

P2b1 samples live XID/MultiXact rates over five seconds, retrying at most three
times if a vacuum moves a MultiXact baseline. Its conservative planning horizon
is 24 hours with ceilings at 80% of each effective freeze limit, including
TOAST. These are authorization evidence, not rehearsal-derived execution
budgets: execution must bind remaining dispatch/rewrite time to the reviewed
cadence
before opening a fence. Exact-count SQL is bounded at 45 minutes, the controller
at one hour, and the competing-writer grace at 30 seconds with one-second SQL
probes. The 016 function-local timeout settings are unchanged. Host gates are
refreshed after long count scans before a transaction writes. Backup skip
observations cover at most the latest 1,000 journal entries in seven days;
unavailable journal evidence is `null`.

016 has no dedicated exclusion-verification function or event kind suitable
for successful exclusion verification: its existing kinds represent failures,
recovery, or phases with their own mandatory verifiers. The action therefore
uses the sealed successful receipt above without modifying 016. It counts the
four exclusions directly and uses the public `purge_record_event` function for
authenticated `FAILED_STOP` records. The summary view is
`v3_app.system_archetype_summary`; 016 grants the executor no access to
`v3_app`, so the action omits the view count and retains the direct target-row
check against `v3_derived.system_archetype`. It never supplies an archetype or
cluster deletion capability. Completion relies on 016's `REWRITE_VERIFIED`
events, whose verifier already proves the rewritten filenode and trailing
`ANALYZE`; P2b1 does not synthesize those events.

## P2b2a delete dispatch and stopping

The protected workflow and disposable rehearsal are prerequisites for later
production execution. The following describes the action contract for reviewed
execution; it does not authorize a manual production invocation.

A `delete-<relation>` dispatch requires both authenticated artifacts: `--plan
PATH --plan-sha256 SHA256` and `--verification PATH --verification-sha256
SHA256`. Its `--wall-clock-seconds` budget defaults to 300 seconds and accepts
1–1800 seconds. `--controller-pid` and `--controller-run-id` (matching `GITHUB_RUN_ID`)
bind its lifetime to the controller; the controller PID/start ticks must remain
alive. `--writer-mode=read-only` is the only accepted writer mode. The
launcher waits for the loop to exit. It holds the non-blocking purge lease
`/run/lock/edfinder-v3-derived-purge.lock` through cleanup, and also holds
`/run/lock/edfinder-v3-pgbackrest-schedule.lock`; a running pgBackRest backup or
verify process refuses admission. `authorize` and `complete` also use the
schedule lock/process gate. A scheduled backup that overlaps the lease uses
the installed wrapper's skip path; retain the skip observations in the receipt.

A matching unresolved `BATCH_STARTED` is resolved first from its durable key
range and database counts, after cancellation of its recorded live backend
through `v3_meta.cancel_purge_batch` and a bounded wait. PID reuse is checked
with `backend_start`. A different relation's open batch or autovacuum fence
refuses the dispatch. An open writer/service fence from an interrupted
controller requires `restore-services` before a new delete dispatch.

This restoration requirement applies even when no batch remains open, and to
every new mutating phase: `authorize`, `complete`, `delete-`,
`abort-relation-`, and new `rewrite-` phases. A new phase never adopts
a writer or service fence left by another dispatch. Restore the interrupted
dispatch first; aborting an autovacuum fence cannot leave application writes
disabled.

The action opens or adopts the relation's `AUTOVACUUM_DISABLED` fence through
016, preserving the ledgered prior heap and TOAST settings. Adoption remeasures
XID and MultiXact ages against the original ceilings; it never resets the
fence's clock. Before opening or adopting a fence, and before every batch, the
projected time to the nearer heap or TOAST XID/MultiXact ceiling must cover the
relation's **remaining target rows divided by
`reviewed_plan.delete[relation].rows_per_second`, plus its reviewed
`rewrite_allowance_seconds`**, and at least this dispatch's budget plus 65
seconds. The throughput must account for the planned cadence across dispatches.
The plan generator records a conservative fallback of one row per second with
`rows_per_second_source: conservative_fallback`; rehearsal may supply a measured
or configured cadence. It supplies no rewrite allowance: rehearsal must add that
relation's allowance before sealing and reviewing the plan. Missing or invalid
horizon fields refuse with `autovacuum_fence_horizon_not_reviewed`; the action
never invents a rewrite time. The receipt records the remaining horizon and each
scope's projected deadline. A horizon that does not fit refuses with
`autovacuum_fence_deadline_unsafe` and recommends `rewrite-<relation>` when fresh
counts prove the relation logically empty, otherwise `abort-relation-<relation>`.

It enables the selected writer fence with
`purge_set_writer_fence`, commits that change, recycles the application role's
other sessions with `purge_recycle_writer_sessions`, then probes a fresh login
and records `purge_verify_writer_fence`. An already verified fence for this
active dispatch may be reused. The API stays up, reads continue, and application
writes fail closed during the fence. The exact running write-capable container
set comes from `deploy/v3-production/target-authority.json`, including container
IDs, and is retained in root-owned host state. No containers are stopped under
option (b). An authority-listed API slot removed by the deployer or never created
at bootstrap counts as stopped only on Docker's exact name-specific
`No such object` exit. Other inspect failures, malformed or mismatched identities,
and running application containers outside the authority refuse execution.

Before every small batch, the action records and checks all of the following:

- Data-filesystem free bytes cover **100,000,000,000 bytes plus 1.5 times the
  relation's per-batch peak-growth reservation**. The authenticated plan may
  supply a rehearsal reservation; otherwise the receipt names the conservative
  fixed fallback of 900,000,000 bytes. The reviewed plan must supply each
  relation's batch limit; the plan generator proposes 1,000 rows. A missing
  reviewed bound refuses execution. That bound and 016's limit of 100,000 rows
  both apply. Both values are recorded in the receipt.
- `pg_wal` remains on that filesystem. No slot is inactive or has `wal_status`
  `extended`, `unreserved` or `lost`. The archiver's `failed_count` has not
  increased from the dispatch snapshot, and `last_failed_time` is no newer than
  `last_archived_time`. Delete and abort receipts measure physical `pg_wal`
  directory bytes for both `wal_before` and `wal_after`, using the same probe as
  plan/authorize; unavailable measurements refuse execution.
- Named workers are stopped, no autovacuum is running on the relation or its
  TOAST relation, and the recorded controller is alive.
- The bounded competing-writer wait finds no other backend with a
  `backend_xid`; the receipt records the wait. Read-only snapshots do not count
  as writers.

016's `purge_start_payload_batch` durably records the backend and deterministic
key range before `purge_derived_payload_batch` executes on that same session.
A batch monitor can cancel only that recorded backend through
`cancel_purge_batch` if free space crosses the floor. Every later iteration
rechecks the gates. A failed gate records `FAILED_STOP` with its measurements
and starts no further batch. Controller loss stops after at most the current
batch. A wall-clock stop also preserves all committed batches; the next
dispatch resumes from database counts. Published-survivor drift, pointer
change, retained-metadata drift, FK/index failure, or an unknown integrity or
FAILED_STOP recording outcome sets `integrity_failed: true`.

When target rows reach zero, the receipt recommends `rewrite-<relation>` and
leaves the autovacuum fence open. Dispatch the separately reviewed rewrite next. Zero rows reclaim no physical disk by
themselves and never satisfy `complete`.
Successful delete receipts include the final boundary's validated integrity
checks in `fk_check` and a fresh relation/index/TOAST size observation in
`relation_bytes_after`. An unavailable observation stops completion.

## Exit, signals and writer restoration

On normal exit, INT, TERM or HUP, cleanup asks the loop to stop after its
current batch and waits until it has exited. It resolves any open batch before
restoring the application role's writer default. Cleanup never releases the
host lease or restores writers while the loop is alive. After an
integrity-failed `FAILED_STOP`, cleanup restores nothing: the writer fence
remains open for owner review, while the durable ledger continues to block
other mutators after the process exits.
Cleanup also preserves the writer fence when local integrity evidence fails or
is unknown, even if recording FAILED_STOP errors. The receipt reports
`integrity_failed: true` and `failed_stop_recorded: null` when that commit is
unproven. A recording error after a non-integrity stop is likewise an unknown
outcome and refuses automatic restoration, including on INT, TERM or HUP.

Restoration uses the exact prior role value in `WRITER_FENCE_ENABLED`: set
`off`, or unset with `RESET`. `purge_set_writer_fence` commits that restoration
with an unverified record; only then does cleanup recycle the role's sessions,
probe a fresh role connection for `off`, and append the verification through
`purge_verify_writer_fence`. This second recycling step also replaces pooled
connections that reconnected while the fence was enabled. Only durable verified
restoration closes the fence. CPython 3.14 is mandatory; a missing exact runtime
returns the `python314_required` receipt before host/database access. Script
identity includes the committed pgBackRest wrapper so local drift refuses
admission. Each successful non-status receipt derives `wal_byte_delta` from its
before/after LSNs with `pg_wal_lsn_diff`; an unprovable delta fails closed.
After verified restoration, the receipt's canonical `writer_fence` reports the
restored state; `writer_restore` retains restoration details.

## Interrupted dispatch: restore-services

Inspect `status` and retain its evidence first. The idempotent
`restore-services` mode requires the authenticated plan and sealed exclusion
proof. It holds the same host and backup-schedule leases. It resolves any open
batch before restoring writers: cancel the exact recorded live backend through
016, wait until it is gone, then check the recorded key range and its closing ledger event. A successful
batch records `BATCH_COMMITTED` in the delete transaction itself; an open start
whose recorded backend has departed is therefore resolved as `BATCH_ROLLED_BACK`. It never assumes a missing client means
a rollback. An open `REWRITE_STARTED` is cancelled through
`cancel_purge_rewrite`, awaited until its exact backend is gone and neither
progress view shows the relation, then resolved by the rewrite procedure below
before writer restoration.

After an integrity-failed stop, restoration requires owner review and the exact
`--acknowledge-failed-stop=<event-sequence>`. The amended, unapplied migration
016 accepts the optional acknowledgement only on writer restoration. It must
name an existing `FAILED_STOP` with `integrity_failed: true` belonging to the
same plan (including a sibling request); missing, non-integrity, wrong-kind,
wrong-plan or enable-path acknowledgements refuse. The dedicated
`purge_set_writer_fence(uuid,boolean,bigint)` records it in
`WRITER_FENCE_RESTORED.operational_payload`; session recycling and fresh-login
verification preserve that payload. No synthetic failure or service event is
used. For a terminal failure after a committed rewrite, the acknowledgement
must also bind that relation's exact `start_event`; 016 proves its recorded
PID plus `backend_start` is gone and neither progress view shows maintenance
before permitting writer restoration. This resolves the earlier mismatch where
P2a treated `FAILED_STOP` as terminal but 016 still required rewrite verification
or rollback. It supplies no `REWRITE_VERIFIED` or autovacuum restoration and
keeps the original integrity stop intact. The trap never supplies owner
acknowledgement.

The original integrity `FAILED_STOP` remains untouched. P2a continues to refuse
other mutators on that event even after owner acknowledgement: an integrity
failure needs separately reviewed repair authority. Acknowledgement grants no
data repair or pointer-change authority, and the trap never supplies it
automatically. For restoration without an integrity failure, the two committed
steps and fresh-role verification above apply; already verified restoration is
a safe no-op. Under option (b) there are no stopped services to restart.
Quiesced-service restoration remains refused until a future owner decision and
implementation select option (a).

## Abandoning a relation: abort-relation

`abort-relation-<relation>` releases only that relation's autovacuum fence after
its authenticated plan/proof and recovery gates pass. The authenticated plan's
optional `reviewed_plan.delete[relation].autovacuum_budget_bytes` must carry a
valid rehearsal-derived measurement. The plan generator supplies no default: abort
is unavailable until P2d's rehearsal figures are included in the reviewed plan,
and missing evidence refuses with `autovacuum_budget_not_measured`. Invalid
values fail plan validation with `autovacuum_budget_invalid`. Measure free space
and the current heap-plus-index bytes first. Required headroom is the 100 GB floor plus
`max(autovacuum_budget_bytes, current heap-plus-index bytes)`. If that does not
fit, the receipt reports the shortfall and leaves the fence open; free space
must be added before retrying.

After that gate, the action restores the exact ledgered heap and TOAST
`autovacuum_enabled` states through `purge_set_relation_autovacuum` and appends
`AUTOVACUUM_RESTORED`. The preceding budgeted `FAILED_STOP` carries
`aborted: true` and measured headroom. The
relation remains physically unreclaimed. Fresh counts for both targets determine
the receipt's next mode: `delete-<relation>` when target rows remain,
`rewrite-<relation>` only when both counts are zero, and `status` when counts
are unproven. `complete` continues to refuse until verified physical rewrites
exist. Rewrite establishes a new autovacuum fence when adopting an aborted
relation, then verifies the physical rewrite before restoring it.


016 has two additional recovery constraints that this action preserves. Its
`AUTOVACUUM_RESTORED` function copies only the prior heap/TOAST options into
that event's payload, and its generic recorder refuses a caller-created
`AUTOVACUUM_RESTORED`; the design's abort/headroom evidence therefore lives in
the prerequisite `FAILED_STOP` instead of that closing event. Likewise,
`BATCH_COMMITTED` is appended only atomically by `purge_derived_payload_batch`;
recovery cannot invent it. A departed backend with a still-open start proves
that delete did not commit, and recovery records `BATCH_ROLLED_BACK`. The
recorded key range is checked before that resolution. Owner acknowledgement
uses only the dedicated 016 writer-restoration amendment described above; no
grant or data-mutation guard is broadened.


## Physical rewrite and recovery

Use the same authenticated plan and sealed exclusion proof as deletion. The
four relations follow the same FK order: Search, opportunity, mechanics,
rating vector. Both target counts must be zero, logical completion must be
ledgered, and no batch or different relation's autovacuum fence may remain open.
An existing autovacuum fence is adopted with its original age ceilings; an
aborted fence is re-established through 016 with exactly the delete age and
remaining-horizon checks. Writer mode remains option (b), verified read-only.
The host purge lease and pgBackRest schedule lock cover the entire dispatch,
backend, recovery and restoration. The persistent maintenance client inherits
both lock descriptors so they remain held if the wrapper disappears; the
monitor itself holds neither lock.

Before dispatch, P2d must supply and seal
`reviewed_plan.rewrite[relation].rewrite_peak_bytes` and
`statement_timeout_ms`. Relation keys use underscores. There is no default for
either field: missing peak refuses with `rewrite_peak_not_measured`, and missing
timeout with `rewrite_statement_timeout_not_measured`. The pre-start free bytes
must cover 100,000,000,000 plus 1.5 times that measured peak. The installed
wrapper hash and heap/index/TOAST/temp/WAL placement are rechecked. The plan's
existing delete `rewrite_allowance_seconds` must also cover the age horizon;
it does not substitute for the measured peak or statement timeout.

The physical phase has exactly three steps:

1. Commit `REWRITE_STARTED` through 016 on the maintenance backend, recording
   the relation OID, original filenode, heap/index/total sizes, PID and
   `backend_start`.
2. Start the independent monitor and wait for its readiness handshake, then
   issue the one fixed `VACUUM (FULL, ANALYZE)` command on that same backend
   under `v3_derived_purge_executor`. It runs outside a transaction, with a
   five-second lock timeout and the reviewed per-relation statement timeout.
3. After backend exit, verify changed filenode, `last_analyze` later than the
   start, exact published counts, pointers and retained metadata, valid FKs,
   indexes/triggers and measured sizes. Append `REWRITE_VERIFIED` through 016;
   its verifier restores the exact prior heap/TOAST autovacuum options.

A verified retry opens no new rewrite or autovacuum fence. An unresolved start
is observed through metadata before touching the heap. Re-dispatch refuses
while its recorded backend or either `pg_stat_progress_cluster` or
`pg_stat_progress_analyze` shows the relation. Once idle, an unchanged filenode
closes with `REWRITE_ROLLED_BACK` and permits a fresh normal rewrite. A changed
filenode causes recovered `ANALYZE`, verification that its timestamp trails the
start, and `REWRITE_VERIFIED` with `recovered: true`; it never runs a second
`VACUUM FULL`. A failed verification of a changed filenode records `FAILED_STOP`
with `rewrite_committed: true` and `integrity_failed: true`, preserving the
writer fence. Unknown integrity evidence likewise cannot reopen writes.

On INT, TERM or HUP, the trap cancels only the recorded backend through 016,
waits for it and both progress views to clear, and performs that same filenode
resolution before restoring writers. `restore-services` uses this identical
resolution. Existing orphan writer/service fences still require
`restore-services` before a new destructive phase. A matching `rewrite-R` may
first perform recovery only when its exact same-plan start and verified writer
fence remain open: it refuses an active backend, resolves an idle start and
restores the old writer fence before returning or starting any fresh phase.
Other relations, services and integrity stops cannot use that narrow recovery
entry. After an integrity stop,
automatic cleanup never restores writers; owner acknowledgement permits only
writer restoration, while P2a continues to block every other mutator pending
separately reviewed repair authority.

## Independent rewrite monitor

The action launches a transient root-owned `systemd-run` unit named
`edfinder-v3-purge-rewrite-<start-event>`, using exact CPython 3.14. Its config
and readiness handshake live under root-owned mode-0700
`/run/edfinder-v3-purge-monitors`; files are mode 0600. Source and its ancestors
must be root-owned and not group/world writable, and the unit verifies the
hashed script identity. A root-owned installed source tree is therefore an
execution prerequisite; this coding change installs nothing. The monitor is
pinned to the container ID, backend PID and `backend_start`, with PID/start-tick
identities for both wrapper and controller. It owns no lease and survives
controller disappearance.

Every 250 ms, with bounded database/host probes, it checks data-filesystem free
bytes against the 100 GB floor, physical `pg_wal` bytes and placement, slot
health, both archiver predicates (start `failed_count` must not rise, and
`last_failed_time` must not be newer than `last_archived_time`), and controller
liveness. No independent WAL-growth ceiling is imposed: WAL shares the monitored
filesystem and the owner floor applies. On a breach or controller loss it calls only
`v3_meta.cancel_purge_rewrite`; 016 authenticates the recorded backend and
appends `REWRITE_CANCEL_REQUESTED` with the condition. Cancellation is retried
until the backend exits, including the short pre-VACUUM idle window. Other
observations are read-only. The unit never signals another backend and exits
when the exact recorded backend disappears. It removes its config/handshake
on exit. Failure to establish readiness prevents VACUUM from starting.

The additional PG18 rewrite and monitor tests are isolated in
`tests/test_v3_purge_rewrite_pg18.py` and
`tests/test_v3_purge_rewrite_monitor_pg18.py` so their maintenance cost is visible rather
than hidden in the existing long purge module. They use disposable fixtures
and cover committed/rolled-back recovery, recovered ANALYZE and completion.
The fixture's catalog-maintenance suppression and bounded writer drain keep
background catalog autovacuum from racing 016's unchanged XID check.
