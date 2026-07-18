# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

ED-Finder: an Elite Dangerous colonisation planner, currently at **Stage 25** (Stages 25A–25H complete). Product journey: **Explore → Inspect → Plan → Simulate/Sequence → Review Evidence → Export/Share**. The **Colony Cockpit** (Plan workspace) is the canonical live planning surface; the galaxy Map is a secondary Explore surface only, not a planning workspace.

`ed-finder` is one of **three repos** in this workspace, and it is the app-only one:
- `ed-finder` (this repo) — runnable product app, frontend, API, local dev stack. Nothing here should invent new colonisation mechanics truth.
- `colonisation-research-engine` — mechanics/evidence/ontology source of truth (sibling repo, cloned alongside this checkout; not yet wired into ed-finder at runtime).
- `colony-planning-engine` — planning-engine boundary/contracts (sibling repo, cloned alongside this checkout; documentation-only, implementation pending).

If a change is "what does the app do with existing mechanics," it belongs here. If it's "what *is* true about colonisation mechanics," it belongs in `colonisation-research-engine`, not here — don't invent or silently revise mechanics rules in this repo.

## Three-repo architecture (decided 2026-07-12)

Option 2: CRE produces research truth, ed-finder consumes it. CPE owns plan construction (implementation pending). CRE is actively developed but NOT yet wired into ed-finder at runtime. Integration work is queued — do not treat CRE/CPE as dormant.

Do not extend ed-finder's evidence/confidence model without checking CRE's model first. CRE's SA-register and confidence vocabulary are more rigorous and should become canonical.

Current integration gap: confidence vocabularies are incompatible. Resolve this before any evidence-layer integration work begins.

## Read this first

**`docs/ROADMAP.md` is the single canonical roadmap.** Read it before any non-trivial change. Its own stated rule: *"If another document disagrees with this file about what happens next, this file wins."* Historical `docs/colonisation-redesign/stage-N-*.md` files remain useful as rationale/implementation records but are **not** roadmap sources — treat them as archive, not instructions. (`docs/colonisation-redesign/engine-roadmap.md`, which an older version of this file pointed to, is now superseded by `docs/ROADMAP.md`.)

For mechanics-affecting work specifically, also read `docs/reference/colonisation/source-priority.md` first — it defines the source-authority hierarchy (Mega Guide > user empirical findings > DaftMav spreadsheet > OASIS Guide > forum/PDF sources > "reference planner" [RavenColonial] screenshots as UI inspiration only, never mechanics authority > future external data feeds as evidence, not automatic truth). Conflicts must be recorded explicitly, never silently merged/averaged.

**Current hard boundaries (from `docs/ROADMAP.md`) — do not cross these without an explicit roadmap update:**
- No silent planner-truth changes from imported/observed/projected/inferred data.
- No automatic Suggested Build generation/loading or Preview execution.
- No hidden scoring/CP/economy/service/optimiser changes.
- No canonical database write lane unless a stage explicitly authorizes it.
- No scheduler/service/timer activation for import automation by default.
- No map redesign or planner–map fusion.
- No visual cloning, asset copying, or code copying from external planner references (RavenColonial).
- Accounts/OAuth/collaboration/plan-sync, journal-import canonical promotion, and score-weighted colonisation-corridor routing are all explicitly **deferred** pending the foundation work below — don't start them opportunistically.

The repo is mid-response to an external adversarial audit (`docs/development/full-stack-adversarial-audit-2026-07-10.md`, tracked in `docs/operations/audit-remediation-plan.md`). Roadmap's stated foundation-safety order: (1) ratings rebaseline / body-data contract drift, (2) migration-ledger discipline, (3) backup/restore rehearsal, (4) CI/build reproducibility, (5) a bounded hygiene pass, (6) *then* re-evaluate accounts/auth. Treat the audit as a prioritization checkpoint, not a competing roadmap.

## Operational safety gate

