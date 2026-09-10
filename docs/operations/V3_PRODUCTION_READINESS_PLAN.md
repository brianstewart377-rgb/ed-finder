# ED-Finder V3 production-readiness plan

Status: planning and review only

Review date: 2026-08-26

Applies to: the preserved corrected Phase 4C full-galaxy rehearsal database after that independent run finishes

Authority: `docs/architecture/V3_GUARDRAILS.md`, `docs/architecture/DECISION_STATUS.md`, ADR-001 through ADR-021, and the frozen V3 baseline

## Decision summary

The corrected Phase 4C database may become the V3 production candidate without a ceremonial re-import only if its final immutable receipt passes every cutover-blocking gate in [V3_PRODUCTION_ACCEPTANCE_GATES.md](V3_PRODUCTION_ACCEPTANCE_GATES.md). Promotion is an operational change around a verified database and generation, not a mutation of canonical content.

The historical fact that the build was a `FULL_REHEARSAL_NOT_PRODUCTION` run must remain true. A separate, append-only promotion envelope will refer to that run and record candidate validation, approval, infrastructure binding, and activation. The promotion process must not edit the source artifact, importer, normalizer, frozen baseline, canonical rows, generation manifest, validation receipt, or rehearsal evidence.

No document in this set authorizes implementation, server access, Phase 4C interference, deployment, DNS changes, production writes, schema changes, or cutover.

Companion plans:

- [Acceptance gates](V3_PRODUCTION_ACCEPTANCE_GATES.md)
- [Controlled cutover](V3_CUTOVER_RUNBOOK.md)
- [Rollback and recovery](V3_ROLLBACK_RUNBOOK.md)
- [Backup, PITR, and disaster recovery](V3_BACKUP_RESTORE_PLAN.md)
- [Monitoring and alerting](V3_MONITORING_ALERTING_PLAN.md)
- Machine-readable [gate matrix](../../artifacts/v3/production-readiness/V3_PRODUCTION_GATE_MATRIX.csv)

## Scope, constraints, and evidence rule

This plan was prepared from local repository evidence only. It does not observe either rehearsal host and must not be used as proof that a gate passed. Phase 4C values are deliberately placeholders until the independently produced, immutable full-run receipt is available.

Evidence precedence follows `docs/architecture/DECISION_STATUS.md`. Locked architecture is not evidence of implementation or authorization. A gate passes only with a dated artifact, command transcript, signed approval, immutable receipt, or drill record that directly demonstrates the criterion. A plan, unchecked box, screenshot without identity, or verbal assurance does not pass a gate.

The earlier failed Phase 4C attempt is historical evidence only. Its measurements must not be substituted for the corrected run.

## Phase 4C evidence intake

The readiness review must ingest these corrected-run fields without guessing:

| Field | Required value |
|---|---|
| Final database size | `[PHASE_4C_PENDING: final_database_size_bytes]` |
| Peak filesystem use and minimum free headroom | `[PHASE_4C_PENDING: peak_filesystem_used_pct_and_min_free_bytes]` |
| Total runtime and phase timings | `[PHASE_4C_PENDING: total_runtime_and_phase_timings]` |
| Peak and retained WAL | `[PHASE_4C_PENDING: peak_and_retained_wal_bytes]` |
| Full-source reconciliation | `[PHASE_4C_PENDING: source_reconciliation_receipt]` |
| Publish and rollback validation | `[PHASE_4C_PENDING: publication_rollback_receipt]` |
| Preserved database identity | `[PHASE_4C_PENDING: system_identifier_database_oid_timeline_checkpoint_lsn]` |

The local rehearsal wrapper pins the following expected inputs. They are pre-run expectations, not results, and must match the final receipt byte-for-byte:

