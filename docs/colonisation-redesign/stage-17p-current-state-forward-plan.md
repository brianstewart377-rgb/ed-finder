# Stage 17P — Current State / Forward Plan Baseline

Stage 17P is a documentation-control stage. It does not implement app behaviour, change backend mechanics, alter scoring, change CP formulas, add ingestion, change persistence, or redesign the Colony Planner UI.

## Purpose

The colonisation roadmap has grown through many implementation and recovery stages. Older documents are still valuable, but several of their "next stage" recommendations are now historical because later work has already landed.

This document is the current planning baseline for future Colony Planner, colonisation intelligence, trust, slot, enrichment, and Raven-style planner work.

Future implementation prompts should read this file first, then inspect the specific historical stage document only when it is relevant evidence for the work being planned.

## Current Baseline

The project has moved beyond the original Stage 17A sequence of:

1. trust/rationale fixes,
2. surface slot prediction,
3. structure picker expansion,
4. validity hardening,
5. visual planner feasibility,
6. durable persistence feasibility,
7. ingestion feasibility.

That sequence remains useful as historical intent, but it has been partly superseded by later merged work.

Current merged direction, based on the latest roadmap trail:

- Stage 16E/16F/16G added inferred, declared, and declared-vs-observed role review concepts while keeping roles advisory and non-mechanical.
- Stage 17B rescued Suggested Builds error handling and usefulness filtering.
- Stage 17G introduced canonical validated slot prediction and a whole-system slot/economy planning map.
- Stage 17M moved the dedicated planner toward a two-region Raven-style canvas plus telemetry/context model.
- Stage 17N tightened the docked telemetry/context region and read-only projection comparison.
- Stage 17N.1 repaired and refined Raven canvas add flows, picker compatibility, lane handling, prerequisite warnings, and canvas clarity.
- Stage 17N.2c recovered trust around unknown coordinates, unknown distances, stale/saturated ratings, and legacy rationale language.
- Stage 17N.2d/17N.2d-H moved existing-infrastructure awareness and station/body association toward backend-backed trust metadata.
- Stage 17N.2d-P and the enrichment roadmap introduced a safer offline/staging warehouse direction for repeatable enrichment evidence and report-only reconciliation.
- Stage 18J-Q8 keeps the first production-scale reconciliation review offline
  and compact: large artifacts must be summarized before Stage 18J-P can
  proceed, and production summaries remain non-git by default.

## Read-Order For Future Work

Use this order before starting new colonisation work:

1. `docs/colonisation-redesign/README.md`
2. This file.
3. `docs/colonisation-redesign/engine-roadmap.md` for broad engine history and delivered stage summaries.
4. `docs/colonisation-redesign/enrichment-roadmap.md` for station/body/ring enrichment, warehouse, and operator-roadmap work.
5. Specific stage docs only when they directly apply to the task.
6. For mechanics-heavy or source-sensitive work, read `docs/reference/colonisation/README.md`, `docs/reference/colonisation/source-priority.md`, and `docs/reference/colonisation/source-inventory.md`.

If this file conflicts with an older "recommended next stage" section, treat this file as newer planning control unless the older doc is being used only for historical context.

## Source Authority Rule

The source-pack issue from Stage 17A remains important, but Stage 17Q now adds
the committed reference entry point:

- `docs/reference/colonisation/README.md`
- `docs/reference/colonisation/source-priority.md`
- `docs/reference/colonisation/source-inventory.md`
- `docs/reference/colonisation/codex-reference-prompt-snippet.md`

The committed path records the source hierarchy, conflict rules, and inventory
placeholders. It does not commit restricted guide files, spreadsheets, PDFs,
screenshots, or third-party assets unless their redistribution status is
explicitly safe.

Future mechanics-heavy implementation prompts must read the committed reference
docs first, then explicitly state whether direct source verification used
committed docs, attached files, external sources, or local/operator-only files.
Do not claim direct source verification from files that are not committed or
attached.

## Non-Negotiable Product Boundaries

These boundaries continue to apply unless a future stage explicitly changes them:

- No automatic Simulation Preview execution.
- No automatic Suggested Build generation.
- No automatic Suggested Build loading.
- No silent Build Plan mutation from imported, observed, projected, or inferred data.
- No hidden scoring, CP, economy, service, buildability, or optimiser-ranking changes.
- No role-aware optimiser scoring/ranking without a dedicated scope.
- No primary-port truth invented from user intent.
- No Architect Slot Survey truth unless backed by an explicit evidence/import workflow.
- No RavenColonial visual clone, asset copy, API mutation, or logistics clone.
- Existing infrastructure is not a Build Plan placement.
- Projected Suggested Build structures are ghost/projection-only until explicitly loaded.
- Unknown data must stay unknown; do not coerce missing coordinates, distances, slot counts, rings, or body associations to zero/false.

## Current Information Model

The planner should keep these concepts visibly separated:

