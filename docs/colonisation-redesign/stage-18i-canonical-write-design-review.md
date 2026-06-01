# Stage 18I — Canonical Write Design Review

Stage 18I is a documentation and design review only. It does not authorize
canonical writes, add apply scripts, add production jobs, change canonical
tables, or promote warehouse evidence into app truth.

## Executive Summary

The enrichment warehouse is now observable, explainable, and report-only. It
can load offline station/body/ring snapshots into warehouse tables, compare
them with canonical ED-Finder tables, publish coverage and confidence reports,
surface aggregate operator status, and expose a conservative planner evidence
placeholder. Those stages make future canonical writes easier to reason about,
but they do not make any warehouse evidence canonical.

The core conclusion is conservative:

- Stage 18I does not authorize canonical writes.
- Stage 18I is design-only.
- Stage 18J cannot begin until Stage 18I and Stage 18I.5 are complete.
- Ordinary warehouse loaders must remain unable to write canonical tables.
- Any future canonical write must go through a separate guarded apply path with
  a dry-run artifact, manual approval, audit trail, rollback pre-image, and
  post-apply verification.

The recommended first Stage 18J pilot is exact station type promotion from
exact trusted station identity. Exact station/body link promotion and trusted
body ring rows may be eligible later, but they are not the first pilot.

## Current Warehouse State

The current warehouse path is:

```text
offline snapshot file
-> deterministic dry-run/load-plan report
-> optional explicitly gated warehouse staging load
-> read-only reconciliation against canonical ED-Finder tables
-> report-only coverage, confidence/risk, and signal reports
-> read-only operator/planner visibility
```

Current guarantees already established by Stages 18C through 18H:

- Snapshot loading is local/offline. It does not call EDSM, Spansh, EDDN, or
  any other live API.
- Staging writes are explicitly gated and target only warehouse tables.
- Reconciliation, coverage, confidence, analytics, and planner evidence output
  remain report-only.
- Missing values remain unknown, not zero or false.
- Missing ring arrays remain unknown, not false.
- Source-only evidence remains source-only.
- `distanceToArrival` / `distanceFromStar` evidence remains volatile and must
  not drive canonical churn.
- Stage 18G's Admin surface reads a prepublished sanitized artifact; it does
  not generate reports, query the warehouse, or write data.
- Stage 18H's planner bridge defaults to unavailable/unknown because the
  current artifact is aggregate-only and admin-gated.

The warehouse currently has enough evidence quality reporting to support a
future narrow pilot design, but not enough operational isolation to begin one.
Stage 18I.5 must decide the warehouse database boundary first.

## Canonical Write Principles

Any future canonical write path must follow these principles:

1. Warehouse evidence is evidence, not truth, until promoted by an explicitly
   approved guarded apply path.
2. Canonical writes must be narrow, table-specific, field-specific, and
   reversible.
3. Report candidates are not instructions. `candidate_insert_missing_canonical`
   remains a review marker, not an insert instruction.
4. Source labels must be preserved in every dry-run/apply artifact.
5. Unknowns must stay unknown; missing data must never be coerced to false,
   zero, or "no evidence".
6. Volatile evidence must remain evidence-only unless a separate future design
   proves a stable semantics and churn policy.
7. No planner, search, scoring, optimiser, Simulation Preview, role, observed
   evidence, or validation workflow may be mutated by warehouse write pilots.
8. Ordinary warehouse loaders and reconciliation commands must remain unable to
   write canonical tables.
9. Apply code, if later approved, must be separate from loaders and reports.
10. Operators must be able to explain every changed row from the dry-run
    artifact, source evidence, pre-image, and post-apply verification.

## Candidate Write Paths

These paths are candidate future designs only. None is authorized by Stage 18I.

### First Recommended Stage 18J Pilot: Exact Station Type Promotion

The safest first pilot is promoting a canonical station's type from unknown or
empty to a stable known station type when all of the following are true:

- The canonical station already exists.
- Identity is exact and trusted: same system, stable station identifier where
  available, matching market ID or EDSM station ID, and matching normalized
  station name.
- The staged source adapter identifies the station type as a permanent station
  type, not a carrier/transient/mobile type.
