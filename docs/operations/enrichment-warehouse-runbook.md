# Enrichment Warehouse Runbook

This runbook covers the Stage 18C operator workflow for the offline enrichment
warehouse. It explains how to inspect local snapshots, optionally load them into
the warehouse staging tables, and produce read-only reconciliation and signal
reports.

It does not describe a canonical apply workflow. The warehouse stores source
evidence and report output only. Warehouse evidence is not canonical truth.

## Overview

The current warehouse path is:

```text
offline snapshot file
-> deterministic dry-run report
-> optional gated staging-table load
-> read-only comparison with canonical ED-Finder tables
-> report-only reconciliation, coverage, confidence/risk, and signals
```

Snapshots come from operator-provided offline exports, such as local EDSM-style
station snapshots or local EDSM-style body/ring snapshots. The current scripts
do not fetch EDSM, Spansh, EDDN, or any other live API. Store real snapshots in
an operator-managed location outside git, or in a local ignored workspace. Do
not commit large snapshots, private host paths, DSNs, API keys, or credentials.
The repository fixtures under `tests/fixtures/` are for deterministic examples
and CI only.

Current supported source adapters:

| Source | Input file | Current purpose |
|---|---|---|
| `edsm_nightly_stations` | Local `.json` or `.json.gz` station snapshot. JSON array, NDJSON, small object wrapper with a `stations` array, or nested EDSM system records with a `stations` array. | Station evidence dry-run, staging load, staged-row summary, reconciliation. |
| `edsm_nightly_bodies` | Local `.json` or `.json.gz` body records with optional `rings` arrays. JSON array or NDJSON. | Body/ring evidence dry-run, staging load, staged-row summary, reconciliation. |

The scripts preserve source payloads and future/unknown fields in raw evidence.
Missing evidence remains unknown. Missing ring arrays are reported as
`unknown_not_false`; they are not proof that a body has no rings. Source-only
ring evidence is not trusted local ring truth unless later reconciled to trusted
`body_rings` evidence.

Nested EDSM system station snapshots are supported only for station extraction.
The loader preserves each full system record in `enrichment_raw_records`,
extracts deterministic station staging rows with station-specific source
hashes, links them back to the parent raw system hash in provenance, and
reports nested `bodies` collections as raw-only unsupported-source-shape
warnings. Nested bodies do not populate body/ring staging tables through the
station source path and do not become canonical truth.

## Safety Model

Safe by default:

- `apps/importer/src/enrichment_snapshot_loader.py` is dry-run only and has no
  database, network, Docker, or canonical write path.
- `apps/importer/src/enrichment_staging_db_loader.py` dry-run mode is also
  no-write.
- `--check-staging-schema`, `--report-staged-run`, and
  `--report-reconciliation` are read-only DB modes.
- Reconciliation and analytics output always reports
  `canonical_writes_planned = 0`.

Explicitly gated staging writes:

- `--write-staging` requires `--dsn` and `--confirm-staging-db`.
- Staging writes target only:
  `enrichment_source_runs`, `enrichment_source_files`,
  `enrichment_raw_records`, `staging_edsm_stations`,
  `staging_edsm_bodies`, and `staging_body_rings`.
- Use a staging or test enrichment DSN only. Do not point this at canonical
  production app tables.

Never use the warehouse scripts to write canonical production tables:

- `systems`
- `stations`
- `bodies`
- `body_rings`
- `body_scan_facts`
- `station_body_links`

The canonical flags `--apply`, `--write`, and `--commit` fail closed. Do not add
workarounds or SQL snippets that bypass that boundary.

## Inputs

Use fixture inputs first when checking commands:

- `tests/fixtures/edsm_station_snapshot.json`
- `tests/fixtures/edsm_body_ring_snapshot.json`

Use larger local snapshots only after the fixture commands are boring. Keep
operator snapshots outside git and name them by source and date, for example:

```text
<operator-snapshot-root>/edsm/stations-YYYY-MM-DD.json.gz
<operator-snapshot-root>/edsm/bodies-YYYY-MM-DD.json.gz
```

