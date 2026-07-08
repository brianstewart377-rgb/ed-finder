# Stage 18J-P12 bounded external identity load-plan review

This document is historical evidence only.
It is not current operational guidance.
For current project state, use docs/colonisation-redesign/stage-19-state-authority.json.
Stage 19 is currently paused.
Stage 19AS-AU has not run.
Do not use this document to authorize writes, canonical apply, production DB actions, or Stage 19 execution.

## Archive source

This archive preserves useful historical documentation from PR #133:

- PR: https://github.com/brianstewart377-rgb/ed-finder/pull/133
- Branch: `stage-18j-p12-bounded-external-identity-load-plan-review`
- Head: `3a617fc1c3c69dc65cf007027f8e4ff4263ffb93`
- Original title: `Stage 18J-P12 bounded external identity load-plan review`

The original PR also changed active roadmap and runbook files. Those active sequencing updates are intentionally not restored here as current guidance.

## Historical purpose

Stage 18J-P12 reviewed a bounded no-write external station identity load-plan artifact generated on Hetzner after Stage 18J-P11.

The original review was docs/review only. It recorded that it did not run production commands from Codex, touch the production database from Codex, load identity evidence, write to `station_external_identity`, run imports, run reconciliation, run the summarizer against production artifacts, run station-type dry-run, run canonical apply, create approval records, or start Stage 18K.

## Historical artifact reviewed

| Field | Historical value |
|---|---|
| Artifact type | `station_external_identity_load_plan/v1` |
| Path | `/var/lib/ed-finder/operator-artifacts/stage-18j/station_external_identity_load_plan_20260603T071913Z.json` |
| Size | `349K` |
| Artifact SHA-256 | `3da39530223f92e89d7129d447944d39199b6510eee473ba1e84ceeb168c9db1` |
| Artifact integrity SHA-256 | `f8cf7260425ba82b1fc476d3cd239dbf41e2b246040ad9b461750ae4322a544f` |
| Source | `edsm_nightly_stations` |
| Source run key | `6ad44d1ad04d53c958ba7f5877b01752a22e29d9e905627c7feba5bb9eca2db1` |
| Source file key | `76f5c8aa5e55d267c96c16da026ff5cbfae58f1d63575d47759c9bf3aaa37c19` |
| Max rows | `20` |

## Historical safety result

The artifact reported:

- `dry_run = true`;
- `read_only = true`;
- `report_only = true`;
- `canonical_writes_planned = 0`;
- `station_type_writes_planned = 0`;
- `identity_rows_planned = 20`;
- `identity_rows_written = 0`.

The original review recorded these post-checks:

- secret/path sanity check: clean;
- `station_external_identity` row count after artifact generation: `0`;
- no identity rows were loaded;
- no station-type dry-run was run;
- no canonical apply was run.

Historical conclusion: the artifact was safe as a no-write planning artifact. It did not approve or perform any insert into `station_external_identity`.

## Historical load-plan counts

| Field | Count |
|---|---:|
| `total_candidates_seen` | `298177` |
| `eligible_confirmed_candidates_seen` | `261938` |
| `planned_rows_count` | `20` |
| `identity_rows_written` | `0` |

The bounded plan selected only the first `20` eligible confirmed candidates for review. It did not plan the full eligible candidate set.

## Historical planned row scope

The original planned row scope was intentionally small:

- planned rows in artifact: `20`;
- sample non-planned candidates in artifact: `100`;
- `max_rows = 20`;
- source was restricted to `edsm_nightly_stations`;
- source run/file filters matched the reviewed Stage 18J-P10 candidate artifact;
- planned rows were candidate `station_external_identity` inserts for manual review only;
- planned rows did not imply station-type canonical truth;
- planned rows did not authorize station-type writes.

The original artifact could support a later manual review packet, but it was not itself an approval packet for a controlled insert.

## Historical skipped and rejected counts

| Reason | Count |
|---|---:|
| `eligible_beyond_max_rows` | `261918` |
| `source_only_no_canonical_station_match` | `35981` |
| `ambiguous_canonical_station_match` | `258` |

The `eligible_beyond_max_rows` rows remained unplanned only because of the bounded first-review cap. The source-only and ambiguous rows remained blocked from confirmed identity use.

## Historical candidate status counts

| Status | Count |
|---|---:|
| `confirmed_candidate` | `261938` |
| `conflicting` | `258` |
| `proposed` | `0` |
| `rejected` | `35981` |

`confirmed_candidate` was a planning status from the read-only matching workflow. It was not a production-confirmed external identity row.

## Historical artifact integrity

The artifact included both file-level and internal integrity checks:

- file SHA-256: `3da39530223f92e89d7129d447944d39199b6510eee473ba1e84ceeb168c9db1`;
- artifact integrity SHA-256: `f8cf7260425ba82b1fc476d3cd239dbf41e2b246040ad9b461750ae4322a544f`.

The original review stated that any later review or load stage had to reference these exact hashes and source filters. That statement is preserved as historical context only and is not current authorization to run a load.

## Historical not-run list

P12 recorded that:

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

## Historical readiness verdict

The original verdict was: `Ready only after extra review`.

The artifact safely planned only `20` rows and wrote `0` rows. The original review said that was enough to proceed to a manual planned-row review packet, but not enough to authorize loading those rows. The planned rows themselves still needed review before any future insert into `station_external_identity`.

## Historical manual review boundaries

The original review said that before any controlled identity evidence load, a manual review packet should check every planned row:

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

These checks are preserved as historical safety context only. They do not authorize current writes, current production DB work, canonical apply, or Stage 19 execution.

## Stale sequencing caveat

The original PR included recommended next stages and active roadmap/runbook edits for Stage 18J-P13 through Stage 18J-P17. Those old sequencing updates are not restored as current guidance.

Current project state is governed by `docs/colonisation-redesign/stage-19-state-authority.json`: Stage 19 is paused, Stage 19AS-AU has not run, and this archive recovery did not execute Stage 19.

