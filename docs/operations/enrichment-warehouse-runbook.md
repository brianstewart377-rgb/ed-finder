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
export EDFINDER_STAGING_DSN="<private-staging-warehouse-dsn>"
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
    --batch-size 500 \
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

For `edsm_nightly_stations`, write-staging mode streams the source file and
flushes warehouse rows by source-record batch. The default `--batch-size` is
500 source records. The station write report is a compact summary: it keeps
counts such as `records_seen`, `raw_records_written`,
`staging_station_rows_written`, `nested_station_records_extracted`,
`batches_written`, warnings, errors, target tables, and
`canonical_writes_planned`, but it does not materialize every raw or staged
row in the final JSON output. Use dry-run mode when exact row payloads are
needed for small-file inspection.

Station staging writes are idempotent at the warehouse evidence layer. Source
runs/files and raw/station rows use deterministic keys and `source_record_hash`
upserts. If a streaming station load is interrupted after one or more batches
commit, retry the same source file with the same source adapter; committed
warehouse evidence is updated in place rather than duplicated. Do not proceed
to read-only reconciliation until the retry completes with zero errors and the
operator has verified the staged-row counts.

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

Stage 18J-Q6 documents memory-safe station warehouse loading in
`docs/colonisation-redesign/stage-18j-q6-memory-safe-warehouse-station-load.md`.
It changes the `edsm_nightly_stations` write-staging path to stream and commit
source-record batches with compact output. After Q6 merges, the next server
action is a controlled retry of the warehouse station staging load. If that
succeeds, move to read-only reconciliation artifact generation. Stage 18J-P
remains blocked until a valid reconciliation artifact exists, and Stage 18K is
not started by Q6.

Stage 18J-Q7 documents the read-only reconciliation JSON serialization fix in
`docs/colonisation-redesign/stage-18j-q7-reconciliation-json-serialization-fix.md`.
The first post-Q6 reconciliation attempt failed before artifact generation
because DB-native timestamp values were not JSON serializable. The failed
artifact was 0 bytes, canonical data was unchanged, and Stage 18J-P remained
blocked. Q7 makes report output JSON-safe before retrying the Stage 18J-Q3
read-only artifact path.

When generating reconciliation artifacts, the CLI converts DB-native report
values such as timestamps and decimals into deterministic JSON-safe values
before printing. Datetimes and dates are emitted as ISO-8601 strings; decimals
are emitted as strings. If JSON printing fails, treat the artifact as invalid,
keep Stage 18J-P blocked, and do not proceed to station-type dry-run or apply.

Stage 18J-Q8 documents the compact reconciliation summary tool in
`docs/colonisation-redesign/stage-18j-q8-compact-reconciliation-summary.md`.
It exists because the valid read-only reconciliation artifact is too large for
normal review. The Q8 tool reads an existing artifact offline, streams candidate
arrays in bounded memory, and emits a compact deterministic JSON extract with
the source basename, file size, SHA-256, schema, candidate counts,
confidence/risk distributions, coverage counts, and capped sanitized candidate
samples.

Compact summary command:

```sh
python3 apps/importer/src/reconciliation_artifact_summary.py \
    --artifact /operator/artifacts/enrichment_staging_reconciliation_YYYYMMDDTHHMMSSZ.json \
    --output /operator/artifacts/enrichment_staging_reconciliation_summary_YYYYMMDDTHHMMSSZ.json \
    --max-candidate-samples 50
```

The summary tool does not connect to a database, run reconciliation, run
station-type dry-run, or apply canonical writes. Its output sets
`safe_for_git = false` by default because production candidate samples may
still contain production identities even after payload/path sanitization. Do
not commit production summaries unless a separate review explicitly marks a
synthetic or sanitized output safe.

Stage 19A.1 documents operator command contexts in
`docs/operations/operator-command-contexts.md` and adds fail-fast operator
scripts under `scripts/operator/`. Codex/local development should edit and
validate these scripts, but Hetzner-only commands must run from the production
operator shell. The Stage 18J compact summary operator wrapper is:

```sh
cd /opt/ed-finder
scripts/operator/stage18j_run_compact_summary.sh
```

That wrapper checks the expected host, `/opt/ed-finder`, Docker Compose
availability, and the Stage 18J artifact directory before reading production
artifacts. It never runs reconciliation, station-type dry-run, or apply. The
optional canonical station count check is disabled unless the operator sets
`CHECK_CANONICAL_COUNT=yes`.