Before any prompt/session that changes repo state, runs data-workflow commands, touches local services, or reports Stage 19/test-environment status, run state resolution first (`docs/development/agent-prompt-contract.md`):

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
# Windows: .venv\Scripts\python.exe -B scripts/dev/resolve_project_state.py --strict
```

If it fails, **stop** — do not edit, commit, push, run DB writes, or report anything as `completed`. Valid non-success outputs are `stopped` / `blocked` / `partial_checkpoint`, never a silent `completed`. Active authority is `docs/colonisation-redesign/stage-19-state-authority.json` + the latest merged docs checkpoint + live git state — pasted/uploaded logs are evidence only and never override it. `docs/archive/stage-19-incident-history.md` is historical only, never operational authority. Branch `work` is non-authoritative for Stage 19/test-env operations unless a prompt explicitly declares scratch/docs-only scope.

## Working agreement

### Plan-change discipline
- If a plan changes mid-execution (e.g. switching from approach A to approach B), stop and confirm the change before committing. Do not silently substitute one fix for another the user approved.
- Every commit pushed to origin/main must be followed through to production deploy in the same message, unless the user explicitly says to hold.
- After any deploy, verify the deployed HEAD matches origin/main and report the receipt (commit hash + production `git log`).
- DeepSeek must NEVER edit production files directly. All changes go through the local repo, commit, push, deploy flow — even for one-line production hotfixes.
- Every bug fix ships with a contract/regression test if one could have caught the bug. Fix-only commits without hardening are incomplete — the test is part of the fix, not a follow-up.
- Every bug fix ships with a contract/regression test if one could have caught the bug. Fix-only commits without hardening are incomplete — the test is part of the fix, not a follow-up.
- **Red main is stop-the-line.** A red CI check masks everything downstream of it (red hides red). Fix or revert before the next merge — do not let "probably pre-existing" accumulate. Branch protection (enabled 2026-07-17) now enforces this structurally: all 10 checks must pass to merge.

## Repo hygiene contract (`docs/development/repo-hygiene.md`)

- Repo root is **allowlist-only**: `CHANGES.md`, `docker-compose.yml`, `docker-compose.local.yml`, `docker-compose.review.yml`, `docker-compose.review-hosted.yml`, `env.example`, `Makefile`, `pyproject.toml`, `README.md`, `setup.sh`. A new visible root file needs an explicit allowlist/test update — don't drop planning docs, audits, or handoffs at root; they belong under `docs/development/` (dated, lowercase-hyphenated names) or `docs/archive/`.
- Prototype/preview UI must not quietly become reachable from the live runtime entrypoint.
- Operator scripts declare active (`scripts/operator/`) vs. historical (`scripts/operator/archive/`) status explicitly.
- Keep `main` boring: `git fetch origin --prune` + `git pull --ff-only`, short-lived topic branches for work, delete merged local/remote branches promptly. Enforced by `tests/test_repo_hygiene_contract.py` and `tests/test_bounded_hygiene_pass.py`.

## Commands

Windows is the primary local dev target now (`docs/development/windows-dev-environment.md`) — prefer the PowerShell wrappers over hand-translating Unix examples:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/bootstrap-windows.ps1 -RunDoctor   # fresh setup: .venv, deps, .env, optional services
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/doctor.ps1 -RunPreflight            # check local toolchain/services
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/reset_local_db.ps1 -ConfirmReset    # rebuild disposable local Postgres via the ledger path
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start_local_api.ps1 -EnsureServices
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start_local_dev.ps1 -EnsureServices # frontend (+ API if needed)
```

Local Docker services run via `docker-compose.local.yml`, with Postgres bound to `127.0.0.1:55432` (not 5432) and Redis on `127.0.0.1:6379` — this is intentional, to keep local test runs off any host Postgres listening on 5432. `tests/helpers/db_isolation.py` enforces this: it's fail-closed, refuses production-looking targets, and requires `EDFINDER_ALLOW_HOST_5432_TEST_DB=yes` to target 5432 or `EDFINDER_TEST_DB_ALLOW_DESTRUCTIVE_RESET=yes` to allow a destructive reset outside CI.