| Source | Meaning | Mutates Build Plan? | Trust handling |
|---|---|---:|---|
| Existing | Infrastructure already present in system/station data | No | Confirmed, inferred/verify, or unresolved based on backend association metadata. |
| Planned | User Build Plan placements | Yes | Local project/user plan state. |
| Projected | Selected Suggested Build ghost placements | No | Read-only comparison until explicitly loaded. |
| Observed Evidence | Manual/imported evidence records | No by default | Used for review/validation; does not mutate mechanics. |
| Inferred Planning Signals | ED-Finder advisory hints from topology/plan shape | No | Conservative guidance only. |
| Declared Strategy | User-declared body roles | No mechanics mutation | Local project intent, not game truth. |
| Unknown/Unresolved | Missing/ambiguous data | No | Display compactly and conservatively. |

## Recommended Next Work Queue

### Stage 17Q — Source Pack Commit / Source Authority Lock

Purpose: make the mechanics/source hierarchy available in-repo so future mechanics-heavy work has a committed reference baseline.

Scope:

- Add `docs/reference/colonisation/README.md`.
- Add `docs/reference/colonisation/source-priority.md`.
- Add the future implementation prompt snippet.
- Add permitted source references, inventories, or placeholders.
- Document licensing/redistribution limits where source files cannot be committed.

Non-goals:

- No app behaviour changes.
- No mechanics changes.
- No scoring changes.

Acceptance:

- Future Codex/AI prompts can start from committed source-priority docs.
- The repo no longer points only at a local ZIP path for the reference pack.

### Stage 17R — Planner Trust Audit

Purpose: verify the current Raven-style planner and trust-recovery work behaves honestly on real awkward systems before adding more intelligence.

Scope:

- Audit current Raven canvas behaviour against systems with known existing stations, predicted slots, unresolved associations, and projected Suggested Builds.
- Remove any temporary slot/debug console logs.
- Confirm unknown coordinates/distances never render as real zero values.
- Confirm stale/saturated rating caveats and legacy-rationale safety copy are still present where needed.
- Confirm predicted slots never appear as known/confirmed slots.
- Confirm existing infrastructure never silently becomes planned infrastructure.
- Add focused regression tests around representative awkward systems/fixtures.

Non-goals:

- No new planner features.
- No scoring changes.
- No automatic preview/generation/load.

Acceptance:

- Trust language is consistent between result cards, system detail, planner canvas, and telemetry.
- Ambiguous station/body/lane associations render as unresolved or verify, not confirmed.
- Capacity calculations clearly separate predicted, existing, planned, projected, and unknown states.

### Stage 17S — Existing Infrastructure UX Hardening

Purpose: make existing infrastructure and occupied-slot reasoning understandable to the user.

Scope:

- Improve display for confirmed existing, inferred/verify existing, unresolved, and unknown-lane infrastructure.
- Add compact explanations/tooltips for association source and confidence.
- Make capacity math visible per lane: predicted slots, existing occupied, planned occupied, projected occupied, remaining, unknown/unresolved.
- Ensure disabled add controls explain the exact reason.

Non-goals:

- No Build Plan mutation from existing infrastructure.
- No canonical write path.
- No new enrichment ingestion.

Acceptance:

- A user can tell why a slot is unavailable.
- A user can tell whether ED-Finder knows, infers, or cannot resolve an existing station's body/lane.

### Stage 17T — Suggested Builds Strategy Advisor V1

Purpose: make Suggested Builds more strategically useful using the planner context already available.

Scope:

- Improve candidate explanation around body choice, existing infrastructure, slot pressure, economy intent, sparse-data warnings, and declared roles.
- Keep deterministic candidate families such as main station candidate, industrial/refinery starter, extraction support, tourism/agriculture, security/military, balanced expansion, and support-body plan.
- Use Raven canvas projection to make candidate impact clearer.
- Keep load explicit and preview explicit.

Non-goals:

- No LLM planning.
- No automatic generation/load/preview.
- No hidden optimiser-ranking mechanics change unless separately scoped.

Acceptance:

- Suggested Builds explain why they exist and what tradeoff they are making.
- Trivial candidates stay filtered.
- Projected structures remain ghost-only until explicit load.

### Stage 17U — Role + Strategy Integration

Purpose: connect declared/inferred/observed role work to Suggested Builds and planner guidance without making roles mechanics truth.

Scope:

- Show which declared roles a candidate supports or conflicts with.
- Surface role gaps such as declared Industrial Core with no industrial placement, Main Station Body with no station/port, or observed Tourism Focus conflicting with declared Industrial Core.
- Keep source labels visible: inferred, declared, observed.

Non-goals:

- No role-aware optimiser ranking.
- No role-driven Simulation Preview mechanics.
- No automatic declared-role assignment from Suggested Builds.

Acceptance:

- Roles improve guidance and review.
- Roles still do not change CP, economy, service, scoring, optimiser ranking, or validation semantics.

### Stage 18A — Enrichment Operator Dashboard / Status Integration

Purpose: make enrichment status observable without SSH/log spelunking.

Scope:

- Surface `station_enrichment_status.py --json` in an operator/admin dashboard.
- Display latest run, checkpoint progress, fetch/rate-limit failures, safety-gate failures, and batch status.
- Keep the dashboard read-only.

Non-goals:

- No production writes from dashboard.
- No live API crawling from dashboard.

Acceptance:

- Operator can inspect progress and failures through ED-Finder UI/admin tooling.
- Status is read-only and safe.

### Stage 18B — Warehouse Reconciliation Hardening

