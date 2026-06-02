# Stage 18J-P6 — External Identity Migration Production Readiness

## Purpose

Stage 18J-P6 reviews whether the Stage 18J-P5 external station identity
migration draft is safe and complete enough for a later schema-only production
application stage.

This stage is docs/review only. It does not run production commands, touch the
production database, apply the migration to production, run imports, run
reconciliation, run the summarizer against production artifacts, run
station-type dry-run, run canonical apply, create approval records, or start
Stage 18K.

## Migration Reviewed

Reviewed migration:

- `sql/027_station_external_identity.sql`

Reviewed supporting material:

- `tests/test_station_external_identity_migration.py`
- `docs/colonisation-redesign/stage-18j-p5-external-station-identity-migration-draft.md`
- `docs/colonisation-redesign/stage-18j-p4-external-station-identity-schema-design.md`
- `docs/operations/enrichment-warehouse-runbook.md`
- `docs/colonisation-redesign/enrichment-roadmap.md`
- `docs/colonisation-redesign/stage-17p-current-state-forward-plan.md`
- `scripts/operator/require_hetzner_operator_env.sh`

The migration creates `station_external_identity` as a separate
provenance-backed identity table. It does not add `market_id` or
`edsm_station_id` to `stations`.

## Readiness Verdict

Ready for schema-only production application.

This verdict is limited to a future schema-only stage that creates the empty
`station_external_identity` table and indexes. It does not approve any identity
data load, backfill, reconciliation run, station-type dry-run, canonical apply,
or approval record.

The verdict depends on the required preflight checks passing and on the
operator applying only `sql/027_station_external_identity.sql` from the Hetzner
production operator shell.

## Additive Safety Review

The migration is additive:

- `CREATE TABLE IF NOT EXISTS station_external_identity`;
- `CREATE INDEX IF NOT EXISTS ...`;
- `CREATE UNIQUE INDEX IF NOT EXISTS ...`;
- comments on the new table and new columns only.

The migration does not:

- alter `stations`;
- alter `systems`;
- alter `station_body_links`;
- insert, update, delete, or backfill data;
- create station-type write paths;
- create views or procedures that imply canonical write eligibility;
- create approval records.

The table references `stations(id)` and `systems(id64)`, but those references do
not rewrite existing rows because the new table starts empty.

## Constraint Review

The migration requires at least one external station identifier:

- `market_id IS NOT NULL OR edsm_station_id IS NOT NULL`

Identity status is constrained to:

- `proposed`;
- `confirmed`;
- `conflicting`;
- `rejected`;
- `superseded`.

Confidence and freshness are constrained to the current project vocabulary used
by station identity, warehouse staging, and P4:

- confidence: `exact_station_identity`, `source_station_snapshot`, `high`,
  `medium`, `low`, `unresolved`;
- freshness: `source_updated_at`, `file_snapshot`, `current`, `recent`,
  `stale`, `undated`, `unknown`.

Conflicting rows require `conflict_reason`, and evidence timestamps must satisfy
`evidence_last_seen_at >= evidence_first_seen_at`.

These constraints are sufficient for schema-only application. Later loader
logic must still enforce higher-level confirmation rules, such as rejecting
name-only matches and internal `stations.id` equality as external identity
proof.

## Index Review

The migration adds lookup indexes for future reconciliation paths:

- `canonical_station_id`;
- `system_id64`;
- `market_id`;
- `edsm_station_id`;
- `source_run_key, source_file_key`;
- `identity_status`.

The migration adds partial unique indexes for confirmed identities:

- `(source, market_id)` when `market_id` is present and status is `confirmed`;
- `(source, edsm_station_id)` when `edsm_station_id` is present and status is
  `confirmed`;
- `(canonical_station_id, source, market_id)` for confirmed market identity;
- `(canonical_station_id, source, edsm_station_id)` for confirmed EDSM identity.

The uniqueness rules are safe for schema-only application because the table is
empty and because only `confirmed` rows are constrained. Non-confirmed
`proposed`, `conflicting`, `rejected`, and `superseded` evidence remains
representable.

The rules are intentionally conservative: a confirmed external ID should not map
to multiple canonical stations for the same source. Later evidence-loader logic
must still detect semantic conflicts such as one canonical station receiving
multiple active external IDs for the same identity kind.

## Provenance Review

The migration preserves the provenance fields needed for review:

- `source`;
- `source_run_key`;
- `source_file_key`;
- `source_record_hash`;
- `source_updated_at`;
- `evidence_first_seen_at`;
- `evidence_last_seen_at`;
- `confidence`;
- `freshness_class`.

These fields are sufficient for a future identity evidence loader and read-only
coverage artifact to explain where an identity row came from. Warehouse
source-only evidence remains source evidence until a later loader/reconciliation
stage promotes it to `confirmed`.

## Conflict Handling Review

Conflict states are representable through:

- `identity_status = 'conflicting'`;
- required `conflict_reason`;
- nullable external IDs so market and EDSM conflicts can be represented
  independently;
- non-confirmed rows remaining outside the confirmed unique-index constraints.

The migration does not resolve conflicts by itself. Later stages must classify
and report conflicts before any identity row is accepted as canonical external
identity proof.

## Rollback / Reversibility Considerations

Before any identity rows are loaded, rollback is straightforward: remove the
new table and indexes. Because the table is new and empty after schema-only
application, rollback does not require restoring canonical station data.

