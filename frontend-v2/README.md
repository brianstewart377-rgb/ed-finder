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

- ✅ **Finder tab** — search form with autocomplete + sliders + body-type filter pills + result cards (~280 LoC across 4 typed files; the vanilla equivalent was scattered across ~1500 lines of `index.html`).
- ✅ **Watchlist tab** — sortable table backed by `/api/watchlist`. Optimistic add/remove with rollback. Renders via the shared `<SystemTable>`. Row-click opens the detail modal.
- ✅ **Pinned tab** — localStorage-backed shortlist (schema-compatible with the vanilla `ed_pinned` key so existing user data survives the cutover). Export-as-JSON, clear-all, cross-tab sync via the `storage` event. No backend round-trip.
- ✅ **Compare tab** — up to 6 systems, matrix view (metrics × systems) with per-row winner highlighting, CSV export, clear-all. Snapshot-based localStorage (`ed_compare_v2`). Column-header names link into the detail modal.
- ✅ **Optimizer tab** — 6 weight sliders (economy / slots / strategic / safety / terraforming / diversity) + economy preference selector. Reranks the current Finder results in place via `/api/ratings/rerank`, shows reordered list with original→reranked deltas. Server normalises non-1.0 sums; UI flags the warning. Row-click opens the detail modal.
- ✅ **System Detail Modal** — full-detail overlay (system info grid + 8 score bars + bodies table + stations table + exploration value + external links). Shares Watchlist / Pin / Compare hooks with the rest of the app, so the modal's own action buttons stay in sync with the tab badges. **Deep-linkable**: `#finder/system/12345678` opens the modal on top of the Finder tab; closing pops back to `#finder`. Esc / backdrop-click / X all close.
- ✅ **Map tab** — pure-React 2-D galactic canvas (drag-pan, scroll-zoom, click-to-select, auto-fit). Plots whatever the Finder tab last returned.
- ✅ **Admin tab** — token-gated ops console. Live status (counts + meta flags + cache stats, auto-refresh every 30s) + two actions (Clear cache / Rebuild clusters). Token stored in **sessionStorage** only (forgotten on tab close — admin tokens shouldn't outlive the browsing session).
- ✅ **Hash routing** — `#{tab}` and `#{tab}/system/{id64}`. Sub-route is optional and works for every tab.
- ✅ **Shared `<SystemTable>`** — common rendering layer for every "list of systems" feature with optional `onRowClick` for opening the detail modal.
- ⏳ FC Planner / Colony Tracker: still vanilla.

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
    optimizer/                      optimizer (POST /api/ratings/rerank)
      OptimizerTab.tsx
      useOptimizer.ts
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
generator is wired up for when we want full coverage:

```bash
yarn types:gen
# writes src/types/api.gen.ts from https://ed-finder.app/openapi.json
# override with VITE_OPENAPI_URL=http://127.0.0.1:8000/openapi.json yarn types:gen
```

`openapi-typescript` is already a devDep. The generated file is git-ignored
on purpose — regenerate when backend routes change rather than committing a
snapshot.

## Bundle size budget

- React + ReactDOM: ~12 KB gzipped (chunked separately for caching)
- App + components: ~60 KB gzipped today
- Tailwind: tree-shaken to ~3 KB
- **Total first paint:** ~75 KB gz, single round-trip

If we cross 200 KB gz total we should investigate code-splitting. Until then
it's not worth the complexity.

## Migration plan (if/when we go full)

1. ✅ Scaffold + result-card POC.
2. ✅ Search form + filters (left rail).
3. ✅ Top tab bar + routing (`#finder`, `#watchlist`, `#pinned`, `#compare`, `#optimizer`, `#map`, `#admin` + sub-route `system/{id64}`).
4. ✅ Watchlist / Pinned / Compare — all three share `<SystemTable>` (Compare uses its own matrix layout but shares `lib/format`).
5. ✅ Map.
6. ✅ System Detail Modal — deep-linkable from any tab; reuses the shared Watchlist/Pin/Compare hooks for its own action buttons.
7. ✅ Optimizer + Admin.
8. Once parity hit (FC Planner + Colony Tracker remain): nginx flips
   root → v2; v1 lives at `/v1/` for one week as rollback insurance;
   then deleted.

Estimated effort remaining: 1 week part-time. Two surfaces left:
FC Planner (jump-range solver) and Colony Tracker (state machine).
