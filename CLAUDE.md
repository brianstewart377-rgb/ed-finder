# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start for New Contributors

**Before making ANY change, read these in order:**
1. `docs/ROADMAP.md` — the single source of truth for what ships next
2. The "Current lane" section below
3. The "Operational safety gate" before running data commands

**Common commands** (from Windows terminal):
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start_local_dev.ps1 -EnsureServices` — start dev server + API
- `cd frontend && yarn test:map` — test map feature
- `cd frontend && yarn dev` — frontend dev server (port 5173)
- `make test-unit` — run backend tests

**Key files for navigation:**
- Backend entry: `apps/api/src/main.py`
- Frontend root: `frontend/src/`
- Simulations/planning logic: `apps/api/src/simulation/`

## What this is

ED-Finder: an Elite Dangerous colonisation planner. **Stage status (this line is a summary of `docs/ROADMAP.md`, which is the authority — keep it in sync after every lane change):** Stages 25A–25H and **26A–26E are complete**. **Stage 27A Spatial Platform Contract and Audit is current and documentation-only; no Babylon runtime implementation is authorized.** The Stage 26 R3F/Three.js desktop map (cutover commit `3b53477`) remains production and rollback (`VITE_STAGE26E_PRODUCTION_MAP=disabled`) until a later Stage 27 bakeoff explicitly earns cutover. Stage 27 may support **Explore → Inspect → Plan → Review** spatially, but Colony Planner/Cockpit remains the canonical detailed Build Plan workspace/persistence owner. No renderer owns planning logic or mechanics, and no map action may silently mutate a Build Plan or execute Preview.

`ed-finder` is one of **three collaborating repositories**, and it is the app-only one (siblings may not be mounted in every checkout):
- `ed-finder` (this repo) — runnable product app, frontend, API, local dev stack. Nothing here should invent new colonisation mechanics truth.
- `colonisation-research-engine` — mechanics/evidence/ontology source of truth (sibling repo, cloned alongside this checkout; not yet wired into ed-finder at runtime).
- `colony-planning-engine` — planning-engine boundary/contracts (sibling repo, cloned alongside this checkout; documentation-only, implementation pending).

If a change is "what does the app do with existing mechanics," it belongs here. If it's "what *is* true about colonisation mechanics," it belongs in `colonisation-research-engine`, not here — don't invent or silently revise mechanics rules in this repo.

## ROADMAP — Read Before Any Change

**`docs/ROADMAP.md` is the single canonical roadmap.** It is the authority on what ships next, what's deferred, and what's currently active. Read it first before any non-trivial change. Its own rule: *"If another document disagrees with this file about what happens next, this file wins."*

Historical context: `docs/colonisation-redesign/stage-N-*.md` files contain rationale and implementation records but are **not** roadmap sources — treat them as archive. (`docs/colonisation-redesign/engine-roadmap.md` is now superseded by `docs/ROADMAP.md`.)

## Current Lane

**Current lane:** Stage 27A Spatial Platform Contract and Audit.

**Active focus:** Authoritative product, architecture, data-readiness,
migration, governance and cross-repo contracts. Stage 27A authorizes Stage 27B
only; do not implement or wire a Babylon runtime in 27A.

**Deferred work:** Accounts/auth, journal A-2/A-3, score-weighted corridor routing, real-star LOD streaming (Phase 2).

**Next map stage:** Stage 27B Babylon 9 Runtime Workbench, only after Stage 27A
acceptance and in isolation from the production route.

**Critical context:** Repo is mid-response to external adversarial audit. Foundation-safety prioritization order:
1. Ratings rebaseline / body-data contract drift
2. Migration-ledger discipline
3. Backup/restore rehearsal
4. CI/build reproducibility
5. Bounded hygiene pass
6. *Then* re-evaluate accounts/auth

See `docs/ROADMAP.md` (the authority) and `docs/operations/audit-remediation-plan.md` for full sequencing. Do not start deferred work opportunistically.

## Three-repo architecture (as of 2026-07-12)

Option 2: CRE produces research truth, ed-finder consumes it. CPE owns plan construction (implementation pending). CRE is actively developed but NOT yet wired into ed-finder at runtime. Integration work is queued — do not treat CRE/CPE as dormant.

Do not extend ed-finder's evidence/confidence model without checking CRE's model first. CRE's SA-register and confidence vocabulary are more rigorous and should become canonical.

**Current integration gap:** the ED-Finder reconciliation document exists, but
there is no released CRE runtime/publication bridge and confidence remains
layer-specific. Do not map labels by spelling or claim live integration.

For mechanics-affecting work specifically, also read `docs/reference/colonisation/source-priority.md` first — it defines the source-authority hierarchy (Mega Guide > user empirical findings > DaftMav spreadsheet > OASIS Guide > forum/PDF sources > "reference planner" [RavenColonial] screenshots as UI inspiration only, never mechanics authority > future external data feeds as evidence, not automatic truth). Conflicts must be recorded explicitly, never silently merged/averaged.

**Current hard boundaries (from `docs/ROADMAP.md`) — do not cross these without an explicit roadmap update:**
- No silent planner-truth changes from imported/observed/projected/inferred data.
- No automatic Suggested Build generation/loading or Preview execution.
- No hidden scoring/CP/economy/service/optimiser changes.
- No canonical database write lane unless a stage explicitly authorizes it.
- No scheduler/service/timer activation for import automation by default — one deliberate, named exception: the EDDN simulation ingest background task (`apps/api/src/ingest/eddn_client.py`, `EDDN_SIMULATION_INGEST_ENABLED`, defaults **on** as of 2026-08-07). It feeds `journal_events`/`body_scan_facts` from the live public EDDN relay for the simulation/buildability engine — the same relay `apps/eddn/eddn_listener.py` already consumes continuously for `systems`/`bodies`/`stations`, just a narrower slice of events into different tables — as an always-fresh complement to the client-side journal-import lane, which only covers systems a user has actually uploaded a journal for. This is a live network feed, not the deferred journal-import work below; see that bullet for the distinction. Any *other* new scheduler/service/timer still needs an explicit roadmap update.
- Spatial-platform work is authorized only through `docs/ROADMAP.md` and the
  Stage 27 contracts. Stage 27A is docs/audit only and authorizes 27B only.
  The old global “secondary Explore only / planner-map fusion prohibited” rule
  is superseded: spatial interaction may support Explore → Inspect → Plan →
  Review, but Colony Planner owns detailed plan persistence, actions are
  explicit, and planned/inferred/schematic state never appears as existing fact.
- No visual cloning, asset copying, or code copying from external planner references (RavenColonial).
- Accounts/OAuth/collaboration/plan-sync, journal-import canonical promotion, and score-weighted colonisation-corridor routing are all explicitly **deferred** pending the foundation work below — don't start them opportunistically. "journal-import canonical promotion" here means promoting *client-uploaded* journal-import staging data (`journal_import/store.py`, the bounded A-1 staging lane) to canonical/trusted status — a decision about trusting user-submitted evidence. That is a different question from the EDDN simulation ingest exception above, which is a live network feed with no user-upload trust decision involved.

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
- A merge to `origin/main` does not authorize a production deploy. Follow the explicit owner-approved release sequence under **Frontend deployment**.
- After any deploy, verify the deployed HEAD matches origin/main and report the receipt (commit hash + production `git log`).
- DeepSeek must NEVER edit production files directly. All changes go through the local repo, commit, push, deploy flow — even for one-line production hotfixes.
- Every bug fix ships with a contract/regression test if one could have caught the bug. Fix-only commits without hardening are incomplete — the test is part of the fix, not a follow-up.
- Every bug fix ships with a contract/regression test if one could have caught the bug. Fix-only commits without hardening are incomplete — the test is part of the fix, not a follow-up.
- **Check the automated review bot (`chatgpt-codex-connector` "Codex Review") before merging, not just CI.** Green CI checks correctness of what's tested; it says nothing about a finding a review pass would catch. Check both inline comments AND the top-level review body — they're two different endpoints, and checking only the first misses findings the bot puts only in the summary: `gh api repos/<owner>/<repo>/pulls/<n>/comments --paginate --jq '.[] | {path, line, body}'` for inline, `gh api repos/<owner>/<repo>/pulls/<n>/reviews --paginate --jq '.[] | {state, body}'` for the top-level review. `--paginate` on both is required, not optional — the endpoint defaults to 30 results per page and a PR with more comments than that silently truncates without it. But its findings are not ground truth either — verify each one against the actual code before acting on it (trace a value to where it's actually persisted/used, grep the whole repo before calling something unused, read the full test file before claiming a gap exists) the same way you'd verify any other claim. On 2026-08-06/07 several of its findings were real and caught genuine bugs; several others were wrong when checked (a value described as "hardcoded" was actually recomputed by a live query three lines later; a "no test covers this" claim was false for two of three cited cases). Treat it as a second reviewer worth listening to, not an oracle.
- **Red main is stop-the-line.** A red CI check masks everything downstream of it (red hides red). Fix or revert before the next merge — do not let "probably pre-existing" accumulate. Branch protection (enabled 2026-07-17) now enforces this structurally: all 11 checks must pass to merge (10 through 2026-08-08; `Semgrep` was added that day — see the CI section below).

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
- **`ingest/`** (`eddn_client.py`) — background asyncio task (wired into the FastAPI lifespan, `EDDN_SIMULATION_INGEST_ENABLED`, defaults on) feeding `journal_events`/`body_scan_facts` from the live public EDDN relay. Independent of `journal_import/`'s client-upload lane above — see the roadmap-boundaries section's named exception for why this isn't the deferred "journal-import canonical promotion" work.
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

Renamed from `frontend-v2/` upstream — it now serves at `/`, not `/v2/`. Vite + React 19 + TS 5 + Tailwind 3, TanStack Query for server cache, Zustand for local stores. Feature-folder layout under `src/features/*`, including `colony-planner/` (the dedicated Cockpit workspace route) and `system-detail/simulation-preview/` (the embedded planner, further split into `observations/`, `optimiser/`, `validation/`). The retired redesign prototype is historical material under `docs/archive/frontend-redesign-prototype/`, not a runtime source tree. All API calls go through `src/lib/api/` (domain-scoped modules — `core.ts`, `search.ts`, `planner.ts`, `observations.ts`, `operator.ts`, `map.ts` — reassembled by `index.ts`) — don't scatter raw `fetch()` calls for endpoints that already have a helper, and don't recreate a flat `src/lib/api.ts`: TypeScript resolves an exact file match before a directory's `index.ts`, so a stray flat file would silently shadow the real barrel.

`package.json` scripts wrap most tooling in small Node scripts rather than calling the underlying CLI directly (`scripts/run-vitest.mjs`, `scripts/types-gen.mjs`, `scripts/dev-doctor.mjs`, `scripts/start-or-reuse.mjs`) — `predev`/`prestart` run a doctor check automatically. `yarn.lock` is committed and pinned (CI installs against it); this is a change from the earlier no-lockfile era, don't assume it's still intentionally absent.

### Data layer

PostgreSQL 16, 186M+ `systems` rows. Migrations are numbered `sql/NNN_*.sql`, applied in manifest order, and protected by the active `schema_migrations` checksum ledger through `scripts/apply_migrations.sh`; production's ledger state and manual migration 019 bookkeeping have been verified. Migration sessions default to `MIGRATION_STATEMENT_TIMEOUT=1h` and `MIGRATION_LOCK_TIMEOUT=30s`; finite overrides are allowed for reviewed migrations, but setting either to zero requires `EDFINDER_ALLOW_UNBOUNDED_MIGRATION_TIMEOUTS=yes`. Backup/restore automation exists and has been rehearsed locally (`scripts/rehearse_postgres_restore.sh`, `scripts/restore_postgres_backup.sh`, `docs/operations/postgres-backup-and-restore.md`, receipts under `artifacts/restore-rehearsals/`) — both were previously known gaps, so do not report them as pending.

Current production data-integrity receipts report zero persisted body, no-body-rating, ring, station-link, and evidence-lifecycle drift. Preserve that baseline through receipted invariant checks and bounded reconciliation; freshness age is telemetry, not itself a persisted-integrity failure. `apps/importer/src/` still holds the Spansh-dump import + post-import builders — invoke via `scripts/run_import.sh`, never raw `docker run`. Every bulk write that updates `systems`, `bodies`, clusters, or `ratings` must follow `docs/development/bulk-database-write-safety.md`: use the shared fail-closed replica-mode helper where safe, or document the explicit trigger-preserving exception next to the write.

`scripts/sync_password.sh` is the single password verification/update path used by `setup.sh` and `scripts/run_import.sh`. The former setup-time plaintext interpolation and password-printing hazard is resolved, and CI rejects inline shell password SQL outside the synchronizer. Keep credentials off argv and SQL text: verification uses an stdin-fed, short-lived in-container passfile against the SCRAM-authenticated container address, and updates use psql `\password`. Never restore a password-bearing libpq URI or `ALTER USER ... PASSWORD '<shell value>'` command.

`pgbouncer` is defined in `docker-compose.yml` but not in the live request path — `api`/`eddn` connect directly to Postgres (a prior incident traced to pgbouncer's transaction-pool mode dropping session-level `SET`s).

### Compose files

Four now exist, not one: `docker-compose.yml` (production stack), `docker-compose.local.yml` (disposable local dev Postgres/Redis on `127.0.0.1:55432`), `docker-compose.review.yml` + `docker-compose.review-hosted.yml` (the hosted PR-review-lab environment — `docs/operations/hosted-review-environment.md`).

### CI

Split across multiple workflow files now, not just one `ci.yml`:
- `.github/workflows/ci.yml` (9 jobs, all required by branch protection): `Detect changed paths`, `Backend unit tests + compose validate`, `Script contracts + migration paths`, `Backend integration (PG+Redis)`, `Canonical safety tests`, `Frontend build`, `Nginx config syntax`, `OpenAPI types drift check`, `Frontend v2 E2E (Playwright)`. Plus two separate workflow files, also required: `Container image parity` (`Built image parity`) and `Semgrep`. A third separate workflow, `CodeQL`, exists but is not yet required — see below.
- `.github/workflows/container-image-parity.yml`: build-reproducibility parity check.
- `.github/workflows/review-lab.yml` (`Review Lab`, required by branch protection): the isolated full browser review journey. It runs on every pull request so the required context is never absent, and remains manually triggerable with `workflow_dispatch`.
- `.github/workflows/semgrep.yml` (`Semgrep`, required by branch protection, added 2026-08-08): `p/ci` + `p/security-audit` + `p/secrets` via the Semgrep OSS CLI, `--error` so any finding fails the job. New findings need the same per-site verification discipline as everything else here (real false positive vs. real issue) before adding a `# nosemgrep` suppression or an `--exclude-rule` — see the commit history on PR #440 for the standard this repo holds suppressions to.
- `.github/workflows/codeql.yml` (`CodeQL`, added 2026-08-09, **not yet required by branch protection**): GitHub's semantic/dataflow (taint-tracking) analysis, matrixed over `python` and `javascript-typescript`, plus a weekly Monday scheduled run. Job-level `permissions:` must list `contents: read` explicitly alongside `security-events: write` — declaring any job-level `permissions:` block resets every unlisted scope to `none`, so without it `actions/checkout` has no repo read access (matches `ci.yml`'s `changes` job; this repo is currently public, so checkout can silently succeed via anonymous fallback even when that scope is missing — don't rely on that). Complements Semgrep's pattern-matching with real taint-tracking for CodeQL's own catalogued vulnerability classes (SQL/command injection, XSS, unsafe deserialization, etc.). **It is not a substitute for domain-specific validation review**: the default query suite has no notion of this app's own business invariants (a payload byte-size cap, "must be a finite float", "must not contain a NUL character") — it will not flag a value that's missing one of those checks merely because the value later reaches a parameterized DB insert, since a parameterized insert is precisely the *safe* pattern CodeQL's injection queries look for, not a violation. None of the 2026-08-09 exploration-API Codex Review findings (NaN/Infinity, NUL bytes, unbounded payload size, budget-accounting logic) would have been caught by this scan; don't describe or rely on it as if they would be. Also note: `analyze` uploads SARIF findings to the Security tab but does not fail the job based on alert severity by default — making this workflow "required" would only gate on the scan running successfully, not on new alerts, unless GitHub's separate code-scanning branch-protection alert gate is configured too. Deliberately left out of the required-checks gate for now so it can run and be observed against this codebase's existing surface area first; promote it to required (matching how Semgrep was added and immediately required) once it's proven stable, and decide the alert-gating question explicitly at that point rather than assuming "required" already covers it.
- `.github/workflows/hetzner-operator.yml`: production operator workflow (`docs/operations/github-actions-hetzner-operator.md`).
- `.github/dependabot.yml` (added 2026-08-08): weekly, grouped-per-ecosystem, 7-day cooldown. Covers `github-actions` (every action in the workflows above is pinned to a commit SHA, not a mutable tag like `@v4` — Dependabot is what keeps those pins from going stale) plus `pip` for each of `apps/api`, `apps/eddn`, `apps/importer` independently, and `npm` for `frontend`. Every Dependabot PR goes through the full required-checks gauntlet above like any other PR.
- `.github/workflows/dependabot-auto-merge.yml` (added 2026-08-08): patch/minor Dependabot PRs auto-merge once every required check passes (`gh pr merge --auto`, gated on the repo's "Allow auto-merge" setting). Major-version bumps are deliberately excluded — they still need a human to merge. Branch protection currently has no required-review count, so passing CI is the only gate; don't add a required-review count without re-checking whether this auto-merge policy still makes sense under it.

### Operator scripts (`scripts/operator/`)

Stage 19 warehouse/enrichment operator scripts live here, split into active (top level + `actions/`) and `archive/`. `require_hetzner_operator_env.sh` gates production-touching operator scripts. **Stage 19 (data warehouse/enrichment) is currently paused** for test-environment hardening, not actively worked — don't resume Stage 19 operator actions without checking `docs/ROADMAP.md`'s current status first; the state-resolution gate above will hard-stop most of them anyway outside the right branch/context.

## Frontend deployment

See memory: [[frontend_deploy_sequence]] for the manual deployment procedure, pre-deployment verification, and drift detection.

## Visual testing before deploy (mandatory)

**Any change affecting rendering, layout, or UI must be tested visually before deploy. No exceptions.**

This includes:
- Three.js/canvas rendering (map heatmap, stars, layers)
- CSS/Tailwind layout changes
- Component restructuring affecting visual output
- Opacity, color, size calculations
- Anything users *see*

**Process:**
1. **Start Docker** if not running: `docker compose -f docker-compose.local.yml up -d`
2. **Run E2E tests** (uses live backend): `cd frontend && npx playwright test --project=chromium`
3. **Use Storybook** for isolated component inspection before E2E
4. **DO NOT DEPLOY** without visual verification passing

**Why:** Unit tests verify behavior, not visuals. A heatmap rendering bug (giant cells covering regions) passed all unit tests but reached production because visual E2E testing was skipped. Storybook and Playwright E2E exist to catch this; use them.

See memory: [[visual_testing_mandatory]] for the full rule.

## Debugging data drift

See memory: [[debugging_data_drift]] for the methodology earned from the body_rings association_status hunt — check schema before code, every write verb, and verify claims before reasoning on top of them.

## Known hazards in this codebase

- **bodies.id is application-supplied with no sequence.** The primary key is
  `id` alone. The EDDN listener binds the journal's BodyID, which is only
  unique *within* a system, so two systems scanning the same BodyID collide.
  This structural hazard remains: migration 041 adds the composite unique
  index but does not remove the global `id` primary key, and attractions,
  station_body_links and body_rings still FK to `bodies(id)`. Guarded writers
  prevent re-parenting today: EDDN uses
  `WHERE bodies.system_id64 = EXCLUDED.system_id64`, Spansh passes
  `guard_col='system_id64'`, and the review seed validates existing ownership
  before writing (with the same SQL predicate as a race-safe backstop). The
  preview SQL seed uses `ON CONFLICT (id) DO NOTHING`. Every future bodies
  writer must perform the same pre-write ownership check and retain a
  same-system conflict guard; an unguarded upsert can corrupt all three FK
  consumers. The bounded schema follow-up is to add/attach a real
  `UNIQUE(system_id64, id)` constraint once every live writer is guarded,
  then separately convert the PK and dependent FKs to composite identity.

- **body\_rings.association\_status is `NOT NULL DEFAULT 'local\_matched'`.**
  Any INSERT that omits the column silently asserts a verified local match.
  As of 2026-08-08 (Emergent recurrence report B1) all five ring writers set
  it explicitly — `importer/enrich_system_data.py` was the last one relying
  on the schema default; watch for this regressing on any new writer.

- **body\_rings has five writers**: eddn_listener.py, ingest/eddn_client.py,
  and journal_import/store.py compute it via the shared
  `BODY_RING_ASSOCIATION_STATUS_CASE_SQL` (see below); importer/import_spansh.py
  and importer/enrich_system_data.py each set it explicitly in Python instead,
  justified by their own local-match guarantee (a rejection-filter and a
  system-scoped body lookup, respectively — see the comment at each call site).

- **BODY\_RING\_ASSOCIATION\_STATUS\_CASE\_SQL lives in
  `shared_contracts/body_ring_association_status.py`**, imported by the three
  asyncpg-based writers above. It used to be defined three times independently
  with no shared module (the exact kind of copy CLAUDE.md warns about
  elsewhere) — already consolidated, so don't reintroduce a fourth copy.

- **The role `edfinder` has `statement\_timeout = 15000` set via ALTER ROLE.**
  It exists nowhere in the repo. Any shell or psql path that does not
  override it is capped at 15 seconds.

- **`psql -c "SET ...; <statement>"` runs both in one transaction.** VACUUM
  and REFRESH MATERIALIZED VIEW CONCURRENTLY cannot run there. Use PGOPTIONS
  or separate -c flags.

- **The Python tests for the ring and body upserts are mocks.** They cannot
  catch malformed SQL — PR #403 shipped a broken cast to production with all
  checks green. Anything touching these statements needs a real Postgres
  integration test.

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

## Delegating to Codex

When you ask me to delegate work to Codex CLI:

1. **Run Codex synchronously:**
   ```bash
   codex exec -C "$PWD" --sandbox workspace-write "<self-contained task>"
   ```

2. **Task requirements:** Include repo context, relevant paths, validation commands, and always end with "do not commit" — Codex will make changes but not git commit.

3. **Wait for completion** — Codex will run in the foreground and report status.

4. **Review the work:**
   ```bash
   git diff
   # Run relevant tests to verify the changes
   ```

5. **Important constraints:**
   - Never edit the same files concurrently with Codex
   - Never ask Codex to delegate work back to Claude
   - For multiple concurrent delegates, use separate Git worktrees

6. **Follow-up in the same session:**
   ```bash
   codex exec resume --last "Address the review issues and rerun the tests."
   ```

**To allow automatic execution** (add to `.claude/settings.local.json`):
```json
{
  "permissions": {
    "allow": [
      "Bash(codex exec *)"
    ]
  }
}
```

**Note:** This launches a separate Codex CLI task. It does not inject a message into this desktop session — Codex runs independently, makes changes to the working tree, and reports results. Review all changes before accepting them.

### SSH MCP setup on Windows
Windows path resolution can trip on case sensitivity; use `claude doctor` to diagnose MCP connectivity issues.

### Model routing (DeepSeek vs Sonnet)

**DeepSeek for:** Running structured diagnostic queries and reporting factually, executing well-specified fixes where the diagnosis is settled, reading files and reporting contents verbatim, applying already-validated patterns to new instances, any task that fits a tight self-contained prompt.

**Sonnet for:** Diagnosis of unknown-cause issues, cross-file reasoning about consequences, code review of DeepSeek's diffs on production-touching code, interpreting ambiguous data, deciding severity or priority when facts alone don't decide, final sanity check before deploying anything.

**Split principle:** DeepSeek gathers, Sonnet reasons.

**Why:** DeepSeek performs well with tight, explicit prompts but will confidently fill gaps with wrong inferences if context is loose. Sonnet is better at diagnosis, tradeoff judgment, and high-stakes review. Tight prompts for DeepSeek require: explicit scope (exact files/tables/commands), required output shape, explicit "do not" list (don't assign severity, don't recommend, don't interpret 0 as cause, don't fix/commit/deploy), verification requirement (every finding must cite source), error reporting (verbatim, no workarounds).

## Frontend deployment

**Deployment sequence (manual, explicit authorization required)**

1. PR merges to `main`
2. Owner checks local preview: `cd frontend && VITE_STAGE26E_PRODUCTION_MAP=enabled yarn dev` — confirm change looks correct
3. Owner explicitly requests production deploy (merge ≠ deploy authorization)
4. Run `scripts/release-main-to-prod.ps1 -SkipPrompt` (delegates to server-side `scripts/deploy_main.sh`)
5. After script succeeds, check `https://ed-finder.app` live and verify change is there

**Critical:** The deploy sequence MUST end with `docker compose restart nginx` — nginx serves static dist via volume mount and requires restart to pick up new build. Without it, the site 404s.

**Checking for deployment drift:**
```powershell
scripts/check-production-drift.ps1
```
Compares live `/api/health` SHA against `origin/main`, prints how many commits production is behind, exits non-zero on drift. Visibility only — never deploys.