- DB/seed changes are proven against a local `postgres:16-alpine` container (matching CI: `edfinder:edfinder@localhost:5432/edfinder`) before push, not discovered in CI.

```bash
# Backend — the repo-local .venv is the canonical Python runner; Makefile auto-detects it
ruff check apps tests scripts shared_contracts               # lint
make test-env-check                                           # preflight: pytest/docker/postgres/redis/creds, no writes
make state-check                                               # Stage 19/test-env state-resolution gate (see above)
make test-unit                                                 # tests needing no external services
make test-db                                                   # DB-marked tests (explicit skip if no real service)
make test-integration                                          # integration-marked tests
make test-ci-local                                              # focused local CI parity pass
python -m pytest tests/test_optimiser.py -q                    # single test file
python -m pytest tests/test_optimiser.py::test_name -q         # single test
```

Pytest markers in use: `unit`, `integration`, `db`, `operator`, `slow`, `e2e`, `frontend`, `requires_docker`, `requires_postgres`, `requires_redis`. Real-service tests must use the right marker and skip explicitly when the service/credentials/baseline data are absent — never silently fall back to a fake and call it a pass.

```bash
# Frontend (frontend/ — NOT frontend-v2, that was renamed upstream)
cd frontend
yarn install          # yarn.lock IS committed and pinned now — do not run without --frozen-lockfile assumptions changing
yarn typecheck
yarn lint
yarn knip --files     # CI-gated unused frontend source-file check
yarn test              # wraps vitest via scripts/run-vitest.mjs
yarn test:planner       # scoped: colony-planner + simulation-preview
yarn test:operator      # scoped: OperatorCockpitTab / api.operator / useHashRoute
yarn test:map           # scoped: map feature + api.map
yarn test:ci            # the full split suite CI actually runs
yarn build              # tsc + vite build
yarn e2e                # playwright
yarn types:gen          # regenerate src/types/api.gen.ts from a running API's OpenAPI schema
```

If `yarn` isn't on `PATH` (e.g. a fresh shell before running the bootstrap script), use `npx yarn <args>` — `package.json` pins `"packageManager": "yarn@1.22.22"` and `npx` will fetch/run that version without needing `corepack enable` (which can fail with `EPERM` against a shared Node install directory).

`pyproject.toml` holds project metadata and the repository Ruff contract; real deps live per-service in `apps/{api,eddn,importer}/requirements.txt`.

## Architecture

### Backend composition root

`apps/api/src/main.py` is the FastAPI composition root. `apps/api/src/server.py` is a 7-line shim (`from main import app`) kept only for an older `uvicorn server:app` supervisor invocation — always edit `main.py`. Production Docker runs `uvicorn main:app`.

`search_economies.py` is the single source of truth for economy/body-filter column mappings (it replaced four independently-drifting copies) — any new economy-keyed lookup belongs there.

### Colony Planner subsystem map (`apps/api/src/`)

