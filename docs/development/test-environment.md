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

## DB Isolation Guardrails

Shared test DB target validation lives in `tests/helpers/db_isolation.py`.
It is fail-closed and test-only. It validates local/disposable database
targets, redacts DSNs for reporting, provides rollback-transaction support,
generates safe schema names, and blocks destructive reset unless the caller is
inside CI or explicitly sets:

```text
EDFINDER_TEST_DB_ALLOW_DESTRUCTIVE_RESET=yes
```

The helper refuses production-looking targets and does not silently default to
host Postgres on `5432`. Local `localhost:5432` is allowed only when the target
is known disposable and the operator explicitly sets:

```text
EDFINDER_ALLOW_HOST_5432_TEST_DB=yes
```

CI may use `localhost:5432` because the workflow service container is
disposable for that run. Local work should prefer `127.0.0.1:55432`.

Run the guardrails directly:

```sh
PYTHONDONTWRITEBYTECODE=1 python -B -m pytest tests/test_db_isolation_guardrails.py -p no:cacheprovider
```

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
- `test-db-isolation`
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

## State Authority

Active Stage 19/test-environment truth lives in `docs/colonisation-redesign/stage-19-state-authority.json`, the latest merged docs checkpoint, and live git state.

Historical evidence lives in `docs/archive/stage-19-incident-history.md`. The archive is not operational authority and must not be copied into operational prompts.

Pasted or uploaded logs are evidence only; they may be stale, duplicated, truncated, or mixed with old prompt results. They never override active authority.

Prompts must run the resolver before operational work:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
```

The resolver is fail-closed for source-of-truth unavailability, branch mismatch, and current branch/head matches in the active invalid-state denylist. The denylist is intentionally tiny; historical archive entries do not become operational blockers by implication.

Branch `work` is non-authoritative for Stage 19/test-env operations unless explicitly declared scratch or docs-only. Stage 19 remains paused while test-environment hardening proceeds.
