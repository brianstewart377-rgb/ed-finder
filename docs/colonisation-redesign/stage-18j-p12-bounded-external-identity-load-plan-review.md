# Stage 18J-P12 — Bounded External Identity Load-Plan Review

## Purpose

Stage 18J-P12 reviews the bounded no-write external station identity load-plan
artifact generated on Hetzner after Stage 18J-P11.

This stage is docs/review only. It does not run production commands from
Codex, touch the production database from Codex, load identity evidence, write
to `station_external_identity`, run imports, run reconciliation, run the
summarizer against production artifacts, run station-type dry-run, run
canonical apply, create approval records, or start Stage 18K.

## Artifact Reviewed

Reviewed artifact:

- artifact type: `station_external_identity_load_plan/v1`;
- path:
  `/var/lib/ed-finder/operator-artifacts/stage-18j/station_external_identity_load_plan_20260603T071913Z.json`;
- size: `349K`;
- artifact SHA-256:
  `3da39530223f92e89d7129d447944d39199b6510eee473ba1e84ceeb168c9db1`;
- artifact integrity SHA-256:
  `f8cf7260425ba82b1fc476d3cd239dbf41e2b246040ad9b461750ae4322a544f`;
- source: `edsm_nightly_stations`;
- source run key:
  `6ad44d1ad04d53c958ba7f5877b01752a22e29d9e905627c7feba5bb9eca2db1`;
- source file key:
  `76f5c8aa5e55d267c96c16da026ff5cbfae58f1d63575d47759c9bf3aaa37c19`;
- max rows: `20`.

## Safety Result

The artifact reports:

- `dry_run = true`;
- `read_only = true`;
- `report_only = true`;
- `canonical_writes_planned = 0`;
- `station_type_writes_planned = 0`;
- `identity_rows_planned = 20`;
- `identity_rows_written = 0`.

Post-checks recorded:

- secret/path sanity check: clean;
- `station_external_identity` row count after artifact generation: `0`;
- no identity rows were loaded;
- no station-type dry-run was run;
- no canonical apply was run.

The artifact is safe as a no-write planning artifact. It does not approve or
perform any insert into `station_external_identity`.

## Load-Plan Counts

Summary counts:

| Field | Count |
|---|---:|
| `total_candidates_seen` | `298177` |
| `eligible_confirmed_candidates_seen` | `261938` |
| `planned_rows_count` | `20` |
| `identity_rows_written` | `0` |

The bounded plan selected only the first `20` eligible confirmed candidates for
review. It did not plan the full eligible candidate set.

## Planned Row Scope

The planned row scope is intentionally small:

- planned rows in artifact: `20`;
- sample non-planned candidates in artifact: `100`;
- `max_rows = 20`;
- source is restricted to `edsm_nightly_stations`;
- source run/file filters match the reviewed Stage 18J-P10 candidate artifact;
- planned rows are intended as candidate `station_external_identity` inserts
  for manual review only;
- planned rows do not imply station-type canonical truth;
- planned rows do not authorize station-type writes.

The artifact can support a later manual review packet, but it is not itself
the approval packet for a controlled insert.

## Skipped / Rejected Counts

Skipped and rejected reason counts:

| Reason | Count |
|---|---:|
| `eligible_beyond_max_rows` | `261918` |
| `source_only_no_canonical_station_match` | `35981` |
| `ambiguous_canonical_station_match` | `258` |

The `eligible_beyond_max_rows` rows remain unplanned only because of the
bounded first-review cap. The source-only and ambiguous rows remain blocked
from confirmed identity use.

## Candidate Status Counts

Candidate status counts:

| Status | Count |
|---|---:|
| `confirmed_candidate` | `261938` |
| `conflicting` | `258` |
| `proposed` | `0` |
| `rejected` | `35981` |

`confirmed_candidate` remains a planning status from the read-only matching
workflow. It is not a production-confirmed external identity row until a later
controlled load writes reviewed rows to `station_external_identity`.

## Artifact Integrity

The artifact includes both file-level and internal integrity checks:

- file SHA-256:
  `3da39530223f92e89d7129d447944d39199b6510eee473ba1e84ceeb168c9db1`;
- artifact integrity SHA-256:
  `f8cf7260425ba82b1fc476d3cd239dbf41e2b246040ad9b461750ae4322a544f`.

Any future review or load stage must reference these exact hashes and source
filters. A mismatch means the planned rows are not the reviewed P12 rows.

## What Was Not Run

P12 records that:

- no production commands were run from Codex;
- no production DB was touched from Codex;
- no identity evidence was loaded;
- no writes to `station_external_identity` occurred;
- no imports were run;
- no reconciliation was run;
- no summarizer was run against production artifacts;
- no station-type dry-run was run;
- no canonical apply was run;
- no approval record was created;
- Stage 18K was not started.

## Readiness Verdict

Ready only after extra review.

The artifact safely planned only `20` rows and wrote `0` rows. That is enough
to proceed to a manual planned-row review packet, but it is not enough to
authorize loading those rows. The planned rows themselves must be reviewed
before any future insert into `station_external_identity`.

## Required Manual Review

Before any controlled identity evidence load, require a manual review packet
that checks every planned row:

- canonical station ID is the intended station;
- `system_id64` matches the intended canonical system;
- station name is the intended source/canonical station;
- source is `edsm_nightly_stations`;
- at least one external ID is present;
- no `market_id` is inferred from `stations.id`;
- no `station_body_links.market_id` is used as general identity proof;
- source run/file/hash provenance is present;
- `identity_status = 'confirmed'` is appropriate for the selected row;
- `conflict_reason = null` is appropriate;
- no row implies station-type truth;
- no row is ambiguous, rejected, proposed, or source-only.

## Required Future Load Boundaries

A future controlled load stage must:

- be separately approved after manual planned-row review;
- reference this artifact path and both recorded hashes;
- load only reviewed planned rows;
- write only to `station_external_identity`;
- preserve source run/file/hash provenance;
- keep `stations` unchanged;
- keep `station_type` unchanged;
- create no approval record unless a later explicit stage asks for one;
- run no imports;
- run no reconciliation;
- run no summarizer;
- run no station-type dry-run;
- run no canonical apply;
- produce post-load row-count and status-count checks.

## Recommended Next Stages

- Stage 18J-P13 - Planned identity row manual review packet.
- Stage 18J-P14 - Controlled identity evidence load of reviewed rows only.
- Stage 18J-P15 - Post-load identity coverage artifact.
- Stage 18J-P16 - Reconciliation integration with confirmed identity.
- Stage 18J-P17 - Retry strict station-type dry-run.

## Final Recommendation

Proceed only to a planned-row manual review packet.

Do not load the `20` planned rows yet. The load-plan artifact is safe and
bounded, but the row contents must be manually reviewed before any controlled
insert into `station_external_identity`. Keep station-type dry-run and
canonical apply blocked.
