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

## What's in the POC

```
src/
  main.tsx                     bootstrap
  App.tsx                      demo page (Sol+50LY, populated only)
  components/
    ResultCard.tsx             the ported component (≈220 LoC, 1 file,
                               typed end-to-end vs ~120 LoC of HTML strings
                               sprinkled across 3 functions in vanilla)
  lib/
    api.ts                     typed fetch wrapper, no axios, no react-query
    format.ts                  pure helpers (rating tier, population etc.)
  types/
    api.ts                     hand-maintained API types
  vite-env.d.ts                ImportMeta.env types
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

When v2 grows past a handful of endpoints, run:

```bash
yarn add -D openapi-typescript
npx openapi-typescript https://ed-finder.app/openapi.json -o src/types/api.gen.ts
```

The backend already publishes a clean OpenAPI schema (31 paths,
30 documented). Generated types replace `src/types/api.ts` and stay in sync
with backend changes for free.

## Bundle size budget

- React + ReactDOM: ~12 KB gzipped (chunked separately for caching)
- App + components: ~60 KB gzipped today
- Tailwind: tree-shaken to ~3 KB
- **Total first paint:** ~75 KB gz, single round-trip

If we cross 200 KB gz total we should investigate code-splitting. Until then
it's not worth the complexity.

## Migration plan (if/when we go full)

1. ✅ Scaffold + result-card POC. (this PR)
2. Search form + filters (left rail) — biggest UI surface, port second.
3. Top tab bar + routing (`/v2/finder`, `/v2/optimizer`, etc.).
4. Watchlist / Pinned / Compare — share `<SystemTable>` component.
5. Map (canvas wrapped in one component, ~no rewrite needed).
6. Once parity hit: nginx flips root → v2; v1 lives at `/v1/` for one week
   as rollback insurance; then deleted.

Estimated effort end-to-end: 4–6 weeks part-time. Don't start until the
backend pipeline (grid/clusters) is rock-solid.
