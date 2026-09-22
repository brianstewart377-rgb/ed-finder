# Galaxy Density Swirl + Cross-fade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing (tested) catalogue-density pipeline into the product Explore view and add the density→real-star semantic-zoom cross-fade, renderer-neutral, inert until the spatial pyramid publishes.

**Architecture:** A new Svelte source adapter fetches `/api/map/heatmap`, maps a `source:'pyramid'` response into the existing `CatalogueDensityPayload` (deriving the fields the response omits), validates fail-closed, and builds the existing `createCatalogueDensityContribution`. A new `catalogue-density` overlay slot renders it beneath stars via the already-built Babylon mesh. The cross-fade lives in the Babylon adapter's `applyCameraState` choke-point: a distance-`t` ramp drives the density mesh alpha up and the star mesh alpha down.

**Tech Stack:** Svelte 5 runes + @tanstack/svelte-query + @hey-api generated client (frontend), Babylon.js 6.49 (renderer), vitest (tests).

## Global Constraints
- Renderer-neutral: Svelte fetches + owns policy; Babylon renders + applies per-camera-change opacity. Components import only the `$lib/api/client` facade (never the generated SDK).
- **Map ONLY `source === 'pyramid'`**; on `source === 'legacy-fallback'` the source adapter returns `null` (never synthesize density from the legacy lane — different cell shape: `cx,cy,cz,n,avg_score,max_score`).
- No feature colours: density colour is derived in the adapter (`catalogueDensityHeatColour`); do not add colour inputs.
- Inert-until-publish: while the endpoint returns legacy-fallback, `null` contribution → no `catalogue-density` layer → behaviour is exactly today's.
- Fail-closed: a malformed/pyramid-mismatched payload yields `null` (no layer), never a wrong render.
- **Spec concretizations (from code facts):** (1) `galaxyStarViewport` returns a viewport for any non-null camera (stars always load — a wide 8,000-star sample above 7,000 ly, focus detail below), so the cross-fade band is concrete distances, not a stars-on/off threshold; defaults `nearLy = 8_000`, `farLy = 40_000` (tunable). (2) Cross-fade is applied in `adapter.ts` `applyCameraState` (lines ~1772-1797), not a per-frame loop. (3) The star material currently has no explicit `.alpha` — the cross-fade adds one.
- Exact existing names: types in `apps/web/src/lib/spatial/galaxy-density.ts`; renderer in `apps/web/src/lib/spatial/babylon/catalogue-density.ts`; SDK fn is `mapHeatmapApiMapHeatmapGet` (no `mapHeatmap`); its generated response is `200: unknown` (hand-author the interface).

---

### Task 1: Heatmap facade + pyramid response type

**Files:**
- Modify: `apps/web/src/lib/api/client.ts` (add near `getCatalogueViewportSystems`, ~L421-451)
- Test: `apps/web/src/lib/api/client.test.ts` (create if absent; else append)

**Interfaces:**
- Consumes: generated `mapHeatmapApiMapHeatmapGet` from `./generated/sdk.gen`.
- Produces:
  ```ts
  export interface MapHeatmapPyramidCell {
    origin_x_ly: number; origin_y_ly: number; origin_z_ly: number;
    centroid_x_ly: number; centroid_y_ly: number; centroid_z_ly: number;
    system_count: number; representative_system_id64: number | string;
  }
  export interface MapHeatmapPyramidResponse {
    source: 'pyramid';
    generation_id: string; spatial_generation_id: string; spatial_pyramid_version: string;
    source_system_count: number; coverage_at: string | null;
    level: number; cell_size_ly: number; voxel_size: number;
    bounds: { min_x: number|null; max_x: number|null; min_y: number|null; max_y: number|null; min_z: number|null; max_z: number|null };
    cells: MapHeatmapPyramidCell[]; count: number; max_cells: number; truncated: boolean;
  }
  export type MapHeatmapResponse = MapHeatmapPyramidResponse | { source: 'legacy-fallback'; [k: string]: unknown };
  export const getMapHeatmap: (query: { voxel_size?: number; min_systems?: number; max_cells?: number }, signal?: AbortSignal) => Promise<MapHeatmapResponse>;
  ```

