# Stage 18J-P7 — External Identity Schema Production Apply Closeout

## Purpose

Stage 18J-P7 records the closeout for the schema-only production application of
`sql/027_station_external_identity.sql` after the Stage 18J-P6 readiness
review.

This is documentation/closeout only. Codex did not run production commands,
touch the production database, reapply the migration, run imports, run
reconciliation, run the summarizer against production artifacts, run
station-type dry-run, run canonical apply, create approval records, or start
Stage 18K.

## Production Action Recorded

The Hetzner operator flow has already applied the schema-only migration:

- migration applied: `sql/027_station_external_identity.sql`;
- environment: Hetzner production operator context;
- scope: schema creation only;
- identity evidence load: not run;
- station-type write path: not run.

This closeout records the supplied operator result. It does not re-run or
verify production commands from Codex.

## Migration Applied

Applied migration:

- `sql/027_station_external_identity.sql`

The migration creates the separate provenance-backed
`station_external_identity` table with constraints and indexes. It does not add
`market_id` or `edsm_station_id` columns to canonical `stations`, and it does
not update canonical station rows.

## Post-Apply Checks

Recorded post-apply checks:

- `station_external_identity` exists;
- `station_external_identity` row count is `0`;
- canonical `stations` count after apply is `284763`;
- expected constraints are present;
- expected indexes are present;
- no imports were run;
- no reconciliation was run;
- no summarizer was run;
- no station-type dry-run was run;
- no canonical apply was run;
- no identity evidence was loaded;
- no station-type data changed.

## Table State

`station_external_identity` is now present in production, but it is empty.

Current recorded row count:

```text
station_external_identity: 0
```

The empty table means the schema is available for later evidence-loading
stages, but no canonical external station identity proof exists yet.

## Constraint Verification

The following constraints were reported present:

- `chk_station_external_identity_confidence`;
- `chk_station_external_identity_conflict_reason`;
- `chk_station_external_identity_external_id`;
- `chk_station_external_identity_freshness`;
- `chk_station_external_identity_seen_window`;
- `chk_station_external_identity_status`;
- `station_external_identity_canonical_station_id_fkey`;
- `station_external_identity_pkey`;
- `station_external_identity_system_id64_fkey`.

These constraints preserve the P5/P6 contract: at least one external ID is
required, identity status/confidence/freshness values are constrained,
conflicting rows require a reason, evidence seen windows are valid, and the
table remains tied to canonical station/system rows.

## Index Verification

The following indexes were reported present:

- `idx_station_external_identity_confirmed_source_edsm`;
- `idx_station_external_identity_confirmed_source_market`;
- `idx_station_external_identity_confirmed_station_source_edsm`;
- `idx_station_external_identity_confirmed_station_source_market`;
- `idx_station_external_identity_edsm_station_id`;
- `idx_station_external_identity_market_id`;
- `idx_station_external_identity_source_run_file`;
- `idx_station_external_identity_station`;
- `idx_station_external_identity_status`;
- `idx_station_external_identity_system`;
- `station_external_identity_pkey`.

These indexes support the initial reconciliation join shape and confirmed
identity uniqueness checks. They do not load evidence or make station-type
updates eligible by themselves.

## Canonical Station Count Verification

The supplied post-apply result records canonical `stations` count stayed
unchanged at:

```text
stations: 284763
```

The closeout result also records that no station-type data changed. Because
Codex did not query production, this document records the supplied operator
verification rather than independently rechecking the production database.

## What Was Not Run

The schema-only apply did not run:

- imports;
- reconciliation;
- summarizer against production artifacts;
- station-type dry-run;
- canonical apply;
- identity evidence load;
- station-type data writes.

Codex did not run production commands, touch the production database, or
reapply the migration while creating this closeout.

## Safety Outcome

The schema-only production application completed with the expected empty table,
expected constraints, expected indexes, and no recorded data-load or
station-type write activity.

This satisfies the Stage 18J-P6 readiness boundary for applying only the
external identity schema. It does not satisfy the identity-proof requirement
for strict station-type dry-run eligibility.

## Remaining Blocker

The schema is now present, but it contains no identity evidence yet. Stage
18J-P station-type dry-run remains blocked from producing eligible candidates
until identity evidence is loaded, reconciled, and confirmed.

Only `identity_status = 'confirmed'` rows should later be eligible for
read-only reconciliation as canonical external identity proof. Name-only
matches, warehouse source-only evidence, internal `stations.id` equality, and
station/body link association evidence remain insufficient.

## Recommended Next Stages

- Stage 18J-P8 - External identity evidence loader/reconciliation design.
- Stage 18J-P9 - External identity evidence load dry-run.
- Stage 18J-P10 - External identity evidence write-staging/load, no
  station-type writes.
- Stage 18J-P11 - Identity coverage artifact.
- Stage 18J-P12 - Reconciliation integration with confirmed identity.
- Stage 18J-P13 - Retry strict station-type dry-run.

## Final Recommendation

Treat the external identity schema as present but empty. The next work should
design and validate identity evidence loading/reconciliation without creating
station-type writes.

Do not retry the strict station-type dry-run until confirmed external identity
coverage exists in read-only reconciliation output. Do not run canonical apply
or create approval records as part of identity evidence loading.
