# Stage 18I.5 — Warehouse Database Boundary Review

Stage 18I.5 is a documentation and design review only. It decides the intended
warehouse storage boundary before any Stage 18J canonical write pilot. It does
not create databases, users, permissions, migrations, write scripts, scheduler
jobs, or canonical apply paths.

## Executive Summary

The current enrichment warehouse is safe as a report-only foundation, but it is
not the preferred long-term boundary for canonical write pilots. The warehouse
tables currently live beside the app's canonical tables and are protected by
code-level table allow-lists, canonical deny-lists, dry-run defaults, and
explicit staging flags. Those protections are necessary, but not sufficient as
the permanent architecture for any future warehouse-to-canonical promotion.

Stage 18I.5 recommends Option B now if feasible: move the warehouse to a
separate `edfinder_enrichment` database on the same Postgres stack/server. This
keeps operational complexity moderate while creating a clearer database,
migration, retention, backup, and permission boundary. The design must preserve
Option C compatibility: the `edfinder_enrichment` database should be able to
move to a separate Postgres instance/server later if load, retention, or
operational risk justifies it.

This stage does not implement Option B. Until the boundary is implemented and
accepted, all warehouse output remains report-only and Stage 18J must not
start.

## Current Boundary

Current implementation characteristics:

- The app services use the live app database DSN, currently represented by
  `DATABASE_URL`.
- The warehouse staging loader accepts an explicit `--dsn` only for gated
  warehouse modes.
- The first warehouse migration creates tables such as
  `enrichment_source_runs`, `enrichment_source_files`,
  `enrichment_raw_records`, `staging_edsm_stations`,
  `staging_edsm_bodies`, and `staging_body_rings`.
- Those tables are currently named as ordinary tables in the same database
  namespace used by canonical app tables.
- `apps/importer/src/enrichment_warehouse.py` defines warehouse write tables
  and a canonical table deny-list for `systems`, `stations`, `bodies`,
  `body_rings`, `body_scan_facts`, and `station_body_links`.
- `apps/importer/src/enrichment_staging_db_loader.py` requires explicit
  `--write-staging`, `--dsn`, and `--confirm-staging-db` for staging writes.
- Reconciliation and staged-row reports are read-only modes that still read
  canonical tables for comparison.
- Admin/operator warehouse status reads a prepublished JSON artifact only; it
  does not query the warehouse database.

This current state is acceptable as a transitional report-only foundation. It
is not the preferred long-term foundation for canonical write pilots because
permissions, retention, backup, and performance are still coupled to the live
app database boundary.

## Options Considered

### Option A — Same Database, Separate Schema

Option A keeps warehouse and canonical app data in the same Postgres database
but moves warehouse tables into a dedicated schema such as
`enrichment_staging`.

Pros:

- Simple queries and joins.
- Easy current deployment because there is still one database connection.
- Minimal operational change from the current same-database layout.
- Good transitional step if a separate database is not immediately feasible.

Cons:

- Weak isolation compared with a separate database.
- Warehouse jobs can still compete with live app workload inside the same DB.
- Permission separation is harder to reason about and easier to erode.
- Backup, restore, retention, and vacuum behavior remain tightly coupled.
- Future canonical apply permissions are more dangerous because canonical and
  warehouse objects share the same database boundary.

Stage 18I.5 decision: Option A is acceptable only as the current transitional
state or an interim schema cleanup. It is not the preferred long-term
canonical-write foundation.

### Option B — Same Postgres Stack, Separate Database

Option B creates a separate warehouse database, recommended name
`edfinder_enrichment`, on the same Postgres server/stack as the app database.

Pros:

- Clearer separation between canonical app data and warehouse evidence.
- Independent migrations, retention, backups, restore tests, and rebuilds.
- Cleaner permission boundaries for app, loader, reporting, snapshot export,
  and future canonical apply users.
- Easier reset/rebuild of warehouse evidence without touching canonical data.
- Keeps same-server operational simplicity for deployment, monitoring, and
  backups.
- Preserves a clean path to move the warehouse database to a separate instance
  later.

Cons:

- Cross-database comparison is not a plain same-database join.
- Reconciliation needs canonical snapshots, exports, tightly controlled
  read-only views, FDW, or another deliberate comparison mechanism.
- More environment variables, deployment configuration, and migration
  ownership than Option A.
- Operators need explicit backup/restore and retention procedures for the new
  database.

Stage 18I.5 decision: Option B is the preferred next architecture if feasible.
It should be designed now but not implemented in this stage.

### Option C — Separate Postgres Instance

