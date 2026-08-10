# Stage 18J-P8 — External Identity Evidence Loader / Reconciliation Design

## Purpose

Stage 18J-P8 designs how external station identity evidence should be loaded
and reconciled into `station_external_identity` after the Stage 18J-P7
schema-only production apply closeout.

This stage is docs/design only. It does not run production commands, touch the
production database, load identity evidence, run imports, run reconciliation,
run the summarizer against production artifacts, run station-type dry-run, run
canonical apply, create approval records, or start Stage 18K.

## Current Production State

Known operator state after Stage 18J-P7:

- `station_external_identity` exists in production.
- `station_external_identity` row count is `0`.
- canonical `stations` count after schema apply stayed unchanged at `284763`.
- no imports were run.
- no reconciliation was run.
- no summarizer was run.
- no station-type dry-run was run.
- no canonical apply was run.
- no identity evidence was loaded.
- no station-type data changed.

The schema is present but empty. It does not yet provide canonical external
identity proof for Stage 18J-P station-type filtering.

## Source Evidence Candidates

Use existing `edsm_nightly_stations` warehouse evidence first, specifically
accepted rows from `staging_edsm_stations` joined to their source run/file/raw
record metadata.

This is the preferred first source because it already carries the fields needed
by `station_external_identity`:

- `system_id64`;
- `system_name`;
- `station_name`;
- `market_id`;
- `edsm_station_id`;
- `source_run_key`;
- `source_file_key`;
- `source_record_hash`;
- `source_updated_at`;
- `confidence`;
- `freshness_class`;
- `source`;
- `source_class`;
- raw/provenance payload.

Do not use live EDSM calls for this first design. Do not use station/body link
evidence as a general station identity source. Body-link evidence can become
supporting context later, but identity and association must remain separate.

## Target Table

Target table:

- `station_external_identity`

Field mapping from `staging_edsm_stations` and source metadata:

| Target field | Proposed source |
|---|---|
| `canonical_station_id` | matched canonical `stations.id`, only after candidate matching |
| `system_id64` | `staging_edsm_stations.system_id64` |
| `station_name` | `staging_edsm_stations.station_name` |
| `source` | `enrichment_source_runs.source`, expected `edsm_nightly_stations` |
| `market_id` | `staging_edsm_stations.market_id` |
| `edsm_station_id` | `staging_edsm_stations.edsm_station_id` |
| `source_run_key` | `enrichment_source_runs.source_run_key` |
| `source_file_key` | `enrichment_source_files.source_file_key` |
| `source_record_hash` | `staging_edsm_stations.source_record_hash` |
| `source_updated_at` | `staging_edsm_stations.source_updated_at` |
| `evidence_first_seen_at` | loader timestamp or preserved existing first-seen value |
| `evidence_last_seen_at` | loader timestamp for the reviewed evidence batch |
| `confidence` | `exact_station_identity` for confirmed reviewed rows, otherwise existing source confidence such as `source_station_snapshot` |
| `freshness_class` | `staging_edsm_stations.freshness_class` |
| `identity_status` | status decision from the candidate artifact |
| `conflict_reason` | required reason for `conflicting` rows |

The loader must preserve `source_run_key`, `source_file_key`, and
`source_record_hash` for every row. Rows without complete provenance are not
eligible for confirmed identity.

## Candidate Matching Strategy

The first implementation should produce a read-only identity candidate artifact
before writing any identity evidence. The artifact should classify each
candidate with enough detail for operator review.

Candidate matching should:

- start from accepted `staging_edsm_stations` rows with at least one external
  ID (`market_id` or `edsm_station_id`);
- require `system_id64` to resolve to exactly one canonical system;
- require a normalized station-name match within that system;
- require exactly one canonical station candidate;
- preserve source `market_id` and `edsm_station_id` without treating them as
  canonical proof until the candidate is reviewed;
- report rows with zero or multiple canonical station matches as blocked from
  confirmation;
- report rows where the same external ID maps to multiple canonical stations;
- report rows where one canonical station receives multiple active external
  IDs from the same source identity kind.

Do not use name-only matching as confirmed identity proof. Normalized station
name can support a match only when paired with `system_id64`, source external
ID evidence, complete provenance, and a single canonical station match.

Do not treat internal `stations.id` equality as external identity proof. The
current reconciliation SQL has compatibility joins where staged `market_id` or
`edsm_station_id` may equal `stations.id`; that behavior must not be promoted
to identity confirmation without the explicit external identity model.

## Identity Status Decision Rules

Recommended status rules:

- `proposed`: source row has at least one external ID, complete provenance, and
  a plausible single canonical match, but it has not been reviewed or accepted
  as confirmed identity.
- `confirmed`: source row has complete provenance, at least one external ID,
  `system_id64` matches the canonical system, normalized station name matches
  exactly one canonical station, no same-source external ID conflict exists,
  no canonical-station external ID conflict exists, and the reviewed dry-run
  artifact approves the row for identity load.
- `conflicting`: evidence is internally or externally contradictory and must
  remain visible but blocked from proof use.
- `rejected`: evidence is malformed, missing required provenance, missing both
  external IDs, attached to an unsupported source, or cannot be made useful for
  identity review.
