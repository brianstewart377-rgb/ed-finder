# Stage 18J-P3 - Canonical External Station Identity Model

## Purpose

Stage 18J-P3 records the follow-up investigation after the bounded Stage 18J-P station-type dry-run proved safe but produced zero eligible rows. The goal is to identify the safest way to model station external identity evidence so the strict station-type filter can stay strict, without writing station types or weakening identity proof.

This stage is investigation/design/tooling only. It does not run production commands, touch the production database, run imports, run reconciliation, run the summarizer against production artifacts, run a production station-type dry-run, run canonical apply, create approval records, or start Stage 18K.

## Production Finding

The Hetzner/operator schema check confirmed that canonical `stations` currently includes:

- `id`
- `system_id64`
- `name`
- `station_type`
- `has_market`
- `has_black_market`
- `station_type_source`
- `station_type_confidence`
- `station_type_updated_at`

The same check confirmed that canonical `stations` does not include:

- `market_id`
- `edsm_station_id`

The attempted identity coverage query failed because `market_id` does not exist on `stations`.

The Stage 18J-P2 dry-run identity coverage then reported:

- `source_edsm_station_id_present`: `298177`
- `canonical_edsm_station_id_present`: `0`
- `canonical_market_id_present`: `0`
- `external_identity_proof_present`: `0`
- `external_identity_proof_absent`: `298177`
- `canonical_station_present_but_external_ids_missing_in_payload`: `262579`
- `possible_canonical_external_ids_omitted_from_reconciliation_payload`: `262579`

## Why Stage 18J-P Has Zero Eligible Rows

The strict station-type filter requires explicit external identity equality:

- `source.market_id == canonical.market_id`, or
- `source.edsm_station_id == canonical.edsm_station_id`.

The source side has EDSM station identifiers, but the canonical side cannot expose matching `market_id` or `edsm_station_id` because those fields are not modeled on `stations` or joined from another canonical identity table. As a result, every candidate fails `external_station_identifier_matches` and is rejected as `rejected_missing_external_identity`.

That is the correct fail-closed result. The zero-candidate outcome means the model is incomplete, not that the filter is too strict.

## Current Canonical Station Schema

`sql/001_schema.sql` defines `stations.id` as the primary key and includes station attributes, service flags, economy fields, government/faction fields, and provenance columns for selected mutable fields. It does not define a separate external `market_id` or `edsm_station_id` column.

`sql/023_station_data_provenance.sql` adds provenance columns for station distance, station type, and body name. It does not add external identity fields.

`sql/021_station_body_links.sql` creates `station_body_links` as a separate association table and includes a nullable `market_id`, but that table models station/body occupied-slot association. It is not a general station external identity registry, and not every station/body link is confirmed.

The API and existing importer paths often project `s.id AS market_id` for compatibility. The EDSM station enrichment probe also selects `id, id AS market_id` from canonical `stations`. That alias is useful for legacy payloads and diagnostics, but it is not modeled external identity proof. Existing docs already warn not to assume `stations.id == market_id` forever.

## Existing Identity / Provenance Options

There is no current canonical/provenance table that stores general station external identity with both `market_id` and `edsm_station_id` evidence.

Existing options and limits:

- `stations.id`: canonical update target and historical import identifier, not explicit external identity proof.
- `station_body_links.market_id`: scoped to station/body association, nullable, and not sufficient as the general external station identity registry.
- `staging_edsm_stations.market_id` and `staging_edsm_stations.edsm_station_id`: source evidence only. These are valuable inputs for backfill, but cannot become canonical proof without a separate verified mapping stage.
- `enrichment_raw_records.raw_payload` and `source_record_hash`: provenance inputs, not direct canonical identity.
- `station_type_source`, `station_type_confidence`, `station_type_updated_at`: field provenance for station type only, not identity proof.

Because no existing table safely carries canonical station external IDs, read-only reconciliation cannot currently join a trusted mapping table and include canonical `market_id` / `edsm_station_id` in `candidate.canonical`.

## Recommended Identity Model