After identity evidence is loaded, rollback becomes a data-retention decision
and must be handled by a separate evidence rollback plan. P6 does not approve
loading evidence, so this readiness verdict applies only to the empty-table
schema step.

The operator should verify that `station_external_identity` does not already
exist before applying the migration. If it does exist, stop and inspect the
table definition instead of relying on `CREATE TABLE IF NOT EXISTS` to repair a
partial or divergent table.

## Required Preflight Checks

Before any future schema-only production application stage, the operator must:

- confirm the shell is the Hetzner production operator shell on host
  `ed-finder`;
- confirm the working directory is `/opt/ed-finder`;
- run the Hetzner operator environment guard;
- confirm `git` main includes PR #126 and `sql/027_station_external_identity.sql`;
- confirm the production database is reachable;
- confirm migration 027 has not already been applied;
- confirm `station_external_identity` does not already exist;
- confirm a backup/snapshot exists, or the operator explicitly accepts the risk
  of a schema-only additive migration;
- confirm no imports are running;
- confirm no reconciliation jobs are running;
- confirm no canonical apply jobs are running;
- confirm no station-type dry-run is running;
- confirm Docker services are healthy;
- check SQL syntax against a disposable or local PostgreSQL database first.

If any preflight check fails or is ambiguous, stop before applying the schema.

## Required Post-Apply Checks

After a future schema-only production application stage, the operator must
verify:

- `station_external_identity` exists;
- all expected constraints exist;
- all expected indexes exist;
- `stations` row count is unchanged from the preflight snapshot;
- `station_external_identity` row count is `0`;
- no station-type data changed;
- no approval record was created;
- app containers and Docker services are still healthy;
- no imports, reconciliation jobs, station-type dry-runs, or canonical apply
  jobs were started by the schema application.

If any post-apply check fails, stop and preserve logs/output for review.

## Production Application Boundaries

A later schema application stage must be schema-only:

- applying the schema must not load identity data;
- applying the schema must not backfill;
- applying the schema must not run imports;
- applying the schema must not run reconciliation;
- applying the schema must not run station-type dry-run;
- applying the schema must not run canonical apply;
- applying the schema must not create approval records;
- identity evidence load/reconciliation remains a later stage.

The migration only creates the place where identity evidence can later be
stored. It does not make any station-type candidate eligible.

## What This Still Does Not Enable

Even after a future schema-only application:

- canonical `stations` still has no `market_id` or `edsm_station_id` columns;
- `stations.id` remains an update target, not external identity proof;
- `station_body_links.market_id` remains association-scoped;
- no identity rows exist yet;
- no confirmed external identity coverage exists yet;
- strict station-type dry-run remains blocked by missing confirmed canonical
  external identity;
- station-type canonical writes remain blocked.

## Risks / Open Questions

Known risks and follow-up questions:

- `CREATE TABLE IF NOT EXISTS` will not fix a partially existing divergent
  table; preflight must require the table to be absent.
- The current indexes are sufficient for the first confirmed-identity join
  shape, but later high-volume reconciliation may need an additional composite
  index such as `(canonical_station_id, identity_status)`.
- The migration constrains common confidence and freshness labels. If a later
  loader needs additional labels, that stage must explicitly extend the
  constraint before using them.
- The migration does not include an automatic `updated_at` trigger. Current
  repo migrations commonly use timestamp defaults without a generic update
  trigger; later loader code must update `updated_at` explicitly.
- Foreign keys use `ON DELETE CASCADE` for stations/systems. That is acceptable
  for identity evidence tied to canonical rows, but evidence archival policy
  should be revisited before any large identity load.

None of these risks blocks a schema-only production application, provided the
preflight and post-apply checks are followed.

## Recommended Operator Command Shape

This is a recommended shape for a later explicitly approved Hetzner operator
stage. Do not run it from Codex/local development.

```sh
cd /opt/ed-finder
scripts/operator/require_hetzner_operator_env.sh

git fetch origin main
git status --short --branch
git log --oneline -5

# Preflight examples:
# - verify PR #126 merge is present on main
# - verify database connectivity through the operator-managed DB environment
# - verify station_external_identity does not already exist
# - capture stations row count
# - verify no imports/reconciliation/dry-run/apply jobs are active
# - verify Docker services are healthy

psql "$EDFINDER_PRODUCTION_DSN" \
  -v ON_ERROR_STOP=1 \
  -f sql/027_station_external_identity.sql

# Post-apply examples:
# - verify station_external_identity exists
# - verify constraints and indexes
# - verify station_external_identity row count is 0
# - verify stations row count is unchanged
# - verify station_type data is unchanged
# - verify app containers remain healthy
```

The real operator prompt should replace the comments with concrete read-only
preflight/post-apply SQL checks and should record the exact outputs.

## Recommended Next Stages

- Stage 18J-P7 - Schema-only external identity migration application packet.
- Stage 18J-P8 - Apply external identity schema migration only, if approved.
- Stage 18J-P9 - External identity evidence loader/reconciliation design.
- Stage 18J-P10 - Load/reconcile identity evidence, no station-type writes.
- Later: retry strict station-type dry-run only after confirmed external
  identity appears in read-only reconciliation output.

## Final Recommendation

`sql/027_station_external_identity.sql` is ready for a future schema-only
production application stage after this readiness review merges.

Do not combine that schema application with evidence loading, reconciliation,
station-type dry-run, canonical apply, or approval-record creation. The next
stage should be a narrow operator packet for applying only the empty
`station_external_identity` schema on Hetzner with explicit preflight and
post-apply checks.
