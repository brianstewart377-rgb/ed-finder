# Local Review Test Environment

## Purpose

Review Lab is the isolated deterministic browser lane for synthetic V3 edge
cases. It runs the real `apps/web` Svelte frontend and Babylon renderer against
the disposable `review_main.py` API and synthetic Review Lab database. It is
separate from normal Product E2E and does not own product visual baselines.

It never authorizes deployment, production access, canonical database changes,
external data acquisition, scheduling, or background ingest.

## Architecture

`scripts/dev/review_environment.py` is a thin CLI over
`scripts/dev/review_lab/`:

- `contract.py` pins paths, ports, resource names, and the apps/web collector.
- `scenarios.py` defines the finite synthetic V3 scenario registry.
- `support_matrix.py` records only routes used by Explore and Inspect.
- `lifecycle.py` owns containment, Docker lifecycle, and baseline restoration.
- `api_contracts.py` checks the isolated health, autocomplete, search, and
  detail contracts.
- `browser_runner.py` builds and previews `apps/web`, then invokes only
  `cypress/e2e/review-lab.cy.ts` with `cypress.review.config.ts`.
- `network_policy.py` allows only explicitly tagged synthetic failures.
- `process_registry.py` owns and tears down the preview process group.
- `reporting.py` writes sanitised evidence below
  `/tmp/edfinder-local-review/<run-id>/`.

The retained `frontend/` React/R3F tree is not part of Review Lab. Its old
Review Lab collector and Planner viewport expectations have been removed.

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

## Commands

From the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py preflight
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py list-scenarios
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py verify --mode quick --scenario explore_inspect --confirm-local-review-environment
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py verify --mode full --scenario all --confirm-local-review-environment
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py report --latest
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py down --confirm-local-review-environment
```

`preflight`, `list-scenarios`, and `report` are read-only. Stack mutations
require the exact confirmation flag. Quick mode runs Review Lab contract, stack,
API, and teardown phases. Full mode adds the apps/web browser collector.

## Synthetic Scenarios

The finite registry is:

- `explore_inspect`: synthetic system discovery, keyboard typeahead, Babylon
  readiness, exact ID64 selection, and canonical Inspect detail.
- `api_failure`: two bounded 503 responses cover the query retry contract and
  prove the Explore error state without changing the backend.
- `empty_results`: a contract-shaped empty response proves the empty UI and
  zero-target Babylon scene.
- `renderer_recovery`: uses `WEBGL_lose_context` when the active Babylon backend
  exposes it; otherwise records the renderer-neutral resize lifecycle fallback.
- `navigation_containment`: direct Inspect and return navigation, heading focus,
  and absence of external resource origins.

These are diagnostic synthetic states. Review Lab does not invoke the normal
Product E2E command or `product-journey.cy.ts`, and normal Product E2E does not
invoke this wrapper, `review_main.py`, Review Lab markers, or synthetic data.

## Lifecycle and Teardown

Every operation has a finite timeout. Verify always captures the pre-run Docker
container, volume, and network baseline; stops its owned preview process group;
runs `docker compose down -v --remove-orphans`; compares the non-review baseline;
and then asserts no labelled or named Review Lab container, volume, or network
remains. A mismatch fails closed.

The required GitHub workflow installs Node 24 and pinned pnpm 11, installs
`apps/web` from its frozen lockfile, runs only focused Review Lab
containment/lifecycle tests, and invokes the same full wrapper command. Generic
lint, formatting, project-state, stage, security, and product checks remain in
normal CI.

## Diagnostics

Reports and browser summaries contain bounded status, scenario, route, phase,
and teardown facts. Cypress screenshots/videos are failure-only diagnostic
artifacts under `apps/web/cypress/artifacts/review-lab`; they are not approved
product visual baselines. Credentials, DSNs, tokens, Docker inspect output,
database dumps, raw environment data, and production identifiers must never be
written or uploaded.
