# Stage 18J-P-filter - Strict Station-Type Dry-Run Filter

## Purpose

Stage 18J-P-filter hardens the station-type dry-run candidate filter before any
future Stage 18J-P production dry-run retry. It converts the Stage 18J-Q9
readiness verdict, `Ready only with strict filter`, into code-level dry-run
eligibility rules and synthetic test coverage.

This stage does not run production commands, touch the production DB, run
imports, run reconciliation, run the summarizer against production artifacts,
run a production station-type dry-run, run canonical apply, create approval
records, start Stage 18J-P, or start Stage 18K.

## Inputs

Stage 18J-Q9 reviewed the compact reconciliation summary and found:

- `298177` station candidates,
- `163722` station candidate updates,
- `35340` source-only missing-canonical candidates,
- `98857` no-change candidates,
- `258` ambiguous matches,
- `298177` station/body association candidates blocked by missing body names,
- volatile evidence present,
- `15014` high-confidence rows.

Those counts show that the full station reconciliation candidate set is too
broad for a production station-type dry-run. The future retry must be bounded
and filtered before an operator runs it.

## Filter Contract

The station-type dry-run planner now requires:

- explicit external station identity proof by matching `source.market_id` to
  `canonical.market_id`, or matching `source.edsm_station_id` to
  `canonical.edsm_station_id`;
- no identity proof from internal canonical `station_id` or primary-key
  equality alone;
- exactly one canonical station match;
- `candidate_action = candidate_update`;
- `stations.station_type` as the only target field;
- a present station-type delta;
- a permanent colony-slot station type;
- no fleet carrier, megaship, transient, mobile, or non-slot station type;
- no source-only insert candidate;
- no volatile evidence;
- no station/body association writes;
- no non-station-type canonical writes;
- a required explicit max-row bound.

Missing `station_body_name` remains a station/body-link blocker, but it no
longer blocks an otherwise externally proven station-type comparison. This
keeps station-type comparison separate from station/body association work.

## Rejection Reasons

Every excluded station candidate receives machine-readable rejection reasons.
The dry-run summary includes these counts:

- `total_candidates_seen`
- `eligible_station_type_updates`
- `rejected_ambiguous_identity`
- `rejected_source_only_insert`
- `rejected_missing_external_identity`
- `rejected_volatile_evidence`
- `rejected_transient_non_slot`
- `rejected_non_station_type_change`
- `rejected_missing_station_type_delta`
- `rejected_ineligible_canonical_old_value`
- `rejected_missing_provenance`
- `rejected_freshness`
- `rejected_by_max_row_bound`

The artifact keeps `rejection_reason_counts` and the legacy
`blocked_by_reason` map aligned so existing review flows can still inspect the
distribution.

## Dry-Run Output

The dry-run artifact remains `station_type_canonical_pilot_dry_run/v1` and is
still deterministic. It now records the input reconciliation artifact basename,
size, and SHA-256 when invoked through the CLI, so a future operator review can
tie the dry-run to the exact read-only reconciliation artifact.

The dry-run output explicitly records:

- `dry_run = true`,
- `summary.canonical_writes_planned = 0`,
- `summary.total_candidates_seen`,
- `summary.eligible_station_type_updates`,
- `summary.rejection_reason_counts`,
- `summary.apply_run = false`,
- `summary.approval_record_created = false`,
- `operator_review.production_artifact_approved = false`.

Eligible rows are reported as `eligible_station_type_updates`; they are not
canonical writes, approval records, or apply instructions.

Stage 18J-P-dryrun-ops adds compact blocked-candidate output controls so the
future operator dry-run does not emit every blocked row from the large
production reconciliation artifact. The dry-run artifact keeps all counts and
rejection distributions, includes eligible rows up to the explicit limit, and
caps blocked row samples through `--blocked-candidate-sample-limit`.

## Tests

Synthetic tests cover:

- market ID external identity qualifies;
- EDSM station ID external identity qualifies;
- internal primary-key-only matching does not qualify;
- ambiguous matches are rejected;
- source-only insert candidates are rejected;
- missing `station_body_name` does not block externally proven station-type
  comparison;
- missing `station_body_name` remains blocked for station/body-link candidates;
- volatile evidence is rejected;
- fleet carriers and megaships are rejected as transient/non-slot;
- non-station-type changes are rejected;
- an explicit max-row bound is required;
- rejection reason counts are present;
- `canonical_writes_planned` remains `0`;
- the dry-run path does not invoke apply.

## Boundaries

This stage does not authorize Stage 18J-P. It only hardens the local code and
tests so a future operator command can be reviewed against the strict filter.

Still blocked:

- production station-type dry-run,
- canonical apply,
- approval record creation,
- station/body association writes,
- Stage 18J-P,
- Stage 18K.

## Future Stage 18J-P Effect

After this stage merges, a future Stage 18J-P production dry-run can proceed
only when separately prompted in the Hetzner operator shell, after the
operator-safe wrapper has merged, and only with:

- the reviewed production reconciliation artifact,
- the explicit max-row bound,
- the recorded source artifact checksum,
- compact/reviewable dry-run output,
- no approval record,
- no canonical apply.

Stage 18J-P remains blocked until that separate operator step is requested.

## Final Recommendation

Merge the strict filter hardening before retrying Stage 18J-P. After merge, the
future production dry-run is technically eligible to proceed as a separate
operator step, but it is not started or approved by this stage.
