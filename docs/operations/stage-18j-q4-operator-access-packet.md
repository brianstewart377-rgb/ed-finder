# Stage 18J-Q4 — Operator Access Packet

## Purpose

Stage 18J-Q4 defines the operator packet needed before Stage 18J-Q3 can retry
the read-only/report-only production reconciliation artifact generation step.

This is documentation/checklist only. It does not authorize or run production
reconciliation, station-type dry-run generation, approval, apply, database
mutation, scheduler wiring, UI/API controls, Docker invocation, live EDSM/API
crawling, Stage 18J-P, Stage 18K, or broader canonical work.

## Current Blocker

Stage 18J-Q3 stopped before any production-connected command because the
required operator variables were not available:

- `EDFINDER_WAREHOUSE_READ_DSN`
- `SOURCE_RUN_KEY`
- `SOURCE_FILE_KEY`
- `SAFE_ARTIFACT_DIR`
- `PGOPTIONS='-c default_transaction_read_only=on'`

No production reconciliation artifact was generated. No production artifact was
approved. Stage 18J-P remains blocked.

## Required Variables

| Variable | Required value | Commit status |
|---|---|---|
| `EDFINDER_WAREHOUSE_READ_DSN` | A verified read-only/report-only warehouse DSN. | Never commit. |
| `SOURCE_RUN_KEY` | The exact approved staged station source run key. | May be summarized only when safe. |
| `SOURCE_FILE_KEY` | The exact approved staged station source file key. | May be summarized only when safe. |
| `SAFE_ARTIFACT_DIR` | An operator-managed output directory outside git. | Never commit if it exposes private paths. |
| `PGOPTIONS` | Exactly `-c default_transaction_read_only=on`. | Safe to document as a literal requirement. |

`EDFINDER_CANONICAL_APPLY_DSN` is not required and must not be provided for
Stage 18J-Q3.

## How To Provide Variables Safely

Provide the variables only in the approved operator shell, secret manager, or
deployment secret mechanism for the single approved Stage 18J-Q3 run.

Do not place real values in:

- committed files,
- `.env` files tracked by git,
- PR descriptions,
- issue comments,
- docs,
- screenshots,
- copied terminal transcripts,
- generated artifacts that will be committed.

Use a private shell session or secret manager injection. Clear the shell
history or use the operator team's normal no-history secret entry procedure if
the DSN could be captured by shell history.

## Read-Only DSN Requirements

`EDFINDER_WAREHOUSE_READ_DSN` must be a dedicated read/report credential. It
must not be:

- the canonical apply user,
- the application write user,
- a warehouse staging loader write user,
- a database owner,
- a superuser,
- any role with canonical table write access,
- any role with broad DDL privileges.

Before Stage 18J-Q3 is retried, the operator must prove outside git that the
DSN role:

- points at the intended warehouse/report source,
- can read the staged warehouse tables needed for reconciliation,
- can read the controlled canonical comparison rows or snapshots needed for
  reconciliation,
- cannot write canonical tables such as `systems`, `stations`, `bodies`,
  `station_body_links`, `body_rings`, or `body_scan_facts`,
- cannot create, alter, drop, truncate, insert, update, delete, or merge
  warehouse or canonical tables,
- does not expose the canonical apply DSN or apply user.

If the deployment still uses the transitional same-database warehouse layout,
the role review must be stricter because warehouse and canonical tables share a
database boundary.

## Source Run / Source File Approval

`SOURCE_RUN_KEY` and `SOURCE_FILE_KEY` must identify an approved staged
`edsm_nightly_stations` source scope.

Before retrying Stage 18J-Q3, the operator must confirm:

- the source run exists in the warehouse/report source,
- the source file exists or the approved scope explicitly allows a missing
  file filter,
- the staged data came from the intended offline snapshot workflow,
- no live EDSM/API crawl is required,
- the source run/file is fresh enough for review,
- the source run/file is narrow enough for a first production reconciliation
  artifact review,
- the source run/file approval is not approval for station-type dry-run
  generation or apply.

## Safe Artifact Directory Requirements

`SAFE_ARTIFACT_DIR` must be:

- outside the git repository,
- operator-managed,
- private to the operator or service account,
- not world-readable,
- not mounted into public UI/API paths,
- not a scheduler drop directory,
- not a location that automatically triggers another job,
- retained long enough for checksum and contract review.

Use restrictive permissions before writing the artifact:

```bash
umask 077
mkdir -p "$SAFE_ARTIFACT_DIR"
chmod 700 "$SAFE_ARTIFACT_DIR"
```

Do not commit the raw production artifact unless a later task explicitly
approves a sanitized version for git.

## Mandatory PGOPTIONS

Stage 18J-Q3 must set:

```bash
export PGOPTIONS='-c default_transaction_read_only=on'
```

This is not a substitute for read-only role grants. It is an additional session
guard. If the target environment does not support this option, stop and document
the equivalent enforced read-only mechanism before running the reconciliation
command.

## Pre-Run Verification Checklist

Before retrying Stage 18J-Q3, verify all items:

- The task explicitly authorizes Stage 18J-Q3 retry only.
- The exact command is printed before execution.
- The command includes `--report-reconciliation`.
- The command includes `--source edsm_nightly_stations`.
- The command includes the approved `--source-run-key`.
- The command includes the approved `--source-file-key`, unless a separately
  approved multi-file scope exists.
