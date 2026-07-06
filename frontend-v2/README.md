# ed-finder v2 (Vite + React + TypeScript)

Proof-of-concept React frontend for ed-finder, mounted at **`/v2/`** alongside
the existing vanilla JS app at `/`. Same backend, same domain, same nginx.

## Why this exists

The vanilla `frontend/index.html` is ~12 500 lines of inline HTML/CSS/JS in a
single file. It works, it ships, it's fast — but a single missing
`-->` once silently nuked 500+ lines of behaviour for an unknown number of
sessions before anyone noticed (see `memory/PRD.md` session #6). v2 is the
seed of a future replacement. We are **not** committing to a full migration;
this is a vertical-slice POC to evaluate whether the dev experience justifies
the porting cost.

## What's in v2 today

**Status: feature parity with the legacy vanilla app.** Ready for nginx
root flip to `/v2/`. Now also:

- **Installable PWA** — `manifest.webmanifest` + `sw.js` shipped at build time. Service worker scope locked to `/v2/` so it can't claim root or `/v1/`. NetworkFirst-with-5s-timeout cache for `/api/*`, StaleWhileRevalidate for static assets. Auto-update on next reload.
- **Vitest unit tests** — `yarn test` runs 14 tests covering FC route maths, Compare cap behaviour, Colony state transitions. Pure-function tests, no DOM/network, ~3s.
- **OpenAPI codegen** — `yarn types:gen` writes `src/types/api.gen.ts` from the live backend (requires nginx forward — see `scripts/nginx_snippet.md`). Hand-maintained `api.ts` stays primary; generated file lives alongside as a drift reference.
- **Profile sync** — single backend endpoint (`PUT/GET/DELETE /api/profile/sync/{key}`) backed by a JSONB slot table. Frontend hook in Admin tab pushes/pulls Pinned + Compare + FC route + Colony tracker as one blob. Sync key = credential; 1 MiB per slot; manual push/pull (no auto-merge).

- ✅ **Finder tab** — search form with autocomplete + sliders + body-type filter pills + result cards.
- ✅ **Watchlist tab** — sortable table backed by `/api/watchlist`. Optimistic add/remove with rollback. Renders via the shared `<SystemTable>`. Row-click opens the detail modal.
- ✅ **Pinned tab** — localStorage-backed shortlist, schema-compatible with the vanilla `ed_pinned` key. Export-as-JSON, clear-all, cross-tab sync.
- ✅ **Compare tab** — up to 6 systems, matrix view with per-row winner highlighting, CSV export. Snapshot-based localStorage (`ed_compare_v2`).
- ✅ **Development Tuning tab** — reranks the current Finder results with archetype-led development weights via `POST /api/archetypes/rerank`. It builds a separate tuned order (Finder results remain unchanged) and is separate from the colony optimiser inside Simulation Preview.
- ✅ **FC Planner tab** — Fleet Carrier route planner with autocomplete-driven waypoints, 4 config inputs (jump range, cargo, tritium/jump, tritium price), pure-client math (no backend call) for total LY / hops / tritium / cost / cargo trips. CSV export. localStorage persisted (`ed_fc_v2`).
- ✅ **Colony Tracker tab** — localStorage-backed list of claimed systems (`ed_colony_v2`) with 4-state phase machine (planning / building / active / complete), per-row population progress bar, edit modal, CSV export, count badges per phase.
- ✅ **System Detail Modal** — full-detail overlay (system info grid + 8 score bars + bodies table + stations table + exploration value + external links). Shares Watchlist / Pin / Compare hooks. **Deep-linkable**: `#tab/system/12345678`.
- ✅ **Map tab** — pure-React 2-D galactic canvas (drag-pan, scroll-zoom, click-to-select, auto-fit).
- ✅ **Admin tab** — token-gated ops console (sessionStorage). Live status auto-refresh + Clear cache + Rebuild clusters.
- ✅ **Hash routing** — `#{tab}` and `#{tab}/system/{id64}`. Nine routes; sub-route works for every tab.
- ✅ **Shared `<SystemTable>`** — Watchlist + Pinned. Row-click opens detail.

```
src/
  App.tsx                           composition root + 9-tab layout + modal overlay
  main.tsx                          bootstrap
  components/
    NavBar.tsx                      9 tabs + 5 count badges (watchlist/pinned/compare/fc/colony)
    ResultCard.tsx                  search result row (live isPinned + isCompared)
    SystemTable.tsx                 shared table + optional row-click → modal
  features/
    search/                         finder
    watchlist/                      server-backed
    pinned/                         localStorage (ed_pinned)
    compare/                        localStorage (ed_compare_v2)
    search-tuning/                  Development Tuning; POST /api/archetypes/rerank
    fc-planner/                     localStorage (ed_fc_v2), pure-client math
    colony/                         localStorage (ed_colony_v2), phase state machine
    admin/                          sessionStorage token + ops actions
    system-detail/                  deep-linkable modal
    map/                            galactic 2-D canvas
  hooks/
    useDebounced.ts
    useHashRoute.ts                 ~90 LoC, supports `#tab/system/N` sub-route
  lib/
    api.ts                          typed fetch wrapper
    format.ts                       pure formatters
  types/
    api.ts                          hand-maintained API types
    api.gen.ts                      (generated — run `yarn types:gen`)
```

```
src/
  App.tsx                           composition root + finder layout + modal overlay
  main.tsx                          bootstrap
  components/
    NavBar.tsx                      7 tabs + watchlist / pinned / compare badges
    ResultCard.tsx                  search result row (live isPinned + isCompared)
    SystemTable.tsx                 shared table + optional row-click → modal
  features/
    search/                         finder
      SearchForm.tsx
      useSearch.ts
      useAutocomplete.ts
    watchlist/                      watchlist (server-backed)
      WatchlistTab.tsx
      useWatchlist.ts
    pinned/                         pinned (client-only, localStorage)
      PinnedTab.tsx
      usePinned.ts
    compare/                        compare (client-only, localStorage)
      CompareTab.tsx
      useCompare.ts
    search-tuning/                  Development Tuning reranker (POST /api/archetypes/rerank)
      AdvancedSearchTuningTab.tsx
      useSearchTuning.ts
    admin/                          admin (token-gated ops)
      AdminTab.tsx
      useAdmin.ts
    system-detail/                  detail modal (deep-linkable)
      SystemDetailModal.tsx
      useSystemDetail.ts            /api/system/{id64} fetch + cancellation
    map/                            galactic map
      GalacticMap.tsx
      MapTab.tsx
  hooks/
    useDebounced.ts
    useHashRoute.ts                 ~90 LoC, supports `#tab/system/N` sub-route
  lib/
    api.ts                          typed fetch wrapper
    format.ts                       pure formatters
  types/
    api.ts                          hand-maintained API types
    api.gen.ts                      (generated — run `yarn types:gen`)
```

```
src/
  App.tsx                           composition root + finder layout + modal overlay
  main.tsx                          bootstrap
  components/
    NavBar.tsx                      top tabs + watchlist / pinned / compare badges
    ResultCard.tsx                  search result row (live isPinned + isCompared)
    SystemTable.tsx                 shared table + optional row-click → modal
  features/
    search/                         finder
      SearchForm.tsx
      useSearch.ts
      useAutocomplete.ts
    watchlist/                      watchlist (server-backed)
      WatchlistTab.tsx
      useWatchlist.ts
    pinned/                         pinned (client-only, localStorage)
      PinnedTab.tsx
      usePinned.ts
    compare/                        compare (client-only, localStorage)
      CompareTab.tsx
      useCompare.ts
    system-detail/                  detail modal (deep-linkable)
      SystemDetailModal.tsx
      useSystemDetail.ts            /api/system/{id64} fetch + cancellation
    map/                            galactic map
      GalacticMap.tsx
      MapTab.tsx
  hooks/
    useDebounced.ts
    useHashRoute.ts                 ~90 LoC, supports `#tab/system/N` sub-route
  lib/
    api.ts                          typed fetch wrapper (now incl. system())
    format.ts                       pure formatters
  types/
    api.ts                          hand-maintained API types (system + bodies + stations)
    api.gen.ts                      (generated — run `yarn types:gen`)
```

## Local dev

```bash
cd frontend-v2
yarn install              # one-time
yarn dev                  # http://localhost:5174/v2/
```

For the Stage 17 planner workflow, prefer:

```bash
cd frontend-v2
npm run start             # runs dev-doctor first, then starts/reuses :3000
```

Manual verification gate:

```bash
npm run dev:doctor        # advisory checks
npm run dev:doctor:strict # non-zero exit if warnings exist
```

If you don't have an API running locally, you still get a clean error UI
that tells you what env var to set:

```bash
VITE_DEV_API_TARGET=https://ed-finder.app yarn dev
```

(The dev server proxies `/api/*` to that target, so CORS isn't an issue.)

## Production build

```bash
yarn build                # → dist/   ~60 KB gzipped
```

`vite.config.ts` sets `base: '/v2/'` so the bundle works when served from
that sub-path. The `dist/` directory is meant to be served by nginx at
`/v2/` (see deployment section).

## Deployment

Nginx mounts the existing vanilla frontend at `/var/www/html` and the v2
build at `/var/www/html-v2`. Both are read-only volumes in docker-compose.

```nginx
# Existing  (unchanged)
location / {
    root /var/www/html;
    try_files $uri $uri/ /index.html;
}

# New  (just add this block)
location /v2/ {
    alias /var/www/html-v2/;
    try_files $uri $uri/ /v2/index.html;
}
```

Build pipeline on Hetzner:

```bash
cd /opt/ed-finder/frontend-v2
yarn install --frozen-lockfile
yarn build
sudo rsync -a --delete dist/ /var/www/html-v2/
sudo docker compose exec nginx nginx -s reload
```

(For now, build locally + commit `dist/`. We can promote to a proper docker
multi-stage build once the v2 surface is more than one component.)

## Type generation

`src/types/api.ts` is hand-maintained for the endpoints in active use. A
generator is wired up to keep `src/types/api.gen.ts` aligned with the backend
OpenAPI schema:

```bash
yarn types:gen
```

This runs a local OpenAPI dump from `apps/api/src/main.py` and then runs
`openapi-typescript` to write `src/types/api.gen.ts`.

Requirements:

- Python 3.12/3.11 (Windows): `asyncpg` does not currently support Python 3.14
- Backend deps installed: `pip install -r apps/api/requirements.txt`
- Optional: set `ED_FINDER_PYTHON` to a compatible interpreter path if you have
  multiple Pythons installed (the script will also try `py -3.12` / `py -3.11`)

`openapi-typescript` is a dev dependency. The generated file is committed so
frontend/backend contract drift is visible in diffs.

## Bundle size budget

- React + ReactDOM: ~12 KB gzipped (chunked separately for caching)
- App + components: ~60 KB gzipped today
- Tailwind: tree-shaken to ~3 KB
- **Total first paint:** ~75 KB gz, single round-trip

If we cross 200 KB gz total we should investigate code-splitting. Until then
it's not worth the complexity.

## Migration plan — DONE

1. ✅ Scaffold + result-card POC.
2. ✅ Search form + filters (left rail).
3. ✅ Top tab bar + routing (9 tabs + sub-route `system/{id64}`).
4. ✅ Watchlist / Pinned / Compare.
5. ✅ Map.
6. ✅ System Detail Modal — deep-linkable.
7. ✅ Search Tuning + Admin. Future Search Tuning rework should add clearer presets, before/after rank movement, and stronger explanations without changing colony-build optimisation.
8. ✅ FC Planner + Colony Tracker.
9. ✅ Polish — Vitest tests + PWA + OpenAPI codegen wired + Profile sync (backend + frontend).
10. **Parity flip → ready.** One-liner deploy:
    ```bash
    sudo bash /opt/ed-finder/scripts/deploy_v2.sh
    ```
    See `scripts/deploy_v2.sh` for what it does and `scripts/nginx_snippet.md` for the (one-time) nginx tweak that exposes `/openapi.json` for codegen + the (eventual) parity-flip block.
