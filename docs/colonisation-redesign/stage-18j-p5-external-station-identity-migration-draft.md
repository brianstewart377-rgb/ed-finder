# Stage 18J-P5 — External Station Identity Migration Draft

## Purpose

Stage 18J-P5 drafts the additive schema migration for the external station
identity model recommended by Stage 18J-P4.

The migration creates a provenance-backed `station_external_identity` table so
future stages can store explicit external station identity evidence separately
from canonical `stations` rows and separately from station/body association
evidence.

This stage drafts and tests the migration only. It does not apply the migration
to production, run production commands, touch the production database, run
imports, run reconciliation, run the summarizer against production artifacts,
run station-type dry-run, run canonical apply, create approval records, or
start Stage 18K.

## Migration Scope

Migration file:

- `sql/027_station_external_identity.sql`

Test file:

- `tests/test_station_external_identity_migration.py`

The migration is additive and idempotent. It creates one new table and its
indexes. It does not update `stations`, add `market_id` or `edsm_station_id`
columns to `stations`, alter `station_body_links`, backfill identity rows, or
create any station-type approval or apply path.

## Table Shape

The drafted table is:

```sql
CREATE TABLE IF NOT EXISTS station_external_identity (
    id                          BIGSERIAL       PRIMARY KEY,
    canonical_station_id        BIGINT          NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    system_id64                 BIGINT          NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
    station_name                TEXT            NOT NULL,
    source                      TEXT            NOT NULL,
    market_id                   BIGINT          DEFAULT NULL,
    edsm_station_id             BIGINT          DEFAULT NULL,
    source_run_key              TEXT            NOT NULL,
    source_file_key             TEXT            NOT NULL,
    source_record_hash          TEXT            NOT NULL,
    source_updated_at           TIMESTAMPTZ     DEFAULT NULL,
    evidence_first_seen_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    evidence_last_seen_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    confidence                  TEXT            NOT NULL,
    freshness_class             TEXT            NOT NULL,
    identity_status             TEXT            NOT NULL DEFAULT 'proposed',
    conflict_reason             TEXT            DEFAULT NULL,
    created_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
```

`canonical_station_id` is the ED-Finder station update target. It is not an
external `market_id`. External identity proof must come from `market_id` and/or
`edsm_station_id` evidence preserved with source provenance.

## Constraints

The migration adds check constraints for:

- at least one external ID: `market_id IS NOT NULL OR edsm_station_id IS NOT NULL`;
- identity status values:
  - `proposed`,
  - `confirmed`,
  - `conflicting`,
  - `rejected`,
  - `superseded`;
- confidence labels aligned with current station/enrichment conventions:
  - `exact_station_identity`,
  - `source_station_snapshot`,
  - `high`,
  - `medium`,
  - `low`,
  - `unresolved`;
- freshness labels aligned with warehouse and P4 terminology:
  - `source_updated_at`,
  - `file_snapshot`,
  - `current`,
  - `recent`,
  - `stale`,
  - `undated`,
  - `unknown`;
- `conflicting` rows must have `conflict_reason`;
- `evidence_last_seen_at` must be greater than or equal to
  `evidence_first_seen_at`.

These constraints make the table suitable for evidence review while keeping all
non-confirmed statuses representable.

## Indexes

The migration adds unique partial indexes for confirmed identities:

- `idx_station_external_identity_confirmed_source_market`
- `idx_station_external_identity_confirmed_source_edsm`
- `idx_station_external_identity_confirmed_station_source_market`
- `idx_station_external_identity_confirmed_station_source_edsm`

These indexes block duplicate confirmed external ID mappings while leaving
`proposed`, `conflicting`, `rejected`, and `superseded` rows available for
review and audit.

The migration also adds lookup indexes for:

- `canonical_station_id`;
- `system_id64`;
- `market_id`;
- `edsm_station_id`;
- `source_run_key, source_file_key`;
- `identity_status`.

## Provenance Requirements

Every identity row must preserve source provenance:

- `source`;
- `source_run_key`;
- `source_file_key`;
- `source_record_hash`;
- `source_updated_at` when available;
- evidence first/last seen timestamps.

Warehouse source-only evidence is still not canonical identity by default. A
future loader/reconciliation stage must decide whether evidence remains
`proposed`, becomes `confirmed`, or is marked `conflicting`, `rejected`, or
`superseded`.

