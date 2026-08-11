# Map Glow + Procedural Body Thumbnails Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Two bounded frontend visual wins — (#2) soft glowing stars on the R3F galaxy map, and (#3) small WebGL procedural planet thumbnails per body in the system-detail panel.

**Architecture:** #2 is a dependency-free swap of the flat `<pointsMaterial>` on the map's *star* point layers for one shared soft-glow point `ShaderMaterial` (radial `gl_PointCoord` falloff + additive blending). #3 adds a shared offscreen Three.js renderer that draws a parametric planet (typed by ED `body_type`) once per unique body, caches the result as a data-URL, and shows it as an `<img>` in each body row. Both reuse the existing `three` 0.185 / `@react-three/fiber` 9.7 stack — **no new dependencies.**

**Tech Stack:** React 19, TypeScript, `@react-three/fiber` 9.7, `three` 0.185, Vite, Vitest.

## Global Constraints
- **No new dependencies.** #2 is a hand-written shader; #3 uses core `three` (WebGLRenderTarget → data-URL). (A future Bloom pass via `@react-three/postprocessing` is explicitly out of scope here.)
- **Frontend gates must pass:** `yarn typecheck`, `yarn lint`, `yarn knip --files`, `yarn test:map` + `yarn test`, `yarn build`.
- **Map is production, "in observation."** Changes must be visually revertable and must not break existing `map-foundation` tests. This is sanctioned *bounded polish*; keep it clean and self-contained.
- **Do not hand-edit `src/types/api.gen.ts`** — `BodyModel` fields come from there.
- Follow existing `features/map-foundation/` R3F idioms (functional components, `useMemo` for buffers).
- **The score heatmap layer is NOT a star layer — do not apply glow to it.** Glow applies to system dots + decorative starfield only.

---

## Task 1: #2 — Soft-glow star points (map), dependency-free

**Files:**
- Create: `frontend/src/features/map-foundation/glowPointsMaterial.ts` (shared material factory + GLSL)
- Create: `frontend/src/features/map-foundation/glowPointsMaterial.test.ts`
- Modify: `frontend/src/features/map-foundation/SceneContents.tsx` (system dot layers)
- Modify: `frontend/src/features/map-foundation/GalaxyBackdrop.tsx` (18k decorative stars)
- Modify: `frontend/src/features/map-foundation/SceneDecorations.tsx` (decorative point stars)

**Interfaces:**
- Produces: `makeGlowPointsMaterial({ color?, size, sizeAttenuation?, vertexColors? }): THREE.ShaderMaterial` — a soft round additive point. Consumed by the three map files above via `<primitive object={material} attach="material" />` (or a small `<glowPoints>`-style wrapper), replacing `<pointsMaterial>`.

- [ ] **Step 1: Write the material factory + GLSL**

```ts
// glowPointsMaterial.ts
import * as THREE from 'three';

const VERT = /* glsl */`
  uniform float uSize;
  uniform bool uAttenuate;
  attribute vec3 color;
  varying vec3 vColor;
  void main() {
    vColor = color;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = uSize * (uAttenuate ? (300.0 / -mv.z) : 1.0);
    gl_Position = projectionMatrix * mv;
  }`;

const FRAG = /* glsl */`
  uniform vec3 uColor;
  uniform bool uUseVertexColor;
  varying vec3 vColor;
  void main() {
    float d = length(gl_PointCoord - vec2(0.5));
    float alpha = smoothstep(0.5, 0.0, d);   // soft round core->edge
    alpha = pow(alpha, 1.6);                  // tighter core, wide halo
    if (alpha < 0.01) discard;
    vec3 c = uUseVertexColor ? vColor : uColor;
    gl_FragColor = vec4(c, alpha);
  }`;

export function makeGlowPointsMaterial(opts: {
  color?: THREE.ColorRepresentation; size: number;
  sizeAttenuation?: boolean; vertexColors?: boolean;
}): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    uniforms: {
      uColor: { value: new THREE.Color(opts.color ?? '#ffffff') },
      uSize: { value: opts.size },
      uAttenuate: { value: opts.sizeAttenuation ?? true },
      uUseVertexColor: { value: opts.vertexColors ?? false },
    },
    vertexShader: VERT, fragmentShader: FRAG,
    transparent: true, blending: THREE.AdditiveBlending,
    depthWrite: false, depthTest: false,
  });
}
```

- [ ] **Step 2: Test the factory** (jsdom, no real GL needed)

```ts
// glowPointsMaterial.test.ts
import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import { makeGlowPointsMaterial } from './glowPointsMaterial';

describe('makeGlowPointsMaterial', () => {
  it('is an additive, non-depth-writing transparent points material', () => {
    const m = makeGlowPointsMaterial({ size: 8 });
    expect(m).toBeInstanceOf(THREE.ShaderMaterial);
    expect(m.blending).toBe(THREE.AdditiveBlending);
    expect(m.depthWrite).toBe(false);
    expect(m.transparent).toBe(true);
    expect(m.fragmentShader).toContain('gl_PointCoord');
  });
  it('honors vertexColors + size uniforms', () => {
    const m = makeGlowPointsMaterial({ size: 12, vertexColors: true });
    expect(m.uniforms.uUseVertexColor.value).toBe(true);
    expect(m.uniforms.uSize.value).toBe(12);
  });
});
```
Run: `yarn vitest run src/features/map-foundation/glowPointsMaterial.test.ts` → PASS.

