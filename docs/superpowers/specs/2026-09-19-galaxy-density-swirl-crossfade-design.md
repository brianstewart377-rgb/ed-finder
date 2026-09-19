# Galaxy Density Swirl + Semantic-Zoom Cross-fade — design

Status: **spec** (2026-09-19). Map roadmap item #3 (density swirl + heatmap) folded
together with #2b (density→real-star cross-fade), for the `apps/web` Babylon galaxy map.

## Problem

The map shows no galaxy core/arms density, and the "heatmap does nothing." Root cause
(from the map investigation): the catalogue-density render pipeline
(`adapter.ts` `catalogueDensitySceneLayer` / `createCatalogueDensityMesh`, palette in
`catalogue-density.ts`, fed to a GlowLayer) is **complete and tested but only wired into
the Review Lab fixture** — never the product Explore view. `/api/map/heatmap` also serves
a **legacy-fallback** lane until the spatial pyramid publishes. Separately, the intended
#2b semantic-zoom cross-fade (density dominates zoomed out; real stars fade in as you zoom)
was never built.

## Goal

Wire the existing density pipeline into the product Explore view and add the #2b cross-fade,
**renderer-neutral** (Svelte fetches + owns policy, Babylon renders + applies per-frame).
The code lands now and is **inert while the endpoint returns `legacy-fallback`**; the swirl
and cross-fade activate **automatically** once the pyramid publishes — no further deploy.
Explicitly **do not** synthesize density from the legacy-fallback response.

## Non-goals

- No ED3D-style additive-point-sprite/bloom look upgrade (deferred; the current cell-mesh +
  GlowLayer look is reused — tune the look after real pyramid data is visible).
- No change to the pyramid build/publish or `/api/map/heatmap` server contract beyond an
  optional, additive tidy (below).
- No new colours from features (respects the locked no-feature-colours contract — density
  colour is derived in the adapter from counts).

## Architecture

Renderer-neutral split: **Svelte** fetches heatmap data, maps it to the payload, and owns
the cross-fade *policy* (the distance band). **Babylon** renders the density mesh and applies
the per-frame cross-fade *opacity* (distance changes every frame — a presentation concern).

### 1. Density source adapter — `apps/web/src/lib/spatial/galaxy-density-source.ts` (new)
- Calls the heatmap SDK via the generated facade (zoomed-out / overlap-band lane only).
- **Only when the response `source === 'pyramid'`**: map each cell →
  `CatalogueDensityPayload` — per-cell `index = floor((origin_*_ly − cellOriginLy)/cellSizeLy)`,
  `centroidLy` from `centroid_*_ly`, `systemCount` from `system_count`; top-level
  `generationId` / `pyramidVersion` / `level` / `cellSizeLy` / `cellOriginLy` / `boundsLy` /
  `coveredSystemCount`. Then `validateCatalogueDensityPayload` (fail-closed) and
  `createCatalogueDensityContribution`.
- When `source === 'legacy-fallback'` (or no pyramid): **return `null`** — never synthesize
  density from the rating-gated legacy lane (different cell semantics, no pyramid identity).

### 2. Overlay slot — `apps/web/src/lib/spatial/galaxy-overlays.ts`
- Add a `density` field to `GalaxyOverlayInput`.
- Add a `catalogue-density` id to `GALAXY_OVERLAY_ORDER` / `overlayById`, ordered **before**
  `catalogue-viewport-stars` (density is the base layer beneath stars).

### 3. ExploreWorkspace queries — `apps/web/src/lib/features/explore/ExploreWorkspace.svelte`
- Add a `createQuery` for the heatmap, **enabled across the zoomed-out lane and the overlap
  band** (complementing the existing `catalogueStars` query at ~L151).
- Extend the `catalogueStars` enable-condition so real stars also load **through the overlap
  band** (both datasets must be present to blend). Outside the band the existing
  gating is unchanged.
- Derive `densityContribution` from the source adapter; pass it plus a `crossFade` band config
  into `collectGalaxySpatialContributions({ …, density, crossFade })` (~L328).
- Replace the static "Known-system density" affordance (~L897) with the live cell count when a
  pyramid density layer is present.

### 4. Cross-fade (#2b)
- **Policy (Svelte):** a distance band `{ nearLy, farLy }` exposed as named constants, passed
  into the scene contributions. Defaults: `nearLy` = the camera distance at which
  `galaxyStarViewport` first yields real stars; `farLy` ≈ 2–3× `nearLy`. **Tunable** — the
  final values want real-data tuning once the swirl is visible.
- **Application (Babylon, per frame in `adapter.ts`):** given the live `camera.distanceLy`,
  compute `t = clamp((distanceLy − nearLy) / (farLy − nearLy), 0, 1)`, then set the
  `catalogue-density` layer opacity = `t` (full when far/zoomed-out) and the
  `catalogue-viewport-stars` layer opacity = `1 − t` (full when near/zoomed-in). Both layers
  render simultaneously inside the band; outside it, one is fully transparent.
- Keep the density GlowLayer contribution scaled by the same `t` so the glow fades with the
  layer.

### 5. Inert-until-publish behaviour
- While `/api/map/heatmap` returns `legacy-fallback`, the source adapter returns `null` → no
  `density` contribution → no `catalogue-density` layer → the cross-fade collapses to today's
  behaviour (stars only, gated as now). No visual change until the pyramid publishes; then the
  swirl + cross-fade appear automatically.

### Optional server tidy (additive, non-breaking) — `apps/api/src/routers/map.py`
- In the `pyramid` branch (~L336-351), expose the voxel-grid origin (`cellOriginLy`) and
  `covered_system_count` / `complete` so the client doesn't have to infer them. Optional; the
  client can derive `cellOriginLy` from cell origins if omitted.

## Contracts respected
- Density payload is **count-only**; colour is derived in the adapter (no feature colours).
- Renderer-neutral: Svelte never renders; Babylon never fetches or decides policy.
- Fail-closed: a malformed/pyramid-mismatched payload yields no layer, not a wrong render.

## Testing
- **Source adapter** (`galaxy-density-source.test.ts`): pyramid response → correct
  `CatalogueDensityPayload`; `legacy-fallback` → `null`; malformed payload → fail-closed
  (`null`, no throw to the caller).
- **Overlay order** (`galaxy-overlays.test.ts`): `catalogue-density` precedes
  `catalogue-viewport-stars` in `GALAXY_OVERLAY_ORDER`.
- **Cross-fade** (`adapter.test.ts`): for distances below `nearLy`, at midpoint, and above
  `farLy`, assert density/star layer opacities are `(0,1)`, `(0.5,0.5)`, `(1,0)`.
- **ExploreWorkspace** query-enable: heatmap query enabled zoomed-out + in-band; stars enabled
  in-band; neither errors when the endpoint returns legacy-fallback.
- **Visual acceptance**: the Cypress map / Review Lab visual lanes once real or fixture pyramid
  data is available (the Review Lab fixture already exercises the density mesh).

## Rollout / dependencies
- Lands behind no flag; inert until the pyramid publishes (gated on the F1 `system_search`
  rebuild → generation READY → governed pyramid publish, already in flight).
- Cross-fade thresholds are constants; expect one follow-up tuning pass after first real render.

## Out of scope / follow-ups
- ED3D additive-particle + bloom look upgrade.
- Star colour-by-spectral-class (separate — now unblocked by the Spansh data grant; needs the
  `SpectralClass` ingest so `/api/map/systems` returns `main_star_class`).