Prefer a separate evidence/provenance-backed mapping table rather than adding external IDs directly to `stations` in this stage.

Reasons:

- External IDs are identity evidence, not ordinary station attributes.
- Source evidence can conflict across snapshots, adapters, and historical imports.
- The warehouse needs to retain provenance: source run, source file, raw record hash, confidence, freshness, and status.
- Canonical `stations` should remain the core application truth table; adding source-only evidence directly there risks making provisional evidence look authoritative.
- The existing `station_body_links` precedent already keeps uncertain association metadata out of the main `stations` row.

The recommended table name is `station_external_identity`.

Stage 18J-P4 refines this recommendation into the explicit schema design:
`stage-18j-p4-external-station-identity-schema-design.md`.
Stage 18J-P5 then drafts the additive migration as
`sql/027_station_external_identity.sql` without applying it to production or
backfilling identity evidence.

## Why Not Relax The Filter

Do not accept name-only matches, system/name matches, or `stations.id == source.market_id` as station-type write eligibility.

The strict filter is protecting a canonical write-capable path. Station names can collide, drift, or be ambiguous inside historical import data. Internal primary keys are update targets, not external identity proof. Treating internal ID equality as market identity would hide exactly the schema gap P2 exposed.

The right fix is to model and populate external station identity safely, then let the existing filter pass only when explicit canonical external IDs match the source IDs.

## Proposed External Identity Table

Design sketch for a later additive migration:

```sql
CREATE TABLE IF NOT EXISTS station_external_identity (
    id BIGSERIAL PRIMARY KEY,
    canonical_station_id BIGINT NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    system_id64 BIGINT NOT NULL REFERENCES systems(id64) ON DELETE CASCADE,
    station_name TEXT NOT NULL,
    source TEXT NOT NULL,
    source_class TEXT NOT NULL CHECK (source_class IN (
        'stable',
        'semi-stable',
        'volatile',
        'diagnostic-only'
    )),
    market_id BIGINT DEFAULT NULL,
    edsm_station_id BIGINT DEFAULT NULL,
    source_run_key TEXT DEFAULT NULL,
    source_file_key TEXT DEFAULT NULL,
    source_record_hash TEXT NOT NULL,
    confidence TEXT NOT NULL,
    identity_status TEXT NOT NULL DEFAULT 'proposed' CHECK (identity_status IN (
        'proposed',
        'confirmed',
        'conflicting',
        'rejected',
        'superseded'
    )),
    match_method TEXT NOT NULL,
    source_updated_at TIMESTAMPTZ DEFAULT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,

    CHECK (market_id IS NOT NULL OR edsm_station_id IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_station_external_identity_source_market
    ON station_external_identity (source, market_id)
    WHERE market_id IS NOT NULL AND identity_status = 'confirmed';

CREATE UNIQUE INDEX IF NOT EXISTS idx_station_external_identity_source_edsm
    ON station_external_identity (source, edsm_station_id)
    WHERE edsm_station_id IS NOT NULL AND identity_status = 'confirmed';

CREATE INDEX IF NOT EXISTS idx_station_external_identity_station
    ON station_external_identity (canonical_station_id, identity_status);

CREATE INDEX IF NOT EXISTS idx_station_external_identity_system_name
    ON station_external_identity (system_id64, station_name);

CREATE INDEX IF NOT EXISTS idx_station_external_identity_source_run
    ON station_external_identity (source_run_key, source_file_key);
```

The table is intended to store canonical-station-to-external-ID mapping evidence. It should not store volatile station facts such as distance, market price, demand, supply, services, or station type changes. Those stay in staging, report-only intelligence, or their own observation tables.

Recommended status semantics:

- `proposed`: one source snapshot suggests the mapping; not yet enough for canonical write eligibility.
- `confirmed`: mapping has passed the identity evidence stage's rules and can be used by read-only reconciliation as canonical external identity.
- `conflicting`: source evidence disagrees with an existing active mapping or maps one external ID to multiple canonical stations.
- `rejected`: evidence was reviewed or classified as not acceptable proof.
- `superseded`: old mapping retained for audit/history but not used as active proof.

