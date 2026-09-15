import { afterEach, describe, expect, it } from 'vitest';
import { VertexBuffer } from '@babylonjs/core/Buffers/buffer.js';
import { FreeCamera } from '@babylonjs/core/Cameras/freeCamera.js';
import { NullEngine } from '@babylonjs/core/Engines/nullEngine.js';
import { Vector3 } from '@babylonjs/core/Maths/math.vector.js';
import { Scene } from '@babylonjs/core/scene.js';

import { buildFixtureCatalogueDensity } from '../galaxy-density.fixture';
import type { CatalogueDensitySceneLayer } from '../galaxy-density';
import {
  buildCatalogueDensityKernel,
  catalogueDensityHeatColour,
  CATALOGUE_DENSITY_KERNEL_SIZE,
  CATALOGUE_DENSITY_PRESENTATION_VERSION,
  createCatalogueDensityMesh,
} from './catalogue-density';

const fixtureOptions = {
  generationId: 'fixture:density-splat-v1' as const,
  pyramidVersion: 'fixture-pyramid-v1',
  level: 2,
  cellSizeLy: 100,
  cellOriginLy: { x: -1_000, y: -1_000, z: -1_000 },
  boundsLy: {
    min: { x: -1_000, y: -1_000, z: -1_000 },
    max: { x: 1_000, y: 1_000, z: 1_000 },
  },
  coverageAsOf: '2026-09-13T00:00:00Z',
};
const density: CatalogueDensitySceneLayer = {
  contributionId: 'catalogue-density-base',
  contributionRevision: 1,
  layerVersion: 1,
  payload: buildFixtureCatalogueDensity(
    [
      { positionLy: { x: 12, y: -4, z: 25 } },
      { positionLy: { x: 18, y: -2, z: 28 } },
      { positionLy: { x: 410, y: 90, z: -240 } },
    ],
    fixtureOptions,
  ),
};