For large files, start with `--limit` so skipped rows, warning counts, source
metadata, and staged-row counts are easy to inspect before a full dry-run.

`distanceToArrival` is volatile evidence. Reports retain it for review and may
warn about differences, but it must not churn canonical
`stations.distance_from_star` or body distance fields.

## Dry-Run Commands

Fixture station snapshot dry-run:

```sh
python3 apps/importer/src/enrichment_snapshot_loader.py \
    --source-file tests/fixtures/edsm_station_snapshot.json \
    --source edsm_nightly_stations \
    --json
```

Fixture body/ring snapshot dry-run:

```sh
python3 apps/importer/src/enrichment_snapshot_loader.py \
    --source-file tests/fixtures/edsm_body_ring_snapshot.json \
    --source edsm_nightly_bodies \
    --json
```

Larger local snapshot dry-run with a limit:

```sh
python3 apps/importer/src/enrichment_snapshot_loader.py \
    --source-file "$EDSM_STATION_SNAPSHOT" \
    --source edsm_nightly_stations \
    --limit 1000 \
    --json
```

For body/ring snapshots, use the body source adapter:

```sh
python3 apps/importer/src/enrichment_snapshot_loader.py \
    --source-file "$EDSM_BODY_SNAPSHOT" \
    --source edsm_nightly_bodies \
    --limit 1000 \
    --json
```

A good dry-run has:

- `schema_version = "enrichment_snapshot_load_plan/v1"`
- `dry_run = true`
- expected `records_seen`, `raw_records`, and staged-row counts
- for nested system station snapshots, expected
  `nested_station_collections` and `nested_station_records_extracted`
- `source_format_version = "json_snapshot_stream/v1"` and the expected
  `record_stream_shape`
- `source_timestamp_summary` and `source_freshness_summary` matching the
  intended snapshot age
- `canonical_writes_planned = 0`
- no unexpected skipped-row reasons
- no source-file or unsupported-source errors

Snapshot-normalisation fields to inspect before staging loads:

- `source_run.metadata` and `source_file.metadata` capture the adapter version,
  source format/version, record stream shape, and source timestamp summary.
- `source_file.source_updated_at` is the latest source timestamp observed in
  raw mapping records, when present. Missing timestamps stay unknown and are
  counted in `source_timestamp_summary`.
- `skipped_row_reasons` and `skipped_row_reason_distribution` explain
  malformed records, unsupported nested source shapes, and invalid station,
  body, or ring rows.
- `source_record_duplicate_groups` reports exact duplicate source payloads by
  `source_record_hash`. This is a dry-run/report signal; explicit staging
  writes still use warehouse upsert keys and never imply canonical truth.
- `conflicts` reports repeated source identities with conflicting payload
  hashes as `duplicate_source_identity_conflict`. Treat these as blockers for
  operator review.
- Body/ring reports include `ring_array_evidence`. Missing ring arrays remain
  `unknown_not_false`; empty arrays are source evidence only and not a
  canonical no-rings conclusion; staged ring rows remain source-only evidence.

Warnings that block moving to staging load:

- required identity fields missing across most records
- unexpected `record_is_not_object` or malformed JSON patterns
- unsupported source adapter
- unsupported nested source shape that is not the supported nested system
  station form. Nested `bodies` on a supported station snapshot are warning
  evidence only and should be reviewed before staging load.
- `duplicate_source_identity_conflict`
- non-array `rings` fields or malformed ring rows in body/ring snapshots
- remote URL used as `--source-file`
- surprising `distance_to_arrival_classification` values; current
  `distanceToArrival` should remain volatile

## Staging DB Commands

Set the DSN only in your shell or secret manager. Do not paste real DSNs into
docs, PRs, issue comments, or committed files.

```sh
export EDFINDER_STAGING_DSN='postgresql://USER:PASSWORD@HOST:PORT/DBNAME'
```

Read-only schema/preflight check:

```sh
python3 apps/importer/src/enrichment_staging_db_loader.py \
    --check-staging-schema \
    --dsn "$EDFINDER_STAGING_DSN" \
    --source edsm_nightly_stations \
    --json
```

For body/ring warehouse tables:

```sh
python3 apps/importer/src/enrichment_staging_db_loader.py \
    --check-staging-schema \
    --dsn "$EDFINDER_STAGING_DSN" \
    --source edsm_nightly_bodies \
    --json
```

A good preflight has `ok = true`, empty `missing_tables`, empty
`missing_columns`, and the expected target warehouse tables. If it returns
`ok = false`, stop and fix the staging schema before loading.

Staging-only DB load with explicit confirmation:

```sh
python3 apps/importer/src/enrichment_staging_db_loader.py \
    --source-file "$EDSM_STATION_SNAPSHOT" \
    --source edsm_nightly_stations \
    --limit 1000 \
    --write-staging \
    --dsn "$EDFINDER_STAGING_DSN" \
    --confirm-staging-db \
    --json
```

For body/ring staging:

```sh
python3 apps/importer/src/enrichment_staging_db_loader.py \
    --source-file "$EDSM_BODY_SNAPSHOT" \
    --source edsm_nightly_bodies \
    --limit 1000 \
    --write-staging \
    --dsn "$EDFINDER_STAGING_DSN" \
    --confirm-staging-db \
    --json
```

A good staging load has:

- `dry_run = false`
- `summary.write_mode = "staging_only"`
- `summary.staging_writes_enabled = true`
- non-zero `raw_records_written` and source-specific staged row counts when the
  input contains valid records
- target tables limited to the warehouse table family
- `summary.canonical_writes_planned = 0`

Staging-load warnings that block progress:

- schema preflight failure
- writes reported to any table outside the warehouse table family
- unexpected rollback or non-zero `errors`
- high skipped-row counts caused by malformed source shape
- source-run or source-file metadata that does not match the intended snapshot

## Reconciliation Reports

Read-only reconciliation compares staged warehouse evidence with canonical
tables and emits candidate sections. It does not write either warehouse or
canonical data.

Read-only reconciliation report:

```sh
python3 apps/importer/src/enrichment_staging_db_loader.py \
    --report-reconciliation \
    --dsn "$EDFINDER_STAGING_DSN" \
    --source edsm_nightly_stations \
    --source-run-key "$SOURCE_RUN_KEY" \
    --source-file-key "$SOURCE_FILE_KEY" \
    --limit 1000 \
    --json
```

Use `--source edsm_nightly_bodies` for body/ring reconciliation, or omit
`--source` to include all currently supported staged source families.
`--source-run-key` and `--source-file-key` are optional for reconciliation but
recommended for repeatable operator review.

Important sections:

- `station_candidates`: staged station evidence compared with canonical
  station rows.
- `body_candidates`: staged body evidence compared with canonical body rows.
- `ring_candidates`: staged ring evidence compared with trusted local ring
  rows.
- `station_body_association_candidates`: report-only station/body-name
  support, unresolved, missing, or ambiguous states. It is not a
  `station_body_links` write plan.
- `source_coverage_summary`: entity coverage, source files/runs, volatile
  warning counts, and ring evidence state.
- `warehouse_coverage_report`: Stage 18E operator review coverage. It shows
  systems with station evidence, systems with only body/ring evidence, trusted
  ring evidence, unknown ring evidence, explicit trusted no-ring scan evidence,
  confirmed/inferred/unresolved station-body links, stale or undated evidence,
  malformed/skipped source rows, duplicate source-record hashes, source
  identity conflicts, high-value systems needing better evidence, and source
  type/source-format coverage.
- `confidence_risk_summary`: confidence, evidence quality, identifier quality,
  reconciliation state, risk-class, review-classification, source-freshness
  impact, future-review-marker, and risk-flag distributions. Stage 18F
  confidence fields explain why a candidate is confirmed, inferred/verify,
  unresolved, source-only, stale, volatile, blocked, report-only, or unknown;
  they are not canonical eligibility or write instructions.