- The canonical station type is currently unknown/empty or otherwise explicitly
  eligible for a narrow promotion rule.
- The reconciliation candidate is not ambiguous, blocked, stale beyond the
  accepted policy, source-only, or volatile.
- The dry-run artifact shows exactly which row and field would change.

This pilot is recommended first because it updates one stable field on an
already-known station and can be post-verified without inventing new entities.

### Later Candidate: Exact Station/Body Link Promotion

Exact station/body link promotion may be eligible after the first pilot proves
the apply machinery. It is not first because incorrect links can distort
planner capacity, lane association, and existing infrastructure reasoning.

Minimum later requirements:

- Exact station identity.
- Exact body identity in the same system.
- Non-ambiguous station body-name evidence.
- Clear lane semantics.
- No conflicting existing `station_body_links` row.
- Post-apply verification that planner source labels still distinguish
  canonical, observed, warehouse report-only, and unknown evidence.

### Later Candidate: Trusted Body Ring Rows

Trusted body ring rows may be eligible later with high caution, but they are not
the first pilot unless exact station type promotion is rejected. Rings affect
body truth, resource reasoning, and future planner display. The source semantics
must be stronger than "source says ringed".

Minimum later requirements:

- Exact body identity.
- Trusted ring payload semantics from a source adapter that proves ring fields
  are complete enough for canonical insertion/update.
- No conflict with existing trusted local `body_rings` rows.
- Missing ring arrays remain unknown.
- Empty source ring arrays remain evidence-only unless a future source adapter
  proves stronger no-rings semantics.

### Not First Pilot: Explicit No-Ring Evidence

Explicit no-ring evidence is not first pilot material. Even where trusted local
scan facts can support explicit no-rings coverage reports, canonical no-ring
promotion has higher semantic risk than station type promotion. It should wait
for a later design with source-specific proof and rollback behavior.

## Evidence-Only / Banned Paths

These paths must remain evidence-only for the first canonical pilot and should
be blocked by tests:

- `distanceFromStar` / `distanceToArrival` changes. Distance evidence remains
  volatile and is banned from the first canonical pilot.
- Source-only station/body associations.
- Source-only ringed `true` evidence.
- Missing ring arrays. They remain unknown, not false.
- Empty source ring arrays unless a future source adapter proves stronger
  semantics.
- Explicit no-ring evidence for the first pilot.
- `candidate_insert_missing_canonical`. It remains a review marker, not an
  insert instruction.
- New canonical `systems`, `stations`, `bodies`, or `station_body_links`
  inserts from warehouse evidence.
- Economy, service, market, faction, population, state, signal, codex, or
  derived colonisation/mission intelligence writes.
- Any planner, scoring, CP, economy, service, buildability, optimiser,
  Simulation Preview, role, observed evidence, validation, or Suggested Build
  mutation.

## Confidence And Source Requirements

A future canonical apply candidate must be rejected unless its dry-run artifact
shows all required source and confidence details.

Required for any candidate:

- Source name and adapter version.
- Source run key and source file key.
- Source record hash or equivalent immutable source identity.
- Source timestamp/freshness when available, or an explicit undated/stale
  classification when absent.
- Canonical row identifier and field-specific pre-image.
- Reconciliation action and confidence/risk metadata.
- Human-readable reason codes.
- `auto_promote_to_canonical = false` in report-only review markers.

Required for exact station type promotion:

- `reconciliation_state = confirmed` or a later explicitly named equivalent.
- `risk_class = clear`.
- Exact trusted station identity.
- Non-volatile field classification.
- No blocked/risky/stale/source-only/unknown labels.
- No duplicate source identity conflict.
- No ambiguous canonical match.
- No insufficient evidence.

If confidence would require a source mechanics decision that is not already
documented, the candidate must remain `needs_review` and cannot be applied.

## Audit Trail Requirements

Every future apply run must emit an immutable audit artifact before and after
the transaction. It must be sufficient to answer who changed what, why, from
which evidence, and how to roll it back.

Required fields:

- Apply run ID.
- Dry-run artifact ID/checksum.
- Operator approval ID or approval text.
- Operator identity where available.
- Git commit/version of the apply tool.
- Source run key, source file key, source adapter/version, and source record
  hashes.
