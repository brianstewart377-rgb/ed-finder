# ED-Finder V3 controlled cutover plan

Status: planning and review only

Review date: 2026-08-26

Authority: V3 guardrails, ADR-001, ADR-002, ADR-012 through ADR-015, ADR-018, ADR-020, ADR-021

## Purpose

Activate the exact validated Phase 4C candidate through a bounded, receipted sequence that preserves V2 as read-only fallback, proves V3 reads before writes, records the point where rollback becomes asymmetric, and stops automatically when identity or integrity is uncertain.

This plan authorizes no server access, deployment, DNS/routing change, write enablement, or cutover. Execution requires every `MUST_PASS_BEFORE_CUTOVER` gate in [V3_PRODUCTION_ACCEPTANCE_GATES.md](V3_PRODUCTION_ACCEPTANCE_GATES.md), the recovery evidence in [V3_BACKUP_RESTORE_PLAN.md](V3_BACKUP_RESTORE_PLAN.md), and the approvals in [V3_PRODUCTION_READINESS_PLAN.md](V3_PRODUCTION_READINESS_PLAN.md).

## Cutover model

There are two rollback regimes:

1. **Before V3 writes:** routing can return to V2 without data translation, provided the V2 system was not mutated and the V3 candidate is frozen for diagnosis.
2. **After V3 writes:** V2 does not contain new account, Commander, session, private, contribution, withdrawal, personal-data, outbox, or audit state. Simple traffic rollback to writable V2 is prohibited. The response is freeze, V3 fix-forward/restore, or an explicitly approved reverse-migration procedure.

The exact boundary is a single append-only `V3_WRITES_ENABLED` marker correlated with UTC time, PostgreSQL timeline/LSN, current generation/derived release, deployed images/config, routing state, backup set, V2 high-water marks, and approval. UI display or feature-flag change alone is not the boundary.

## Required people and controls

The change record names, for the full window:

- Cutover commander and separate scribe/evidence custodian.
- Data/DB operator and backup operator.
- API owner and frontend/map owner.
- Security/identity/privacy owner.
- Async/NATS owner.
- Operations/network owner.
- Product/accountable decision owner.
- Primary and backup incident communications contacts.

One person may cover multiple technical roles only if separation-of-duty approvals remain intact. The builder of the acceptance packet cannot be the sole go/no-go approver. All participants share one UTC timeline and explicit voice/text decision channel. Only the cutover commander calls transitions.

## Inputs to the final change record

- Signed acceptance packet with all mandatory PR gates passed.
- Phase 4C immutable receipt and complete database/generation identity tuple.
- Candidate promotion envelope in `APPROVED_FOR_CUTOVER` state.
- Exact V2 and V3 URLs/origins, target groups, DNS records/TTLs, load-balancer weights, and cache/CDN purge controls.
- API, frontend, NATS, exporter, backup, and configuration image/artifact digests.
- OpenAPI/generated-TypeScript compatibility receipt and security/CSP receipt.
- Current canonical generation ID, optional derived release ID, and known-good rollback identities.
- pgBackRest backup set, protected off-host proof, continuous WAL health, restore receipt, and recovery commands.
- V2 private/sync/high-water snapshot and read-only enforcement method.
- Monitoring dashboard, alert routes, communications templates, status page, and abort/runbook links.
- Step-by-step timings from a representative dry run, including DNS/cache behavior.

Any drift in an identity-bearing input after approval invalidates approval until the acceptance delta is reviewed.

## Abort conditions

Stop the current step, make no further traffic/write transition, preserve evidence, and follow [V3_ROLLBACK_RUNBOOK.md](V3_ROLLBACK_RUNBOOK.md) if any condition occurs:

