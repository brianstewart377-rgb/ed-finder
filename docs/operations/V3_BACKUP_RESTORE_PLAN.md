# ED-Finder V3 backup, PITR, and disaster-recovery plan

Status: planning and review only

Review date: 2026-08-26

Authority: ADR-020, ADR-002, ADR-010, ADR-014, ADR-015, ADR-021, and the V3 guardrails

## Objective

Protect the preserved Phase 4C candidate and later production data according to value and rebuildability, prove recovery before cutover, and avoid pretending that one daily logical dump is an adequate recovery strategy for a 1+ TB V3 system.

This plan is subordinate to [the readiness plan](V3_PRODUCTION_READINESS_PLAN.md), [acceptance gates](V3_PRODUCTION_ACCEPTANCE_GATES.md), and [rollback plan](V3_ROLLBACK_RUNBOOK.md). It authorizes no backup, server access, restore, or cutover action.

## Recovery principles

1. PostgreSQL is authoritative. pgBackRest physical backup plus continuous WAL archive is the primary recovery path.
2. A backup is not accepted until it is restorable and the restored database passes identity and application-level verification.
3. Protected off-host copies use a distinct failure and account boundary. Production credentials cannot delete protected history.
4. Canonical generations are rebuildable but expensive; private/security records and evidence/provenance ledgers may be irreplaceable.
5. NATS JetStream carries work but is not authoritative. Redis is disposable and is not backed up as a source of truth.
6. Cutover creates an asymmetric boundary once V3 accepts writes. Recovery must preserve the precise write-enable time and WAL position.
7. Retention that is safe for a small private table is not automatically economical for the full canonical corpus.

## Protection classes

The values below are initial planning objectives from the V3 DR review. They remain provisional until owners approve them and Phase 4C/restore evidence demonstrates feasibility.

| Class | Examples | Loss impact | Initial RPO | Initial RTO | Primary protection |
|---|---|---|---:|---:|---|
| A — private/security | Accounts, external identities, Commander access, sessions/revocation, device/service credentials, personal-data requests, security audit | Irreplaceable ownership/privacy/security state | 5 minutes | 4 hours | PITR, encrypted off-host physical backup, selected logical export |
| B — evidence/provenance | Source rights, acquisition/source runs, generation inputs, contribution/withdrawal receipts, validation/publication audit, effect receipts | Trust and legal/audit loss | 5 minutes | 8 hours | PITR, protected physical backup, selected logical export, immutable artifacts |
| C — curated canonical | Published canonical generation and vocab needed for API service | Service unavailable; expensive reconstruction | 15 minutes | 12 hours to queryable; 24 hours to enriched | Physical backup/PITR and retained source artifacts |
| D — rebuildable bulk | Candidate/unpublished canonical builds, staging, quarantines where source is retained | Time/cost loss | 24-hour source freshness | 24–72 hours | Source artifacts plus optional physical retention |
| E — derived products | Facilities/suitability/map buckets and other READY products | Degraded features; recomputable | Pinned-input RPO | 24–72 hours | Recompute from pinned canonical generation; optional physical backup |
| F — async transport | NATS streams/consumers | Delivery delay or duplicate replay | No authoritative data loss | 4 hours | Config as code; rebuild/redrive from PostgreSQL outbox/jobs |
| G — disposable cache | Redis/cache entries | Temporary latency/cold cache | None | 15–60 minutes | Rebuild; no backup |
| H — source/evidence artifacts | Full source seed, deltas, manifests, receipts, configuration evidence | Rebuild or audit becomes impossible | Zero loss after acceptance | 24 hours | Checksummed immutable off-host object storage |
| I — configuration | Compose/manifests, grants, dashboards, alert rules, OpenAPI, generated DTO, runbooks | Slow or unsafe rebuild | On every accepted change | 2–4 hours | Version control, signed release bundle, protected secrets escrow |

An owner may tighten an objective. Relaxing a Class A, B, H, or security objective requires architecture, security/privacy, and operations approval before cutover.

## pgBackRest topology

### Repository layout

- `repo1`: local/near-host repository for fast operational recovery. It is convenience, not disaster recovery.
- `repo2`: encrypted off-host repository in a different account/failure domain with TLS, bucket/version/object protection, access logging, and recovery keys held outside the production host.
- The PostgreSQL host can append backups/WAL to the approved location but cannot permanently delete protected `repo2` history.
- Repository names, stanza, cipher scheme, key escrow, immutability/object-lock duration, and restore identities are recorded in the release packet without exposing secret material.

The design must prove no archive command silently falls back to local-only success. Loss of `repo2` delivery raises an alert even if `repo1` remains healthy.

### Initial cadence and retention

These are provisional operating values to benchmark and then either accept or replace with measured values:

- Continuous WAL archiving; `archive_timeout` target 5 minutes.
- Incremental physical backup every 6 hours.
- Differential physical backup daily.
- Full physical backup weekly.
- Local repository: two recoverable chains and approximately 14 days, subject to capacity evidence.
- Protected off-host repository: six recoverable chains and approximately 42 days, subject to cost/capacity evidence.
- Critical logical exports: daily with 35 daily, 12 weekly, and 12 monthly copies where privacy/erasure and restore tests approve that retention.
- Global roles/tablespaces/configuration: daily and after every accepted role or configuration change.
- Whole-database logical dumps: optional monthly diagnostic copy only if Phase 4C-size benchmark proves runtime, space, consistency, encryption, and restore value. They never replace pgBackRest/PITR.

The backup scheduler must refuse overlap that endangers the WAL archive, filesystem headroom, API latency, or maintenance window. A failed backup never ages out the last known-good chain.

### WAL and PITR controls

- Enable and verify archive mode, deterministic archive command, checksums, `fsync`, `full_page_writes`, and production-approved `synchronous_commit`.
- Monitor archive success/failure, last archived WAL age, queue/spool size, retained `pg_wal`, timeline changes, and repository free space.
- Record the UTC time, timeline, current/replay/checkpoint LSNs, backup set, and archive range at every cutover checkpoint.
- Recovery targets use unambiguous UTC timestamps plus the recorded LSN; a timestamp alone does not identify the write boundary.
- Restores never write into the production data directory. Use an isolated namespace/host, distinct ports, non-production credentials, and outbound network deny until validation finishes.
- Timeline history and WAL required by retained backups are protected from premature expiration.

## Source-artifact and evidence retention

The accepted full Spansh seed, its manifest, acquisition/source-rights record, SHA-256, byte length, importer/normalizer/baseline identities, rejection evidence, and final Phase 4C receipt remain protected through the full cutover and rollback window. Initial off-host retention is at least 90 days after cutover, followed by a documented legal/cost/rebuild review. The source file is not silently replaced by a same-named object.

Routine deltas or transient acquisition files may use a 7–14 day operational retention only after their accepted source-run and canonical-evidence receipts are durably stored and the generation can be explained without the raw transient object. Evidence required for rights, attribution, withdrawal, audit, or reproducibility follows its governing retention, not the transient-file default.

Validation receipts, promotion envelopes, publication audit, cutover/rollback receipts, backup/restore receipts, configuration bundles, and acceptance packets are immutable release evidence. They are not rotated with general logs.

## Private data, erasure, and backup restoration

Backups are access-controlled personal-data stores. The privacy owner must approve locations, processors, jurisdiction, encryption/key custody, access logging, retention, legal holds, and breach procedures.

Deletion or withdrawal from the live database does not rewrite immutable backup history. Instead, the live system maintains durable deletion/withdrawal tombstones and a restore procedure that reapplies every applicable tombstone before an isolated restore can serve traffic or be copied onward. Restore validation demonstrates that deleted provider identities, private facts, contribution eligibility, sessions, and export artifacts do not reappear.

Logical exports of Class A/B data are encrypted independently, minimize fields, exclude raw credentials/tokens, and have an explicit disposal receipt when retention ends.

## NATS and Redis recovery

NATS stream/account/consumer configuration is versioned as code. Optional JetStream snapshots may be retained briefly (initial planning value: about seven days) only if a restore drill proves they improve RTO. They are never counted as the only copy of a command, job, publication event, or user mutation. A total NATS loss is recovered by recreating configuration and redriving pending PostgreSQL outbox/job state with stable message IDs and effect-receipt deduplication.

Redis has no authoritative backup. Recovery creates an empty instance, validates namespace/version configuration, resumes with bounded warm-up, and monitors load amplification. Any feature that cannot tolerate empty Redis fails architecture review.

## Restore and verification programme

### Automated checks

Every backup cycle verifies repository metadata, checksums, WAL continuity, encryption access, expected databases, backup size/duration, and expiration safety. A successful process exit without repository/catalogue checks is not enough.

Initial alert limits from the reviewed operating model are:

- last archived WAL older than 10 minutes: page;
- latest incremental older than 8 hours: page;
- latest differential older than 26 hours: page;
- latest full older than 8 days: page;
- critical logical export older than 26 hours: page;
- latest isolated restore receipt older than 35 days: page;
- latest clean-host recovery receipt older than 100 days: page.

The final monitoring plan records actual route, owner, runbook, and test receipt.

### Drill cadence

| Cadence | Drill | Minimum proof |
|---|---|---|
| Every backup cycle | Catalogue/checksum/WAL continuity validation | Machine-readable check result linked to backup set |
| Daily | Repository and restore-point inventory | Both repos visible; no silent local-only condition |
| Weekly | Deeper verification and selected file/object restore | Checksums and encryption access verified |
| Monthly | Isolated restore from protected off-host repository | Database starts; identity, integrity, grants, and application probes pass |
| Quarterly | Clean-host recovery from documented prerequisites | Approved RPO/RTO measured without hidden local state |
| Event-driven | Before cutover; after backup tool/credential/topology/major PostgreSQL change | Full applicable drill repeated and signed |