Purpose: mature the offline enrichment warehouse path before any canonical writes are considered.

Scope:

- Broaden read-only reconciliation across staged station, body, and ring evidence.
- Improve confidence/risk explanations.
- Improve source coverage summaries, colonisation signals, and mission-density signals.
- Keep output report-only.

Non-goals:

- No canonical station/body/system writes.
- No production live API crawl.
- No scoring changes.

Acceptance:

- Warehouse reports are boring, deterministic, and explainable.
- Any future canonical write path can be designed from stable report evidence rather than live API behaviour.

### Stage 18C — Warehouse Runbook + Operator Workflow

Purpose: make the warehouse safe and repeatable to run.

Runbook: `docs/operations/enrichment-warehouse-runbook.md`.

Scope:

- Document where snapshots come from, where they are stored, how they are loaded, and how dry-run reconciliation is run.
- Define what a good run looks like, which warnings block progress, and what should never write canonical data.
- Provide operator commands for fixture, staging, and production-read-only dry-runs.

Non-goals:

- No canonical writes.
- No production scheduler/job wiring unless separately scoped.

Acceptance:

- A future operator can run the warehouse path without guessing which script or flags to use.
- Dry-run/report-only behaviour remains the default.

### Stage 18D — Snapshot Source Normalisation

Purpose: make snapshot inputs predictable and explainable.

Scope:

- Harden source metadata, source timestamps, source freshness, malformed-row handling, skipped-row reasons, and source-format versioning for station and body/ring snapshots.
- Prepare for future Spansh-style body/ring source shapes without silently merging conflicting semantics.

Non-goals:

- No live API crawl.
- No canonical writes.

Acceptance:

- Bad or incomplete source files produce clear skipped-row/error summaries instead of partial mystery loads.

### Stage 18E — Warehouse Coverage Reports

Purpose: show how complete the warehouse evidence is.

Scope:

- Report systems with/missing station evidence.
- Report bodies with trusted/unknown ring evidence.
- Report stations with confirmed, inferred/verify, and unresolved body links.
- Report stale evidence and high-value systems needing better evidence.

Non-goals:

- No canonical writes.
- No planner mutation.

Acceptance:

- The warehouse can answer what evidence coverage exists and what remains unknown.

### Stage 18F — Reconciliation Confidence Model

Purpose: make reconciliation explain itself.

Scope:

- Add or harden confidence levels, reasons, source freshness, risk classes, and report-only/canonical-eligible markers for reconciliation candidates and conflicts.
- Preserve volatile fields such as `distanceToArrival` as volatile evidence, not churn sources.

Non-goals:

- No canonical writes.
- No automatic canonical eligibility promotion.

Acceptance:

- Each important reconciliation decision can explain why it is safe, risky, stale, volatile, or blocked.

### Stage 18G — Warehouse Operator Dashboard

Purpose: expose warehouse-specific run and evidence status in a read-only operator surface.

Scope:

- Show latest snapshot loads, latest reconciliation run, source coverage, unresolved count, risky conflicts, stale warnings, report links, and whether canonical tables were untouched.

Non-goals:

- No write controls.
- No live API crawling.
- No canonical writes.

Acceptance:

- Operators can inspect warehouse state without SSH while preserving read-only boundaries.

### Stage 18H — Warehouse-to-Planner Evidence Bridge, Read-Only

Purpose: let the planner see warehouse evidence as evidence, not truth.

Scope:

- Surface selected warehouse evidence context such as available verify station/body evidence, ring evidence, stale/conflicting enrichment state, or newer report-only evidence.
- Keep all warehouse-derived planner context source-labelled and non-mutating.

Non-goals:

- No planner mutation.
- No scoring, CP, economy, service, buildability, Simulation Preview, or optimiser changes.
- No automatic promotion to canonical truth.

Acceptance:

- The planner can display warehouse evidence context without treating report-only evidence as canonical data.

Status: delivered (conservative placeholder path). The Stage 18G warehouse
artifact is admin-gated and aggregate-only, so per-system linking is not yet
safe. Stage 18H shipped a typed read-only `PlannerWarehouseEvidence` model, a
compact source-labelled planner card defaulting to a safe unavailable/unknown
state, no-mutation tests, and a design doc with the future per-system
integration path
(`stage-18h-warehouse-planner-evidence-bridge.md`). No backend endpoint, no live
calls, no canonical or planner state mutation.

### Stage 18I — Canonical Write Design Review

Purpose: design, but not implement, the rules for promoting warehouse evidence into canonical data.

Scope:

- Define which findings could ever write canonical tables, which must remain evidence-only, required confidence, manual approval, audit trail, rollback, table scope, and banned writes.

Non-goals:

- No write-path implementation.
- No canonical data mutation.

Acceptance:

- Stage 18J cannot begin until this design review clearly defines the promotion boundary.

Design review: `stage-18i-canonical-write-design-review.md`. Stage 18I remains
documentation-only and does not authorize canonical writes. It recommends exact
station type promotion as the first Stage 18J pilot only after Stage 18I.5
settles the warehouse database boundary.

### Stage 18I.5 — Warehouse Database Boundary Review

Purpose: decide and document the storage boundary before canonical write pilots begin.

