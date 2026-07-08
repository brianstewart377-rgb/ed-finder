# Stage 19AO - Operator visibility design

## Purpose

Stage 19AO designs a read-only operator/admin visibility layer for Data Warehouse Utopia before any wider 25-row or real staging pilot.

The goal is cockpit instrumentation, not throttle. Operators need one place to see recent source runs, artifacts, bridge state, staging impact, diagnostic-only rows, and safety gates before enabling larger rehearsals, scheduler work, or any canonical apply lane.

This is a docs-only design. It does not implement API routes, UI, repositories, migrations, imports, DB writes, scheduler units, or canonical writes.

## Current proven capabilities

The production chain now has enough real evidence to design visibility around facts rather than wishes:

- `source_runs` schema is live and tracks import/source-run lifecycle state, row counts, timestamps, artifact paths, hashes, importer identity, git SHA, trigger context, safety boundary, and error summaries.
- Source-run helper lifecycle is live through create, running, final completion, cancellation, failure, rejection, and supersede paths.
- Artifact helpers write canonical JSON with SHA-256 file hashes and self-checking integrity hashes.
- Source-run artifact helpers pair importer completion with artifact metadata and complete `source_runs` rows.
- `source_run_compatibility.py` bridges new `source_runs` provenance into legacy `enrichment_source_runs` rows for staging tables whose `source_run_id` still references `enrichment_source_runs(id)`.
- `edsm_station_import.py` can parse local EDSM-like station JSON, stage only through an explicit compatible stager, and refuses default staging that might pass `source_runs.id` into legacy staging FKs.
- Stage 19AF/19AL proved the single-row EDSM staging smoke and then marked that row diagnostic-only.
- Stage 19AM proved a bundled three-row synthetic EDSM staging rehearsal.
- Stage 19AN-R proved a reviewed operator script can sample five real-shaped warehouse rows, create a local EDSM-like fixture, run the local-file import wrapper, create a bridge row, insert five `staging_edsm_stations` rows, mark those rows diagnostic-only, and verify artifact integrity.
- No scheduler/timer has been enabled, no canonical writes have been performed, and no canonical apply has been performed.

Stage 19A's existing `GET /api/admin/data-status` note remains useful for general station/external-identity data status. Stage 19AO is narrower and newer: it designs source-run, artifact, bridge, staging, and safety visibility.

## Operator questions the cockpit must answer

The first cockpit should answer these questions quickly, without broad scans and without write permissions:

- What source runs happened recently?
- Which runs succeeded, failed, cancelled, rejected, or remain running?
- Are any source runs currently active for the same source/domain/import scope?
- Which source runs have artifacts, and which do not?
- Do artifact file hashes and integrity hashes match the `source_runs` ledger?
- Which `source_runs` rows have legacy `enrichment_source_runs` bridge rows?
- Does the bridge metadata prove the staging FK path targets `enrichment_source_runs(id)`?
- Which staging rows were written by one source run through its bridge?
- Are those staging rows diagnostic-only or normal source evidence?
- Do staging rows preserve `provenance.canonical_write_allowed=false`?
- Did the latest rehearsal/import complete with expected row counts?
- Are there unrecovered failed imports that should block another pilot?
- Are any scheduler/timer/service states enabled when they should still be off?
- Are there any signs of canonical writes or canonical apply activity?
- Is it safe to proceed to the next bounded pilot?

## Read-only view models

These are proposed response/view models, not production tables.

### OperatorSourceRunSummary

| Field | Meaning |
|---|---|
| `source_run_key` | Stable source-run key from `source_runs`. |
| `source_name` | Source, for example `edsm` or `operator_artifact`. |
| `source_category` | Source category such as `source_of_evidence`. |
| `domain` | Domain such as `stations`. |
| `import_scope` | Scope such as `staging_only`. |
| `status` | `running`, `succeeded`, `failed`, `rejected`, `cancelled`, or `superseded`. |
| `started_at` | Source-run start timestamp. |
| `finished_at` | Completion timestamp, if final. |
| `duration_ms` | Run duration, if present. |
| `rows_read` | Rows read by importer/helper. |
| `rows_staged` | Rows staged. |
| `rows_rejected` | Rows rejected. |
| `rows_skipped` | Rows skipped. |
| `artifact_present` | Whether `artifact_path` is present. |
| `artifact_hash_present` | Whether `artifact_sha256` and integrity hash are present. |
| `bridge_present` | Whether a matching legacy bridge row exists. |
| `staging_rows_known` | Whether staging impact could be computed cheaply. |
| `trigger_context` | Operator, test, scheduler, or other trigger context. |
| `git_commit_sha` | Importer code revision recorded by the source run. |
| `error_code` | Error code for failed/rejected/cancelled runs. |
| `error_summary` | Short error summary with secret/path redaction policy applied. |