- Source artifact SHA-256: `b4944ab5d7537d7e3c370d55bf92a887bebf36e6db0ba1159c072c7cdf9e9868`
- Source artifact bytes: `116027020549`
- Frozen baseline SHA-256: `ee08c17eb3f87f614468db5a038d2f23273ce2b72906226c9aa1f669e724cd2e`
- Importer composite SHA-256: `b5bf4e0c62a75e10bf6e3dfb6dc1934353f09e18afabcddbbb706e8277238d53`
- Normalizer SHA-256: `e9d86fbea1bad3049f2ab9e93e51da9eb1ca681a631ed049dee833d185820f24`
- Expected generation key: `phase4c_full_20260826`
- Expected PostgreSQL major/runtime: PostgreSQL 18 with data checksums, `fsync`, `synchronous_commit`, and `full_page_writes` enabled

A mismatch is a failed identity gate, not an invitation to edit the evidence.

## Promotion model

### Identity bundle

The candidate is identified by the complete tuple below. A generation ID alone is insufficient.

1. PostgreSQL `system_identifier`, server major/minor, data-checksum state, database name and OID, timeline, checkpoint LSN, and control-file timestamp.
2. Canonical generation UUID/key, generation schema, lifecycle state, manifest SHA-256, current-pointer sequence, and the exact publication-audit entry.
3. Source artifact ID, filename, byte length, SHA-256, acquisition/source-rights record, source-run IDs, and generation-input edges.
4. Frozen baseline, importer composite, and normalizer SHA-256 values.
5. Immutable validation-receipt ID, receipt SHA-256, validator version, invariant results, reconciliation counts, rejection/quarantine summary, API readback, and publish/rollback/readback proof.
6. Physical checkpoint: backup set ID, repository, start/stop LSN, WAL archive range, restore verification, and protected storage version/object identifiers.
7. Configuration identity: container image digests, PostgreSQL/NATS/API/frontend configuration revisions, secrets generation identifiers (never secret values), OpenAPI hash, generated TypeScript hash, and security-header hash.

The tuple is serialized using a documented canonical JSON form and hashed. The receipt and its detached approval signatures are stored in the evidence repository and a protected off-host location. At least two independent commands must corroborate database and generation identity immediately before approval and immediately before routing.

### Append-only candidate states

Candidate state belongs in a new operational promotion registry or signed external manifest, not in canonical relations. The frozen baseline is not changed by this review. If a database registry is later chosen, it requires a separately reviewed additive migration.

| State | Meaning | Required transition evidence |
|---|---|---|
| `REHEARSAL_PRESERVED` | Independent Phase 4C has ended and writes are stopped | Final receipt plus database identity |
| `CANDIDATE_QUARANTINED` | Exact preserved database is isolated from public traffic | Network, role, and process isolation proof |
| `CANDIDATE_HARDENED` | Production roles, secrets, backup, monitoring, and runtime configuration are applied without canonical mutation | Change receipts and canonical hash/readback equality |
| `CANDIDATE_VALIDATED` | All technical MUST gates pass against the hardened candidate | Acceptance packet and independent review |
| `APPROVED_FOR_CUTOVER` | Named accountable owners approve a bounded window and rollback boundary | Signed go/no-go record |
| `PRODUCTION_BOUND` | Production infrastructure identity is bound but traffic/writes are not enabled | Images/config/DNS/load-balancer identity receipt |
| `ACTIVE` | Read smoke passes and controlled traffic is enabled | Activation timestamp, routing receipt, smoke evidence |
| `REVOKED` | A failed check or approval withdrawal prevents activation | Append-only reason and incident/change reference |

Every transition appends an event with actor, UTC time, prior-event hash, evidence hashes, and authorization. No state is overwritten. The original `FULL_REHEARSAL_NOT_PRODUCTION` classification remains in the Phase 4C receipt.

### Same database, no ceremonial rebuild

The default path is an in-place data promotion of the preserved PostgreSQL cluster on the intended production host:

1. Stop all builder/importer/normalizer processes after Phase 4C closes and prove no unexpected writers remain.
2. Capture the immutable identity bundle and a pgBackRest full backup plus continuous WAL checkpoint.
3. Place the database behind production-grade network isolation; apply only separately reviewed operational roles, grants, secrets, monitoring, backup, and runtime configuration.
4. Re-run non-mutating validation and compare canonical table fingerprints, manifest hash, counts, and sampled API reads with the Phase 4C receipt.
5. Approve and activate through the controlled cutover plan.

