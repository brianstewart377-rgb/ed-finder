# Stage 19E — source_runs Schema Implementation Plan

## Purpose

Stage 19E turns the Stage 19D source-run ledger design and compatibility audit into a concrete implementation plan.

Stage 19D compatibility audit concluded:

- `existing_usable_ledger_candidate`: `False`
- `recommended_decision`: `create_or_extend_source_runs_contract`

Therefore ED-Finder should implement a proper `source_runs` ledger contract rather than pretending the current enrichment/source-run scaffolding is sufficient.

No DB writes, imports, migrations, or canonical apply are approved by this document.

## Implementation decision

Preferred implementation path:

1. Create a new durable `source_runs` table as the canonical import-run ledger.
2. Keep existing `enrichment_source_runs`, `enrichment_source_files`, and `enrichment_raw_records` as legacy/enrichment-specific tables for now.
3. Add compatibility/linkage columns later if needed.
4. Do not migrate old rows into `source_runs` until a separate backfill plan exists.

Reasoning:

- the compatibility audit did not find an existing table that satisfies the full Stage 19D contract;
- a clean `source_runs` table avoids overloading enrichment-specific concepts;
- future import wrappers can consistently target one ledger;
- legacy enrichment tables can remain untouched until we understand their current role fully.

## Proposed table: source_runs

Recommended table name:

- `source_runs`

Recommended purpose:

- one row per attempted import/source capture/warehouse refresh;
- records run identity, source identity, input identity, status, counts, artifacts, errors, and safety boundary;
- acts as the root provenance record for staging rows and warehouse facts.

## Proposed columns

| Column | Type idea | Required | Notes |
|---|---|---:|---|
| `id` | `bigserial primary key` | yes | Internal row ID. |
| `source_run_key` | `text unique not null` | yes | Stable external key used by artifacts/staging. |
| `source_name` | `text not null` | yes | Stage 19C source key, such as `edsm`, `spansh`, `inara`. |
| `source_category` | `text not null` | yes | Stage 19C source category. |
| `domain` | `text not null` | yes | Stage 19C import domain, such as `stations`, `systems`, `bodies`. |
| `import_scope` | `text not null` | yes | Stage 19C import scope. |
| `status` | `text not null` | yes | planned/running/succeeded/failed/rejected/superseded/cancelled. |
| `source_uri` | `text` | no | API URL, source path, logical source key, or manifest path. |
| `source_input_sha256` | `text` | conditional | Required for file/snapshot imports. |
| `source_manifest_sha256` | `text` | no | For huge sources or chunk manifests. |
| `started_at` | `timestamptz` | yes | Start timestamp. |
| `finished_at` | `timestamptz` | no | Null while running. |
| `duration_ms` | `integer` | no | Derived or written by wrapper. |
| `git_commit_sha` | `text not null` | yes | Repo commit used by importer. |
| `importer_name` | `text not null` | yes | Tool/script name. |
| `importer_version` | `text not null` | yes | Tool/script version. |
| `trigger_context` | `text not null` | yes | operator/scheduler/manual/test. |
| `artifact_path` | `text` | no | Required for completed runs. |
| `artifact_sha256` | `text` | no | Required for completed runs. |
| `artifact_integrity_sha256` | `text` | no | Required for canonical JSON artifacts. |
| `rows_read` | `integer not null default 0` | yes | Count read from source. |
| `rows_staged` | `integer not null default 0` | yes | Count written to staging. |
| `rows_rejected` | `integer not null default 0` | yes | Count rejected. |
| `rows_skipped` | `integer not null default 0` | yes | Count skipped/idempotent duplicates. |
| `error_code` | `text` | no | Structured failure key. |
| `error_summary` | `text` | no | Secret-safe error summary. |
| `safety_boundary` | `jsonb not null default {}::jsonb` | yes | Records no-canonical-write/no-apply flags. |
| `metadata` | `jsonb not null default {}::jsonb` | yes | Extra source-specific details. |
| `created_at` | `timestamptz not null default now()` | yes | Row creation timestamp. |
| `updated_at` | `timestamptz not null default now()` | yes | Row update timestamp. |

## Proposed status constraint

Allowed status values:

- `planned`
- `running`
- `succeeded`
- `failed`
- `rejected`
- `superseded`
- `cancelled`

Implementation may use either:

1. a text column with a CHECK constraint; or
2. a PostgreSQL enum.

Recommendation for first implementation:

- use `text` plus CHECK constraint.

Reason:

- easier to extend safely during early warehouse design;
- avoids enum migration churn while the importer contract is still evolving.

## Proposed source/category/domain/scope constraints

Recommendation for first implementation:

- use `text` columns plus CHECK constraints generated from Stage 19C contract.

This gives validation without committing too early to PostgreSQL enums.

Future hardening may move these to enums once the contract stabilises.

## Proposed indexes

Required indexes:

- unique index on `source_run_key`;
- index on `(source_name, domain, started_at desc)`;
- index on `(status, started_at desc)`;
- index on `(source_name, status)`;
- index on `artifact_sha256` where not null;
- index on `source_input_sha256` where not null;
- GIN index on `metadata` only if query patterns justify it later.

Recommended partial uniqueness/safety index:

- prevent more than one `running` run per `(source_name, domain, import_scope)`.

Implementation idea:

`CREATE UNIQUE INDEX ... WHERE status = running`

## Proposed safety constraints

Recommended CHECK constraints:

- `rows_read >= 0`
- `rows_staged >= 0`
- `rows_rejected >= 0`
- `rows_skipped >= 0`
- `finished_at IS NULL OR finished_at >= started_at`
- completed runs should have artifact path/hash

Completed-run constraint can initially be enforced in code instead of DB if the SQL gets too awkward.

## Staging linkage requirement

Future staging tables should reference `source_run_key`.

Minimum staging provenance columns:

- `source_run_key`
- `source_name`
- `source_record_hash`
- `source_file_key` or `source_uri`
- `source_updated_at` where available
- `first_seen_at`
- `last_seen_at`
- `created_at`
- `updated_at`

Stage 19E does not require updating every staging table immediately.

Instead, Stage 19E should create the ledger first, then Stage 19F/G import wrappers should use it for the first automated source.

## Migration strategy

Implementation should be split into separate safe steps:

1. repo branch creates migration SQL and tests;
2. migration is reviewed;
3. migration preflight checks current DB state;
4. migration apply adds only `source_runs` and indexes;
5. post-migration verification confirms table/index/constraint presence;
6. no imports run as part of migration.

## Proposed migration file

Recommended migration filename:

- `sql/029_create_source_runs.sql`

Boundary:

- create table only;
- create indexes only;
- no import;
- no staging writes;
- no canonical writes;
- no backfill;
- no scheduler enablement.

## Required tests

Add tests that verify:

- migration file exists;
- migration creates `source_runs`;
- `source_run_key` is unique;
- status values are constrained;
- row counters are non-negative;
- no canonical table is updated by the migration;
- migration does not mention `UPDATE stations`;
- migration does not mention canonical apply;
- migration does not create scheduler/timer side effects.

## Codex task boundary

Codex should be used for implementation after this plan is merged.

Codex may:

- create the migration;
- add tests;
- inspect existing SQL style;
- open a PR;
- run local/repo tests available in its environment.

Codex must not:

- connect to production DB;
- run the production migration;
- run imports;
- enable scheduler/timers;
- canonical apply;
- modify production data.

## Grok review boundary

Grok can review the Stage 19E plan and later Codex PR for:

- missing fields;
- unsafe assumptions;
- weak constraints;
- source-run edge cases;
- scheduler failure modes;
- UI/admin visibility implications.

Grok must not run commands against production.

## Emergent use

Emergent is useful after the ledger exists for prototyping:

- warehouse status UI;
- source-run history panel;
- import freshness dashboard;
- failed import panel;
- mission intelligence dashboard.

Emergent must not run production DB commands.

## Acceptance criteria for Stage 19E plan

Stage 19E plan is complete when:

- `source_runs` table shape is documented;
- status/failure/freshness boundaries are documented;
- migration strategy is documented;
- tests are listed;
- Codex/Grok/Emergent boundaries are clear;
- no production DB change is performed by the planning stage.

## Next stage

Stage 19F should be the Codex implementation branch for `source_runs` migration and tests.

Stage 19F should remain repo-only until a separate production migration preflight is reviewed.

## Verdict

Implement a clean `source_runs` ledger contract.

Do not overload the current enrichment-specific source-run scaffolding as the final warehouse ledger.

No DB writes, imports, migrations, or canonical apply are approved by this document.