- Canonical table, primary key, field name, old value, new value.
- Confidence/risk/reason metadata from the dry-run.
- Transaction timestamp.
- Number of rows planned, applied, skipped, and blocked.
- Post-apply verification result and artifact checksum.

Audit records must not expose DSNs, API keys, private host paths, or secrets.

## Rollback Requirements

Every future canonical write must carry a rollback pre-image before it is
eligible for apply.

Rollback requirements:

- Full pre-image for each changed canonical field.
- Stable primary key for each changed row.
- Source run/file context for traceability.
- Transaction-scoped rollback artifact.
- Ability to produce a dry-run rollback plan before executing rollback.
- Rollback verification proving the row returned to the pre-image value.

If a row cannot be rolled back safely, it cannot be part of the first pilot.
Rollback design must not rely on re-reading mutable warehouse evidence after
the fact; the pre-image must be captured at apply time.

## Dry-Run / Apply / Post-Apply Verification

Future implementation must split these phases clearly:

1. Dry-run creates a versioned artifact with candidate rows, pre-images,
   reason codes, safety blocks, and expected post-apply state.
2. Operator approval explicitly names the dry-run artifact and allowed row
   count.
3. Apply runs only through a separate guarded apply path, not through ordinary
   warehouse loaders.
4. Post-apply verification re-runs the read-only comparison and proves the
   planned updates are now no-ops.

Hard requirements:

- Dry-run remains default.
- Apply requires an explicit confirmation flag and artifact reference.
- Apply must fail closed if the current canonical pre-image differs from the
  dry-run pre-image.
- Apply must fail closed if row count, table, field, source, confidence, or
  risk class differs from the approved dry-run artifact.
- Post-apply verification must be stored as an artifact.
- Any failed post-apply verification blocks wider rollout.

## Operator Approval Workflow

A future apply workflow must require deliberate manual approval:

1. Generate dry-run artifact.
2. Review summary counts, examples, warnings, confidence/risk distributions,
   and exact row-level changes.
3. Confirm Stage 18I.5 database boundary and permissions are in place.
4. Confirm no blocked/risky/stale/source-only/volatile/unknown candidates are
   present in the apply set.
5. Approve a specific artifact checksum and maximum row count.
6. Run guarded apply with the approval reference.
7. Review post-apply verification.
8. Archive dry-run, approval, apply audit, rollback, and verification
   artifacts together.

Approval must be field-specific and table-specific. A general "apply all
warehouse recommendations" command is explicitly out of scope.

## Table-By-Table Risk Review

| Table | First-pilot eligibility | Risk notes |
|---|---|---|
| `systems` | Not eligible | System inserts/updates can affect search, maps, ratings, and planner context. Keep review-only. |
| `stations` | Eligible only for exact station type promotion | First pilot may update only station type under exact trusted station identity. Distance, economy, services, faction, and population remain out of scope. |
| `station_body_links` | Later eligible | Requires exact station/body identity and lane semantics. Not first because incorrect links affect planner capacity and existing infrastructure reasoning. |
| `bodies` | Not first-pilot eligible | Body identity and physical fields have broad downstream effects. Keep review-only until a later design. |
| `body_rings` | Later eligible with high caution | Trusted ring rows may be considered later. Source-only ringed evidence is not enough. |
| `body_scan_facts` | Not first-pilot eligible | Explicit no-ring semantics need separate source proof and rollback policy. |
| `ratings` | Not eligible | No scoring/rating mutation from warehouse evidence. |
| `api_cache` / derived app caches | Not eligible | Cache invalidation may be part of a later apply implementation, but cache rows are not evidence targets. |

Ordinary warehouse tables remain writeable only by the staging loader under
existing warehouse gates. They must not gain canonical write privileges.

## Failure Modes And Safety Blocks

Any of these must block future apply:

- Missing dry-run artifact.
- Dry-run artifact checksum mismatch.
- Missing manual approval.
- Approval row count lower than planned row count.
- Current canonical pre-image differs from dry-run pre-image.
- Ambiguous canonical match.
- Insufficient evidence.
- Duplicate source identity conflict.
- Blocked, risky, stale, volatile, source-only, unknown, or report-only
  candidate in the apply set.
