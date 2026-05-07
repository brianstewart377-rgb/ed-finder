# `_redesign/` — UIItty4 design system, quarantined

This directory is the **landing zone for the UIItty4 prototype** (see
`UX_AUDIT.md` on the `UIItty4` branch for the design rationale). It is
deliberately isolated from the rest of `frontend-v2/src/` while we migrate.

## Status: Phase 1 — design system landed, mock data only

- All components are copied from the `UIItty4` branch unchanged (`.jsx`, not
  yet ported to `.tsx`).
- All data is read from `lib/mockData.js`. **No backend calls.** Wiring to the
  real API (`/api/local/search`, `/api/map/*`, `/api/watchlist`, etc.) lands
  in Phase 2 via an adapter layer and per-workspace hooks.

## How users opt in

The redesign is gated by a feature flag in `src/main.tsx`. It does **not** load
for default users:

| Action                                   | Effect                          |
|------------------------------------------|---------------------------------|
| Visit `…/v2/?ui=v3`                      | Load redesign + remember choice |
| Visit `…/v2/?ui=v2`                      | Load v2 + clear redesign choice |
| `localStorage.setItem('uiV3','1')`+reload| Sticky redesign preview         |
| `localStorage.removeItem('uiV3')`+reload | Back to v2                      |

The redesign bundle (`RedesignApp-*.js`) and its CSS (`RedesignApp-*.css`) are
emitted as **separate chunks** by Vite's dynamic-import code splitting, so
opt-out users never download them.

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
│   ├── Tabs/      ←  Watchlist/Pinned/Compare/Optimizer/Admin stubs
│   └── UI/        ←  Hud primitives (Panel, HudButton, RatingBar, TierPill, etc.)
└── lib/
    └── mockData.js          # single source of truth for the prototype
```

## What NOT to do

- ❌ Don't import anything from `_redesign/` outside `_redesign/` itself or
  `main.tsx`. The folder must remain easy to delete in one rm if we abandon
  the design.
- ❌ Don't import anything from `@/` (the rest of `src/`) into this folder
  yet. Until Phase 2, the prototype is **fully self-contained**.
- ❌ Don't add the redesign to the default render path in `main.tsx`. The
  flag-gate is the entire safety story for production.

## Phase 2 (next PR): wire to the real backend

Add `_redesign/adapters/` with typed functions that return `mockData`-shaped
objects from the live endpoints, then replace the `import { SYSTEMS, … } from
'../../lib/mockData'` imports inside each workspace one at a time:

| Workspace | Mock dependency             | Real endpoint                         |
|-----------|------------------------------|---------------------------------------|
| Discover  | `SYSTEMS`, `EDDN_FEED`       | `POST /api/local/search`, `GET /api/events/recent` |
| Map       | `REGIONS`, `CLUSTERS`, `HEATMAP` | `GET /api/map/{regions,clusters/hulls,heatmap}` |
| Drawer    | `SYSTEMS[i]` detail          | `GET /api/system/{id64}`              |
| Tabs      | hard-coded stubs             | `/api/watchlist`, `/api/ratings/rerank`, etc. |

Until those land, anyone opening the redesign sees the prototype's hand-picked
mock data and not real galactic data — which is the desired behaviour for an
opt-in preview.