Stage 18J-Q9 documents compact summary review and station-type dry-run
readiness in
`docs/colonisation-redesign/stage-18j-q9-compact-summary-review-station-type-dry-run-readiness.md`.
The review verdict is `Ready only with strict filter`. Do not run Stage 18J-P
against the full `298177` station candidate set. Any station-type dry-run retry
must exclude ambiguous matches, source-only missing-canonical candidates,
volatile evidence, station/body association writes, fleet carriers/transient
station types, and candidates without explicit external identity proof. Missing
`station_body_name` remains a blocker for station/body-link work but must not
by itself block station-type comparison when station identity is otherwise
externally proven. A dry-run retry still requires a separate prompt, an
explicit max-row bound, recorded reconciliation checksum, compact output, and
no canonical apply.

Stage 18J-P-filter hardens the station-type dry-run eligibility code before
any future operator retry. The filter accepts only update-only station-type
candidates with external identity proof by matching `market_id` or
`edsm_station_id`; internal canonical `station_id` is never identity proof.
It emits explicit rejection counts for ambiguous identity, source-only inserts,
missing external identity, volatile evidence, transient/non-slot station types,
non-station-type changes, missing station-type deltas, and max-row exclusions.
Dry-run output keeps `canonical_writes_planned = 0`, records the input
reconciliation artifact checksum, creates no approval record, and does not run
apply. This hardening does not itself authorize or run Stage 18J-P.

Stage 18J-P-dryrun-ops adds the Hetzner-only wrapper for the future
station-type dry-run:
`scripts/operator/stage18j_run_station_type_dry_run.sh`. The wrapper calls the
shared operator environment guard, verifies the known reconciliation artifact
checksum before running, requires bounded `MAX_ROWS` with a hard first-pilot cap
of `20`, passes the compact blocked-candidate sample limit to the pilot tool,
and writes the dry-run artifact under the operator artifact directory. It never
passes apply-mode or database connection arguments, creates no approval record,
and keeps `canonical_writes_planned = 0`. This wrapper must be run only from
the Hetzner operator shell and only after a separate Stage 18J-P prompt.

The first bounded operator dry-run succeeded safely but found zero eligible
station-type update candidates because all `298177` candidates failed external
identity proof. Stage 18J-P2 adds `identity_coverage_summary` to future dry-run
artifacts so a diagnostic rerun can show whether the missing proof comes from
absent source IDs, absent canonical IDs in the reconciliation payload, ID
mismatches, system/name mismatches, or non-exact canonical match counts. The
diagnostic summary does not relax eligibility, does not create approvals, and
keeps `canonical_writes_planned = 0`. Any rerun for these diagnostics is still
a separate Hetzner/operator step and must not run apply.

Stage 18J-P3 records the follow-up identity-model finding in
`docs/colonisation-redesign/stage-18j-p3-canonical-external-station-identity-model.md`.
Canonical `stations` has no `market_id` or `edsm_station_id`; existing
`s.id AS market_id` usage is only a compatibility alias/update target; and
`station_body_links.market_id` is association-scoped, not a general external
station identity model. This is why the strict filter correctly produced zero
eligible candidates.

Stage 18J-P4 designs the external identity schema in
`docs/colonisation-redesign/stage-18j-p4-external-station-identity-schema-design.md`.
The recommended model is a separate provenance-backed
`station_external_identity` table with source run/file/hash provenance,
confidence, freshness, identity status, and visible conflict handling. Only
`confirmed` identity rows should later be eligible as canonical external
identity proof in read-only reconciliation. Do not treat warehouse source-only
evidence, station-name matches, internal `stations.id` equality, or
station/body link association evidence as station-type proof.

Stage 18J-P5 drafts that schema migration in
`sql/027_station_external_identity.sql` and documents it in
`docs/colonisation-redesign/stage-18j-p5-external-station-identity-migration-draft.md`.
The migration is additive and creates only `station_external_identity` plus
indexes and constraints. It is not applied to production by P5, does not load
or reconcile identity evidence, does not update `stations`, and does not
authorize station-type dry-run or apply. Any production schema application
requires a later explicit readiness review and approval stage.

Stage 18J-P6 records that readiness review in
`docs/colonisation-redesign/stage-18j-p6-external-identity-migration-production-readiness.md`.
The verdict is `Ready for schema-only production application`, limited to a
future operator stage that applies only `sql/027_station_external_identity.sql`.
The P6 review requires Hetzner `/opt/ed-finder` preflight checks, proof that PR
#126 is present on main, confirmation that `station_external_identity` does not
already exist, a backup/snapshot or explicit schema-only risk acceptance, no
active imports/reconciliation/apply jobs, disposable/local SQL syntax testing,
and post-apply verification that the new table is empty and `stations` is
unchanged. Applying this schema later must still not load identity data,
backfill, run station-type dry-run, or run canonical apply.

