# Local Review Test Environment

## Purpose

This workflow prepares a self-contained disposable local review stack for the
real application-backed browser journey:

- Finder
- System Detail
- Colony Planner

It exists to unblock manual acceptance review for draft PR `#259` without
changing that PR, without using public endpoints, and without touching any
existing developer, Stage 19, warehouse, staging, canonical, or disposable
database.

## Safety Boundary

The review environment is fail-closed and isolated.

- It does not reuse `ed-postgres`.
- It starts a dedicated Compose project named `edfinder-review`.
- It creates only the review-only services `review-postgres`, `review-redis`,
  and `review-api`.
- It uses only the dedicated review database `edfinder_local_review`.
- It uses uniquely named review-only volumes and removes only those volumes on
  shutdown.
- It publishes only the API on `127.0.0.1:8001`.
- It does not publish host ports for Postgres or Redis.
- It never reads a developer `.env` file and never uses `env_file`.
- It never accepts passwords, DSNs, tokens, or secret file paths as CLI
  arguments.
- It does not use any public endpoint.
- It does not start Stage 19, source acquisition, canonical apply, rebaseline,
  scheduler, or background ingestion work.
- Synthetic review data is reachable only inside the isolated review stack.
- Normal API runtime cannot serve synthetic review fixtures.

## Review Stack

The tracked stack definition lives in `docker-compose.review.yml`.

- `review-postgres` stores the review-only schema and synthetic review corpus.
- `review-redis` is review-only and internal to the Compose network.
- `review-api` exposes the real API routes on `127.0.0.1:8001`.

The review API entrypoint is `apps/api/src/review_main.py`.

- It is not imported by normal `apps/api/src/main.py`.
- It fails closed unless both of these are true:
  - review stack marker is `edfinder-review`
  - database target is exactly `review-postgres` / `edfinder_local_review`
- It serves the real Finder, System Detail, and Colony Planner routes with the
  normal database-backed application code.
- It serves review-only planner evidence and provenance contracts from review
  data stored in the dedicated review database.

## Commands

Run commands from the repository root with the project virtualenv:

```bash
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py preflight
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py up --confirm-local-review-environment
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py status
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py down --confirm-local-review-environment
```

Command behavior:

- `preflight` is fully read-only and starts nothing.
- `up` validates the review Compose file statically, starts only the isolated
  review services, bootstraps schema only inside `review-postgres`, seeds only
  review-only synthetic data into `edfinder_local_review`, and then starts the
  isolated review API.
- `status` reports running review services and API health without printing
  credentials.
- `down` removes only the review-stack containers, network, and review-only
  volumes.

## Synthetic Review Corpus

The seeded review database is deterministic, synthetic, and review-only.

- `Review Alpha` exercises available evidence while keeping canonical planner
  data as the planner truth source. Supporting evidence is report-only,
  non-canonical, bounded, and incomplete.
- `Review Beta` exercises unavailable selected-system evidence.
- `Review Gamma` exercises unknown selected-system evidence.
- `Review Delta` exercises not-evaluated selected-system evidence and the
  provenance fallback route.

Every review system has:

- a deterministic `id64`
- coordinates near Sol so Finder's normal default query can surface it
- at least one station
- bodies and ratings sufficient for System Detail and Colony Planner rendering

## Frontend Startup

Start the normal frontend in a separate terminal and intentionally point it at
the isolated review API:

```bash
cd frontend-v2
VITE_DEV_API_TARGET=http://127.0.0.1:8001 npm run start
```

This keeps the normal frontend development environment unchanged unless you
explicitly choose the isolated review API target.

## Health Checks

API health:

```bash
curl http://127.0.0.1:8001/api/health
```

Finder:

```bash
curl -X POST http://127.0.0.1:8001/api/local/search \
  -H 'Content-Type: application/json' \
  -d '{"reference_coords":{"x":0,"y":0,"z":0},"filters":{"distance":{"min":0,"max":200},"population":{"value":null,"comparison":"equal"},"economy":"any"},"size":50,"from":0,"sort_by":"rating","galaxy_wide":false}'
```

System Detail:

```bash
curl http://127.0.0.1:8001/api/system/7200000000001
```

Planner evidence:

```bash
curl http://127.0.0.1:8001/api/colony-planner/system/7200000000001/warehouse-planner-evidence
```

Provenance fallback:

```bash
curl http://127.0.0.1:8001/api/colony-planner/system/7200000000004/provenance-cockpit
```

## Browser Acceptance Journey

Follow this exact browser review flow:

1. Open Finder.
2. Confirm `Review Alpha`, `Review Beta`, `Review Gamma`, and `Review Delta`
   are visible in search results.
3. Open `Review Alpha`.
4. Confirm System Detail loads full synthetic fields.
5. Confirm `Open Colony Planner` works.
6. Confirm Colony Planner identifies `Review Alpha`.
7. Confirm the player-facing evidence summary says planning uses canonical
   planner data.
8. Confirm report-only, non-canonical, bounded, and incomplete review context
   is explicit.
9. Open the technical evidence details disclosure.
10. Confirm freshness, provenance, source class, and source posture are visible.
11. Repeat the key evidence checks for `Review Beta`, `Review Gamma`, and
    `Review Delta`.
12. Confirm keyboard focus and disclosure operation.
13. Confirm narrow viewport usability.
14. Confirm no app-wide recovery screen appears.
15. Confirm no unexpected browser console exception appears.

## Shutdown

When review is complete:

```bash
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -B scripts/dev/review_environment.py down --confirm-local-review-environment
```

This removes only the `edfinder-review` stack resources created by this
workflow.