Preferred direction:

- Use **Option B now** if feasible: a separate database on the same Postgres server/stack, for example `edfinder_enrichment`.
- Keep **Option C compatible later**: design the warehouse so it can move to a separate Postgres instance/server if load, retention, or operational risk justify it.

Scope:

- Decide same DB/schema vs same server/separate DB vs separate instance.
- Define proposed database name, connection strings, environment variables, migration ownership, and migration path.
- Define permissions for app user, warehouse loader, warehouse reader, and canonical apply user.
- Decide whether reconciliation uses canonical snapshot copies, read-only views, FDW, or direct read-only access.
- Define backup/restore, retention, performance-isolation expectations, and how write plans cross into guarded canonical apply.
- Explicitly ban direct warehouse mutation of canonical app tables.

Non-goals:

- No canonical writes.
- No production migration of the warehouse DB unless separately approved.
- No planner behaviour changes.
- No scoring, CP, economy, service, buildability, Simulation Preview, or optimiser changes.

Acceptance:

- The repo contains a clear B-vs-C decision document.
- The recommendation is explicit: separate `edfinder_enrichment` database now if feasible, with a clean route to a separate instance/server later.
- Future Stage 18J cannot start until this boundary review is complete.

Boundary review: `stage-18i5-warehouse-database-boundary-review.md`.
Stage 18I.5 recommends Option B, a separate `edfinder_enrichment` database on
the same Postgres stack if feasible, while preserving Option C as the future
separate-instance path. It remains documentation-only and does not create
databases, users, permissions, or migrations.

### Stage 18J — First Narrow Canonical Write Pilot

Purpose: prove one narrow canonical write path can be trusted.

Scope:

- Choose one tiny, low-risk canonical write path such as exact station type promotion, exact confirmed station/body link promotion, or trusted ring rows only if source semantics are strong enough.
- Require dry-run, guarded apply, audit trail, rollback information, conflict blocking, and post-apply verification.

Non-goals:

- No broad canonical backfill.
- No unrestricted warehouse-to-canonical writes.
- No planner mutation beyond reading already-canonical data.

Acceptance:

- One narrow canonical write path is proven safe, auditable, reversible, and boring before any wider canonical expansion.

Stage 18J delivered the station type canonical pilot as the first
canonical-write-capable path. Production apply remains unauthorized unless a
separate future instruction approves the exact artifact, candidate count,
source run/file, table, field, max row count, and apply DSN context.

### Stage 18T — Canonical Safety Test Environment

Purpose: make canonical-write-capable test coverage repeatable in CI and local
development before further production dry-run or apply work.

Scope:

- Add a dedicated canonical safety CI job.
- Install explicit test prerequisites, including `pytest-asyncio`.
- Add a local one-command canonical safety test runner.
- Add disposable Postgres rehearsal and permission-boundary tests for the
  guarded Stage 18J station type apply path.

Non-goals:

- No production apply.
- No production artifact.
- No production DB access.
- No broad canonical backfill.
- No UI/API apply controls or scheduler wiring.

Acceptance:

- The canonical safety suite runs consistently in CI and locally.
- Disposable Postgres rehearsal proves the guarded apply path and scoped
  permissions without touching production.

Environment doc: `stage-18t-canonical-safety-test-environment.md`.

### Stage 18J-Q — Production Reconciliation Artifact Readiness

Purpose: prepare the missing report-only production reconciliation artifact
prerequisite before Stage 18J-P can generate a station-type production dry-run.

Scope:

- Search local/configured artifact locations for a suitable
  `enrichment_staging_reconciliation/v1` production artifact.
- Define the required artifact contract, read-only generation path,
  DSN/access safety checks, sanitisation checks, and stop conditions.
- Keep production apply and production artifact approval blocked.

Non-goals:

- No production apply.
- No production canonical data changes.
- No approved station-type dry-run artifact.
- No broad canonical backfill.
- No UI/API apply controls or scheduler wiring.

Acceptance:

- The repo documents whether a suitable artifact exists.
- Stage 18J-P proceeds only if a verified report-only artifact exists and
  passes the Stage 18J-Q contract.

Readiness doc:
`stage-18j-q-production-reconciliation-artifact-readiness.md`.

### Stage 18J-Q2 — Read-Only Production Reconciliation Plan

Purpose: define the exact safe command path for producing the missing
production reconciliation artifact in a later explicitly approved operation.

Scope:

- Identify the existing `--report-reconciliation` tooling.
- Define required staged warehouse inputs, read-only DSN/access proof,
  environment variables, output path, artifact contract checks, and stop
  conditions.
- Keep Stage 18J-P, production reconciliation execution, station-type dry-run
  generation, and production apply blocked.

Non-goals:

- No production-connected reconciliation command execution.
- No production reconciliation artifact generation.
- No production station-type dry-run artifact.
- No production apply or approval.

Acceptance:

- The repo contains a precise operator plan for the later read-only/report-only
  reconciliation command.
- Stage 18J-P remains blocked until a verified artifact exists and passes the
  contract checks.

Plan doc:
`stage-18j-q2-readonly-production-reconciliation-plan.md`.

### Stage 18J-Q3 — Read-Only Production Reconciliation Artifact