Stage 18J-P7 records the schema-only production apply closeout in
`docs/colonisation-redesign/stage-18j-p7-external-identity-schema-production-apply-closeout.md`.
The migration `sql/027_station_external_identity.sql` has been applied on
Hetzner. `station_external_identity` exists with the expected constraints and
indexes, its row count is `0`, and the recorded canonical `stations` count
stayed unchanged at `284763`. No identity evidence was loaded, no imports,
reconciliation, summarizer, station-type dry-run, or canonical apply were run,
and no station-type data changed. The table is present but empty, so
station-type dry-run remains blocked until confirmed external identity evidence
is loaded and integrated into read-only reconciliation.

Stage 18J-P8 designs the identity evidence loader/reconciliation workflow in
`docs/colonisation-redesign/stage-18j-p8-external-identity-evidence-loader-reconciliation-design.md`.
Use existing `edsm_nightly_stations` warehouse evidence as the first candidate
source, but produce a read-only identity candidate artifact before writing
anything to `station_external_identity`. Candidate confirmation must not rely
on name-only matching, internal `stations.id` equality, or source-only evidence
by default. Future identity loading must write only the identity table, preserve
source run/file/hash provenance, keep conflicts visible, leave `stations` and
`station_type` unchanged, and keep station-type dry-run blocked until confirmed
identity coverage is reviewed.

Stage 18J-P9 adds that read-only artifact generator in
`apps/importer/src/station_external_identity_candidates.py` and documents it in
`docs/colonisation-redesign/stage-18j-p9-readonly-external-identity-candidate-artifact.md`.
It requires an explicit read-only DSN plus `--source-run-key`, supports
`--source-file-key`, `--limit`, `--sample-limit`, `--json`, and `--output`, and
rejects write/apply/load flags. The artifact is review-only: it writes nothing
to `station_external_identity`, does not update `stations` or `station_type`,
and must not be combined with imports, reconciliation, station-type dry-run, or
canonical apply.

Stage 18J-P10 reviews the first Hetzner read-only external identity candidate
artifact in
`docs/colonisation-redesign/stage-18j-p10-external-identity-candidate-artifact-review.md`.
The artifact
`station_external_identity_candidates_20260603T002504Z.json` inspected
`298177` staged EDSM station rows and reported `261938`
`confirmed_candidate` rows, `258` conflicting rows, and `35981`
rejected/source-only rows. It kept `dry_run`, `read_only`, and `report_only`
true, with `canonical_writes_planned = 0`, `station_type_writes_planned = 0`,
and `identity_rows_written = 0`. The verdict is `Ready only for bounded
identity load dry-run`; the next operator step must be a bounded no-write
load-plan artifact, not a bulk insert into `station_external_identity`.

Stage 18J-P11 adds that bounded no-write load-plan artifact generator in
`apps/importer/src/station_external_identity_load_plan.py` and documents it in
`docs/colonisation-redesign/stage-18j-p11-bounded-external-identity-load-plan-artifact.md`.
The tool requires a read-only DSN, explicit `--source-run-key`, optional
`--source-file-key`, and explicit `--max-rows`; it rejects `--max-rows` above
`20` for the first bounded plan. It emits
`station_external_identity_load_plan/v1`, plans only eligible
`confirmed_candidate` rows, preserves source run/file/hash provenance, rejects
write/apply/load flags, and keeps `identity_rows_written = 0`. This is still a
review artifact and must not be combined with identity evidence load,
reconciliation, summarizer, station-type dry-run, or canonical apply.

Stage 18J-P-OPT documents the identity evidence execution board in
`docs/colonisation-redesign/stage-18j-p-identity-evidence-execution-board.md`.
Use it as the remaining Stage 18J-P tracker. Repo work may be bundled into
larger chunks when the bundle has one safety boundary and includes tool, tests,
operator script, docs, and roadmap updates. Hetzner actions remain tiny:
pre-check row counts, run a guarded script, output artifact path/checksum and
compact summary, post-check row counts, and explicitly confirm no forbidden
actions. Never combine identity load with station-type dry-run, never combine
station-type dry-run with canonical apply, and never run apply without a
separate approval packet.

