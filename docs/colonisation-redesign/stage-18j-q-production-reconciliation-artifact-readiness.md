# Stage 18J-Q — Production Reconciliation Artifact Readiness

## Purpose

Stage 18J-Q prepares the missing prerequisite for Stage 18J-P: a verified,
read-only/report-only production `enrichment_staging_reconciliation/v1`
artifact that could later be used as input to the Stage 18J station type
production dry-run review.

This stage is artifact-readiness only. No production apply was run, no guarded
apply was run, no production canonical data was modified, no production
approval record was created, no production station-type dry-run artifact was
approved, and no Stage 18K or broader canonical work was started.

## Preconditions

Confirmed from the current `origin/main` branch:

- PR #107 is merged at `be2348dfda57274658876be9fdd78333b0b36401`.
- The Stage 18J station type canonical pilot exists, but production apply is
  not authorized.
- The Stage 18T canonical safety test environment is present and requires the
  Stage 18J safety suite in CI.
- Stage 18J-P remains blocked until a suitable report-only production
  reconciliation artifact exists.
- The requested Stage 18J-R non-production rehearsal document
  `docs/colonisation-redesign/stage-18j-r-station-type-nonprod-rehearsal.md`
  is still absent on `origin/main`.

No production-connected command was run during this review.

## Artifact Search

Local artifact discovery was limited to filesystem inspection and did not
connect to production:

```sh
rg -l '"schema_version"\s*:\s*"enrichment_staging_reconciliation/v1"|enrichment_staging_reconciliation/v1' \
    /home/brian/Documents/GitHub/ed-finder /home/brian/.codex /tmp \
    --glob '*.json' --glob '*.jsonl' --glob '*.md' \
    --glob '!frontend-v2/node_modules/**' --glob '!node_modules/**' --glob '!.git/**'

find /home/brian/Documents/GitHub/ed-finder /home/brian/.codex /tmp -maxdepth 5 -type f \
    \( -name '*reconciliation*.json' -o -name '*warehouse*.json' -o -name '*stage18j*.json' -o -name '*station*pilot*.json' \) \
    -printf '%TY-%Tm-%Td %TH:%TM %p\n'
```

Configured artifact-path checks:

```sh
if [ -n "${ENRICHMENT_WAREHOUSE_STATUS_JSON_PATH:-}" ]; then
    printf 'ENRICHMENT_WAREHOUSE_STATUS_JSON_PATH is set locally\n'
else
    printf 'ENRICHMENT_WAREHOUSE_STATUS_JSON_PATH is not set locally\n'
fi

if [ -f /data/logs/warehouse-status.json ]; then
    printf '/data/logs/warehouse-status.json exists\n'
else
    printf '/data/logs/warehouse-status.json not found\n'
fi
```

Search result:

- `ENRICHMENT_WAREHOUSE_STATUS_JSON_PATH` is not set locally.
- `/data/logs/warehouse-status.json` was not found.
- `/data/logs` was not present in the local workspace environment.
- The only local JSON matches were pytest scratch artifacts under `/tmp` and
  historical/session/doc references. Those are not production artifacts and
  are not suitable Stage 18J-P inputs.

Some `/tmp/systemd-private-*` paths were unreadable during broad search. Those
permission-denied paths are service-private temporary directories, not
configured ED-Finder artifact locations.

## Artifact Found / Not Found

No suitable production `enrichment_staging_reconciliation/v1` artifact was
found locally or in the configured local artifact path.

The local pytest scratch artifacts are not suitable because they are generated
test fixtures, not production reconciliation output. No source run key, source
file key, production source scope, production freshness state, or operator
artifact location was available for a real production reconciliation artifact.

Stage 18J-P remains blocked.

## Required Artifact Contract

A production reconciliation artifact is suitable for Stage 18J-P input only if
it satisfies all of these checks:

- `schema_version = "enrichment_staging_reconciliation/v1"`.
- `dry_run = true`.
- `summary.canonical_writes_planned = 0`.
- `station_candidates` exists, even if empty.
- `filters.source = "edsm_nightly_stations"`.
- `filters.source_run_key` is present and matches the operator-approved source
  run.
- `filters.source_file_key` is present unless an explicitly approved multi-file
  source scope is being reviewed.
- Candidate rows are report-only reconciliation rows, not executable write
  instructions.
- No `--apply`, `--write`, `--commit`, approval, rollback, or confirmation
  command metadata is embedded as an executed production action.
- The artifact is free of secrets, DSNs, API tokens, private host paths, raw
  credentials, and unsafe raw payload dumps.