Purpose: run the read-only/report-only production reconciliation artifact
generation path only if all pre-run safety checks are satisfied.

Scope:

- Verify the command shape, read-only DSN/access, approved source run/file,
  read-only session option, and operator-managed output path.
- Generate and validate the `enrichment_staging_reconciliation/v1` artifact
  only when those gates pass.
- Stop and document blockers before any production-connected command if any
  gate is missing.

Current result:

- The pre-run gate failed because no verified read-only/report-only DSN,
  approved source run/file, read-only session option, or operator-managed
  output path was available.
- No production-connected reconciliation command was run.
- No production artifact was generated or approved.
- Stage 18J-P remains blocked.

Report:
`stage-18j-q3-readonly-production-reconciliation-artifact.md`.

### Stage 18J-Q4 — Operator Access Packet

Purpose: define the safe operator checklist for providing the variables that
Stage 18J-Q3 lacked.

Scope:

- Document the required read-only/report-only DSN, source run/file keys,
  operator-managed artifact directory, and mandatory read-only `PGOPTIONS`.
- Provide a redacted command template that matches the real loader CLI.
- Define secret handling, sign-off, and rerun criteria without committing real
  DSNs, credentials, hostnames, or production artifact paths.

Non-goals:

- No production-connected reconciliation command execution.
- No production artifact generation or approval.
- No station-type dry-run generation.
- No production apply or canonical data changes.

Access packet:
`../operations/stage-18j-q4-operator-access-packet.md`.

### Stage 18J-Q4b/Q4c — Read-Only Warehouse DSN Operator Prep

Purpose: document the missing read-only/report-only warehouse DSN and the
operator plan to provision it safely before Stage 18J-Q3 is retried.

Scope:

- Confirm the repo does not already define a usable
  `EDFINDER_WAREHOUSE_READ_DSN`.
- Explain why a local/dev checkout such as DAVE2 is not sufficient unless it
  has separately approved deployment database administration access.
- Define the required read/report role properties, forbidden permissions,
  private environment variables, redacted verification steps, and Q3 retry
  criteria.

Non-goals:

- No production-connected reconciliation command execution.
- No production artifact generation or approval.
- No role creation, grant changes, deployment config changes, or database
  access.
- No station-type dry-run generation.
- No production apply or canonical data changes.

Operator note:
`../operations/stage-18j-q4b-readonly-warehouse-dsn-operator-note.md`.

Provisioning plan:
`../operations/stage-18j-q4c-readonly-warehouse-dsn-provisioning-plan.md`.

### Stage 18J-Q5 — Nested EDSM Station Snapshot Support

Purpose: support the nested EDSM system station snapshot shape observed on the
server without committing production data or running production loads.

Scope:

- Preserve full source system records as raw warehouse evidence.
- Extract deterministic station staging rows from nested `stations` arrays.
- Preserve source run/file keys, station source hashes, parent raw provenance,
  station identity, and station-type labels.
- Keep nested `bodies` collections as raw-only unsupported-source-shape
  warning evidence.

Non-goals:

- No production load.
- No production reconciliation.
- No station-type dry-run.
- No canonical apply.
- No Stage 18J-P or Stage 18K work.

Support doc:
`stage-18j-q5-nested-edsm-station-snapshot-support.md`.

### Stage 18J-Q6 — Memory-Safe Warehouse Station Load

Purpose: make the explicit station warehouse staging load safe for the large
nested EDSM station snapshot after the post-Q5 full load attempt was killed.

Scope:

- Stream `edsm_nightly_stations` source records in write-staging mode.
- Add source-record batch sizing for station writes.
- Keep dry-run as the default/no-write full report path.
- Emit compact write summaries instead of materializing every raw/staged row
  in the final JSON output.
- Document idempotent retry expectations for interrupted staging loads.

Non-goals:

- No production load during the development stage.
- No production reconciliation or artifact generation.
- No station-type dry-run.
- No canonical apply.
- No scheduler/cron implementation.
- No Stage 18J-P or Stage 18K work.

After Q6 merges, the next server action is a controlled retry of the warehouse
station staging load. If that succeeds, move to read-only reconciliation
artifact generation. Stage 18J-P remains blocked until a valid reconciliation
artifact exists.

Support doc:
`stage-18j-q6-memory-safe-warehouse-station-load.md`.

### Stage 18J-Q7 — Reconciliation JSON Serialization Fix

Purpose: fix the read-only reconciliation artifact path after the first
post-Q6 reconciliation attempt failed while printing JSON.

Scope:

- Convert DB-native reconciliation report values such as datetimes, dates, and
  decimals into deterministic JSON-safe values.
- Preserve `enrichment_staging_reconciliation/v1` content and deterministic
  `sort_keys=True` output.
- Keep station candidates and `canonical_writes_planned = 0` visible.
- Document the 0-byte artifact failure and the blocked Stage 18J-P state.

Non-goals:

- No production reconciliation run from development.
- No production artifact generation or approval.
- No station-type dry-run.
- No canonical apply.
- No production DB access.
- No Stage 18J-P or Stage 18K work.

Q7 fixes serialization only. Stage 18J-P remains blocked until a valid
read-only reconciliation artifact exists.