- Database, generation, source, manifest, validation, backup, image, OpenAPI, generated DTO, or configuration identity mismatch.
- Missing/unknown/stale monitoring, backup/WAL archive failure, or alert route failure.
- Unexpected writer, superuser service, grant drift, public database/NATS exposure, secret leakage, or CSP/auth/privacy control failure.
- Filesystem capacity violates admission, database health is degraded, or restore/rollback point is unavailable.
- Source reconciliation, publication/readback, canonical/derived pairing, outbox, effect receipt, identity/ownership, or private-data invariant fails.
- Smoke error/latency exceeds the approved cutover values, not the placeholder `MEASURE` labels.
- Step exceeds its approved maximum duration or the commander loses a required operator/decision owner.
- V2 write freeze is not effective before the boundary, or V3 receives writes before the recorded enable marker.
- Any participant cannot determine whether user writes were accepted.

An abort is not automatically a rollback. The commander chooses the correct regime based on the durable write marker and database audit evidence.

## Phase 0 — independent rehearsal completion

This workstream waits for Phase 4C to finish independently. It does not poll, alter, restart, or help the running rehearsal.

After the owner declares it finished:

1. Copy the final receipt into the protected evidence intake without editing it.
2. Fill the Phase 4C placeholders: final database size, peak filesystem, runtime, WAL, reconciliation, publish/rollback, and preserved database identity.
3. Verify expected source artifact, baseline, importer, normalizer, PostgreSQL settings, and generation key against the final receipt.
4. Confirm the original `FULL_REHEARSAL_NOT_PRODUCTION` classification remains present.
5. Record all processes with write access, stop rehearsal builders/listeners, and prove the database is quiescent except approved hardening operations.

Exit: PR-01 through PR-05 pass and candidate is `REHEARSAL_PRESERVED`.

## Phase 1 — quarantine, recovery checkpoint, and hardening

1. Isolate the candidate from public traffic and unauthorized networks.
2. Capture database/system/generation identity twice with independent tools.
3. Create the protected pgBackRest full/checkpoint and verify continuous WAL to both approved repositories.
4. Restore the exact checkpoint in isolation, validate it, and record measured RPO/RTO and scratch capacity.
5. Apply only approved production operational changes: roles/grants/default privileges, distinct secrets, TLS/network, backup/WAL, monitoring/exporters, NATS configuration, API/frontend runtime configuration, and OS/container hardening.
6. Do not run importer/normalizer, rewrite canonical rows, change generation manifest, or create a substitute generation.
7. Recompute non-mutating canonical fingerprints/counts, manifest and receipt hashes, current-pointer/audit readback, private/security constraints, and grant inventory. Compare with pre-hardening evidence.
8. Revoke temporary migrator/builder access; prove no unapproved writer or owner membership remains.

Exit: candidate is `CANDIDATE_HARDENED`; canonical content and generation identity are unchanged; hardening changes are fully receipted.

## Phase 2 — full production validation

Run the tests against the hardened, quarantined candidate using production-equivalent images/config and sanitized fixtures:

- database health, constraints, schema migration ledger, privileges, checksums, WAL, backup, restore, capacity, and BG-14 reference safety;
- `/api/v1` OpenAPI/fixture/drift, string-safe IDs, generation-aware reads, no V2 fallback, read-only role enforcement, auth/private write ownership, error/timeout, rate limit, rolling restart, load, and failure tests;
- frontend asset/cache/source-map/config checks, generated DTO use, CSP/CORS/origin/proxy, accessibility, authenticated/private cache isolation, and previous-artifact rollback;
- shared map/Babylon boundary, bounded LOD, renderer-neutral contribution, trust/privacy/share/export, visual/accessibility/non-WebGL checks;
- OAuth/link/unlink/session/revocation/recovery, one-time sync-key claim/quarantine/dispute, account/Commander access, contribution/withdrawal, privacy export/deletion/tombstone replay;
- Frontier OAuth proxy-trust tests proving distinct controlled clients receive
  distinct SlowAPI identities and spoofed `X-Forwarded-For` or
  `CF-Connecting-IP` cannot select one; wildcard forwarded-proxy trust is an
  automatic failure;
