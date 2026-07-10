# Ratings Resume Handoff (Historical)

This note records an earlier resume point for the ratings-overhaul work. The
migration has since been completed in the canonical local workspace.

**Status (2026-07): completed.**

## Current Position (2026-07-09)

- The ratings migration itself is complete; this file remains historical and is
  no longer the source of truth for active prioritization.
- The canonical current scorer remains **Ratings v3.4 Best-Build Potential**,
  with the archetype-led frontend/API cutover in place.
- The production ratings closeout lane is in healthy steady state; the remaining
  follow-up is contract/integrity hardening such as body-data truthfulness and
  related provenance/drift guardrails, not an active mixed-generation rerate
  backlog.
- Stage 25 product work is complete on the integrated line, production is now
  running deployed commit `ee6707c`, and the large post-deploy ring/no-body
  repair buckets have already been drained.
- The remaining production residue is small and explicit: ring drift is `0`,
  the no-body dirty tail is now a small live-churn retry band, and the only
  persistent structural tail still being tracked is `3` body-contract rows.
- The local engineering environment is materially healthier than when this
  handoff was written: repo-local `.venv` execution is canonical, disposable
  Docker-backed Postgres/Redis preflight is green, and the broad local pytest
  burn-down was most recently observed green at `1487 passed, 16 skipped` in
  the current workspace.
- The active product roadmap has moved on to Stage 25 shell/context work plus
  foundation hardening around migration safety, backup/restore rehearsal, and
  CI/build honesty. See [`../ROADMAP.md`](../ROADMAP.md) for the current queue.

## Use This File As Reference Only

- [`../ROADMAP.md`](../ROADMAP.md) is the single authoritative roadmap for current work.
- This file is preserved for migration traceability, not as the default answer to "what next?".
- If you are resuming active work, start from `docs/README.md`, then `docs/ROADMAP.md`, then the nearest active contract doc.

## Final Direction

The implementation path that shipped is:

1. Finish the archetype-led cutover (Development Score + archetype assessment)
2. Retire the legacy ratings rerank surface (`/api/ratings/rerank`) and legacy `_rating` payloads from the active frontend contract
3. Keep evidence-authoritative scoring as a separate future track

This was chosen because the archetype engine is already real, mounted, and materially further along than the evidence-governance path.

## Canonical Repo Context

- Canonical repo: the local `ED-Finder` checkout (outside OneDrive sync)
- Frontend: `frontend/`
- Backend: `apps/api/`
- Main archetype routes: `/api/archetypes/*`
- Local stack entrypoint: `.\scripts\dev\start_local_dev.ps1`

## What Was Done

- Finder, Compare, Map, Pinned, Watchlist, and System Detail lead with archetype/development scoring
- Search/watchlist contracts treat `development` / `min_development_score` as canonical
- Search Tuning was retained but reframed as **Development Tuning** and now reranks via `POST /api/archetypes/rerank`
- Legacy ratings rerank (`POST /api/ratings/rerank`) is retired and removed from the backend + active frontend contract
- The live frontend no longer shows or depends on legacy rating rationale/radar surfaces

## Most Relevant Files (Post-Migration)

### Backend

- `apps/api/src/models.py`
- `apps/api/src/local_search.py`
- `apps/api/src/routers/archetypes.py`
- `apps/api/src/helpers.py`

### Frontend

- `frontend/src/lib/archetypes.ts`
- `frontend/src/lib/api.ts`
- `frontend/src/types/api.ts`
- `frontend/src/types/api.gen.ts`
- `frontend/src/components/ResultCard.tsx`
- `frontend/src/components/SystemTable.tsx`
- `frontend/src/features/search/useSearch.ts`
- `frontend/src/features/search/SearchForm.tsx`
- `frontend/src/features/compare/CompareTab.tsx`
- `frontend/src/features/compare/useCompare.ts`
- `frontend/src/features/map/MapTab.tsx`
- `frontend/src/features/map/GalacticMap.tsx`
- `frontend/src/features/pinned/pinnedEntry.ts`
- `frontend/src/App.tsx`

## Current Technical State

### Canonical wire terminology

- Search uses `sort_by=development`
- Search uses `min_development_score`
- Watchlist alert input uses `min_development_score`

### Legacy compatibility status

Legacy rating terminology and payloads are removed from the active frontend contract. Historical redesign documents may still mention “ratings rerank” as part of Stage 7 forensic notes and are explicitly marked as historical.

## Next Work (After Ratings Migration)

- Evidence-authoritative scoring work (Observed Evidence / Validation) can proceed independently of the Development Score cutover.
- Remaining “ratings” references should be treated as historical doc debt and cleaned gradually.

## Environment Notes

Tooling in the older OneDrive-synced workspace was unreliable for long frontend
commands. The canonical dev workspace is now a local checkout outside OneDrive.

Python note: the backend expects a Python version with `asyncpg` wheels available. Python 3.14 does not currently support `asyncpg` on Windows, so use Python 3.12/3.11 for backend work.

Useful verification:

- `frontend`: `npm run test:ci`, `npm run build:typecheck`, `npm run types:gen`
- `apps/api`: `python -m compileall apps/api/src`

## Historical Resume Prompt

This prompt is preserved only as a record of how the migration was resumed at
the time. Do not use it as the default instruction set for current work.

If starting a historical reconstruction chat, use something close to this:

> Read `docs/development/ratings-resume-handoff-2026-07-06.md` and continue the ratings-overhaul work from there. Stay on the archetype-led cutover path. The next task is to reduce the remaining live use of legacy score fields in the active frontend while keeping legacy rating as compatibility-only context.

## Success Criteria For The Next Slice

- No new user-facing frontend surface should rely on nested `_rating` as its normal source
- Archetype/development data should drive active ranking and display behavior
- Legacy rating should remain visible only where explicitly intended as context
- Compatibility aliases should remain intact unless there is a deliberate migration step to remove them