- The artifact is small enough, or summarized enough, for manual review before
  Stage 18J-P dry-run generation.

For Stage 18J station-type eligibility, candidate rows must also expose the
identity fields required by the pilot:

- `source.system_id64`
- `source.market_id`
- `source.edsm_station_id` when an EDSM-station-id path is explicitly allowed
- `source.station_name`
- `source.source_run_key`
- `source.source_file_key`
- `source.source_record_key`
- `source.source_record_hash`
- `canonical.system_id64`
- `canonical.station_id` as the canonical update target
- explicit `canonical.market_id`, or explicit `canonical.edsm_station_id` when
  the EDSM-station-id path is explicitly allowed
- `canonical.station_name`
- `canonical.station_type`

`canonical.station_id` alone is not external identity proof. If a production
reconciliation artifact lacks explicit canonical external identity fields, the
Stage 18J pilot must block the affected candidates rather than treating the
internal primary key as stable external identity.

Code inspection shows the current report-only reconciliation shaper records
`canonical.station_id` and not explicit `canonical.market_id` or
`canonical.edsm_station_id` in station candidate payloads. That means a newly
generated artifact from the current general reconciliation command may be
schema-valid and report-only, but it may not produce eligible Stage 18J
station-type candidates until the artifact is proven to include the explicit
canonical external identity fields or a later generator update adds them.

## Read-Only Generation Path

The reviewed report-only generation path is the existing warehouse
reconciliation command:

```sh
.venv/bin/python apps/importer/src/enrichment_staging_db_loader.py \
    --report-reconciliation \
    --dsn "$EDFINDER_WAREHOUSE_READ_DSN" \
    --source edsm_nightly_stations \
    --source-run-key "$SOURCE_RUN_KEY" \
    --source-file-key "$SOURCE_FILE_KEY" \
    --json \
    > "$SAFE_ARTIFACT_DIR/stage18j-q-reconciliation-$SOURCE_RUN_KEY-$SOURCE_FILE_KEY.json"
```

This command was reviewed but not run.

Safety properties from code inspection:

- `--report-reconciliation` is a read-only report mode.
- It cannot be combined with `--write-staging`.
- `--apply`, `--write`, and `--commit` fail closed during argument parsing.
- The reconciliation SQL is checked by existing tests as read-only.
- The report builder emits `schema_version =
  "enrichment_staging_reconciliation/v1"`.
- The report builder emits `dry_run = true`.
- The report builder emits `summary.canonical_writes_planned = 0`.
- The command reads already staged warehouse data and compares it with
  canonical rows; it does not fetch live EDSM/API data.

The command can generate the artifact without live EDSM/API crawling if the
warehouse already contains the intended staged station source run/file. If the
source run/file is not staged yet, an earlier offline snapshot staging workflow
is required. That staging workflow uses local snapshot files; it must not be
replaced by an unreviewed live crawl.

## Access / DSN Safety Requirements

`EDFINDER_WAREHOUSE_READ_DSN` must be a read-only/report-only credential. It
must not be the app owner DSN, warehouse loader DSN, canonical apply DSN, or any
credential that can mutate canonical tables.

Before running the production-connected report command, the operator must
verify and record outside git:

- the host/database are the intended warehouse/report source,
- the role is a dedicated read/report role,
- the role has no write privileges on canonical tables such as `systems`,
  `stations`, `bodies`, `station_body_links`, `body_rings`, and
  `body_scan_facts`,
- the role cannot create, alter, drop, truncate, insert, update, delete, or
  merge warehouse or canonical tables,
- the role can read the staged warehouse tables and the controlled canonical
  snapshot/view data required for reconciliation,
- the DSN does not contain production secrets in any committed file, PR body,
  issue comment, or artifact,
- using a DSN option such as `default_transaction_read_only=on` has been
  considered where the deployment supports it.

If the warehouse is still in the transitional same-database arrangement, the
read/report role must be especially constrained. The preferred Stage 18I.5
target remains a separate `edfinder_enrichment` warehouse database with a
controlled read-only canonical comparison path.

## Report-Only Safety Checks

Before running the report-only command, print the exact command and confirm:

- `--report-reconciliation` is present.
- `--write-staging` is absent.
- `--apply` is absent.
- `--write` is absent.
- `--commit` is absent.
- no Stage 18J `--apply` path is invoked.
- no `--confirm-station-type-canonical-pilot` flag is present.
- no rollback flag is present.
- source is `edsm_nightly_stations`.
- `SOURCE_RUN_KEY` and `SOURCE_FILE_KEY` are the intended source scope.
- output path is outside git and under an operator-managed artifact directory.
- the command stdout is captured to one JSON file.

