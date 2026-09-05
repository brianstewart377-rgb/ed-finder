# ED-Finder frontend

React + TypeScript + Vite frontend for ED-Finder, served at `/` when built into the current application surface.

Production deployment is governed by the current V3 infrastructure/operator documentation. This file documents frontend development and validation only.

## Main capabilities

The frontend contains the Finder, Watchlist, Pinned, Compare, Development Tuning, Fleet Carrier Planner, Colony Planner/Tracker, System Detail, Map, Admin/Operator, profile sync and supporting workspace flows.

API access should go through the typed client modules under `src/lib/api/`. Generated OpenAPI types live under `src/types/`.

## Layout

```text
src/
  App.tsx
  main.tsx
  app/
  components/
  features/
    admin/
    colony-planner/
    compare/
    fc-planner/
    map/
    my-work/
    operator/
    pinned/
    profile-sync/
    search/
    search-tuning/
    system-detail/
    watchlist/
  hooks/
  lib/
  store/
  types/
```

## Local development

Windows-first bootstrap:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ..\scripts\dev\bootstrap-windows.ps1 -RunDoctor
powershell -NoProfile -ExecutionPolicy Bypass -File ..\scripts\dev\start_local_dev.ps1 -EnsureServices
```

See `docs/development/windows-dev-environment.md` for the canonical Windows wrapper flow and Git Bash usage.

```bash
cd frontend
yarn install --frozen-lockfile
yarn dev
```

The dev server normally runs at `http://localhost:3000/`.

Useful checks:

```bash
yarn typecheck
yarn test
yarn build
npm run dev:doctor
npm run dev:doctor:strict
```

Additional focused map, planner, operator, Cypress, Storybook and accessibility scripts are defined in `package.json`.

## API target for local development

Local development should point at a local/disposable API where practical. When an explicit remote read path is authorized for a development task, set `VITE_DEV_API_TARGET` deliberately rather than relying on an implicit production fallback.

## Production build artifact

```bash
yarn build
```

The build writes `dist/`. Treat `dist/` as an artifact; do not infer a production deployment procedure from this repository directory. Current production promotion follows the V3 operator boundary documented under `docs/operations/`.

## Type generation

```bash
yarn types:gen
```

The generator keeps `../packages/api-client/src/generated/api.gen.ts` aligned with the backend OpenAPI schema. The generated file is committed so contract drift is visible in diffs.

Requirements:

- use the repository-supported Python 3.12 environment for backend schema generation;
- install backend dependencies from the repository's pinned requirements;
- use `ED_FINDER_PYTHON` only when an explicit interpreter override is needed.

## Bundle size

Track bundle size with the current `yarn build` output. If the bundle grows materially, prefer targeted code-splitting and measured improvements rather than blanket optimisation.
