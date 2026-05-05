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
- ✅ **Watchlist tab** — sortable table backed by `/api/watchlist`. Optimistic add/remove with rollback. Now uses the shared `<SystemTable>`.
- ✅ **Pinned tab** — localStorage-backed shortlist (schema-compatible with the vanilla `ed_pinned` key so existing user data survives the cutover). Export-as-JSON, clear-all, cross-tab sync via the `storage` event. No backend round-trip.
- ✅ **Map tab** — pure-React 2-D galactic canvas (drag-pan, scroll-zoom, click-to-select, auto-fit). Plots whatever the Finder tab last returned.
- ✅ **Hash routing** — `#finder` / `#watchlist` / `#pinned` / `#map`. Deep-links work.
- ✅ **Shared `<SystemTable>`** — common rendering layer for every "list of systems" feature (Watchlist + Pinned today; Compare + Cluster anchors tomorrow). Finite column set keeps the visual identity consistent.
- ⏳ Optimizer / FC Planner / Compare / Colony Tracker / Admin: still vanilla.

```
src/
  App.tsx                           composition root + finder layout
  main.tsx                          bootstrap
  components/
    NavBar.tsx                      top tabs + watchlist / pinned badges
    ResultCard.tsx                  search result row (live isPinned state)
    SystemTable.tsx                 shared table used by every list feature
  features/
    search/                         finder
      SearchForm.tsx
      useSearch.ts                  filters→request→results state machine
      useAutocomplete.ts            debounced /api/local/autocomplete
    watchlist/                      watchlist (server-backed)
      WatchlistTab.tsx
      useWatchlist.ts               optimistic add/remove
    pinned/                         pinned (client-only, localStorage)
      PinnedTab.tsx
      usePinned.ts                  localStorage + storage-event sync
    map/                            galactic map
      GalacticMap.tsx               pure-React canvas (~250 LoC)
      MapTab.tsx                    map + selection panel
  hooks/
    useDebounced.ts
    useHashRoute.ts                 30 LoC, no react-router
  lib/
    api.ts                          typed fetch wrapper
    format.ts                       pure formatters
  types/
    api.ts                          hand-maintained API types
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
3. ✅ Top tab bar + routing (`#finder`, `#watchlist`, `#pinned`, `#map`).
4. 🟡 Watchlist / Pinned / Compare — **Watchlist + Pinned done, Compare remaining** (will reuse `<SystemTable>`).
5. ✅ Map (canvas wrapped in one component).
6. Once parity hit: nginx flips root → v2; v1 lives at `/v1/` for one week
   as rollback insurance; then deleted.

Estimated effort remaining: 2–4 weeks part-time. Hardest surfaces left:
Optimizer (numeric controls + rerank API), FC Planner (jump-range solver),
and the system detail modal (deep-linkable from every list).