After generation, verify:

- the JSON parses cleanly,
- schema is `enrichment_staging_reconciliation/v1`,
- `dry_run` is `true`,
- `summary.canonical_writes_planned` is `0`,
- `station_candidates` exists,
- source run/file filters match the approved values,
- no canonical apply approval or station-type dry-run approval is present,
- no unexpected raw payload volume, secrets, DSNs, or private paths are present,
- candidate identity fields include the explicit source and canonical external
  identity fields needed by Stage 18J.

## Secret / Path Sanitisation

The production reconciliation artifact is production-sensitive. It may contain
station names, system IDs, source run/file identifiers, source record keys,
source record hashes, freshness metadata, and canonical comparison details.

Do not commit the raw production artifact unless a separate review explicitly
declares it safe for git. The default handling should be:

- keep the raw artifact in an operator-managed location outside the repo,
- publish only a sanitized summary in docs/PRs,
- omit DSNs, tokens, private host paths, usernames, and raw credentials,
- avoid committing large source payloads or raw records,
- record checksums and source run/file identifiers only when they are safe for
  review.

If the artifact contains any DSN-like string, API key, local private path, host
path, or unredacted credential, stop and regenerate or sanitize the artifact
before Stage 18J-P.

## Suitability For Stage 18J-P

No suitable artifact exists in the local/configured locations, so Stage 18J-P
cannot proceed yet.

Once a report-only artifact exists, Stage 18J-P may generate a station-type
production dry-run only if all of these are true:

- the artifact passes the required contract above,
- the source run/file scope is approved for review,
- the artifact is confirmed report-only with `canonical_writes_planned = 0`,
- the artifact has `station_candidates`,
- the artifact is free of secrets, DSNs, private paths, and unsafe raw payloads,
- the candidate payload contains explicit canonical external identity fields or
  the operator accepts that missing fields will block candidates,
- the Stage 18T canonical safety CI job remains green,
- no production apply or approval is requested in the same task.

If the current reconciliation generator still omits explicit canonical external
identity fields, Stage 18J-P can at most produce a dry-run artifact with those
candidates blocked. It must not approve or apply any candidate on the basis of
`canonical.station_id` equality alone.

## Stop Conditions

Stop before generating the reconciliation artifact if:

- the DSN/access has not been verified read-only,
- the command includes `--write-staging`, `--apply`, `--write`, `--commit`, a
  confirmation flag, or rollback flag,
- the command would invoke live EDSM/API crawling,
- the source run/file scope is unclear,
- the output path is inside git,
- the operator cannot prove which host/database will be read,
- the source run/file has not already been staged through the offline warehouse
  workflow.

Stop after generating the artifact if:

- schema is not `enrichment_staging_reconciliation/v1`,
- `dry_run` is not `true`,
- `summary.canonical_writes_planned` is not `0`,
- `station_candidates` is missing,
- source run/file filters are missing or wrong,
- the artifact contains secrets, DSNs, private paths, or unsafe raw payloads,
- station candidates lack the explicit identity fields Stage 18J requires,
- any artifact is treated as approved for apply.

Stop before Stage 18J-P if no verified artifact exists.

## Remaining Blockers

Stage 18J-P remains blocked by these prerequisites:

- No suitable production `enrichment_staging_reconciliation/v1` artifact was
  found locally or at the configured local status path.
- No verified read-only/report-only production warehouse DSN/access context was
  provided.
- No operator-approved source run/file scope was provided.
- The current general reconciliation candidate payload appears to omit explicit
  canonical external identity fields needed for eligible Stage 18J station-type
  candidates.
- No sanitized artifact summary exists for a real production source run/file.

## Recommendation

Do not run Stage 18J-P yet.

The next safe prerequisite is for an operator to provide verified read-only
warehouse/report access and a specific staged station source run/file, then run
the report-only reconciliation command into an operator-managed path outside
git. The resulting artifact must be validated against the contract in this
document and summarized without secrets. Only after that can Stage 18J-P review
whether a station-type production dry-run artifact can be generated with
`--limit 5`.

Stage 18J-Q2 defines the exact later operator command plan and pre-run checklist
for that read-only/report-only artifact generation:
[`stage-18j-q2-readonly-production-reconciliation-plan.md`](./stage-18j-q2-readonly-production-reconciliation-plan.md).

No production apply is authorized. No production artifact is approved for
apply. Any future apply still requires a separate explicit instruction and
approval naming the exact station-type dry-run artifact hash, candidate count,
table `stations`, field `station_type`, source run/file, max row count, and
apply DSN context.