Option C moves `edfinder_enrichment` to a separate Postgres instance/server.

Pros:

- Strongest performance and operational isolation.
- Warehouse load, retention, large imports, vacuum behavior, and recovery can
  be managed separately from the live app database.
- Failure or overload in warehouse storage has less chance of impacting user
  traffic.
- Cleanest security boundary for future production-scale ingestion.

Cons:

- More infrastructure, monitoring, networking, backup, restore, secret, and
  deployment complexity.
- Cross-instance comparison requires snapshots, exports, FDW, logical
  replication, or another controlled data transfer mechanism.
- More operational work than the warehouse needs before the first narrow pilot.

Stage 18I.5 decision: Option C is the future-compatible target if warehouse
load grows or operational risk requires stronger isolation. Option B should be
designed so this move remains possible.

## Recommendation

Recommend Option B now if feasible: `edfinder_enrichment` as a separate
warehouse database on the same Postgres stack/server.

Do not implement Option B in this stage. Do not create databases, users,
permissions, migrations, Docker changes, or write scripts here. The purpose of
Stage 18I.5 is to document and accept the boundary so later implementation can
be done deliberately.

Explicitly reject leaving the warehouse as an unbounded extension of the live
app database forever. The current same-database state can remain transitional
for report-only development, but it should not become the permanent foundation
for Stage 18J canonical write pilots.

## Target Boundary Model

Target model:

```text
edfinder app database
  canonical current facts
  app APIs/search/planner data
  app-owned migrations

edfinder_enrichment database
  raw source archives
  normalized staging evidence
  reconciliation/coverage/report artifacts
  future immutable write-plan proposals
  warehouse-owned migrations

guarded canonical apply boundary
  explicit dry-run artifact
  manual approval
  immutable audit/rollback pre-image
  post-apply verification
```

Warehouse DB may store raw, staging, report, and write-plan evidence. The
canonical app DB remains the source of trusted current facts. Warehouse evidence
does not become canonical until it crosses a guarded apply boundary in a later
approved stage.

## Database And Schema Naming

Recommended database name:

- `edfinder_enrichment`

Recommended initial schema approach:

- Use a default schema inside `edfinder_enrichment` only if operations stay
  simple and permissions are clear.
- Prefer a named schema such as `warehouse` or `enrichment` if it improves
  migration ownership and table grouping.

Table names can remain close to the existing foundation names:

- `enrichment_source_runs`
- `enrichment_source_files`
- `enrichment_raw_records`
- `staging_edsm_stations`
- `staging_edsm_bodies`
- `staging_body_rings`
- future report/audit/write-plan proposal tables

Do not rename current tables in this stage. Naming changes belong to a later
implementation or migration proposal.

## Connection Strings And Environment Variables

Current state:

- `DATABASE_URL` points app services at the canonical app database.
- The staging loader accepts an operator-provided `--dsn`.
- Test-only smoke DSNs use `EDFINDER_STAGING_TEST_DSN`.
- Admin status reads artifact paths, not warehouse DB connections.

Future proposed environment variables:

- `DATABASE_URL`: canonical app database for app/API services.
- `EDFINDER_WAREHOUSE_DSN`: warehouse loader DSN for
  `edfinder_enrichment`.
- `EDFINDER_WAREHOUSE_READ_DSN`: read/report DSN for warehouse reporting
  processes.
- `EDFINDER_CANONICAL_READ_DSN`: tightly scoped canonical snapshot/export or
  read-only comparison DSN.
- `EDFINDER_CANONICAL_APPLY_DSN`: disabled/unavailable by default until Stage
  18J or later.

Do not add these variables to `env.example` or deployment config in this stage.
They are proposed names for the implementation stage.

## Migration Ownership

Target ownership:

- Canonical app migrations remain owned by the app database migration path.
- Warehouse migrations should be owned separately and run only against
  `edfinder_enrichment`.
- Warehouse migrations must not alter canonical app tables.
- Canonical apply migrations, if ever needed, must be separate from ordinary
  warehouse migrations and reviewed as part of a future apply stage.

The existing `sql/026_enrichment_staging_foundation.sql` remains the current
foundation. A later implementation should decide whether it is copied, moved,
or superseded by warehouse-database migrations. Stage 18I.5 does not change it.

## Permissions Model

