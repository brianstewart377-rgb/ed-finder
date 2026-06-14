# Stage 19AS.2 - Operator Script Contract Formalization

## Purpose

Stage 19AS.2 turns the deferred Stage 19 operator-script contract into a
repo-only safety checkpoint. It records the minimum contract future Stage 19
operator scripts must satisfy before any wider pilot, scheduler work, canonical
write lane, or canonical apply lane is considered.

This checkpoint is documentation and static/unit test coverage only. It does
not run Stage 19 operator commands. It does not connect to a database or create
a new source run.

## Current Authority

Active authority remains
`docs/colonisation-redesign/stage-19-state-authority.json`.

- Stage 19AS-AU is complete and recorded.
- Stage 19AS.1 is complete and recorded.
- Stage 19 remains paused.
- The approved Stage 19AR baseline remains the 5f777 source run, b617 artifact,
  and 25 diagnostic rows.
- The Stage 19AS-AU checkpoint remains the 100-row source run
  `stage19as-au-edsm-100-row-controlled-expansion-1843ccf903dfa6c9`.
- No canonical apply is complete.
- No rebaseline is complete.

## Operator Script Contract

Stage 19 operator scripts must keep these boundaries explicit:

- dry-run or read-only mode is the default;
- writes require an explicit `--commit` opt-in;
- pilot and rehearsal paths expose a bounded `--limit`;
- hard maximum limits are required for committed expansion paths;
- artifact output behavior is explicit through either a required
  `--artifact-dir` or a documented default operator artifact directory;
- preflight checks run before writes and detect unsafe leftovers where the path
  can create Stage 19 rows;
- writes produce an operator artifact with source-run, bridge, import artifact,
  validation, and safety-summary fields;
- post-run validation verifies diagnostic staging, bridge usage, artifact
  hashes, artifact integrity, and canonical-write blocking;
- error paths roll back the transaction before returning failure;
- scheduler, timer, service-manager, canonical apply, and production import
  dispatches stay out of these scripts;
- shell mega-scripts must not replace repo operator scripts when a typed repo
  script can express the safety boundary.

## Known Script Notes

`scripts/operator/stage19ar_edsm_25_row_staging_pilot.py` and
`scripts/operator/stage19as_au_edsm_100_row_controlled_expansion.py` are the
current bounded committed-pilot contract examples. They use explicit commit
gates, hard limits, preflight checks, rollback behavior, operator artifacts,
post-run validation, and canonical-write blocking.

Stage 19AN-R
(`scripts/operator/stage19anr_warehouse_derived_staging_rehearsal.py`) is older
rehearsal code. It keeps the required `--artifact-dir`, explicit `--commit`,
dry-run rollback, operator artifact, and canonical-write blocking boundaries,
but it has only a lower-bound `--limit` check. Future committed expansion
scripts should not copy that lower-bound-only limit behavior.

`scripts/operator/stage19as_au_edsm_100_row_controlled_expansion.py` includes a
read-only `--preflight-db` helper for operator target verification. Stage
19AS.2 did not run it. Future use still requires an explicitly safe local or
disposable target and must not target host `5432` directly for committed Stage
19 work.

## Added Coverage

`tests/test_stage19as2_operator_script_contract.py` covers:

- Stage 19AS-AU and Stage 19AS.1 remain recorded while Stage 19 stays paused;
- Stage 19AS.2 is documented as repo-only static/unit coverage;
- operator CLIs keep `--commit` opt-in and `--limit` controls;
- artifact directory behavior is explicit;
- committed-pilot scripts keep hard maximum limits;
- operator scripts keep rollback, validation, artifact summary, and
  no-canonical-write reporting;
- scheduler, service-manager, canonical apply, production import dispatch, and
  shell execution patterns are absent from Stage 19 operator scripts;
- local CI parity includes the new static contract test without adding operator
  commands.

## Safety Boundary

Stage 19AS.2 does not:

- run Stage 19 operator expansion commands;
- run Stage 19AR with `--commit`;
- run Stage 19AS-AU with `--commit`;
- run a full source batch;
- connect to a database;
- write staging rows;
- write canonical tables;
- run canonical apply;
- rebaseline;
- enable scheduler, timer, or service units;
- target production-like DBs;
- use host `5432` as a direct committed Stage 19 target;
- print secrets;
- commit runtime source JSON or operator artifact JSON.

## Validation

Expected focused validation:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest tests/test_stage19as2_operator_script_contract.py -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest tests/test_project_state_resolver.py tests/test_stage19as1_disposable_postgres_constraints.py tests/test_stage19aq1_test_fortress_guardrails.py tests/test_stage19ar_operator_script.py -p no:cacheprovider
git diff --check
```

These checks are repo-local and static/unit-only for AS.2. They must not run
operator scripts or DB commands.