- [ ] **Step 1: Write the failing test**
```ts
import { describe, expect, it, vi } from 'vitest';
vi.mock('$lib/api/generated/sdk.gen', () => ({
  mapHeatmapApiMapHeatmapGet: vi.fn(async () => ({ data: { source: 'pyramid', cells: [] } })),
}));
import { getMapHeatmap } from './client';
import * as sdk from '$lib/api/generated/sdk.gen';
describe('getMapHeatmap', () => {
  it('calls the heatmap SDK with query + throwOnError and returns data', async () => {
    const out = await getMapHeatmap({ voxel_size: 500, max_cells: 40000 });
    expect(out).toMatchObject({ source: 'pyramid' });
    expect(vi.mocked(sdk.mapHeatmapApiMapHeatmapGet)).toHaveBeenCalledWith(
      expect.objectContaining({ query: { voxel_size: 500, max_cells: 40000 }, throwOnError: true }),
    );
  });
});
```

- [ ] **Step 2: Run to verify it fails** — `cd apps/web && pnpm exec vitest run src/lib/api/client.test.ts` → FAIL (`getMapHeatmap` not exported).

- [ ] **Step 3: Implement** — in `client.ts`, add the interfaces above and:
```ts
import { mapHeatmapApiMapHeatmapGet } from './generated/sdk.gen';
export const getMapHeatmap = async (
  query: { voxel_size?: number; min_systems?: number; max_cells?: number },
  signal?: AbortSignal,
): Promise<MapHeatmapResponse> =>
  (await mapHeatmapApiMapHeatmapGet({ query, throwOnError: true, signal })).data as MapHeatmapResponse;
```

- [ ] **Step 4: Run to verify it passes** — same command → PASS.
- [ ] **Step 5: Commit** — `git add apps/web/src/lib/api/client.ts apps/web/src/lib/api/client.test.ts && git commit -m "feat(web): map heatmap facade + pyramid response type"`

---

### Task 2: Density source adapter

**Files:**
- Create: `apps/web/src/lib/spatial/galaxy-density-source.ts`
- Test: `apps/web/src/lib/spatial/galaxy-density-source.test.ts`

**Interfaces:**
- Consumes: `getMapHeatmap`, `MapHeatmapResponse`, `MapHeatmapPyramidResponse` (Task 1); from `./galaxy-density`: `CATALOGUE_DENSITY_SCHEMA_VERSION`, `validateCatalogueDensityPayload`, `createCatalogueDensityContribution`, type `CatalogueDensityPayload`.
- Produces:
  - `export function mapHeatmapToDensityPayload(res: MapHeatmapResponse): CatalogueDensityPayload | null` — `null` unless `res.source === 'pyramid'`; wraps `validateCatalogueDensityPayload` and returns `null` if it throws.
  - `export async function loadGalaxyDensityContribution(query, revision: number, signal?): Promise<SpatialContribution | null>` — fetches + maps + `createCatalogueDensityContribution`; `null` on legacy/empty/failure.

Mapping (pyramid → payload), deriving omitted fields:
- `cellOriginLy` = `{ x: bounds.min_x ?? min(origin_x_ly), y: bounds.min_y ?? min(origin_y_ly), z: bounds.min_z ?? min(origin_z_ly) }`.
- each cell: `index = { x: Math.round((origin_x_ly - cellOriginLy.x)/cell_size_ly), y: …, z: … }`, `centroidLy = { x: centroid_x_ly, y: centroid_y_ly, z: centroid_z_ly }`, `systemCount = system_count`.
- `boundsLy = { min: {x:bounds.min_x??…, …}, max: {x:bounds.max_x??…, …} }` (fall back to min/max of cell origins ± cell_size_ly if a bound is null).
- `sourceSystemCount = source_system_count`; `coveredSystemCount = sum(system_count)`; `coverageAsOf = coverage_at ?? new Date(0).toISOString()`; `complete = !truncated`; `schemaVersion = CATALOGUE_DENSITY_SCHEMA_VERSION`; `generationId = generation_id`; `pyramidVersion = spatial_pyramid_version`; `level`, `cellSizeLy = cell_size_ly`.