Stage 18J-P5 drafts this status model in `sql/027_station_external_identity.sql`.

## Backfill Strategy

Backfill should be its own stage and must be separate from station-type dry-run/apply.

Recommended backfill path:

1. Read warehouse station evidence from staged, already reviewed offline snapshots.
2. Match to canonical stations conservatively inside the same `system_id64`.
3. Prefer source rows with explicit `market_id` and/or `edsm_station_id`, station name, source run/file keys, and source record hash.
4. Require exactly one canonical station candidate by strict criteria before creating a `proposed` or `confirmed` identity row.
5. Detect conflicts before writes:
   - one external ID mapping to multiple canonical stations,
   - one canonical station mapping to multiple active external IDs for the same source identity kind,
   - source system/name disagreement,
   - stale or undated evidence when the stage requires current evidence.
6. Emit a versioned identity coverage artifact before any table write.
7. In a non-production/staging rehearsal, load only identity rows, never station type rows.
8. Only after review, run a bounded production identity evidence load if explicitly approved.

The backfill must retain raw provenance fields and never mark failed or ambiguous rows as confirmed.

## Reconciliation Integration

After the identity table exists and is populated, read-only reconciliation can join it to canonical station matches and include canonical external IDs in `candidate.canonical`:

- `canonical.market_id`
- `canonical.edsm_station_id`
- `canonical.external_identity_status`
- `canonical.external_identity_source`
- `canonical.external_identity_confidence`
- `canonical.external_identity_source_record_hash`

Only `identity_status = 'confirmed'` should count as strict proof for
station-type dry-run eligibility. `proposed`, `conflicting`, `rejected`, and
`superseded` rows should be visible in diagnostics but not accepted by the
strict filter.

The Stage 18J station-type dry-run filter should remain unchanged in spirit: explicit external ID match, exactly one canonical station, matching `system_id64`, matching normalized station name, station-type-only delta, no volatile evidence, no transient type, and `canonical_writes_planned = 0` in dry-run output.

## Dry-Run Impact

Before the identity model exists, a zero-eligible Stage 18J-P dry-run is expected and safe.

After a confirmed identity table exists, the read-only reconciliation artifact should be able to report canonical external identity coverage. Only then should the station-type dry-run be retried. That retry should remain a dry-run and should still produce:

- `canonical_writes_planned = 0`
- `apply_run = false`
- `approval_record_created = false`
- explicit identity coverage counts
- rejected candidates for missing, proposed-only, conflicting, or stale identity mappings

A non-zero eligible count would still not authorize apply. It would only support a later review packet.

## Boundaries

This stage does not:

- run production commands,
- touch production DB,
- run imports,
- run reconciliation,
- run summarizer against production artifacts,
- run production station-type dry-run,
- run canonical apply,
- create approval records,
- start Stage 18K,
- apply or create a production migration,
- populate station external identity rows,
- alter the strict filter to accept weaker proof,
- allow station-type writes.

## Recommended Next Stages

- Stage 18J-P4 - External station identity schema design.
- Stage 18J-P5 - External station identity migration draft, not applied to production.
- Stage 18J-P6 - External identity evidence loader/reconciliation design.
- Stage 18J-P7 - External identity migration production readiness review.
- Stage 18J-P8 - Apply external identity schema migration only, if approved.
- Stage 18J-P9 - Load/reconcile identity evidence, no station-type writes.
- Stage 18J-P10 - Retry strict station-type dry-run with confirmed external identity.

## Final Recommendation

Do not add `market_id` or `edsm_station_id` directly to `stations` in the next implementation stage unless an app-level need is separately proven. The safer path is a separate `station_external_identity` table populated by a dedicated identity evidence stage, with provenance and conflict status preserved.

Keep the strict station-type filter exactly as strict as it is now. Stage 18J-P cannot produce eligible station-type updates until canonical external station identity is modeled, populated, and exposed through read-only reconciliation. The smallest next stage that unblocks progress is a design-reviewed additive identity schema migration plus a report-only identity evidence loader plan, not station-type apply.

