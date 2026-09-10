# ED-Finder V3 monitoring and alerting plan

Status: planning and review only

Review date: 2026-08-26

Authority: V3 guardrails, ADR-002, ADR-010, ADR-014, ADR-015, ADR-020, ADR-021, Phase 4C wrapper limits, and existing incident-backed operational thresholds

## Objective

Detect loss of availability, capacity, recoverability, integrity, security, or progress early enough for an accountable operator to act. Monitoring evidence is a cutover gate: dashboards without routed alerts and alerts without a tested runbook do not count.

This plan complements [the readiness plan](V3_PRODUCTION_READINESS_PLAN.md), [backup/DR plan](V3_BACKUP_RESTORE_PLAN.md), and [acceptance gates](V3_PRODUCTION_ACCEPTANCE_GATES.md). It does not authorize deployment or production monitoring changes.

## Threshold policy

Thresholds in this document have one of three statuses:

- `EVIDENCE-BACKED`: already present in the repository, incident evidence, Phase 4C wrapper, or reviewed DR plan.
- `DERIVED`: calculated from an approved capacity/RPO/RTO/SLO, not a free-standing invented number.
- `MEASURE`: no defensible number exists yet. Phase 4C, load tests, restore drills, or an owner decision must supply it before the related gate passes.

An unknown value is never converted into a convenient round number. For every `MEASURE` row, the acceptance packet records measurement window, percentile/baseline, proposed warning/critical value, failure budget, owner, review date, and runbook. Security and integrity signals can be immediate conditions without a numeric performance threshold.

## Alert contract

Every alert has: stable name, environment, severity, signal query, duration/debounce, labels that omit secrets/private values, dashboard link, runbook link, primary and backup owner, tested route, silence/maintenance rules, and resolution evidence. Alerts distinguish `no data` from healthy zero. The monitoring path must not depend only on the component it monitors.

Severities:

- `PAGE`: immediate threat to correctness, security, recoverability, or active service.
- `URGENT`: action within the staffed operating window before risk reaches the page boundary.
- `TICKET`: bounded follow-up with an owner and due date.

Security, data-integrity, backup/PITR, and unknown-state failures do not become optional because traffic is low.

## Mandatory signal matrix

### PostgreSQL, storage, and host