- **`domain/`** — foundational rules/data, no I/O. `colonisation_rules.py` classifies bodies into economy profiles; `facilities.py` loads the facility-template catalogue.
- **`mechanics/`** — pure constants/rules shared across subsystems (CP cost curves, link/topology/economy/service/scoring rules, `versions.py`'s `MECHANICS_VERSION`, `confidence.py`'s `ConfidenceLevel` vocabulary). No DB/asyncio.
- **`simulation/`** — the deterministic build engine (`cp_simulator.py`, `buildability.py`, `topology_simulator.py`, `economy_simulator.py`/`economy_stack.py`/`port_economy.py`, `service_graph.py`, `build_order.py`, `build_preview.py`/`preview_pipeline.py`/`preview_response.py`, `cp_repair.py`, `mechanics_trace.py`).
- **`recommendations/`** — generates/ranks candidate builds; backs the recommended-builds endpoint.
- **`optimiser/`** — bounded deterministic candidate generation (does not compare alternatives, apply candidates, or alter simulation mechanics). Entry: `candidate_generator.generate_candidates()`.
- **`regional/`** — regional positioning intelligence.
- **`observations/`** — user-submitted "observed facts" vs. engine predictions, plus a newer comparison-engine package and a `review/` advisory layer. **Two comparison engines exist deliberately** (older in-pipeline comparator vs. a newer modularized one) — don't merge them without checking why first.
- **`colony_planner/`** — in-game colony layout import helper.
- **`evidence_store/`** — newer: backs the Stage 20+ evidence/provenance surfaces (readonly evidence adoption, per-system warehouse joins) referenced throughout `docs/colonisation-redesign/stage-2{0,3,4}-*`.
- **`journal_import/`** — newer: backs the bounded `A-1` journal-import staging/evidence lane (client-side parsed, no canonical writes yet — see ROADMAP boundaries above).
- **`edfinder_api/`** — a newer, more conventionally-packaged module; check whether new code should land here vs. the flat `apps/api/src/*.py` style before adding files.

