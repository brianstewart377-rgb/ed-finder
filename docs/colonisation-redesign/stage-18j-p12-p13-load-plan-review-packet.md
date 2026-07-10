# Stage 18J-P12/P13 — Load-Plan Review + Planned Row Review Packet

## Purpose

Stage 18J-P12/P13 implements Chunk A from the Stage 18J-P identity evidence
execution board.

This stage records the bounded no-write identity load-plan artifact review and
adds an offline planned-row review packet generator. It does not run
production commands, touch the production database, load identity evidence,
write to `station_external_identity`, run imports, run reconciliation, run the
summarizer against production artifacts, run station-type dry-run, run
canonical apply, create approval records, or start Stage 18K.

## Inputs

Reviewed operator artifact:

- artifact type: `station_external_identity_load_plan/v1`;
- path:
  `/var/lib/ed-finder/operator-artifacts/stage-18j/station_external_identity_load_plan_20260603T071913Z.json`;
- size: `349K`;
- artifact SHA-256:
  `3da39530223f92e89d7129d447944d39199b6510eee473ba1e84ceeb168c9db1`;
- artifact integrity SHA-256:
  `f8cf7260425ba82b1fc476d3cd239dbf41e2b246040ad9b461750ae4322a544f`;
- schema version: `station_external_identity_load_plan/v1`;
- source: `edsm_nightly_stations`;
- source run key:
  `6ad44d1ad04d53c958ba7f5877b01752a22e29d9e905627c7feba5bb9eca2db1`;
- source file key:
  `76f5c8aa5e55d267c96c16da026ff5cbfae58f1d63575d47759c9bf3aaa37c19`.

The artifact reports:

- `dry_run = true`;
- `read_only = true`;
- `report_only = true`;
- `canonical_writes_planned = 0`;
- `station_type_writes_planned = 0`;
- `identity_rows_planned = 20`;
- `identity_rows_written = 0`;
- `max_rows = 20`;
- `total_candidates_seen = 298177`;
- `eligible_confirmed_candidates_seen = 261938`;
- `planned_rows_count = 20`;
- `eligible_beyond_max_rows = 261918`;
- `source_only_no_canonical_station_match = 35981`;
- `ambiguous_canonical_station_match = 258`;
- `confirmed_candidate = 261938`;
- `conflicting = 258`;
- `proposed = 0`;
- `rejected = 35981`.

Post-checks recorded:

- `station_external_identity` row count after artifact generation: `0`;
- no identity rows loaded;
- no station-type dry-run run;
- no canonical apply run.

## P12 Load-Plan Review Result

The load-plan artifact is internally consistent as a bounded no-write review
artifact:

- it uses the expected versioned schema,
  `station_external_identity_load_plan/v1`;
- the artifact file checksum and internal integrity checksum are recorded;
- the source scope matches the reviewed EDSM nightly station run/file keys;
- the plan is capped at `20` rows;
- the plan reports no identity rows written;
- rejected/source-only rows remain excluded from planned confirmed identity;
- ambiguous canonical station matches remain excluded from planned confirmed
  identity;
- no canonical station writes are planned;
- no station-type writes are planned.

The result is not an authorization to load identity evidence. It is only ready
to produce a compact manual review packet for the exact planned rows.

## Readiness Verdict

`Ready only after planned-row manual review`

The bounded load-plan artifact can be used as the input to an offline
planned-row review packet. It does not authorize a controlled insert into
`station_external_identity`.

## P13 Review Packet Tool

P13 adds:

- `apps/importer/src/station_external_identity_review_packet.py`;
- `scripts/operator/archive/stage18j/stage18j_run_identity_review_packet.sh`;
- synthetic tests in
  `tests/test_station_external_identity_review_packet.py`.

The Python tool:

- accepts `--load-plan-artifact`;
- accepts `--expected-load-plan-sha256`;
- accepts `--output`;
- supports `--json`;
- supports `--max-planned-rows`, defaulting to `20`;
- refuses `--max-planned-rows` above `20`;
- verifies the load-plan artifact file SHA-256 before parsing;
- parses only local JSON;
- never accepts `--dsn`;
- rejects write/apply/load/commit flags;
- emits deterministic JSON with schema
  `station_external_identity_review_packet/v1`;