- [ ] **Step 1: Write the failing test**
```ts
import { describe, expect, it } from 'vitest';
import { mapHeatmapToDensityPayload } from './galaxy-density-source';
const pyramid = {
  source: 'pyramid' as const, generation_id: 'g1', spatial_generation_id: 's1',
  spatial_pyramid_version: 'v1', source_system_count: 3, coverage_at: '2026-09-19T00:00:00Z',
  level: 3, cell_size_ly: 100, voxel_size: 100,
  bounds: { min_x: 0, max_x: 100, min_y: 0, max_y: 100, min_z: 0, max_z: 100 },
  cells: [
    { origin_x_ly: 0, origin_y_ly: 0, origin_z_ly: 0, centroid_x_ly: 50, centroid_y_ly: 50, centroid_z_ly: 50, system_count: 2, representative_system_id64: 1 },
    { origin_x_ly: 100, origin_y_ly: 0, origin_z_ly: 0, centroid_x_ly: 150, centroid_y_ly: 50, centroid_z_ly: 50, system_count: 1, representative_system_id64: 2 },
  ],
  count: 2, max_cells: 40000, truncated: false,
};
describe('mapHeatmapToDensityPayload', () => {
  it('maps a pyramid response into a validated payload', () => {
    const p = mapHeatmapToDensityPayload(pyramid)!;
    expect(p.generationId).toBe('g1');
    expect(p.cellSizeLy).toBe(100);
    expect(p.coveredSystemCount).toBe(3);
    expect(p.complete).toBe(true);
    expect(p.cells).toHaveLength(2);
    expect(p.cells[1].index).toEqual({ x: 1, y: 0, z: 0 });
  });
  it('returns null on legacy-fallback', () => {
    expect(mapHeatmapToDensityPayload({ source: 'legacy-fallback', cells: [] })).toBeNull();
  });
  it('returns null (fail-closed) on a malformed pyramid payload', () => {
    expect(mapHeatmapToDensityPayload({ ...pyramid, cell_size_ly: 0 })).toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify it fails** — `pnpm exec vitest run src/lib/spatial/galaxy-density-source.test.ts` → FAIL (module missing).

- [ ] **Step 3: Implement** `galaxy-density-source.ts`:
```ts
import type { SpatialContribution } from './contracts';
import {
  CATALOGUE_DENSITY_SCHEMA_VERSION,
  createCatalogueDensityContribution,
  validateCatalogueDensityPayload,
  type CatalogueDensityPayload,
} from './galaxy-density';
import { getMapHeatmap, type MapHeatmapResponse, type MapHeatmapPyramidResponse } from '$lib/api/client';

function minBy(cells: MapHeatmapPyramidResponse['cells'], k: 'origin_x_ly'|'origin_y_ly'|'origin_z_ly') {
  return cells.reduce((m, c) => Math.min(m, c[k]), Number.POSITIVE_INFINITY);
}

