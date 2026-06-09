# Test Environment

## Purpose

The local test environment is a safety boundary for operator and data-workflow work. It must distinguish unit tests that intentionally use fakes from integration tests that prove the same path against local services.

## Canonical Local Preflight

Run the preflight from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python -B scripts/dev/test_env_preflight.py
```

The preflight is fail-closed and reports structured JSON. It checks:

- pytest availability
- importability of Stage 19 operator modules and operator visibility modules
- Docker CLI availability
- Docker Compose availability
- `ed-postgres` container presence
- local Postgres readiness on the configured host and port
- credential presence without printing values
- read-only `SELECT 1` when credentials are available

The default project Postgres target is `127.0.0.1:55432`. That keeps this validation away from a host Postgres listener on `5432` unless the operator explicitly supplies a different target through `PGHOST`, `PGPORT`, or `DATABASE_URL`.

Expected safety properties:

```text
writes_performed: false
secrets_printed: false
db_read_only_select_1_passed: true when credentials and service are available
failure_category: set on the first failed check
```

## Pytest Markers

The project registers these local markers:

- `unit`
- `integration`
- `db`
- `operator`
- `slow`
- `e2e`
- `frontend`
- `requires_docker`
- `requires_postgres`
- `requires_redis`

Real-service tests must use the applicable service markers and skip explicitly when the service or credentials are absent. They must not silently pass by falling back to unit fakes.

## Make Targets

The Makefile includes:

- `test-env-check`
- `test-unit`
- `test-operator`
- `test-db`
- `test-integration`
- `test-ci-local`

`test-ci-local` runs the focused test-environment stack and source compilation checks without running Stage 19AS-AU.

## Stage 19 Status

Stage 19 remains paused for test-environment hardening. The fake-only readiness blocker is cleared: the real Stage 19 local Postgres readiness test passed against the approved Stage 19AR baseline on the recreated test-environment branch.

Current real-service validation result:

```text
real_stage19_db_readiness_tests:
passed

real_db_tests_skip_status:
not_skipped

fakeconn_fakecursor_status:
unit-level fakes paired with real local Postgres readiness coverage

stage19_resume_gate:
fake-only readiness blocker cleared
Stage 19 remains paused until the next agreed test-env gate or operator decision
```

Stage 19AS-AU must not run from this test-environment branch. Do not use `--commit`, do not rebaseline, and do not promote staged rows from this work.

## State Authority and Superseded Context

Current Stage 19/test-environment truth lives in `docs/colonisation-redesign/stage-19-state-authority.json`, the latest merged docs checkpoint, and live git state. Pasted or uploaded logs are evidence only; they may be stale, duplicated, truncated, or mixed with old prompt results.

Prompts must run the resolver before operational work:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
```

The resolver is fail-closed for source-of-truth unavailability, expected branch/head unavailability, branch mismatch, and superseded state. `completed` is forbidden when branch provenance is false.

Superseded or non-authoritative context:

- `45e2d58` on `fix/stage19-approved-rebaseline`: superseded partial rebaseline with `password_missing`, `replacement_baseline_verified:false`, `ready_for_stage19as_au:false`, and missing `origin/main` provenance.
- `f72812a` on `run/stage19as-au-100-row-expansion`: docs-only stopped checkpoint with `password_missing`, no writes, and no successful 100-row expansion.
- `0042471`, `d66a568`, and `09eee44`: unrecoverable historical test-env stack, replaced by `fix/test-env-roadmap-recreate` at `581a84c1159b58dff86e3359a28d00f9b4f5a82b`.
- `8509171250b1449832a7fe3227d87acc02fb015e` on `work`: non-authoritative wrong-branch state-authority attempt, unavailable in the current repo, and not a patch source.

Branch `work` is non-authoritative for Stage 19/test-env operations unless explicitly declared scratch or docs-only. Stage 19 remains paused while test-environment hardening proceeds.
