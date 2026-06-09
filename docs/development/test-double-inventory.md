# Test Double Inventory

## Scope

This inventory separates unit-level test doubles from real-service proof. A fake can prove local branching and SQL shape, but it cannot prove credentials, live schema, transaction mode, or service availability.

## Current Critical Doubles

| Test double | Location | Classification | Purpose | Required real-service pair |
|---|---|---|---|---|
| `FakeConn` / `FakeCursor` | `tests/test_stage19ar_operator_script.py` | unit fake | Exercise Stage 19AR and Stage 19AS-AU operator SQL paths without DB writes | `tests/test_stage19_real_postgres_readiness.py` |
| `FakeAsyncConn` / `FakePool` | `tests/test_stage19ap_operator_visibility.py` | unit fake | Exercise operator visibility query composition and router path handling | `tests/test_stage19_real_postgres_readiness.py` plus local preflight |
| command runner doubles | `tests/test_test_env_preflight.py` | unit stub | Classify Docker/Postgres/preflight command outcomes without touching services | `scripts/dev/test_env_preflight.py` |

## FakeConn and FakeCursor Status

```text
fakeconn_fakecursor_status:
unit-level fakes paired with real local Postgres readiness coverage
```

`FakeConn` and `FakeCursor` are still useful for commit/rollback, validation, and artifact-guard tests. They are not accepted as Stage 19 readiness proof by themselves.

The real-service pair is `tests/test_stage19_real_postgres_readiness.py`. It uses live Postgres through `psycopg2`, runs in read-only transaction mode, checks `SELECT 1`, and verifies the approved Stage 19AR baseline identity when local credentials and service are available. It skips explicitly for absent credentials or absent service and does not fall back to fakes.

## Confidence Rules

- Unit fakes may validate deterministic control flow and SQL intent.
- Integration tests must carry `integration`, `db`, `operator`, and service requirement markers when they touch local services.
- Missing credentials or unavailable services must be visible as explicit skips, not fake-backed passes.
- Broad runtime dependency stubs are not allowed for real-service tests.
- No test double may be treated as proof that Stage 19AS-AU is safe to run.

## Current Gate

```text
real_stage19_db_readiness_tests:
pending_real_service_result

real_db_tests_skip_status:
explicit_skip_allowed_only_when_credentials_or_service_are_absent

critical_fakes_replaced_or_paired_with_real_service_tests:
true
```

The fake-only readiness blocker is cleared when the real Stage 19 DB readiness test passes against local Postgres. Stage 19 remains paused until the next agreed test-environment gate.