Candidate actions to expect:

| Action | Meaning |
|---|---|
| `no_change` | One canonical row matched and stable staged fields agree. |
| `candidate_update` | One canonical row matched, but stable staged fields differ. Report-only. |
| `candidate_insert_missing_canonical` | No canonical row matched. Treat as review evidence, not an insert instruction. |
| `ambiguous_match` | More than one canonical row matched. Manual review required. |
| `insufficient_evidence` | Source identifiers are too sparse for a conclusion. |

Warnings that block any later stage:

- `ambiguous_match`
- `insufficient_evidence`
- `volatile_source_evidence` where an operator expected a stable-field change
- `source_only_association`, `ambiguous_staged_body_evidence`,
  `missing_staged_body_evidence`, or `missing_station_body_name`
- non-zero `warehouse_coverage_report.operator_review.needs_attention_buckets`
  values that the operator cannot explain from the source file and staging
  filters
- any non-zero `errors`
- any report that omits `canonical_writes_planned = 0`
- confidence/risk output that labels a candidate as a future canonical review
  candidate without also keeping `auto_promote_to_canonical = false`

Coverage report rules:

- `warehouse_coverage_report` is deterministic and report-only. It is not a
  write plan and must keep `canonical_writes_planned = 0`.
- Missing station evidence means no staged station evidence for a system that
  does have staged body or ring evidence in the current report scope; it is not
  a galaxy-wide absence claim.
- Trusted ring evidence requires matched local `body_rings` rows with trusted
  association status.
- Source-only ring rows remain source-only and do not confirm ring truth.
- Explicit no-ring coverage is counted only from trusted local scan facts such
  as `body_scan_facts.is_ringed = false`. Missing arrays and empty source
  arrays remain review evidence, not canonical no-rings.
- Stale or undated coverage uses source timestamp/freshness fields only; the
  report does not apply a wall-clock age threshold so output stays
  deterministic and offline-safe.

## Staged-Row Summary

Staged-row summaries are read-only and require a source run key.

```sh
python3 apps/importer/src/enrichment_staging_db_loader.py \
    --report-staged-run \
    --dsn "$EDFINDER_STAGING_DSN" \
    --source-run-key "$SOURCE_RUN_KEY" \
    --source-file-key "$SOURCE_FILE_KEY" \
    --source edsm_nightly_stations \
    --json
```

A good staged-row summary has:

- `schema_version = "enrichment_staged_rows_summary/v1"`
- `dry_run = true`
- expected `source_run` and `source_files`
- expected raw/staged counts for the source family
- `warning_records = 0` and `error_records = 0` for clean fixture-sized loads
- target tables limited to the source-specific warehouse tables

## Analytics And Signals

Analytics and signals currently come embedded in the reconciliation report.
There is no separate analytics CLI flag.

Run the reconciliation command and inspect these sections:

```sh
python3 apps/importer/src/enrichment_staging_db_loader.py \
    --report-reconciliation \
    --dsn "$EDFINDER_STAGING_DSN" \
    --source-run-key "$SOURCE_RUN_KEY" \
    --json
```

Signal sections:

- `analytics_signals`: quality signals such as missing identifiers, ambiguous
  matches, records without canonical matches, rings without body matches, and
  high warning rates.
- `colonisation_signals`: conservative review candidates grouped by system.
  These are advisory `needs_review` records, not planner truth.
- `mission_density_signals`: station/body/ring evidence counts by system,
  useful for seeing where source density is high or sparse.

A good signal report is deterministic, has `dry_run = true`, has
`canonical_writes_planned = 0` in signal summaries where present, and keeps
review flags as review flags rather than promotion instructions.

## Status Publishing

Stage 18A's station enrichment status JSON is a separate read-only operator
status path for the guarded station enrichment job. It is useful context beside
warehouse runs, but it is not the warehouse loader and it does not publish
warehouse reconciliation reports.

Safe status publishing path:

```sh
python3 scripts/station_enrichment_status.py --json \
    > /data/logs/station-enrichment-status.json
```

The API reads the artifact configured by:

```text
ENRICHMENT_STATUS_JSON_PATH=/data/logs/station-enrichment-status.json
```

The status helper reads local files only. It does not call EDSM, connect to the
database, invoke Docker, or mutate state. Missing status must stay unavailable,
not zero.

Stage 18G adds a second read-only Admin tab panel for warehouse status. The API
does not generate reports from a request. Operators must publish a reviewed
warehouse reconciliation/status JSON artifact, usually the output of
`--report-reconciliation --json`, to a path mounted into the API container:

```text
ENRICHMENT_WAREHOUSE_STATUS_JSON_PATH=/data/logs/warehouse-status.json
```

The warehouse status endpoint sanitizes the artifact to file names, schema
versions, source identifiers, coverage counts, unresolved/risky/stale/skipped
counts, and canonical-safety flags. It hides full filesystem paths and treats
missing, invalid, unset, or oversized artifacts as unavailable instead of zero.
It does not query the warehouse database, invoke Docker, call live APIs, run
importer scripts, or write canonical data.

Stage 18H adds a read-only warehouse-to-planner evidence bridge in the Colony
Planner. It presents warehouse evidence as report-only, never canonical truth.
Because this warehouse status artifact is admin-gated and aggregate-only (it has
no per-`system_id64` rows), the planner card cannot safely link evidence to a
system yet and defaults to a safe unavailable/unknown state. It adds no backend
endpoint, makes no live calls, and changes no planner, Build Plan, role,
observed-evidence, validation, scoring, Preview, optimiser, or canonical state.
The future per-system artifact contract is documented in
`docs/colonisation-redesign/stage-18h-warehouse-planner-evidence-bridge.md`.

Stage 18I documents the future canonical-write design review in
`docs/colonisation-redesign/stage-18i-canonical-write-design-review.md`. It is
design-only and does not authorize any canonical apply workflow. Until Stage
18I.5 and a later approved Stage 18J pilot exist, warehouse evidence and
reconciliation candidates remain report-only.

Stage 18I.5 documents the database-boundary decision in
`docs/colonisation-redesign/stage-18i5-warehouse-database-boundary-review.md`.
It recommends a separate `edfinder_enrichment` warehouse database on the same
Postgres stack if feasible, with a future path to a separate instance. This
runbook still describes the current report-only workflow; no database creation,
migration, permission, or canonical apply step is added by Stage 18I.5.

Stage 18T documents the canonical safety test environment in
`docs/colonisation-redesign/stage-18t-canonical-safety-test-environment.md`.
It adds a dedicated CI gate, a local runner, and disposable Postgres rehearsal
coverage for the guarded Stage 18J station type apply path. This does not
authorize production apply or production artifact creation.

Stage 18J-Q documents production reconciliation artifact readiness in
`docs/colonisation-redesign/stage-18j-q-production-reconciliation-artifact-readiness.md`.
It defines the required `enrichment_staging_reconciliation/v1` artifact
contract, read-only DSN checks, report-only command path, sanitisation checks,
and blockers before Stage 18J-P may generate a station-type production dry-run.

Stage 18J-Q2 documents the exact read-only production reconciliation artifact
generation plan in
`docs/colonisation-redesign/stage-18j-q2-readonly-production-reconciliation-plan.md`.
It names the later `--report-reconciliation` command, required source scope,
read-only DSN proof, output handling, contract checks, and stop conditions.

Stage 18J-Q3 records the first attempted artifact-generation pass in
`docs/colonisation-redesign/stage-18j-q3-readonly-production-reconciliation-artifact.md`.
It stopped before any production-connected command because the verified
read-only DSN, source run/file scope, read-only session option, and
operator-managed output path were not available.

Stage 18J-Q4 documents the operator access packet in
`docs/operations/stage-18j-q4-operator-access-packet.md`. It defines the
missing variables, read-only DSN requirements, source run/file approval, safe
artifact directory requirements, mandatory `PGOPTIONS`, redacted command
template, secret handling, and sign-off checklist needed before retrying
Stage 18J-Q3.

