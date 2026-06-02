# Stage 18J-P2 - Station-Type Identity Coverage Diagnostics

## Purpose

Stage 18J-P2 adds compact identity coverage diagnostics to the strict station-type dry-run output. The first bounded Hetzner/operator dry-run was safe and compact, but it found zero eligible station-type update candidates because every station candidate failed external identity proof.

This stage is diagnostic/review tooling only. It does not run production commands, touch the production DB, run imports, run reconciliation, run the summarizer against production artifacts, run production station-type dry-run, run canonical apply, create approval records, or start Stage 18K.

## Input Dry-Run Result

The operator dry-run artifact reported:

- schema: `station_type_canonical_pilot_dry_run/v1`
- dry-run artifact SHA-256: `29a95f910d86707d90ef4b1cbd393ca37831ed2cca9e320446ab0101fef3d4e7`
- source reconciliation artifact SHA-256: `0bacd62b7de0adf749b3c0de59ac3eebd4f67a6bea18eb96510d29f999935802`
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

That means the strict filter behaved safely, but it did not explain whether the failure came from missing source IDs, missing canonical IDs, mismatched IDs, system/name mismatches, ambiguous match counts, or omitted canonical external IDs in the reconciliation payload.

## Diagnostic Output

`station_type_canonical_pilot.py` now emits `identity_coverage_summary` in dry-run artifacts. The summary is compact, deterministic, and count-only. It does not include raw payloads and does not change candidate eligibility.

The summary records:

- source and canonical `market_id` presence,
- `market_id` matches and mismatches when both sides are present,
- source and canonical `edsm_station_id` presence,
- `edsm_station_id` matches and mismatches when both sides are present,
- source and canonical `system_id64` presence and mismatch counts,
- source and canonical station-name presence and mismatch counts,
- canonical match count distribution,
- canonical station presence,
- canonical station present while external IDs are absent from the reconciliation payload,
- possible omitted canonical external IDs in reconciliation payload,
- internal primary-key-only cases that remain insufficient identity proof,
- external identity proof present/absent counts.

## Production Finding After P2

The follow-up Hetzner/operator finding confirmed that canonical `stations` has no `market_id` or `edsm_station_id` columns. The attempted coverage query failed on missing `market_id`, and the P2 identity coverage reported:

- `source_edsm_station_id_present`: `298177`
- `canonical_edsm_station_id_present`: `0`
- `canonical_market_id_present`: `0`
- `external_identity_proof_present`: `0`
- `external_identity_proof_absent`: `298177`
- `canonical_station_present_but_external_ids_missing_in_payload`: `262579`
- `possible_canonical_external_ids_omitted_from_reconciliation_payload`: `262579`

The updated conclusion is that Stage 18J-P cannot produce eligible station-type update candidates until external station identity is modeled and populated safely. Re-running the same strict dry-run without canonical external identity available should continue to produce zero eligible rows.

## Eligibility Boundary

The diagnostics do not relax the strict filter. A candidate is still eligible only when the existing Stage 18J-P-filter rules pass:

- update-only station candidate,
- station-type delta only,
- `source.market_id == canonical.market_id`, or `source.edsm_station_id == canonical.edsm_station_id`,
- exactly one canonical match,
- matching `system_id64`,
- matching normalized station name,
- no volatile evidence,
- no transient/non-slot station type,
- eligible canonical old value,
- explicit max-row bound.

Internal canonical `station_id` remains only the update target. It is never accepted as identity proof.

## What The Diagnostics Answered

The P2 diagnostics answered the core question: the missing identity proof is not primarily source-side absence. Source EDSM station IDs are present in the source payload, but canonical external station IDs are absent from the canonical payload because canonical `stations` does not model them.

This shifts the next step from dry-run retry to identity-model design. See
`stage-18j-p3-canonical-external-station-identity-model.md` and the refined
schema design in
`stage-18j-p4-external-station-identity-schema-design.md`.

## Boundaries

This stage creates no approval record and authorizes no apply. The dry-run artifact remains review input only. `canonical_writes_planned` remains `0`, `apply_run` remains `false`, and `approval_record_created` remains `false`.

No follow-up should relax the identity filter or reinterpret internal primary keys as external proof. Production reruns, if requested later, must still use the Hetzner operator wrapper, the known reconciliation checksum, bounded `MAX_ROWS`, compact blocked samples, and no apply arguments.

## Roadmap Impact

Stage 18J-P is not ready for any apply path. Stage 18J-P3 identified the
external identity model gap, and Stage 18J-P4 designs the separate
provenance-backed `station_external_identity` table. The next appropriate
implementation step is a migration draft that is not applied to production,
followed by non-canonical evidence extraction, a read-only identity coverage
artifact, and confirmed identity integration into reconciliation output. Only
after that should the station-type dry-run be retried.

Stage 18K remains not started.

## Final Recommendation

Keep the strict filter. Do not create an approval packet or apply plan from the zero-eligible P2 result. Model external station identity separately, preserve provenance and conflict status, and retry station-type dry-run only after canonical external identity is available in read-only reconciliation output.