- includes planned rows capped by `--max-planned-rows`;
- includes one manual review item per included planned row;
- makes each manual review item self-contained with `planned_row`, `checks`,
  and `reviewer_notes = null`;
- defaults each review item to `needs_manual_review`;
- keeps `canonical_writes_planned = 0`;
- keeps `station_type_writes_planned = 0`;
- keeps `identity_rows_written = 0`;
- keeps `approval_record_created = false`.

The generated packet is an offline manual review artifact. It is not a load
artifact and it is not an approval record.

## P13A Review Packet Contract Hardening

The first Hetzner offline review-packet run completed safely:

- review packet:
  `/var/lib/ed-finder/operator-artifacts/stage-18j/station_external_identity_review_packet_20260603T103130Z.json`;
- review packet SHA-256:
  `6b2415ef4f12a0f81808f90a9eb592d18269e181660e7cbd9fe597e63cc18705`;
- source load-plan artifact:
  `station_external_identity_load_plan_20260603T071913Z.json`;
- source load-plan SHA-256:
  `3da39530223f92e89d7129d447944d39199b6510eee473ba1e84ceeb168c9db1`;
- `planned_rows_included = 20`;
- `manual_review_items_count = 20`;
- `manual_review_status_counts = {"needs_manual_review": 20}`;
- `canonical_writes_planned = 0`;
- `station_type_writes_planned = 0`;
- `identity_rows_written = 0`;
- `approval_record_created = false`;
- no database access;
- no identity load;
- no station-type dry-run;
- no canonical apply.

Manual inspection found that the safety fields were correct but
`manual_review_items` were not self-contained enough for human review:

- `manual_review_items` existed and had length `20`;
- top-level `planned_rows` existed and had length `20`;
- each `manual_review_items[n].planned_row` was missing or null in the
  inspection contract;
- each `manual_review_items[n].checks` was empty in the inspection contract.

Stage 18J-P13A fixes the packet contract. Each item in
`manual_review_items` must include:

- `review_item_id`;
- `review_status = "needs_manual_review"`;
- `planned_row`;
- `checks`;
- `reviewer_notes = null`.

The nested `planned_row` must include the planned identity row fields needed
for review, including canonical station ID, source system/station, source,
external IDs, source run/file/hash provenance, confidence, freshness class,
identity status, and conflict reason. The top-level `planned_rows` list remains
for convenience and must exactly match the rows embedded in
`manual_review_items`.

The nested `checks` object must include boolean fields for:

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

The P13A fix does not approve a load. It only makes a future offline review
packet rerun suitable for manual row inspection.

## P14 Controlled Loader Follow-up

Stage 18J-P14 adds controlled external identity load tooling in
`apps/importer/src/station_external_identity_loader.py` and a dry-run-only
Hetzner wrapper in `scripts/operator/archive/stage18j/stage18j_run_identity_load_dry_run.sh`.

The fixed review packet from the P13A rerun is reviewable:

- review packet:
  `/var/lib/ed-finder/operator-artifacts/stage-18j/station_external_identity_review_packet_20260603T110848Z.json`;
- review packet SHA-256:
  `8cf118d552e6bc35d23ab302d9e1020092385b372729dbb9b2bae5cd5f0758b6`;
- artifact integrity SHA-256:
  `8cbcf4f2c0d4e3180c3fa6fcbf44f41e71269254168fee0b121f4c6b07bcab84`;
- `manual_review_items = 20`;
- `planned_rows = 20`;
- `manual_review_status_counts = {"needs_manual_review": 20}`;
- all inspected row checks were true;
- `identity_rows_written = 0`;
- no database access or load occurred.

The rows are reviewable but not automatically approved. P14 therefore requires
a separate approval allowlist artifact for `--write-reviewed`. The allowlist is
only approval to load exact external identity evidence rows into
`station_external_identity`; it is not canonical apply approval.

Stage 18J-P14B records the first controlled load dry-run. It selected all `20`
review items and all `20` plan rows, verified review packet SHA-256
`8cf118d552e6bc35d23ab302d9e1020092385b372729dbb9b2bae5cd5f0758b6`,
kept `canonical_writes_planned = 0`, `station_type_writes_planned = 0`, and
`identity_rows_written = 0`, and left `station_external_identity` at `0` rows.
The verdict is `Ready only after approval allowlist artifact`. See
[`stage-18j-p14b-identity-load-dry-run-review.md`](./stage-18j-p14b-identity-load-dry-run-review.md).

