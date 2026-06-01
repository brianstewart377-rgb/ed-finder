# Stage 18J-Q3 — Read-Only Production Reconciliation Artifact

## Purpose

Stage 18J-Q3 was intended to generate the missing production
`enrichment_staging_reconciliation/v1` artifact through the documented
read-only/report-only path from Stage 18J-Q2.

This pass stopped at the pre-run safety gate. No production-connected
reconciliation command was run, no production reconciliation artifact was
generated, no station-type canonical dry-run artifact was generated, no
production apply was run, no production approval record was created, and no
production canonical data was modified.

## Preconditions

Confirmed repository state:

- PR #109 is merged into `origin/main`.
- `origin/main` includes merge commit
  `b41b332bbd16af47af24161c0f9074136e41fda0`.
- The Stage 18J-Q2 command plan is present.
- The Stage 18T canonical safety test runner is present.
- The local-only `main` commit
  `ee6f546 refactor: extract map projection and layer view models` was
  preserved by leaving local `main` untouched and creating this branch from
  `origin/main`.

The Q3 branch was created from `origin/main`:

```sh
git switch main
git branch backup/local-main-ee6f546-map-refactor || true
git status --short --branch
git fetch origin main
git switch -c stage-18j-q3-readonly-production-reconciliation-artifact origin/main
git log --oneline -12
```

## Pre-Run Safety Checks

The production-connected command was not run because required pre-run checks
were not satisfied.

| Check | Result |
|---|---|
| Command is `--report-reconciliation` only | Reviewed as the only allowed command shape. |
| No `--write-staging` | Reviewed; absent from the proposed command. |
| No `--apply` | Reviewed; absent from the proposed command. |
| No `--write` | Reviewed; absent from the proposed command. |
| No `--commit` | Reviewed; absent from the proposed command. |
| No canonical apply command | Reviewed; Stage 18J apply path was not invoked. |
| `PGOPTIONS='-c default_transaction_read_only=on'` set | Failed: `PGOPTIONS` was not set in the shell. |
| DSN/access read-only/report-only or equivalent | Failed: no verified read-only/report-only DSN was available. |
| Approved `SOURCE_RUN_KEY` set | Failed: `SOURCE_RUN_KEY` was not set. |
| Approved `SOURCE_FILE_KEY` set | Failed: `SOURCE_FILE_KEY` was not set. |
| Output path operator-managed and outside git | Failed: `SAFE_ARTIFACT_DIR` was not set. |
| No secrets/DSNs/private paths will be committed | Satisfied by not generating or committing an artifact. |
| No live EDSM/API crawl | Satisfied by not running any source crawl command. |
| No Docker invocation from UI/API | Satisfied by not invoking Docker or UI/API paths. |

The following local environment presence check was run without printing secret
values:

```sh
printf 'EDFINDER_WAREHOUSE_READ_DSN=%s\n' "${EDFINDER_WAREHOUSE_READ_DSN:+set}"
printf 'SOURCE_RUN_KEY=%s\n' "${SOURCE_RUN_KEY:+set}"
printf 'SOURCE_FILE_KEY=%s\n' "${SOURCE_FILE_KEY:+set}"
printf 'SAFE_ARTIFACT_DIR=%s\n' "${SAFE_ARTIFACT_DIR:+set}"
printf 'PGOPTIONS=%s\n' "${PGOPTIONS:+set}"
printf 'EDFINDER_CANONICAL_APPLY_DSN=%s\n' "${EDFINDER_CANONICAL_APPLY_DSN:+set}"
```

Result:

```text
EDFINDER_WAREHOUSE_READ_DSN=
SOURCE_RUN_KEY=
SOURCE_FILE_KEY=
SAFE_ARTIFACT_DIR=
PGOPTIONS=
EDFINDER_CANONICAL_APPLY_DSN=
```

Because the read-only/report-only DSN, approved source run/file scope,
operator-managed output path, and read-only session option were missing, the
safe outcome was to stop before any production connection.

## Command Reviewed