- synthetic callbacks on both Frontier paths using unique fake `code` and
  `state` canaries, followed by negative searches across nginx access/error,
  API/Uvicorn/container, retained log-driver, and Sentry/GlitchTip records;
- NATS outage/rebuild, outbox dispatch, consumer dedupe, poison message, job fence, failed effect, publication event, and redrive;
- canonical publication/rollback and, only if in launch scope and authorized, derived release pin/publication/rollback/BG-14 cleanup refusal.

No real user identity, sync key, provider token, session, or private journal data is used for rehearsal evidence.

Exit: candidate is `CANDIDATE_VALIDATED`; every mandatory technical gate has immutable evidence.

## Phase 3 — final go/no-go

At the scheduled checkpoint, the scribe reads the exact candidate hash and mandatory-gate result. Each accountable owner states `GO`, `NO-GO`, or `ABSTAIN` with reason. `ABSTAIN`, missing owner, expired evidence, new critical alert, or identity drift is `NO-GO`.

The signed approval records:

- approved start/end and maximum duration for every phase;
- pre-write and post-write rollback authorities;
- exact smoke traffic percentage/cohort and success/error/latency limits;
- DNS/load-balancer/cache plan and propagation observations;
- write-freeze and V3-write-enable times;
- V2 read-only retention of at least 30 successful V3 days;
- incident and user communication thresholds;
- any post-cutover commitments, all of which must be eligible `CAN_FOLLOW_AFTER_CUTOVER` gates.

Exit: append `APPROVED_FOR_CUTOVER`. No traffic has moved.

## Phase 4 — bind production while dark

1. Deploy/pin the approved V3 database-facing configuration, API, async services, frontend artifact, exporters, and public-edge configuration with no public routing and no production user writes.
2. Confirm every running image/artifact/config hash matches the approval packet.
3. Confirm database/NATS/exporters are private, TLS/origin/CSP/cache rules are active, and service database roles are least privilege.
4. Confirm canonical generation and optional derived release identities from direct SQL and `/api/v1` probes.
5. Validate health/readiness from inside and outside the intended edge, monitoring data freshness, and alert routes.
6. Warm only non-private, generation-partitioned caches with bounded traffic. Do not clone V2 caches or private sessions.

Exit: candidate is `PRODUCTION_BOUND`; externally routable user traffic is still zero; writes disabled.

## Phase 5 — freeze V2 writes and capture boundary

1. Announce the bounded maintenance/read-only transition.
2. Disable V2 mutation endpoints/background writers/importers using the rehearsed control; leave V2 reads available.
3. Drain in-flight V2 writes and queues; prove no service account can continue writing.
4. Capture V2 database identity, transaction/WAL position, account/profile/sync/private high-water marks, queue/outbox state, and UTC time.
5. Reconcile any explicitly migrated V2 identity/private records into V3 by the approved selective migration process; do not wholesale restore V2 into V3.
6. Validate counts/ownership/quarantine and record the final migration receipt.
7. Take/label the cutover-boundary V2 recovery checkpoint and confirm V3 WAL/backup health.

Exit: V2 is durably read-only; V3 remains write-disabled. Failure here returns to V2 before-write regime.

## Phase 6 — read-only V3 traffic

1. Route only the approved canary cohort or percentage to V3; keep all V3 mutations disabled.
2. Test public shell, health, generation, representative system/body/station queries, cache behavior, map render/selection, accessibility fallback, CSP, TLS, and error paths.
3. Compare results with direct candidate queries and approved fixtures; verify string IDs and generation/derived pairing.
4. Observe database pools/queries/locks/WAL, host/container resources, API p95/p99/errors, client/CSP errors, NATS/outbox (expected bounded), and alert freshness for the approved interval.
5. Increase read traffic only through predefined steps. At every step the commander reads the identities and metrics aloud/into the log.

The initial read-only smoke window is planned as 30–60 minutes based on the reviewed DR/cutover evidence; the final approved duration and traffic steps come from the production-equivalent dry run.

Exit: read-only acceptance passes at intended traffic. Before-write rollback remains simple.