- The command includes `--json`.
- The command writes only to `SAFE_ARTIFACT_DIR` via stdout redirection.
- `PGOPTIONS` is exactly `-c default_transaction_read_only=on`.
- `EDFINDER_WAREHOUSE_READ_DSN` is verified read-only/report-only.
- `EDFINDER_CANONICAL_APPLY_DSN` is not present.
- No production apply command is invoked.
- No station-type dry-run command is invoked.
- No live EDSM/API crawl is invoked.
- No Docker, UI/API, scheduler, or automation hook is invoked.
- No real DSN, credential, hostname, private path, or raw artifact content will
  be committed.

Stop immediately if any checklist item is missing or ambiguous.

## Redacted Command Template

The loader CLI was verified with:

```bash
.venv/bin/python apps/importer/src/enrichment_staging_db_loader.py --help
```

The local shell did not provide a `python` command, so the verification used the
repo virtualenv interpreter. The loader has no `--output` flag; it emits JSON
to stdout. Use stdout redirection to the operator-managed path.

Template only. Do not paste real values into this document.

```bash
export PGOPTIONS='-c default_transaction_read_only=on'
export EDFINDER_WAREHOUSE_READ_DSN='<read-only-warehouse-dsn-not-committed>'
export SOURCE_RUN_KEY='<approved-source-run-key>'
export SOURCE_FILE_KEY='<approved-source-file-key>'
export SAFE_ARTIFACT_DIR='<operator-managed-path-outside-git>'
export PGAPPNAME='stage18j-q3-readonly-reconciliation'

PYTHON="${PYTHON:-.venv/bin/python}"
TIMESTAMP='<utc-timestamp>'

umask 077
mkdir -p "$SAFE_ARTIFACT_DIR"
chmod 700 "$SAFE_ARTIFACT_DIR"

"$PYTHON" apps/importer/src/enrichment_staging_db_loader.py \
  --dsn "$EDFINDER_WAREHOUSE_READ_DSN" \
  --report-reconciliation \
  --source edsm_nightly_stations \
  --source-run-key "$SOURCE_RUN_KEY" \
  --source-file-key "$SOURCE_FILE_KEY" \
  --limit 1000 \
  --json \
  > "$SAFE_ARTIFACT_DIR/enrichment_staging_reconciliation_${TIMESTAMP}.json"
```

The actual Stage 18J-Q3 retry must print the exact redacted command before
execution and must not print the real DSN.

## What Must Not Be Done

Do not:

- run production apply,
- run guarded apply,
- generate a station-type canonical pilot dry-run artifact,
- approve any artifact,
- create an approval record,
- modify production canonical data,
- run broad canonical backfill,
- start Stage 18J-P,
- start Stage 18K,
- add UI/API apply controls,
- add scheduler wiring,
- run live EDSM/API crawl,
- use `--write-staging`,
- use `--apply`,
- use `--write`,
- use `--commit`,
- use confirmation flags,
- invoke Docker from UI/API,
- commit real DSNs, credentials, hostnames, secrets, private paths, or raw
  production artifacts.

## Secret Handling

Treat the DSN and raw production artifact as production-sensitive.

Allowed in git:

- this redacted checklist,
- variable names,
- non-secret command shape,
- non-secret validation notes.

Not allowed in git:

- real DSNs,
- database usernames or passwords,
- private hostnames,
- private artifact paths,
- API keys or tokens,
- raw production reconciliation artifacts,
- raw source payloads,
- unredacted command history.

If a production artifact is generated in a later task, keep it outside git
unless the later task explicitly approves a sanitized version for commit.

## Operator Sign-Off Template

Use this outside git before a Stage 18J-Q3 retry. Do not fill real values into
this repository.

```text
Stage 18J-Q3 operator access sign-off

Operator:
Date/time UTC:

Read-only DSN reviewed:
- DSN stored outside git:
- Role is dedicated read/report:
- Role is not app/write/apply/owner/superuser:
- Role cannot write canonical tables:
- Role cannot run DDL:
- PGOPTIONS read-only guard accepted:

Source scope approved:
- Source: edsm_nightly_stations
- SOURCE_RUN_KEY:
- SOURCE_FILE_KEY:
- Source run/file exists in staged warehouse:
- No live crawl required:

Artifact output approved:
- SAFE_ARTIFACT_DIR outside git:
- Directory is not world-readable:
- Directory does not trigger scheduler/UI/API:

Execution boundary:
- No --write-staging:
- No --apply:
- No --write:
- No --commit:
- No confirmation flags:
- No station-type dry-run:
- No artifact approval:
- No production apply:
```

## Stage 18J-Q3 Rerun Criteria

Stage 18J-Q3 may be retried only when:

- this packet has been reviewed by the operator,
- all required variables are available in the approved operator environment,
- read-only/report-only access has been proven outside git,
- source run/file scope has been approved,
- `SAFE_ARTIFACT_DIR` is ready outside git with restrictive permissions,
- the exact command is printed and reviewed before execution,
- the Stage 18T canonical safety suite is green on the branch used for the
  retry.

Even after a successful Q3 artifact generation, Stage 18J-P does not
automatically proceed. A later explicit task must review the artifact contract,
checksum, candidate counts, identity fields, and sanitisation state.

## Final Recommendation

Keep Stage 18J-Q3 and Stage 18J-P blocked until the operator provides the
required variables through a safe channel and completes the sign-off outside
git. This packet is not an approval to run production reconciliation, generate a
station-type dry-run artifact, approve an artifact, or apply canonical writes.
