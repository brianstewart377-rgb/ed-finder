# Stage 19AS.1 - Disposable Postgres Pilot-Path Constraint Tests

## Purpose

Stage 19AS.1 adds the next safety-test checkpoint after the completed Stage
19AS-AU controlled 100-row expansion. It covers the pilot path that must remain
safe before any wider pilot, scheduler work, canonical write lane, or canonical
apply lane is considered.

This checkpoint is tests and documentation only. It does not run Stage 19
operator expansion commands and does not create a new staging source run.

## Current Authority

Active authority remains
`docs/colonisation-redesign/stage-19-state-authority.json`.

- Stage 19AS-AU is complete and recorded.
- Stage 19 remains paused.
- The approved Stage 19AR baseline remains the 5f777 source run, b617 artifact,
  and 25 diagnostic rows.
- The Stage 19AS-AU checkpoint remains the 100-row source run
  `stage19as-au-edsm-100-row-controlled-expansion-1843ccf903dfa6c9`.
- No canonical apply is complete.
- No rebaseline is complete.

## Added Coverage

`tests/test_stage19as1_disposable_postgres_constraints.py` covers:

- the active authority still records Stage 19AS-AU while leaving Stage 19
  paused;
- invalid Stage 19 states remain denylisted and are not operational authority;
- `source_runs` schema constraints required by the pilot path, including
  source-run identity, status/scope constraints, row counters, artifact fields,
  and `finished_at >= started_at`;
- `staging_edsm_stations.source_run_id` still targets
  `enrichment_source_runs(id)`, not `source_runs(id)`;
- diagnostic-only staging policy and provenance storage remain available;
- operator validation still checks artifact hashes, artifact integrity, legacy
  bridge FK usage, source-run FK non-use, diagnostic isolation, and the explicit
  no-canonical-write result;
- optional read-only disposable/local Postgres verification of the recorded
  Stage 19AS-AU source run, bridge row, 100 diagnostic staging rows, marker, and
  canonical-write block when a safe local DB is available.

The optional real-Postgres test uses the existing
`tests.helpers.db_isolation` guardrails. It skips unless the target is local or
disposable, credentials are present, and the DB is reachable. Its connection is
read-only and rolls back before closing.

## Safety Boundary

Stage 19AS.1 does not:

- run Stage 19 operator expansion commands;
- run Stage 19AR with `--commit`;
- run Stage 19AS-AU with `--commit`;
- run a full source batch;
- write canonical tables;
- run canonical apply;
- rebaseline;
- enable scheduler, timer, or service units;
- target production-like DBs;
- use host `5432` unless the existing disposable-DB opt-in allows it;
- print secrets;
- commit runtime source JSON or operator artifact JSON.

## Validation

Expected focused validation:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest tests/test_project_state_resolver.py tests/test_db_isolation_guardrails.py tests/test_stage19aq1_test_fortress_guardrails.py tests/test_stage19_real_postgres_readiness.py -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest tests/test_stage19as1_disposable_postgres_constraints.py -p no:cacheprovider
git diff --check
```

The real-Postgres checks are allowed to skip when no safe disposable/local DB is
available. A non-skipped run must remain read-only.