Support doc:
`stage-18j-q7-reconciliation-json-serialization-fix.md`.

### Stage 18J-Q8 - Compact Reconciliation Summary

Purpose: make the valid large reconciliation artifact reviewable without
loading or committing the full production artifact.

Scope:

- Add an offline CLI that streams an existing
  `enrichment_staging_reconciliation/v1` JSON artifact in bounded memory.
- Output source basename only, SHA-256, file size, schema,
  `canonical_writes_planned`, candidate counts, update/insert counts, blocking
  reasons, confidence/risk counts, coverage counts, and capped sanitized
  candidate samples.
- Exclude raw payloads, private paths, DSNs, and secrets from the compact
  output.
- Mark compact output `safe_for_git = false` by default.

Non-goals:

- No production reconciliation run from development.
- No production data or artifact commits.
- No station-type dry-run.
- No canonical apply.
- No production DB access.
- No Stage 18J-P or Stage 18K work.

Q8 is a review-enabling extraction step only. Stage 18J-P remains blocked until
a compact review output exists and is explicitly reviewed.

Support doc:
`stage-18j-q8-compact-reconciliation-summary.md`.

### Stage 19A - Warehouse Artifact Taxonomy and Chunked Roadmap

Purpose: define how warehouse artifacts are named, separated, reviewed, and
sequenced before Stage 19 broadens beyond station reconciliation.

Scope:

- Separate artifact families for stations, bodies, rings, station/body links,
  markets, services, economies, colonisation, freshness, coverage, analytics,
  and future write plans.
- Standardize domain-qualified artifact names for loads, reconciliation,
  compact summaries, freshness status, operator status, and future write plans.
- Require source inventory before load, load before reconciliation,
  reconciliation before compact summary, compact summary before dry-run,
  dry-run before approval packet, approval packet before apply, and manual
  apply only.
- State that scheduler work must remain disabled by default and must never run
  canonical apply.
- Preserve the Stage 18J continuation path: Q9 compact review, strict-filter
  hardening, operator-safe dry-run wrapper, P2 identity diagnostics, P3/P4
  external identity design, P5 migration draft, P6 production readiness review,
  P7 schema-only application packet, P8 schema-only migration apply if
  approved, P9 evidence loader/reconciliation design, P10 identity evidence
  load/reconciliation with no station-type writes, and only later a strict
  station-type dry-run retry with confirmed external identity.

Non-goals:

- No production commands.
- No production DB access.
- No imports, reconciliation, station-type dry-run, or apply.
- No cron/scheduler wiring.
- No Stage 18J-P or Stage 18K work.

Support doc:
`stage-19a-warehouse-artifact-taxonomy-and-chunked-roadmap.md`.

### Stage 18J-Q9 - Compact Summary Review / Station-Type Dry-Run Readiness

Purpose: review the valid compact reconciliation summary and decide whether
Stage 18J-P can retry the station-type production dry-run.

Scope:

- Record compact summary counts for station candidates, update candidates,
  missing-canonical insert candidates, ambiguous matches, confidence/risk
  distributions, and station/body association blockers.
- Set the readiness verdict to `Ready only with strict filter`.
- Require external identity proof, non-ambiguous canonical match, non-volatile
  evidence, permanent station type, station-type-only scope, no station/body
  association writes, no source-only inserts, and an explicit max-row bound
  before any Stage 18J-P retry.

Non-goals:

- No production commands.
- No production DB access.
- No imports, reconciliation, production summarizer run, station-type dry-run,
  or canonical apply.
- No artifact approval or approval record.
- No Stage 18J-P or Stage 18K work.

Support doc:
`stage-18j-q9-compact-summary-review-station-type-dry-run-readiness.md`.

### Stage 18J-P-filter - Strict Station-Type Dry-Run Filter Hardening

Purpose: harden the station-type dry-run eligibility filter before any future
Stage 18J-P production dry-run retry.

Scope:

- Require explicit external station identity proof by matching `market_id` or
  matching `edsm_station_id`; internal canonical `station_id` is not identity
  proof.
- Reject ambiguous identity, source-only inserts, volatile evidence,
  transient/non-slot station types, non-station-type changes, missing
  station-type deltas, and candidates outside the explicit max-row bound.
- Preserve `missing_station_body_name` as a station/body-link blocker while
  allowing externally proven station-type comparisons.
- Keep dry-run output at `canonical_writes_planned = 0`, record the input
  reconciliation artifact checksum, and report explicit rejection counts.
- Add synthetic tests only.

Non-goals:

- No production commands.
- No production DB access.
- No imports, reconciliation, production summarizer run, production
  station-type dry-run, or canonical apply.
- No approval record.
- No Stage 18J-P or Stage 18K work.

Support doc:
`stage-18j-p-filter-strict-station-type-dry-run-filter.md`.

### Stage 18J-P-dryrun-ops - Operator-Safe Station-Type Dry-Run Wrapper

Purpose: add the Hetzner-only wrapper and compact-output controls required
before any future Stage 18J-P production station-type dry-run.

Scope:

- Add `scripts/operator/stage18j_run_station_type_dry_run.sh`.
- Require the shared Hetzner operator environment guard.
- Verify the validated reconciliation artifact checksum before dry-run.
- Require bounded `MAX_ROWS`, with first-pilot refusal above `20`.
- Write the dry-run artifact under the operator artifact directory.
- Cap blocked candidate samples while preserving full rejection counts and
  total candidate counts.