If the intended production host differs, an identity-preserving physical pgBackRest restore is allowed. It is not a re-import, but it must produce a restore receipt and explain the new `system_identifier` or control identity behavior. Logical export/import or rerunning the importer is not an accepted promotion shortcut.

Hardening that would require a new cluster, a canonical rewrite, incompatible DDL, or a new generation invalidates the in-place path and returns the decision to architecture review.

### Approval and separation of duties

Four approvals are required:

- Data/DB owner: generation identity, reconciliation, database health, and recovery point.
- Security/identity owner: roles, network, secrets, CSP, authentication, privacy, and audit controls.
- Operations/release owner: backup restore, monitoring, runbooks, capacity, change window, and routing.
- Product/accountable owner: accepted user impact, V2 read-only period, write-enable boundary, and asymmetric rollback.

The person who builds the acceptance packet cannot be the sole approver. A security or data-integrity exception cannot be accepted as a post-cutover TODO.

## PostgreSQL least-privilege model

### Role design

All roles are `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS` unless a documented PostgreSQL facility requires otherwise. Service logins cannot own schemas or objects. Interactive access is time-bound, individually attributable, and not shared with services.

| Role | Login | Purpose and permitted scope | Explicit exclusions |
|---|---:|---|---|
| `v3_schema_owner` | No | Own database objects, schemas, types, functions, migrations, and default privileges; used only through controlled `SET ROLE` | No network credential; no application use |
| `v3_migrator` | Yes, disabled normally | May `SET ROLE v3_schema_owner` only in an approved migration session | No standing API/import use; no superuser; no role creation |
| `v3_builder` | Yes | Read source/vocab, write build/source ledgers and candidate generation objects, and emit build outbox events under a bounded build procedure | Cannot move current pointers, alter published generations, write private data, or grant roles |
| `v3_api_ro` | Yes | Read current pointer, published canonical generation, allowed vocab/metadata, and curated views | No DDL, source/build writes, private payloads, pointer changes, or unrestricted catalogue reads |
| `v3_api_rw` | Yes | All `v3_api_ro` rights plus narrowly scoped identity/private/session/outbox functions or tables protected by ownership checks/RLS | No canonical/source/build DML, no schema ownership, no `BYPASSRLS` |
| `v3_operator_ro` | Yes, individual membership | Read operational views, promotion/publication metadata, validation receipts, backup status, and non-sensitive statistics | No private facts, credential hashes, provider tokens, DDL, DML, or pointer changes |
| `v3_maintenance` | Yes, disabled normally | `pg_maintain` and bounded maintenance procedures; analyze/vacuum/reindex only during approved windows | No general DML or private reads; no schema ownership |
| `v3_backup_logical` | Yes, disabled normally | Read-all data/settings needed for logical secondary exports and consistency checks | No DML/DDL; not used for physical pgBackRest filesystem access |
| `v3_monitor` | Yes | `pg_monitor` plus execute/select on sanitized health views | No application-table write; no secret or private payload access |
| `v3_security_auditor` | Yes, individual membership | Read redacted security/audit views and role/grant inventory | No session/token digest export; no DML |

The operating-system account used by pgBackRest is separate from database logins, owns only the required repository/spool paths, and receives no interactive application credential. NATS, Redis, API, importer, backup, and monitoring each use distinct credentials.

### Ownership and grants

- Revoke `CREATE` on schema `public` and database-level privileges from `PUBLIC`; revoke default function execution from `PUBLIC`.
- `v3_schema_owner` owns `v3_source`, `v3_vocab`, `v3_identity`, `v3_private`, `v3_meta`, `v3_async`, published generation schemas, types, sequences, and functions. Builders may own temporary/candidate objects only until validation and ownership transfer.
- Grant database `CONNECT`, schema `USAGE`, table/view privileges, sequence privileges, and function `EXECUTE` explicitly. Never use blanket `ALL` for a service role.
- Define `ALTER DEFAULT PRIVILEGES FOR ROLE v3_schema_owner IN SCHEMA ...` separately for tables, sequences, and functions. Builder-created generation objects receive the same reviewed defaults before any service can read them.
- Security-definer functions pin a safe `search_path`, set an explicit owner, validate the caller, and revoke `EXECUTE` from `PUBLIC`.
- Current-generation and derived-release pointer changes occur only through audited, transactionally safe procedures that require a dedicated short-lived release role; neither API role receives this right.
- RLS is defense in depth for account/Commander private records, not a substitute for tested ownership predicates and separate private schemas.
- A pre-cutover grant diff must prove service roles are not members of owner/migrator roles and have no superuser-like built-in roles such as `pg_write_all_data` or `pg_execute_server_program`.

