# Local Review Test Environment

## Purpose

Review Lab is an isolated deterministic proving environment for V3 states that
normal Product E2E cannot reliably create. It runs the real `apps/web` Svelte
frontend and Babylon renderer against the disposable `review_main.py` API and
synthetic Review Lab database.

Review Lab is **not** a second Product E2E suite. Normal user journeys,
accessibility acceptance, interaction regression, and approved visual baselines
belong to V3 Product E2E / Visual Acceptance. Cypress is used here only as a
controlled browser driver and evidence collector.

It never authorizes deployment, production access, canonical database changes,
external data acquisition, scheduling, or background ingest.

## Architecture

`scripts/dev/review_environment.py` is a thin CLI over
`scripts/dev/review_lab/`:

- `contract.py` pins paths, ports, resource names, phases, and the apps/web collector.
- `scenarios.py` defines the finite Review Lab-only synthetic scenario registry.
- `support_matrix.py` records only routes required to create or observe those states.
- `lifecycle.py` owns containment, Docker lifecycle, and baseline restoration.
- `api_contracts.py` checks the isolated health, Finder fixture, and review-control contracts.
- `browser_runner.py` builds and previews `apps/web`, then invokes only
  `cypress/e2e/review-lab.cy.ts` with `cypress.review.config.ts`.
- `network_policy.py` rejects unexpected API errors, console/page errors, and external origins.
- `process_registry.py` owns and tears down the preview process group.
- `reporting.py` writes sanitised evidence below `/tmp/edfinder-local-review/<run-id>/`.

The retained `frontend/` React/R3F tree is not part of Review Lab.

## Hard ownership boundary

Product E2E owns normal Explore -> Inspect journeys, keyboard/mouse behaviour,
normal accessibility, ordinary resize/remount behaviour, and approved
screenshots/visual baselines.

Review Lab owns only:

- synthetic fixture wiring proof;
- backend-induced failure and edge states;
- renderer fault/recovery conditions that normal product data cannot guarantee;
- same-origin/network containment;
- disposable database/container/process lifecycle and teardown;
- diagnostic screenshots/videos on failure.

The Review Lab Cypress collector must not stub product API responses to create
its scenarios. Failure/empty modes are selected through the review-only
`/api/review/scenario/{mode}` control route and implemented inside guarded
`review_main.py`. Normal `main.py` never exposes this control surface.

Review Lab reports whether its **environment and synthetic scenarios** are
ready. It does not report product-acceptance readiness.

## Safety Boundary

The Compose project name is `edfinder-review`. It starts only
`review-postgres`, `review-redis`, and `review-api`, uses database
`edfinder_local_review`, and binds only the API to `127.0.0.1:8001`. Postgres
and Redis expose no host ports. The stack reads no `.env` file and uses no
external network or volume.

`review_main.py` fails closed unless the marker, database host/name, and Redis
host exactly match the Review Lab contract. Normal `main.py` does not import
the review entrypoint or synthetic fixtures.

The Cypress collector also fails closed. Its marker, summary path, and scenario
plan are captured by a Node-side task rather than `Cypress.env`. Summary writes
must match the wrapper-selected absolute path and remain beneath
`/tmp/edfinder-local-review`.

The preview is explicitly bound to `127.0.0.1:4173`; readiness probes target the
same loopback endpoint.

## Commands

From the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py preflight
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py list-scenarios
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py verify --mode quick --scenario synthetic_wiring --confirm-local-review-environment
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py verify --mode full --scenario all --confirm-local-review-environment
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py report --latest
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py down --confirm-local-review-environment
```

`preflight`, `list-scenarios`, and `report` are read-only. Stack mutations
require the exact confirmation flag. Quick mode runs Review Lab contract, stack,
API, and teardown phases. Full mode adds only the Review Lab synthetic browser
collector and browser containment diagnostics.

## Synthetic Scenarios

The finite registry is:

- `synthetic_wiring`: minimally proves the disposable Review systems reach the
  real `apps/web` + Babylon runtime. It does not select, inspect, perform a11y
  acceptance, or establish visual baselines.
- `api_failure`: the guarded Review API returns explicitly tagged 503 search
  responses so the real frontend's bounded error state can be observed.
- `empty_results`: the guarded Review API returns a contract-shaped empty search
  response so the real frontend and Babylon zero-target scene can be observed.
- `renderer_recovery`: injects renderer lifecycle stress/fault behaviour and
  records recovery diagnostics.

These are diagnostic synthetic states. Review Lab does not invoke the normal
Product E2E command or `product-journey.cy.ts`, and normal Product E2E does not
invoke this wrapper, `review_main.py`, Review Lab markers, control routes, or
synthetic data.

## Lifecycle and Teardown

Every operation has a finite timeout. Verify always captures the pre-run Docker
container, volume, and network baseline; stops its owned preview process group;
runs `docker compose down -v --remove-orphans`; compares the non-review baseline;
and then asserts no labelled or named Review Lab container, volume, or network
remains. A mismatch fails closed.

The required GitHub workflow installs Node 24 and pinned pnpm 11, installs
`apps/web` from its frozen lockfile, runs only focused Review Lab
containment/lifecycle tests, and invokes the same full wrapper command. Generic
lint, formatting, project-state, security, product E2E, and visual-acceptance
checks remain outside Review Lab.

## Diagnostics

Reports and browser summaries contain bounded status, scenario, route, phase,
network/console, and teardown facts. Cypress screenshots/videos are failure-only
diagnostic artifacts under `apps/web/cypress/artifacts/review-lab`; they are not
approved product visual baselines. Credentials, DSNs, tokens, Docker inspect
output, database dumps, raw environment data, and production identifiers must
never be written or uploaded.
