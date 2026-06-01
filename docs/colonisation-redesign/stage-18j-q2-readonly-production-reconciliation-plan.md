# Stage 18J-Q2 — Read-Only Production Reconciliation Artifact Generation Plan

## Purpose

Stage 18J-Q2 defines the exact safe command path for generating the missing
production `enrichment_staging_reconciliation/v1` artifact that Stage 18J-P
needs before it can review a station-type production dry-run.

This stage is planning/report-only. No production-connected reconciliation
command was run in this stage, no production reconciliation artifact was
generated, no production station-type dry-run artifact was generated, no
production apply was run, and no production canonical data was modified.

The next executable step requires a separate explicit approval after
read-only/report-only DSN access is verified.

## Current Blocker

Stage 18J-Q found no suitable local or configured production
`enrichment_staging_reconciliation/v1` artifact. Stage 18J-P remains blocked
until an operator produces a verified report-only production reconciliation
artifact from already staged warehouse data.

Additional blocker: the current general reconciliation candidate payload
appears to expose `canonical.station_id` but not explicit `canonical.market_id`
or `canonical.edsm_station_id`. Stage 18J identity safety requires explicit
canonical external identity fields for eligible station-type candidates.
Without those fields, Stage 18J-P may still consume the artifact, but affected
candidates must be blocked rather than treated as stable identity matches.

## Required Artifact

The required artifact is a JSON report with:

- `schema_version = "enrichment_staging_reconciliation/v1"`.
- `dry_run = true`.
- `summary.canonical_writes_planned = 0`.
- `station_candidates` present, even if empty.
- `filters.source = "edsm_nightly_stations"`.
- `filters.source_run_key` matching the approved production source run.
- `filters.source_file_key` matching the approved production source file,
  unless a separately approved multi-file review scope is used.

For Stage 18J-P candidate evaluation, station candidates must include:

- `source.system_id64`.
- `source.market_id` or `source.edsm_station_id`.
- `source.station_name`.
- a `station_type` difference.
- `source.source_run_key`.
- `source.source_file_key`.
- `source.source_record_key`.
- `source.source_record_hash`.
- `canonical.station_id` as the database update target.
- explicit `canonical.market_id` or explicit `canonical.edsm_station_id` as
  external identity proof.
- `canonical.station_name`.
- `canonical.station_type`.

The artifact must remain a report-only input. It is not an apply artifact, not
an approval record, and not a production station-type dry-run artifact.

## Existing Tooling Review

The existing report generator is:

```text
apps/importer/src/enrichment_staging_db_loader.py --report-reconciliation
```

Code path:

```text
enrichment_staging_db_loader.main
-> build_reconciliation_report
-> EnrichmentWarehouseRepository.build_reconciliation_report
-> station_reconciliation_candidates / body_reconciliation_candidates / ring_reconciliation_candidates
-> enrichment_warehouse_sql.*_reconciliation_query
```

Safety properties already present in code/tests:

- `--report-reconciliation` requires a DSN and is a read-only report mode.
- `--report-reconciliation` cannot be combined with `--write-staging`.
- `--apply`, `--write`, and `--commit` fail closed in the staging loader.
- The report builder emits `enrichment_staging_reconciliation/v1`.
- The report builder emits `dry_run = true`.
- The report builder emits `summary.canonical_writes_planned = 0`.
- `tests/test_enrichment_staging_reconciliation.py` proves the CLI rejects
  write combinations and the generated SQL is read-only.
- `tests/test_enrichment_warehouse_boundary.py` proves reconciliation SELECTs
  from canonical tables are allowed while write/DDL SQL is rejected.

The command does not fetch EDSM, call live APIs, invoke Docker, or write
canonical tables. It reads already staged warehouse evidence and read-only
canonical comparison data.

## Proposed Read-Only Generation Path

Use the existing `--report-reconciliation` command against a verified
read-only/report-only warehouse DSN. The command should be run from the
production host or another approved operator environment with access to the
warehouse/report database.

The source should be restricted to `edsm_nightly_stations`, one approved source
run, and preferably one approved source file. Keep the first artifact bounded
with a reviewed limit, such as `1000`, unless an operator explicitly approves a
larger source scope.

The artifact can be generated from already staged warehouse data. It does not
require live EDSM/API crawling if the target source run/file is already staged.
If the source run/file is not staged, stop and use the existing offline
snapshot staging workflow in a separate approved operation; do not introduce a
live crawl in Stage 18J-Q2.

## Required Inputs

Required operator inputs:

- `EDFINDER_WAREHOUSE_READ_DSN`: secret read-only/report-only DSN.
- `SOURCE_RUN_KEY`: exact staged station source run key.
- `SOURCE_FILE_KEY`: exact staged station source file key.
- `SAFE_ARTIFACT_DIR`: operator-managed directory outside git.
- approved reconciliation row limit, initially recommended as `1000`.

Required data already present in the warehouse/report environment:

- `enrichment_source_runs`.
- `enrichment_source_files`.
- `enrichment_raw_records`.
- `staging_edsm_stations`.
- read-only canonical comparison data for `systems`, `stations`, and
  `station_body_links`, or equivalent snapshots/views if using the Stage 18I.5
  separate warehouse database direction.

The command does not need `EDFINDER_CANONICAL_APPLY_DSN`. That DSN must remain
unavailable for this stage.

## DSN / Access Safety Requirements

`EDFINDER_WAREHOUSE_READ_DSN` must use a dedicated read/report role. It must
not be:

- the app runtime DSN,
- a warehouse loader/write DSN,
- a canonical apply DSN,
- a database owner/superuser DSN,
- a role with write privileges on canonical tables.

Before the command is run in a later approved operation, the operator must
prove the DSN/access is read-only or report-only. Acceptable proof includes:

- role and database name recorded outside git,
- role grants reviewed by an operator,
- successful metadata-only privilege checks showing no INSERT/UPDATE/DELETE,
  TRUNCATE, CREATE, ALTER, DROP, or MERGE-equivalent privileges on canonical
  tables,
- no write privileges on warehouse tables for the read/report role, unless a
  separately approved report-artifact table exists,
- `PGOPTIONS='-c default_transaction_read_only=on'` or equivalent session
  read-only enforcement where supported,
- no access to `EDFINDER_CANONICAL_APPLY_DSN`.

If the deployment is still using the transitional same-database warehouse
layout, the read/report role must be extra constrained because warehouse and
canonical tables share a database boundary. The preferred future path remains
Stage 18I.5 Option B: a separate `edfinder_enrichment` warehouse database with
controlled canonical snapshots, read-only views, FDW, or immutable exports for
comparison.

## Command To Run Later

Do not run this command in Stage 18J-Q2.

After read-only access, source scope, and output location are explicitly
approved, the later operator command should be:

```sh
export EDFINDER_WAREHOUSE_READ_DSN='<secret-readonly-report-dsn>'
export SOURCE_RUN_KEY='<approved-source-run-key>'
export SOURCE_FILE_KEY='<approved-source-file-key>'
export SAFE_ARTIFACT_DIR='/var/lib/ed-finder/operator-artifacts/stage18j-q2'
export PGAPPNAME='stage18j-q2-readonly-reconciliation'
export PGOPTIONS='-c default_transaction_read_only=on'

mkdir -p "$SAFE_ARTIFACT_DIR"
chmod 700 "$SAFE_ARTIFACT_DIR"

.venv/bin/python apps/importer/src/enrichment_staging_db_loader.py \
    --report-reconciliation \
    --dsn "$EDFINDER_WAREHOUSE_READ_DSN" \
    --source edsm_nightly_stations \
    --source-run-key "$SOURCE_RUN_KEY" \
    --source-file-key "$SOURCE_FILE_KEY" \
    --limit 1000 \
    --json \
    > "$SAFE_ARTIFACT_DIR/enrichment-reconciliation-$SOURCE_RUN_KEY-$SOURCE_FILE_KEY.json"
```

The exact later command must be printed before execution and approved in that
future task. The approved command must not include `--write-staging`, `--apply`,
`--write`, `--commit`, `--confirm-staging-db`,
`--confirm-station-type-canonical-pilot`, rollback flags, Docker invocation, or
live API crawl flags.

## Pre-Run Safety Checklist

Before a later operator runs the command:

- Confirm this is a separate approved task to generate a report-only artifact.
- Confirm the command is `--report-reconciliation`.
- Confirm source is `edsm_nightly_stations`.
- Confirm `SOURCE_RUN_KEY` and `SOURCE_FILE_KEY` are the intended staged
  production source scope.
- Confirm staged warehouse data already exists for that source run/file.
- Confirm no live EDSM/API crawl is being invoked.
- Confirm no Docker command is being invoked from UI/API.
- Confirm the DSN is read-only/report-only and not a loader/app/apply DSN.
- Confirm session read-only enforcement is enabled where supported.
- Confirm output goes to an operator-managed path outside git.
- Confirm the raw artifact will not be committed by default.
- Confirm Stage 18T canonical safety CI remains green on the relevant branch.

