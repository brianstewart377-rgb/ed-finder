# Stage 19AV - Expanded Source-Run Staging Pilot

## Purpose

Stage 19AV is the selected bounded write lane after Stage 19AU. It prepares an
expanded controlled source-run staging pilot that extends the Stage 19AS-AU
path without canonical writes.

This checkpoint prepares the Stage 19AV operator wrapper, documentation, and
static/unit coverage only. The Stage 19AV bounded write was not run in this
checkpoint because a dedicated stage-specific wrapper and review gate were
required before the first AV write.

## Current Authority

Active authority remains
`docs/colonisation-redesign/stage-19-state-authority.json`.

- Stage 19AS-AU is complete and recorded.
- Stage 19AS.1 is complete and recorded.
- Stage 19AS.2 is complete and recorded.
- Stage 19AT is complete and recorded.
- Stage 19AU read-only DB verification is complete and recorded.
- Stage 19 remains paused.
- No canonical apply is complete.
- No rebaseline is complete.
- Scheduler and wider service work remain unauthorized.

## Prepared Operator Boundary

The prepared Stage 19AV wrapper is
`scripts/operator/stage19av_expanded_source_run_staging_pilot.py`.

The wrapper reuses the proven Stage 19AR/AS-AU staging helper with a new
stage-specific profile:

- source-run prefix:
  `stage19av-expanded-source-run-staging-pilot-`;
- bridge prefix:
  `source_runs:stage19av-expanded-source-run-staging-pilot-`;
- provenance marker:
  `stage19av_expanded_source_run_staging_pilot`;
- default and hard maximum row count: `250`;
- exact committed row count requirement: `250`;
- artifact namespace:
  `/var/lib/ed-finder/operator-artifacts/stage-19av`;
- safe local target for a future approved run: `127.0.0.1:55432`.

The wrapper keeps the existing contract:

- dry-run/non-commit mode is the default;
- `--commit` is required before any DB write;
- `--confirm-stage19av` is also required with `--commit`;
- commit mode requires the exact Stage 19AV row count;
- `--preflight-db` authenticates and verifies prerequisites without writes or
  artifacts;
- `DATABASE_URL` must be unset for Stage 19AV operator commands;
- a direct local host `5432` target is rejected by the wrapper;
- passwords and secrets are redacted from preflight output;
- production-like DB targets and direct host `5432` targets remain blocked by
  the operator procedure.

## Required Future Gates

Before the Stage 19AV pilot can run, the operator must complete a separate
review/merge gate for this prepared wrapper and then rerun the Stage 19AV task
from current main.

The future run must confirm:

- Stage 19AR baseline remains preserved;
- Stage 19AS-AU checkpoint remains preserved;
- Stage 19AU read-only verification remains preserved;
- no active or failed Stage 19 source run blocks the lane;
- safe target is `127.0.0.1:55432`;
- `DATABASE_URL` is unset;
- `PGPASSWORD` is present but not printed;
- artifact output goes to an operator artifact directory and is not committed.

If the future pilot succeeds, a later checkpoint must record:

- Stage 19AV source run key;
- bridge key;
- import artifact path and checksum;
- operator artifact path and checksum;
- rows read, staged, rejected, and skipped;
- post-run verification summary;
- canonical writes performed as `false`;
- Stage 19 still paused unless a separate operator decision changes that.

## Blocked Work

Stage 19AV preparation does not authorize:

- running the AV bounded write before this wrapper is reviewed and merged;
- Stage 19AR with `--commit`;
- Stage 19AS-AU with `--commit`;
- unbounded source batches;
- canonical table writes;
- canonical apply;
- rebaseline;
- scheduler, timer, or service-manager work;
- production-like DB targets;
- host `5432` as a direct Stage 19 target;
- secrets access or printing;
- runtime source JSON or operator artifact JSON commits.

Any future write-capable lane after Stage 19AV requires a separate explicit
operator decision.