### OperatorSourceRunDetail

Extends `OperatorSourceRunSummary` with:

- `importer_name`;
- `importer_version`;
- `source_uri_redacted`;
- `source_input_sha256`;
- `source_manifest_sha256`;
- `safety_boundary`;
- `metadata_summary`;
- `artifact_summary`;
- `bridge_summary`;
- `staging_impact_summary`;
- `validation_warnings`;
- `operator_notes`.

The detail view should avoid returning full artifact payloads or full raw source rows by default.

### OperatorArtifactSummary

| Field | Meaning |
|---|---|
| `artifact_path_redacted` | Stored artifact path, redacted to avoid leaking private host layout where needed. |
| `artifact_sha256` | File SHA-256 recorded in `source_runs`. |
| `artifact_integrity_sha256` | Canonical JSON integrity hash recorded in `source_runs`. |
| `artifact_record_present` | Whether completion metadata includes an artifact record. |
| `file_exists` | Optional server-side file existence check if implementation has safe file access. |
| `file_sha256_matches` | Optional exact file hash validation result. |
| `integrity_hash_matches` | Optional canonical JSON integrity validation result. |
| `schema_version` | Artifact schema version, if read safely. |
| `rows_read` | Artifact summary rows read, if present. |
| `rows_staged` | Artifact summary rows staged, if present. |
| `status` | Artifact summary status, if present. |

Hash validation should be explicit and bounded. A first API skeleton may report ledger-side hash presence only, then add file validation as a separate reviewed step.

### OperatorBridgeSummary

| Field | Meaning |
|---|---|
| `bridge_key` | Deterministic `enrichment_source_runs.source_run_key`, usually `source_runs:<source_run_key>`. |
| `legacy_source_run_id` | `enrichment_source_runs.id`, the FK value legacy staging rows must use. |
| `source_run_key` | New `source_runs.source_run_key` represented by the bridge. |
| `bridge_present` | Whether a bridge row exists. |
| `dry_run` | Legacy bridge dry-run flag. |
| `adapter_name` | Bridge adapter name. |
| `adapter_version` | Bridge adapter version. |
| `target_staging_fk` | Expected value `enrichment_source_runs(id)`. |
| `metadata_has_compatibility_bridge` | Whether compatibility metadata is present. |
| `staging_policy_blocks_source_runs_id` | Whether metadata records the no-`source_runs.id` rule. |

### OperatorStagingImpactSummary

| Field | Meaning |
|---|---|
| `source_run_key` | New source-run key. |
| `bridge_key` | Legacy bridge key. |
| `legacy_source_run_id` | Legacy FK id used by staging rows. |
| `staging_table` | Table name, initially `staging_edsm_stations`. |
| `rows_total` | Bounded count for rows tied to the bridge. |
| `rows_diagnostic_only` | Rows with `source_class='diagnostic-only'` and `confidence='diagnostic-only'`. |
| `rows_canonical_write_blocked` | Rows with `provenance->>'canonical_write_allowed' = 'false'`. |
| `rows_with_stage_markers` | Rows with known Stage 19 markers such as `stage19anr_diagnostic_mark`. |
| `rows_using_legacy_bridge_id` | Rows whose `source_run_id` equals `enrichment_source_runs.id`. |
| `rows_using_source_runs_id` | Rows whose `source_run_id` accidentally equals `source_runs.id`; must be zero. |
| `sample_rows` | Optional bounded sample of row ids, station names, station types, and systems. |

Counts must be keyed by bridge id or exact row ids. Avoid broad staging scans.

### OperatorSafetyGateSummary

