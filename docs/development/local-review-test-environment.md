# Local Review Test Environment

## Purpose

The Review Lab turns draft PR `#260` into a reusable, deterministic proving
ground for the real review journey:

- Finder
- System Detail
- Colony Planner

It is DevEx and test infrastructure only. It does not change PR `#259`, does
not make either PR ready to merge, and does not authorize Stage 19, source
acquisition, canonical apply, rebaseline, scheduler, or production database
work.

## Review Lab Architecture

`scripts/dev/review_environment.py` is a thin CLI over the Review Lab modules in
`scripts/dev/review_lab/`.

- `contract.py` defines fixed constants, dataclasses, and run metadata.
- `scenarios.py` owns the finite scenario registry and deterministic ordering.
- `support_matrix.py` owns the review-only support-route matrix.
- `lifecycle.py` owns static checks, stack lifecycle, and Docker baseline
  capture/restore.
- `api_contracts.py` validates real route contracts against the isolated review
  API.
- `browser_runner.py` runs the real frontend build, preview, and Playwright
  collector.
- `network_policy.py` classifies allowed versus unexpected browser/API noise.
- `observations.py` separates environment readiness from product observations.
- `process_registry.py` tracks only review-owned preview/browser child
  processes.
- `reporting.py` writes sanitised results beneath
  `/tmp/edfinder-local-review/<run-id>/`.
- `timeouts.py` centralises finite phase timeouts.

The Review Lab never loads arbitrary scenarios, shell fragments, endpoints,
credentials, or `.env` files.

## GitHub Actions

Review Lab CI is separate from the normal frontend E2E lane for the canonical `frontend/` app.

- Normal frontend E2E continues to test normal application behaviour only.
- `frontend/e2e/review-environment.spec.js` intentionally skips outside
  Review Lab execution.
- The dedicated GitHub Actions workflow is `Review Lab` in
  `.github/workflows/review-lab.yml`.
- It is manually triggerable via `workflow_dispatch`.
- Its `pull_request` trigger is path-filtered to Review Lab-relevant files so
  unrelated feature changes do not pay for the expensive isolated browser lane.
- It uses least-privilege `contents: read` permissions and cancels stale runs on
  the same branch.
- The workflow authority remains the wrapper command:

```bash
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B \
  scripts/dev/review_environment.py verify \
  --mode full \
  --scenario all \
  --confirm-local-review-environment
```

- The dedicated Review Lab lane does not call normal `yarn e2e` as a substitute
  for isolated review validation.
- The Review Lab browser collector receives
  `EDFINDER_REVIEW_OUTPUT_PATH` and `EDFINDER_REVIEW_SCENARIOS_JSON` only from
  the wrapper. Partial Review Lab configuration fails closed.

## Safety Boundary

The review environment is isolated, disposable, and fail-closed.

- It does not reuse `ed-postgres`.
- It starts only `review-postgres`, `review-redis`, and `review-api`.
- It uses only the dedicated review database `edfinder_local_review`.
- It binds the review API only to `127.0.0.1:8001`.
- It does not publish host ports for Postgres or Redis.
- It never reads a developer `.env` file and never uses `env_file`.
- It never accepts passwords, DSNs, tokens, secret paths, or arbitrary shell
  text as CLI input.
- It does not use public endpoints or external data.
- It does not start Stage 19, source acquisition, canonical apply, rebaseline,
  scheduler, or background ingestion work.
- Synthetic review data is reachable only inside the isolated review stack.
- Normal API runtime cannot serve synthetic review fixtures or review-only
  routes.

## Commands

Run commands from the repository root with the project virtualenv:

```bash
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py preflight
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py list-scenarios
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py verify --mode quick --scenario planner_core --confirm-local-review-environment
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py verify --mode full --scenario all --confirm-local-review-environment
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py report --latest
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py down --confirm-local-review-environment
```

- `preflight` is read-only and validates containment, review-only routing,
  support-route matrix coverage, scenario registry validity, and Compose safety
  before Docker startup.
- `list-scenarios` is read-only and prints the finite scenario registry. Future
  coverage should add a declarative scenario or contract, not one-off browser
  logic.
