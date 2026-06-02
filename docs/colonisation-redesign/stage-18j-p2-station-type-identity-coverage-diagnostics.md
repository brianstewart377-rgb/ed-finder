# Stage 18J-P2 - Station-Type Identity Coverage Diagnostics

## Purpose

Stage 18J-P2 adds compact identity coverage diagnostics to the strict
station-type dry-run output. The first bounded Hetzner/operator dry-run was
safe and compact, but it found zero eligible station-type update candidates
because every station candidate failed external identity proof.

This stage is diagnostic/review tooling only. It does not run production
commands, touch the production DB, run imports, run reconciliation, run the
summarizer against production artifacts, run production station-type dry-run,
run canonical apply, create approval records, or start Stage 18K.

## Input Dry-Run Result

The operator dry-run artifact reported:

- schema: `station_type_canonical_pilot_dry_run/v1`
- dry-run artifact SHA-256:
  `29a95f910d86707d90ef4b1cbd393ca37831ed2cca9e320446ab0101fef3d4e7`
- source reconciliation artifact SHA-256:
  `0bacd62b7de0adf749b3c0de59ac3eebd4f67a6bea18eb96510d29f999935802`
- `canonical_writes_planned`: `0`
- `total_candidates_seen`: `298177`
- `eligible_station_type_updates`: `0`
- `blocked_candidates`: `298177`
- `blocked_candidate_samples_included`: `100`
- `max_row_bound`: `5`
- `apply_run`: `false`
- `approval_record_created`: `false`

The leading rejection count was:

- `rejected_missing_external_identity`: `298177`

That means the strict filter behaved safely, but it did not explain whether
the failure came from missing source IDs, missing canonical IDs, mismatched IDs,
system/name mismatches, ambiguous match counts, or omitted canonical external
IDs in the reconciliation payload.

## Diagnostic Output

`station_type_canonical_pilot.py` now emits
`identity_coverage_summary` in dry-run artifacts. The summary is compact,
deterministic, and count-only. It does not include raw payloads and does not
change candidate eligibility.

The summary records:

- source and canonical `market_id` presence,
- `market_id` matches and mismatches when both sides are present,
- source and canonical `edsm_station_id` presence,
- `edsm_station_id` matches and mismatches when both sides are present,
- source and canonical `system_id64` presence and mismatch counts,
- source and canonical station-name presence and mismatch counts,
- canonical match count distribution,
- canonical station presence,
- canonical station present while external IDs are absent from the
  reconciliation payload,
- possible omitted canonical external IDs in reconciliation payload,
- internal primary-key-only cases that remain insufficient identity proof,
- external identity proof present/absent counts.

## Eligibility Boundary

The diagnostics do not relax the strict filter. A candidate is still eligible
only when the existing Stage 18J-P-filter rules pass:

- update-only station candidate,
- station-type delta only,
- `source.market_id == canonical.market_id`, or
  `source.edsm_station_id == canonical.edsm_station_id`,
- exactly one canonical match,
- matching `system_id64`,
- matching normalized station name,
- no volatile evidence,
- no transient/non-slot station type,
- eligible canonical old value,
- explicit max-row bound.

Internal canonical `station_id` remains only the update target. It is never
accepted as identity proof.

## What The Next Diagnostic Rerun Should Answer

After this change merges, a separate Hetzner/operator bounded dry-run can
produce the new identity coverage summary. That rerun should answer:

- whether source `market_id` values are absent,
- whether canonical `market_id` values are absent from reconciliation output,
- whether both sides have `market_id` values but disagree,
- whether source `edsm_station_id` values are absent,
- whether canonical `edsm_station_id` values are absent from reconciliation
  output,
- whether both sides have `edsm_station_id` values but disagree,
- whether `system_id64` or station names fail the identity guard,
- whether canonical match counts are not exactly one,
- whether canonical station rows are present but external IDs are missing from
  the reconciliation payload.

## Boundaries

This stage creates no approval record and authorizes no apply. The dry-run
artifact remains review input only. `canonical_writes_planned` remains `0`,
`apply_run` remains `false`, and `approval_record_created` remains `false`.

Production rerun, if requested later, must still use the Hetzner operator
wrapper, the known reconciliation checksum, bounded `MAX_ROWS`, compact blocked
samples, and no apply arguments.

## Roadmap Impact

Stage 18J-P is not ready for any apply path. The next appropriate step after
merge is a separate bounded Hetzner/operator dry-run rerun for diagnostics
only. If the new identity coverage summary shows canonical external IDs are
missing from the reconciliation payload, the follow-up should inspect and
repair reconciliation identity payload coverage before considering any apply
approval packet.

Stage 18K remains not started.

## Final Recommendation

Merge the identity coverage diagnostics, then rerun the bounded Hetzner
station-type dry-run only as a separate operator-shell diagnostic step. Do not
create an approval packet or apply plan until the identity coverage summary is
reviewed and the source of the missing external identity proof is understood.