export function mapHeatmapToDensityPayload(res: MapHeatmapResponse): CatalogueDensityPayload | null {
  if (res.source !== 'pyramid') return null;
  const cells = res.cells ?? [];
  if (!cells.length) return null;
  const originX = res.bounds?.min_x ?? minBy(cells, 'origin_x_ly');
  const originY = res.bounds?.min_y ?? minBy(cells, 'origin_y_ly');
  const originZ = res.bounds?.min_z ?? minBy(cells, 'origin_z_ly');
  try {
    return validateCatalogueDensityPayload({
      schemaVersion: CATALOGUE_DENSITY_SCHEMA_VERSION,
      generationId: res.generation_id,
      pyramidVersion: res.spatial_pyramid_version,
      level: res.level,
      cellSizeLy: res.cell_size_ly,
      cellOriginLy: { x: originX, y: originY, z: originZ },
      boundsLy: {
        min: { x: res.bounds.min_x ?? originX, y: res.bounds.min_y ?? originY, z: res.bounds.min_z ?? originZ },
        max: { x: res.bounds.max_x ?? originX + res.cell_size_ly, y: res.bounds.max_y ?? originY + res.cell_size_ly, z: res.bounds.max_z ?? originZ + res.cell_size_ly },
      },
      sourceSystemCount: res.source_system_count,
      coveredSystemCount: cells.reduce((n, c) => n + c.system_count, 0),
      coverageAsOf: res.coverage_at ?? new Date(0).toISOString(),
      complete: !res.truncated,
      cells: cells.map((c) => ({
        index: {
          x: Math.round((c.origin_x_ly - originX) / res.cell_size_ly),
          y: Math.round((c.origin_y_ly - originY) / res.cell_size_ly),
          z: Math.round((c.origin_z_ly - originZ) / res.cell_size_ly),
        },
        centroidLy: { x: c.centroid_x_ly, y: c.centroid_y_ly, z: c.centroid_z_ly },
        systemCount: c.system_count,
      })),
    });
  } catch {
    return null;
  }
}

