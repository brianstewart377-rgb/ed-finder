# Split R3FMapFoundation.tsx Into Scene-Concern Files Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Shrink `frontend/src/features/map-foundation/R3FMapFoundation.tsx` from 1663 lines to roughly 1000 by extracting its self-contained galaxy-backdrop, scene-decoration, and scene-content-composer concerns into three new files, plus two small pure-math additions to the existing `camera.ts`, with zero logic changes.

**Architecture:** Pure code movement, no logic changes. `camera.ts` (existing, currently dependency-free pure math) gains `cameraDistanceForView` and `attenuatedPointSize`. `GalaxyBackdrop.tsx` and `SceneDecorations.tsx` (new) each own one rendering concern and depend only on `camera.ts` (the latter) or nothing (the former). `SceneContents.tsx` (new) owns the R3F-context bridge components, the main per-frame scene composer, and the camera/label projection math, and imports from `camera.ts`, `GalaxyBackdrop.tsx`, and `SceneDecorations.tsx`. `R3FMapFoundation.tsx` keeps its exported component, all keyboard/pointer physics state (NOT extracted — see Global Constraints), and the final JSX render, now importing what it needs from the three new files. This is the live production map renderer (Stage 26E cutover complete, in observation — see `docs/superpowers/specs/2026-08-06-split-r3f-map-foundation-design.md` for full context) so verification in the final task is more thorough than prior items in this series: manual interaction testing (pan/zoom/tilt/select), not just a static render check.

**Tech Stack:** Frontend only (Vite + React 19 + TS 5, React Three Fiber, Three.js, `frontend/`).

## Global Constraints

