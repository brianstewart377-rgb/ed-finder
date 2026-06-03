# Stage 18J-P10 — External Identity Candidate Artifact Review

## Purpose

Stage 18J-P10 reviews the read-only external station identity candidate
artifact generated on Hetzner from staged EDSM station evidence.

This stage is docs/review only. It does not run production commands from
Codex, touch the production database from Codex, load identity evidence, write
to `station_external_identity`, run imports, run reconciliation, run the
summarizer against production artifacts, run station-type dry-run, run
canonical apply, create approval records, or start Stage 18K.

## Artifact Reviewed

Reviewed artifact:

- artifact: `station_external_identity_candidates_20260603T002504Z.json`;
- path:
  `/var/lib/ed-finder/operator-artifacts/stage-18j/station_external_identity_candidates_20260603T002504Z.json`;
- size: `178K`;
- artifact SHA-256:
  `c306321e5bc22b864c9bfe09e92b407c3b407e25e2d4dce4b822e9613aa3b834`;
- artifact integrity SHA-256:
  `23f8208acef617249d1bd7d831834eb84a2a35deac103114b8940039a65efc65`;
- schema: `station_external_identity_candidates/v1`;
- source: `edsm_nightly_stations`;
- source run key:
  `6ad44d1ad04d53c958ba7f5877b01752a22e29d9e905627c7feba5bb9eca2db1`;
- source file key:
  `76f5c8aa5e55d267c96c16da026ff5cbfae58f1d63575d47759c9bf3aaa37c19`;
- total staged rows inspected: `298177`;
- sample candidates included: `100`.

## Read-only Safety Result

The artifact reports:

- `dry_run = true`;
- `read_only = true`;
- `report_only = true`;
- `canonical_writes_planned = 0`;
- `station_type_writes_planned = 0`;
- `identity_rows_written = 0`.

Post-checks recorded:

- `station_external_identity` row count before artifact generation: `0`;
- `station_external_identity` row count after artifact generation: `0`;
- no obvious credential/private path markers were found;
- no identity rows were loaded;
- no station-type dry-run was run;
- no canonical apply was run.

## Candidate Status Counts

The artifact classified candidates as:

| Status | Count |
|---|---:|
| `confirmed_candidate` | `261938` |
| `conflicting` | `258` |
| `rejected` | `35981` |
| `proposed` | `0` |

`confirmed_candidate` is a read-only artifact status. It means exactly one
canonical station matched by `system_id64` plus normalized station name and the
source evidence was complete enough for review. It does not mean the identity
has been approved, written, or made available as canonical external identity
proof.

## Source Identity Coverage

Source evidence coverage:

| Field | Count |
|---|---:|
| `source_edsm_station_id_present` | `298177` |
| `source_edsm_station_id_missing` | `0` |
| `source_market_id_present` | `0` |
| `source_market_id_missing` | `298177` |
| `source_station_name_present` | `298177` |
| `source_station_name_missing` | `0` |
| `source_system_id64_present` | `298177` |
| `source_system_id64_missing` | `0` |

Every staged row includes `edsm_station_id`, `station_name`, and `system_id64`.
No staged row includes `market_id`, so future load planning must preserve
`market_id = NULL` rather than inferring it from `stations.id` or
`station_body_links.market_id`.

## Canonical Match Coverage

Canonical match coverage:

| Match count bucket | Count |
|---|---:|
| `canonical_station_match_count_1` | `261938` |
| `canonical_station_match_count_0` | `35981` |
| `canonical_station_match_count_multiple` | `258` |

Match basis counts:

| Match basis | Count |
|---|---:|
| `system_id64_normalized_station_name` | `261938` |
| `no_canonical_station_match` | `35981` |
| `ambiguous_system_id64_normalized_station_name` | `258` |

## Conflict Findings

The artifact found `258` conflicting rows.

Conflict reason counts:

| Conflict reason | Count |
|---|---:|
| `ambiguous_canonical_station_match` | `258` |

These rows must remain blocked from confirmed identity use until a later review
resolves the ambiguity. They must not be overwritten by a bulk load and must
not be used as station-type proof.

## Rejected / Source-only Findings

The artifact found `35981` rejected rows with
`no_canonical_station_match`.

These rows have source identity evidence but no matching canonical station by
the required `system_id64` plus normalized station-name rule. They remain
source-only for this workflow. They are not eligible for confirmed identity and
must not be used to loosen the strict station-type filter.

## Interpretation

The artifact is useful and internally consistent as a review gate:

- it inspected the full staged EDSM station source scope;
- it found a large set of reviewable `confirmed_candidate` rows;
- it preserved source run/file/hash provenance and source `edsm_station_id`;
- it did not infer external identity from internal `stations.id`;
- it did not use `station_body_links.market_id` as general station identity;
- it surfaced ambiguous matches and source-only rows instead of silently
  promoting them.