| Role | Reads | Writes | Must never access | Exists now? |
|---|---|---|---|---|
| App user | Canonical app tables needed by APIs/search/planner. | App-owned canonical tables according to existing app behavior. | Warehouse raw/staging tables by default; canonical apply proposal/audit tables unless explicitly needed read-only. | Existing as current app DB user. |
| Warehouse loader user | Warehouse source/run metadata needed for idempotent staging loads. | Warehouse raw/staging/source tables in `edfinder_enrichment`. | Canonical app tables; canonical apply audit tables except maybe write-plan proposal output if later approved. | Future Option B requirement. Current loader uses caller-supplied `--dsn`. |
| Warehouse read/report user | Warehouse raw/staging/report tables and controlled canonical snapshots or views. | Nothing, or only report artifact tables if later explicitly approved. | Canonical app writes; warehouse loader mutation paths. | Future Option B requirement. |
| Canonical snapshot exporter or read-only canonical user | Canonical app tables needed for reconciliation snapshots/views. | Snapshot/export target only if using an export job; never live canonical tables. | Warehouse staging writes; canonical apply writes. | Future requirement. |
| Canonical apply user | Only the narrow canonical tables/fields approved by a future Stage 18J apply path. | Approved canonical fields only, via guarded apply transaction. | Warehouse staging mutation; broad canonical writes; planner/scoring/role/observed/validation mutation paths. | Future requirement; should be disabled/unavailable by default until Stage 18J or later. |
| Operator/admin status reader | Sanitized prepublished JSON status artifacts. | Nothing. | DSNs, private paths, warehouse DB direct access, canonical write paths. | Existing artifact-reader pattern from Stage 18G. |

The canonical apply user must be separate from the warehouse loader user. Audit
ownership belongs to the canonical apply side, not ordinary warehouse staging.

## Canonical Snapshot / Read-Only Comparison Strategy

Reconciliation should initially compare warehouse evidence against canonical
snapshots or tightly controlled read-only views, not ad hoc direct writes.

Acceptable comparison approaches for later implementation:

- Periodic canonical snapshot exports into `edfinder_enrichment`.
- Read-only canonical views exposed to the warehouse report user.
- FDW or controlled cross-database access with strict read-only credentials.
- Immutable exported artifacts used by offline reconciliation.

The first implementation should prefer the simplest auditable approach that
keeps canonical data read-only from the warehouse side. Snapshot exports are
boring and easy to audit, but they introduce freshness lag. Read-only views or
FDW reduce lag but need stricter permission review.

Missing canonical snapshot data must remain unknown, not false.

## Write Plan Transfer Boundary

Write plans are proposals, not executable commands.

Approved write plans must cross the warehouse-to-canonical boundary only by:

- immutable JSON artifacts with checksums, or
- an apply queue/table with strict permissions and immutable rows.

The transfer artifact or queue row must include:

- source run/file identifiers,
- source record hashes,
- canonical row pre-images,
- candidate action and reason codes,
- confidence/risk labels,
- field-specific proposed changes,
- operator approval reference,
- maximum row count,
- artifact checksum,
- creation timestamp and tool version.

Ordinary warehouse loaders must not execute these write plans. A future guarded
canonical apply tool must read the approved artifact/queue, validate the
current canonical pre-image, apply only the approved field/table changes, and
write audit/rollback records on the canonical apply side.

## Canonical Apply User Boundary

The canonical apply user is a future-stage account. It should not exist, or
should be disabled/unavailable, until Stage 18J or later.

If later created, it must:

- be separate from the app user and warehouse loader user,
- have no warehouse staging write privileges,
- have no broad canonical table privileges,
- be scoped to specific tables and fields for the approved pilot,
- be unavailable to normal app/API/runtime services,
- be usable only by the guarded apply path,
- require explicit operator approval and dry-run artifact references.

For the recommended Stage 18J pilot, this would mean narrow permission to update
only the station type field on eligible existing `stations` rows, if the
database permission model can express that safely. If field-level permission is
not practical, the apply code and database transaction checks must enforce the
field restriction and tests must prove it.

## Backup, Restore, And Retention

Option B allows warehouse evidence to have different retention and recovery
rules from canonical app data.

Target policy:

- Canonical app DB remains backed up and restored as the source of trusted
  current facts.
- `edfinder_enrichment` can be rebuilt from source snapshots where practical,
  but report/audit/write-plan artifacts may need retention for traceability.
- Raw source archives can have a retention window based on storage cost and
  reproducibility.
- Canonical apply audit and rollback artifacts must be retained with canonical
  operational records, not ordinary throwaway warehouse staging.
- Restore tests should cover both the app database and the warehouse database
  separately.

Warehouse retention must not force canonical app restore behavior, and
canonical app retention must not be weakened by warehouse volume.

## Performance And Operational Isolation

Option B improves but does not fully isolate performance because the database
still shares the same Postgres server/stack.

