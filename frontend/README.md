# ed-finder frontend (Vite + React + TypeScript)

Current React frontend for ed-finder, served at **`/`**. `frontend/` is the
only shipping frontend in the repo.

## Why this exists

The retired vanilla frontend grew into a large inline HTML/CSS/JS bundle that
was difficult to change safely. This React app replaced it and is now the live
frontend. The goal here is maintainability, testability, and a cleaner typed
contract with the API.

## What's In The React App Today

**Status: feature parity with the retired vanilla app.** The React app is now
the canonical frontend served from `/`. Now also:

- **Installable PWA** — `manifest.webmanifest` + `sw.js` shipped at build time. Service worker scope follows the app base (`/` in production). NetworkFirst-with-5s-timeout cache for `/api/*`, StaleWhileRevalidate for static assets. Auto-update on next reload.
- **Vitest unit tests** — `yarn test` runs the frontend unit suite for features, hooks, and UI flows.
- **OpenAPI codegen** — `yarn types:gen` writes `src/types/api.gen.ts` from a local OpenAPI dump by default. You can also point it at a live URL with `ED_FINDER_OPENAPI_URL` or `VITE_OPENAPI_URL` when needed.
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
  main.tsx                          bootstrap + alternate-shell gate
  app/                              app-shell helpers and shared view wiring
  components/
    NavBar.tsx                      top navigation + workspace badges
    ResultCard.tsx                  search result row
    SystemTable.tsx                 shared table + optional row-click → modal
  features/
    admin/                          ops console
    colony-planner/                 planner + slot canvas tools
    compare/                        localStorage (ed_compare_v2)
    fc-planner/                     localStorage (ed_fc_v2)
    map/                            galactic 2-D canvas
    my-work/                        saved systems + planning workflows
    operator/                       operator cockpit + diagnostics
    pinned/                         localStorage (ed_pinned)
    profile-sync/                   cross-device sync panel
    search/                         finder
    search-tuning/                  development tuning
    system-detail/                  deep-linkable modal
    watchlist/                      server-backed
  hooks/
    useDebounced.ts
    useHashRoute.ts
  lib/
    api.ts                          typed fetch wrapper
    format.ts                       pure formatters
  store/
    pinnedStore.ts
    syncKeyStore.ts
  types/
    api.ts                          public API type surface
    api.gen.ts                      generated from OpenAPI
```

## Local dev

Windows-first bootstrap:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ..\scripts\dev\bootstrap-windows.ps1 -RunDoctor
powershell -NoProfile -ExecutionPolicy Bypass -File ..\scripts\dev\start_local_dev.ps1 -EnsureServices
```

See `docs/development/windows-dev-environment.md` for the canonical Windows
wrapper flow and Git Bash usage.

```bash
cd frontend
yarn install              # one-time
yarn dev                  # http://localhost:3000/
```

For the Stage 17 planner workflow, prefer:

```bash
cd frontend
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
yarn build                # → dist/
```

`vite.config.ts` defaults to `base: '/'` for the canonical root-served app.
The `dist/` directory is meant to be served by nginx at `/` (see deployment
section).

## Deployment

Nginx serves the built frontend from `/var/www/app`, backed by the
`frontend/dist` volume in `docker-compose.yml`.

```nginx
# Canonical root-served SPA
location / {
    root /var/www/app;
    try_files $uri /index.html;
}

# Legacy redirects for old bookmarks / cached HTML
location = /v2  { return 301 https://$host/; }
location = /v2/ { return 301 https://$host/; }
location ~ ^/v2/(.*)$ { return 301 https://$host/$1; }
```

Build pipeline on Hetzner:

```bash
cd /opt/ed-finder
bash scripts/deploy_main.sh
```

The canonical deploy recreates nginx when needed so mount/config changes are
picked up reliably.

Preferred release path:

- build and test locally
- package the already-built `frontend/dist` via
  `scripts/package_frontend_bundle.sh`
- let `scripts/release-main-to-prod.ps1` upload that archive and call
  `scripts/deploy_main.sh --frontend-archive ...`

That keeps production on the exact certified frontend bundle instead of doing a
fresh dependency resolution on the server just to rebuild JS assets.

## Type generation

`src/types/api.ts` is hand-maintained for the endpoints in active use. A
generator is wired up to keep `src/types/api.gen.ts` aligned with the backend
OpenAPI schema:

```bash
yarn types:gen
```

By default this runs a local OpenAPI dump from `apps/api/src/main.py` and then
runs `openapi-typescript` to write `src/types/api.gen.ts`.

Requirements:

- Python 3.12/3.11 (Windows): `asyncpg` does not currently support Python 3.14
- Backend deps installed: `pip install -r apps/api/requirements.txt`
- Optional: set `ED_FINDER_PYTHON` to a compatible interpreter path if you have
  multiple Pythons installed (the script will also try `py -3.12` / `py -3.11`)

`openapi-typescript` is a dev dependency. The generated file is committed so
frontend/backend contract drift is visible in diffs.

## Bundle size budget

Track bundle size with the current `yarn build` output rather than relying on
stale hard-coded numbers. If the production bundle grows meaningfully, prefer
targeted code-splitting over blanket optimisation.

## Promotion Notes

1. ✅ Scaffold + result-card POC.
2. ✅ Search form + filters (left rail).
3. ✅ Top tab bar + routing (9 tabs + sub-route `system/{id64}`).
4. ✅ Watchlist / Pinned / Compare.
5. ✅ Map.
6. ✅ System Detail Modal — deep-linkable.
7. ✅ Search Tuning + Admin. Future Search Tuning rework should add clearer presets, before/after rank movement, and stronger explanations without changing colony-build optimisation.
8. ✅ FC Planner + Colony Tracker.
9. ✅ Polish — Vitest tests + PWA + OpenAPI codegen wired + Profile sync (backend + frontend).
10. **Root promotion complete.** `frontend/` is the live app and `/v2` is redirect-only. Deploy with:
    ```bash
    bash /opt/ed-finder/scripts/deploy_main.sh
    ```
    `scripts/nginx_snippet.md` remains as a reference for the root-served nginx shape and optional OpenAPI forwarding.