### Candidate restore acceptance

Before V3 cutover, restore the protected Phase 4C candidate into an isolated environment and demonstrate:

1. Backup set, stanza, timeline, target LSN, source database identity, and restored identity are recorded.
2. PostgreSQL 18 starts with expected checksums/settings and no unexpected recovery errors.
3. Required roles and grants are restored or reproducibly reapplied; service roles remain non-superuser.
4. Canonical generation manifest, source inputs, relation/table counts, validation receipt, current pointer, and publication audit match the accepted packet.
5. Private/security/evidence tables pass referential, ownership, uniqueness, and tombstone-replay checks.
6. API `/api/v1` read probes return the pinned generation and string-safe identifiers; no V2 fallback is possible.
7. Outbox/job/effect-receipt state is coherent; NATS may be rebuilt empty and redriven without duplicate authoritative effects.
8. Measured RPO/RTO, backup/restore duration, peak scratch space, and bottlenecks are recorded.
9. The restored environment is destroyed or returned to protected quarantine with a disposal record.

### Cutover-boundary PITR drill

The final pre-cutover drill creates two synthetic recovery targets around a representative write-enable marker:

- target A immediately before V3 writes, proving read-only candidate recovery;
- target B immediately after controlled V3 writes, proving those writes, session/ownership/private state, outbox, and audit records survive consistently.

The test must show that recovery to A discards post-boundary writes and recovery to B preserves them without partial effects. This is the evidence for the asymmetric rollback decision.

## Disaster scenarios and recovery order

| Scenario | Immediate action | Recovery path | Completion evidence |
|---|---|---|---|
| Single database corruption/operator error | Freeze writes; preserve logs/WAL; declare incident | PITR to isolated cluster, validate, controlled route | Target LSN, integrity/API checks, approval |
| Host/storage loss | Declare DR; prevent split brain | Restore protected off-host backup/WAL to replacement host | Clean-host receipt and fencing proof |
| Off-host repository/account compromise | Stop archive to affected path without deleting local chain; rotate credentials | Establish clean protected repo, copy from known-good source, verify | Independent security approval |
| WAL archive stalled | Stop risky build/maintenance; protect `pg_wal` headroom | Repair archive, prove continuity, resume bounded work | No missing segment; lag cleared |
| NATS loss | Leave PostgreSQL authoritative state untouched | Recreate config, redrive outbox/jobs, dedupe via effect receipt | Backlog zero and no duplicate effects |
| Redis loss | Start empty instance | Rebuild caches with rate limits | API stable and cache keys correctly partitioned |
| Bad canonical publication | Do not rebuild content | Atomically move pointer to retained valid generation | Publication audit and API readback |
| Bad derived publication | Keep canonical pointer | Atomically move derived release pointer; retain pin | Release audit and combined ID readback |
| Credential/key loss | Revoke/contain, preserve evidence | Use escrowed recovery path, rotate all dependent credentials | Access restored and old credential rejected |

## Capacity admission for backups

The cutover capacity model reserves, at minimum, live database/index/TOAST, retained canonical and derived generations, peak WAL, local backup chain, repository spool, restore scratch space, logs, temporary maintenance/reindex space, and old/new deployment overlap. It uses Phase 4C peak values rather than final database size alone.

BG-14 governs deletion of canonical generations pinned by current or rollback-eligible derived releases. Backup expiration is a separate decision: deleting a live generation does not authorize deleting the recovery history that protects the rollback window. Cleanup fails closed if either live references or backup/WAL dependencies are unknown.

## Ownership and evidence

The Operations/DR owner maintains pgBackRest, repository and drill evidence. The Data/DB owner verifies PostgreSQL/generation identity and restore integrity. Security owns encryption, credentials, off-host account boundaries, and access review. Privacy owns personal-data retention and tombstone replay. The Release owner owns cutover checkpoints and recovery authorization.

Every recovery exercise produces an immutable receipt containing identities, commands/tool versions, inputs, UTC timings, observed RPO/RTO, hashes, checks, exceptions, cleanup, and two-person review. Redact secrets without removing the identifiers required to audit which credential generation or key version was used.

## Cutover blockers

Cutover is blocked if any of the following is true:

- Phase 4C candidate identity or final receipt is incomplete or mismatched.
- Continuous WAL or protected off-host backup is not healthy.
- Production can delete the protected recovery history.
- No successful isolated off-host restore of the exact candidate exists.
- RPO/RTO, storage headroom, or restore scratch capacity is unmeasured or unacceptable.
- The write-enable PITR boundary has not been rehearsed.
- Private-data tombstones/withdrawals cannot be reapplied after restore.
- NATS or Redis is being treated as the only source of authoritative state.
- A current or rollback-eligible canonical/derived generation would be reclaimed.

Post-cutover improvements may automate more drills, add a tested replica/failover tier, or tune retention after measurement. They may not weaken the minimum primary/off-host/PITR/restore controls above.