- Print compact summary fields and artifact checksum.

Non-goals:

- No production commands from Codex.
- No production DB access.
- No imports, reconciliation, production summarizer run, production
  station-type dry-run, or canonical apply.
- No approval record.
- No Stage 18J-P or Stage 18K work.

Support doc:
`stage-18j-p-dryrun-operator-safe-wrapper.md`.

### Stage 18J-P2 - Station-Type Identity Coverage Diagnostics

Purpose: explain why the first bounded operator station-type dry-run produced
zero eligible update candidates after every candidate failed external identity
proof.

Scope:

- Add count-only `identity_coverage_summary` to the strict station-type dry-run
  artifact.
- Count source/canonical `market_id` and `edsm_station_id` presence, matches,
  and mismatches.
- Count `system_id64` and station-name matches and mismatches.
- Count canonical match distribution and canonical station rows whose external
  IDs are absent from the reconciliation payload.
- Keep the strict filter unchanged and keep `canonical_writes_planned = 0`.
- Support a future bounded Hetzner/operator diagnostic rerun.

Non-goals:

- No production commands from Codex.
- No production DB access.
- No imports, reconciliation, production summarizer run, production
  station-type dry-run, or canonical apply.
- No approval record.
- No Stage 18K work.

Support doc:
`stage-18j-p2-station-type-identity-coverage-diagnostics.md`.

### Stage 18J-P3 - Canonical External Station Identity Model

Purpose: record why Stage 18J-P produced zero eligible station-type candidates
under the strict filter and identify the missing canonical external identity
model.

Scope:

- Confirm canonical `stations` has no `market_id` or `edsm_station_id`.
- Confirm existing `s.id AS market_id` usage is a compatibility alias/update
  target, not external identity proof.
- Confirm `station_body_links.market_id` is association-scoped and not a
  general external station identity registry.
- Recommend a separate provenance-backed `station_external_identity` table.
- Keep the strict station-type filter unchanged.

Non-goals:

- No production commands.
- No production DB access.
- No imports, reconciliation, production summarizer run, station-type dry-run,
  or canonical apply.
- No approval record.
- No Stage 18K work.

Support doc:
`stage-18j-p3-canonical-external-station-identity-model.md`.

### Stage 18J-P4 - External Station Identity Schema Design

Purpose: design the external station identity schema that can eventually let
read-only reconciliation prove canonical station identity with explicit
external IDs.

Scope:

- Define a separate `station_external_identity` table shape.
- Preserve `canonical_station_id`, `system_id64`, station name, source,
  nullable `market_id`, nullable `edsm_station_id`, source run/file/hash
  provenance, source update time, evidence first/last seen timestamps,
  confidence, freshness, identity status, and conflict reason.
- Use statuses `proposed`, `confirmed`, `conflicting`, `rejected`, and
  `superseded`.
- Allow only `confirmed` rows to serve as read-only reconciliation proof.
- Keep station-type writes blocked until confirmed external identity is
  available.
- Recommend a draft migration first, then a separate production readiness
  review before any schema application, identity evidence load, or dry-run
  retry.

Non-goals:

- No live SQL migration under `sql/`.
- No production commands.
- No production DB access.
- No imports, reconciliation, production summarizer run, station-type dry-run,
  or canonical apply.
- No approval record.
- No Stage 18K work.

Support doc:
`stage-18j-p4-external-station-identity-schema-design.md`.

### Stage 18J-P5 - External Station Identity Migration Draft

Purpose: draft the additive schema migration for the external station identity
model without applying it to production.

Scope:

- Add `sql/027_station_external_identity.sql`.
- Create `station_external_identity` with canonical station reference,
  `system_id64`, station name, source, nullable `market_id`, nullable
  `edsm_station_id`, source run/file/hash provenance, source update time,
  evidence first/last seen timestamps, confidence, freshness, identity status,
  conflict reason, and timestamps.
- Require at least one external ID.
- Allow identity statuses `proposed`, `confirmed`, `conflicting`, `rejected`,
  and `superseded`.
- Add partial unique indexes for confirmed external identities and lookup
  indexes for station, system, external IDs, source run/file, and status.
- Add migration contract tests for constraints, indexes, status behavior,
  additive scope, and no station-type write implication.

Non-goals:

- No production commands.
- No production DB access.
- No production migration apply.
- No imports, reconciliation, production summarizer run, station-type dry-run,
  or canonical apply.
- No approval record.
- No Stage 18K work.

Support doc:
`stage-18j-p5-external-station-identity-migration-draft.md`.

### Stage 18J-P6 - External Identity Migration Production Readiness Review

Purpose: review `sql/027_station_external_identity.sql` before any production
schema application stage.

Scope:

- Confirm the migration is additive and schema-only.
- Confirm it does not alter `stations`.
- Confirm it does not write canonical station-type data.
- Review constraints, indexes, provenance fields, conflict handling, rollback
  expectations, preflight checks, and post-apply checks.