Expected gains:

- Warehouse rebuilds can be stopped, backed up, restored, or dropped without
  dropping canonical app tables.
- Warehouse migrations can be scheduled separately.
- Warehouse table bloat, retention, and vacuum behavior are easier to manage.
- Permissions are easier to audit.

Remaining risks:

- Large imports can still use shared CPU, memory, disk IO, WAL, and backup
  bandwidth.
- Cross-database comparison may require export jobs that need scheduling and
  freshness monitoring.
- A future move to Option C may still be needed if warehouse workloads grow.

Mitigation: design all DSNs, migrations, and reconciliation inputs so
`edfinder_enrichment` can move to another instance without changing report
semantics.

## Local Development And Test Strategy

Local development should keep dry-run and fixture tests first:

- Snapshot loaders and write-plan builders remain pure/offline where possible.
- Unit tests continue to prove ordinary warehouse loaders cannot write
  canonical tables.
- Real-Postgres smoke tests remain skipped by default.
- Option B smoke tests should use disposable databases only.

Future test DSN names may include:

- `EDFINDER_WAREHOUSE_TEST_DSN`
- `EDFINDER_CANONICAL_READ_TEST_DSN`
- `EDFINDER_CONFIRM_WAREHOUSE_TEST_DB=yes`

Do not add these variables in this stage. They are design placeholders for a
future implementation.

## Deployment Migration Plan

Stage 18I.5 does not perform deployment migration. A future implementation
should use a staged plan:

1. Keep current same-database report-only workflow running.
2. Create `edfinder_enrichment` in staging or a disposable environment.
3. Add warehouse-only migrations for the new database.
4. Add dedicated warehouse loader/read users.
5. Prove fixture and smoke loads against `edfinder_enrichment`.
6. Add canonical snapshot/export or controlled read-only comparison path.
7. Prove reconciliation reports match same-database output for a bounded
   fixture or staging dataset.
8. Update runbook and deployment secrets.
9. Only after acceptance, retire same-database warehouse writes.
10. Keep Stage 18J blocked until the boundary is accepted.

No production database creation, user creation, permission changes, compose
changes, or migrations happen in this stage.

## Risks And Mitigations

| Risk | Mitigation |
|---|---|
| Cross-database comparison becomes complex. | Start with canonical snapshots or tightly controlled read-only views; keep output deterministic. |
| Warehouse snapshots become stale. | Include snapshot timestamp/freshness in reports and keep missing/stale values unknown/report-only. |
| Permissions drift toward broad access. | Separate app, loader, read/report, snapshot/export, and apply users; test denied canonical writes. |
| Warehouse load still impacts app DB server. | Bound imports, schedule large jobs, monitor resource use, and preserve Option C path. |
| Apply queue becomes an implicit command channel. | Treat write plans as immutable proposals; require guarded apply validation and manual approval. |
| Audit ownership is misplaced in warehouse staging. | Store canonical apply audit/rollback artifacts on the apply side, tied to canonical transaction records. |
| Option B remains design-only too long. | Keep all warehouse output report-only until implementation lands. |

## Stage 18J Readiness Criteria

Stage 18J cannot start until:

- This boundary decision is accepted.
- The project either implements Option B or explicitly accepts a temporary
  bounded transitional arrangement with equivalent safety controls.
- Ordinary warehouse loaders remain unable to write canonical app tables.
- Warehouse loader, read/report, canonical snapshot/read-only, and canonical
  apply roles are defined.
- The canonical apply user is unavailable by default or scoped to the approved
  pilot only.
- Reconciliation has a documented read-only comparison strategy.
- Write-plan transfer is immutable and non-executable by ordinary loaders.
- Audit and rollback ownership are assigned to the canonical apply side.
- Stage 18I's exact station type pilot requirements remain unchanged.

If the database boundary remains unresolved, all warehouse output remains
report-only and Stage 18J must not begin.

## Final Decision

Stage 18I.5 recommends Option B as the next architecture:
`edfinder_enrichment` should become a separate warehouse database on the same
Postgres stack/server if feasible. Option C remains the future scaling and
isolation path.

This stage does not implement the recommendation. It creates no database,
users, permissions, migrations, Docker changes, canonical apply path, or write
scripts.

The canonical app database remains the source of trusted current facts.
Warehouse evidence remains raw/staging/report/write-plan evidence only.
Warehouse-to-canonical promotion must cross a guarded apply boundary in a later
approved stage. Stage 18J cannot start until this boundary decision is accepted;
if the boundary is not implemented or otherwise explicitly accepted, all
warehouse output remains report-only.