- `superseded`: a previously loaded non-current evidence row has been replaced
  by a newer reviewed row for the same canonical station/source/external ID.

Do not mark warehouse source-only evidence as `confirmed` automatically.
Confirmation is a reviewed identity decision, not just the presence of a staged
row.

Rejected evidence that lacks both external IDs or required provenance cannot be
inserted into `station_external_identity` because the table requires those
fields. Keep those rows in the dry-run artifact as artifact-only rejects. Only
schema-valid rejected evidence should be loaded with
`identity_status = 'rejected'`.

## Conflict Handling

Conflicts must be stored or reported as `conflicting`, not overwritten.

Block confirmed identity when:

- `market_id` is associated with multiple canonical stations for the same
  source;
- `edsm_station_id` is associated with multiple canonical stations for the same
  source;
- one canonical station receives multiple active `market_id` values for the
  same source without an explicit supersession decision;
- one canonical station receives multiple active `edsm_station_id` values for
  the same source without an explicit supersession decision;
- source rows with the same `source_record_hash` or external ID disagree on
  `system_id64` or normalized `station_name`;
- staged evidence matches zero canonical stations;
- staged evidence matches multiple canonical stations;
- source `system_id64` conflicts with the matched canonical station system;
- normalized source and canonical station names do not match;
- provenance is incomplete;
- the row would rely only on internal `stations.id` equality.

Every conflicting row needs a `conflict_reason` that is specific enough for
later review, for example `external_id_maps_to_multiple_canonical_stations`,
`canonical_station_has_multiple_market_ids`, `system_id64_mismatch`,
`station_name_mismatch`, or `missing_source_provenance`.

## Proposed Loader Workflow

P8 does not implement the loader. The recommended workflow for later stages is:

1. Select an explicit `source_run_key` and optional `source_file_key`.
2. Read only accepted `edsm_nightly_stations` staged rows.
3. Build identity candidates from rows with at least one external ID.
4. Join candidates to canonical systems by `system_id64`.
5. Match canonical stations within the system by normalized station name.
6. Classify candidates into `proposed`, `confirmed_candidate`,
   `conflicting_candidate`, `rejected_candidate`, or `superseded_candidate` in
   a read-only artifact.
7. Include all source provenance and match proof in the artifact.
8. Record aggregate counts by status, external ID type, source run/file, and
   conflict reason.
9. Require operator review of the artifact before any write-stage/load step.

The first loader implementation should be report-only by default and should
reject any canonical write flag.

## Proposed Dry-Run Artifact

Stage 18J-P9 should produce an identity evidence dry-run artifact only.
Stage 18J-P9 implements this as
`apps/importer/src/station_external_identity_candidates.py`, a read-only JSON
artifact generator.

Suggested artifact schema:

- `schema_version`: `station_external_identity_candidates/v1`;
- `dry_run`: `true`;
- `report_only`: `true`;
- `canonical_writes_planned`: `0`;
- `identity_rows_planned`: count by status;
- `filters`: source run/file and source;
- `source_summary`: staged rows considered, rows with external IDs, rows with
  complete provenance, rows skipped;
- `candidate_summary`: counts for proposed/confirmable/conflicting/rejected;
- `conflict_summary`: counts by conflict reason;
- `confirmed_candidate_samples`;
- `conflicting_candidate_samples`;
- `rejected_candidate_samples`;
- `proposed_candidate_samples`;
- `artifact_integrity`: canonical JSON hash.

Each candidate row should include:

- source run/file/hash;
- source record key;
- source `market_id`;
- source `edsm_station_id`;
- source `system_id64`;
- source `station_name`;
- normalized source station name;
- matched canonical station ID;
- matched canonical system ID64;
- normalized canonical station name;
- canonical match count;
- proposed `identity_status`;
- proposed confidence/freshness;
- `conflict_reason` when applicable;
- explicit statement that `stations.id` was not used as external proof.

## Proposed Write-Staging / Load Workflow

Stage 18J-P10 reviews the first read-only candidate artifact and records the
verdict `Ready only for bounded identity load dry-run`. The next implementation
step should be a bounded no-write load-plan artifact before any write-staging
or load stage.

Stage 18J-P11 implements that bounded no-write load-plan artifact as
`apps/importer/src/station_external_identity_load_plan.py`. It emits
`station_external_identity_load_plan/v1`, requires an explicit `--max-rows`
bound no greater than `20`, rejects write/apply/load flags, and keeps
`identity_rows_written = 0`.

A later controlled write-staging/load stage should write only to
`station_external_identity`.

Recommended load behavior:

- require an artifact hash from the reviewed P9 candidate artifact;
- require exact source run/file filters to match the artifact;
- write no canonical tables;
- write no station-type data;
- insert reviewed `confirmed`, `conflicting`, schema-valid `rejected`,
  `proposed`, and `superseded` rows as explicitly selected by the load plan;
- keep conflicting evidence visible with `conflict_reason`;
- update `evidence_last_seen_at` and `updated_at` for existing matching rows;
- preserve previous `evidence_first_seen_at` when refreshing the same evidence;
- mark old rows `superseded` only through an explicit reviewed supersession
  decision;
