# Stage 19D — Source-Run Ledger Design

## Purpose

Stage 19D defines the durable source-run ledger for Data Warehouse Utopia.

The source-run ledger is the foundation for safe auto-import. Before ED-Finder imports anything automatically, every run must be identifiable, auditable, idempotent, and tied to artifacts.

No DB writes, imports, migrations, or canonical apply are approved by this design document.

## Why this exists

Stage 19A showed that ED-Finder already has large data tables and some source-run/enrichment scaffolding.

Stage 19B defined the warehouse architecture.

Stage 19C defined the source/domain vocabulary.

Stage 19D now defines the first concrete contract the implementation should build or harden: the source-run ledger.

## Ledger responsibilities

The source-run ledger must answer:

- what source was imported?
- what domain was imported?
- what exact input was used?
- what hash identifies that input?
- when did the run start and finish?
- did it succeed, fail, get rejected, or get superseded?
- how many rows were read, staged, rejected, or skipped?
- what artifact proves the run result?
- what code version performed the run?
- was the run operator-triggered or scheduler-triggered?
- did the run touch canonical data?

## Required table concept

The implementation should either create or harden a table equivalent to `source_runs`.

Recommended canonical name:

- `source_runs`

Acceptable existing equivalent if already present and compatible:

- `enrichment_source_runs`

If an existing table is reused, Stage 19D implementation must document the mapping from this contract to the existing columns.

## Source run core fields

| Field | Type idea | Required | Notes |
|---|---|---:|---|
| `id` | bigserial/uuid | yes | Internal primary key. |
| `source_run_key` | text | yes | Stable external key for artifacts and staging rows. Unique. |
| `source_name` | text/enum | yes | Example: `edsm`, `spansh`, `inara`, `operator_artifact`. |
| `source_category` | text/enum | yes | From Stage 19C category contract. |
| `domain` | text/enum | yes | Example: `stations`, `systems`, `bodies`, `rings`. |
| `import_scope` | text/enum | yes | Example: `raw_capture_only`, `staging_only`, `warehouse_fact_refresh`. |
| `status` | text/enum | yes | planned/running/succeeded/failed/rejected/superseded/cancelled. |
| `source_uri` | text | maybe | File path, API endpoint, URL, or logical source key. |
| `source_input_sha256` | text | yes for file/snapshot | Hash of input file/snapshot/manifest. |
| `source_manifest_sha256` | text | maybe | For very large sources. |
| `started_at` | timestamptz | yes | Start timestamp. |
| `finished_at` | timestamptz | maybe | Null while running. |
| `duration_ms` | integer | maybe | Useful for monitoring. |
| `git_commit_sha` | text | yes | Code version that performed run. |
| `importer_name` | text | yes | Import tool name. |
| `importer_version` | text | yes | Import tool version. |
| `trigger_context` | text | yes | operator/scheduler/test/manual. |
| `artifact_path` | text | yes when complete | Output artifact path. |
| `artifact_sha256` | text | yes when complete | File SHA. |
| `artifact_integrity_sha256` | text | yes when complete | Canonical JSON integrity hash when applicable. |
| `rows_read` | integer | yes | Count read from source. |
| `rows_staged` | integer | yes | Count written to staging. |
| `rows_rejected` | integer | yes | Count rejected. |
| `rows_skipped` | integer | yes | Count skipped/idempotent duplicates. |
| `error_code` | text | maybe | Structured failure reason. |
| `error_summary` | text | maybe | Secret-safe summary. |
| `created_at` | timestamptz | yes | DB row creation time. |
| `updated_at` | timestamptz | yes | DB row update time. |

## Status contract

| Status | Meaning |
|---|---|
| `planned` | Run record exists but work has not started. |
| `running` | Run is currently active. |
| `succeeded` | Run completed and produced an artifact. |
| `failed` | Run errored and recorded failure details. |
| `rejected` | Source/input validation failed before staging. |
| `superseded` | A newer successful run replaced this for latest evidence. |
| `cancelled` | Operator or scheduler stopped the run. |

## Failure code contract

Initial failure codes:

- `missing_source_hash`
- `source_download_failed`
- `source_schema_mismatch`
- `source_too_large`
- `source_parse_failed`
- `row_validation_failed`
- `duplicate_active_run`
- `db_connection_failed`
- `staging_write_failed`
- `artifact_write_failed`
- `postcheck_failed`
- `operator_cancelled`

## Idempotency rules

1. `source_run_key` must be unique.
2. A source/domain pair should not have more than one active `running` run.
3. File/snapshot imports must record `source_input_sha256`.
4. Very large imports may record a manifest hash instead of full raw retention.
5. Re-running the same input should not duplicate staging facts.
6. A successful import must produce an artifact.
7. A failed import must produce a failure artifact or error summary.

## Staging linkage

Every staging table should carry enough source-run lineage to trace rows back to a run.

Recommended staging columns:

- `source_run_key`
- `source_name`
- `source_record_hash`
- `source_file_key` or `source_uri`
- `source_updated_at` where available
- `first_seen_at`
- `last_seen_at`
- `created_at`
- `updated_at`

## Artifact contract

Every source run should produce a JSON artifact with:

- schema version;
- generated timestamp;
- source run key;
- source name;
- domain;
- import scope;
- git commit SHA;
- input hash;
- rows read/staged/rejected/skipped;
- status;
- safety summary;
- artifact integrity hash.

## Scheduler contract

Scheduler-triggered imports must include:

- trigger context: `scheduler`;
- scheduler name;
- lock acquisition result;
- previous active-run check;
- log file path;
- artifact path;
- explicit no-canonical-write confirmation.

## Canonical boundary

Source-run imports may write to:

- source-run ledger;
- raw/source retention tables;
- staging tables;
- warehouse fact tables;
- import artifacts.

Source-run imports must not directly write to canonical tables.

Canonical-impacting changes require a separate controlled lane:

dry-run artifact -> review packet -> approval allowlist -> bounded write-reviewed execution -> post-write verification -> docs closeout

## Initial implementation recommendation

Stage 19D implementation should start by inspecting existing `enrichment_source_runs` and related tables.

If compatible, harden and document them rather than creating duplicate ledger tables.

If not compatible, create a new `source_runs` table and migration.

Implementation should be split into:

1. read-only compatibility audit;
2. schema/migration proposal;
3. tests;
4. dry-run artifact;
5. controlled migration only if needed.

## Acceptance criteria

Stage 19D design is complete when:

- source-run fields are defined;
- statuses are defined;
- failure codes are defined;
- staging linkage requirements are defined;
- artifact contract is defined;
- canonical boundary is explicit;
- implementation path is clear.

No DB writes, imports, migrations, or canonical apply are approved by this document.