The current repository only wires optional app/import/maintenance/migration DSNs; the frozen V3 baseline contains no production role/grant/default-privilege provisioning. Therefore role implementation and a reproducible privilege audit are cutover blockers.

## Network, host, and secrets posture

Only the public HTTPS ingress is Internet-reachable. PostgreSQL, NATS, Redis, exporters, and administrative endpoints bind to a private container/network namespace or loopback. Host firewall evidence must prove public ingress to PostgreSQL and NATS is denied. Operator access uses a named VPN/SSH tunnel path with MFA, individual keys, and audit logging; it never exposes a database port to the Internet.

If traffic crosses a host or untrusted network, PostgreSQL uses `sslmode=verify-full` with a private CA and NATS uses TLS with server verification plus scoped account/user credentials. Same-host private-container traffic may rely on the documented host boundary only if the threat model and firewall evidence approve it. TLS downgrade or plaintext cross-host fallback fails the security gate.

Secrets are loaded from a dedicated secret manager or root-owned files mounted read-only, not committed files, URLs, shell history, images, browser bundles, metrics labels, or general logs. Each service has a distinct credential. Rotation uses create-new, deploy/verify, revoke-old sequencing; emergency revocation and certificate replacement are rehearsed. Backups are encrypted in transit and at rest with independently recoverable keys. Production credentials cannot delete protected off-host backup history.

## Capacity, storage, and retention

Phase 4C produces the initial measured storage and runtime model. The final capacity packet must include database size by schema/table/index/TOAST, WAL peaks and steady state, temporary space, backup repository growth, restore scratch space, container/image overhead, source artifacts, logs, and concurrent old/new deployment headroom.

The rehearsal wrapper's build admission ceiling is an evidence-backed hard boundary: projected and actual filesystem use must remain at or below 70%, with at least 25% available. Production alerting retains the existing warning at less than 30% free and critical at less than 20% free. A cutover-specific capacity calculation must also reserve space for one failed deployment, WAL/backup lag, maintenance, and the retained V2 read-only system.

BG-14 is coupled to admission and cleanup. A current or rollback-eligible derived release pins its canonical generation. Cleanup must fail closed when references are unknown, prove in one transaction that the generation is not current and not referenced by any retained release, and preserve immediate rollback. The admission formula includes all pinned canonical generations plus derived products, backups, WAL, temporary/reclaim overhead, and the candidate build. Final-size-only estimates do not pass.

Initial retention numbers are provisional until Phase 4C and BG-14 evidence close. The production decision records the approved rollback-generation count/time, cleanup cadence, admission margin, and owner. No referenced generation is deleted to make room for cutover.

## Backup, PITR, and recovery

The mandatory design is detailed in [V3_BACKUP_RESTORE_PLAN.md](V3_BACKUP_RESTORE_PLAN.md). In summary:

- pgBackRest continuous WAL archiving and physical backups are the primary PostgreSQL recovery path.
- Protected off-host storage has a different failure/account boundary, encryption, versioning/object protection, and credentials that production cannot use to delete retained history.
- Logical dumps of critical metadata/private/security/evidence domains are a secondary recovery aid, not a replacement for PITR.
- The 1+ TB rebuildable canonical corpus, high-value private/security records, evidence ledgers, artifacts, configuration, NATS transport, and disposable Redis caches have distinct protection classes.
- A verified full restore of the Phase 4C candidate and point-in-time recovery around the write-enable boundary are cutover blockers.

## Monitoring and alerting