| Field | Meaning |
|---|---|
| `no_running_source_runs` | No active `planned` or `running` source runs for the pilot source/domain/scope. |
| `latest_artifacts_valid` | Latest relevant artifacts have expected hashes/integrity. |
| `bridge_fk_path_verified` | Staging rows use `enrichment_source_runs.id`, not `source_runs.id`. |
| `diagnostic_rows_isolated` | Existing rehearsal rows are diagnostic-only and canonical-write-blocked. |
| `no_failed_unrecovered_source_runs` | No unresolved failed/rejected runs in the relevant recent window. |
| `scheduler_disabled` | Scheduler/timer/service remains disabled for this lane. |
| `canonical_writes_zero` | No canonical writes performed by warehouse import/rehearsal tooling. |
| `canonical_apply_disabled` | Canonical apply lane is not active. |
| `staging_impact_identifiable` | Operator can identify every staging row written by a run. |
| `safe_to_proceed` | Aggregate verdict; true only when all required gates pass. |
| `blockers` | Human-readable blocker list. |

## Proposed read-only queries and repository functions

These are design-only function shapes. They should be implemented later behind a read-only repository that accepts a caller-owned DB connection/session.

### `list_recent_source_runs(limit, status=None, source_name=None, domain=None)`

Purpose:

- show the recent source-run ledger.

Shape:

- query `source_runs` ordered by `started_at DESC, id DESC`;
- require a bounded `limit`, default 25 and hard cap 100;
- optional indexed filters by `status`, `source_name`, and `domain`;
- return `OperatorSourceRunSummary` rows.

Avoid:

- reading artifacts from disk;
- joining staging tables in the list query;
- returning full metadata JSON.

### `get_source_run_detail(source_run_key)`

Purpose:

- show one source-run record and attach bridge/staging/artifact summaries.

Shape:

- exact lookup by `source_runs.source_run_key`;
- call artifact, bridge, and staging impact helpers separately;
- return `OperatorSourceRunDetail`.

Avoid:

- accepting numeric ids from the URL;
- returning raw secrets in `source_uri` or metadata;
- broad staging counts when no bridge is present.

### `get_source_run_artifacts(source_run_key)`

Purpose:

- summarize source-run artifact metadata.

Shape:

- read artifact path/hash/integrity columns from `source_runs`;
- read completion metadata artifact record when present;
- optionally validate artifact file hash only when the path is under an allowlisted artifact root.

Avoid:

- arbitrary filesystem reads;
- exposing full private paths when the UI only needs file basename and hash;
- streaming large artifacts through the API by default.

### `get_legacy_bridge_for_source_run(source_run_key)`

Purpose:

- show the deterministic bridge to legacy enrichment source-run rows.

Shape:

- compute `source_runs:<source_run_key>`;
- exact lookup by `enrichment_source_runs.source_run_key`;
- return `OperatorBridgeSummary`.

Avoid:

- searching by loose run label;
- assuming `source_runs.id` is safe for legacy staging FKs.

### `get_staging_impact_for_bridge(legacy_source_run_id)`

Purpose:

- count and sample staging rows tied to one legacy bridge id.

Shape:

- exact `WHERE source_run_id = :legacy_source_run_id`;
- initially support `staging_edsm_stations`;
- count diagnostic-only rows, canonical-write-blocked rows, Stage 19 markers, and row-id sample;
- return `OperatorStagingImpactSummary`.

Avoid:

- cross-source full staging scans;
- joining canonical tables;
- using `source_runs.id` as a staging FK.

### `list_diagnostic_staging_rows(source_run_key=None, limit=100)`

Purpose:

- show diagnostic rows that must not be treated as canonical candidates.

Shape:

- if `source_run_key` is present, resolve bridge then filter by exact `source_run_id`;
- if absent, require a small bounded limit and indexed/orderable predicates;
- return row id, bridge id, station name, station type, system name, marker keys, and canonical-write flag.

Avoid:

- returning full `raw_payload`;
- returning unbounded row lists;
- mixing diagnostic rows into candidate queues.

### `get_operator_safety_gates()`

Purpose:

- compute proceed/stop signals for the next Stage 19 pilot.

Shape:

- query exact recent statuses from `source_runs`;
- inspect latest relevant source-run artifact summaries;
- inspect known bridge/staging rows for latest Stage 19 rehearsal keys;
- include static implementation-state gates supplied by configuration or reviewed operator artifacts for scheduler/canonical apply state.