Approval to run the command must come from the operator responsible for
production warehouse/report access. That approval is not approval for Stage
18J-P, not approval for a station-type dry-run artifact, and not approval for
apply.

## Artifact Contract Checks

After generation, the operator should validate the artifact offline before
Stage 18J-P:

- JSON parses successfully.
- `schema_version == "enrichment_staging_reconciliation/v1"`.
- `dry_run == true`.
- `summary.canonical_writes_planned == 0`.
- `station_candidates` exists.
- `filters.source == "edsm_nightly_stations"`.
- `filters.source_run_key == SOURCE_RUN_KEY`.
- `filters.source_file_key == SOURCE_FILE_KEY`.
- `errors` is empty.
- Candidate actions remain report-only review actions.
- No approval, apply, rollback, write, commit, or confirmation metadata is
  present as an executed production action.
- No DSNs, API keys, private host paths, usernames/passwords, or raw
  credentials appear in the artifact.
- Station candidates include the source and canonical identity fields required
  by Stage 18J-P.

If explicit `canonical.market_id` or `canonical.edsm_station_id` is absent,
the artifact may still document evidence, but Stage 18J-P must block affected
station-type candidates rather than treating `canonical.station_id` equality as
external identity proof.

## Output Location And Retention

Use an operator-managed location outside git, for example:

```text
/var/lib/ed-finder/operator-artifacts/stage18j-q2/
```

The raw artifact is production-sensitive and should not be committed by
default. Retain it with operator artifacts until Stage 18J-P review either
rejects it or creates a separate station-type dry-run artifact. If the artifact
is later summarized in a PR, include only sanitized counts, schema/version,
source run/file identifiers when safe, checksum when safe, and blocker notes.

Do not publish the raw artifact to a UI/API-mounted path unless the operator
has separately reviewed that exposure. The Admin warehouse status path
sanitizes a configured status artifact for display, but Stage 18J-Q2 does not
require publishing this raw production reconciliation artifact to the API.

## Secret / Path Sanitisation

The artifact and any summaries must omit:

- DSNs,
- database usernames/passwords,
- API keys and tokens,
- private host paths,
- SSH paths,
- local operator home directories,
- raw credentials,
- unreviewed raw source payload dumps.

If any of those appear, stop before Stage 18J-P and regenerate or sanitize the
artifact. Do not add the raw artifact to git.

## Stop Conditions

Stop before command execution if:

- read-only/report-only DSN access is not verified,
- source run/file scope is not approved,
- the command includes any write/apply/commit/confirm/rollback flag,
- the command would run a live EDSM/API crawl,
- the output path is inside the repo,
- the operator cannot prove which host/database will be read,
- the intended staged source run/file does not exist,
- Stage 18T canonical safety tests are failing.

Stop after artifact generation if:

- schema is not `enrichment_staging_reconciliation/v1`,
- `dry_run` is not `true`,
- `summary.canonical_writes_planned` is not `0`,
- `station_candidates` is missing,
- source filters do not match the approved source run/file,
- `errors` is non-empty,
- the artifact contains secrets, DSNs, private paths, or raw credentials,
- the artifact is treated as approval for station-type dry-run or apply,
- station candidates lack explicit canonical external identity fields and the
  Stage 18J-P review expects eligible candidates.

## Stage 18J-P Readiness Criteria

Stage 18J-P can resume only after:

- the production reconciliation artifact exists in an operator-managed path,
- the artifact passes all contract checks above,
- the artifact is confirmed report-only and production-sensitive,
- source run/file scope is recorded,
- any missing explicit canonical external identity fields are understood as a
  candidate-blocking condition,
- the Stage 18T canonical safety suite is green,
- a separate task explicitly authorizes Stage 18J-P dry-run review.

Stage 18J-P still must not approve production apply. Any future apply requires
a separate explicit instruction and approval naming the exact station-type
dry-run artifact hash, candidate count, table `stations`, field
`station_type`, source run/file, max row count, and apply DSN context.

## Recommendation

Do not run production reconciliation or Stage 18J-P in this stage.

The next executable action should be a separate, explicitly approved
read-only/report-only operation using the command above after the operator
proves the DSN/access boundary. The generated artifact should remain outside
git and be summarized only after it passes the contract checks.

Stage 18J-P remains blocked until that artifact exists and passes validation.

Stage 18J-Q3 attempted that artifact-generation step but stopped before any
production-connected command because the required verified read-only DSN,
approved source run/file, read-only session option, and operator-managed output
path were not available. See
[`stage-18j-q3-readonly-production-reconciliation-artifact.md`](./stage-18j-q3-readonly-production-reconciliation-artifact.md).
