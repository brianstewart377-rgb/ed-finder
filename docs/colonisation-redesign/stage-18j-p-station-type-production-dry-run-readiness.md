# Stage 18J-P — Station Type Production Dry-Run Readiness

## Purpose

Stage 18J-P prepares for a possible future production station-type pilot by
reviewing whether a production dry-run artifact can be generated safely from an
existing report-only reconciliation artifact.

This report is dry-run readiness documentation only. No production apply was
run, no production canonical data was modified, no production approval was
granted, and no production canonical artifact was approved. Any future apply
requires a separate explicit instruction and approval.

## Preconditions

Confirmed:

- PR #104 was merged into `main`.
- Stage 18J station type canonical pilot code is present on `origin/main` at
  merge commit `acf7b88222ac1f0d20136815aa741f48dd426ec6`.
- The pilot tool defaults to dry-run and requires a reconciliation report
  artifact for dry-run mode.
- The apply path remains guarded and requires explicit artifact checksum,
  candidate count, table, field, source run, approval reference,
  confirmation, max row count, and DSN.
- The production cap remains tiny: default 5 and max 20 unless a later stage
  changes it.

Blocked or missing:

- No suitable production `enrichment_staging_reconciliation/v1` JSON artifact
  was found locally.
- The requested non-production rehearsal document
  `docs/colonisation-redesign/stage-18j-r-station-type-nonprod-rehearsal.md`
  was not present on `origin/main` at review time.
- Because no suitable reconciliation artifact was available, Stage 18J-P could
  not generate a production dry-run artifact safely in this pass.

## Commands Reviewed

The Stage 18J dry-run command reviewed for future use is:

```sh
.venv/bin/python apps/importer/src/station_type_canonical_pilot.py \
    --reconciliation-report <reviewed-production-reconciliation.json> \
    --output <operator-artifact-root>/stage18j-p-station-type-dry-run.json \
    --limit 5 \
    --json
```

Safety review for this command:

- It is dry-run mode because `--apply` is absent.
- It has no `--confirm-station-type-canonical-pilot` flag.
- It has no `--write`, `--commit`, `--rollback`, or rollback-apply flag.
- It does not accept a DSN in dry-run mode.
- It reads a local reconciliation artifact and writes only a local dry-run
  output artifact.
- It cannot be run until the input reconciliation artifact is confirmed to be
  report-only, production-safe for review, and free of secrets, DSNs, private
  paths, and unredacted sensitive data.

The report-only reconciliation command that may be needed before a future
Stage 18J-P run is:

```sh
.venv/bin/python apps/importer/src/enrichment_staging_db_loader.py \
    --report-reconciliation \
    --dsn "$EDFINDER_WAREHOUSE_READ_DSN" \
    --source edsm_nightly_stations \
    --source-run-key "$SOURCE_RUN_KEY" \
    --source-file-key "$SOURCE_FILE_KEY" \
    --limit 1000 \
    --json
```

This command was reviewed but not run. It is production-connected and must not
be run until the DSN/access is verified as read-only/report-only and the source
run/file scope is approved for review.

## Commands Run

Repository setup and inspection:

```sh
git switch main
git branch backup/local-main-ee6f546-map-refactor || true
git status --short --branch
git fetch origin main
git switch -c stage-18j-p-station-type-production-dry-run origin/main
git log --oneline -12
```

Artifact discovery:

```sh
rg -l '"schema_version"\s*:\s*"enrichment_staging_reconciliation/v1"|enrichment_staging_reconciliation/v1' . \
    --glob '*.json' --glob '*.jsonl' --glob '*.md' \
    --glob '!frontend-v2/node_modules/**' --glob '!.git/**' --glob '!frontend-v2/.git/**'

find . -maxdepth 4 -type f \( -name '*reconciliation*.json' -o -name '*warehouse*.json' -o -name '*stage18j*.json' -o -name '*station*pilot*.json' \) \
    -printf '%TY-%Tm-%Td %TH:%TM %p\n'

find /home/brian -maxdepth 5 -type f \( -name '*reconciliation*.json' -o -name '*warehouse*.json' -o -name '*stage18j*.json' -o -name '*station*pilot*.json' \) \
    -printf '%TY-%Tm-%Td %TH:%TM %p\n'
```

No production-connected command was run. No Stage 18J apply command was run.

## Source Artifact / Source Run

No source reconciliation artifact was available.

- Source artifact path: not available.
- Source run key: not available.
- Source file key: not available.
- Source: not available.
- Artifact suitability: blocked pending a reviewed
  `enrichment_staging_reconciliation/v1` report.

Stage 18J-P cannot proceed to production dry-run generation until a suitable
report-only reconciliation artifact exists.

## Dry-Run Artifact

No production dry-run artifact was generated in this pass.

Reason: the Stage 18J pilot tool requires an existing reconciliation report
artifact in dry-run mode, and no suitable production reconciliation artifact was
found. Generating a new production reconciliation report would require a
production-connected read/report command, and no read-only DSN/access context
was available to verify.

