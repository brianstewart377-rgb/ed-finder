# `_redesign/` — archived prototype, quarantined

This directory is the **landing zone for the UIItty4 prototype** (see
`UX_AUDIT.md` on the `UIItty4` branch for the design rationale). It is
deliberately isolated from the rest of `frontend/src/` while we migrate.

## Status: Phase 1 — design system landed, mock data only

- All components are copied from the `UIItty4` branch unchanged (`.jsx`, not
  yet ported to `.tsx`).
- All data is read from `lib/mockData.js`. **No backend calls.** Wiring to the
  real API (`/api/local/search`, `/api/map/*`, `/api/watchlist`, etc.) lands
  in Phase 2 via an adapter layer and per-workspace hooks.

## Current status

The redesign is no longer wired into `src/main.tsx` and is not reachable
through the live app entrypoint. It remains in-tree only as archived reference
material while the active Stage 25 shell continues on the canonical app path.

## Layout

```
_redesign/
├── RedesignApp.jsx          # entry — mirrors UIItty4's App.js
├── redesign.css             # global styles (brushed steel, nebula bg, sliders)
├── components/
│   ├── Discover/  ←  Finder workspace (filter rail + result rail + drawer + radar + EDDN feed)
│   ├── Map/       ←  Map workspace (canvas + layer toggles)
│   ├── Plan/      ←  FC Planner workspace
│   ├── Track/     ←  Colony Tracker workspace
│   ├── Shell/     ←  TopBar + StatusStrip (top + bottom HUD)
│   ├── Tabs/      ←  Watchlist/Pinned/Compare/Advanced Search Tuning/Admin stubs
│   └── UI/        ←  Hud primitives (Panel, HudButton, RatingBar, TierPill, etc.)
└── lib/
    └── mockData.js          # single source of truth for the prototype
```

## What NOT to do

- ❌ Don't import anything from `_redesign/` outside `_redesign/` itself or
  explicit archive/reference docs. The folder must remain easy to delete in one
  rm if we abandon the design.
- ❌ Don't import anything from `@/` (the rest of `src/`) into this folder
  yet. Until Phase 2, the prototype is **fully self-contained**.
- ❌ Don't reintroduce the redesign into `main.tsx` or any other live render
  path. The current app shell is the only canonical runtime entrypoint.

## Phase 2 (next PR): wire to the real backend

Add `_redesign/adapters/` with typed functions that return `mockData`-shaped
objects from the live endpoints, then replace the `import { SYSTEMS, … } from
'../../lib/mockData'` imports inside each workspace one at a time:

| Workspace | Mock dependency             | Real endpoint                         |
|-----------|------------------------------|---------------------------------------|
| Discover  | `SYSTEMS`, `EDDN_FEED`       | `POST /api/local/search`, `GET /api/events/recent` |
| Map       | `REGIONS`, `CLUSTERS`, `HEATMAP` | `GET /api/map/{regions,clusters/hulls,heatmap}` |
| Drawer    | `SYSTEMS[i]` detail          | `GET /api/system/{id64}`              |
| Tabs      | hard-coded stubs             | `/api/watchlist`, `/api/archetypes/rerank`, etc. |

Until those land, this folder remains a quarantined prototype snapshot with
hand-picked mock data rather than a supported preview surface.