- Missing source run/file key or source record hash.
- Missing rollback pre-image.
- Candidate requires mechanics/source semantics not committed in docs.
- Candidate would insert missing canonical rows.
- Candidate would write a banned table or banned field.
- Candidate would invoke live APIs or Docker.
- Candidate would mutate planner, scoring, optimiser, Simulation Preview,
  roles, observed evidence, validation, or Suggested Builds.
- Post-apply verification does not return the planned no-op state.

## Stage 18I.5 Dependency: Warehouse DB Boundary

Stage 18J cannot begin until Stage 18I.5 is complete. The database boundary is
not a detail; it determines permissions, blast radius, backup/restore, and how
write plans cross from warehouse evidence into guarded canonical apply.

Stage 18I.5 should prefer a separate `edfinder_enrichment` database on the
same Postgres server if feasible. That keeps the warehouse operationally close
enough for current deployment while separating credentials and migration
ownership from the canonical app database. The design should preserve a route
to a separate Postgres instance later if load, retention, or operational risk
requires it.

Stage 18I.5 must decide:

- database/schema/instance boundary,
- connection strings and environment variable names,
- migration ownership,
- warehouse loader, warehouse reader, and canonical apply permissions,
- read-only canonical access pattern for reconciliation,
- backup/restore and retention expectations,
- how approved write plans move into the guarded canonical apply path.

Until Stage 18I.5 lands, no canonical write pilot should be implemented.

Stage 18I.5 decision document:
[`stage-18i5-warehouse-database-boundary-review.md`](./stage-18i5-warehouse-database-boundary-review.md).
It recommends Option B, a separate `edfinder_enrichment` database on the same
Postgres stack if feasible, and keeps Option C as the future separate-instance
path. That decision is still design-only; it does not create databases, users,
permissions, migrations, write scripts, or canonical apply paths.

## Recommended Stage 18J Pilot

The recommended Stage 18J pilot is exact station type promotion only.

The pilot should:

- target only existing canonical station rows,
- update only the station type field,
- require exact trusted station identity,
- reject any carrier/transient/mobile type,
- reject any non-empty known canonical type unless a separate rule explicitly
  allows it,
- require a dry-run artifact, manual approval, audit artifact, rollback
  pre-image, and post-apply verification,
- use a separate guarded apply path,
- prove ordinary warehouse loaders still cannot write canonical tables.

Exact station/body link promotion is eligible later, but not first. Trusted
body ring rows are eligible later with high caution, but not first unless
station type promotion is rejected. Explicit no-ring evidence is not first
pilot material.

## Required Tests Before Implementation

Before any Stage 18J implementation, tests must prove:

- dry-run is the default,
- ordinary warehouse loaders cannot write canonical tables,
- canonical apply path is separate from loaders and reports,
- station type pilot accepts only exact trusted station identity,
- station type pilot rejects ambiguous, insufficient, source-only, stale,
  risky, blocked, volatile, unknown, and report-only candidates,
- carrier/transient station types are rejected,
- existing known station types are not overwritten by default,
- `distanceFromStar` / `distanceToArrival` is banned,
- source-only ring evidence remains source-only,
- missing ring arrays remain unknown,
- empty source ring arrays remain evidence-only,
- `candidate_insert_missing_canonical` is never inserted,
- audit artifact includes source, pre-image, approval, and verification data,
- rollback artifact can restore pre-image values,
- apply fails when current canonical pre-image differs from dry-run pre-image,
- post-apply verification must pass,
- no planner/search/scoring/optimiser/Simulation Preview/role/observed
  evidence/validation mutation occurs,
- no live API, Docker, or production scheduler path is introduced.

## Final Recommendation

Stage 18I should land as design-only and stop. It should not create scripts,
commands, migrations, or code paths.

Proceed next to Stage 18I.5: Warehouse Database Boundary Review. Prefer a
separate `edfinder_enrichment` database now if feasible, while preserving a
route to a separate instance later.

Only after Stage 18I and Stage 18I.5 are both complete should Stage 18J begin,
and the first pilot should be exact station type promotion from exact trusted
station identity. Warehouse evidence must stay evidence/report-only unless it
is promoted by an explicitly approved guarded path.