- `verify` defaults to `--mode full`. `--scenario all` runs the registry in
  deterministic order.
- `verify --mode quick --scenario planner_core --confirm-local-review-environment`
  is the fast stack and contract smoke path.
- `verify --mode full --scenario all --confirm-local-review-environment` is the
  complete proving run.
- `report --latest` is read-only and prints the latest sanitised JSON report.
- `down --confirm-local-review-environment` removes only the isolated
  `edfinder-review` stack resources.

The dedicated `Review Lab` GitHub Actions workflow runs the same full-mode
wrapper command against synthetic review data only.

## Scenario Registry

The Review Lab uses a validated finite registry with no arbitrary scenario
execution. Each scenario declares:

- name
- purpose
- synthetic data profile
- required review-only routes
- API contracts
- browser journey
- expected network and console policy
- evidence and provenance posture
- accessibility and viewport checks
- product-observation policy and owner

The initial deterministic registry is:

- `planner_core`
- `evidence_available`
- `evidence_unavailable`
- `evidence_unknown`
- `evidence_not_evaluated`
- `provenance_fallback`
- `empty_optional_support_data`
- `large_result_set`
- `partial_optional_data`
- `support_route_compatibility`

Only synthetic `Review Alpha`, `Review Beta`, `Review Gamma`, and `Review Delta`
data are valid. `Review Delta` remains the deliberate fallback-only case.

## Quick And Full

Every verify run writes a sanitised result beneath
`/tmp/edfinder-local-review/<run-id>/`.

The exact phase groups are:

- `static`
- `stack`
- `api_contracts`
- `browser_desktop`
- `browser_accessibility`
- `browser_console`
- `teardown`
- `product_observations`

Each phase records:

- `status`
- `duration_ms`
- `summary`
- `failure_code`
- `safe_diagnostics`

quick mode runs:

- `static`
- `stack`
- `api_contracts`
- `teardown`

quick mode skips browser, accessibility, console, and product observation
phases by design.

full mode adds:

- frontend build
- preview readiness
- Playwright/browser verification
- accessibility checks
- network and console policy enforcement
- product observations

Dependent phases become skipped after an upstream failure, teardown still runs,
the final JSON report still writes, and the CLI exits non-zero.

## Timeouts And Cleanup

All operations are bounded:

- static: `60s`
- stack readiness: `60s`
- API contracts: `30s`
- frontend build: `90s`
- preview readiness: `30s`
- Playwright: `120s`
- teardown: `60s`

The process registry records only processes started by the current verify run.
It stores only review-owned PID and process-group data in the run directory,
stops only review-owned preview/browser children, and never kills arbitrary host
Node, Vite, Docker, database, or browser processes.

Verify always:

- captures a Docker baseline before startup
- tears the review stack down in `finally`
- compares the non-review Docker baseline after teardown
- fails closed if review-owned resources already exist before verify
- fails with `DOCKER_BASELINE_NOT_RESTORED` if the non-review baseline changes
- fails with `REVIEW_RESOURCES_NOT_REMOVED` if any review-owned container or
  volume remains after teardown

## What Verify Proves

The Review Lab proves isolated review-environment readiness for the real
frontend and the loopback review API on `127.0.0.1:8001`.

It validates all of the following:

- Finder returns `Review Alpha`, `Review Beta`, `Review Gamma`, and
  `Review Delta`.
- System Detail loads the synthetic review systems.
- Colony Planner loads using the real support routes
  `/api/facility-templates`,
  `/api/systems/{id64}/simulation-summary`, and
  `/api/systems/{id64}/slot-predictions`.
- Required review-only support routes return contract-shaped responses instead
  of avoidable 404 or 5xx noise.
- Optional noisy routes may return safe empty or zeroed review responses.
- Review Alpha preserves available evidence without claiming canonical truth.
- Review Beta preserves unavailable evidence.
- Review Gamma preserves unknown evidence.
- Review Delta deliberately returns a dedicated-evidence `503`, then triggers
  the provenance fallback path.
- The Delta sequence is accepted only when the browser shows:
  dedicated evidence `503` -> provenance fallback request -> provenance
  fallback `200` -> visible fallback posture.