| Signal | Warning/urgent condition | Page condition | Status and evidence | Required response |
|---|---|---|---|---|
| PostgreSQL exporter/SQL probe availability | Partial replica/secondary signal loss | Target or direct SQL probe down for 2 minutes | `EVIDENCE-BACKED`: existing `MonitoringTargetDown` rule | Confirm host/container/network/database; prevent blind writes; use database-availability runbook |
| Filesystem free space | Less than 30% free for 5 minutes | Less than 20% free for 5 minutes | `EVIDENCE-BACKED`: current Prometheus rules; 95% incident confirms harm | Stop optional builds/maintenance; inspect WAL/backups/index/temp growth; expand or safely reclaim |
| Build/cutover capacity admission | Projected or actual use above 70%, or available space below 25% | Work proceeds after admission failure | `EVIDENCE-BACKED`: corrected Phase 4C wrapper | Refuse start or pause at safe checkpoint; do not delete retained generation/backup to force admission |
| Filesystem time-to-full | `MEASURE` from growth rate and approved response time | Forecast crosses critical free-space boundary before operator can recover | `DERIVED` from measured growth and runbook duration | Identify growth source; protect WAL/PITR; stop bounded writers |
| Connection utilization | Pool wait/timeout or sustained utilization threshold `[MEASURE]` | Remaining slots reach configured administrative reserve, or API/import cannot acquire a connection | `DERIVED` from `max_connections`, reserved slots, pools; warning needs load evidence | Shed load, stop nonessential builder/maintenance, inspect leaks/long transactions; preserve admin access |
| Pool saturation | Queue/wait p95 `[MEASURE]` | Pool acquisition failures or unbounded queue | `MEASURE` in Phase 4C-size API/load test | Scale/tune only within database capacity; find N+1/slow query before increasing limits |
| Long transactions | Age threshold `[MEASURE]` by workload class | Transaction blocks publication/migration, threatens WAL retention/cleanup, or exceeds approved cutover step deadline | `MEASURE`; publication deadline derived from drill | Identify owner/query, capture evidence, cancel only per runbook |
| Lock waits/blockers | Wait threshold `[MEASURE]`; any unexpected DDL lock is urgent | Blocked current-pointer/write-enable operation reaches step abort deadline | `MEASURE` plus controlled-cutover timeout | Freeze step, capture lock graph, abort safely; never retry pointer mutation blindly |
| Deadlocks | Any deadlock is urgent and investigated | Repeating deadlock or one affecting identity/private/publication correctness | Integrity condition; numeric rate not invented | Preserve graph/log context, stop risky writer, open incident/defect |
| Slow queries | Per-route/query p95/p99 and timeout `[MEASURE]` | Query cancellations/error budget threaten availability or cutover smoke | `MEASURE` from full-size load test; API statement timeout is configuration evidence, not an SLO | Capture normalized query ID/plan safely; bound/cancel; avoid logging parameters |
| Checkpoints/write pressure | Baseline variance `[MEASURE]` | Checkpoint/WAL pressure causes sustained API/import failure or threatens disk | `MEASURE` during Phase 4C and load | Stop optional writers; inspect checkpoint, storage latency, WAL settings |
| WAL archive freshness | Trend at `[MEASURE]` below page | Last archived WAL older than 10 minutes | `EVIDENCE-BACKED`: reviewed DR plan | Protect `pg_wal` space, repair archive, prove continuity before resuming risky work |
| Retained `pg_wal`/slots | Growth threshold `[MEASURE]`; Phase 4C build hard ceiling 128 GiB | Space critical, archive gap, or slot retention threatens filesystem | Phase 4C ceiling is build-only evidence; steady threshold `MEASURE` | Identify archive/slot/replica cause; never delete WAL manually |
| Autovacuum health | Oldest transaction, freeze age, missed/analyze lag `[MEASURE]` | Wraparound risk or blocked maintenance within derived deadline | `MEASURE`; mutable identity/private/async domains remain in scope | Stop offending transaction; run controlled maintenance; verify settings/table coverage |
| Table/index/TOAST growth | Weekly trend anomaly `[MEASURE]` | Growth defeats storage admission or evidence shows runaway bloat | Incident evidence supports monitoring; exact per-object values `MEASURE` | Attribute to schema/generation/job; use BG-14-safe cleanup and reviewed maintenance only |
| Host memory | Sustained threshold `[MEASURE]` | Phase 4C/candidate work exceeds 75% host/PG/worker ceiling or OOM occurs | 75% `EVIDENCE-BACKED` for rehearsal/build; steady production `MEASURE` | Stop optional workers, preserve DB, capture OOM/container evidence |
| Swap | Any sustained use `[MEASURE]` | Phase 4C/candidate swap reaches 1 GiB ceiling or latency threatens service | 1 GiB `EVIDENCE-BACKED` for build | Reduce concurrency; investigate memory; do not normalize swapping |
| CPU/load/storage latency | Baseline anomaly `[MEASURE]` | API/DB availability or recovery objective breached | `MEASURE` under representative load/restore | Attribute by container/query/I/O; shed optional load |
| Host clock | Drift threshold from identity/TLS design `[MEASURE]` | TLS/session/audit ordering invalid or NTP unsynchronized | Security dependency; value must come from host design | Restore time sync; halt security-sensitive transitions if audit time unreliable |

### Backups and disaster recovery

| Signal | Page condition | Status | Runbook result |
|---|---|---|---|
| WAL archive | Last successful archive older than 10 minutes; archive continuity failure | `EVIDENCE-BACKED` | Repair and verify contiguous recoverable range |
| Incremental backup | Latest successful incremental older than 8 hours | `EVIDENCE-BACKED` | Produce/verify new backup without expiring good chain |
| Differential backup | Latest successful differential older than 26 hours | `EVIDENCE-BACKED` | Repair schedule/repository; verify chain |
| Full backup | Latest successful full older than 8 days | `EVIDENCE-BACKED` | Produce full and verify repository |
| Critical logical export | Latest accepted export older than 26 hours | `EVIDENCE-BACKED` | Re-run encrypted export and verification |
| Off-host delivery | Any silent local-only success or protected repo unavailable beyond `[MEASURE]` urgent window | Security/recoverability condition; duration `MEASURE` from RPO | Restore protected archive path and prove no WAL gap |
| Restore receipt freshness | No isolated restore within 35 days | `EVIDENCE-BACKED` | Complete isolated off-host restore and application verification |
| Clean-host drill freshness | No clean-host recovery within 100 days | `EVIDENCE-BACKED` | Execute clean-host recovery and record RPO/RTO |
| Backup repository capacity | Forecast cannot retain approved chains/WAL; free threshold `[MEASURE]` | `DERIVED/MEASURE` from retention/capacity model | Add capacity or approved retention change; never delete last good chain |
| Backup integrity/access | Checksum/catalogue/encryption/key test fails | Immediate recoverability failure | Stop expiration, preserve evidence, repair and re-verify |

### API, frontend, and public edge

