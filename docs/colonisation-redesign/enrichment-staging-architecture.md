# Enrichment Staging Architecture

This document defines the offline enrichment warehouse foundation for
ED-Finder. It is separate from the existing station enrichment runbook and does
not add canonical writes.

## Target Pipeline

```text
external snapshot / stream / dump
-> raw immutable archive
-> source run registry
-> raw staging records
-> normalised staging tables
-> read-only comparison against canonical ED-Finder tables
-> pure planners
-> versioned dry-run reports
-> separately designed write path only if explicitly approved later
```

The warehouse exists so ED-Finder can ingest large repeatable offline sources:
EDSM dumps, Spansh dumps, and local EDDN-derived archives. It should replace
large live API crawls over time because snapshots are rerunnable, diffable,
batchable, and not tied to upstream rate-limit windows.

## Implemented Foundation Stage

Migration `sql/026_enrichment_staging_foundation.sql` adds the first warehouse
tables:

| Family | Tables |
|---|---|
| Source registry | `enrichment_source_runs`, `enrichment_source_files`, `enrichment_raw_records` |
| Core staging | `staging_edsm_stations`, `staging_edsm_bodies`, `staging_body_rings` |
| Future product staging | `staging_factions`, `staging_system_states`, `staging_station_economies`, `staging_station_services`, `staging_market_commodities`, `staging_body_signals`, `staging_codex_entries` |
| Derived dry-run intelligence | `derived_mission_intelligence`, `derived_exploration_intelligence`, `derived_colonisation_economy_intelligence`, `derived_alert_candidates` |

The migration is additive. It creates new tables and indexes only. It does not
alter canonical `systems`, `stations`, `bodies`, `body_rings`,
`body_scan_facts`, or `station_body_links`.

The helper modules keep parsing, write planning, warehouse SQL, reconciliation,
and report-only signals separate:

| Path | Role |
|---|---|
| `apps/importer/src/enrichment_staging.py` | Pure canonicalisation, hashing, source classification, staging validation, and report skeleton helpers. |
| `apps/importer/src/enrichment_snapshot_loader.py` | Offline-only local `.json` / `.json.gz` snapshot reader and dry-run report builder. |
| `apps/importer/src/enrichment_write_plans.py` | Pure station and body/ring staging write-plan builders. |
| `apps/importer/src/enrichment_warehouse.py` | Warehouse table registry, canonical deny-list, and SQL safety helpers. |
| `apps/importer/src/enrichment_warehouse_repository.py` | Repository orchestration for schema checks, staging writes, staged-row reports, and reconciliation reports. |
| `apps/importer/src/enrichment_warehouse_sql.py` | Warehouse SQL query helpers. |
| `apps/importer/src/enrichment_reconciliation.py` / `apps/importer/src/enrichment_reconciliation_scoring.py` | Read-only candidate shaping and transparent confidence/risk scoring. |
| `apps/importer/src/enrichment_staged_reports.py` | Staged-row report shaping. |
| `apps/importer/src/enrichment_analytics.py` | Pure report-only analytics, colonisation, and mission-density signal scaffolds. |

The implemented adapter paths support local EDSM station snapshots
(`edsm_nightly_stations`) and local EDSM body/ring snapshots
(`edsm_nightly_bodies`). They read local `.json` and `.json.gz` files, stream
JSON-array or NDJSON records, build deterministic dry-run reports, and can
optionally write only to warehouse/staging tables when explicitly gated with
staging-only DB flags. They do not make network calls, invoke containers, run
production migrations, or write canonical tables.

## Source Evidence Classes

The foundation tracks source stability without treating any source as canonical
truth:

| Class | Meaning | Examples |
|---|---|---|
| `stable` | Snapshot facts that should not drift except through newer dumps. | Spansh dump body/ring identity and long-lived catalogue fields. |
| `semi-stable` | Snapshot facts that are useful but may change between dumps. | EDSM station/body snapshot identity, station type, body name, EDDN journal/signals. |
| `volatile` | Operational observations that can churn and must not overwrite canonical values by themselves. | `distanceToArrival`, market prices, demand/supply. |
| `diagnostic-only` | Live/manual probe evidence for investigation, not bulk enrichment truth. | Live EDSM diagnostics. |

`distanceToArrival` is staged as `distance_to_arrival` with volatile
classification. It is evidence for comparison and planning only; it must not
churn canonical `stations.distance_from_star`.

## Report Contracts

The helper supports these versioned report contracts:

* `enrichment_snapshot_load_plan/v1`
* `station_snapshot_enrichment_dry_run/v1`
* `body_ring_enrichment_dry_run/v1`
* `mission_intelligence_dry_run/v1`
* `exploration_intelligence_dry_run/v1`
* `colonisation_economy_intelligence_dry_run/v1`
* `alert_candidate_dry_run/v1`

`enrichment_snapshot_load_plan/v1` has fixture-backed station and body/ring
snapshot output. Reconciliation uses `enrichment_staging_reconciliation/v1`,
and pure signal helpers emit report-only analytics contracts such as
`enrichment_analytics_signals/v1`, `colonisation_candidate_signals/v1`, and
`mission_density_signals/v1`. Reports include source run/file summaries,
summary counts, staged/planned rows, skipped rows, conflicts, warnings,
confidence/freshness/source-class distributions, candidate confidence/risk
fields, and deterministic sorting for stable diffs.

Stage 18B broadens the read-only reconciliation report with named sections:

* `station_body_association_candidates` records staged station/body-name
  association evidence as supported, unresolved, missing, or ambiguous. It is
  report-only and does not create `station_body_links`.
* `source_coverage_summary` records per-entity action/confidence/source
  coverage, volatile warning counts, and ring-evidence state. Missing ring
  arrays remain `unknown_not_false`.
* `confidence_risk_summary` keeps aggregate confidence, identifier/evidence
  quality, and risk-flag distributions explainable.
* `analytics_signals`, `colonisation_signals`, and `mission_density_signals`
  are embedded as report-only signal sections with
  `canonical_writes_planned = 0`.

## Offline Fixture Loader

Run from the repo root:

```sh
python3 apps/importer/src/enrichment_snapshot_loader.py \
    --source edsm_nightly_stations \
    --source-file tests/fixtures/edsm_station_snapshot.json \
    --json
```

For gzip input:

```sh
python3 apps/importer/src/enrichment_snapshot_loader.py \
    --source edsm_nightly_stations \
    --source-file path/to/local-edsm-stations.json.gz \
    --limit 1000 \
    --json
```

The loader accepts only local files. `--dry-run` is the default and only
supported mode. `--apply`, `--write`, and `--commit` fail closed.

The staging DB loader remains explicitly opt-in. Staging writes require
`--write-staging`, `--dsn`, and `--confirm-staging-db`; read-only schema,
staged-row, and reconciliation report modes require a DSN but do not require
the staging-write confirmation flag. Canonical flags continue to fail closed.
The repository writes only to:

* `enrichment_source_runs`
* `enrichment_source_files`
* `enrichment_raw_records`
* `staging_edsm_stations`
* `staging_edsm_bodies`
* `staging_body_rings`

It never writes to `systems`, `stations`, `bodies`, `body_rings`,
`body_scan_facts`, or `station_body_links`.

Optional real-Postgres smoke tests exist for station staging, body/ring
staging, and read-only reconciliation. They are skipped by default unless both
`EDFINDER_STAGING_TEST_DSN` and `EDFINDER_CONFIRM_STAGING_TEST_DB=yes` are set.

## Current EDSM Station Normalisation

The first offline adapter normalises station snapshot records into staging
evidence with these fields when present:

* `system_id64`, `system_name`
* `market_id`, `edsm_station_id`
* `station_name`, `station_type`
* `distance_to_arrival` as volatile observation
* `body_name`
* `services`, `economies`
* `controlling_faction`, `allegiance`, `government`
* `source_updated_at`, `raw_payload`, `source_record_hash`
* `source_class`, `confidence`, `freshness_class`, `provenance`

Missing or invalid required station fields are skipped with warnings. They do
not crash the loader and do not imply canonical writes.

## Trust Boundaries

These existing contracts remain unchanged:

* Staging tables are source evidence, not canonical truth.
* Derived intelligence is analysis output, not a canonical fact overwrite.
* Source-only `body_scan_facts.is_ringed = true` remains unknown until
  resolved to trusted local `body_rings` rows.
* Source-only `body_scan_facts.is_ringed = false` may represent explicit
  trusted no-rings according to existing tests.
* Station `distanceToArrival` is volatile and must not churn canonical station
  distance.
* No station/body/system canonical rows are updated by this foundation.
* No station/body links are created by this foundation.

## Next Recommended Stage

Keep the next stage report-only: broaden warehouse-backed reconciliation and
analytics around staged station/body/ring evidence, improve candidate quality
signals, and add more skipped-by-default smoke coverage. Any future canonical
write path is out of scope until it has a separate design, safety review, and
test plan.