- run inside a transaction;
- emit a post-load identity evidence report.

The load should not be combined with read-only reconciliation integration or
station-type dry-run.

## Required Operator Preflight Checks

Before any future identity evidence dry-run or load stage, require:

- confirm the shell context is correct for the intended action;
- confirm Codex/local prompts are not running production commands;
- confirm `station_external_identity` exists;
- confirm current row count before the action;
- confirm `stations` count snapshot before the action;
- confirm target source run/file exists in warehouse staging;
- confirm source rows are from `edsm_nightly_stations`;
- confirm no imports are running;
- confirm no reconciliation jobs are running;
- confirm no summarizer jobs are running;
- confirm no station-type dry-run is running;
- confirm no canonical apply is running;
- confirm no approval-record creation is part of the workflow;
- for write-load only, confirm the reviewed P9 artifact hash and source filters
  match exactly;
- for write-load only, confirm backup/snapshot or explicit identity-table load
  risk acceptance.

## Required Post-Load Checks

After a future identity evidence load, require:

- `station_external_identity` row count matches the load report;
- counts by `identity_status` match the reviewed plan;
- conflicts have non-null `conflict_reason`;
- no row lacks `source_run_key`, `source_file_key`, or `source_record_hash`;
- no row lacks both `market_id` and `edsm_station_id`;
- `stations` row count is unchanged;
- station-type data is unchanged;
- no canonical write plan was produced;
- no imports, reconciliation, summarizer, station-type dry-run, or canonical
  apply started as part of the load;
- a follow-up coverage artifact can be produced from the identity table.

## Reconciliation Integration

Stage 18J-P15 should integrate confirmed external identity into read-only
station reconciliation output.

Recommended read-only join shape:

- join canonical station matches to `station_external_identity` by
  `canonical_station_id`;
- restrict proof rows to `identity_status = 'confirmed'`;
- preserve source/provenance fields in the reconciliation output;
- expose canonical external identity fields such as `canonical.market_id`,
  `canonical.edsm_station_id`, `canonical.external_identity_status`,
  `canonical.external_identity_source`,
  `canonical.external_identity_confidence`,
  `canonical.external_identity_freshness_class`,
  `canonical.external_identity_source_run_key`,
  `canonical.external_identity_source_file_key`, and
  `canonical.external_identity_source_record_hash`;
- keep ambiguous or conflicting identity rows out of proof use while reporting
  them in coverage.

Reconciliation integration must remain read-only and must preserve
`canonical_writes_planned = 0`.

## Station-Type Dry-Run Impact

P8 does not run or unblock station-type dry-run.

The strict station-type filter should remain unchanged until:

- identity evidence has been loaded in a separate reviewed stage;
- an identity coverage artifact shows confirmed identity coverage;
- read-only reconciliation exposes confirmed canonical external IDs;
- strict station-type dry-run is retried in Stage 18J-P16.

Station-type writes remain blocked. Non-zero dry-run candidates still require a
separate review packet before canonical apply can be discussed.

## What This Does Not Enable

P8 does not enable:

- production commands from Codex;
- production DB access from Codex;
- identity evidence loading;
- imports;
- reconciliation runs;
- summarizer runs against production artifacts;
- station-type dry-run;
- canonical apply;
- approval-record creation;
- changes to `stations`;
- changes to `station_type`;
- Stage 18K.

## Risks / Open Questions

Open questions for the load-plan and controlled-load design:

- whether the first candidate artifact should emit only confirmable/conflicting
  rows or all staged external-ID rows;
- whether `edsm_station_id` and `market_id` are always identical in current
  EDSM station snapshots, and how to classify rows where they diverge;
- whether later high-volume reads need an additional
  `(canonical_station_id, identity_status)` index;
- how to handle station renames where source external ID stays stable but
  normalized station name changes;
- whether supersession should be modeled as a load-time status transition or as
  separate historical rows only;
- whether future body-link evidence should be included as secondary context in
  coverage reports without affecting identity confirmation.

## Recommended Next Stages

- Stage 18J-P10 - External identity candidate artifact review.
- Stage 18J-P11 - Bounded external identity load-plan artifact, no DB writes.
- Stage 18J-P12 - Review bounded identity load plan.
- Stage 18J-P13 - Controlled identity evidence load into
  `station_external_identity`, no station-type writes.
- Stage 18J-P14 - Identity coverage artifact after load.
- Stage 18J-P15 - Read-only reconciliation integration with confirmed
  identity.
- Stage 18J-P16 - Retry strict station-type dry-run.

## Final Recommendation

Proceed with a read-only identity candidate artifact before any writes to
`station_external_identity`.

Use `staging_edsm_stations` as the first source of external station identity
evidence, but do not confirm identity from source evidence alone. Confirmation
must require complete provenance, at least one external ID, `system_id64`, a
single normalized station-name match to canonical, no conflicts, and explicit
review of the dry-run artifact.

Keep station-type dry-run and canonical apply blocked until confirmed identity
coverage exists and has been reviewed through read-only reconciliation.