## Planned Row Review Requirements

Each planned row must be manually reviewed before any future controlled load
tooling may use it.

Required row checks:

- confirm the planned `canonical_station_id` is the intended station for the
  source `system_id64` and station-name evidence;
- confirm at least one source external identifier is present,
  `edsm_station_id` or `market_id`;
- confirm `source_run_key`, `source_file_key`, and `source_record_hash` are
  present and match the reviewed load plan;
- confirm `identity_status = 'confirmed'`;
- confirm `conflict_reason = null`;
- confirm the row does not plan canonical writes;
- confirm the row does not plan station-type writes;
- confirm the row does not depend on internal `stations.id` as external
  identity proof;
- confirm the row does not use `station_body_links.market_id` as general
  station identity proof.

Rows that remain `needs_manual_review` are not loadable. Conflicting,
ambiguous, rejected, or source-only rows remain blocked.

## Operator Workflow

After this PR merges, a future Hetzner operator action may run the offline
review packet wrapper:

```sh
scripts/operator/archive/stage18j/stage18j_run_identity_review_packet.sh
```

The wrapper:

- calls `scripts/operator/require_hetzner_operator_env.sh`;
- defaults `ART_DIR` to
  `/var/lib/ed-finder/operator-artifacts/stage-18j`;
- defaults `LOAD_PLAN_ARTIFACT` to the reviewed P11 load-plan path;
- requires the expected load-plan SHA-256
  `3da39530223f92e89d7129d447944d39199b6510eee473ba1e84ceeb168c9db1`;
- writes the review packet under the same artifact directory;
- applies mode `600` to the output packet;
- prints the packet path, output checksum, compact summary fields, planned row
  count, manual review item count, and whether the first review item has
  non-empty `planned_row` and `checks` objects.

This wrapper does not source DB environment variables, does not connect to a
database, and does not run imports, reconciliation, summarizer,
station-type dry-run, identity load, approval-record creation, or canonical
apply.

## Safety Boundaries

Safety boundaries for P12/P13:

- no production commands from Codex;
- no production DB access from Codex;
- no identity evidence load;
- no writes to `station_external_identity`;
- no imports;
- no reconciliation;
- no summarizer run against production artifacts;
- no station-type dry-run;
- no canonical apply;
- no approval record;
- no Stage 18K work.

The only future production action enabled by this repo work is a tiny
Hetzner-only offline review-packet generation step after merge.

## What This Does Not Approve

P12/P13 does not approve:

- loading the `20` planned rows;
- loading all `261938` eligible confirmed candidates;
- writing to `station_external_identity`;
- treating `confirmed_candidate` as production-confirmed identity;
- using identity candidates as station-type proof;
- running reconciliation against production artifacts;
- retrying station-type dry-run;
- creating an approval record;
- running canonical apply;
- starting Stage 18K.

## Required Future Load Boundaries

A later controlled identity load stage, if approved separately, must:

- consume only a manually reviewed packet;
- require exact source artifact checksum verification;
- require exact reviewed row identifiers/hashes;
- enforce a small max-row bound;
- write only to `station_external_identity`;
- write no canonical station fields;
- write no station-type fields;
- run in a transaction;
- report row counts before and after;
- preserve source run/file/hash provenance;
- create no approval record unless a separate approval stage explicitly
  defines that record.

No load stage may be combined with reconciliation, summarizer,
station-type dry-run, or canonical apply.

## Recommended Next Stages

Recommended sequence after this PR:

- run the P12/P13 review packet wrapper as a tiny Hetzner offline action;
- manually review every planned row in the generated packet;
- proceed to Chunk B / Stage 18J-P14 controlled identity load tooling only
  after the planned-row review is accepted;
- keep Chunk C, Chunk D, and Chunk E blocked until the controlled load is
  separately implemented, run, and reviewed.

## Final Recommendation

Accept the bounded load-plan artifact only as input to offline planned-row
manual review.

Do not load identity evidence yet. Keep identity writes, station-type writes,
canonical apply, approval-record creation, and Stage 18K blocked.

