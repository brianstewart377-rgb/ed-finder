# Windows Development Environment

## Purpose

This repo already has good local entrypoints, but many of the older examples
assume Unix shells, `.venv/bin/python`, or an always-available `/bin/bash`.
On Windows, the canonical path is now PowerShell-first with an explicit Git
Bash wrapper where a real bash shell is required.

## Canonical Entry Points

Run these from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/bootstrap-windows.ps1 -RunDoctor
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/doctor.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/doctor.ps1 -RunPreflight
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/reset_local_db.ps1 -ConfirmReset
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start_local_api.ps1 -EnsureServices
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start_local_dev.ps1 -EnsureServices
```

What each one does:

- `bootstrap-windows.ps1`: creates `.venv`, installs Python deps, installs the
  frontend lockfile, creates `.env` from `env.example` when missing, and can
  optionally start the local Postgres/Redis services.
- `doctor.ps1`: checks the local Windows toolchain and repo prerequisites
  without assuming WSL.
- `run-bash.ps1`: launches a real Git Bash shell for repo scripts that still
  need bash semantics.
- `reset_local_db.ps1`: rebuilds the disposable local Postgres database through
  the manifest-ledger migration path and optionally reseeds preview data.
- `start_local_api.ps1`: starts the loopback API with the local Docker services.
- `start_local_dev.ps1`: starts the frontend and, when needed, launches the API
  as well.

## Tooling Expectations

Recommended local tools:

- Git for Windows, including `bash.exe`
- GNU Make 4.4+ for the repository convenience targets
- Python `3.12+`
- Node.js with Yarn support (`yarn` or `corepack yarn`)
- Docker Desktop
- PostgreSQL client tools if you want `pg_isready` checks in the doctor output

`doctor.ps1` will still run without every optional tool, but it will tell you
what is missing.

Install GNU Make without an elevated shell:

```powershell
winget install --id ezwinports.make --exact --scope user --source winget --accept-source-agreements --accept-package-agreements
```

Restart the terminal after installation so the updated user `PATH` is visible.
The Makefile now supports Windows-native GNU Make for its Python verification
targets:

```powershell
make state-check
make test-unit
```

## Bootstrap Flow

Fresh or repaired Windows setup:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/bootstrap-windows.ps1 -StartServices -RunDoctor
```

Optional browser test setup:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/bootstrap-windows.ps1 -InstallPlaywright
```

Notes:

- If `.env` is missing, bootstrap copies `env.example` to `.env`.
- Existing `.env` is preserved unless you pass `-ForceEnvFile`.
- Local Docker services use `docker-compose.local.yml` and bind Postgres on
  `127.0.0.1:55432`.

## Bash Wrapper

Use the wrapper instead of relying on `/bin/bash` existing in the current
terminal host.

Run an inline bash command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/run-bash.ps1 -Command "bash scripts/apply_migrations.sh --include-manual"
```

Run a repo script directly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/run-bash.ps1 -Script scripts/restore_postgres_backup.sh -ScriptArgs @('--target-db', 'edfinder_restore_20260708')
```

If Git Bash is installed somewhere unusual, set `EDFINDER_BASH` to the full
`bash.exe` path before using the wrapper.

## Windows Equivalents

Common Unix-style commands translate to:

```powershell
.venv\Scripts\python.exe -B scripts/dev/test_env_preflight.py
.venv\Scripts\python.exe -B scripts/dev/resolve_project_state.py --strict
.venv\Scripts\python.exe -B scripts/dev/review_environment.py preflight
.venv\Scripts\python.exe -B scripts/dev/review_environment.py verify --mode quick --scenario planner_core --confirm-local-review-environment
```

If you prefer a single verification pass after bootstrap:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/doctor.ps1 -RunPreflight -Strict
```

## Local App Startup

If the local disposable DB needs to be rebuilt through the canonical
manifest-ledger path instead of the historical raw init-script path:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/reset_local_db.ps1 -ConfirmReset
```

Schema-only rebuild:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/reset_local_db.ps1 -ConfirmReset -SchemaOnly
```

API only:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start_local_api.ps1 -EnsureServices
```

Frontend plus API:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start_local_dev.ps1 -EnsureServices
```

The frontend script already redirects Vite cache output to
`$env:LOCALAPPDATA\ED-Finder\vite-cache` when possible, which helps avoid noisy
cache issues in OneDrive-synced workspaces.

## Troubleshooting

- `bash not found`: install Git for Windows or set `EDFINDER_BASH`.
- `make not found`: install `ezwinports.make` with the user-scoped `winget`
  command above, then restart the terminal.
- `Virtualenv not found`: run `bootstrap-windows.ps1`.
- `POSTGRES_PASSWORD is missing in .env`: bootstrap again or edit `.env`.
- `pg_isready_missing`: install PostgreSQL client tools if you want full DB
  readiness checks.
- Docker or Compose failures: start Docker Desktop first, then rerun
  `doctor.ps1 -RunPreflight`.
