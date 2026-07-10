# Test Double Inventory

## Scope

This inventory separates unit-level test doubles from real-service proof. A fake can prove local branching and SQL shape, but it cannot prove credentials, live schema, transaction mode, or service availability.

## Current Critical Doubles

| Test double | Location | Classification | Purpose | Required real-service pair |
|---|---|---|---|---|
| `FakeConn` / `FakeCursor` | `tests/test_stage19ar_operator_script.py` | unit fake | Exercise Stage 19AR and Stage 19AS-AU operator SQL paths without DB writes | `tests/test_stage19_real_postgres_readiness.py` |
| `FakeAsyncConn` / `FakePool` | `tests/test_stage19ap_operator_visibility.py` | unit fake | Exercise operator visibility query composition and router path handling | `tests/test_stage19_real_postgres_readiness.py` plus local preflight |
| command runner doubles | `tests/test_test_env_preflight.py` | unit stub | Classify Docker/Postgres/preflight command outcomes without touching services | `scripts/dev/test_env_preflight.py` |
| DB connection doubles | `tests/test_db_isolation_guardrails.py` | unit fake | Prove rollback and close behavior without opening a real database socket | Optional Postgres smoke tests using `tests/helpers/db_isolation.py` |

## FakeConn and FakeCursor Status

```text
fakeconn_fakecursor_status:
unit-level fakes paired with real local Postgres readiness coverage
```

`FakeConn` and `FakeCursor` are still useful for commit/rollback, validation, and artifact-guard tests. They are not accepted as Stage 19 readiness proof by themselves.

The real-service pair is `tests/test_stage19_real_postgres_readiness.py`. It uses live Postgres through `psycopg2`, runs in read-only transaction mode, checks `SELECT 1`, and verifies the approved Stage 19AR baseline identity when that canonical baseline is present locally. It skips explicitly for absent credentials, absent service, or absent baseline data and does not fall back to fakes.

All optional Postgres smoke tests now route their DSN checks through
`tests/helpers/db_isolation.py`. The helper rejects production-like hosts or
database names, redacts passwords from summaries, requires explicit
confirmation for staging/canonical smoke writes, and keeps `localhost:5432`
out of the local default path.

## Confidence Rules

- Unit fakes may validate deterministic control flow and SQL intent.
- Integration tests must carry `integration`, `db`, `operator`, and service requirement markers when they touch local services.
- Missing credentials or unavailable services must be visible as explicit skips, not fake-backed passes.
- Broad runtime dependency stubs are not allowed for real-service tests.
- No test double may be treated as proof that Stage 19AS-AU is safe to run.

## Current Gate

```text
real_stage19_db_readiness_tests:
passed

real_db_tests_skip_status:
not_skipped

fakeconn_fakecursor_status:
unit-level fakes paired with real local Postgres readiness coverage

critical_fakes_replaced_or_paired_with_real_service_tests:
true

stage19_resume_gate:
fake-only readiness blocker cleared
Stage 19 remains paused until the next agreed test-env gate or operator decision
```

The fake-only readiness blocker is cleared by the real Stage 19 DB readiness test passing against local Postgres. Stage 19 remains paused until the next agreed test-environment gate or operator decision.

## State Authority

Active truth for Stage 19/test-environment readiness lives in `docs/colonisation-redesign/stage-19-state-authority.json`, latest merged docs, and live git state.

Historical evidence lives in `docs/archive/stage-19-incident-history.md`. The archive is not operational authority and must not be copied into operational prompts.

Pasted or uploaded logs are evidence only and cannot override active authority.

Run the state resolver before operational work:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
```

The resolver rejects current branch/head matches from the active invalid-state denylist before any fake-backed test result can be treated as readiness proof. The denylist is intentionally tiny; historical archive entries do not expand it.

Stage 19 remains paused while test-environment hardening proceeds.

