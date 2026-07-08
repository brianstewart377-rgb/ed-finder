# Stage 18J-P14C — Approval Allowlist Artifact

## Purpose

Stage 18J-P14C adds offline tooling and operator guardrails for an explicit
approval allowlist artifact for the exact reviewed external identity rows.

This stage does not load identity evidence. It only prepares the artifact that
a future controlled loader run must verify before `--write-reviewed` can insert
rows into `station_external_identity`.

This is repo/tooling/tests/docs work only. It does not run production commands,
touch the production database, load identity evidence in production, write to
`station_external_identity` in production, run imports, run reconciliation, run
the summarizer against production artifacts, run station-type dry-run, run
canonical apply, create production approval records, or start Stage 18K.

## Inputs

The allowlist generator is scoped to the fixed review packet:

- review packet path:
  `/var/lib/ed-finder/operator-artifacts/stage-18j/station_external_identity_review_packet_20260603T110848Z.json`;
- review packet SHA-256:
  `8cf118d552e6bc35d23ab302d9e1020092385b372729dbb9b2bae5cd5f0758b6`;
- review packet artifact integrity SHA-256:
  `8cbcf4f2c0d4e3180c3fa6fcbf44f41e71269254168fee0b121f4c6b07bcab84`;
- schema: `station_external_identity_review_packet/v1`;
- manual review items: `20`;
- planned rows: `20`.

The P14B load dry-run selected the same bounded set:

- schema: `station_external_identity_load_execution_plan/v1`;
- `dry_run = true`;
- `write_reviewed = false`;
- `identity_rows_selected = 20`;
- `identity_rows_written = 0`;
- `canonical_writes_planned = 0`;
- `station_type_writes_planned = 0`;
- `max_rows = 20`;
- selected review item IDs: `20`;
- selected plan row IDs: `20`;
- `station_external_identity` row count after dry-run: `0`.

## Why An Allowlist Is Required

The P14B dry-run proves the selected rows are structurally loadable, but it
does not approve a write. The review packet rows still need an explicit
operator decision artifact before a future controlled write-reviewed load can
insert anything.

The allowlist is that decision artifact. It binds the decision to the exact
review packet checksum and the exact selected review item IDs or plan row IDs.

## Approval Scope

The allowlist scope is deliberately narrow:

- decision: `approve_selected_identity_rows`;
- scope: external identity evidence load only;
- target table for a future load: `station_external_identity`;
- maximum rows: `20`;
- source packet SHA-256 must match exactly.

The allowlist is not a broad canonical approval.

## What The Allowlist Approves

The allowlist approves only the exact external identity evidence rows selected
from the verified review packet. A future loader run must verify:

- `schema_version = station_external_identity_load_approval_allowlist/v1`;
- `review_packet_sha256` matches the review packet being loaded;
- approved review item IDs or approved plan row IDs select rows from that
  packet;
- selected rows still pass all required checks;
- selected rows still have `identity_status = confirmed`;
- selected rows still have `conflict_reason = null`;
- selected rows still include source run/file/hash provenance;
- selected rows still include an external ID.

## What The Allowlist Does Not Approve

The allowlist does not approve:

- station-type writes;
- station-type dry-run;
- canonical apply;
- writes to `stations`;
- imports;
- reconciliation;
- summarizer runs against production artifacts;
- production approval-record creation;
- Stage 18K.

It is not a production approval record. It is only an input artifact for a
future, separately approved controlled identity evidence load.

## Artifact Contract

P14C adds `apps/importer/src/station_external_identity_approval_allowlist.py`.

The tool emits deterministic JSON with schema:

`station_external_identity_load_approval_allowlist/v1`

Required top-level fields include:

- `schema_version`;
- `generated_at`;
- `offline = true`;
- `read_only = true`;
- `approval_record_created = false`;
- `source_review_packet_basename`;
- `source_review_packet_sha256`;
- `source_review_packet_integrity_sha256`;
- `review_packet_sha256`;
- `reviewer_decision`;
- `reviewer`;
- `reviewed_at`;
- `declaration`;
- `reviewer_attestation`;
- `max_rows`;
- `approved_review_item_ids`;
- `approved_plan_row_ids`;
- `approved_rows_count`;
- `identity_rows_written = 0`;
- `canonical_writes_planned = 0`;
- `station_type_writes_planned = 0`;
- `safety_summary`;
- `artifact_integrity`.

The reviewer attestation records:

- reviewed packet schema;
- reviewed packet SHA-256;
- reviewed row count;
- `decision_scope = external_identity_evidence_load_only`;
- `does_not_approve_station_type_writes = true`;
- `does_not_approve_canonical_apply = true`;
- `does_not_create_production_approval_record = true`.

The tool refuses:

- checksum mismatch;
- missing review packet;
- missing `--confirm-reviewed`;
- reviewer decision other than `approve_selected_identity_rows`;
- `--max-rows > 20`;
- `--dsn`;
- write/apply/load/commit/reconciliation/import/station-type/canonical flags;
- missing planned rows;
- failed row checks;
- missing source provenance;
- missing external IDs;
- non-confirmed identity status;
- non-null conflict reason.

## Operator Workflow

P14C adds:

`scripts/operator/stage18j_run_identity_approval_allowlist.sh`

The wrapper:

- calls `scripts/operator/require_hetzner_operator_env.sh`;
- defaults `ART_DIR` to
  `/var/lib/ed-finder/operator-artifacts/stage-18j`;
- defaults the review packet path to the P13A packet;
- requires review packet SHA-256
  `8cf118d552e6bc35d23ab302d9e1020092385b372729dbb9b2bae5cd5f0758b6`;
- requires review packet integrity SHA-256
  `8cbcf4f2c0d4e3180c3fa6fcbf44f41e71269254168fee0b121f4c6b07bcab84`;
- requires `CONFIRM_IDENTITY_ALLOWLIST=yes`;
- defaults `MAX_ROWS = 20`;
- refuses `MAX_ROWS > 20`;
- writes the allowlist under the operator artifact directory;
- applies mode `600` to the output;
- prints artifact path, checksum, and summary fields;
- prints explicit no-load, no-station-type, no-apply confirmation.

The wrapper never sources DB env, never connects to a DB, and never runs
imports, reconciliation, summarizer, station-type dry-run, or canonical apply.

## Safety Boundaries

P14C keeps these boundaries:

- no production commands from Codex;
- no production DB access from Codex;
- no identity evidence loaded in production;
- no production writes to `station_external_identity`;
- no imports;
- no reconciliation;
- no summarizer against production artifacts;
- no station-type dry-run;
- no canonical apply;
- no production approval record;
- no Stage 18K.

## Required Future Load Gate

Before any future controlled write-reviewed load:

- run the allowlist wrapper as a tiny Hetzner operator action;
- inspect the allowlist artifact path and checksum;
- verify the allowlist references the exact review packet SHA-256;
- verify `approved_review_item_ids` and `approved_plan_row_ids` count `20`;
- verify `approval_record_created = false`;
- verify `identity_rows_written = 0`;
- use the allowlist only as input to a separately approved controlled
  write-reviewed loader action.

The controlled load remains a future Hetzner action and must still be bounded
to approved rows only.

## Recommended Next Stages

Recommended sequence:

- Stage 18J-P14C — run the approval allowlist artifact wrapper after merge;
- Stage 18J-P14D — controlled write-reviewed identity load of approved rows
  only;
- Stage 18J-P15 — post-load identity coverage artifact;
- Stage 18J-P16 — read-only reconciliation integration with confirmed
  identity;
- Stage 18J-P17 — strict station-type dry-run retry.

## Final Recommendation

Merge P14C as approval-allowlist tooling and documentation only.

After merge, a future Hetzner operator action may create the offline allowlist
artifact. Do not load identity evidence until a later controlled write-reviewed
stage explicitly uses that allowlist.

