# Stage 19AR Canonical Baseline and Fresh DB Recovery

## Purpose

Stage 19AS-AU depends on the exact Stage 19AR baseline. A project database can authenticate successfully and have the required schema while still being unsafe for Stage 19AS-AU if the canonical Stage 19AR source run and artifact are absent.

The Stage 19AR canonical baseline is not "any valid-looking 25-row Stage 19AR run." It is the specific verified run identity and artifact below.

## Canonical Stage 19AR Baseline

| Field | Required value |
|---|---|
| `source_run_key` | `stage19ar-edsm-25-row-staging-pilot-381a609ed62b80fd` |
| `bridge_key` | `source_runs:stage19ar-edsm-25-row-staging-pilot-381a609ed62b80fd` |
| `artifact` | `418bc0db66978623c460aa8cc46a8ab14811098f39cb99a16274d9d181f19417` |
| `rows` | `25` |

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

## Fresh Project DB Failure Mode

The local project Postgres target may be started on an alternate port, such as `127.0.0.1:55432`, to avoid a host Postgres collision on `5432`. In that state, DB authentication can pass while the canonical Stage 19AR baseline is still missing.

This is a baseline-state failure, not a DB-auth failure and not a Stage 19AS-AU logic failure. Stage 19AS-AU must remain blocked until the exact canonical Stage 19AR identity is present, unless a human explicitly approves a new baseline in a separate operator decision.

## Rejected Substitute Baseline

The following substitute run was created during fresh project DB recovery and must not be treated as canonical:

| Field | Rejected value |
|---|---|
| `source_run_key` | `stage19ar-edsm-25-row-staging-pilot-5f777958b81bd034` |
| `artifact` | `b617d0239b7458b5b881895b564d091c771394b555c88a5bae942fd9d2c10e5e` |
| `rows` | `25` |

The substitute was valid-looking because it exercised the source run, bridge, staging, diagnostic, provenance, artifact, and visibility path. It is still not equivalent to the canonical Stage 19AR baseline because both the source run key and artifact differ from the required canonical values.

## Current Checkpoint

```text
repair_key:
stage19ar-canonical-baseline-repair-55432-guardrails

project_db:
service: postgres
container: ed-postgres
host: 127.0.0.1
port: 55432
host_postgres_avoided: true

canonical_stage19ar_restored: false
canonical_artifact_restored: false
ready_for_stage19as_au: false

source_correct_db_preflight_passes: true
project_db_authenticated: true
```

The canonical source run key and canonical artifact are currently absent from the fresh project DB and searched local artifact/data locations. The rejected substitute remains evidence of a non-canonical replay only.

## Source-Correct DB Preflight (Repaired)

The Stage 19 DB preflight is now reproducible from source and does not depend on cached bytecode.

Entrypoint and command (source-correct, no bytecode):

```sh
set -a; . ./.env; set +a   # provides POSTGRES_PASSWORD; .env is gitignored
PYTHONDONTWRITEBYTECODE=1 python -B \
  scripts/operator/stage19as_au_edsm_100_row_controlled_expansion.py \
  --preflight-db --db-port 55432
```

Expected result: `auth_success: true`, `db_config.host: 127.0.0.1`, `db_config.port: 55432`, `performed_no_writes: true`, `secrets_redacted: true`. The preflight runs `SELECT 1` only and never prints the password.

Root cause of the earlier `project_db_authenticated: false`:

- The source-correct run failed only because `POSTGRES_PASSWORD`/`PGPASSWORD` was absent from the environment, returning `failure_category: password_missing`. Cached bytecode cannot carry DB credentials, so the earlier "success from bytecode" was a misdiagnosis of an ambient-environment difference.
- Verification removed all project-local `__pycache__` and `.pytest_cache`, then re-ran the preflight with `python -B` (no bytecode written or read). It authenticated against `127.0.0.1:55432`, proving zero reliance on cached bytecode.

Source repair applied:

- `scripts/operator/stage19ar_edsm_25_row_staging_pilot.py` `build_operator_dsn` now honors `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER` and `PGPASSWORD` (or `POSTGRES_PASSWORD`) environment precedence, matching the sibling `stage19as_au_edsm_100_row_controlled_expansion.py` preflight DSN. This lets an environment-driven, source-correct run target the configured isolated DB instead of silently defaulting to host Postgres on `5432`. `DATABASE_URL` is deliberately not read here, to keep the Stage 19AR script within its static safety guardrails.

Port note: the isolated container port `55432` is a local `.codex-runtime` compose override (`127.0.0.1:55432:5432`) used to avoid a host Postgres collision on `5432`. The canonical base `docker-compose.yml` maps `127.0.0.1:5432:5432`, so `55432` is environmental and must be supplied via `--db-port 55432` or `PGPORT`; it is never hardcoded into source.

Rule: source-correct DB preflight against `127.0.0.1:55432` must pass without relying on cached bytecode before any rebaseline or Stage 19AS-AU work.

## Required Guardrails

- Canonical Stage 19AR mode requires the exact canonical `source_run_key`.
- Canonical Stage 19AR mode requires the exact canonical artifact hash.
- Stage 19AS-AU preflight must reject substitute baselines.
- Substitute runs must not be silently promoted to canonical baselines.
- Stage 19AS-AU must not run unless the exact canonical Stage 19AR `source_run_key` and artifact are present, or a human explicitly approves a new baseline in a separate operator decision.

## Fresh-Chat Handoff

Use this block when resuming Stage 19 in a new chat:

```text
STAGE 19 CURRENT CHECKPOINT

Guardrails:
Stage 19AR canonical identity guardrails are repaired.
Stage 19AS-AU rejects substitute baselines.

Canonical Stage 19AR baseline required:

source_run_key:
stage19ar-edsm-25-row-staging-pilot-381a609ed62b80fd

bridge_key:
source_runs:stage19ar-edsm-25-row-staging-pilot-381a609ed62b80fd

artifact:
418bc0db66978623c460aa8cc46a8ab14811098f39cb99a16274d9d181f19417

rows:
25

Rejected substitute baseline:

source_run_key:
stage19ar-edsm-25-row-staging-pilot-5f777958b81bd034

artifact:
b617d0239b7458b5b881895b564d091c771394b555c88a5bae942fd9d2c10e5e

Recovery status:
Git/local recovery searched current files, branches, tags, stashes, reflogs, deleted-file history, tracked blobs, reflog blobs, unreachable commits/blobs, .codex-artifacts, and .codex-runtime.
canonical_recovery_source_found: false
canonical_stage19ar_restored: false
canonical_artifact_restored: false
ready_for_stage19as_au: false

DB preflight rule:
Source-correct DB preflight against 127.0.0.1:55432 must pass without relying on cached bytecode before any rebaseline or Stage 19AS-AU work.

Rule:
Do not run Stage 19AS-AU until either:
1. the exact canonical Stage 19AR baseline exists, or
2. a human explicitly approves a new canonical baseline in a separate prompt.

Important:
A fresh project DB can authenticate and have schema while still missing the canonical Stage 19AR baseline.
A new 25-row Stage 19AR-like run is not the canonical baseline unless it has the exact canonical source_run_key and artifact.
```