Avoid:

- shelling out to `systemctl` from the API;
- guessing scheduler state without a reviewed data source;
- claiming canonical safety from broad canonical table counts.

## Proposed read-only API

These endpoints are future design only. Stage 19AO does not implement them.

| Endpoint | Purpose |
|---|---|
| `GET /api/operator/source-runs` | Recent source runs with bounded filters. |
| `GET /api/operator/source-runs/{source_run_key}` | One detailed source-run cockpit view. |
| `GET /api/operator/source-runs/{source_run_key}/artifacts` | Artifact metadata and optional hash validation. |
| `GET /api/operator/source-runs/{source_run_key}/bridge` | Legacy enrichment bridge state. |
| `GET /api/operator/source-runs/{source_run_key}/staging-impact` | Staging rows tied to the bridge. |
| `GET /api/operator/diagnostic-staging-rows` | Bounded diagnostic-only staging rows. |
| `GET /api/operator/safety-gates` | Aggregate proceed/stop gate summary. |

Implementation constraints for later stages:

- all endpoints use read-only DB transactions;
- endpoints require existing admin/operator authorization;
- list endpoints enforce bounded limits;
- source-run keys are treated as opaque strings;
- response paths are redacted or normalized;
- artifact file validation is optional and allowlist-bound;
- no endpoint invokes imports, scheduler commands, migrations, canonical writes, or canonical apply.

## UI cockpit design

The first UI should be an operator/admin page, not a broad planner redesign.

### Layout

- Recent runs table at the top.
- Source-run detail drawer or detail page.
- Artifact/hash panel.
- Bridge panel.
- Staging impact panel.
- Diagnostic rows panel.
- Safety gates panel.

### Recent runs table

Columns:

- status chip;
- source run key;
- source/domain/scope;
- started/finished;
- rows read/staged/rejected/skipped;
- artifact badge;
- bridge badge;
- staging impact badge;
- trigger context;
- error indicator.

Status chips:

- green: `succeeded`;
- amber: `rejected`, `cancelled`, or `superseded`;
- red: `failed`;
- blue: `running` or `planned`.

### Artifact/hash panel

Shows:

- artifact basename or redacted path;
- artifact SHA-256;
- integrity SHA-256;
- schema version when available;
- hash validation state;
- warning if artifact is missing or hash validation is unavailable.

### Bridge panel

Shows:

- bridge key;
- legacy `enrichment_source_runs.id`;
- `target_staging_fk`;
- compatibility metadata status;
- explicit warning if the operator cannot confirm the bridge path.

### Staging impact panel

Shows:

- staging table;
- total rows tied to bridge;
- diagnostic-only rows;
- canonical-write-blocked rows;
- rows with known Stage 19 markers;
- row-id/station sample.

The panel must make `source_runs.id` versus `enrichment_source_runs.id` visually explicit.

### Diagnostic rows panel

Shows only bounded diagnostic rows:

- row id;
- station name;
- station type;
- system name;
- source class;
- confidence;
- marker keys;
- canonical-write flag.

Rows marked diagnostic-only should never appear as "ready for canonical candidate" rows.

### Safety gates panel

Shows pass/fail/unknown for:

- running source-run absence;
- artifact validity;
- bridge FK path;
- diagnostic isolation;
- unresolved failures;
- scheduler disabled;
- canonical writes zero;
- canonical apply disabled;
- staging impact identifiable.

The page should display a persistent warning while scheduler/canonical apply remain out of scope:

`Scheduler and canonical apply are intentionally disabled for Stage 19 staging pilots. Do not enable them from this cockpit.`

## Safety gates before next pilots

### Before a 25-row staging pilot

Required pass gates:

- no active `source_runs` for `edsm/stations/staging_only`;
- latest Stage 19AN-R artifacts have valid ledger hashes and integrity hashes;
- Stage 19AN-R bridge row exists;
- Stage 19AN-R staging rows use `enrichment_source_runs.id`;
- diagnostic rows are isolated and preserve `canonical_write_allowed=false`;
- no unrecovered failed Stage 19 source runs in the pilot lineage;
- operator can identify every staging row written by the latest run;
- scheduler/timer remains disabled;
- canonical writes remain zero;
- canonical apply remains disabled.

Stop conditions:

- any active run exists for the same source/domain/scope;
- artifact hash cannot be verified for the latest rehearsal;
- bridge is missing or ambiguous;
- any staging row uses `source_runs.id` in a legacy staging FK;
- any diagnostic rehearsal row lacks canonical-write blocking;
- any canonical write/apply evidence appears.

### Before a 100-row staging pilot

Additional required gates:

- 25-row pilot has a closeout artifact and operator review;
- list/detail views can load recent runs without unbounded staging scans;
- staging impact counts remain keyed by bridge id;
- diagnostic row table remains bounded and paginated;
- operator can compare 5-row and 25-row runs side by side.

Stop conditions:

- queries become slow enough to require broad scans;
- UI cannot distinguish diagnostic-only rows from candidate evidence;
- artifact validation produces unknown or conflicting results.

### Before scheduler enablement

Additional required gates:

- read-only cockpit has been implemented and reviewed;
- scheduler state is visible from a reviewed source of truth;
- overlap prevention is implemented and visible;
- failed/rejected/cancelled runs surface as blocking warnings;
- operator artifact retention and log paths are documented;
- no source-run completion timestamp-window issues remain.

Stop conditions:

- operator cannot see running/failed runs;
- scheduler status would require ad hoc shell commands from the UI/API;
- import artifacts are missing or not integrity-checkable.

### Before canonical apply

Additional required gates:

- separate canonical apply design is approved;
- reconciliation candidate artifacts are implemented and reviewable;
- approval allowlist flow exists;
- rollback/preimage artifact flow exists;
- post-apply verification flow exists;
- diagnostic-only rows are excluded from candidate engines by design and tests;
- cockpit shows candidate, approval, apply, and verification states separately.

Stop conditions:

- any workflow attempts to use ordinary staging rows as executable commands;
- diagnostic rows enter canonical candidate lanes;
- source-run/bridge identity is ambiguous;
- canonical write scope cannot be shown before execution.

## Recommended next stages

| Stage | Scope | Boundary |
|---|---|---|
| Stage 19AP | Read-only operator visibility repository/API skeleton | Repo-only, no production DB, no UI yet. |
| Stage 19AQ | Minimal operator UI page | Repo-only UI consuming read-only endpoints or fixtures. |
| Stage 19AR | Bounded 25-row staging pilot using operator visibility | Operator-reviewed, staging-only, diagnostic handling preserved. |
| Stage 19AS | Post-pilot verification and closeout | Docs/artifact closeout, no scheduler or canonical apply. |

## Risks

| Risk | Mitigation |
|---|---|
| Broad table scans | Use exact `source_run_key`, bridge key, bridge id, row ids, bounded limits, and indexed predicates. |
| Expensive staging counts | Count by exact `source_run_id` bridge id and avoid cross-run aggregates in the first version. |
| Secret or private path exposure | Redact source URIs and artifact paths; show basenames/hashes by default. |
| Confusing `source_runs.id` and `enrichment_source_runs.id` | Make bridge id and FK target visible in the model and UI. |
| Treating diagnostic rows as canonical candidates | Keep diagnostic rows in their own panel and require `canonical_write_allowed=false`. |
| Moving to scheduler/canonical apply too early | Safety gates must stay red/blocked until separate stages implement visibility, approvals, and verification. |
| Hash validation false confidence | Distinguish ledger hash presence from actual file hash/integrity verification. |
| Overloading the first cockpit | Start with source-runs, artifacts, bridge, staging impact, diagnostics, and safety gates only. |

## Non-goals

Stage 19AO does not:

- run imports;
- write DB rows;
- enable scheduler/timers;
- apply canonical changes;
- build the whole cockpit;
- implement API routes;
- implement UI components;
- replace the existing planner UI;
- replace the existing `GET /api/admin/data-status` endpoint;
- implement full admin auth;
- add migrations;
- design a canonical apply lane in full;
- approve any 25-row, 100-row, scheduler, or canonical apply execution by itself.

## Stage 19AO verdict

The next Stage 19 implementation work should make source-run and staging state visible before expanding ingestion. The system has proven the path from local fixture to `source_runs`, legacy bridge, staging rows, diagnostic mark, and artifacts. The missing safety layer is operator visibility that can answer, in one place, what happened and whether the next step is safe.

