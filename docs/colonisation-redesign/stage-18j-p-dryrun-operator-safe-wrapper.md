# Stage 18J-P-dryrun-ops - Operator-Safe Station-Type Dry-Run Wrapper

## Purpose

Stage 18J-P-dryrun-ops adds an operator-safe wrapper for the strict
station-type dry-run after Stage 18J-P-filter hardened eligibility. The wrapper
is for the Hetzner production operator shell only and keeps the dry-run bounded,
checksumed, compact, and outside git.

This stage does not run production commands, touch the production DB, run
imports, run reconciliation, run the summarizer against production artifacts,
run a production station-type dry-run, run canonical apply, create approval
records, start Stage 18J-P, or start Stage 18K.

## Operator Wrapper

New script:

```text
scripts/operator/stage18j_run_station_type_dry_run.sh
```

The script calls `scripts/operator/require_hetzner_operator_env.sh` before it
can operate. It requires the Hetzner host/path/Docker context, defaults to the
Stage 18J operator artifact directory, and writes the dry-run artifact under:

```text
/var/lib/ed-finder/operator-artifacts/stage-18j
```

Default input artifact basename:

```text
enrichment_staging_reconciliation_20260602T112948Z.json
```

Default expected SHA-256:

```text
0bacd62b7de0adf749b3c0de59ac3eebd4f67a6bea18eb96510d29f999935802
```

The wrapper verifies that checksum before running the dry-run tool. A checksum
mismatch stops the script.

## Bounded Dry-Run Controls

The wrapper uses `MAX_ROWS`, defaulting to the conservative first-pilot value
of `5`, and refuses values above `20`.

The wrapper never passes apply-mode or database connection arguments. It runs
the pilot tool in dry-run mode only and prints:

- output path,
- output artifact SHA-256,
- schema version,
- `dry_run`,
- `canonical_writes_planned`,
- total candidates seen,
- eligible station-type updates,
- eligible candidate count,
- blocked candidate count,
- rejection reason counts,
- artifact integrity checksum,
- source reconciliation artifact basename,
- source reconciliation artifact SHA-256,
- max-row bound,
- apply/approval flags.

## Compact Blocked-Candidate Output

`station_type_canonical_pilot.py` now supports:

```text
--blocked-candidate-sample-limit N
--quiet
```

The dry-run artifact keeps full counts and rejection reason distributions, but
only emits a capped sample of blocked candidates. Eligible candidates remain
included up to the explicit `--limit`.

The default blocked sample limit is `100`; the operator wrapper passes
`BLOCKED_CANDIDATE_SAMPLE_LIMIT`, also defaulting to `100`.

## Identity Coverage Diagnostics

Stage 18J-P2 adds `identity_coverage_summary` to future dry-run artifacts. The
summary is count-only and explains external identity coverage without including
raw payloads. It records source/canonical `market_id`, `edsm_station_id`,
`system_id64`, station-name, canonical match count, canonical station presence,
and possible missing canonical external IDs in the reconciliation payload.

The diagnostics do not relax the strict filter. They are intended to explain
why the bounded operator dry-run can produce zero eligible station-type updates
while still keeping `canonical_writes_planned = 0`.

## Output Contract

Dry-run output remains:

```text
station_type_canonical_pilot_dry_run/v1
```

The artifact records:

- `summary.canonical_writes_planned = 0`,
- `summary.apply_run = false`,
- `summary.approval_record_created = false`,
- `summary.total_candidates_seen`,
- `summary.eligible_station_type_updates`,
- `summary.blocked_candidates`,
- `summary.rejection_reason_counts`,
- `summary.blocked_candidate_samples_included`,
- `summary.blocked_candidate_samples_omitted`,
- `identity_coverage_summary`,
- `source_scope.input_artifact_basename`,
- `source_scope.input_artifact_sha256`,
- `artifact_integrity.canonical_json_sha256`.

Eligible rows are still dry-run review rows. They are not approval records and
not canonical apply instructions.

## Boundaries

The wrapper does not authorize Stage 18J-P from Codex or local dev. It is a
server-only operator script. Production artifacts remain private and must not
be committed.

Still not allowed in this stage:

- production dry-run execution from Codex,
- production DB access,
- imports,
- reconciliation,
- summarizer execution against production artifacts,
- canonical apply,
- approval record creation,
- Stage 18J-P,
- Stage 18K.

## Future Stage 18J-P Effect

After this stage merges, the future Stage 18J-P production dry-run can proceed
only when separately prompted for the Hetzner operator shell. That future step
must use the wrapper, the validated reconciliation checksum, an explicit
`MAX_ROWS` no greater than `20`, and compact blocked-candidate output.

This stage does not run that command.

## Final Recommendation

Merge this wrapper before asking the Hetzner operator to run the production
station-type dry-run. Then run Stage 18J-P only as a separate operator step and
review the resulting compact dry-run artifact before any approval packet or
apply discussion.