The actual loader CLI was reviewed with:

```sh
.venv/bin/python apps/importer/src/enrichment_staging_db_loader.py --help
```

The loader does not expose an `--output` flag. It writes JSON to stdout, so the
later operator command must redirect stdout to an operator-managed path outside
git.

The later-only command shape remains:

```sh
export EDFINDER_WAREHOUSE_READ_DSN='<redacted-verified-readonly-report-dsn>'
export SOURCE_RUN_KEY='<approved-source-run-key>'
export SOURCE_FILE_KEY='<approved-source-file-key>'
export SAFE_ARTIFACT_DIR='<operator-managed-path-outside-git>'
export PGAPPNAME='stage18j-q3-readonly-reconciliation'
export PGOPTIONS='-c default_transaction_read_only=on'

.venv/bin/python apps/importer/src/enrichment_staging_db_loader.py \
    --report-reconciliation \
    --dsn "$EDFINDER_WAREHOUSE_READ_DSN" \
    --source edsm_nightly_stations \
    --source-run-key "$SOURCE_RUN_KEY" \
    --source-file-key "$SOURCE_FILE_KEY" \
    --limit 1000 \
    --json \
    > "$SAFE_ARTIFACT_DIR/enrichment_staging_reconciliation_${SOURCE_RUN_KEY}_${SOURCE_FILE_KEY}.json"
```

This command was reviewed only. It was not run.

It must not include `--write-staging`, `--apply`, `--write`, `--commit`,
`--confirm-staging-db`, `--confirm-station-type-canonical-pilot`, rollback
flags, Docker invocation, or live API crawl flags.

## Command Run

No production-connected reconciliation command was run.

Only local repository inspection, loader help, and local safety tests were run.
No command connected to production, no command generated a production
reconciliation artifact, and no station-type canonical pilot dry-run command
was run.

## DSN / Access Safety

Read-only/report-only DSN access could not be proven because
`EDFINDER_WAREHOUSE_READ_DSN` was not set in the local shell and no separate
operator proof of grants, host/database, or role privileges was available in
this task.

`EDFINDER_CANONICAL_APPLY_DSN` was also not set, which is correct for this
stage. Q3 does not require or authorize canonical apply credentials.

A future attempt must prove, outside git, that the DSN:

- points at the intended warehouse/report source,
- uses a dedicated read/report role,
- is not an app, loader, owner, superuser, or canonical apply DSN,
- cannot INSERT, UPDATE, DELETE, TRUNCATE, CREATE, ALTER, DROP, or otherwise
  mutate canonical tables,
- can only read the staged warehouse and controlled canonical comparison data
  needed for reconciliation,
- runs with session read-only enforcement where supported.

## Source Run / Source File

No approved production source scope was available in this task.

| Field | Value |
|---|---|
| Source | `edsm_nightly_stations` was reviewed as the required source. |
| Source run key | Not available; `SOURCE_RUN_KEY` was not set. |
| Source file key | Not available; `SOURCE_FILE_KEY` was not set. |
| Source scope approval | Not available. |

## Output Artifact Location

No output artifact was written.

`SAFE_ARTIFACT_DIR` was not set, so an operator-managed output path outside git
was not available. The production artifact itself was not committed, because no
artifact was generated and no artifact was explicitly sanitized or approved for
git.

## Artifact Contract Validation

Artifact contract validation was not performed because no artifact was
generated.

| Contract check | Result |
|---|---|
| `schema_version == "enrichment_staging_reconciliation/v1"` | Not available. |
| Report is dry-run/report-only | Not available. |
| `summary.canonical_writes_planned == 0` | Not available. |
| `station_candidates` exists | Not available. |
| Source identity fields present | Not available. |
| Canonical update target `canonical.station_id` present | Not available. |
| Explicit canonical external identity fields present | Not available. |
| No secrets/DSNs/private paths | Not available; no artifact existed to scan. |
| No apply/write/commit metadata | Not available; no artifact existed to scan. |

No artifact checksum exists for this pass.

