# Ratings Resume Handoff (Historical)

This note was used to resume the ratings-overhaul work after a chat loss. The migration has since been completed in the canonical non-OneDrive workspace.

**Status (2026-07): completed.**

## Final Direction

The implementation path that shipped is:

1. Finish the archetype-led cutover (Development Score + archetype assessment)
2. Retire the legacy ratings rerank surface (`/api/ratings/rerank`) and legacy `_rating` payloads from the v2 contract
3. Keep evidence-authoritative scoring as a separate future track

This was chosen because the archetype engine is already real, mounted, and materially further along than the evidence-governance path.

## Canonical Repo Context

- Canonical repo: `c:\Users\brian\Documents\trae_projects\ED-Finder` (non-OneDrive)
- Frontend: `frontend-v2/`
- Backend: `apps/api/`
- Main archetype routes: `/api/archetypes/*`
- Local stack entrypoint: `.\scripts\dev\start_local_dev.ps1`

## What Was Done

- Finder, Compare, Map, Pinned, Watchlist, and System Detail lead with archetype/development scoring
- Search/watchlist contracts treat `development` / `min_development_score` as canonical
- Search Tuning was retained but reframed as **Development Tuning** and now reranks via `POST /api/archetypes/rerank`
- Legacy ratings rerank (`POST /api/ratings/rerank`) is retired and removed from the backend + v2 contract
- v2 UI no longer shows or depends on legacy rating rationale/radar surfaces

## Most Relevant Files (Post-Migration)

### Backend

- `apps/api/src/models.py`
- `apps/api/src/local_search.py`
- `apps/api/src/routers/archetypes.py`
- `apps/api/src/helpers.py`

### Frontend

- `frontend-v2/src/lib/archetypes.ts`
- `frontend-v2/src/lib/api.ts`
- `frontend-v2/src/types/api.ts`
- `frontend-v2/src/types/api.gen.ts`
- `frontend-v2/src/components/ResultCard.tsx`
- `frontend-v2/src/components/SystemTable.tsx`
- `frontend-v2/src/features/search/useSearch.ts`
- `frontend-v2/src/features/search/SearchForm.tsx`
- `frontend-v2/src/features/compare/CompareTab.tsx`
- `frontend-v2/src/features/compare/useCompare.ts`
- `frontend-v2/src/features/map/MapTab.tsx`
- `frontend-v2/src/features/map/GalacticMap.tsx`
- `frontend-v2/src/features/pinned/pinnedEntry.ts`
- `frontend-v2/src/App.tsx`
- `frontend-v2/public/development.html`

## Current Technical State

### Canonical wire terminology

- Search uses `sort_by=development`
- Search uses `min_development_score`
- Watchlist alert input uses `min_development_score`

### Legacy compatibility status

Legacy rating terminology and payloads are removed from the active v2 app contract. Historical redesign documents may still mention “ratings rerank” as part of Stage 7 forensic notes and are explicitly marked as historical.

## Next Work (After Ratings Migration)

- Evidence-authoritative scoring work (Observed Evidence / Validation) can proceed independently of the Development Score cutover.
- Remaining “ratings” references should be treated as historical doc debt and cleaned gradually.

## Environment Notes

Tooling in the OneDrive workspace was unreliable for long frontend commands. The canonical dev workspace is now non-OneDrive:

- `c:\Users\brian\Documents\trae_projects\ED-Finder`

Python note: the backend expects a Python version with `asyncpg` wheels available. Python 3.14 does not currently support `asyncpg` on Windows, so use Python 3.12/3.11 for backend work.

Useful verification:

- `frontend-v2`: `npm run test:ci`, `npm run build:typecheck`, `npm run types:gen`
- `apps/api`: `python -m compileall apps/api/src`

## Resume Prompt

If starting a new chat, use something close to this:

> Read `docs/development/ratings-resume-handoff-2026-07-06.md` and continue the ratings-overhaul work from there. Stay on the archetype-led cutover path. The next task is to reduce the remaining live use of legacy score fields in the active v2 UI while keeping legacy rating as compatibility-only context.

## Success Criteria For The Next Slice

- No new user-facing v2 surface should rely on nested `_rating` as its normal source
- Archetype/development data should drive active ranking and display behavior
- Legacy rating should remain visible only where explicitly intended as context
- Compatibility aliases should remain intact unless there is a deliberate migration step to remove them
