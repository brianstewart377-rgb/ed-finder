# ED-Finder V3 rollback and recovery plan

Status: planning and review only

Review date: 2026-08-26

Authority: V3 guardrails, ADR-002, ADR-012, ADR-014, ADR-015, ADR-020, and BG-14

## Purpose

Choose a safe response when validation or cutover fails, preserve authoritative writes and evidence, and avoid the dangerous assumption that traffic can always be switched back to writable V2.

This plan is paired with [the controlled cutover plan](V3_CUTOVER_RUNBOOK.md) and [backup/PITR plan](V3_BACKUP_RESTORE_PLAN.md). It authorizes no rollback, restore, server change, or traffic action.

## First decision: did V3 accept writes?

The cutover commander determines the regime from the durable `V3_WRITES_ENABLED` audit marker, PostgreSQL transaction/timeline/LSN, API access/audit records, private/identity table state, and outbox/effect receipts.

- **Proven no V3 write was accepted:** use the pre-write rollback path.
- **Any V3 write was accepted, or acceptance is uncertain:** use the post-write recovery path. Uncertainty is treated as committed data until disproved.

Feature flags, UI messages, load-balancer state, or an HTTP timeout are not proof that no write committed.

## Universal incident actions

1. Declare the incident/change abort and assign commander, scribe, data, security/privacy, async, and communications owners.
2. Stop further traffic expansion and nonessential automation. Preserve the current database, WAL, logs, outbox, NATS state, deployment/config identities, and monitoring snapshots.
3. Do not rerun the importer/normalizer, mutate canonical content, delete WAL/backups/messages, purge a generation, or retry a pointer/write operation blindly.
4. Capture V2/V3 database identities, timeline/LSNs, current canonical and derived pointers, candidate/promotion state, active images/config, routing, writer sessions, and backup/archive health.
5. Revoke or contain a compromised credential/network path if security requires it, while retaining forensic identifiers.
6. Select the path below and record the authority, expected data effect, abort condition, and verification before executing it.

## Path A — validation failure before production binding

Use when the candidate has not received public traffic or writes.

1. Keep the candidate quarantined and append `REVOKED` with failed gate/evidence.
2. Preserve the Phase 4C receipt, candidate database, backup, and failure evidence.
3. Remove/revoke only the failed production binding or temporary hardening credential through its reviewed reversal; do not alter canonical rows to make a test pass.
4. Diagnose in a physical clone or isolated restore when possible.
5. Fix forward through a separately reviewed operational/config/additive migration, or reject the candidate and return to architecture/build planning.
6. Re-run all gates affected by the change, plus identity equality, before a new approval.

V2 remains unchanged. There is no need for user-visible production rollback.

## Path B — pre-write traffic rollback

Use only when direct evidence proves V3 accepted no user or background authoritative writes.

1. Disable V3 write paths and background dispatchers/builders; verify they are disabled.
2. Route the canary/read traffic back to the known-good V2 read surface using the approved previous edge configuration.
3. If V2 was deliberately made read-only, the accountable owner may restore its previous write mode only after verifying its database/checkpoint, queued work, credentials, and no split-brain writer. This is a distinct recorded decision.
4. Purge/revalidate only mutable edge caches; immutable V3 assets may remain referenced by their content hash but must not be served by active HTML.
5. Keep V3 quarantined with its database, WAL, backup, outbox/NATS evidence, logs, and exact deployed artifacts.
6. Confirm external DNS/edge behavior, V2 read/write smoke as applicable, no traffic to V3, and alert health.
7. Communicate the abort and next review time; append `REVOKED` to the promotion registry.

Completion requires proof that V2 is authoritative for current writes, V3 has no accepted write to migrate, and there is only one writable system.

## Path C — post-write V3 fix-forward

This is the preferred response after V3 writes when database integrity and recovery remain trustworthy.