## Candidate Availability Summary

No production reconciliation artifact was generated, so no production
candidate counts were produced.

| Metric | Value |
|---|---:|
| Station candidates | Not available |
| Candidate station updates | Not available |
| Canonical writes planned | Not available |
| Stage 18J-P eligible candidates | Not evaluated |
| Blocked candidates | Not evaluated |

Code inspection still shows an important Stage 18J-P risk: the current general
reconciliation SQL joins staged station `market_id` and `edsm_station_id` to
`stations.id`, and the shaped station candidate exposes `canonical.station_id`
but not explicit `canonical.market_id` or `canonical.edsm_station_id`.

That means even a future schema-valid Q3 artifact may still leave Stage 18J-P
without eligible station-type candidates unless the artifact is proven to
include explicit canonical external identity fields or a later generator update
adds them. `canonical.station_id` alone must not be treated as stable external
identity proof.

## Secret / Path Sanitisation

No production artifact was generated, so no production artifact was scanned or
sanitized.

No DSN values, credentials, private host paths, API keys, production artifact
contents, or source payloads were committed.

Future sanitized summaries may record schema version, source run/file
identifiers when safe, candidate counts, blocking reasons, and checksums when
safe. Raw production reconciliation artifacts should remain outside git unless
they have been explicitly sanitized and approved for commit.

## Suitability For Stage 18J-P

Stage 18J-P cannot proceed from this pass.

No valid `enrichment_staging_reconciliation/v1` production artifact was
generated, no artifact checksum exists, no candidate counts exist, and no
source run/file scope was verified. Stage 18J-P remains blocked.

## Remaining Blockers

Before Q3 can be retried, the operator must provide and verify:

- `EDFINDER_WAREHOUSE_READ_DSN` for a dedicated read/report role,
- proof that the DSN/access is read-only/report-only,
- `PGOPTIONS='-c default_transaction_read_only=on'` or equivalent session
  read-only enforcement,
- approved `SOURCE_RUN_KEY`,
- approved `SOURCE_FILE_KEY`,
- operator-managed `SAFE_ARTIFACT_DIR` outside git,
- confirmation that the staged source run/file already exists,
- confirmation that the later command will not invoke live EDSM/API crawling,
  Docker, write-staging, apply, write, commit, confirmation, or rollback flags.

Stage 18J-Q4 provides the operator-facing access packet and sign-off template
for these missing variables:
[`../operations/stage-18j-q4-operator-access-packet.md`](../operations/stage-18j-q4-operator-access-packet.md).

Stage 18J-P also remains blocked by the possible missing explicit canonical
external identity fields in the general reconciliation payload. If a future Q3
artifact lacks `canonical.market_id` and `canonical.edsm_station_id`, Stage
18J-P must block affected candidates rather than matching on internal primary
key equality.

## Stop Conditions

Stop before command execution if:

- any required environment value is absent,
- DSN/access cannot be proven read-only/report-only,
- the command includes any write/apply/commit/confirm/rollback flag,
- the command would run a live EDSM/API crawl,
- the output path is missing or inside the repo,
- source run/file scope is not approved,
- the intended staged source run/file cannot be proven to exist.

Stop after artifact generation if a future attempt produces an artifact that:

- is not `enrichment_staging_reconciliation/v1`,
- is not dry-run/report-only,
- has `summary.canonical_writes_planned != 0`,
- lacks `station_candidates`,
- contains secrets, DSNs, private paths, or raw credentials,
- contains apply/write/commit metadata,
- lacks explicit canonical external identity fields required for Stage 18J-P
  eligible station-type candidates.

## Recommendation

Do not treat Stage 18J-P as unblocked.

Retry Stage 18J-Q3 only in a separate explicit operation after read-only
warehouse/report DSN access, source run/file scope, session read-only
enforcement, and an operator-managed output path are all verified. Until then,
no production reconciliation artifact exists, no station-type dry-run artifact
exists, no production artifact is approved, and no production apply is
authorized.
