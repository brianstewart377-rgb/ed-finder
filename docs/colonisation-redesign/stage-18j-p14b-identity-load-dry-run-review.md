# Stage 18J-P14B — Identity Load Dry-Run Review

## Purpose

Stage 18J-P14B records the controlled external identity load dry-run result
before any identity evidence is written to `station_external_identity`.

This is a review, documentation, and contract-hardening stage. It does not run
production commands from Codex, touch the production database from Codex, load
identity evidence in production, write to `station_external_identity` in
production, run imports, run reconciliation, run the summarizer against
production artifacts, run station-type dry-run, run canonical apply, create
production approval records, or start Stage 18K.

## Dry-Run Artifact Reviewed

The Hetzner operator dry-run produced a
`station_external_identity_load_execution_plan/v1` artifact from the verified
P13A review packet:

- review packet basename:
  `station_external_identity_review_packet_20260603T110848Z.json`;
- review packet SHA-256:
  `8cf118d552e6bc35d23ab302d9e1020092385b372729dbb9b2bae5cd5f0758b6`;
- `dry_run = true`;
- `write_reviewed = false`;
- `max_rows = 20`;
- `identity_rows_selected = 20`;
- `identity_rows_written = 0`.

The dry-run artifact itself is an operator artifact and is not committed to the
repository.

## Safety Result

The dry-run result preserved the Stage 18J-P safety boundaries:

- `canonical_writes_planned = 0`;
- `station_type_writes_planned = 0`;
- `identity_rows_written = 0`;
- `station_external_identity` row count after the dry-run was `0`;
- the secret/path sanity check was clean;
- no identity rows were loaded;
- no station-type dry-run ran;
- no canonical apply ran.

## Selected Rows

The dry-run selected the full bounded packet:

- selected review item IDs: `20`;
- selected plan row IDs: `20`;
- selected row cap: `20`;
- source review packet:
  `station_external_identity_review_packet_20260603T110848Z.json`.

These rows are structurally loadable according to the loader checks, but the
dry-run does not approve them for insertion.

## Validation Summary

The dry-run validation summary reported:

- `all_required_checks_passed = true`;
- `approval_allowlist_present = false`;
- `approval_allowlist_required = false`;
- `approval_allowlist_sha256 = null`;
- `canonical_writes_planned = 0`;
- `conflict_reason_null = true`;
- `duplicate_rows_skipped = 0`;
- `external_id_present = true`;
- `identity_rows_written = 0`;
- `identity_status_confirmed = true`;
- `manual_review_items_selected = 20`;
- `review_packet_schema_valid = true`;
- `review_packet_sha256_verified = true`;
- `source_provenance_present = true`;
- `station_type_writes_planned = 0`.

## Approval / Allowlist Status

No approval allowlist artifact exists yet:

- `approval_allowlist_present = false`;
- `approval_allowlist_required = false` for dry-run mode;
- `approval_allowlist_sha256 = null`.

The absence of an allowlist is correct for dry-run mode. It is also the reason
this result is not sufficient for a controlled write-reviewed load.

## Contract Nit / Hardening

The operator quick summary printed `approval_record_created: None` because the
P14 execution-plan artifact did not explicitly emit that field. The loader has
now been hardened so execution plans emit:

- top-level `approval_record_created = false`;
- `validation_summary.approval_record_created = false`.

The dry-run wrapper now validates and prints the top-level field. Regression
tests cover both dry-run output and synthetic/local write-reviewed output.

This hardening does not change production write behavior and does not create an
approval record.

## Readiness Verdict

`Ready only after approval allowlist artifact`

The dry-run proves the `20` selected rows are structurally loadable and remain
bounded, but no approval allowlist exists. A future write-reviewed load must be
restricted to exact review item IDs or plan row IDs in a separate allowlist
artifact tied to the exact review packet SHA-256.

## Required Next Gate

Before any controlled write-reviewed load:

- create `station_external_identity_load_approval_allowlist/v1`;
- reference review packet SHA-256
  `8cf118d552e6bc35d23ab302d9e1020092385b372729dbb9b2bae5cd5f0758b6`;
- list exactly the approved review item IDs or plan row IDs;
- include reviewer declaration fields;
- keep the allowlist separate from canonical apply approval;
- run no imports, reconciliation, summarizer, station-type dry-run, canonical
  apply, or production approval-record creation as part of the allowlist step.

Stage 18J-P14C adds this offline allowlist artifact tooling in
`apps/importer/src/station_external_identity_approval_allowlist.py` and a
Hetzner-only wrapper in
`scripts/operator/archive/stage18j/stage18j_run_identity_approval_allowlist.sh`. The allowlist
approves only external identity evidence loading for exact selected rows. It
does not approve station-type writes, canonical apply, or production
approval-record creation. See
[`stage-18j-p14c-approval-allowlist-artifact.md`](./stage-18j-p14c-approval-allowlist-artifact.md).

## What Was Not Run

Stage 18J-P14B did not run:

- production commands from Codex;
- production DB access from Codex;
- identity evidence loading in production;
- production writes to `station_external_identity`;
- imports;
- reconciliation;
- summarizer against production artifacts;
- station-type dry-run;
- canonical apply;
- production approval-record creation;
- Stage 18K.

## Recommended Next Stages

Recommended sequence:

- Stage 18J-P14C — Approval allowlist artifact for the 20 selected rows;
- Stage 18J-P14D — Controlled write-reviewed identity load of approved rows
  only;
- Stage 18J-P15 — Post-load identity coverage artifact;
- Stage 18J-P16 — Read-only reconciliation integration with confirmed
  identity;
- Stage 18J-P17 — Strict station-type dry-run retry.

## Final Recommendation

Do not load identity evidence yet.

Proceed only to Stage 18J-P14C. The next appropriate work is a separate
approval allowlist artifact for the exact `20` selected review items or plan
rows, tied to the verified review packet checksum.

