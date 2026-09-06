# ED-Finder Agent Contract

This file defines the current repository rules for automated coding/review agents.

## Authority order

Start at `README.md`, then use this small current authority chain:

1. `docs/ROADMAP.md` — current programme order and decision gates.
2. `docs/development/v3-application-stack-decision.md` — V3 technology and application ownership.
3. `docs/colonisation-redesign/spatial-platform-product-contract.md` — product and spatial feature contract.
4. `docs/colonisation-redesign/spatial-platform-architecture-decision.md` — renderer-neutral architecture and ownership.
5. `docs/development/v3-browser-validation-lanes.md` — browser acceptance lanes.
6. `docs/operations/infrastructure-status.md` — current production/recovery boundary.
7. this file — engineering and agent constraints, followed by current code/tests on the target branch.

Git history, removed workflows, old artifacts, and superseded design documents are evidence only. They are not current execution authority.

## Current programme

The V3 application and One Spatial Platform programme is current. PR #601 is
the single active application integration lane; at its currently known head it
contains an Explore/Finder → fresh Babylon results → canonical Inspect slice.
Because that work is an active PR, do not claim it has merged into `main`
before repository state proves it.

`apps/web/` is the sole target for new browser application work. Svelte/SvelteKit
owns the application, domain orchestration, routes, panels, and accessible DOM;
Babylon owns spatial/GPU presentation only. The React/R3F/Three implementation
is historical migration and behaviour evidence, not the V3 target or current
production authority. Preserve the historical fact that R3F won Stage 26.

The roadmap controls execution order and unresolved decision gates. Do not
infer authorization from installed dependencies, old stage labels, previous
production state, unfinished experiments, or audit documents.

### Named runtime exception: EDDN simulation ingest

The EDDN simulation ingest background task (`apps/api/src/ingest/eddn_client.py`, controlled by `EDDN_SIMULATION_INGEST_ENABLED` and defaulting on) is a deliberate named exception to the deferred journal-import automation boundary. It consumes the live public EDDN feed and is not authorization for a general journal-import scheduler, service, timer, or **journal-import canonical promotion**. Preserve that distinction when changing ingest or automation behaviour.

## Repository state

`main` is protected. Normal changes go through a branch and pull request.

Before implementation:

- fetch the current target branch;
- run the repository state resolver/preflight when the touched workflow requires it;
- avoid working from a divergent or stale local `main`;
- keep unrelated dirty files out of the change;
- never force-push protected/control-plane branches.

## Current infrastructure boundary

Production is `ed-finder-prod` at `nb79a3d.mevnode.com` on the V3 replacement
environment. Hetzner/V2 is decommissioned.

- PostgreSQL 18 is the production database generation.
- Production backup/recovery follows the current V3 backup/PITR boundary.
- A retained offsite custom-format dump is a selective migration source only; it is not the operating database.
- Do not copy older PostgreSQL physical data directories into PostgreSQL 18.
- Redis/cache state is disposable and rebuildable.
- NATS/JetStream transport state is not canonical domain truth.
- Production commands must come from current V3 runbooks/workflows that explicitly identify the target and safety boundary.
- Contabo hosts exactly three self-hosted Codex runners. It is not production
  and is not automatically a live-checkpoint destination; that destination is
  a deployment decision with explicit capacity and isolation limits.
- Ollama was experimental Octopus residue and has been removed from production;
  do not restore or document it as architecture.

Do not invent or adapt a production procedure from Git history.

## Current operator control plane

The current GitHub-hosted replacement-host operator workflow is:

- `.github/workflows/chatgpt-ed-new-ops.yml`

It uses the `ED_NEW_OPERATOR_*` credential boundary and pinned known-host trust. Do not weaken host verification, use runtime `ssh-keyscan`, expose credentials, or broaden allowlisted operations casually.

Current operator helpers include:

- `scripts/operator/actions/octopus-edge-status.sh`
- `scripts/operator/actions/octopus-qdrant-healthcheck-repair.sh`
- `scripts/operator/recover_v3_runtime_contract.py`

Other scripts under `scripts/operator/` are repository tooling unless a current V3 runbook explicitly promotes them to production authority.

## Codex bridge and repository writes

Codex review is a reviewer path. Repository writes must preserve the repo's trust separation:

- validate the exact target branch/SHA before implementation;
- run Codex without a push credential;
- seal/verify the result before a trusted writer receives credentials;
- use compare-and-swap/lease semantics for existing branch updates;
- ensure updates to an existing PR trigger fresh CI and review;
- do not let task text control branch routing or expected remote SHAs.