- No function/component body changes — every line moves verbatim from the current `frontend/src/features/map-foundation/R3FMapFoundation.tsx` (read it before starting; it is the source of truth for every implementation. Current file is 1663 lines. Line numbers below refer to this file as it exists before this plan's changes — re-verify a cited range's content matches its description before moving it, in case something shifted).
- The keyboard/pointer-physics block (current lines 997-1663 except the final JSX return) and the `export function R3FMapFoundation(...)` signature are NOT restructured — they stay in `R3FMapFoundation.tsx`, moved verbatim with only their internal references to now-imported symbols changing (e.g. `SceneContents` becomes an import instead of a same-file reference). Do not convert this block into a custom hook or otherwise restructure it — that is explicitly out of scope (see the design doc's Decision section).
- Every new file uses `import * as THREE from 'three'` (matching the existing file's namespace-import style), not named imports from `'three'`.
- No new file introduces a default export; match the codebase's existing named-export convention.
- `R3FMapFoundation.test.tsx` (589 lines, existing, not modified by this plan) must continue to pass unmodified — it tests `R3FMapFoundation` as a black box via its exported component and `data-*` attribute contract, and does not import any of the moved internals directly (verify this in Task 5 Step 1 before assuming it).

---

### Task 1: Add `cameraDistanceForView` and `attenuatedPointSize` to `camera.ts`

**Files:**
- Modify: `frontend/src/features/map-foundation/camera.ts`
- Reference (read, do not modify yet): `frontend/src/features/map-foundation/R3FMapFoundation.tsx`

**Interfaces:**
- Consumes: nothing new — both functions are pure, and `camera.ts` already imports `CameraState` (from the map-scene-contract artifact) and `ViewportSize` (from `./types`), which is all either function needs
- Produces: `export function cameraDistanceForView(camera: CameraState, size: ViewportSize): number` and `export function attenuatedPointSize(zoom: number, pixels: number): number` — Task 4 (`SceneContents.tsx`) and Task 3 (`SceneDecorations.tsx`) import both from `./camera`

- [ ] **Step 1: Add both functions**

Move verbatim from `R3FMapFoundation.tsx` lines 135-141 (`cameraDistanceForView`) and 143-145 (`attenuatedPointSize`). Append both to the end of `camera.ts` (after `zoomCamera`, the current last export). `cameraDistanceForView` references `CAMERA_VIEWPORT_HEIGHT_RATIO`, which `camera.ts` already defines and exports at its own line 7 — no new import needed for either function.

```typescript
export function cameraDistanceForView(camera: CameraState, size: ViewportSize): number {
  const visibleHeight = Math.max(
    20,
    camera.zoom * size.height * CAMERA_VIEWPORT_HEIGHT_RATIO,
  );
  return visibleHeight / (2 * Math.tan((42 * Math.PI / 180) / 2));
}

export function attenuatedPointSize(zoom: number, pixels: number): number {
  return Math.max(0.12, zoom * pixels * 0.78);
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && yarn typecheck`
Expected: passes with no errors (these are pure additions with no new external dependencies).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/map-foundation/camera.ts
git commit -m "Add cameraDistanceForView and attenuatedPointSize to camera.ts

Pure zoom/viewport math extracted verbatim from R3FMapFoundation.tsx
ahead of the wider scene-concern split. No behavior change."
```

---

### Task 2: Create `GalaxyBackdrop.tsx`

**Files:**
- Create: `frontend/src/features/map-foundation/GalaxyBackdrop.tsx`
- Reference (read, do not modify yet): `frontend/src/features/map-foundation/R3FMapFoundation.tsx`

**Interfaces:**
- Consumes: nothing from this plan's other tasks
- Produces: exported `GALAXY_CENTER`, `GALAXY_RADIUS_LY`, `GALAXY_POINT_COUNT`, `GALACTIC_CORE_GLOW_CLOSE_RADIUS_LY`, `GALACTIC_CORE_GLOW_WIDE_RADIUS_LY`, `GALACTIC_CORE_GLOW_CLOSE_ZOOM`, `GALACTIC_CORE_GLOW_WIDE_ZOOM`, `GALACTIC_CORE_GLOW_HEIGHT_LY` (constants), `galacticCoreGlowPresentation` (function), `GalacticCoreGlow`, `GalaxyBackdrop` (components) — Task 4 (`SceneContents.tsx`) imports `GalaxyBackdrop`; Task 5 (main file) imports `GALAXY_CENTER`, `GALAXY_POINT_COUNT` (used directly in the main file's JSX at `data-galaxy-point-count={GALAXY_POINT_COUNT}` — easy to miss since every other `GALAXY_POINT_COUNT` reference is inside the moved `makeGalaxyPointCloud`/`GalaxyBackdrop`, verify with a grep across the *whole* original file before assuming a constant is fully self-contained in the block being moved), `GALACTIC_CORE_GLOW_HEIGHT_LY`, `galacticCoreGlowPresentation`

- [ ] **Step 1: Create the file**

Move verbatim from `R3FMapFoundation.tsx`: constants at lines 56-58 (`GALAXY_CENTER`, `GALAXY_RADIUS_LY`, `GALAXY_POINT_COUNT`) and 67-71 (`GALACTIC_CORE_GLOW_CLOSE_RADIUS_LY`, `GALACTIC_CORE_GLOW_WIDE_RADIUS_LY`, `GALACTIC_CORE_GLOW_CLOSE_ZOOM`, `GALACTIC_CORE_GLOW_WIDE_ZOOM`, `GALACTIC_CORE_GLOW_HEIGHT_LY` — mark all as `export const`); `galacticCoreGlowPresentation` (106-120, export); `makeGalaxyPointCloud` (439-483, do not export); `makeGalaxyTexture` (485-532, do not export); `makeGalacticCoreGlowTexture` (534-555, do not export); `GalacticCoreGlow` (557-581, export); `GalaxyBackdrop` (583-626, export).

Imports needed (verified by grepping every hook and `THREE.*` reference in the moved lines against the full file): `useEffect, useMemo` from `'react'`; `import * as THREE from 'three'` (uses `THREE.CanvasTexture`, `THREE.SRGBColorSpace`, `THREE.AdditiveBlending`). No type imports from `./types` or the map-scene-contract artifact are needed — `GalacticCoreGlow`/`GalaxyBackdrop` both take inline `{ spatial: boolean; zoom: number }` prop types, matching the original.

```tsx
import { useEffect, useMemo } from 'react';
import * as THREE from 'three';

export const GALAXY_CENTER = { x: 25.2, z: 25_899.9 } as const;
export const GALAXY_RADIUS_LY = 50_000;
export const GALAXY_POINT_COUNT = 18_000;
export const GALACTIC_CORE_GLOW_CLOSE_RADIUS_LY = 18_000;
export const GALACTIC_CORE_GLOW_WIDE_RADIUS_LY = 10_000;
export const GALACTIC_CORE_GLOW_CLOSE_ZOOM = 70;
export const GALACTIC_CORE_GLOW_WIDE_ZOOM = 145;
export const GALACTIC_CORE_GLOW_HEIGHT_LY = -850;

export function galacticCoreGlowPresentation(zoom: number, spatial: boolean) {
  const closeProgress = Math.max(0, Math.min(
    1,
    (GALACTIC_CORE_GLOW_WIDE_ZOOM - zoom)
      / (GALACTIC_CORE_GLOW_WIDE_ZOOM - GALACTIC_CORE_GLOW_CLOSE_ZOOM),
  ));
  const easedProgress = closeProgress * closeProgress * (3 - 2 * closeProgress);
  return {
    radiusLy: GALACTIC_CORE_GLOW_WIDE_RADIUS_LY
      + (GALACTIC_CORE_GLOW_CLOSE_RADIUS_LY - GALACTIC_CORE_GLOW_WIDE_RADIUS_LY)
      * easedProgress,
    opacity: (spatial ? 0.38 : 0.44)
      + (spatial ? 0.68 - 0.38 : 0.76 - 0.44) * easedProgress,
  };
}

function makeGalaxyPointCloud() {
  const pointPositions = new Float32Array(GALAXY_POINT_COUNT * 3);
  const pointColors = new Float32Array(GALAXY_POINT_COUNT * 3);
  let seed = 0x5f3759df;
  const random = () => {
    seed = (Math.imul(seed, 1_664_525) + 1_013_904_223) >>> 0;
    return seed / 4_294_967_296;
  };

  for (let index = 0; index < GALAXY_POINT_COUNT; index += 1) {
    const inCentralBar = random() < 0.28;
    let x: number;
    let y: number;
    let radial: number;
    if (inCentralBar) {
      const along = (random() - random()) * 31_000;
      const across = (random() - random()) * (7_500 - Math.abs(along) * 0.12);
      const barAngle = -22 * Math.PI / 180;
      x = along * Math.cos(barAngle) - across * Math.sin(barAngle);
      y = along * Math.sin(barAngle) + across * Math.cos(barAngle);
      radial = Math.min(1, Math.hypot(x, y) / GALAXY_RADIUS_LY);
    } else {
      radial = Math.pow(random(), 0.68);
      const radius = radial * GALAXY_RADIUS_LY;
      const angle = random() * Math.PI * 2;
      x = Math.cos(angle) * radius + (random() - random()) * 1_250;
      y = Math.sin(angle) * radius * 0.72 + (random() - random()) * 900;
    }
    const thickness = (random() - random()) * (1 - radial * 0.8) * 1_150;
    pointPositions.set([
      GALAXY_CENTER.x + x,
      GALAXY_CENTER.z + y,
      thickness,
    ], index * 3);

    const warmth = Math.max(0, 1 - radial * 1.25);
    const brightness = 0.34 + random() * 0.28;
    pointColors.set([
      brightness + warmth * 0.24,
      brightness * 0.7 + warmth * 0.12,
      brightness * 0.54 + (1 - warmth) * 0.16,
    ], index * 3);
  }
  return { positions: pointPositions, colors: pointColors };
}

function makeGalaxyTexture(): THREE.CanvasTexture | null {
  if (typeof document === 'undefined') return null;
  const canvas = document.createElement('canvas');
  canvas.width = 1_024;
  canvas.height = 1_024;
  const context = canvas.getContext('2d');
  if (!context) return null;
  const centre = 512;

  context.globalCompositeOperation = 'lighter';
  context.save();
  context.translate(centre, centre);
  context.rotate(-22 * Math.PI / 180);
  context.scale(1.9, 0.42);
  const bar = context.createRadialGradient(0, 0, 0, 0, 0, 245);
  bar.addColorStop(0, 'rgba(255, 177, 87, 0.32)');
  bar.addColorStop(0.48, 'rgba(185, 88, 39, 0.13)');
  bar.addColorStop(1, 'rgba(60, 53, 54, 0)');
  context.fillStyle = bar;
  context.fillRect(-260, -260, 520, 520);
  context.restore();

  let cloudSeed = 0xa511e9b3;
  const cloudRandom = () => {
    cloudSeed = (Math.imul(cloudSeed, 1_103_515_245) + 12_345) >>> 0;
    return cloudSeed / 4_294_967_296;
  };
  for (let index = 0; index < 190; index += 1) {
    const progress = Math.pow(cloudRandom(), 0.72);
    const radius = progress * 455;
    const angle = cloudRandom() * Math.PI * 2;
    const x = centre + Math.cos(angle) * radius;
    const y = centre + Math.sin(angle) * radius * 0.72;
    const cloudRadius = 18 + cloudRandom() * 42 * (1 - progress * 0.55);
    const cloud = context.createRadialGradient(x, y, 0, x, y, cloudRadius);
    const alpha = 0.012 + cloudRandom() * 0.018;
    cloud.addColorStop(0, `rgba(224, ${Math.round(120 + progress * 42)}, ${Math.round(82 + progress * 50)}, ${alpha})`);
    cloud.addColorStop(1, 'rgba(58, 66, 82, 0)');
    context.fillStyle = cloud;
    context.fillRect(x - cloudRadius, y - cloudRadius, cloudRadius * 2, cloudRadius * 2);
  }
  context.globalCompositeOperation = 'source-over';

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

function makeGalacticCoreGlowTexture(): THREE.CanvasTexture | null {
  if (typeof document === 'undefined') return null;
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 512;
  const context = canvas.getContext('2d');
  if (!context) return null;
  const centre = canvas.width / 2;
  const glow = context.createRadialGradient(centre, centre, 0, centre, centre, centre);
  glow.addColorStop(0, 'rgba(255, 196, 116, 0.92)');
  glow.addColorStop(0.12, 'rgba(255, 150, 62, 0.58)');
  glow.addColorStop(0.36, 'rgba(190, 86, 31, 0.28)');
  glow.addColorStop(0.68, 'rgba(93, 45, 27, 0.1)');
  glow.addColorStop(1, 'rgba(35, 39, 52, 0)');
  context.fillStyle = glow;
  context.fillRect(0, 0, canvas.width, canvas.height);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

export function GalacticCoreGlow({ spatial, zoom }: { spatial: boolean; zoom: number }) {
  const texture = useMemo(makeGalacticCoreGlowTexture, []);
  const presentation = galacticCoreGlowPresentation(zoom, spatial);
  useEffect(() => () => texture?.dispose(), [texture]);
  if (!texture) return null;
  return <mesh
    position={[
      GALAXY_CENTER.x,
      GALAXY_CENTER.z,
      GALACTIC_CORE_GLOW_HEIGHT_LY,
    ]}
    scale={[presentation.radiusLy, presentation.radiusLy, 1]}
    renderOrder={-2}
  >
    <planeGeometry args={[2, 2]} />
    <meshBasicMaterial
      map={texture}
      transparent
      opacity={presentation.opacity}
      blending={THREE.AdditiveBlending}
      depthTest={false}
      depthWrite={false}
    />
  </mesh>;
}

export function GalaxyBackdrop({ spatial, zoom }: { spatial: boolean; zoom: number }) {
  const galaxy = useMemo(makeGalaxyPointCloud, []);
  const texture = useMemo(makeGalaxyTexture, []);
  useEffect(() => () => texture?.dispose(), [texture]);
  return <group>
    {texture && <mesh position={[GALAXY_CENTER.x, GALAXY_CENTER.z, -1_350]} renderOrder={-5}>
      <planeGeometry args={[GALAXY_RADIUS_LY * 2.08, GALAXY_RADIUS_LY * 1.5]} />
      <meshBasicMaterial
        map={texture}
        transparent
        opacity={spatial ? 0.66 : 0.56}
        blending={THREE.AdditiveBlending}
        depthWrite={false}
      />
    </mesh>}
    <mesh position={[GALAXY_CENTER.x, GALAXY_CENTER.z, -1_250]} renderOrder={-4}>
      <circleGeometry args={[GALAXY_RADIUS_LY * 1.02, 128]} />
      <meshBasicMaterial color="#1b100b" transparent opacity={spatial ? 0.13 : 0.2} depthWrite={false} />
    </mesh>
    <mesh position={[GALAXY_CENTER.x, GALAXY_CENTER.z, -1_100]} renderOrder={-3}>
      <circleGeometry args={[GALAXY_RADIUS_LY * 0.48, 128]} />
      <meshBasicMaterial color="#48210f" transparent opacity={spatial ? 0.1 : 0.14} depthWrite={false} />
    </mesh>
    <mesh position={[GALAXY_CENTER.x, GALAXY_CENTER.z, -1_000]} renderOrder={-2}>
      <circleGeometry args={[GALAXY_RADIUS_LY * 0.16, 96]} />
      <meshBasicMaterial color="#b45a1b" transparent opacity={spatial ? 0.11 : 0.15} depthWrite={false} />
    </mesh>
    <GalacticCoreGlow spatial={spatial} zoom={zoom} />
    <points renderOrder={-1}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[galaxy.positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[galaxy.colors, 3]} />
      </bufferGeometry>
      <pointsMaterial
        vertexColors
        size={Math.max(18, zoom * (spatial ? 1.4 : 1.1))}
        sizeAttenuation
        transparent
        opacity={spatial ? 0.44 : 0.34}
        depthWrite={false}
      />
    </points>
  </group>;
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && yarn typecheck`
Expected: passes with no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/map-foundation/GalaxyBackdrop.tsx
git commit -m "Extract GalaxyBackdrop.tsx from R3FMapFoundation.tsx

Galaxy point-cloud/texture generation and the galactic core glow move
verbatim into their own file, ahead of wiring them back in. No
behavior change; R3FMapFoundation.tsx still defines its own copies
until Task 5 removes them."
```

---

### Task 3: Create `SceneDecorations.tsx`

**Files:**
- Create: `frontend/src/features/map-foundation/SceneDecorations.tsx`
- Reference (read, do not modify yet): `frontend/src/features/map-foundation/R3FMapFoundation.tsx`

**Interfaces:**
- Consumes: `attenuatedPointSize` from `./camera` (Task 1)
- Produces: exported `rangeStepForView` (function), `RegionBoundaryLines`, `CameraCenterGuide`, `RangeGrid`, `ReferenceMarker` (components) — Task 4 (`SceneContents.tsx`) imports all four components; Task 5 (main file) imports `rangeStepForView`

- [ ] **Step 1: Create the file**

Move verbatim from `R3FMapFoundation.tsx`: `RegionBoundaryLines` (327-389, export); `CameraCenterGuide` (391-437, export); `niceRangeStep` (628-633, do not export); `rangeStepForView` (635-638, export); `RangeGrid` (640-680, export); `ReferenceMarker` (682-728, export).

Imports needed (verified against every hook/`THREE.*`/external-symbol reference in the moved lines): `useEffect, useMemo` from `'react'`; `import * as THREE from 'three'` (uses `THREE.DoubleSide`); `Line2` from `'three/examples/jsm/lines/Line2.js'`; `LineGeometry` from `'three/examples/jsm/lines/LineGeometry.js'`; `LineMaterial` from `'three/examples/jsm/lines/LineMaterial.js'`; `type { CameraState } from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract'`; `type { FoundationRendererProps, ViewportSize } from './types'`; `{ buildBoundaryPolylines } from './map-presentation'`; `{ attenuatedPointSize } from './camera'` (Task 1).

```tsx
import { useEffect, useMemo } from 'react';
import * as THREE from 'three';
import { Line2 } from 'three/examples/jsm/lines/Line2.js';
import { LineGeometry } from 'three/examples/jsm/lines/LineGeometry.js';
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js';
import type { CameraState } from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import type { FoundationRendererProps, ViewportSize } from './types';
import { buildBoundaryPolylines } from './map-presentation';
import { attenuatedPointSize } from './camera';

export function RegionBoundaryLines({
  boundaries,
  viewport,
  spatial,
}: {
  boundaries: FoundationRendererProps['regions']['boundaries'];
  viewport: FoundationRendererProps['viewport'];
  spatial: boolean;
}) {
  const polylines = useMemo(() => buildBoundaryPolylines(boundaries), [boundaries]);
  const layer = useMemo(() => {
    const haloMaterial = new LineMaterial({
      color: 0xff8a2c,
      linewidth: spatial ? 3.4 : 3.8,
      transparent: true,
      opacity: spatial ? 0.16 : 0.12,
      depthTest: false,
      depthWrite: false,
    });
    const coreMaterial = new LineMaterial({
      color: spatial ? 0xf0ad56 : 0xd58b3b,
      linewidth: spatial ? 2.15 : 1.8,
      transparent: true,
      opacity: spatial ? 0.9 : 0.76,
      depthTest: false,
      depthWrite: false,
    });
    const lines = polylines.map((positions) => {
      const geometry = new LineGeometry();
      geometry.setPositions(positions);
      geometry.computeBoundingBox();
      geometry.computeBoundingSphere();
      const halo = new Line2(geometry, haloMaterial);
      const core = new Line2(geometry, coreMaterial);
      halo.renderOrder = 5;
      core.renderOrder = 6;
      halo.frustumCulled = false;
      core.frustumCulled = false;
      return { geometry, halo, core };
    });

    return { lines, haloMaterial, coreMaterial };
  }, [polylines, spatial]);

  useEffect(() => {
    layer.haloMaterial.resolution.set(viewport.width, viewport.height);
    layer.coreMaterial.resolution.set(viewport.width, viewport.height);
  }, [layer, viewport.height, viewport.width]);

  useEffect(() => () => {
    layer.haloMaterial.dispose();
    layer.coreMaterial.dispose();
    layer.lines.forEach(({ geometry }) => geometry.dispose());
  }, [layer]);

  if (boundaries.length === 0) return null;
  return <>
    {layer.lines.map(({ halo, core }, index) => <group key={index}>
      <primitive object={halo} />
      <primitive object={core} />
    </group>)}
  </>;
}

export function CameraCenterGuide({
  camera,
  viewport,
}: {
  camera: CameraState;
  viewport: ViewportSize;
}) {
  const layer = useMemo(() => {
    const halfWidth = camera.zoom * viewport.width * 0.7;
    const halfHeight = camera.zoom * viewport.height * 0.7;
    const horizontalGeometry = new LineGeometry();
    horizontalGeometry.setPositions([
      camera.center.x - halfWidth, camera.center.z, -8,
      camera.center.x + halfWidth, camera.center.z, -8,
    ]);
    const verticalGeometry = new LineGeometry();
    verticalGeometry.setPositions([
      camera.center.x, camera.center.z - halfHeight, -8,
      camera.center.x, camera.center.z + halfHeight, -8,
    ]);
    const material = new LineMaterial({
      color: 0x8b6746,
      linewidth: 1,
      transparent: true,
      opacity: 0.22,
      depthTest: false,
      depthWrite: false,
      resolution: new THREE.Vector2(viewport.width, viewport.height),
    });
    const horizontal = new Line2(horizontalGeometry, material);
    const vertical = new Line2(verticalGeometry, material);
    horizontal.renderOrder = 1;
    vertical.renderOrder = 1;
    return { horizontal, vertical, horizontalGeometry, verticalGeometry, material };
  }, [camera.center.x, camera.center.z, camera.zoom, viewport.height, viewport.width]);

  useEffect(() => () => {
    layer.horizontalGeometry.dispose();
    layer.verticalGeometry.dispose();
    layer.material.dispose();
  }, [layer]);

  return <>
    <primitive object={layer.horizontal} />
    <primitive object={layer.vertical} />
  </>;
}

function niceRangeStep(target: number): number {
  const magnitude = 10 ** Math.floor(Math.log10(Math.max(0.01, target)));
  const normalized = target / magnitude;
  const multiplier = normalized < 2.5 ? 1 : normalized < 5 ? 2.5 : normalized < 10 ? 5 : 10;
  return multiplier * magnitude;
}

export function rangeStepForView(camera: CameraState, viewport: ViewportSize): number {
  const radius = camera.zoom * Math.min(viewport.width, viewport.height) * 0.48;
  return niceRangeStep(radius / 5);
}

export function RangeGrid({
  reference,
  camera,
  viewport,
  spatial,
}: {
  reference: { x: number; z: number };
  camera: CameraState;
  viewport: ViewportSize;
  spatial: boolean;
}) {
  const step = rangeStepForView(camera, viewport);
  const maxRadius = step * 5;
  const lineWidth = Math.max(0.015, camera.zoom * (spatial ? 0.9 : 0.65));
  const axes = useMemo(() => new Float32Array([
    reference.x - maxRadius, reference.z, 0,
    reference.x + maxRadius, reference.z, 0,
    reference.x, reference.z - maxRadius, 0,
    reference.x, reference.z + maxRadius, 0,
  ]), [maxRadius, reference.x, reference.z]);

  return <group>
    <lineSegments position={[0, 0, -2]}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[axes, 3]} /></bufferGeometry>
      <lineBasicMaterial color="#b36b30" transparent opacity={spatial ? 0.34 : 0.26} depthWrite={false} />
    </lineSegments>
    {Array.from({ length: 5 }, (_, index) => {
      const radius = step * (index + 1);
      return <mesh key={radius} position={[reference.x, reference.z, -1]} renderOrder={0}>
        <ringGeometry args={[Math.max(0.001, radius - lineWidth), radius + lineWidth, 160]} />
        <meshBasicMaterial
          color={index === 4 ? '#b87638' : '#714c31'}
          transparent
          opacity={index === 4 ? 0.5 : 0.34}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>;
    })}
  </group>;
}

export function ReferenceMarker({
  reference,
  zoom,
}: {
  reference: { x: number; z: number };
  zoom: number;
}) {
  const inner = Math.max(0.08, zoom * 7);
  const outer = Math.max(0.14, zoom * 13);
  const lineWidth = Math.max(0.018, zoom * 0.8);
  const cross = useMemo(() => new Float32Array([
    reference.x - outer * 1.4, reference.z, 4,
    reference.x - outer * 0.65, reference.z, 4,
    reference.x + outer * 0.65, reference.z, 4,
    reference.x + outer * 1.4, reference.z, 4,
    reference.x, reference.z - outer * 1.4, 4,
    reference.x, reference.z - outer * 0.65, 4,
    reference.x, reference.z + outer * 0.65, 4,
    reference.x, reference.z + outer * 1.4, 4,
  ]), [outer, reference.x, reference.z]);

  return <group>
    {[inner, outer].map((radius, index) => <mesh
      key={radius}
      position={[reference.x, reference.z, 3]}
      renderOrder={12}
    >
      <ringGeometry args={[radius - lineWidth, radius + lineWidth, 80]} />
      <meshBasicMaterial color="#ff8a22" transparent opacity={index === 0 ? 0.9 : 0.5} depthTest={false} />
    </mesh>)}
    <lineSegments renderOrder={13}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[cross, 3]} /></bufferGeometry>
      <lineBasicMaterial color="#ff9b43" transparent opacity={0.9} depthTest={false} />
    </lineSegments>
    <points position={[reference.x, reference.z, 6]} renderOrder={14}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[new Float32Array([0, 0, 0]), 3]} />
      </bufferGeometry>
      <pointsMaterial
        color="#ffffff"
        size={attenuatedPointSize(zoom, 4)}
        sizeAttenuation
        depthTest={false}
      />
    </points>
  </group>;
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && yarn typecheck`
Expected: passes with no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/map-foundation/SceneDecorations.tsx
git commit -m "Extract SceneDecorations.tsx from R3FMapFoundation.tsx

Region boundary lines, camera center guide, range grid, and reference
marker move verbatim into their own file. No behavior change;
R3FMapFoundation.tsx still defines its own copies until Task 5 removes
them."
```

---

### Task 4: Create `SceneContents.tsx`

**Files:**
- Create: `frontend/src/features/map-foundation/SceneContents.tsx`
- Reference (read, do not modify yet): `frontend/src/features/map-foundation/R3FMapFoundation.tsx`

**Interfaces:**
- Consumes: `attenuatedPointSize`, `cameraDistanceForView` from `./camera` (Task 1); `GalaxyBackdrop` from `./GalaxyBackdrop` (Task 2); `CameraCenterGuide`, `RangeGrid`, `RegionBoundaryLines`, `ReferenceMarker` from `./SceneDecorations` (Task 3)
- Produces: exported `RendererSizeSync`, `GpuTimingBridge`, `CameraProjection`, `SceneContents` (components), `projectWorldPoint`, `projectLabels`, `projectSystemLabels` (functions) — Task 5 (main file) imports `RendererSizeSync`, `GpuTimingBridge`, `SceneContents`, `projectWorldPoint`, `projectLabels`, `projectSystemLabels` (not `CameraProjection`, which is only rendered inside this file's own `SceneContents`, but must still be `export`ed per the Global Constraints named-export convention)

- [ ] **Step 1: Create the file**

Move verbatim from `R3FMapFoundation.tsx`: `positions` (122-133, do not export — grepped every call site in the source file: used only inside `SceneContents`, never in the main component body); `configureRenderCamera` (147-177, do not export — only this file's own `projectWorldPoint`/`projectLabels`/`projectSystemLabels`/`CameraProjection` call it); `projectWorldPoint` (179-198, export); `CameraProjection` (200-207, export); `RendererSizeSync` (209-315, export); `GpuTimingBridge` (317-325, export); `RegionBoundaryLines` reference removed — do not move, it now comes from `./SceneDecorations`; `SceneContents` (730-909, export — replace its internal `<GalaxyBackdrop>`, `<CameraCenterGuide>`, `<RangeGrid>`, `<ReferenceMarker>`, `<RegionBoundaryLines>` JSX references with imports, no other change); `projectLabels` (911-945, export); `projectSystemLabels` (947-995, export).

Imports needed (verified against every hook/`THREE.*`/external-symbol reference in the moved lines): `useCallback, useEffect, useLayoutEffect, useMemo, useState` from `'react'`; `useThree, type ThreeEvent` from `'@react-three/fiber'`; `import * as THREE from 'three'`; `type { CameraState, MapInteractionEvent, SystemRecord } from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract'`; `type { FoundationRendererProps, ProjectedLabel, ViewportSize } from './types'`; `{ measureRendererGpuTiming } from './performance'`; `{ declutterRegionLabels } from './map-presentation'`; `{ buildClusterGeometry, clusterAnchorIdForSystem, findOverlappingSystemIds, selectVisibleSystems } from './visibility'` (NOT `highlightedSystemIds` — that stays used only in the main file); `{ attenuatedPointSize, cameraDistanceForView } from './camera'` (Task 1); `{ GalaxyBackdrop } from './GalaxyBackdrop'` (Task 2); `{ CameraCenterGuide, RangeGrid, RegionBoundaryLines, ReferenceMarker } from './SceneDecorations'` (Task 3).

```tsx
import { Canvas, type ThreeEvent, useThree } from '@react-three/fiber';
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
} from 'react';
import * as THREE from 'three';
import type {
  CameraState,
  MapInteractionEvent,
  SystemRecord,
} from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import type {
  FoundationRendererProps,
  ProjectedLabel,
  ViewportSize,
} from './types';
import { measureRendererGpuTiming } from './performance';
import { declutterRegionLabels } from './map-presentation';
import {
  buildClusterGeometry,
  clusterAnchorIdForSystem,
  findOverlappingSystemIds,
  selectVisibleSystems,
} from './visibility';
import { attenuatedPointSize, cameraDistanceForView } from './camera';
import { GalaxyBackdrop } from './GalaxyBackdrop';
import {
  CameraCenterGuide,
  RangeGrid,
  RegionBoundaryLines,
  ReferenceMarker,
} from './SceneDecorations';

function positions(
  systems: SystemRecord[],
  heightOffset = 0,
): Float32Array {
  const values = new Float32Array(systems.length * 3);
  systems.forEach((system, index) => values.set([
    system.coords.x,
    system.coords.z,
    system.coords.y + heightOffset,
  ], index * 3));
  return values;
}

function configureRenderCamera(
  camera: THREE.PerspectiveCamera,
  size: ViewportSize,
  cameraState: CameraState,
) {
  const bearing = cameraState.bearingDeg * Math.PI / 180;
  const pitch = Math.max(
    // NOTE: MIN_CAMERA_PITCH_DEG / MAX_CAMERA_PITCH_DEG import — see Step 1 note below
    cameraState.pitchDeg,
    cameraState.pitchDeg,
  );
  throw new Error('placeholder-should-not-compile');
}
```

**STOP — the placeholder above is intentionally broken and must not be used.** `configureRenderCamera` clamps `cameraState.pitchDeg` using `MIN_CAMERA_PITCH_DEG` and `MAX_CAMERA_PITCH_DEG`, which are exported from `./camera` (not moved by this plan — they stay defined in `camera.ts` as they are today). Add `MIN_CAMERA_PITCH_DEG, MAX_CAMERA_PITCH_DEG` to this file's `import { attenuatedPointSize, cameraDistanceForView } from './camera';` line (making it `import { attenuatedPointSize, cameraDistanceForView, MIN_CAMERA_PITCH_DEG, MAX_CAMERA_PITCH_DEG } from './camera';`), then write `configureRenderCamera`, `projectWorldPoint`, `CameraProjection`, `RendererSizeSync`, `GpuTimingBridge` verbatim from `R3FMapFoundation.tsx` lines 147-325:

```tsx
function configureRenderCamera(
  camera: THREE.PerspectiveCamera,
  size: ViewportSize,
  cameraState: CameraState,
) {
  const bearing = cameraState.bearingDeg * Math.PI / 180;
  const pitch = Math.max(
    MIN_CAMERA_PITCH_DEG,
    Math.min(MAX_CAMERA_PITCH_DEG, cameraState.pitchDeg),
  ) * Math.PI / 180;
  const fov = 42;
  const visibleHeight = Math.max(
    20,
    cameraState.zoom * size.height * CAMERA_VIEWPORT_HEIGHT_RATIO,
  );
  const distance = visibleHeight / (2 * Math.tan((fov * Math.PI / 180) / 2));
  const horizontalDistance = Math.sin(pitch) * distance;
  const verticalDistance = Math.cos(pitch) * distance;
  camera.fov = fov;
  camera.aspect = Math.max(0.1, size.width / Math.max(1, size.height));
  camera.position.set(
    cameraState.center.x - Math.sin(bearing) * horizontalDistance,
    cameraState.center.z - Math.cos(bearing) * horizontalDistance,
    Math.max(10, verticalDistance),
  );
  camera.up.set(0, 0, 1);
  camera.lookAt(cameraState.center.x, cameraState.center.z, 0);
  camera.near = Math.max(0.1, distance / 20_000);
  camera.far = Math.max(250_000, distance + 200_000);
  camera.updateProjectionMatrix();
}
```

**A second correction to the same paragraph above:** `configureRenderCamera` also references `CAMERA_VIEWPORT_HEIGHT_RATIO` (already exported from `./camera` today, same as `MIN_CAMERA_PITCH_DEG`/`MAX_CAMERA_PITCH_DEG`) — add it to the same import line, making it `import { attenuatedPointSize, cameraDistanceForView, CAMERA_VIEWPORT_HEIGHT_RATIO, MIN_CAMERA_PITCH_DEG, MAX_CAMERA_PITCH_DEG } from './camera';`.

Continue with the rest of the file verbatim from `R3FMapFoundation.tsx`:

```tsx
function projectWorldPoint(
  cameraState: CameraState,
  viewport: ViewportSize,
  point: [number, number, number],
): { x: number; y: number; depth: number } {
  const camera = new THREE.PerspectiveCamera(
    42,
    viewport.width / Math.max(1, viewport.height),
    0.1,
    500_000,
  );
  configureRenderCamera(camera, viewport, cameraState);
  camera.updateMatrixWorld(true);
  const projected = new THREE.Vector3(...point).project(camera);
  return {
    x: (projected.x * 0.5 + 0.5) * viewport.width,
    y: (-projected.y * 0.5 + 0.5) * viewport.height,
    depth: projected.z,
  };
}

function CameraProjection({ cameraState }: { cameraState: CameraState }) {
  const { camera, size, invalidate } = useThree();
  useEffect(() => {
    configureRenderCamera(camera as THREE.PerspectiveCamera, size, cameraState);
    invalidate();
  }, [camera, cameraState, invalidate, size]);
  return null;
}

function RendererSizeSync({ viewport }: { viewport: ViewportSize }) {
  const {
    get,
    gl,
    invalidate,
    setDpr,
    setSize,
  } = useThree();

  useLayoutEffect(() => {
    const canvas = gl.domElement;

    let frame: number | null = null;
    let lastWidth: number | null = null;
    let lastHeight: number | null = null;
    let lastDpr: number | null = null;
    const measure = () => {
      const rect = canvas.getBoundingClientRect();
      const width = Math.max(1, Math.round(rect.width || viewport.width));
      const height = Math.max(1, Math.round(rect.height || viewport.height));
      const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
      return { width, height, dpr };
    };
    const sync = () => {
      frame = null;
      const { width, height, dpr } = measure();
      const state = get();

      if (Math.abs(state.viewport.dpr - dpr) > 0.001) setDpr(dpr);
      if (state.size.width !== width || state.size.height !== height) {
        setSize(width, height);
      }

      const expectedWidth = Math.round(width * dpr);
      const expectedHeight = Math.round(height * dpr);
      const drawingBuffer = gl.getDrawingBufferSize(new THREE.Vector2());
      if (
        Math.abs(drawingBuffer.x - expectedWidth) > 1
        || Math.abs(drawingBuffer.y - expectedHeight) > 1
      ) {
        gl.setPixelRatio(dpr);
        gl.setSize(width, height, false);
      }
      gl.setViewport(0, 0, width, height);

      const syncedBuffer = gl.getDrawingBufferSize(new THREE.Vector2());
      const context = gl.getContext();
      const syncedViewport = context.getParameter(context.VIEWPORT) as Int32Array;
      canvas.dataset.cssWidth = String(width);
      canvas.dataset.cssHeight = String(height);
      canvas.dataset.drawingBufferWidth = String(syncedBuffer.x);
      canvas.dataset.drawingBufferHeight = String(syncedBuffer.y);
      canvas.dataset.viewportX = String(syncedViewport[0]);
      canvas.dataset.viewportY = String(syncedViewport[1]);
      canvas.dataset.viewportWidth = String(syncedViewport[2]);
      canvas.dataset.viewportHeight = String(syncedViewport[3]);
      canvas.dataset.contextLost = String(context.isContextLost());
      canvas.dataset.drawingBufferSynced = String(
        Math.abs(syncedBuffer.x - expectedWidth) <= 1
        && Math.abs(syncedBuffer.y - expectedHeight) <= 1,
      );
      invalidate();
      lastWidth = width;
      lastHeight = height;
      lastDpr = dpr;
    };
    const queueSync = () => {
      const { width, height, dpr } = measure();
      if (
        lastWidth == null
        || lastHeight == null
        || lastDpr == null
        || width !== lastWidth
        || height !== lastHeight
        || Math.abs(dpr - lastDpr) > 0.001
      ) {
        canvas.dataset.drawingBufferSynced = 'false';
      }
      if (frame != null) window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(sync);
    };

    sync();
    const observer = typeof ResizeObserver === 'undefined'
      ? null
      : new ResizeObserver(queueSync);
    observer?.observe(canvas);
    window.addEventListener('resize', queueSync);
    window.visualViewport?.addEventListener('resize', queueSync);
    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', queueSync);
      window.visualViewport?.removeEventListener('resize', queueSync);
      if (frame != null) window.cancelAnimationFrame(frame);
    };
  }, [
    get,
    gl,
    invalidate,
    setDpr,
    setSize,
    viewport.height,
    viewport.width,
  ]);

  return null;
}

function GpuTimingBridge({ onReady }: { onReady: FoundationRendererProps['onGpuTimerReady'] }) {
  const { camera, gl, scene } = useThree();
  useEffect(() => {
    if (!onReady) return undefined;
    onReady((sampleCount) => measureRendererGpuTiming(gl, scene, camera, sampleCount));
    return () => onReady(null);
  }, [camera, gl, onReady, scene]);
  return null;
}
```

Then `SceneContents` verbatim from lines 730-909 (unchanged body — it already references `GalaxyBackdrop`, `CameraCenterGuide`, `RangeGrid`, `ReferenceMarker`, `RegionBoundaryLines`, `CameraProjection` by these exact names, which now resolve to this file's own definition (`CameraProjection`) or the new imports (the other four) instead of same-file sibling functions — no JSX changes needed, only the import block added above makes this resolve correctly), then `projectLabels` (911-945) and `projectSystemLabels` (947-995) verbatim, both unchanged (they already call `configureRenderCamera`, which is this file's own private function).

Finally, mark `RendererSizeSync`, `GpuTimingBridge`, `CameraProjection`, `SceneContents`, `projectWorldPoint`, `projectLabels`, `projectSystemLabels` as `export function` / `export function` (all seven) per the Interfaces section above; `positions` and `configureRenderCamera` stay as plain `function` (not exported).

- [ ] **Step 2: Type-check**

Run: `cd frontend && yarn typecheck`
Expected: passes with no errors. This step in particular will catch a missed import (e.g. forgetting `MIN_CAMERA_PITCH_DEG`/`MAX_CAMERA_PITCH_DEG`/`CAMERA_VIEWPORT_HEIGHT_RATIO` from `./camera`, or `highlightedSystemIds` incorrectly included when it should not be) — do not skip it even though this file is not yet imported anywhere, `tsc --noEmit` checks every file in the project regardless of whether anything currently imports it.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/map-foundation/SceneContents.tsx
git commit -m "Extract SceneContents.tsx from R3FMapFoundation.tsx

The R3F-context bridge components (CameraProjection, RendererSizeSync,
GpuTimingBridge), the main per-frame scene composer, and the camera/
label projection math move verbatim into their own file, importing
GalaxyBackdrop and the SceneDecorations components rather than
defining them locally. No behavior change; R3FMapFoundation.tsx still
defines its own copies until Task 5 removes them."
```

---

### Task 5: Update `R3FMapFoundation.tsx`, verify, and commit

**Files:**
- Modify: `frontend/src/features/map-foundation/R3FMapFoundation.tsx`

**Interfaces:**
- Consumes: `GALAXY_CENTER`, `GALACTIC_CORE_GLOW_HEIGHT_LY`, `galacticCoreGlowPresentation` from `./GalaxyBackdrop` (Task 2); `rangeStepForView` from `./SceneDecorations` (Task 3); `RendererSizeSync`, `GpuTimingBridge`, `SceneContents`, `projectWorldPoint`, `projectLabels`, `projectSystemLabels` from `./SceneContents` (Task 4)
- Produces: `export function R3FMapFoundation(props: FoundationRendererProps)` — unchanged signature; this is the only symbol anything outside `frontend/src/features/map-foundation/` imports from this file (verify with a grep before assuming — `ProductionMapTab.tsx`, `AuthoritativeRegionMap.tsx`, or other siblings may import it too, all within this same directory)

- [ ] **Step 1: Confirm `R3FMapFoundation.test.tsx` does not import moved internals**

Run: `grep -n "^import" frontend/src/features/map-foundation/R3FMapFoundation.test.tsx`
Expected: only imports `R3FMapFoundation` (and possibly its prop/type dependencies) from `./R3FMapFoundation` — no direct import of `SceneContents`, `GalaxyBackdrop`, `RegionBoundaryLines`, or any other symbol this plan moves. If the test file does import one of these directly, stop and re-plan Task 5's import list to also update the test file's import path (do not proceed silently).

- [ ] **Step 2: Replace the import block**

Replace `R3FMapFoundation.tsx` lines 1-54 (everything from `import { Canvas, type ThreeEvent, useThree } from '@react-three/fiber';` through the closing `} from './visibility';` of the `selectVisibleSystems` import) with:

```tsx
import { Canvas } from '@react-three/fiber';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  type CSSProperties,
} from 'react';
import type {
  CameraState,
  SystemRecord,
} from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import type {
  FoundationRendererProps,
  ViewportSize,
} from './types';
import {
  clampCameraCenter,
  KEYBOARD_PAN_ACCELERATION_MS,
  KEYBOARD_PAN_DECELERATION_MS,
  MAX_CAMERA_PITCH_DEG,
  MIN_CAMERA_PITCH_DEG,
  sampleKeyboardPanTransition,
  type KeyboardPanTransition,
  type KeyboardPanVelocity,
  zoomCamera,
} from './camera';
import { regionLabelScale } from './map-presentation';
import {
  decodeAuthoritativeRegionLookup,
  findAuthoritativeRegionAt,
} from './authoritative-regions';
import {
  buildClusterGeometry,
  highlightedSystemIds,
  selectVisibleSystems,
} from './visibility';
import {
  GALACTIC_CORE_GLOW_HEIGHT_LY,
  GALAXY_CENTER,
  GALAXY_POINT_COUNT,
  galacticCoreGlowPresentation,
} from './GalaxyBackdrop';
import { rangeStepForView } from './SceneDecorations';
import {
  GpuTimingBridge,
  projectLabels,
  projectSystemLabels,
  projectWorldPoint,
  RendererSizeSync,
  SceneContents,
} from './SceneContents';
```

This is a real trim, not just reformatting — verify each dropped symbol against the source file before trusting this list: `Canvas` and `useThree` (from `@react-three/fiber`) are no longer referenced directly in the main component body once `SceneContents`/`RendererSizeSync`/`GpuTimingBridge`/`CameraProjection` move out — **except** `Canvas` is still used directly in the main component's JSX return (verify: yes, `<Canvas frameloop="demand" ...>` wraps `<RendererSizeSync>`/`<GpuTimingBridge>`/`<SceneContents>` in the final return). Keep `import { Canvas } from '@react-three/fiber';` (drop only `type ThreeEvent, useThree`, which are unused once `SceneContents`/`CameraProjection` move out — `ThreeEvent` was only used in `SceneContents`'s `select`/`hover` callback signatures). `useState` is dropped (confirmed via grep: the only `useState` call in the original file, line 732, was inside `SceneContents`). `useLayoutEffect` is dropped (confirmed via grep: the only call, line 218, was inside `RendererSizeSync`). `THREE` namespace import is dropped entirely — confirmed via grep, every `THREE.*` reference in the original file falls within ranges this plan moves to `GalaxyBackdrop.tsx`/`SceneDecorations.tsx`/`SceneContents.tsx`; the main component body (lines 997-1663) has zero direct `THREE.*` references. `Line2`/`LineGeometry`/`LineMaterial` imports are dropped entirely (moved to `SceneDecorations.tsx`, not referenced elsewhere). `type ProjectedLabel` is dropped from the `./types` import (only used in `SceneContents.tsx`'s `projectLabels` return type now) — keep `FoundationRendererProps, ViewportSize`. `type MapInteractionEvent` is dropped from the map-scene-contract import (only used inside the moved `SceneContents`'s `select` callback) — keep `CameraState, SystemRecord` (verify `SystemRecord` is still referenced directly in the main file: yes, `systemLabels` useMemo body at line 1074 does `const byId = new Map<number, SystemRecord>();`). `buildBoundaryPolylines` (from `./map-presentation`) is dropped — only used in the moved `RegionBoundaryLines`; keep `regionLabelScale`, which the main file still calls directly (`const labelScale = regionLabelScale(props.scene.camera.zoom);`). `declutterRegionLabels` (from `./map-presentation`) is dropped — only used in the moved `projectLabels`. `clusterAnchorIdForSystem, findOverlappingSystemIds` (from `./visibility`) are dropped — only used in the moved `SceneContents`'s `select` callback; keep `buildClusterGeometry` (still called directly in the main file at lines 1072 and, for `clusters`, also used inline in JSX — verify: yes, `const clusters = useMemo(() => buildClusterGeometry(props.scene), [props.scene]);` at line 1072, and `clusters.flatMap(...)` in the cluster-labels JSX), and `highlightedSystemIds` (still called directly: `const highlightedIds = useMemo(() => highlightedSystemIds(props.scene.highlights), [props.scene.highlights]);` at line 1071) and `selectVisibleSystems` (still called directly: `const visible = useMemo(() => selectVisibleSystems(...), ...)` at line 1023).

- [ ] **Step 3: Delete the moved function/component definitions**

Delete the following ranges verbatim from the current file (do this after Step 2's import replacement, so line numbers below still refer to the pre-Step-2 file — re-locate each by function name if line numbers have already shifted from an earlier edit in this task):
- `galacticCoreGlowPresentation` (was lines 106-120) — now imported from `./GalaxyBackdrop`.
- `positions` (was lines 122-133) — moved fully into `SceneContents.tsx` (Task 4), not used elsewhere in this file.
- `cameraDistanceForView` (was lines 135-141) — moved into `camera.ts` (Task 1), not used directly in this file (only `SceneContents.tsx` calls it).
- `attenuatedPointSize` (was lines 143-145) — moved into `camera.ts` (Task 1), not used directly in this file.
- `configureRenderCamera` (was lines 147-177) — moved into `SceneContents.tsx` (Task 4) as a private function there.
- `projectWorldPoint` (was lines 179-198) — now imported from `./SceneContents`.
- `CameraProjection` (was lines 200-207) through `GpuTimingBridge` (was lines 317-325) — the whole block, now imported (`RendererSizeSync`, `GpuTimingBridge`) or unused directly (`CameraProjection`, only used inside the now-external `SceneContents`).
- `RegionBoundaryLines` (was lines 327-389) — now imported from `./SceneDecorations` via `SceneContents.tsx`; not referenced directly by the main file.
- `CameraCenterGuide` (was lines 391-437) — same as above.
- `makeGalaxyPointCloud` (was lines 439-483) through `GalaxyBackdrop` (was lines 583-626) — the whole block, now imported (`GALAXY_CENTER`, `galacticCoreGlowPresentation`) or unused directly by the main file.
- `niceRangeStep` (was lines 628-633) through `ReferenceMarker` (was lines 682-728) — the whole block, now imported (`rangeStepForView`) or unused directly.
- `SceneContents` (was lines 730-909) — now imported from `./SceneContents`.
- `projectLabels` (was lines 911-945) and `projectSystemLabels` (was lines 947-995) — now imported from `./SceneContents`.

After this deletion, the file should contain (in order): the new import block (Step 2), the keyboard-physics constants (`KEYBOARD_PAN_PIXELS_PER_SECOND` through `GALACTIC_CORE_GLOW_HEIGHT_LY` — **wait**, the galactic-core-glow constants (`GALACTIC_CORE_GLOW_CLOSE_RADIUS_LY` etc.) were also moved to `GalaxyBackdrop.tsx` in Task 2 — delete those five constant declarations (was lines 67-71) from the main file too, keeping only `KEYBOARD_PAN_PIXELS_PER_SECOND` through `REDUCED_MOTION_QUERY` (was lines 59-66) and dropping `GALAXY_CENTER`/`GALAXY_RADIUS_LY`/`GALAXY_POINT_COUNT` (was lines 56-58, now imported) and `GALACTIC_CORE_GLOW_*` (was lines 67-71, now imported except `GALACTIC_CORE_GLOW_HEIGHT_LY` which the main file still references directly in `galacticCoreProjection` and must come from the new import in Step 2), the `MapControlKey`/`KeyboardPanPhase` types (was lines 73-74), `mapControlKey`/`protectsFocusFromMap`/`keyboardPanTarget` (was lines 76-104), and the full `export function R3FMapFoundation(...)` (was lines 997-1663) unchanged.

- [ ] **Step 4: Type-check**

Run: `cd frontend && yarn typecheck`
Expected: passes with no errors.

- [ ] **Step 5: Lint**

Run: `cd frontend && yarn lint`
Expected: passes (0 errors; pre-existing unrelated warnings are fine).

- [ ] **Step 6: Knip unused-file/export check**

Run: `cd frontend && yarn knip --files`
Expected: passes — no new unused-export warnings (would indicate a moved symbol never got wired into an importer, or an old import survived deletion unused).

- [ ] **Step 7: Run the full frontend test suite**

Run: `cd frontend && yarn test`
Expected: `R3FMapFoundation.test.tsx` (589 lines) passes in full — this is the primary automated safety net for this task, since it exercises the `data-camera-*`, `data-current-region-*`, `data-galactic-core-*`, `data-keyboard-pan-*` attribute contract that a wiring mistake (wrong import, dropped prop) would break. If the local full suite shows unrelated failures in other files, cross-check against isolated runs before treating anything as a real regression (this repo's local Windows test environment has shown resource-contention flakiness on unrelated files during this series — verify, don't assume, in either direction).

- [ ] **Step 8: Production build**

Run: `cd frontend && yarn build`
Expected: succeeds with no errors.

- [ ] **Step 9: Manual interaction smoke check (elevated bar — this is the live production map)**

Start the dev server (`yarn dev`) and the local API server, then in a browser navigate to the Map route:
- Confirm the galaxy view loads with region boundaries, labels, and the galactic core glow visible.
- Drag to pan; confirm smooth camera motion, no console errors.
- Use W/A/S/D keys to pan; confirm keyboard pan works and decelerates smoothly on key-up.
- Scroll/use Z and X keys to zoom; confirm zoom works in both directions.
- Shift-drag to tilt the camera; confirm the view transitions between top-down and spatial/tilted presentation (this toggles `spatial`, which changes opacity/color on several of the moved components — a real exercise of the split, not just a static render).
- Click a system point; confirm selection works (check `data-current-region-id`/`data-current-region-name` attributes update, and that the selected-system visual marker appears).
- Hover a system point; confirm the hover-highlight ring appears.
- Check the browser console for any new errors versus a pre-change baseline (expect only the pre-existing, already-documented Vite HMR WebSocket errors from earlier smoke checks in this series).

- [ ] **Step 10: Verify no function or type was missed**

Run: `grep -c "^export function\|^export const\|^export type" frontend/src/features/map-foundation/{GalaxyBackdrop,SceneDecorations,SceneContents}.tsx`
Expected: non-zero counts matching each file's Interfaces "Produces" list from Tasks 2-4. Then run `grep -rn "GalacticCoreGlow\b" frontend/src/features/map-foundation/R3FMapFoundation.tsx` and confirm zero matches (it should only be referenced from within `GalaxyBackdrop.tsx` now, never directly by the main file) as a spot-check that no stray duplicate definition survived the Step 3 deletion.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/features/map-foundation/R3FMapFoundation.tsx
git commit -m "Wire R3FMapFoundation.tsx to the extracted scene-concern files

R3FMapFoundation.tsx shrinks from 1663 to roughly 1000 lines - the
galaxy backdrop, scene decorations, and R3F scene-content/camera-
projection code extracted in the prior four commits are now imported
instead of locally defined. Keyboard/pointer physics state and the
final JSX render are unchanged, as designed. No behavior change. See
docs/superpowers/specs/2026-08-06-split-r3f-map-foundation-design.md."
```

---

## Self-Review

**Spec coverage:** Every function/component/constant enumerated in the design doc's Decision section has an explicit Task, explicit source line range, explicit export/private designation, and explicit destination. The dependency graph (camera.ts ← GalaxyBackdrop/SceneDecorations ← SceneContents ← main file) is realized by the task ordering (Task 1 before 2/3, Tasks 2-3 before 4, Task 4 before 5) so each task's `yarn typecheck` step can only fail on that task's own content, never a forward reference to a not-yet-created file.

**Placeholder scan:** Task 4 Step 1 contains one deliberately-broken code block, but it is explicitly flagged in bold as "intentionally broken and must not be used," immediately followed by the corrected version and an explanation of exactly why (a missed import of `MIN_CAMERA_PITCH_DEG`/`MAX_CAMERA_PITCH_DEG`/`CAMERA_VIEWPORT_HEIGHT_RATIO`) — this documents a real trap (an implementer who moves `configureRenderCamera` without checking what it references from the original file's *other* imports, not just the lines being moved, would silently produce broken code) rather than leaving a silent gap. No other TBD/placeholder exists.

**Type consistency:** Every cross-file reference (function names, exported constant names) is spelled identically at its export site and its import site throughout Tasks 1-5, cross-checked against the original file's actual usage via targeted greps (hook calls, `THREE.*` calls, `positions(` calls) performed while writing this plan, not assumed from memory.
