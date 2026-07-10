# Trae Solo Desktop Handoff (Historical PR #316 CI)

This document is a preserved troubleshooting handoff from the PR `#316`
stabilization window.

## Status

- Historical incident record only.
- Superseded by the merged repo state and the current clean-promotion work.
- [`../ROADMAP.md`](../ROADMAP.md) is the single authoritative roadmap for current work.
- Use `docs/README.md` plus the nearest active workflow/runbook doc for present-day tasks.

## Goal

Get PR **#316** (`devscore-retire-ratings`) to **all-green CI** after the ratings → archetypes / Development Score cutover.

This handoff exists because the current Trae Solo web session cannot view full GitHub Actions logs (GitHub shows “Sign in to view logs” and truncates the failing step output).

## Repo + Branch

- Repo: the local `ED-Finder` checkout
- PR: https://github.com/brianstewart377-rgb/ed-finder/pull/316
- Branch: `devscore-retire-ratings`

## Current Situation (as of 2026-07-06)

- CI was down to a single failing check: **Backend integration (PG+Redis)**.
- The job output was truncated in the UI, making the root cause hard to read without the raw logs.

## Fixes Already Pushed (on `devscore-retire-ratings`)

### 1) Ensure archetype MV is usable after seeding

Problem: `mv_archetype_rankings` is created **WITH NO DATA**, so any query using it fails unless it’s refreshed. CI seed path (`scripts/seed_check.sh`) did not refresh it.

Fix: refresh the MV during seed-check.

- Commit: `a2d6951` “Fix CI search: refresh archetype MV”
- File: `scripts/seed_check.sh`
  - Adds `REFRESH MATERIALIZED VIEW mv_archetype_rankings;`

### 2) Fix Phase 6 integration test archetype seeding helper

Problem: `_seed_archetype_rerank_rows()` in `tests/integration/test_phase6_api_coverage.py` built tuples that didn’t match the SQL placeholders for `executemany()`, which can fail the whole integration suite.

Fix: split the payload into separate lists for `system_archetype_scores` and `system_archetype_traits` inserts (matching their parameter counts).

- Commit: `e5fafb0` “Fix integration archetype seed helper”
- File: `tests/integration/test_phase6_api_coverage.py`

## What To Do Next (Desktop Trae Solo)

### 1) Check latest CI run on the branch

Open:
- https://github.com/brianstewart377-rgb/ed-finder/actions?query=branch%3Adevscore-retire-ratings

Find the newest run (after `e5fafb0`), then open the failing job.

### 2) Download raw logs (required if the UI truncates)

On the failing job page:
- Use the “⋯” menu (top-right on the job/run page) and select **Download log archive** (or “View raw logs” depending on GitHub UI).
- Search inside the log for:
  - `ERROR`
  - `FAILED`
  - `Traceback`
  - `psql:` / `seed_check`
  - `asyncpg.exceptions`

### 3) If Backend integration still fails, likely buckets

- **Seed failures** (sql/seed_preview.sql or invariant checks)
  - `scripts/seed_check.sh` now refreshes `mv_archetype_rankings`, but verify the script didn’t fail earlier.
- **Integration test failures**
  - If it still fails, check which file under `tests/integration/` is failing and why.
  - The Phase 6 archetype rerank tests seed their own minimal rows; the most likely failure mode here was the param mismatch fixed in `e5fafb0`.

## Local Repro (optional, requires Docker Desktop)

Bring up local Postgres+Redis using the repo’s compose file:

1) Start services:
   - `docker compose -f docker-compose.local.yml up -d`

2) Run integration tests against it:
   - Set environment:
     - `DATABASE_URL=postgresql://edfinder:edfinder-local-dev@127.0.0.1:55432/edfinder`
     - `REDIS_URL=redis://127.0.0.1:6379/15`
     - `CORS_ORIGINS=http://test`
     - `ADMIN_TOKEN=test-admin-token`
   - Run:
     - `python -m pytest tests/integration/ -v`

3) Tear down:
   - `docker compose -f docker-compose.local.yml down`

## Resume Prompt (paste into Desktop Trae Solo)

Read `docs/development/trae-solo-desktop-handoff-2026-07-06.md`. You are in the local `ED-Finder` checkout on branch `devscore-retire-ratings` (PR #316). CI still has a failing Backend integration check; open the newest Actions run, download raw logs, identify the failing test or seed step, patch, commit, and push until all checks are green.


