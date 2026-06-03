# Stage 18J-P14 — Controlled External Identity Load Tooling

## Purpose

Stage 18J-P14 adds controlled external station identity load tooling and a
dry-run operator path for reviewed identity rows.

This is repo/tooling/tests/docs work only. It does not run production
commands, touch the production database, load identity evidence in production,
write to `station_external_identity` in production, run imports, run
reconciliation, run the summarizer against production artifacts, run
station-type dry-run, run canonical apply, create production approval records,
or start Stage 18K.

## Inputs

Verified review packet context:

- review packet:
  `/var/lib/ed-finder/operator-artifacts/stage-18j/station_external_identity_review_packet_20260603T110848Z.json`;
- review packet SHA-256:
  `8cf118d552e6bc35d23ab302d9e1020092385b372729dbb9b2bae5cd5f0758b6`;
- review packet artifact integrity SHA-256:
  `8cbcf4f2c0d4e3180c3fa6fcbf44f41e71269254168fee0b121f4c6b07bcab84`;
- source load-plan artifact:
  `station_external_identity_load_plan_20260603T071913Z.json`;
- source load-plan SHA-256:
  `3da39530223f92e89d7129d447944d39199b6510eee473ba1e84ceeb168c9db1`;
- schema: `station_external_identity_review_packet/v1`.

## Review Packet Result

The verified packet reports:

- `manual_review_items = 20`;
- `planned_rows = 20`;
- `first_review_item_has_planned_row = true`;
- `first_review_item_has_non_empty_checks = true`;
- `manual_review_status_counts = {"needs_manual_review": 20}`;
- `canonical_writes_planned = 0`;
- `station_type_writes_planned = 0`;
- `identity_rows_written = 0`;
- `approval_record_created = false`;
- no database access;
- no identity load;
- no station-type dry-run;
- no canonical apply.

Observed row quality from inspection:

- all `20` inspected rows had canonical station ID, system ID64, station name,
  `source = edsm_nightly_stations`, EDSM station ID, source run/file/hash
  provenance, `confidence = source_station_snapshot`,
  `freshness_class = source_updated_at`, `identity_status = confirmed`,
  `conflict_reason = null`, and all boolean checks true.

These rows are reviewable, but not automatically approved. The packet still
has `review_status = needs_manual_review`, so write tooling must require a
separate approval allowlist before any row can be inserted.

## Loader Modes

P14 adds `apps/importer/src/station_external_identity_loader.py`.

The loader supports two modes:

- `--dry-run`: validates a review packet and emits
  `station_external_identity_load_execution_plan/v1` without opening a DB
  connection or writing rows.
- `--write-reviewed`: writes only approved/allowlisted rows from the verified
  packet to `station_external_identity`.

Both modes require:

- `--review-packet`;
- `--expected-review-packet-sha256`;
- `--dsn`;
- `--max-rows`;
- `--output`;
- exactly one of `--dry-run` or `--write-reviewed`;
- optional `--json` output.

Dry-run accepts `--dsn` because the CLI contract is shared with write mode, but
the dry-run implementation does not connect to the database.

## Required Safety Checks

The loader refuses to proceed when:

- `--max-rows` is missing;
- `--max-rows > 20`;
- the review packet SHA-256 does not exactly match;
- the review packet schema is not
  `station_external_identity_review_packet/v1`;
- `identity_rows_written` in the packet is not `0`;
- `canonical_writes_planned` is not `0`;
- `station_type_writes_planned` is not `0`;
- `approval_record_created` is true;
- any selected item is missing `planned_row`;
- any selected item has missing or empty `checks`;
- any selected item has a failed required check;
- any selected item has `identity_status` other than `confirmed`;
- any selected item has non-null `conflict_reason`;
- any selected row lacks source run/file/hash provenance;
- any selected row lacks both `market_id` and `edsm_station_id`;
- selected row count exceeds `--max-rows`;
- forbidden flags are present: `--write`, `--apply`, `--canonical-apply`,
  `--station-type-dry-run`, `--reconciliation`, `--import`, `--summarizer`,
  or `--commit`.

The required boolean row checks are:

- `canonical_station_id_present`;
- `system_id64_present`;
- `station_name_present`;
- `source_run_key_present`;
- `source_file_key_present`;
- `source_record_hash_present`;
- `external_id_present`;
- `identity_status_is_confirmed`;
- `conflict_reason_is_null`;
- `station_type_write_not_planned`.

## Approval / Allowlist Requirement

P14 implements a separate approval allowlist artifact for write mode:

- schema:
  `station_external_identity_load_approval_allowlist/v1`;
- `review_packet_sha256`;
- `approved_review_item_ids`;
- `approved_plan_row_ids`;
- `reviewer`;
- `reviewed_at`;
- `declaration`.

Stage 18J-P14C adds offline allowlist artifact tooling in
`apps/importer/src/station_external_identity_approval_allowlist.py` and a
Hetzner-only wrapper in
`scripts/operator/stage18j_run_identity_approval_allowlist.sh`. The generated
artifact also records `offline = true`, `read_only = true`,
`approval_record_created = false`, source review packet basename/checksum,
source review packet integrity checksum, reviewer attestation, approved row
count, `identity_rows_written = 0`, `canonical_writes_planned = 0`, and
`station_type_writes_planned = 0`. See
[`stage-18j-p14c-approval-allowlist-artifact.md`](./stage-18j-p14c-approval-allowlist-artifact.md).