- Any uncoupled Delta `503` fails verification.
- No unexpected browser console error, uncaught exception, reviewed-flow 404,
  unexpected API 4xx/5xx response, or app-wide recovery screen appears.
- The review stack tears down safely and the Docker baseline is restored.

## Delta Rule

`Review Delta` is review-only and must never leak into normal runtime.

- The dedicated warehouse-evidence request must fail with `503`.
- That `503` is valid only when it correlates to a successful provenance
  fallback request and a visible fallback disclosure.
- The UI must not claim dedicated evidence is available.
- The fallback remains report-only, non-canonical, and explicit about technical
  provenance details.
- An uncoupled `503` fails with `DELTA_FALLBACK_NOT_TRIGGERED` or
  `DELTA_FALLBACK_PROVENANCE_FAILED`.

## Support-Route Matrix

The Review Lab test-enforces a support-route matrix with route, frontend caller,
required status, review-only handling, allowed response characteristics,
scenario coverage, and explicit validation mode.

At minimum it covers:

- `/api/events/live`
- `/api/events/recent`
- `/api/watchlist`
- `/api/cache/stats`
- `/api/facility-templates`
- `/api/systems/{id64}/simulation-summary`
- `/api/systems/{id64}/slot-predictions`

Rules:

- Normal runtime never mounts review-only routes.
- Every route must be classified as `api_contract_validated`,
  `browser_only_validated`, or `intentionally_not_exercised`.
- `/api/events/live` is validated through a bounded loopback SSE handshake that
  asserts `200` plus `text/event-stream` without consuming an unbounded stream.
- Required routes must return contract-shaped review responses.
- Optional noisy routes may return safe empty or zeroed responses.
- No fake operational or source claims are allowed.
- Unexpected reviewed-flow 404 or 5xx responses fail verification.

## Product Observations

The Review Lab separates environment readiness from product acceptance.

- Broken stack startup, missing routes, malformed contracts, unexpected browser
  console errors, unexpected network errors, or failed teardown are environment
  failures.
- Product observations are reported separately and do not hide environment
  readiness.

The known allowlisted product observation is:

- classification: `PRODUCT_NARROW_VIEWPORT_OVERFLOW`
- owner: `PR #259`
- environment ready: `true`
- product acceptance ready: `false`

This observation remains owned by PR `#259`. It should be detected and reported,
not hidden, and it does not make PR `#260` or PR `#259` ready for merge.

That classification also applies in Review Lab CI: PR `#259`'s narrow viewport
overflow remains a product finding and does not fail the isolated environment
lane when the Review Lab itself behaves correctly.

Any new or different product issue fails as
`UNEXPECTED_PRODUCT_OBSERVATION`.

## Review Runtime

The review API entrypoint is `apps/api/src/review_main.py`.

- It is not imported by normal `apps/api/src/main.py`.
- It fails closed unless the review stack marker is exactly
  `edfinder-review`.
- It fails closed unless the database target is exactly
  `review-postgres` / `edfinder_local_review`.
- It serves the real Finder, System Detail, and Colony Planner routes with the
  normal database-backed application code.
- It serves review-only planner evidence, provenance contracts, and support
  routes from the isolated review database.

## Temporary Artifacts

Review Lab artifacts are temporary and sanitised.

- Reports, logs, screenshots, traces, and process-registry data live only under
  `/tmp/edfinder-local-review/<run-id>/`.
- Never commit artifacts, logs, screenshots, traces, or browser dumps.
- Safe diagnostics must not include credentials, DSNs, tokens, passwords,
  secret paths, private local paths, or unredacted stack traces.

GitHub Actions uploads failure-only, sanitised Review Lab artifacts:

- final JSON report and latest-report pointer
- sanitised browser summary
- isolated Playwright test results from synthetic review scenarios only

It does not upload `.env` files, Docker inspect output, container environment
data, DSNs, tokens, passwords, database dumps, operator artifacts, or raw logs
that could carry credentials.

The Actions job summary records only safe high-level facts such as full verify
pass/fail state, duration, Delta fallback correlation, unexpected console/API
error summary, Docker baseline restoration, and review-owned resource absence.