describe('catalogue density splats', () => {
  const engines: NullEngine[] = [];
  const createScene = () => {
    const engine = new NullEngine();
    engines.push(engine);
    const scene = new Scene(engine);
    const camera = new FreeCamera('camera', new Vector3(0, 0, -2_000), scene);
    camera.setTarget(Vector3.Zero());
    scene.activeCamera = camera;
    return { scene, camera };
  };
  afterEach(() => {
    for (const engine of engines.splice(0)) engine.dispose();
  });

  it('keeps one instance per factual cell, exact centroids and count-ordered intensity', () => {
    const { scene } = createScene();
    const mesh = createCatalogueDensityMesh(scene, density)!;
    const matrices = mesh.thinInstanceGetWorldMatrices();
    const colours = mesh
      .getVertexBuffer('instanceColor')!
      .getFloatData(density.payload.cells.length)!;

    expect(mesh.getTotalVertices()).toBe(4);
    expect(matrices).toHaveLength(density.payload.cells.length);
    for (const [index, cell] of density.payload.cells.entries()) {
      const matrix = matrices[index];
      const translation = matrix.getTranslation();
      expect(translation.asArray()).toEqual([
        cell.centroidLy.x,
        cell.centroidLy.y,
        cell.centroidLy.z,
      ]);
      expect(matrix.m[0]).toBeLessThanOrEqual(100 * 0.62);
    }
    expect(matrices[0].m[0]).toBeGreaterThan(matrices[1].m[0]);
    expect(colours[3]).toBeGreaterThan(colours[7]);
    expect(mesh.metadata.spatialLayer).toMatchObject({
      generationId: density.payload.generationId,
      renderedCellCount: 2,
      coveredSystemCount: 3,
      generatedOccupancy: false,
      presentation: {
        version: CATALOGUE_DENSITY_PRESENTATION_VERSION,
        palette: 'cool-sparse-to-warm-dense',
        blend: 'alpha-combine',
        maximumSupportRadiusLy: 62,
      },
    });
  });

  it('maps only real cell counts from cool/faint to warm/luminous', () => {
    const sparse = catalogueDensityHeatColour(1, 100);
    const medium = catalogueDensityHeatColour(20, 100);
    const dense = catalogueDensityHeatColour(100, 100);

    expect(sparse[2]).toBeGreaterThan(sparse[0]);
    expect(dense[0]).toBeGreaterThan(dense[2]);
    expect(medium[3]).toBeGreaterThan(sparse[3]);
    expect(dense[3]).toBeGreaterThan(medium[3]);
    expect(dense.every((channel) => channel >= 0 && channel <= 1)).toBe(true);
    expect(() => catalogueDensityHeatColour(0, 100)).toThrow(/positive/);
  });

  it('faces rotated cameras without orbiting or rebuilding source instance positions', () => {
    const { scene, camera } = createScene();
    const mesh = createCatalogueDensityMesh(scene, density)!;
    const matrices = mesh.thinInstanceGetWorldMatrices();
    const positionsBefore = Array.from(
      mesh.getVerticesData(VertexBuffer.PositionKind)!,
    );
    camera.position.set(1_000, 700, 900);
    camera.setTarget(new Vector3(40, 0, 20));
    scene.onBeforeCameraRenderObservable.notifyObservers(camera);

    const positions = mesh.getVerticesData(VertexBuffer.PositionKind)!;
    expect(Array.from(positions)).not.toEqual(positionsBefore);
    expect(mesh.thinInstanceGetWorldMatrices()).toBe(matrices);
    const first = Vector3.FromArray(positions, 0);
    const second = Vector3.FromArray(positions, 3);
    const third = Vector3.FromArray(positions, 6);
    const normal = Vector3.Cross(
      second.subtract(first),
      third.subtract(first),
    ).normalize();
    const cameraForward = Vector3.TransformNormal(
      Vector3.Forward(),
      camera.getWorldMatrix(),
    ).normalize();
    expect(Math.abs(Vector3.Dot(normal, cameraForward))).toBeCloseTo(1, 5);
    const centre = first.add(third).scaleInPlace(0.5);
    expect(centre.length()).toBeCloseTo(0);
  });

  it('has a smooth symmetric kernel with no luminous samples beyond its support', () => {
    const pixels = buildCatalogueDensityKernel();
    const size = CATALOGUE_DENSITY_KERNEL_SIZE;
    const alpha = (x: number, y: number) => pixels[(y * size + x) * 4 + 3];
    const midpoint = size / 2;
    expect(alpha(midpoint, midpoint)).toBeGreaterThan(250);
    expect(alpha(midpoint + 8, midpoint)).toBeLessThan(
      alpha(midpoint, midpoint),
    );
    expect(alpha(midpoint + 16, midpoint)).toBeLessThan(
      alpha(midpoint + 8, midpoint),
    );
    for (let y = 0; y < size; y += 1) {
      for (let x = 0; x < size; x += 1) {
        expect(alpha(x, y)).toBe(alpha(size - 1 - x, size - 1 - y));
        if (
          ((2 * x) / (size - 1) - 1) ** 2 + ((2 * y) / (size - 1) - 1) ** 2 >=
          1
        ) {
          expect(alpha(x, y)).toBe(0);
        }
      }
    }
  });

  it('allocates no replacement for missing or empty data and releases owned resources', () => {
    const { scene } = createScene();
    expect(createCatalogueDensityMesh(scene, null)).toBeNull();
    expect(
      createCatalogueDensityMesh(scene, {
        ...density,
        payload: buildFixtureCatalogueDensity([], fixtureOptions),
      }),
    ).toBeNull();
    expect(scene.meshes).toHaveLength(0);
    expect(scene.materials).toHaveLength(0);
    expect(scene.textures).toHaveLength(0);

    const baselineObservers =
      scene.onBeforeCameraRenderObservable.observers.length;
    const mesh = createCatalogueDensityMesh(scene, density)!;
    const material = mesh.material;
    expect(scene.onBeforeCameraRenderObservable.observers).toHaveLength(
      baselineObservers + 1,
    );
    mesh.dispose();
    expect(scene.materials).not.toContain(material);
    expect(scene.textures).toHaveLength(0);
    expect(scene.onBeforeCameraRenderObservable.hasObservers()).toBe(false);
  });
});