The allowlist is not a canonical apply approval. It only approves loading exact
external identity evidence rows into `station_external_identity`.

`--write-reviewed` requires:

- `--approved-review-items-file`;
- the allowlist `review_packet_sha256` to match the verified packet;
- at least one approved review item ID or plan row ID;
- `--confirm-write-reviewed`;
- `--confirm-station-external-identity-only`;
- `--confirm-no-canonical-writes`.

The current verified review packet contains only
`review_status = needs_manual_review`, so it is not sufficient by itself for
write mode.

## Dry-run Execution Plan

Dry-run emits `station_external_identity_load_execution_plan/v1` with:

- `dry_run = true`;
- `write_reviewed = false`;
- `canonical_writes_planned = 0`;
- `station_type_writes_planned = 0`;
- `identity_rows_selected`;
- `identity_rows_written = 0`;
- `approval_record_created = false`;
- `max_rows`;
- review packet basename and SHA-256;
- selected review item IDs;
- selected plan row IDs;
- validation summary;
- empty refusal reasons when validation passes;
- artifact integrity.

Dry-run may select up to `--max-rows` valid review rows for the execution plan.
It writes no database rows.

Stage 18J-P14B records the first Hetzner dry-run result. It selected `20`
review items and `20` plan rows from
`station_external_identity_review_packet_20260603T110848Z.json`, verified
review packet SHA-256
`8cf118d552e6bc35d23ab302d9e1020092385b372729dbb9b2bae5cd5f0758b6`, kept
`canonical_writes_planned = 0`, `station_type_writes_planned = 0`, and
`identity_rows_written = 0`, and left `station_external_identity` at `0` rows.
The P14B verdict is `Ready only after approval allowlist artifact`. See
[`stage-18j-p14b-identity-load-dry-run-review.md`](./stage-18j-p14b-identity-load-dry-run-review.md).

P14B also hardens the execution-plan contract so artifacts explicitly emit
top-level `approval_record_created = false` and
`validation_summary.approval_record_created = false`.

## Write-reviewed Boundaries

`--write-reviewed` is deliberately narrow:

- it writes only allowlisted rows;
- it inserts only into `station_external_identity`;
- it uses `ON CONFLICT DO NOTHING` so duplicate confirmed external IDs are
  skipped rather than updated;
- it records inserted row IDs when available;
- it reports duplicate rows skipped;
- it writes no canonical station fields;
- it never updates `stations`;
- it never touches `station_type`;
- it does not run station-type dry-run;
- it does not run reconciliation;
- it does not run canonical apply;
- it does not create an approval record.

This PR does not add a production write operator script.

## Operator Workflow

P14 adds:

- `scripts/operator/stage18j_run_identity_load_dry_run.sh`

The wrapper:

- calls `scripts/operator/require_hetzner_operator_env.sh`;
- defaults `ART_DIR` to
  `/var/lib/ed-finder/operator-artifacts/stage-18j`;
- defaults `REVIEW_PACKET` to the verified P13A packet path;
- requires review packet SHA-256
  `8cf118d552e6bc35d23ab302d9e1020092385b372729dbb9b2bae5cd5f0758b6`;
- defaults `MAX_ROWS = 20`;
- refuses `MAX_ROWS > 20`;
- runs `--dry-run` only;
- writes the execution plan under the operator artifact directory;
- applies mode `600` to the output;
- prints artifact path, checksum, and summary fields;
- prints explicit no-write, no-station-type, no-apply confirmation.

The wrapper does not perform production writes.

## What This Does Not Enable

P14 does not enable:

- production commands from Codex;
- production DB access from Codex;
- production identity evidence loading;
- production writes to `station_external_identity`;
- imports;
- reconciliation;
- summarizer runs against production artifacts;
- station-type dry-run;
- canonical apply;
- production approval-record creation;
- Stage 18K.

## Required Future Production Gates

Before any future production write-reviewed run:

- use the P14B-reviewed load dry-run result;
- inspect the execution plan artifact and checksum;
- create the P14C separate approval allowlist artifact for exact reviewed rows;
- verify the allowlist references the exact review packet SHA-256;
- verify selected row IDs and plan row IDs match the manual review;
- record pre-check `station_external_identity` row count;
- run a tiny, explicit operator write action that loads only allowlisted rows;
- record post-check row count and inserted/duplicate counts;
- confirm no imports, reconciliation, summarizer, station-type dry-run,
  canonical apply, or approval-record creation ran.

## Recommended Next Stages

Recommended sequence:

- use the P14B load dry-run review as the dry-run gate record;
- manually review the load execution plan;
- prepare the P14C approval allowlist artifact only if rows are accepted;
- add a future guarded write operator action only after the approval allowlist
  is reviewed;
- proceed to post-load coverage only after an approved controlled load has run.

## Final Recommendation

Merge P14 as controlled load tooling and dry-run guardrails only.

Do not load identity evidence yet. The next appropriate Hetzner action after
merge is a dry-run execution plan using the verified review packet and checksum.