## Phase 7 — enable V3 writes

1. Confirm one last time: V2 write freeze, candidate/current generation, backup/WAL, roles, identity/session/privacy controls, NATS/outbox, alert routing, and post-write recovery authority.
2. Append an intent event containing the anticipated write-enable state and pre-enable PostgreSQL LSN.
3. Enable the smallest approved mutation cohort: authentication/session and private/user operations only if all corresponding gates pass. Frontier OAuth remains disabled unless the per-client proxy identity and callback-query log-redaction proofs above are attached. Never enable a partially secured identity surface.
4. In the same coordinated step, append the durable `V3_WRITES_ENABLED` marker/audit event and capture returned transaction/timeline/LSN, UTC time, deployed revisions, routing state, generation/release IDs, and V2 high-water receipt.
5. Perform synthetic controlled writes: create/rotate/revoke a test session, private fact/ownership check, contribution/withdrawal if in scope, outbox delivery/effect receipt, and privacy/audit visibility. Clean up through supported operations and retain audit proof.
6. Reconcile accepted HTTP responses, authoritative rows, outbox/messages, consumer effects, and audit. If acceptance is uncertain, treat the write as committed until database evidence proves otherwise.
7. Expand write traffic only in approved steps with a reconciliation checkpoint between steps.

Exit: V3 is active and the asymmetric rollback regime has begun.

## Phase 8 — stabilization

For the signed intensive-monitoring window:

- freeze nonessential schema, role, feature, dependency, retention, and infrastructure changes;
- maintain named staffed coverage and a single incident timeline;
- watch every mandatory dashboard and reconcile generation/release, write, outbox, privacy, backup, and alert state at each checkpoint;
- run scheduled read/write probes that use synthetic accounts/data and test revocation/withdrawal cleanup;
- confirm protected backups/WAL continue after real writes and perform the planned early PITR verification;
- record actual latency/error/resource baselines and threshold proposals without loosening integrity/security conditions;
- keep V2 online but read-only and protect its cutover checkpoint.

Daily approval records whether stabilization is successful. A successful V3 day requires availability, integrity, recoverability, security/privacy, and no unresolved cutover-severity incident—not merely process uptime.

## Phase 9 — close cutover, retain V2

Close the change only when:

- the stabilization criteria and mandatory checkpoint duration pass;
- all cutover alerts/incidents are resolved or explicitly reclassified without weakening a mandatory gate;
- V3 backups, WAL, off-host copy, and restore evidence cover post-write state;
- current generation/release and rollback candidates remain valid;
- V2 is confirmed read-only, monitored, backed up per its retention decision, and isolated from new writes;
- every command, decision, metric snapshot, identity, routing transition, and communication is in the immutable cutover receipt.

V2 remains read-only for at least 30 successful V3 days. Retirement, destructive cleanup, DNS removal, credentials deletion, or loss of the V2 checkpoint requires a separate plan and approval; it is not part of this cutover.

## Communications

Prepare messages for planned read-only/maintenance, canary start, write enable, success, extended stabilization, abort before writes, incident after writes, and recovery completion. Each message states user impact and next update time without exposing internal hostnames, credentials, private data, or unverified root cause.

The status page and support channel use the same UTC timeline as the technical receipt. Security/privacy incidents follow their restricted notification and legal process; the public update does not substitute for it.

## Evidence packet

The final cutover receipt includes:

- all promotion/candidate events and approvals;
- database/generation/source/validation/backup/config identities before and after every boundary;
- V2 freeze/high-water and V3 write-enable transaction/LSN;
- routing/DNS/cache changes and observed propagation;
- smoke/load/reconciliation/monitoring snapshots with data freshness;
- synthetic write and outbox/effect evidence;
- alerts/incidents/decisions/communications;
- backup/WAL and post-write recovery evidence;
- final ACTIVE state and V2 read-only proof.

Secrets and personal data are redacted, but hashes and generation identifiers that make the receipt auditable remain.