The result is not sufficient to authorize a bulk identity evidence load yet.
The next step should translate the reviewed artifact into a bounded no-write
load-plan artifact before any insert into `station_external_identity`.

## Load Readiness Verdict

Ready only for bounded identity load dry-run.

The `261938` `confirmed_candidate` rows are promising, but they are still
artifact candidates. A future stage should first produce a bounded identity
load-plan artifact, preferably with a small explicit max-row sample and no
database writes, before any controlled insert into `station_external_identity`
is considered.

## Required Future Load Scope

The next load-planning stage should:

- use only the reviewed artifact hash and integrity hash recorded above;
- require the exact `source_run_key` and `source_file_key`;
- select a bounded max-row sample, not the full `261938` candidate set;
- plan writes only to `station_external_identity`;
- plan no writes to `stations`, `station_type`, or any canonical apply table;
- map `confirmed_candidate` to planned `identity_status = 'confirmed'` only
  in the load plan, not in production;
- keep `conflicting` rows blocked or explicitly planned as
  `identity_status = 'conflicting'` with `conflict_reason`;
- keep rejected/source-only rows out of confirmed identity;
- preserve source run/file/hash provenance for every planned row;
- keep `canonical_writes_planned = 0`;
- keep `station_type_writes_planned = 0`;
- keep `identity_rows_written = 0`.

Stage 18J-P11 implements this as
`apps/importer/src/station_external_identity_load_plan.py`, emitting
`station_external_identity_load_plan/v1` artifacts. The tool requires
`--max-rows`, rejects values above `20`, rejects write/apply/load flags, and
writes no database rows.

Stage 18J-P12/P13 then records the first bounded load-plan artifact review and
adds `apps/importer/src/station_external_identity_review_packet.py`. The
review packet tool verifies the exact load-plan artifact checksum, reads only
local JSON, accepts no DSN, caps planned rows at `20`, and emits
`station_external_identity_review_packet/v1` with each row defaulting to
`needs_manual_review`. The P12/P13 verdict is
`Ready only after planned-row manual review`.

## Required Operator Preconditions

Before any future bounded load-plan or controlled load stage, require:

- confirm the operation is a separately approved stage;
- confirm Codex/local prompts are not running production commands;
- confirm the Hetzner operator context and artifact path;
- confirm `station_external_identity` exists and record its row count;
- confirm the artifact SHA-256 and integrity SHA-256 match this review;
- confirm the source run/file filters match this review exactly;
- confirm no imports are running;
- confirm no reconciliation jobs are running;
- confirm no summarizer jobs are running;
- confirm no station-type dry-run is running;
- confirm no canonical apply is running;
- confirm no approval-record creation is part of the workflow;
- for any write stage, confirm backup/snapshot or explicit identity-table load
  risk acceptance.

## Required Post-load Checks

After a future controlled identity evidence load, require:

- `station_external_identity` row count matches the reviewed load report;
- counts by `identity_status` match the load report;
- all loaded rows preserve `source_run_key`, `source_file_key`, and
  `source_record_hash`;
- no loaded row lacks both `market_id` and `edsm_station_id`;
- conflicting rows have non-null `conflict_reason`;
- `stations` row count is unchanged;
- `station_type` data is unchanged;
- no imports, reconciliation, summarizer, station-type dry-run, or canonical
  apply were run as part of the load;
- no approval record was created;
- a follow-up identity coverage artifact can be generated from the identity
  table.

## What This Still Does Not Enable

P10 does not enable:

- production commands from Codex;
- production DB access from Codex;
- identity evidence loading;
- writes to `station_external_identity`;
- imports;
- reconciliation runs;
- summarizer runs against production artifacts;
- station-type dry-run;
- canonical apply;
- approval-record creation;
- changes to `stations`;
- changes to `station_type`;
- Stage 18K.

Strict station-type dry-run remains blocked until confirmed external identity
evidence is loaded in a later approved stage, reviewed through a coverage
artifact, and integrated into read-only reconciliation.

## Recommended Next Stages

- Stage 18J-P11 - Bounded external identity load-plan artifact, no DB writes.
- Stage 18J-P-OPT - Identity evidence execution board.
- Chunk A - P12/P13 review pack: review bounded load-plan artifact and
  generate planned-row review packet, no DB writes.
- Chunk B - P14 controlled identity load tooling.
- Chunk C - P15 post-load identity coverage.
- Chunk D - P16 read-only reconciliation integration with confirmed identity.
- Chunk E - P17 strict station-type dry-run retry.

## Final Recommendation

Use the reviewed P9 artifact as the basis for a bounded no-write load-plan
artifact only.

Do not bulk load the `261938` `confirmed_candidate` rows yet. Do not treat
`confirmed_candidate` as production-confirmed identity, and do not use it for
station-type writes. Proceed next with Stage 18J-P11 as a bounded identity
load-plan artifact with no database writes.

After P11, use the Stage 18J-P execution board to bundle repo work safely while
keeping each Hetzner production action tiny, explicit, and single-purpose.
