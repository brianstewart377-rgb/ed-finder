# Stage 19AQ.1 - Test Fortress / CI parity hardening

Stage 19AQ.1 inserts a repo-only test-hardening step before Stage 19AR, the bounded 25-row staging pilot.

The purpose is to make the local "close to CI" path boring and repeatable after recent work exposed OpenAPI drift, local frontend timeout pressure, UI race conditions, fake cursor gaps, and safety-contract checks that should be easier to run before a PR reaches CI.

## Added commands

Repository-level scripts:

- `scripts/checks/local-ci-parity.sh`
- `scripts/checks/openapi-drift.sh`
- `scripts/checks/stage19-safety-guardrails.py`

Frontend grouped scripts:

- `yarn test:operator`
- `yarn test:planner`
- `yarn test:map`
- `yarn test:stores`
- `yarn test:ci`

## Local parity flow

Run from the repository root:

```bash
bash scripts/checks/local-ci-parity.sh
```

The script fails fast and runs:

- backend Python compile checks;
- Stage 19/source-run/operator focused pytest files;
- Stage 19 static safety guardrails;
- frontend operator/API/routing tests;
- frontend typecheck;
- frontend build;
- OpenAPI drift check;
- `git diff --check`.

If local disposable Postgres/Redis are not available, the OpenAPI section can be skipped for a partial local pass:

```bash
LOCAL_CI_SKIP_OPENAPI=1 bash scripts/checks/local-ci-parity.sh
```

That skip is for local dependency gaps only. The OpenAPI helper should still be run when local PG/Redis are available, and CI continues to run the authoritative OpenAPI drift job.

## OpenAPI drift helper

Run from the repository root:

```bash
bash scripts/checks/openapi-drift.sh
```

The helper mirrors the CI OpenAPI job as closely as practical:

- requires local/disposable Postgres reachable through `DATABASE_URL`;
- requires local Redis reachable through `REDIS_URL`;
- applies schema/seed through `scripts/seed_check.sh`;
- boots the API locally;
- regenerates `frontend-v2/src/types/api.gen.ts` from `/openapi.json`;
- fails if `git diff` detects generated type drift.

It refuses production-looking or non-local `DATABASE_URL` values and does not print the refused DSN.

## Static guardrails

`scripts/checks/stage19-safety-guardrails.py` scans only the Stage 19 operator/source-run surfaces. It checks for:

- no `systemctl` usage;
- no `.timer` or `.service` activation fragments;
- no canonical apply command/dispatch fragments;
- no production-looking database URLs or password assignments;
- no `POST`, `PUT`, `PATCH`, or `DELETE` operator router endpoints;
- no write-method frontend helpers under `/api/operator`;
- legacy staging FK policy remains explicit: `staging_edsm_stations.source_run_id` uses `enrichment_source_runs.id`, not `source_runs.id`.

The pytest wrapper `tests/test_stage19aq1_test_fortress_guardrails.py` keeps the static scan in the focused Stage 19 test set.

## What is intentionally not covered

This stage does not add a new CI job, does not add production services, and does not make the full local frontend suite slower. The existing GitHub CI workflow remains authoritative for backend integration, canonical safety, frontend build, E2E, nginx syntax, and OpenAPI drift.

This stage does not run imports, migrations, scheduler/timer activation, staging writes, canonical writes, or canonical apply.

Stage 19 remains paused. Stage 19AS-AU was not run, and these scripts are safety/check helpers rather than a Stage 19 execution path.

No auth or secret files are part of this recovery. In particular, local `gh-device-auth` artifacts are intentionally excluded and must not be copied into this branch.

## Stage 19AR protection

Stage 19AR remains the bounded 25-row staging pilot. Stage 19AQ.1 protects that step by making these checks easier to run before the pilot PR:

- source-run compatibility and artifact tests;
- operator visibility and cockpit tests;
- static read-only/operator guardrails;
- frontend build/type safety;
- OpenAPI drift parity against the backend schema.

Run the local CI parity checks before resuming Stage 19 pilot work.

## Future disposable DB parity tests

A follow-up stage should add disposable Postgres tests dedicated to the Stage 19 pilot path. Those tests should cover:

- `source_runs` constraints;
- `finished_at >= started_at`;
- `source_runs` to `enrichment_source_runs` bridge rows;
- `staging_edsm_stations.source_run_id` uses `enrichment_source_runs.id`;
- artifact hash and integrity fields;
- diagnostic-only staging marks;
- canonical tables remain untouched.

Those tests must stay disposable/local only and must not use production DB credentials.
