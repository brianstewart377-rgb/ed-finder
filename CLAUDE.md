# ED-Finder Agent Contract

This file defines the current repository rules for automated coding/review agents.

## Authority order

Before making changes, use these sources in order:

1. `docs/operations/infrastructure-status.md` — current production/recovery boundary.
2. `docs/ROADMAP.md` — current programme stage and authorized work.
3. `docs/development/v3-application-stack-decision.md` — locked target stack for new V3 application implementation.
4. this file — engineering and agent constraints.
5. current code/tests on the target branch.

Git history, removed workflows, old artifacts, and superseded design documents are evidence only. They are not current execution authority.

## Current programme

Stage 27 — One Spatial Platform is current. The roadmap controls which slice is authorized. Do not infer authorization from installed dependencies, old branches, previous production state, or unfinished experiments.

The intended spatial direction is a Babylon 9-class workbench. Colony Planner remains the detailed planning/persistence owner; renderer work must not silently mutate plans.

The stack decision selects technology for new V3 application implementation; it does not expand programme authorization. Stage 27A itself remains docs/audit/contracts only and did not authorize a Babylon runtime, a production map change, or any later Stage 27 slice. The later governed PR #601 packet authorizes only the isolated, explicitly non-product Svelte/Babylon executable foundation recorded in the current roadmap; it does not authorize Finder/Inspect implementation, product map design, production wiring, or a renderer cutover.

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

Production is the V3 replacement environment.

- PostgreSQL 18 is the production database generation.
- Production backup/recovery follows the current V3 backup/PITR boundary.
- A retained offsite custom-format dump is a selective migration source only; it is not the operating database.
- Do not copy older PostgreSQL physical data directories into PostgreSQL 18.
- Redis/cache state is disposable and rebuildable.
- NATS/JetStream transport state is not canonical domain truth.
- Production commands must come from current V3 runbooks/workflows that explicitly identify the target and safety boundary.

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

The checked-in backend still uses Python 3.12 and the repository-pinned test dependencies; use that toolchain when validating still-current legacy code. New V3 application implementation targets CPython 3.14 with uv as locked by `docs/development/v3-application-stack-decision.md`. Do not claim the migration has landed before its reviewed slices do.

Backend code lives primarily under `apps/`; migrations live under `sql/`.

Rules:

- keep DB tests on disposable/test databases;
- use parameterized SQL;
- preserve fail-closed validation and bounded inputs;
- bulk database writes must follow `docs/development/bulk-database-write-safety.md`;
- do not perform production DB reads/writes from a coding task unless an explicit current production operation authorizes them.

## Frontend

New V3 application implementation lives solely under `apps/web/` and follows the locked Svelte 5/SvelteKit 2/TypeScript 6, Node 24 and pnpm 11 target in `docs/development/v3-application-stack-decision.md`. The checked-in React tree under `frontend/` is temporary source evidence only, not a runnable destination or parallel validation lane. The hard-cut branch must remain unmerged until replacement parity is complete. Cypress is the only active browser automation framework; historical Playwright receipts remain provenance only.

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

The required `Review Lab` GitHub Actions workflow exercises the browser review journey on pull requests.

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