export async function loadGalaxyDensityContribution(
  query: { voxel_size?: number; min_systems?: number; max_cells?: number },
  revision: number,
  signal?: AbortSignal,
): Promise<SpatialContribution | null> {
  const payload = mapHeatmapToDensityPayload(await getMapHeatmap(query, signal));
  return payload ? createCatalogueDensityContribution(payload, revision) : null;
}
```

- [ ] **Step 4: Run to verify it passes** — same command → PASS.
- [ ] **Step 5: Commit** — `git add apps/web/src/lib/spatial/galaxy-density-source.* && git commit -m "feat(map): pyramid heatmap -> density contribution source (fail-closed)"`

---

### Task 3: Density overlay slot

**Files:**
- Modify: `apps/web/src/lib/spatial/galaxy-overlays.ts` (L10-42)
- Test: `apps/web/src/lib/spatial/galaxy-overlays.test.ts`

**Interfaces:** Produces an extended `GalaxyOverlayInput` with `density: SpatialContribution | null` and `'catalogue-density'` in `GALAXY_OVERLAY_ORDER` before `'catalogue-viewport-stars'`.

- [ ] **Step 1: Write the failing test**
```ts
import { describe, expect, it } from 'vitest';
import { GALAXY_OVERLAY_ORDER } from './galaxy-overlays';
it('orders catalogue-density beneath catalogue stars', () => {
  const order = GALAXY_OVERLAY_ORDER as readonly string[];
  expect(order).toContain('catalogue-density');
  expect(order.indexOf('catalogue-density')).toBeLessThan(order.indexOf('catalogue-viewport-stars'));
});
```

- [ ] **Step 2: Run to verify it fails** — FAIL (id absent).
- [ ] **Step 3: Implement** — in `galaxy-overlays.ts`: add `'catalogue-density'` to `GALAXY_OVERLAY_ORDER` immediately before `'catalogue-viewport-stars'`; add `density: SpatialContribution | null;` to `GalaxyOverlayInput`; add `'catalogue-density': 'density',` to `overlayById`. (`collectGalaxySpatialContributions` needs no change — it iterates the order.)
- [ ] **Step 4: Run to verify it passes** — PASS. Also run existing `galaxy-overlays.test.ts` to confirm no regression.
- [ ] **Step 5: Commit** — `git commit -am "feat(map): catalogue-density overlay slot beneath stars"`

---

### Task 4: Cross-fade in the Babylon adapter

**Files:**
- Create: `apps/web/src/lib/spatial/galaxy-density-crossfade.ts` (band + ramp — shared, neutral policy module)
- Modify: `apps/web/src/lib/spatial/babylon/adapter.ts` (star material ~L1282-1289; `applyCameraState` ~L1772-1797; keep refs to density mesh + star mesh)
- Test: `apps/web/src/lib/spatial/galaxy-density-crossfade.test.ts` + assertion in `adapter.test.ts`

**Interfaces:**
- Produces `galaxy-density-crossfade.ts`:
  ```ts
  export const DENSITY_CROSSFADE_NEAR_LY = 8_000;
  export const DENSITY_CROSSFADE_FAR_LY = 40_000;
  export function densityCrossfadeT(distanceLy: number, nearLy = DENSITY_CROSSFADE_NEAR_LY, farLy = DENSITY_CROSSFADE_FAR_LY): number; // clamp((d-near)/(far-near),0,1)
  ```
- Consumed by the adapter: density mesh `material.alpha = 0.9 * t`; star mesh `material.alpha = 1 - t`.

- [ ] **Step 1: Write the failing test**
```ts
import { describe, expect, it } from 'vitest';
import { densityCrossfadeT, DENSITY_CROSSFADE_NEAR_LY, DENSITY_CROSSFADE_FAR_LY } from './galaxy-density-crossfade';
it('ramps density in as the camera zooms out', () => {
  expect(densityCrossfadeT(DENSITY_CROSSFADE_NEAR_LY - 1)).toBe(0);       // zoomed in -> density off
  expect(densityCrossfadeT((DENSITY_CROSSFADE_NEAR_LY + DENSITY_CROSSFADE_FAR_LY) / 2)).toBeCloseTo(0.5, 5);
  expect(densityCrossfadeT(DENSITY_CROSSFADE_FAR_LY + 1)).toBe(1);        // zoomed out -> density full
});
```

- [ ] **Step 2: Run to verify it fails** — FAIL (module missing).
- [ ] **Step 3: Implement** the module:
```ts
export const DENSITY_CROSSFADE_NEAR_LY = 8_000;
export const DENSITY_CROSSFADE_FAR_LY = 40_000;
export function densityCrossfadeT(distanceLy: number, nearLy = DENSITY_CROSSFADE_NEAR_LY, farLy = DENSITY_CROSSFADE_FAR_LY): number {
  if (farLy <= nearLy) return distanceLy >= farLy ? 1 : 0;
  return Math.min(1, Math.max(0, (distanceLy - nearLy) / (farLy - nearLy)));
}
```
Then in `adapter.ts`:
- After building the star material (~L1289) add `starMaterial.alpha = 1;` and `starMaterial.transparencyMode = Material.MATERIAL_ALPHABLEND;` (so alpha < 1 blends).
- Store the density mesh + star mesh + their materials on `product` (or capture in the `applyCameraState` closure) so they're reachable.
- In `applyCameraState` (after the existing star-scale recompute at ~L1779) add:
  ```ts
  const t = densityCrossfadeT(camera.distanceLy);
  if (densityMesh?.material) (densityMesh.material as StandardMaterial).alpha = 0.9 * t;
  if (starMesh?.material) (starMesh.material as StandardMaterial).alpha = 1 - t;
  ```
  Import `densityCrossfadeT` from `../galaxy-density-crossfade`.

- [ ] **Step 4: Run to verify it passes** — run the crossfade test (PASS) + add an `adapter.test.ts` case that builds the scene with a density layer, calls the adapter's camera-apply at `distanceLy` below-near / mid / above-far, and asserts `densityMesh.material.alpha` ≈ `0 / 0.45 / 0.9` and `starMesh.material.alpha` ≈ `1 / 0.5 / 0`. Run `pnpm exec vitest run src/lib/spatial/babylon/adapter.test.ts src/lib/spatial/galaxy-density-crossfade.test.ts` → PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(map): density<->star semantic-zoom cross-fade in applyCameraState"`