Stage 18J-Q4b records the local/operator note for the missing
`EDFINDER_WAREHOUSE_READ_DSN` in
`docs/operations/stage-18j-q4b-readonly-warehouse-dsn-operator-note.md`.

Stage 18J-Q4c documents the provisioning plan for a dedicated
read-only/report-only warehouse DSN in
`docs/operations/stage-18j-q4c-readonly-warehouse-dsn-provisioning-plan.md`.
It is docs/ops planning only and does not create roles, change deployment
config, run reconciliation, generate artifacts, or authorize apply.

Stage 18J-Q5 documents nested EDSM station snapshot support in
`docs/colonisation-redesign/stage-18j-q5-nested-edsm-station-snapshot-support.md`.
It hardens the local loader for `/data/dumps/galaxy_stations.json.gz`-style
nested system records without using production data. Stage 18J-Q3 remains
blocked until this support is merged and a separate explicitly approved
production staging load is retried; no production load, reconciliation, or
apply is authorized by Q5.

## Optional Postgres Smoke Tests

These tests are skipped by default. They write only to warehouse staging tables
and clean up after themselves, but they still require a disposable staging/test
database.

```sh
EDFINDER_STAGING_TEST_DSN="$EDFINDER_STAGING_DSN" \
EDFINDER_CONFIRM_STAGING_TEST_DB=yes \
.venv/bin/pytest \
    tests/test_enrichment_staging_db_loader_postgres_smoke.py \
    tests/test_enrichment_body_ring_staging_loader_postgres_smoke.py \
    tests/test_enrichment_staging_reconciliation_postgres_smoke.py \
    -q
```

Do not run these against a production canonical database. The confirmation
variable means the operator has verified the DSN is staging/test only.

## Troubleshooting

If dry-run fails:

- Check that `--source-file` is a local file path, not a URL.
- Check that the source is exactly `edsm_nightly_stations` or
  `edsm_nightly_bodies`.
- Run with a small `--limit` and inspect `skipped_rows`.
- Treat missing evidence as unknown; do not patch fixture/source values to
  force false conclusions.

If schema preflight fails:

- Confirm migration `sql/026_enrichment_staging_foundation.sql` has been
  applied to the staging/test warehouse database.
- Confirm `--source` matches the table family you are checking.
- Do not proceed to `--write-staging` until `ok = true`.

If reconciliation shows conflicts or warnings:

- Ambiguous matches and insufficient identifiers block progress.
- Volatile distance warnings are expected review evidence when only
  `distanceToArrival` changed; they are not canonical update candidates.
- Source-only ring evidence is review evidence until trusted local
  `body_rings` rows support it.
- Station/body association candidates remain report-only until a separate
  canonical write design exists.

## What Not To Do

- Do not wire these commands into a production scheduler from this stage.
- Do not run live EDSM/API crawls from the warehouse path.
- Do not invoke Docker from UI/API code for this workflow.
- Do not change planner, search, scoring, optimiser, Simulation Preview,
  Suggested Build, or role behavior from warehouse report output.
- Do not use report candidates as canonical write instructions.
- Do not coerce missing rings, missing body links, missing distances, or sparse
  source records to false or zero.
- Do not paste private DSNs, API keys, or host-specific paths into reports or
  committed docs.

## Future DB Boundary Notes

Stage 18I.5 reviewed the database boundary. The preferred future direction is
to move the warehouse from same-database staging tables toward a separate
`edfinder_enrichment` database on the same Postgres server/stack if feasible,
with a path to a separate instance later if operational load or retention risk
requires it.

Until that architecture is implemented, treat DSNs and paths in this runbook as
current operator examples. Future work may rename the warehouse DSN variable,
move the warehouse schema, or require different read-only access patterns for
canonical comparison. The hard boundary remains unchanged: warehouse data is
evidence and reports, not canonical truth.