The mandatory signals, provisional thresholds, evidence sources, and ownership are in [V3_MONITORING_ALERTING_PLAN.md](V3_MONITORING_ALERTING_PLAN.md). Before cutover, dashboards and routed test alerts must cover database availability, filesystem headroom, connection exhaustion, locks/long transactions, deadlocks, WAL and archive freshness, backup/restore freshness, autovacuum/index growth, API latency/error/health, NATS/JetStream, outbox and failed effects, import progress, generation/publication state, certificates, container health, and host memory/CPU/I/O.

Unknown numeric thresholds remain marked `MEASURE`; they are not silently invented. A gate closes only after load/rehearsal evidence supplies the value, owner, response, and review date.

## `/api/v1` deployment model

The V3 API is the versioned `/api/v1` contract from ADR-013. Production requires:

- immutable API image digest, SBOM/vulnerability result, startup migration compatibility check, health/readiness probes, graceful drain, bounded connection pools, server-side timeouts, request/body limits, correlation IDs, sanitized errors, structured redacted logs, and metrics;
- separate read-only and write-capable database pools/roles, with V3 canonical GET endpoints using the read-only role;
- generation-aware reads that resolve one current pointer per request/transaction, never concatenate untrusted schema identifiers, and return string-safe IDs plus canonical-generation identity;
- OpenAPI as the source for generated frontend DTOs, fixture compatibility tests, and a zero-diff generation/drift gate;
- load and failure testing against the Phase 4C-size candidate, including station/system query shapes, connection saturation, slow-query cancellation, cache failure, rolling restart, and previous-image rollback;
- explicit CORS/origin policy, trusted-proxy configuration, TLS-only external URLs, rate limiting by endpoint sensitivity, and no admin/service credential in a browser.

The existing V3 router is useful implementation evidence but is not production proof. The acceptance test must demonstrate every intended endpoint from outside the container boundary and prove there is no fallback to V2 rows or an unpublished generation.

## Frontend and map deployment model

Frontend configuration is an immutable, reviewed release input. The release packet records the frontend image/artifact hash, `VITE_API_BASE`, feature flags, OpenAPI hash, generated `api.gen.ts` hash, source-map policy, service-worker version, CSP/security-header hash, cache rules, and compatibility with the deployed API image.

V3 wire DTOs come only from generated OpenAPI types. Handwritten TypeScript may adapt generated DTOs to view models but must not redefine the wire contract. The frontend must reject or visibly handle generation changes during multi-request flows and must not cache private/authenticated responses in shared caches or the service worker.

Static assets use content hashes and immutable caching; HTML and mutable manifests use `no-store` or explicit revalidation. API/private/auth responses use `Cache-Control: no-store` unless a reviewed endpoint-specific policy proves otherwise. Rollback requires the previous frontend artifact and API image to remain compatible with the same database state.

The map must follow `docs/architecture/V3_MAP_INTEGRATION_CONTRACT.md`: one shared map, renderer-neutral typed contributions, Babylon as the V3 adapter, no feature import of Babylon objects, string-safe system IDs, bounded LOD/viewport work, trust-zone/provider cache partitioning, explicit public-share eligibility, and no serialization of the in-memory scene. The old R3F path is a bounded compatibility fallback, not an alternate V3 architecture. Accessibility and non-WebGL behavior are release gates.

CSP must undergo an authenticated V3 review. Script `unsafe-inline` is not accepted unless an owner documents a narrowly bounded legacy exception with hashes/nonces and an expiry; broad security-header weakening is a cutover blocker.

## Identity, authentication, and private data

ADR-012 and the frozen baseline establish account UUIDs, provider identities by exact issuer/subject, Commander identities, membership/access, sessions, device credentials, personal-data requests, service principals, security audit, and claim-only legacy sync keys. Production additionally requires explicit decisions and tests for:

- supported OAuth providers and exact issuer/subject normalization;
- identity link/unlink with recent authentication, nonce, notification, and no automatic account merge;
- opaque server-side sessions stored as digests, idle and absolute expiry, rotation, revocation, session/device inventory, and recovery;
- `__Host-` secure/HTTP-only/SameSite cookies, exact-origin checks on cookie-authenticated mutations, CSRF protection separate from CORS, and trusted forwarded-header/proxy behavior;
- one-time legacy sync-key claims over TLS in a body, never a URL/log/auth bearer; rate limiting, data preview, Commander selection, atomic assignment, ambiguity quarantine, notification, dispute, and disabling the legacy claim path;
- strict separation of private facts, shared contributions, and canonical generations; explicit contribution policy/rights/attribution, receipts, withdrawal, recomputation, and no silent private-to-canonical promotion;
- data inventory, minimization, retention, export, deletion/withdrawal, backup-restoration tombstone replay, audit, breach response, and named privacy/legal decisions.

Identity, authorization, session, privacy, and private/canonical boundary controls are security/data-integrity gates and cannot be deferred past public writes.

## Async, outbox, NATS, and failure handling

PostgreSQL is authoritative. NATS JetStream transports work; Redis is disposable cache/coordination only. An API or database transaction that changes authoritative state writes an outbox message in the same transaction. A dispatcher publishes with stable message IDs and records success. Consumers are at-least-once, idempotent, and acknowledge only after the authoritative effect or immutable effect receipt is durable.

Production readiness requires stream/consumer configuration as code, scoped NATS credentials, retention sized from measured outage/replay behavior, max-delivery and dead-letter handling, replay and redrive procedures, poison-message quarantine, trace/correlation propagation, outbox-age and failed-effect metrics, and proof that total NATS loss can be rebuilt/re-driven from PostgreSQL. PostgreSQL job/lease/fencing records remain the durable authority; in-memory queues and Redis cannot own lifecycle state.

Generation publication and derived-release publication are separate atomic pointers. A derived release pins exactly one canonical generation; responses and cache keys carry both identities. No derived implementation is authorized merely by this plan.

## Required operational runbooks

Before cutover, the named owner and backup owner must execute or tabletop each runbook and attach a receipt:

1. Candidate identity capture and validation.
2. Production role/grant provisioning and privilege audit.
3. Secret/certificate rotation and emergency revocation.
4. pgBackRest backup, PITR, off-host restore, and restore verification.
5. Filesystem/WAL pressure and failed archive recovery.
6. PostgreSQL connection exhaustion, lock/deadlock, long transaction, and slow query.
7. Import/build resume or abandonment without touching a published generation.
8. Canonical generation publication and rollback.
9. Derived release publication/rollback and BG-14-safe cleanup, if derived data is in launch scope.
10. API/frontend rolling deployment, health failure, and previous-image rollback.
11. NATS outage, consumer poison message, outbox backlog, idempotent redrive, and failed effect.
12. OAuth/provider outage, session revocation, sync-claim dispute, account recovery, privacy export/deletion, and contribution withdrawal.
13. Controlled cutover, write-enable, freeze, fix-forward, and asymmetric recovery.
14. Incident declaration, communications, evidence preservation, and post-incident review.

Runbook commands must identify the environment, database identity, generation/release IDs, expected output, abort condition, and rollback. Commands copied from V2 without V3 identity protections do not pass.

## Decision sequence

1. Wait for independent Phase 4C completion; do not poll or intervene from this workstream.
2. Intake and independently validate its immutable receipt and placeholders.
3. Freeze the preserved candidate and capture the promotion identity bundle.
4. Establish protected backup/PITR and prove restore before hardening.
5. Apply separately reviewed production-only roles, network, secrets, backup, monitoring, and runtime configuration.
6. Revalidate canonical equality and complete API/frontend/identity/async/security tests.
7. Close every `MUST_PASS_BEFORE_CUTOVER` gate and assemble signed approvals.
8. Execute [V3_CUTOVER_RUNBOOK.md](V3_CUTOVER_RUNBOOK.md).
9. If any abort condition fires, execute [V3_ROLLBACK_RUNBOOK.md](V3_ROLLBACK_RUNBOOK.md).
10. Keep V2 read-only for at least 30 successful V3 days, then require a separate retirement approval.

## Explicit non-authorization

This planning packet does not authorize server access, changes to the running corrected rehearsal, importer/normalizer/baseline changes, production role creation, schema migration, backup execution, deployment, traffic routing, user migration, write enablement, cutover, rollback, or V2 retirement.