---

### Task 5: Wire into ExploreWorkspace

**Files:**
- Modify: `apps/web/src/lib/features/explore/ExploreWorkspace.svelte` (heatmap query near the `commanderVisits` pattern ~L183-209; `collectGalaxySpatialContributions` call ~L328-333; revision sum ~L317-323; density affordance ~L897)
- Test: extend `apps/web/src/lib/features/explore/ExploreWorkspace.*test*` (mirror the existing mock pattern; mock `$lib/api/client` `getMapHeatmap`)

**Interfaces:** Consumes `loadGalaxyDensityContribution` (Task 2), the extended `collectGalaxySpatialContributions` input (Task 3).

- [ ] **Step 1: Write the failing test** — mock `getMapHeatmap` to resolve a pyramid response; render the workspace zoomed out (default `distanceLy: 118_000`); assert the heatmap query fired (i.e. `getMapHeatmap` called) and that a density contribution reaches the scene (assert the live cell-count affordance shows the cell count rather than the static "Known-system density" text). Add a second case: `getMapHeatmap` resolves `{ source: 'legacy-fallback' }` → no density contribution, no error, affordance stays static.

- [ ] **Step 2: Run to verify it fails.**
- [ ] **Step 3: Implement**:
  - Add a `createQuery` mirroring `commanderVisits`:
    ```ts
    const heatmap = createQuery(() => ({
      queryKey: ['map-heatmap', streamCamera?.distanceLy ?? 0],
      queryFn: ({ signal }) => getMapHeatmap({ voxel_size: Math.max(200, Math.round((streamCamera?.distanceLy ?? 118_000) / 200)), max_cells: 40_000 }, signal),
      enabled: (streamCamera?.distanceLy ?? 0) >= DENSITY_CROSSFADE_NEAR_LY,
      staleTime: 60_000,
      placeholderData: (p) => p,
    }));
    ```
    (Enabled across the zoomed-out + overlap band; below `nearLy` density is fully faded so no fetch needed.)
  - `const densityContribution = $derived(heatmap.data ? mapHeatmapToDensityPayload(heatmap.data) ? createCatalogueDensityContribution(mapHeatmapToDensityPayload(heatmap.data)!, heatmap.dataUpdatedAt) : null : null);` — or call `loadGalaxyDensityContribution` in an effect; simplest is a `$derived` using `mapHeatmapToDensityPayload(heatmap.data)` once. (Export a `densityContributionFrom(data, revision)` helper from the source module to avoid double-mapping.)
  - Add `density: densityContribution` to the `collectGalaxySpatialContributions({...})` object (~L331) and add `+ (heatmap.dataUpdatedAt ?? 0)` to the revision sum (~L317-323).
  - Replace the static density affordance (~L897) with the live count when `densityContribution` is present.
  - `catalogueStars` already loads for any camera (wide sample), so no enable change is needed for the overlap; leave it.
- [ ] **Step 4: Run to verify it passes** — vitest for the workspace test + `pnpm check` (0 errors).
- [ ] **Step 5: Commit** — `git commit -am "feat(map): wire density swirl + cross-fade into Explore"`

---

## Notes for the executor
- To avoid double-mapping in Task 5, add `export function densityContributionFrom(data: MapHeatmapResponse | undefined, revision: number): SpatialContribution | null` to `galaxy-density-source.ts` (maps + creates, or returns null) and use it in the `$derived`.
- Cross-fade band (`8_000`/`40_000` ly) is a first tunable guess — expect one visual-tuning pass once real pyramid data renders (Cypress map / Review Lab visual lanes are the acceptance gate; the Review Lab fixture already exercises the density mesh).
- Everything is inert until `/api/map/heatmap` returns `source:'pyramid'` (after the F1 rebuild → generation READY → governed pyramid publish).