Stage 18J-P12/P13 records the bounded no-write identity load-plan review and
adds the offline planned-row review packet generator in
`apps/importer/src/station_external_identity_review_packet.py`. The
Hetzner-only wrapper is
`scripts/operator/stage18j_run_identity_review_packet.sh`. It calls the
operator environment guard, verifies the exact load-plan artifact SHA-256
`3da39530223f92e89d7129d447944d39199b6510eee473ba1e84ceeb168c9db1`, writes
the review packet under
`/var/lib/ed-finder/operator-artifacts/stage-18j`, applies mode `600`, and
prints the packet path, checksum, and summary fields. It does not source DB
environment, connect to Postgres, load identity evidence, run imports,
reconciliation, summarizer, station-type dry-run, approval-record creation, or
canonical apply. The verdict remains
`Ready only after planned-row manual review`.

Stage 18J-P13A hardens that review packet contract after the first offline
Hetzner packet showed correct safety fields but non-self-contained
`manual_review_items`. New packets must keep top-level `planned_rows` and must
also embed the exact planned row plus non-empty boolean `checks` inside each
manual review item. The wrapper summary now validates and prints the planned
row count, manual review item count, and whether the first review item has
`planned_row` and `checks`. After P13A merges, rerun only the offline guarded
review-packet wrapper; do not load identity evidence or run reconciliation,
summarizer, station-type dry-run, approval-record creation, or canonical
apply.

Stage 18J-P14 adds controlled external identity load tooling in
`apps/importer/src/station_external_identity_loader.py` and a dry-run-only
operator wrapper in `scripts/operator/stage18j_run_identity_load_dry_run.sh`.
The wrapper validates the verified review packet
`station_external_identity_review_packet_20260603T110848Z.json` with expected
SHA-256 `8cf118d552e6bc35d23ab302d9e1020092385b372729dbb9b2bae5cd5f0758b6`,
emits `station_external_identity_load_execution_plan/v1`, and prints explicit
no-write/no-station-type/no-apply confirmation. It does not connect to the
database in dry-run mode. Any future `--write-reviewed` run requires a separate
`station_external_identity_load_approval_allowlist/v1` artifact tied to the
exact review packet SHA-256 and must be a later, explicitly approved operator
action. P14 does not add a production write operator script.

Stage 18J-P14B records the first controlled load dry-run. The dry-run selected
`20` review items and `20` plan rows from
`station_external_identity_review_packet_20260603T110848Z.json`, verified
review packet SHA-256
`8cf118d552e6bc35d23ab302d9e1020092385b372729dbb9b2bae5cd5f0758b6`, kept
`canonical_writes_planned = 0`, `station_type_writes_planned = 0`, and
`identity_rows_written = 0`, and left `station_external_identity` at `0` rows.
The verdict is `Ready only after approval allowlist artifact`. Before any
write-reviewed identity load, create and review a separate
`station_external_identity_load_approval_allowlist/v1` artifact for exact
review item IDs or plan row IDs. Do not treat that allowlist as canonical apply
approval.

Stage 19A documents the warehouse artifact taxonomy and chunked roadmap in
`docs/colonisation-redesign/stage-19a-warehouse-artifact-taxonomy-and-chunked-roadmap.md`.
Use domain-qualified artifact families for stations, bodies, rings,
station/body links, markets, services, economies, colonisation, freshness,
coverage, analytics, and future write plans. Do not mix lifecycle steps in one
artifact: source inventory comes before load, load before reconciliation,
reconciliation before compact summary, compact summary before dry-run, dry-run
before approval packet, and approval packet before any manual apply.

Preferred naming patterns:

```text
warehouse_<domain>_load_<timestamp>.json
enrichment_staging_reconciliation_<domain>_<timestamp>.json
reconciliation_compact_summary_<domain>_<timestamp>.json
warehouse_<domain>_freshness_status_<timestamp>.json
warehouse_operator_status_<timestamp>.json
canonical_write_plan_<domain>_<timestamp>.json
```

Scheduler work must stay disabled by default until a later approved stage, and
scheduler jobs must never run canonical apply.

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

If a station staging load is interrupted:

- Do not run reconciliation against an incomplete or failed load.
- Confirm the canonical station count did not change.
- Confirm warehouse row counts and the compact loader output before retrying.
- Retry only the warehouse staging load with the same source file/source
  adapter and explicit staging flags.
- Treat the retry as a staging-only operation. It must not run station-type
  dry-run, reconciliation apply, canonical apply, or scheduler work.

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