## Artifact Checksum

No dry-run artifact checksum exists for this pass.

Any future apply must approve the exact dry-run artifact hash before apply.
The artifact hash must be recomputed from canonical JSON and must match the
artifact's embedded `artifact_integrity.canonical_json_sha256`.

## Candidate Summary

Candidate counts were not produced because no production dry-run artifact was
generated.

| Metric | Value |
|---|---:|
| Eligible candidates at limit 5 | Not available |
| Blocked candidates | Not available |
| Top blocking reasons | Not available |
| Candidate count approved for apply | None |

## Eligible Candidate Review

No eligible candidates were produced or reviewed.

Before any future apply, every eligible candidate must be manually reviewed and
must show:

- `canonical_table = "stations"`.
- `field = "station_type"`.
- `canonical.station_type` is unknown/empty/eligible under the narrow rule.
- `new_value` is an approved permanent station type.
- `match_proof.identifier_match_type` is `market_id`, or `edsm_station_id`
  only when explicitly allowed.
- The source and canonical external identity values match on explicit fields.
- The candidate count is small enough for complete manual review.

## Blocked Candidate Summary

No blocked candidate distribution was produced because no production dry-run
artifact was generated.

Future review should inspect `summary.blocked_by_reason` and confirm every
high-count blocking reason is expected. Unknown, source-only, stale, volatile,
risky, blocked, missing identity, missing external canonical identity, and
report-only evidence must remain blocked.

## Identity Safety Review

The merged Stage 18J pilot code enforces the important identity boundary:

- `source.market_id` matches explicit `canonical.market_id` only.
- `source.edsm_station_id` matches explicit `canonical.edsm_station_id` only
  when the EDSM flag is used.
- `canonical.station_id` is treated as the internal database primary key and
  update target, not as external identity proof.
- Internal primary key equality alone cannot satisfy stable identity.
- Missing canonical external identity fields block the candidate.

No production candidates were available to verify against these rules in this
pass.

## Existing Canonical Value Review

No production eligible candidates were available to inspect.

Future review must confirm that no known canonical station type is overwritten
by default. Current known station types must block unless a later explicitly
approved rule changes that behavior. The first pilot should promote only
unknown, blank, or otherwise explicitly eligible old values.

## Risk / Freshness / Source Notes

No production source freshness, risk, or blocking distribution was available.

Future review must confirm:

- `risk_class = clear` for every eligible candidate.
- `reconciliation_state = confirmed` for every eligible candidate.
- `report_only` evidence is not selected.
- stale, volatile, risky, source-only, unknown, and blocked classifications are
  not selected.
- source run key, source file key, source record key/hash, and source freshness
  are present.
- missing or undated source evidence is either blocked or covered by a
  separately approved freshness exception.

## Manual Approval Requirements

No approval was granted in this pass.

Any future apply requires a separate explicit instruction and approval. That
approval must name:

- the exact dry-run artifact hash,
- the exact candidate count,
- the exact table `stations`,
- the exact field `station_type`,
- the exact source run,
- the exact source file unless a multi-file scope is explicitly approved,
- the maximum row count,
- the approval reference,
- the guarded apply command and DSN context.

The production cap remains tiny: default 5 and max 20 unless a later stage
changes it.

## Stop Conditions

Stop before dry-run generation if:

- no suitable report-only reconciliation artifact exists,
- the reconciliation artifact contains secrets, DSNs, private paths, or
  unredacted sensitive data,
- source run/file scope is unclear,
- the artifact schema is not `enrichment_staging_reconciliation/v1`,
- the report omits `canonical_writes_planned = 0`,
- a production-connected reconciliation command is needed but read-only access
  cannot be verified.

Stop before any future apply if:

- the dry-run artifact checksum mismatches,
- candidate count mismatches,
- approved table/field/source run/source file mismatches,
- max row count is missing or too high,
- current canonical pre-image differs,
- any selected candidate is source-only, stale, volatile, risky, blocked,
  unknown, report-only, ambiguous, or identity-unsafe,
- any write would target a table or field outside `stations.station_type`,
- post-apply verification cannot be emitted and reviewed.

## Production Apply Status

Production apply status: not authorized and not run.

- No production apply was run.
- No guarded apply was run against production.
- No production canonical data was modified.
- No production approval record was created.
- No rollback was run.
- No production canonical artifact was approved.
- No Stage 18K or broader canonical work was started.

The artifact status for this pass is blocked: no production dry-run artifact
was generated.

## Recommendation

Do not proceed to production apply.

Stage 18J-P should remain blocked until an operator supplies or generates a
safe report-only production reconciliation artifact using verified read-only
access. Once that artifact exists, rerun the Stage 18J dry-run command with
`--limit 5`, review every eligible candidate manually, and approve nothing
until the exact artifact hash, candidate count, table, field, source run/file,
and max row count are explicitly accepted.