- Record the readiness verdict for a future schema-only Hetzner operator stage.
- Keep identity evidence loading, reconciliation, station-type dry-run, and
  canonical apply blocked.

Non-goals:

- No production commands.
- No production DB access.
- No production migration apply.
- No imports, reconciliation, production summarizer run, station-type dry-run,
  or canonical apply.
- No approval record.
- No Stage 18K work.

Support doc:
`stage-18j-p6-external-identity-migration-production-readiness.md`.

### Stage 19A.1 - Operator Path Guardrails

Purpose: prevent Codex/local prompts from accidentally running Hetzner
production operator commands.

Scope:

- Add a reusable shell guard that checks the Hetzner host, `/opt/ed-finder`,
  Docker Compose availability, and required operator artifact directories.
- Add a Stage 18J compact-summary operator wrapper that calls the guard before
  reading production artifacts.
- Document Codex, DAVE2/local dev, and Hetzner production operator command
  contexts.
- Keep operator scripts fail-fast outside the production operator shell.

Non-goals:

- No production commands from Codex.
- No production DB access.
- No imports, reconciliation, production summarizer run, station-type dry-run,
  or canonical apply.
- No cron/scheduler wiring.
- No Stage 18J-P or Stage 18K work.

Support doc:
`../operations/operator-command-contexts.md`.

## Historical Docs Status

Older docs should not be deleted by default. They contain useful context, rationale, boundaries, and acceptance criteria. Treat them as historical/reference unless this file points to them as active.

| Doc | Status | Use |
|---|---|---|
| `stage-17a-colony-planner-intelligence-forward-plan.md` | Partly superseded | Source alignment and original trust/slot/picker roadmap. Do not follow its next-stage order blindly. |
| `stage-16-colony-role-model-plan.md` | Historical/reference | Role terminology, source separation, declared/inferred/observed boundaries. |
| `stage-15-planner-workspace-redesign-plan.md` | Historical/reference | Topology-first workspace rationale and UI architecture intent. |
| `simulation-preview-ui-architecture.md` | Historical/reference plus current architecture notes | Component ownership and delivered Stage 16/17 architecture notes. |
| `engine-roadmap.md` | Living historical roadmap | Broad engine history and delivered stage summaries. This Stage 17P file controls immediate next work. |
| `enrichment-roadmap.md` | Active for enrichment/operator work | Station enrichment, body/ring enrichment, warehouse, and operator roadmap. |
| Stage 5-14 docs | Historical/reference | Use only for the specific feature or regression they describe. |

## Final Recommendation

Do not add another large planner feature immediately. The healthiest next sequence is:

1. Stage 17Q source pack commit.
2. Stage 17R planner trust audit.
3. Stage 17S existing infrastructure UX hardening.
4. Stage 17T Suggested Builds Strategy Advisor V1.
5. Stage 17U role/strategy integration.
6. Stage 18A enrichment operator dashboard.
7. Stage 18B warehouse reconciliation hardening.
8. Stage 18C warehouse runbook + operator workflow.
9. Stage 18D snapshot source normalisation.
10. Stage 18E warehouse coverage reports.
11. Stage 18F reconciliation confidence model.
12. Stage 18G warehouse operator dashboard.
13. Stage 18H warehouse-to-planner evidence bridge, read-only.
14. Stage 18I canonical write design review.
15. Stage 18I.5 warehouse database boundary review.
16. Stage 18J first narrow canonical write pilot.
17. Stage 18T canonical safety test environment.
18. Stage 18J-Q production reconciliation artifact readiness.
19. Stage 18J-Q2 read-only production reconciliation plan.
20. Stage 18J-Q3 read-only production reconciliation artifact gate.
21. Stage 18J-Q4 operator access packet.
22. Stage 18J-Q4b/Q4c read-only warehouse DSN operator prep.
23. Stage 18J-Q5 nested EDSM station snapshot support.
24. Stage 18J-Q6 memory-safe warehouse station load.
25. Stage 18J-Q7 reconciliation JSON serialization fix.
26. Stage 18J-Q8 compact reconciliation summary.
27. Stage 19A warehouse artifact taxonomy and chunked roadmap.
28. Stage 19A.1 operator path guardrails.
29. Stage 18J-Q9 compact summary review / station-type dry-run readiness.
30. Stage 18J-P-filter strict station-type dry-run filter hardening.
31. Stage 18J-P-dryrun-ops operator-safe station-type dry-run wrapper.
32. Stage 18J-P2 station-type identity coverage diagnostics.
33. Stage 18J-P3 canonical external station identity model.
34. Stage 18J-P4 external station identity schema design.
35. Stage 18J-P5 external station identity migration draft, not applied to production.
36. Stage 18J-P6 external identity migration production readiness review.
37. Stage 18J-P7 schema-only external identity migration application packet.
38. Stage 18J-P8 apply external identity schema migration only, if approved.
39. Stage 18J-P9 external identity evidence loader/reconciliation design.
40. Stage 18J-P10 load/reconcile identity evidence, no station-type writes.
41. Later: retry strict station-type dry-run with confirmed external identity.

This keeps ED-Finder moving toward a genuinely intelligent colony planner while protecting the trust boundaries that make the tool useful. The warehouse should become observable, explainable, and storage-isolated before it becomes a canonical write source.
