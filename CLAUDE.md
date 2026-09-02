# ED-Finder Agent Contract

This file defines the current repository rules for automated coding/review agents.

## Authority order

Before making changes, use these sources in order:

1. `docs/operations/infrastructure-status.md` — current production/recovery boundary.
2. `docs/ROADMAP.md` — current programme stage and authorized work.
3. this file — engineering and agent constraints.
4. current code/tests on the target branch.

Git history, removed workflows, old artifacts, and superseded design documents are evidence only. They are not current execution authority.

## Current programme

Stage 27 — One Spatial Platform is current. The roadmap controls which slice is authorized. Do not infer authorization from installed dependencies, old branches, previous production state, or unfinished experiments.

The intended spatial direction is a Babylon 9-class workbench. Colony Planner remains the detailed planning/persistence owner; renderer work must not silently mutate plans.

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

Use Python 3.12 and the repository-pinned test dependencies.

Backend code lives primarily under `apps/`; migrations live under `sql/`.

Rules:

- keep DB tests on disposable/test databases;
- use parameterized SQL;
- preserve fail-closed validation and bounded inputs;
- bulk database writes must follow `docs/development/bulk-database-write-safety.md`;
- do not perform production DB reads/writes from a coding task unless an explicit current production operation authorizes them.

## Frontend

The frontend is under `frontend/` and uses React, TypeScript and Vite.

- package manager: Yarn 1.22.22;
- `yarn.lock` is committed and authoritative;
- API access should use the existing domain-scoped client modules under `frontend/src/lib/api/`;
- do not introduce a flat `frontend/src/lib/api.ts` that shadows the API barrel;
- preserve typed API contracts and regenerate/check OpenAPI types when backend response shapes change.

Typical checks:

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

When instructions conflict, prefer the current infrastructure status, current roadmap, current branch code/tests, and fail-closed safety. If a requested action depends on a procedure that no longer exists in the current tree, stop rather than recreating it from history.