| Signal | Warning/urgent condition | Page condition | Status | Required dimensions |
|---|---|---|---|---|
| API readiness/health | Instance unavailable during rollout | Public health/representative read fails for 2 minutes or healthy capacity below safe rollout minimum | 2-minute target-down is `EVIDENCE-BACKED`; capacity minimum `MEASURE` | Route, status, image digest, instance, generation ID |
| API latency | Per-route p50/p95/p99 thresholds `[MEASURE]` | Approved SLO/error budget breach or widespread timeout | `MEASURE` against Phase 4C-size DB | Separate endpoint/query/cache-hit status; no IDs/private terms in labels |
| API error rate | 4xx baseline and 5xx rate `[MEASURE]` | Error-budget breach; authentication/authorization/canonical-generation errors may page immediately | `MEASURE`, with security/integrity conditions explicit | Status family, route template, exception class, generation, deploy revision |
| Generation mismatch | Any response/cache combines incompatible canonical/derived IDs | Immediate integrity page | Locked architecture invariant | Capture request trace and IDs; stop affected feature/traffic |
| V2 fallback | Any `/api/v1` result sourced from V2 or unpublished generation | Immediate integrity page | ADR-001/013 | Disable route/deploy; preserve evidence |
| Frontend asset/error telemetry | Asset load/client error trend `[MEASURE]` | Shell unusable or auth/private data exposed | `MEASURE` plus security condition | Frontend artifact, browser class, CSP violation, API revision; redact URLs/query |
| CSP violations | Baseline `[MEASURE]` for expected extensions/noise | Policy bypass, injected script, or credential/private data signal | Security condition | Report-only trial then enforced policy; preserve sanitized samples |
| TLS certificate expiry | Warning/page windows `[MEASURE]` from certificate renewal lead time and on-call coverage | Expired/untrusted certificate or renewal cannot finish before expiry | Must be derived; no arbitrary 30/14/7 values in this plan | Hostname, issuer, expiry, chain, renewal job; never private key |
| DNS/load-balancer | Probe variance `[MEASURE]` | Wrong origin/host, split routing, or loss of safe capacity | `MEASURE` during cutover drill | External and internal probes; target/image/config identity |

### NATS, jobs, and outbox

| Signal | Warning/urgent condition | Page condition | Status and rationale |
|---|---|---|---|
| NATS/JetStream availability | Node/stream/consumer unavailable; duration `[MEASURE]` | Total transport loss threatens approved delivery/recovery objective | Availability duration `MEASURE`; NATS is not authority |
| Stream storage/retention | Bytes/messages/age near configured limit `[DERIVED]` | Messages expire before PostgreSQL redrive/recovery can complete | Derived from measured outage/redrive and Class F RTO |
| Consumer lag | Oldest pending/ack age `[MEASURE]` by consumer | Lag exceeds approved effect-delivery objective or blocks cutover reconciliation | Must be measured under replay/load |
| Redeliveries | Baseline/rate `[MEASURE]` | Max-delivery/poison message reached without quarantine | Correctness condition; rate threshold measured |
| Outbox oldest unpublished | Age/count `[MEASURE]` by event class | Backlog threatens class RPO/RTO, publication visibility, or write-enable reconciliation | PostgreSQL authoritative; limit tied to accepted SLO |
| Dispatcher failures | Repeated rate `[MEASURE]` | No dispatcher progress or publication event cannot be delivered in cutover deadline | Cutover deadline derived from drill |
| Failed effects/dead letters | Any new unresolved item is urgent | Security/private/publication effect fails, or item is dropped/unowned | Immediate ownership condition |
| Effect-receipt conflicts | Any stable message ID maps to a different effect/payload hash | Immediate integrity page | Idempotency invariant |
| Durable job lease/fence | Stale lease/heartbeat `[MEASURE]` | Two owners pass fence or terminal receipt conflicts | Fence violation is immediate integrity page |

### Imports, generations, publication, and retention

| Signal | Warning/urgent condition | Page/abort condition | Status |
|---|---|---|---|
| Import/build progress | No progress for `[MEASURE]`; parser/writer queue imbalance `[MEASURE]` | Safety ceiling exceeded, receipt conflict, source mismatch, or unbounded failures | Phase 4C supplies throughput/stall evidence; ceilings evidence-backed |
| Rejections/quarantine | Rate and reason mix deviate `[MEASURE]` | Rights/provenance failure, unbounded loss, or reconciliation cannot close | Numeric threshold `MEASURE`; provenance failure immediate |
| Source reconciliation | Count/hash mismatch | Any unexplained mismatch blocks publication | Deterministic data-integrity gate |
| Generation lifecycle | Candidate stuck duration `[MEASURE]` | Invalid transition, multiple current pointers, or published generation not READY/validated | Lifecycle timing measured; invariant immediate |
| Publication transaction | Duration `[MEASURE]` | Pointer/audit/outbox not atomic, readback mismatch, or step exceeds cutover abort deadline | Atomicity invariant; time from rehearsal |
| Rollback eligibility | Retained count/headroom trend `[MEASURE]` | No known-good rollback generation or its evidence/backup is unavailable | Cutover blocker |
| Derived release/canonical pin | Reference count/storage trend `[MEASURE]` | Current/rollback release points to missing canonical generation or cleanup proceeds on unknown reference | BG-14 invariant |
| Cleanup/reclaim | Duration/catalogue/lock impact `[MEASURE]` | Current/rollback-eligible generation selected, reference proof races, or service harmed | BG-14 evidence required before automation |