- [ ] **Step 3: Swap into the star layers.** In `SceneContents.tsx`, replace each system-dot `<pointsMaterial …>` (background/guaranteed/selected — NOT the heatmap `<pointsMaterial>` and NOT the aggregate-hull `<lineBasicMaterial>`) with the glow material via a `useMemo` + `<primitive object={mat} attach="material" />`, preserving each layer's existing `color` and `attenuatedPointSize(...)` size. Do the same for `GalaxyBackdrop.tsx` (use `vertexColors:true` since it has a color buffer) and the `SceneDecorations.tsx` point-star material(s). Keep `emphasizedSystems` marker rings as-is.

- [ ] **Step 4: Run the map suite + typecheck.** `yarn test:map` and `yarn typecheck` → PASS (existing `ProductionMapTab`/`GalacticMap` tests must stay green — they assert structure, not pixels).

- [ ] **Step 5: Visual check + commit.** Local preview (`VITE_STAGE26E_PRODUCTION_MAP=enabled yarn dev`): stars are soft round glows, not squares; heatmap unchanged. Commit `feat(map): soft-glow star points`.

---

## Task 2: #3 — WebGL procedural body thumbnails (system-detail)

**Files:**
- Create: `frontend/src/features/system-detail/body-thumbnail/bodyThumbnailParams.ts` (body_type/flags → planet params) + `.test.ts`
- Create: `frontend/src/features/system-detail/body-thumbnail/renderBodyThumbnail.ts` (shared offscreen renderer → data-URL, cached)
- Create: `frontend/src/features/system-detail/body-thumbnail/BodyThumbnail.tsx` + `.test.tsx`
- Modify: `frontend/src/features/system-detail/SystemBodiesAndStationsSections.tsx` (add a leading thumbnail cell to each body row in `BodiesSection`)

**Interfaces:**
- `bodyThumbnailParams(body: SystemBody): PlanetParams` — pure mapping (base color, roughness/noise, `hasAtmosphere`, `hasRings`, `isStar`, `emissive`) keyed by `body_type` + `is_water_world`/`is_ammonia_world`/`is_earth_like`/`is_landable`/`spectral_class`.
- `renderBodyThumbnail(params: PlanetParams, seed: number, px = 72): string` — returns a cached PNG data-URL; lazily creates ONE hidden `WebGLRenderer` + reusable sphere; renders once per cache key `${type}:${seed}` and memoizes. Falls back to `''` (→ CSS disc) if WebGL is unavailable (e.g. jsdom/tests).
- `<BodyThumbnail body={body} />` — 36px `<img>` (or CSS-gradient disc fallback).

- [ ] **Step 1: Write the param mapping + test.** Map each ED `body_type`/flag combo to a `PlanetParams` (rocky→brown noise; High metal content→dark metallic; Metal-rich→bright metallic; Icy→pale blue-white; Rocky ice→grey-blue; lava/volcanic→dark+emissive-cracks; Water world→blue+white cloud; Ammonia→amber; Earth-like→blue-green+cloud; Gas giant classes→banded, `hasRings` heuristic; Star→emissive by `spectral_class` via the blackbody ramp). Test: a few representative bodies produce the expected `isStar`/`hasRings`/base-color-family.

- [ ] **Step 2: Write the offscreen renderer** — one module-level lazy `WebGLRenderer({ alpha:true, antialias:true, preserveDrawingBuffer:true })` at `px`×`px`, an `IcosahedronGeometry` sphere + a `ShaderMaterial` driven by `PlanetParams` (fbm noise surface, simple lambert + terminator, banded flow for gas giants, additive rim for atmosphere, a `RingGeometry` when `hasRings`, emissive for stars). Render once → `renderer.domElement.toDataURL('image/png')` → store in a `Map<string,string>` cache. Guard: if `WebGLRenderingContext` is absent (tests), return `''`.

- [ ] **Step 3: `<BodyThumbnail>` component + test.** Calls `bodyThumbnailParams` + `renderBodyThumbnail`; renders `<img width=36 height=36>` when a data-URL exists, else a typed CSS radial-gradient disc (so tests + no-WebGL environments still show *something* deterministic). Test (jsdom, WebGL absent): renders the fallback disc with a `data-body-thumb` attr and doesn't throw.

- [ ] **Step 4: Wire into `BodiesSection`.** Add a leading `<td>` with `<BodyThumbnail body={body} />` to each body `<tr>` (and a header cell). Keep the table layout/tests intact.

- [ ] **Step 5: Gates + commit.** `yarn typecheck`, `yarn lint`, `yarn knip --files`, `yarn test` (system-detail suite) → PASS. Commit `feat(system-detail): procedural body thumbnails`.

---

## Final verification (both tasks)
- [ ] `yarn typecheck && yarn lint && yarn knip --files` clean.
- [ ] `yarn test:ci` (the split suite CI runs) green.
- [ ] `yarn build` succeeds.
- [ ] Open PR(s) (Task 1 and Task 2 can be separate PRs — Task 1 is lower-risk); watch checks incl. Review Lab; self-review; merge on green.
- [ ] Production deploy is a **separate owner-approved step** (frontend deploy sequence ends with `docker compose restart nginx`) — not part of the merge.

## Self-review
- **Coverage:** Task 1 = #2 (glow) on star layers only; Task 2 = #3 (WebGL thumbnails) in bodies table. Both dependency-free.
- **Placeholder scan:** shader + factory + test code are literal; the offscreen-renderer body (Task 2 Step 2) is described precisely rather than fully quoted because the exact shader is iterated during implementation against the visual result — the interface + guards are pinned.
- **Risk:** the WebGL-absent guard (Task 2) keeps jsdom tests green; the heatmap-exclusion note (Task 1) prevents recoloring the data layer.