**CP** = Construction Points (Elite Dangerous's colony-building currency), not "Colony Planner" — same acronym, unrelated. Mechanics in `mechanics/cp_rules.py` + `simulation/cp_simulator.py`/`cp_repair.py`.

`tests/test_trust_layer.py` cross-checks that `domain.facilities`, `mechanics.confidence`/`constants`/`link_rules`, `mechanics.versions.MECHANICS_VERSION`, `regional.regional_analysis`, and `simulation.build_preview` stay mutually consistent — run it after touching any of those.

### Scoring vocabulary (`docs/development/scoring-vocabulary-decision-2026-07-10.md`)

Three layers, three deliberately different names — don't collapse them into one term:
- **UI / player-facing copy:** "Development Score" (Finder rerank helper surface: "Development Tuning" — an advanced helper, not primary nav).
- **API rerank endpoint family:** `archetypes` (`/api/archetypes/...`, `/api/ratings/rerank` internals).
- **Database / operational implementation:** `ratings` / `rating_version` (currently **Ratings v3.4**).

Backend/API code still uses `optimiser`/`candidate`/`archetype` vocabulary in many places for compatibility even where user-facing UI copy has moved on — don't rename backend identifiers to match UI copy without checking `docs/api-contracts.md` and the current roadmap stage first.

### Type contract (backend ↔ frontend)

`apps/api/src/models.py` is the source of truth for HTTP wire types. `frontend/src/types/api.gen.ts` is auto-generated (`yarn types:gen`, wraps `scripts/types-gen.mjs`) from the live OpenAPI schema — **never hand-edit it**; CI's `openapi-types` job fails on drift. Note: the `openapi-types` job runs data-invariants + boots the API **before** type generation, so a red job there is often an upstream failure (seed invariants, or the API failing to boot) rather than a types problem — check the earlier steps first. Avoid `Optional[dict]` in Pydantic request models (Pydantic 2.10+ turns bare `dict` into the unusable `Record<string, never>` via `openapi-typescript`) — use a real sub-model or `Any`. Full conventions: `docs/api-contracts.md`.

### Frontend (`frontend/`)

Renamed from `frontend-v2/` upstream — it now serves at `/`, not `/v2/`. Vite + React 19 + TS 5 + Tailwind 3, TanStack Query for server cache, Zustand for local stores. Feature-folder layout under `src/features/*`, including `colony-planner/` (the dedicated Cockpit workspace route) and `system-detail/simulation-preview/` (the embedded planner, further split into `observations/`, `optimiser/`, `validation/`). The retired redesign prototype is historical material under `docs/archive/frontend-redesign-prototype/`, not a runtime source tree. All API calls go through `src/lib/api.ts` — don't scatter raw `fetch()` calls for endpoints that already have a helper.

`package.json` scripts wrap most tooling in small Node scripts rather than calling the underlying CLI directly (`scripts/run-vitest.mjs`, `scripts/types-gen.mjs`, `scripts/dev-doctor.mjs`, `scripts/start-or-reuse.mjs`) — `predev`/`prestart` run a doctor check automatically. `yarn.lock` is committed and pinned (CI installs against it); this is a change from the earlier no-lockfile era, don't assume it's still intentionally absent.

### Data layer

PostgreSQL 16, 186M+ `systems` rows. Migrations are numbered `sql/NNN_*.sql`, applied in manifest order, and protected by the active `schema_migrations` checksum ledger through `scripts/apply_migrations.sh`; production's ledger state and manual migration 019 bookkeeping have been verified. Backup/restore automation exists and has been rehearsed locally (`scripts/rehearse_postgres_restore.sh`, `scripts/restore_postgres_backup.sh`, `docs/operations/postgres-backup-and-restore.md`, receipts under `artifacts/restore-rehearsals/`) — both were previously known gaps, so do not report them as pending.

Current production data-integrity receipts report zero persisted body, no-body-rating, ring, station-link, and evidence-lifecycle drift. Preserve that baseline through receipted invariant checks and bounded reconciliation; freshness age is telemetry, not itself a persisted-integrity failure. `apps/importer/src/` still holds the Spansh-dump import + post-import builders — invoke via `scripts/run_import.sh`, never raw `docker run` (bulk `UPDATE systems` needs `SET session_replication_role = replica` to avoid RI-trigger storms — apply that pattern to any new bulk-update script).

`pgbouncer` is defined in `docker-compose.yml` but not in the live request path — `api`/`eddn` connect directly to Postgres (a prior incident traced to pgbouncer's transaction-pool mode dropping session-level `SET`s).

### Compose files

Four now exist, not one: `docker-compose.yml` (production stack), `docker-compose.local.yml` (disposable local dev Postgres/Redis on `127.0.0.1:55432`), `docker-compose.review.yml` + `docker-compose.review-hosted.yml` (the hosted PR-review-lab environment — `docs/operations/hosted-review-environment.md`).

### CI

Split across multiple workflow files now, not just one `ci.yml`:
- `.github/workflows/ci.yml` (8 jobs, all required by branch protection): `Backend unit tests + compose validate`, `Script contracts + migration paths`, `Backend integration (PG+Redis)`, `Canonical safety tests`, `Nginx config syntax`, `OpenAPI types drift check`, `Frontend build`, `Frontend v2 E2E (Playwright)`. Plus the separate `Container image parity` workflow (`Built image parity`), also required.
- `.github/workflows/container-image-parity.yml`: build-reproducibility parity check.
- `.github/workflows/review-lab.yml` (`Review Lab`, required by branch protection): the isolated full browser review journey. It runs on every pull request so the required context is never absent, and remains manually triggerable with `workflow_dispatch`.
- `.github/workflows/hetzner-operator.yml`: production operator workflow (`docs/operations/github-actions-hetzner-operator.md`).

### Operator scripts (`scripts/operator/`)

Stage 19 warehouse/enrichment operator scripts live here, split into active (top level + `actions/`) and `archive/`. `require_hetzner_operator_env.sh` gates production-touching operator scripts. **Stage 19 (data warehouse/enrichment) is currently paused** for test-environment hardening, not actively worked — don't resume Stage 19 operator actions without checking `docs/ROADMAP.md`'s current status first; the state-resolution gate above will hard-stop most of them anyway outside the right branch/context.

## Frontend deployment

After any frontend code change is pushed to origin/main, the production deploy sequence is:

```sh
cd /opt/ed-finder && git pull origin main
cd frontend && yarn install --immutable && yarn build
docker compose restart nginx
```

This must always end with `docker compose restart nginx` — nginx serves the static dist via a volume mount and requires a restart to pick up the new build. Without it the site 404s.

## Operational patterns

### Cross-app imports in importer scripts
`build_regional_analysis.py` needs to import from `apps/api/src/mechanics/` and `apps/api/src/regional/`. The importer container makes this work by:
- `docker-compose.yml` mounts `./apps/api/src` as `/app/apps_api_src:ro`
- The script's `_find_api_src()` checks this vendored path first, then falls back to marker-file walk-up

Do not remove.

### run_importer entrypoint
The `importer` image sets `ENTRYPOINT ["python3"]`. `docker compose run <service> <cmd>` appends the given command on top of the entrypoint rather than replacing it, so `run_importer()` in `scripts/nightly_update.sh` must invoke it as `docker compose run --rm --entrypoint python3 importer <script> <args>` — never pass a redundant literal `python3` as part of `<cmd>`, or every invocation fails trying to execute a file named `python3`. `scripts/run_dirty_ratings_if_needed.sh` already uses the correct `--entrypoint python3` pattern; match it.

### Dirty ratings maintenance
`scripts/run_dirty_ratings_if_needed.sh` owns both sides of the deferred queue
under one `flock`: it first runs bounded `reconcile_no_body_ratings.py` cleanup,
then counts and rates only `rating_dirty = TRUE AND has_body_data = TRUE` rows.
Do not remove the no-body cleanup or broaden the ratings stream back to all
dirty systems; truthful no-body rows otherwise become permanent retry errors
and stale ratings survive indefinitely.

### Nightly job caps
`build_archetype_scores.py`'s new-system mode has a hidden `limit or 10_000_000` fallback that silently caps at 10M rows if `--limit` isn't passed explicitly — always pass `--limit`. `scripts/nightly_update.sh` caps new-system archetype scoring and regional-analysis backfills at 5,000,000 rows/night to avoid unattended multi-day runs; lower this once each backlog clears (e.g. to `--limit 500000` for steady-state maintenance).

### SSH MCP setup on Windows
ssh-mcp / npx path resolution can trip on case sensitivity in Windows system paths — encountered case where the tool looked for "SYSTEM32" (uppercase) instead of "System32". If `claude mcp list` shows connected but `/mcp` shows no servers, run `claude doctor` to diagnose config validation errors.

### Model routing (DeepSeek vs Sonnet)

Use DeepSeek for:
- Running structured diagnostic queries and reporting factually
- Executing well-specified fixes where the diagnosis is settled
- Reading files and reporting contents verbatim
- Applying already-validated patterns to new instances
- Any task that fits the "tight prompt" template below

Use Sonnet for:
- Diagnosis of unknown-cause issues
- Cross-file reasoning about consequences
- Code review of DeepSeek's diffs on production-touching code
- Interpreting ambiguous data
- Deciding severity or priority when facts alone don't decide
- Final sanity check before deploying anything

Split principle: DeepSeek gathers, Sonnet reasons.

#### Tight prompt template for DeepSeek

DeepSeek performs well with tight, self-contained prompts. Loose prompts let it fill gaps with confident but wrong inferences. Every DeepSeek prompt should include:

1. Explicit scope — exact files, tables, or commands. No open-ended "investigate."
2. Required output shape — table format with defined columns, or bulleted list with defined structure.
3. Explicit "do not" list:
   - Do not assign severity, priority, or urgency
   - Do not recommend actions
   - Do not interpret "empty" or "0" as any specific cause
   - Do not substitute alternative commands if given ones fail
   - Do not fix, commit, or deploy anything
4. Verification requirement — every finding must cite the file/line, query output, or command return code.
5. Instruction to report errors verbatim rather than working around them.

Example format:
```
Task: [narrow, specific]
Required output: table with columns X, Y, Z
Commands to run (exact, do not substitute):
  1. [command]
  2. [command]
Rules:
- Do not [list]
- Report [format]
Output the table only. No preamble or summary.
```

Never tell the user to just run yarn build without the nginx restart. Always give the full three-step sequence.
