# Stage 18J-P11 — Bounded External Identity Load-Plan Artifact

## Purpose

Stage 18J-P11 adds a bounded no-write external station identity load-plan
artifact generator.

The tool proposes a small, reviewable set of `station_external_identity` insert
rows from staged EDSM station evidence, but it does not execute the inserts.
This stage is no-write tooling/test/docs work only. It does not run production
commands, touch the production database, write to `station_external_identity`,
load identity evidence, run production imports, run production reconciliation,
run the summarizer against production artifacts, run station-type dry-run, run
canonical apply, create approval records, or start Stage 18K.

## Inputs

Primary tool:

- `apps/importer/src/station_external_identity_load_plan.py`

Required runtime inputs:

- read-only warehouse/staging DSN through `--dsn`;
- explicit `--source-run-key`;
- optional `--source-file-key`;
- explicit `--max-rows`;
- optional `--sample-limit`;
- optional reviewed P9 artifact checksum through
  `--input-candidate-artifact-sha256`.

The current reviewed production artifact context from Stage 18J-P10 is:

- candidate artifact:
  `station_external_identity_candidates_20260603T002504Z.json`;
- artifact SHA-256:
  `c306321e5bc22b864c9bfe09e92b407c3b407e25e2d4dce4b822e9613aa3b834`;
- schema: `station_external_identity_candidates/v1`;
- total staged rows inspected: `298177`;
- `confirmed_candidate`: `261938`;
- `conflicting`: `258`;
- `rejected`: `35981`;
- `proposed`: `0`;
- `identity_rows_written`: `0`.

## Load-Plan Scope

The load-plan artifact uses the same read-only staged EDSM station matching
logic as Stage 18J-P9. It reads staged evidence and canonical station matches,
classifies candidates, and plans at most the requested bounded number of
eligible `confirmed_candidate` rows.

The first-run cap is `20` planned rows. The CLI rejects `--max-rows` values
above that cap.

The artifact schema is:

- `station_external_identity_load_plan/v1`

The artifact includes:

- `dry_run = true`;
- `read_only = true`;
- `report_only = true`;
- `canonical_writes_planned = 0`;
- `station_type_writes_planned = 0`;
- `identity_rows_written = 0`;
- `identity_rows_planned`;
- `max_rows`;
- source filters;
- optional input candidate artifact checksum;
- total candidates seen;
- eligible confirmed candidates seen;
- planned row count;
- skipped/rejected/conflicting reason counts;
- capped rejected/conflicting samples;
- planned rows capped by `max_rows`;
- artifact integrity hash.

## Planned Row Contract

Each planned row aligns with `station_external_identity` insert fields:

- `canonical_station_id`;
- `system_id64`;
- `station_name`;
- `source`;
- nullable `market_id`;
- nullable `edsm_station_id`;
- `source_run_key`;
- `source_file_key`;
- `source_record_hash`;
- nullable `source_updated_at`;
- `confidence`;
- `freshness_class`;
- `identity_status = 'confirmed'`;
- `conflict_reason = null`.

The plan omits `evidence_first_seen_at`, `evidence_last_seen_at`,
`created_at`, and `updated_at` as insert values because the table defaults are
intended for a later controlled load stage. The artifact records those planned
database defaults separately.

## Eligibility Rules

A candidate can become a planned row only when:

- candidate status is `confirmed_candidate`;
- exactly one canonical station matched;
- match basis is `system_id64_normalized_station_name`;
- source has at least one external identifier, `edsm_station_id` or
  `market_id`;
- source provenance includes `source_run_key`, `source_file_key`, and
  `source_record_hash`;
- the candidate is not conflicting;
- the candidate is not rejected/source-only;
- the candidate is within the explicit `--max-rows` bound.

This planning step uses `system_id64` plus normalized station name to select
candidate identity rows for review. It does not promote station-type canonical
truth and it does not prove station-type writes.

## Rejection Rules

The plan skips:

- rejected/source-only candidates;
- conflicting/ambiguous candidates;
- proposed candidates;
- candidates without exactly one canonical station match;
- candidates without source external ID evidence;
- candidates without complete source provenance;
- otherwise eligible candidates beyond `--max-rows`.

Skipped candidates are counted by reason. Rejected and conflicting samples are
capped by `--sample-limit`.

## Safety Boundaries

The load-plan tool is no-write:

- it uses a read-only DB connection/session;
- its DB SQL is SELECT-only;
- it asserts the SQL is read-only;
- it never inserts, updates, or deletes rows;
- it never writes to `station_external_identity`;
- it never updates `stations`;
- it never changes `station_type`;
- it never runs station-type dry-run;
- it rejects `--apply`, `--write`, `--write-staging`, `--load`, and
  `--commit`.

## Operator Workflow

A future Hetzner operator run is appropriate after this PR merges, limited to a
bounded read-only load-plan artifact:

1. Run from the approved Hetzner operator context.
2. Use a read-only DB role/DSN.
3. Provide the reviewed `source_run_key`.
4. Provide the reviewed `source_file_key`.
5. Provide an explicit `--max-rows` value no greater than `20`.
6. Provide the reviewed P9 artifact SHA-256 when available.
7. Write the JSON artifact under the operator artifact directory.
8. Preserve the artifact checksum.
9. Do not combine this with identity evidence load, reconciliation,
   summarizer, station-type dry-run, or canonical apply.

## Review Requirements

Before any controlled identity evidence load:

- review the load-plan artifact checksum;
- confirm `dry_run`, `read_only`, and `report_only` are true;
- confirm `canonical_writes_planned = 0`;
- confirm `station_type_writes_planned = 0`;
- confirm `identity_rows_written = 0`;
- confirm `identity_rows_planned` is within the explicit bound;
- inspect every planned row;
- confirm every planned row preserves source run/file/hash provenance;
- confirm every planned row has at least one external source ID;
- confirm skipped rejected/source-only candidates are not planned;
- confirm skipped conflicting/ambiguous candidates are not planned;
- confirm the plan does not imply station-type writes.

## What This Does Not Write

P11 writes nothing to:

- `station_external_identity`;
- `stations`;
- `station_type`;
- warehouse staging tables;
- approval records;
- production artifact directories from Codex.

It also does not load identity evidence, run imports, run reconciliation, run
the summarizer, run station-type dry-run, run canonical apply, or start Stage
18K.

## Recommended Next Stages

- Stage 18J-P12 - Review bounded identity load-plan artifact.
- Stage 18J-P13 - Controlled identity evidence load into
  `station_external_identity`, no station-type writes.
- Stage 18J-P14 - Identity coverage artifact after load.
- Stage 18J-P15 - Read-only reconciliation integration with confirmed
  identity.
- Stage 18J-P16 - Retry strict station-type dry-run.

## Final Recommendation

Use the P11 tool to produce a bounded no-write load-plan artifact after merge.

Do not load identity evidence until the bounded plan has been generated,
reviewed, and accepted with exact source filters, artifact checksum, and a
small explicit max-row bound. Keep station-type dry-run and canonical apply
blocked.