## Conflict Handling

The table represents conflict state directly with:

- `identity_status = 'conflicting'`;
- a required `conflict_reason`.

Conflicting evidence is retained for visibility and audit. It is blocked from
canonical external identity proof, blocked from strict station-type dry-run
eligibility, and should appear in future coverage/reconciliation artifacts.

Examples that should be represented as conflicts in later evidence stages:

- one `market_id` maps to multiple canonical stations;
- one `edsm_station_id` maps to multiple canonical stations;
- one canonical station receives multiple active external IDs for the same
  source identity kind;
- source system/name evidence disagrees with the canonical station;
- repeated source evidence disagrees by source record hash.

## What This Does Not Do

This stage does not:

- apply the migration to production;
- update or rewrite `stations`;
- add `market_id` or `edsm_station_id` directly to `stations`;
- reuse `station_body_links` as a general identity table;
- backfill identity evidence;
- load warehouse evidence;
- run imports;
- run reconciliation;
- run summarizer against production artifacts;
- run station-type dry-run;
- run canonical apply;
- create approval records;
- relax the strict station-type filter;
- start Stage 18K.

## Production Application Status

The migration is drafted only. It is not applied to production in this stage.

Production application requires a later explicit readiness review and approval
stage. That later stage must verify the migration against a disposable or
staging database, confirm rollback expectations before any identity data exists,
and keep station-type writes blocked.

Stage 18J-P6 performs that readiness review in
`stage-18j-p6-external-identity-migration-production-readiness.md` and finds the
migration ready for a future schema-only production application stage, provided
the required preflight and post-apply checks pass.

## Reconciliation Impact

No reconciliation code is changed in P5. Current reconciliation output remains
unchanged.

After a later approved schema application and evidence load, read-only
reconciliation can be extended to join only `identity_status = 'confirmed'`
rows and expose canonical external identity fields such as:

- `canonical.market_id`;
- `canonical.edsm_station_id`;
- `canonical.external_identity_status`;
- `canonical.external_identity_source`;
- `canonical.external_identity_confidence`;
- `canonical.external_identity_freshness_class`;
- `canonical.external_identity_source_run_key`;
- `canonical.external_identity_source_file_key`;
- `canonical.external_identity_source_record_hash`.

## Station-Type Dry-Run Impact

P5 does not run or change station-type dry-run.

The strict station-type filter remains unchanged. Until confirmed external
identity is available through read-only reconciliation, the Stage 18J-P
station-type dry-run should continue to reject candidates that lack canonical
external identity proof.

The new table does not imply station-type approval. Even after the schema is
applied and evidence is loaded, only confirmed external identity should satisfy
the identity proof portion of the strict filter, and any non-zero dry-run result
still requires a separate review packet before apply can be discussed.

## Validation

Validation for this stage should include:

- `git diff --check`;
- shell syntax checks for the Stage 18J operator guard/wrappers;
- canonical safety tests;
- targeted station-type and enrichment tests;
- py_compile for the station-type pilot and tests;
- `tests/test_station_external_identity_migration.py`;
- secret/DSN scan across changed docs, code, and SQL.

The migration tests verify:

- the table is created;
- required columns and foreign-key references are present;
- at least one external ID is required;
- valid identity statuses are represented while older P3 draft names are not;
- confidence and freshness checks use local conventions;
- duplicate confirmed identity indexes exist;
- non-confirmed statuses remain representable;
- lookup indexes exist;
- the migration is additive and does not write canonical station data.

## Recommended Next Stages

- Stage 18J-P6 - External identity migration production readiness review.
- Stage 18J-P7 - Schema-only external identity migration application packet.
- Stage 18J-P8 - Apply external identity schema migration only, if approved.
- Stage 18J-P9 - External identity evidence loader/reconciliation design.
- Stage 18J-P10 - Load/reconcile identity evidence, no station-type writes.
- Later: retry strict station-type dry-run only after confirmed external
  identity appears in read-only reconciliation output.

## Final Recommendation

Keep `sql/027_station_external_identity.sql` as a draft additive migration
until a later production readiness review approves applying only the schema.

Do not backfill identity evidence, alter the strict station-type filter, or
start any station-type dry-run/apply path in P5. The correct next step is an
external identity evidence loader/reconciliation design that can populate and
review the table safely after the schema has been separately approved.
