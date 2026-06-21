# Local Review Test Environment

## Purpose

This workflow hardens the isolated local review stack for the real
application-backed review journey:

- Finder
- System Detail
- Colony Planner

It exists to validate review-environment readiness for draft PR `#260` without
changing PR `#259`, without using public endpoints, and without touching any
developer database, Stage 19 path, source acquisition, canonical apply,
rebaseline, or scheduler work.

## Safety Boundary

The review environment is isolated, disposable, and fail-closed.

- It does not reuse `ed-postgres`.
- It starts only the review-only services `review-postgres`, `review-redis`,
  and `review-api`.
- It uses only the dedicated review database `edfinder_local_review`.
- It binds the review API only to `127.0.0.1:8001`.
- It does not publish host ports for Postgres or Redis.
- It never reads a developer `.env` file and never uses `env_file`.
- It never accepts passwords, DSNs, tokens, or secret file paths as CLI
  arguments.
- It does not use any public endpoint.
- It does not start Stage 19, source acquisition, canonical apply, rebaseline,
  scheduler, or background ingestion work.
- Synthetic review data is reachable only inside the isolated review stack.
- Normal API runtime cannot serve synthetic review fixtures.

## Commands

Run commands from the repository root with the project virtualenv:

```bash
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py preflight
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py verify --confirm-local-review-environment
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py down --confirm-local-review-environment
```

Use exactly these commands:

- `preflight` is read-only. It validates containment, review-only routing,
  support-route matrix coverage, and Compose safety before Docker startup.
- `verify --confirm-local-review-environment` is the normal one-command
  readiness check. It runs static validation, captures the Docker baseline,
  starts the isolated stack, checks API contracts, runs the real browser flow,
  records product observations, and always tears the review stack down again.
- `down --confirm-local-review-environment` is the explicit cleanup command if
  you need to stop the isolated stack outside `verify`.

## What Verify Proves

`verify --confirm-local-review-environment` proves that the isolated review
stack is ready for the real review journey against the real frontend and the
loopback review API on `127.0.0.1:8001`.

It validates all of the following:

- Finder returns `Review Alpha`, `Review Beta`, `Review Gamma`, and
  `Review Delta`.
- System Detail loads the synthetic review systems.
- Colony Planner loads using the real planner support routes
  `/api/facility-templates`,
  `/api/systems/{id64}/simulation-summary`, and
  `/api/systems/{id64}/slot-predictions`.
- Review-only support routes prevent avoidable browser noise for
  `/api/events/recent`, `/api/watchlist`, and `/api/cache/stats`.
- Review Alpha dedicated evidence succeeds.
- Review Beta preserves the unavailable posture.
- Review Gamma preserves the unknown posture.
- Review Delta deliberately returns a dedicated-evidence `503`, then triggers
  the existing provenance fallback path.
- The Delta sequence is only accepted when the browser shows:
  dedicated evidence `503` -> provenance fallback request -> provenance
  fallback `200` -> visible fallback posture.
- The fallback remains report-only, non-canonical, and honest about
  provenance/fallback state.
- No unexpected browser console error, uncaught exception, unexpected API
  4xx/5xx response, or app-wide recovery screen appears.
- The review stack tears down safely and the Docker baseline is restored.

## What Verify Does Not Prove

`verify` is review-environment reliability work only.

- It does not mark PR `#260` ready.
- It does not merge PR `#260`.
- It does not prove full product acceptance for PR `#259`.
- It does not authorize Stage 19, production database work, source
  acquisition, canonical apply, rebaseline, or scheduler work.
- It does not make normal runtime capable of serving review fixtures.

## Synthetic Review Corpus

The seeded review database is deterministic, synthetic, and review-only.

- `Review Alpha` exercises available evidence while keeping canonical planner
  data as the planner truth source.
- `Review Beta` exercises unavailable selected-system evidence.
- `Review Gamma` exercises unknown selected-system evidence.
- `Review Delta` exercises the deliberate dedicated-evidence `503` and the
  provenance fallback path.

Review Delta is special by design:

- The dedicated warehouse-evidence request must fail with `503`.
- That `503` is acceptable only when the browser immediately follows it with a
  successful provenance fallback request and renders the honest fallback state.
- The UI must not claim dedicated warehouse evidence is available.
- The fallback remains report-only and non-canonical.

## Product Observations

`verify` separates environment failures from product observations.

- A broken stack, missing route, unexpected API error, unexpected browser
  console error, or failed teardown is an environment failure.
- A known narrow viewport planner overflow remains a product observation owned
  by PR `#259`.

The current known product observation is recorded as:

- classification: `PRODUCT_NARROW_VIEWPORT_OVERFLOW`
- owner: PR `#259`
- environment ready: `true`
- product acceptance ready: `false`

This means the isolated review stack can be ready even while PR `#259`
continues to own the narrow viewport acceptance issue.

## Review Runtime

The review API entrypoint is `apps/api/src/review_main.py`.

- It is not imported by normal `apps/api/src/main.py`.
- It fails closed unless the review stack marker is `edfinder-review`.
- It fails closed unless the database target is exactly `review-postgres` /
  `edfinder_local_review`.
- It serves the real Finder, System Detail, and Colony Planner routes with the
  normal database-backed application code.
- It serves review-only planner evidence and provenance contracts from review
  data stored in the dedicated review database.

## Cleanup

When manual cleanup is needed, run:

```bash
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py down --confirm-local-review-environment
```

This removes only the `edfinder-review` stack resources created by the local
review workflow.