Never expose repository write credentials to the Codex execution environment.

## Python/backend

Every active Python execution, configuration, developer, and runtime surface
uses CPython 3.14. The deployable V3 API and its validation lanes additionally
use uv 0.11.33 and the frozen `apps/api/pyproject.toml` + `apps/api/uv.lock`
graph. Repository orchestration, static contracts, importer/canonical tooling,
container images, and the Codex worker bootstrap must not introduce an older
Python fallback. This version unification does not make retained importer
PostgreSQL-driver debt part of the V3 API runtime graph.

Backend code lives primarily under `apps/`; migrations live under `sql/`.

Rules:

- keep DB tests on disposable/test databases;
- use parameterized SQL;
- preserve fail-closed validation and bounded inputs;
- bulk database writes must follow `docs/development/bulk-database-write-safety.md`;
- do not perform production DB reads/writes from a coding task unless an explicit current production operation authorizes them.

## Frontend

New V3 application implementation lives under `apps/web/` and follows the locked Svelte 5/SvelteKit 2/TypeScript 6, Node 24 and pnpm 11 target in `docs/development/v3-application-stack-decision.md`. The checked-in frontend under `frontend/` still uses React, TypeScript and Vite; it remains migration/reference evidence with protected validation until deliberately retired after equivalent coverage exists.

PR #601's known active head includes Finder, fresh Babylon results, and
canonical Inspect integration. Treat that as active-PR state until merged, and
keep new implementation in `apps/web/`.

The `apps/web/` static SPA owns application/static routes. FastAPI retains `/api/*`, exact `/openapi.json`, and numeric `/s/{id64}`; do not add a frontend route or backend catch-all that blurs that boundary.

- package manager: Yarn 1.22.22;
- `yarn.lock` is committed and authoritative;
- API access should use the existing domain-scoped client modules under `frontend/src/lib/api/`;
- do not introduce a flat `frontend/src/lib/api.ts` that shadows the API barrel;
- preserve typed API contracts and regenerate/check OpenAPI types when backend response shapes change.

Use these legacy-toolchain commands only to validate the still-current checked-in frontend:

```bash
cd frontend
yarn install --frozen-lockfile
yarn typecheck
yarn test
yarn build
```

Run focused map/planner/operator/E2E checks when those surfaces are touched.

## Local review/testing

`docker-compose.review.yml` is the disposable local Review Lab data/service contract. It is not production and must remain isolated from production credentials, URLs and data.

Product E2E/Visual Acceptance and Review Lab are separate browser lanes. Both
V3 map lanes exercise `apps/web/` with Babylon; Review Lab may use a different
synthetic dataset and isolated environment. The required `Review Lab` GitHub
Actions workflow exercises the review journey on pull requests.

## CI and acceptance

Every pull request must satisfy the canonical [Pull Request Acceptance Policy](docs/development/pull-request-acceptance-policy.md) before merge. Acceptance is fail-closed and must apply to the **exact latest PR head SHA**.

Both Codex Review (`chatgpt-codex-connector`) and Octopus Review must satisfy that policy for the exact latest PR head SHA. **Green CI alone is insufficient**: every substantive reviewer finding must have an explicit recorded disposition and no substantive unresolved thread may remain before merge.

Required checks are defined by branch protection and current workflows. Do not weaken tests just to make a PR green.

At minimum, preserve the protected backend, integration, migration/script, canonical safety, frontend, E2E, image-parity, Review Lab and security gates that apply to the change.

If a docs/config change invalidates a contract test because the contract itself intentionally changed, update the test to assert the new contract rather than restoring stale text.

## Visual changes

Any change affecting rendering, layout, maps, CSS, components, opacity, colour, sizing, or other user-visible output requires visual validation before production promotion.

Preserve accessibility, browser coverage, bounded-data, memory/performance and visual evidence requirements defined by the current stage/feature contract.

## Secrets and sensitive material

Never commit or print:

- passwords;
- DSNs containing credentials;
- API tokens;
- OAuth client secrets;
- SSH/private keys;
- recovery codes;
- credential-bearing URLs;
- private production environment files.

Use scoped secrets and existing current credential paths. Keep secrets off command-line arguments and logs wherever practical.

## Final rule

When instructions conflict, prefer the current infrastructure status, current roadmap authorization, the V3 application stack decision for new implementation, current branch code/tests, and fail-closed safety. If a requested action depends on a procedure that no longer exists in the current tree, stop rather than recreating it from history.
