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

Stage 19 remains paused for test-environment hardening. The fake-only readiness blocker is cleared only when the real Stage 19 local Postgres readiness test passes against the approved Stage 19AR baseline. Until then, FakeConn/FakeCursor coverage is unit confidence only.

Stage 19AS-AU must not run from this test-environment branch. Do not use `--commit`, do not rebaseline, and do not promote staged rows from this work.