1. Freeze the affected V3 mutation surface or all V3 writes while keeping safe reads available if approved. Keep V2 read-only.
2. Classify the failure: frontend/edge, API image/config, NATS/consumer, database query/index, identity/privacy, canonical/derived pointer, corruption, or security compromise.
3. Preserve and reconcile accepted requests to authoritative transactions, outbox messages, effect receipts, audit, and user-visible outcomes.
4. Roll back a stateless frontend/API image only if it is schema/contract compatible with the current V3 database and accepted writes. Otherwise deploy a reviewed fix-forward image/config.
5. For transport failure, repair/recreate NATS and redrive PostgreSQL outbox/jobs with stable IDs; do not reverse committed database mutations because delivery lagged.
6. For bad canonical publication, atomically move the canonical current pointer to a retained READY, validated generation and append publication audit/outbox. Do not mutate the bad generation.
7. For bad derived publication, move only the derived release pointer to a retained release pinned to its canonical generation. Do not point products at a different canonical generation.
8. For identity/private/security defects, keep the surface frozen, involve security/privacy, use audited correction/migration procedures, notify affected users when required, and verify no cross-account/canonical leakage.
9. Resume traffic/writes in cutover-style canary steps only after reconciliation, backup/WAL health, targeted regression, monitoring, and accountable approval pass.

Completion requires a recovery receipt, affected-user/data determination, post-recovery backup, and refreshed acceptance evidence for every impacted gate.

## Path D — post-write PITR or restore

Use for corruption, destructive operator error, failed migration, storage loss, or a condition that cannot be fixed safely in place.

1. Fence the failed primary and every writer. Prevent split brain at database, service, and edge layers.
2. Record the last known-good target and the range of potentially accepted writes. Choose a UTC target plus timeline/LSN from evidence, not intuition.
3. Restore the protected backup/WAL into an isolated replacement. Never overwrite the failed data directory.
4. Validate database/generation/source/manifest/publication identity, roles/grants, private ownership, sessions/revocations, contribution/withdrawal, privacy tombstones, outbox/jobs/effects, and `/api/v1` behavior.
5. Reapply deletion/withdrawal tombstones and any approved post-restore secrets/role configuration before serving traffic.
6. Reconcile requests/writes after the restore target using audit/access logs and upstream receipts. Never replay a mutation without idempotency/ownership proof.
7. Recreate NATS configuration and redrive authoritative PostgreSQL state. Start Redis empty.
8. Take a new protected backup/checkpoint of the validated recovered database.
9. Route traffic through a read-only canary, then a controlled write-enable boundary equivalent to the original cutover.

If PITR necessarily loses accepted V3 writes, the accountable owner, data owner, and security/privacy owner must approve the loss assessment and user notification. RPO is a target, not permission to discard data silently.

## Path E — reverse migration to V2

This is an exceptional, separately designed operation—not the default rollback. It is unavailable until a versioned, tested mapping and runbook proves how to carry all post-boundary V3 state into a compatible destination.

The design must cover account/provider/Commander identity, membership/access, session invalidation, device/service credentials, legacy sync-claim status, private facts/imports, contribution/withdrawal, personal-data requests/tombstones, security audit, canonical generation compatibility, outbox/effects, identifiers, timestamps, conflicts, and provenance. V2 must not become writable until reconciliation proves a single owner for every migrated datum and unsupported state is safely quarantined.

Because ADR-001 forbids restoring the V2 database into V3 and the V3 identity/private model is different, a generic dump/restore or column copy is prohibited. Without a passed reverse-migration packet, keep V2 read-only and recover V3.

## Component-specific rollback rules

### PostgreSQL and schema

- Never use `git reset`, destructive database reset, `DROP` of candidate/current schemas, or down-migrations that discard accepted data as incident shortcuts.
- Database schema migrations declare forward/backward application compatibility and rollback mode before cutover. An additive migration may be left in place while the app image rolls back; destructive migration requires a prior expand/migrate/contract sequence and separate recovery proof.
- Service roles remain non-owner/non-superuser during recovery. Temporary migrator access is time-bound, recorded, and revoked.
- Validate current-pointer singleton, publication audit/outbox atomicity, and readback after any canonical or derived pointer recovery.

### API and frontend

- Keep previous immutable API and frontend artifacts plus their OpenAPI/generated DTO/CSP/config hashes.
- Rollback compatibility is tested against both pre-write and post-write database states. The old image cannot be used if it misreads new rows, bypasses authorization, or emits incompatible outbox effects.
- HTML/config is purged/revalidated; content-hashed assets are immutable. Service-worker/cache version rollback must not serve private or mixed-generation responses.
- A map-renderer fallback cannot bypass the renderer-neutral map contribution, trust/privacy, ID, LOD, share/export, or accessibility contracts.