### Security, privacy, and audit

Monitor authentication failures, provider/OAuth errors, identity link/unlink, sync-key claim attempts/outcomes, session creation/rotation/revocation, recent-auth failures, privilege/role changes, secret/certificate rotation, operator/migrator access, contribution/withdrawal, privacy export/deletion jobs, audit-pipeline health, and anomalous private-data access.

Numeric anomaly thresholds are `MEASURE` from a privacy-safe baseline. The following conditions page immediately: service role becomes superuser/owner, unauthorized grant/default privilege drift, audit pipeline stops, raw sync key/provider token/session secret appears in telemetry, cross-account private access, unauthorized private-to-canonical copy, withdrawal/deletion state regresses after restore, or production backup protection is weakened.

Logs and metrics use route templates and opaque internal correlation IDs. They do not include passwords, DSNs, OAuth codes/state, provider tokens, raw sync keys, cookie/session values, private facts, Commander names, full query parameters, or SQL bind values. Access to security/audit views is itself audited.

## Dashboards

At minimum, ship and validate these operator views:

1. **Production overview:** public health, API latency/errors, instances, deployed digests, current canonical generation/derived release, active alerts.
2. **PostgreSQL:** availability, sessions/pools, locks/transactions, query IDs, deadlocks, checkpoints/WAL/archive, autovacuum, growth, storage latency.
3. **Capacity and retention:** filesystem, database/table/index/TOAST, WAL/temp, backup repositories, pinned generations/releases, BG-14 admission forecast.
4. **Backup and DR:** last successful backup by type/repository, WAL freshness/continuity, restore/drill receipts, RPO/RTO history.
5. **Async:** NATS nodes/streams/consumers, outbox oldest/count, redeliveries, failed effects, job leases/fences, redrive progress.
6. **Imports and publication:** source/build phase progress, throughput, rejections, reconciliation, validation, pointer history, rollback eligibility.
7. **Security/privacy:** sanitized authentication/session/claim/role/audit/privacy-job health with restricted access.
8. **Host/containers/edge:** CPU, memory, swap, disk/I/O, restarts/OOM, certificate, DNS/load-balancer, exporter health.

Each dashboard exposes data freshness and an explicit `unknown` state. A green panel based on stale data fails acceptance.

## Test and acceptance procedure

Before cutover, the owner performs controlled synthetic tests without using real private data:

- stop or block a non-production probe target and verify the 2-minute route;
- exercise warning/critical disk rules with synthetic metrics or rule tests;
- simulate connection reserve, lock, deadlock fixture, slow query, WAL archive failure, and backup-age conditions in an isolated environment;
- fail one API instance, serve a bad readiness response, test error/latency rules, and validate rollback visibility;
- interrupt NATS/dispatcher/consumer, create a poison message, replay outbox, and prove effect deduplication;
- create failed generation/publication/rollback fixtures and verify invariant alerts;
- test certificate-expiry rules with a fixture certificate;
- verify an audit/privilege-drift event and that sensitive fixture values are redacted;
- record delivery time, acknowledgement, escalation, runbook outcome, and final cleanup.

The release packet contains rule-test results, dashboard screenshots with environment/time/data freshness, notification receipts, and owner sign-off. Real credentials or personal data are never inserted to make a monitoring screenshot persuasive.

## Ownership

- Operations/SRE owns alert delivery, host/container/edge, capacity, dashboards, and response process.
- Data/DB owns database, WAL, queries, generation/publication, and BG-14 interpretation.
- DR owner owns backup/restore signals and drills.
- API/frontend owners own route/client signals and deploy correlations.
- Async/platform owner owns NATS/outbox/job signals.
- Security/identity/privacy owners own restricted telemetry, redaction, and incident conditions.

Every page has a primary and backup. An alert with no staffed route or actionable runbook blocks cutover.

## Post-cutover tuning

During the stabilization window, record actual baselines and adjust only through reviewed changes. A threshold change includes before/after data and cannot silence a security, data-integrity, backup, or no-data condition. Advanced forecasting, longer-trend dashboards, and automatic capacity tickets may follow cutover; mandatory signal coverage and paging may not.
