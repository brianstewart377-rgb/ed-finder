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

Stage 18D hardens the snapshot boundary by making source normalisation visible
in the dry-run report. Source runs/files now carry source format/version,
record stream shape, source timestamp summaries, and freshness summaries.
Skipped rows are counted by explicit reason, exact duplicate source payloads
are reported by `source_record_hash`, and repeated source identities with
conflicting payload hashes become report-only conflicts instead of silent
merges. Unsupported nested source shapes, including future system-with-`bodies`
inputs, are skipped with explicit unsupported-shape reasons until a dedicated
adapter exists.

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

The snapshot load plan also includes source-normalisation observability:
`source_timestamp_summary`, `source_freshness_summary`,
`source_record_duplicate_groups`, skipped-row reason distributions, and
body/ring `ring_array_evidence`. Missing ring arrays remain
`unknown_not_false`; empty arrays are source evidence only and do not become a
canonical no-rings conclusion.

Stage 18E keeps those semantics in warehouse coverage reports: source-only ring
rows are counted separately from trusted local `body_rings` evidence, missing
ring arrays stay unknown, and explicit no-ring coverage is counted only from
trusted local scan facts such as `body_scan_facts.is_ringed = false`. Empty
source arrays remain review evidence unless a future source adapter proves
stronger semantics.

Stage 18B broadens the read-only reconciliation report with named sections:

* `station_body_association_candidates` records staged station/body-name
  association evidence as supported, unresolved, missing, or ambiguous. It is
  report-only and does not create `station_body_links`.
* `source_coverage_summary` records per-entity action/confidence/source
  coverage, volatile warning counts, and ring-evidence state. Missing ring
  arrays remain `unknown_not_false`.
* `warehouse_coverage_report` records Stage 18E operator coverage sections for
  systems with and missing station evidence, trusted/unknown/explicit no-ring
  body coverage, confirmed/inferred/unresolved station-body links, stale or
  undated source evidence, duplicate and skipped source coverage, high-value
  systems needing better evidence, and source type/format coverage. It is
  versioned as `enrichment_warehouse_coverage_report/v1`, deterministic, and
  report-only.
* `confidence_risk_summary` keeps aggregate confidence, identifier/evidence
  quality, risk-class, review-classification, source-freshness-impact, and
  future-review-marker distributions explainable. Stage 18F keeps this model
  report-only and versioned as `enrichment_reconciliation_confidence/v1`;
  blocked, risky, stale, volatile, source-only, confirmed, inferred/verify,
  unresolved, report-only, and unknown states are labels for operator review,
  not canonical eligibility or write instructions.
* `analytics_signals`, `colonisation_signals`, and `mission_density_signals`
  are embedded as report-only signal sections with
  `canonical_writes_planned = 0`.

## Operator Status Surface

Stage 18G makes warehouse evidence status visible in the existing token-gated
Admin surface without adding a live warehouse job runner. The API reads only a
configured JSON artifact, `ENRICHMENT_WAREHOUSE_STATUS_JSON_PATH`, and returns
sanitized status for latest snapshot/reconciliation state, source coverage,
unresolved/risky/blocked/stale evidence, skipped or duplicate source records,
and canonical-safety flags. Missing, invalid, unset, or unsafe artifacts remain
unavailable/unknown rather than zero.

The status endpoint hides full filesystem paths and does not query the
warehouse database, generate reports, invoke Docker, call live APIs, or write
canonical rows. Operators publish the artifact from a separate reviewed
warehouse run, usually a reconciliation report.

## Planner Evidence Bridge (Stage 18H)

Stage 18H surfaces warehouse evidence in the Colony Planner as report-only
evidence, not canonical truth. The current Stage 18G warehouse artifact is
admin-token-gated and aggregate-only, so it cannot be safely joined to a planner
system by `system_id64`. Following the stage decision gate, Stage 18H ships a
typed read-only model (`PlannerWarehouseEvidence`), a compact source-labelled
planner card that defaults to a safe unavailable/unknown state, no-mutation
tests, and a design doc with the future per-system artifact contract. It adds no
backend endpoint and makes no live calls. See
`stage-18h-warehouse-planner-evidence-bridge.md` for the artifact contract and
integration path.

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
The Stage 18C operator workflow and exact command examples are documented in
[`../operations/enrichment-warehouse-runbook.md`](../operations/enrichment-warehouse-runbook.md).
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

The body/ring adapter normalises body records and source-only ring payloads
separately. Ring payloads remain `association_status = "source_only"` unless a
later read-only reconciliation finds trusted local ring evidence. Missing ring
arrays are preserved as unknown, non-array ring fields are reported as malformed
ring evidence, and unsupported nested source shapes are not inferred into body
or ring rows.

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

Stage 18I.5 adds the warehouse database boundary decision in
[`stage-18i5-warehouse-database-boundary-review.md`](./stage-18i5-warehouse-database-boundary-review.md).
It recommends moving the warehouse to a separate `edfinder_enrichment` database
on the same Postgres stack if feasible, while keeping a future path to a
separate instance. Until that boundary is implemented and accepted, warehouse
output remains report-only.

## Next Recommended Stage

Keep the next stage report-only: broaden warehouse-backed reconciliation and
analytics around staged station/body/ring evidence, improve candidate quality
signals, and add more skipped-by-default smoke coverage. Any future canonical
write path is out of scope until it has a separate design, safety review, and
test plan.
