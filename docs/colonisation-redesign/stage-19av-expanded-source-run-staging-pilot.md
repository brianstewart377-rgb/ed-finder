# Stage 19AV - Expanded Source-Run Staging Pilot

## Purpose

Stage 19AV is the selected bounded write lane after Stage 19AU. It prepares an
expanded controlled source-run staging pilot that extends the Stage 19AS-AU
path without canonical writes.

This checkpoint records the successful Stage 19AV bounded write after the
stage-specific wrapper, documentation, and static/unit coverage were reviewed
and merged. The run added a bounded staging-only prerequisite source input,
verified the exact 250-row AV sample gate, and executed the reviewed AV wrapper
against the approved local target only.

## Current Authority

Active authority remains
`docs/colonisation-redesign/stage-19-state-authority.json`.

- Stage 19AS-AU is complete and recorded.
- Stage 19AS.1 is complete and recorded.
- Stage 19AS.2 is complete and recorded.
- Stage 19AT is complete and recorded.
- Stage 19AU read-only DB verification is complete and recorded.
- Stage 19AV expanded source-run staging pilot is complete and recorded.
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
- profile default and hard maximum row count: `250`;
- CLI invocations must provide an explicit `--limit`;
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
- the only accepted future DB target is exactly `127.0.0.1:55432`;
- local `5432` targets, including `127.0.0.1:5432`, `localhost:5432`,
  `::1:5432`, and `0.0.0.0:5432`, are rejected by the wrapper;
- non-local hosts, hostnames, private-network IPs, public IPs, and
  production-like DB targets are rejected by the wrapper;
- passwords and secrets are redacted from preflight output;
- environment-driven DB target overrides are accepted only when they still
  resolve to exactly `127.0.0.1:55432`.

## Completed Run Evidence

Stage 19AV was run on `2026-06-15T06:21:02Z` after a staging-only prerequisite
source input supplied the missing 125 eligible non-diagnostic staging rows.

- safe DB target: `127.0.0.1:55432`;
- staging prerequisite source run:
  `7fe4382fbde60752e026b576d92e0352c01d85799613884d2b2e7ee57cd3f5f3`;
- staging prerequisite rows: `125`;
- AV source run:
  `stage19av-expanded-source-run-staging-pilot-48688d9d46067867`;
- AV bridge:
  `source_runs:stage19av-expanded-source-run-staging-pilot-48688d9d46067867`;
- import artifact:
  `/home/brian/.local/share/ed-finder/operator-artifacts/stage-19av/stage19av_edsm_import_20260615T062102Z.json`;
- import artifact checksum:
  `09652a1c6e6ad661415f535a713432b0d3a76aef5b8c931c0b1874e1c52604f4`;
- operator artifact:
  `/home/brian/.local/share/ed-finder/operator-artifacts/stage-19av/stage19av_operator_expanded_staging_pilot_20260615T062102Z.json`;
- operator artifact checksum:
  `b2d7f2649b68d9ededb965dd8442f37399bb90a1327c934ea8145258759068a1`;
- rows read: `250`;
- rows staged: `250`;
- rows rejected: `0`;
- rows skipped: `0`;
- canonical writes performed: `false`.

Post-run verification confirmed:

- the Stage 19AV source run exists and succeeded;
- the Stage 19AV bridge exists;
- the import artifact checksum matches the source run record;
- exactly 250 AV staging rows were inserted;
- all AV staging rows are diagnostic-only and preserve canonical-write blocking;
- Stage 19AR baseline remains preserved;
- Stage 19AS-AU checkpoint remains preserved;
- Stage 19AU read-only verification remains preserved;
- no active or failed Stage 19 source run blocks the lane;
- no canonical apply or canonical write was performed;
- Stage 19 remains paused.

The runtime source JSON used for the staging prerequisite and the operator
artifact JSON files are evidence only and are not committed authority.

## Blocked Work

Stage 19AV completion does not authorize:

- Stage 19AR with `--commit`;
- Stage 19AS-AU with `--commit`;
- unbounded source batches;
- canonical table writes;
- canonical apply;
- rebaseline;
- scheduler, timer, or service-manager work;
- production-like DB targets;
- non-local DB hosts or any target other than `127.0.0.1:55432`;
- host `5432` as a direct Stage 19 target;
- secrets access or printing;
- runtime source JSON or operator artifact JSON commits.

Any future write-capable lane after Stage 19AV requires a separate explicit
operator decision.

