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

The retired run was valid-looking because it exercised the source run, bridge, staging, diagnostic, provenance, artifact, and visibility path. It is no longer equivalent to the approved canonical Stage 19AR baseline because both the source run key and artifact differ from the approved replacement values.

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

## Required Guardrails

- Canonical Stage 19AR mode requires the exact approved replacement `source_run_key`.
- Canonical Stage 19AR mode requires the exact approved replacement artifact hash.
- Stage 19AS-AU preflight must reject missing or retired baselines.
- Retired runs must not be silently promoted back to canonical baselines.
- Stage 19AS-AU must not run unless the exact approved Stage 19AR `source_run_key` and artifact are present.

## Fresh-Chat Handoff

Use this block when resuming Stage 19 in a new chat:

```text
STAGE 19 CURRENT CHECKPOINT

Guardrails:
Stage 19AR canonical identity guardrails require the approved replacement baseline.
Stage 19AS-AU rejects missing or retired baselines.

Approved canonical Stage 19AR baseline required:

source_run_key:
stage19ar-edsm-25-row-staging-pilot-5f777958b81bd034

bridge_key:
source_runs:stage19ar-edsm-25-row-staging-pilot-5f777958b81bd034

artifact:
b617d0239b7458b5b881895b564d091c771394b555c88a5bae942fd9d2c10e5e

rows:
25

Retired Stage 19AR baseline:

source_run_key:
stage19ar-edsm-25-row-staging-pilot-381a609ed62b80fd

artifact:
418bc0db66978623c460aa8cc46a8ab14811098f39cb99a16274d9d181f19417

status:
retired_unrecoverable

DB preflight rule:
Source-correct DB preflight against 127.0.0.1:55432 must pass without relying on cached bytecode before any rebaseline verification or Stage 19AS-AU work.

Rule:
Do not run Stage 19AS-AU until the exact approved Stage 19AR baseline exists.

Important:
A fresh project DB can authenticate and have schema while still missing the approved Stage 19AR baseline.
A 25-row Stage 19AR-like run is not the approved baseline unless it has the exact approved source_run_key and artifact.
```