### Identity and private data

- Revoke affected sessions/device/service credentials when authorization correctness is uncertain.
- Provider link/unlink, account/Commander ownership, legacy sync claims, and cross-account access are never reconstructed from names or browser state.
- Private data remains private. A recovery must not promote it to canonical, erase attribution/rights, or make withdrawn contributions eligible.
- Privacy deletion/withdrawal tombstones are reapplied and independently verified after every restore.

### NATS/outbox/jobs

- Pause consumers before changing stream/consumer configuration; capture sequence and pending state.
- PostgreSQL outbox/job/effect receipts decide what to redrive. JetStream sequence alone is not proof of authoritative effect.
- Consumers acknowledge only after durable effect. A poison item is quarantined with ownership; it is not silently skipped.
- Lease fencing prevents old workers from completing after a replacement. Conflicting terminal receipts are an integrity incident.

### Canonical and derived data

- Canonical rollback moves one atomic pointer to a retained valid generation and appends audit/outbox. It does not mutate/rebuild the published generation.
- Derived rollback moves the release pointer to a retained release that still pins its own canonical generation.
- Responses and cache keys expose both canonical generation and derived release identities where combined data is served.
- BG-14 cleanup fails closed. Current and rollback-eligible canonical/derived data, backups, and evidence are retained throughout incident recovery.

## Verification checklist by path

Every completed path records:

- one writable authority and expected routing/DNS/cache state;
- database system identity, timeline/LSN, generation/release pointers, validation/publication evidence;
- accepted-write reconciliation and explicit lost/duplicated/unknown result (unknown cannot close);
- roles/grants/network/secrets/security-header state;
- identity/private/withdrawal/privacy-tombstone invariants;
- outbox/jobs/NATS/effect-receipt reconciliation;
- backup/WAL health and a new recovery point;
- API/frontend/map smoke, generation-aware cache behavior, monitoring/alert freshness;
- incident/user communications and owner approval;
- quarantined evidence and cleanup/disposal decision.

## Recovery decision table

| Condition | Writable authority | Allowed primary response | Prohibited shortcut |
|---|---|---|---|
| Candidate validation fails, no traffic | V2 | Quarantine/fix/revalidate | Edit canonical/evidence to pass |
| Read-only V3 canary fails, proven no writes | V2 | Route reads back; optionally re-enable verified V2 writes | Assume no writes from feature flag alone |
| Frontend/API fault after V3 writes, DB healthy | V3 | Freeze affected path; compatible image rollback or fix-forward | Make V2 writable |
| NATS/consumer failure after writes | V3 | Repair/rebuild transport and redrive PostgreSQL | Treat stream as authority or delete outbox |
| Bad canonical/derived pointer | V3 | Atomic pointer rollback with audit | Mutate published content or mix release/generation |
| Database corruption/operator error | Recovered V3 | Fence; isolated PITR/restore; controlled activation | Restore over failed primary or split brain |
| Security/private-data incident | Frozen/recovered V3 by incident decision | Contain, revoke, preserve evidence, audited fix/restore | Silent cross-account repair or privacy regression |
| V3 unrecoverable after writes | None until approved recovery | Separately designed reverse migration or rebuilt V3 recovery | Generic V3-to-V2 dump/copy |

## V2 retention and retirement

V2 remains read-only for at least 30 successful V3 production days. Its database/checkpoint, application artifact, configuration, access path, and security monitoring remain sufficient for forensic comparison and an approved pre-write fallback, but it receives no new user/background writes.

Retirement requires a new evidence packet covering V3 stability, post-write restores, unresolved disputes/privacy jobs, data retention/legal needs, source/evidence preservation, DNS/cache removal, credential revocation, backup disposal, and the fact that reverse migration is no longer intended. This plan does not authorize retirement.

## Post-incident follow-up

Within the approved incident process, preserve an immutable timeline and produce a blameless review with root cause, contributing controls, affected identities/data, RPO/RTO result, user/legal notifications, gate/runbook/test changes, and owner/due date. Reopening traffic does not close the incident if write reconciliation, privacy impact, or backup recovery remains unknown.
