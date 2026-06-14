# Stage 19AR Canonical Baseline and Fresh DB Recovery

## Purpose

Stage 19AS-AU depends on the exact Stage 19AR baseline. A project database can authenticate successfully and have the required schema while still being unsafe for Stage 19AS-AU if the approved Stage 19AR source run and artifact are absent.

The Stage 19AR canonical baseline is not "any valid-looking 25-row Stage 19AR run." It is the specific approved replacement run identity and artifact below.

## Approved Canonical Stage 19AR Baseline

| Field | Required value |
|---|---|
| `source_run_key` | `stage19ar-edsm-25-row-staging-pilot-5f777958b81bd034` |
| `bridge_key` | `source_runs:stage19ar-edsm-25-row-staging-pilot-5f777958b81bd034` |
| `artifact` | `b617d0239b7458b5b881895b564d091c771394b555c88a5bae942fd9d2c10e5e` |
| `rows` | `25` |

The tracked manifest is `tests/fixtures/stage19ar_approved_rebaseline_manifest.json`. It pins the approved replacement identity, source fixture hash, artifact hash, row count, and retired baseline identity without committing runtime artifacts from `.codex-artifacts`.

The expected verified path is:

```text
source_runs
-> enrichment bridge
-> 25 staging rows
-> diagnostic isolation
-> provenance tracking
-> artifact verification
-> operator visibility
```

## Retired Baseline

The previous Stage 19AR baseline is retired and unrecoverable. It must not be treated as canonical for Stage 19AS-AU readiness.

| Field | Retired value |
|---|---|
| `source_run_key` | `stage19ar-edsm-25-row-staging-pilot-381a609ed62b80fd` |
| `bridge_key` | `source_runs:stage19ar-edsm-25-row-staging-pilot-381a609ed62b80fd` |
| `artifact` | `418bc0db66978623c460aa8cc46a8ab14811098f39cb99a16274d9d181f19417` |
| `rows` | `25` |
| `status` | `retired_unrecoverable` |

Historical detail about why this baseline was retired lives in `docs/archive/stage-19-incident-history.md`. The archive is evidence only and must not be used as operational authority.

## Fresh Project DB Failure Mode

The local project Postgres target may be started on an alternate port, such as `127.0.0.1:55432`, to avoid a host Postgres collision on `5432`. In that state, DB authentication can pass while the approved Stage 19AR baseline is still missing.

This is a baseline-state failure, not a DB-auth failure and not a Stage 19AS-AU logic failure. Stage 19AS-AU must remain blocked until the exact approved Stage 19AR identity is present.

## Current Checkpoint

```text
repair_key:
stage19ar-approved-replacement-baseline-55432-guardrails

project_db:
service: postgres
container: ed-postgres
host: 127.0.0.1
port: 55432
host_postgres_avoided: true

approved_stage19ar_source_run_key:
stage19ar-edsm-25-row-staging-pilot-5f777958b81bd034

approved_stage19ar_bridge_key:
source_runs:stage19ar-edsm-25-row-staging-pilot-5f777958b81bd034

approved_stage19ar_artifact:
b617d0239b7458b5b881895b564d091c771394b555c88a5bae942fd9d2c10e5e

retired_stage19ar_source_run_key:
stage19ar-edsm-25-row-staging-pilot-381a609ed62b80fd

retired_stage19ar_artifact:
418bc0db66978623c460aa8cc46a8ab14811098f39cb99a16274d9d181f19417

retired_stage19ar_status:
retired_unrecoverable
```

## Source-Correct DB Preflight

The Stage 19 DB preflight is reproducible from source and does not depend on cached bytecode.

Entrypoint and command (source-correct, no bytecode):

```sh
set -a; . ./.env; set +a   # provides POSTGRES_PASSWORD; .env is gitignored
PYTHONDONTWRITEBYTECODE=1 python -B \
  scripts/operator/stage19as_au_edsm_100_row_controlled_expansion.py \
  --preflight-db --db-port 55432
```

Expected result: `auth_success: true`, `db_config.host: 127.0.0.1`, `db_config.port: 55432`, `performed_no_writes: true`, `secrets_redacted: true`. The preflight runs `SELECT 1` only and never prints the password.

Source repair already applied:

- `scripts/operator/stage19ar_edsm_25_row_staging_pilot.py` `build_operator_dsn` honors `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER` and `PGPASSWORD` (or `POSTGRES_PASSWORD`) environment precedence, matching the sibling `stage19as_au_edsm_100_row_controlled_expansion.py` preflight DSN. This lets an environment-driven, source-correct run target the configured isolated DB instead of silently defaulting to host Postgres on `5432`. `DATABASE_URL` is deliberately not read here, to keep the Stage 19AR script within its static safety guardrails.
- The isolated container port `55432` is a local `.codex-runtime` compose override (`127.0.0.1:55432:5432`) used to avoid a host Postgres collision on `5432`. The canonical base `docker-compose.yml` maps `127.0.0.1:5432:5432`, so `55432` is environmental and must be supplied via `--db-port 55432` or `PGPORT`; it is never hardcoded into source.

Rule: source-correct DB preflight against `127.0.0.1:55432` must pass without relying on cached bytecode before any Stage 19AR rebaseline verification or Stage 19AS-AU work.

## DB isolation guardrails

The shared test helper `tests/helpers/db_isolation.py` is now the local DB
safety gate for optional Postgres smoke tests and real Stage 19 readiness
checks.

Required properties:

- local/disposable database targets only;
- production-like DSNs fail closed;
- passwords are redacted in summaries;
- `localhost:5432` is not selected silently for local work;
- destructive reset requires `EDFINDER_TEST_DB_ALLOW_DESTRUCTIVE_RESET=yes`
  outside CI;
- optional staging/canonical smoke tests keep their explicit `*_CONFIRM_*`
  environment gates;
- Stage 19AS-AU remains paused and no expansion has been attempted from this
  branch.

## Required Guardrails

- Canonical Stage 19AR mode requires the exact approved replacement `source_run_key`.
- Canonical Stage 19AR mode requires the exact approved replacement artifact hash.
- Stage 19AS-AU preflight must reject missing or retired baselines.
- Retired runs must not be silently promoted back to canonical baselines.
- Stage 19AS-AU must not run unless the exact approved Stage 19AR `source_run_key` and artifact are present.

## Current Stage 19 State

Active authority:
`docs/colonisation-redesign/stage-19-state-authority.json`

Historical evidence:
`docs/archive/stage-19-incident-history.md`

Stage 19AS-AU has completed its controlled 100-row expansion checkpoint. Stage 19 itself remains paused while the next test-environment gate or operator decision is chosen. The pause is a test-environment gate, not a new baseline decision.

Current operational state:

```text
stage19_status:
paused

stage19as_au_status:
completed

stage19_resume_gate:
controlled 100-row expansion verified
Stage 19 remains paused until the next agreed test-env gate or operator decision

real_stage19_db_readiness_tests:
passed

real_db_tests_skip_status:
not_skipped

fakeconn_fakecursor_status:
unit-level fakes paired with real local Postgres readiness coverage

stage19as_au_expansion_attempted:
true

stage19as_au_source_run_key:
stage19as-au-edsm-100-row-controlled-expansion-1843ccf903dfa6c9

stage19as_au_bridge_key:
source_runs:stage19as-au-edsm-100-row-controlled-expansion-1843ccf903dfa6c9

stage19as_au_artifact_sha256:
7f6f20a4d01b543d8ef12072891d8fda749bcc1b6633c26bc9ec178a40b8f84e

stage19as_au_rows:
100
```

The restored real-service readiness path is `tests/test_stage19_real_postgres_readiness.py`. It passed against local Postgres on the recreated test-environment branch, so FakeConn/FakeCursor coverage is now paired with real-service readiness coverage. The Stage 19AS-AU checkpoint preserved the approved Stage 19AR baseline and performed no canonical apply. Stage 19 remains paused until the next agreed test-environment gate or operator decision.

## Fresh-Chat Handoff

Operational prompts should run the resolver first:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
```

Do not paste archive history or large stale prompt bundles into fresh-chat handoffs. Include the active authority path, latest merged docs checkpoint, and live branch/head instead.

## Authority Boundaries

The active source of truth is `docs/colonisation-redesign/stage-19-state-authority.json`, this latest merged docs checkpoint, and live git state. Pasted or uploaded prompt bundles are evidence only. They must not override active authority, current branch/head, or latest merged checkpoint.

The active invalid-state denylist is intentionally tiny. Historical detail belongs in `docs/archive/stage-19-incident-history.md`; the archive must never be copied into operational prompts or used as operational authority.

If source-of-truth branch/commit or branch provenance is unavailable, stop. Branch mismatch is a hard stop. `completed` is forbidden when branch provenance is false.
