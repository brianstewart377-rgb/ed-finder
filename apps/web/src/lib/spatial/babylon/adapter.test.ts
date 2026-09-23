import { describe, expect, it, vi } from 'vitest';
import { NullEngine } from '@babylonjs/core/Engines/nullEngine.js';
import { Matrix } from '@babylonjs/core/Maths/math.vector.js';

import type { GalaxySceneContract, SystemSceneContract } from '../contracts';
import { buildFixtureCatalogueDensity } from '../galaxy-density.fixture';
import { createCatalogueDensityContribution } from '../galaxy-density';
import {
  DENSITY_CROSSFADE_FAR_LY,
  DENSITY_CROSSFADE_NEAR_LY,
} from '../galaxy-density-crossfade';
import { createCommanderHistoryContribution } from '../commander-history';
import {
  createGalaxyNebulaeContribution,
  type GalaxyNebulaePayload,
} from '../galaxy-nebulae';
import type { SpatialBackendSession } from '../lifecycle';
import {
  createBabylonGalaxyScene,
  createBabylonSession,
  createBabylonSystemScene,
  createBabylonSpatialRuntime,
  commanderHistoryHeatColour,
  galaxyStarMarkerSizeLy,
  nebulaCloudRadiusLy,
  subscribeToBabylonResourceEvents,
  type BabylonRuntimeDependencies,
} from './adapter';

const createSession = (backend: 'WEBGPU' | 'WEBGL2') =>
  ({
    backend,
    resize: vi.fn(),
    render: vi.fn(),
    dispose: vi.fn(),
  }) satisfies SpatialBackendSession;

describe('Babylon spatial adapter boundary', () => {
  it('renders an interactive three-dimensional system scene with pickable bodies and schematic orbits', () => {
    const engine = new NullEngine();
    const contract: SystemSceneContract = {
      kind: 'system',
      revision: 3,
      systemId64: '42',
      fidelity: 'S1',
      camera: {
        systemId64: '42',
        focus: { kind: 'system', systemId64: '42' },
        semanticDistance: 32,
        bearingRad: -0.8,
        pitchRad: 0.56,
        revision: 3,
      },
      bodies: [
        {
          ref: { systemId64: '42', bodyId: 0 },
          name: 'Test Star',
          class: { value: 'Star', representation: 'AUTHORITATIVE' },
          subtype: {
            value: 'G (White-Yellow) Star',
            representation: 'AUTHORITATIVE',
          },
          distanceFromArrivalLs: {
            value: 0,
            representation: 'AUTHORITATIVE',
          },
          displayRadius: 2.2,
          orbital: { placement: 'DETERMINISTIC_SCHEMATIC' },
          rings: { state: 'ABSENT', bands: [] },
        },
        {
          ref: { systemId64: '42', bodyId: 2 },
          name: 'Test Giant',
          class: { value: 'Planet', representation: 'AUTHORITATIVE' },
          subtype: {
            value: 'Gas giant with water based life',
            representation: 'AUTHORITATIVE',
          },
          distanceFromArrivalLs: {
            value: 12_000,
            representation: 'AUTHORITATIVE',
          },
          displayRadius: 1.1,
          orbital: { placement: 'DETERMINISTIC_SCHEMATIC' },
          rings: { state: 'PRESENT', bands: [] },
        },
      ],
      infrastructure: [],
      contributions: [],
    };

    const product = createBabylonSystemScene(engine, contract);
    expect(product.bodies).toHaveLength(2);
    expect(product.bodies.every((body) => body.mesh.isPickable)).toBe(true);
    expect(product.bodies[1]?.ringMeshes).toHaveLength(1);
    expect(product.orbitMesh?.metadata).toMatchObject({
      spatialLayer: {
        representation: 'SCHEMATIC',
        meaning: 'ordered-distance-layout-not-observed-orbital-elements',
      },
    });
    expect(product.scene.metadata).toMatchObject({
      spatialScene: {
        kind: 'system',
        bodyCount: 2,
        visualProfile: {
          threeDimensional: true,
          physicalScale: false,
        },
      },
    });

    product.scene.dispose();
    engine.dispose();
  });

  it('accepts a system contract through the shared runtime session', () => {
    const engine = new NullEngine();
    const session = createBabylonSession(engine, 'WEBGL2');
    const events = vi.fn();
    const contract: SystemSceneContract = {
      kind: 'system',
      revision: 21,
      systemId64: '99',
      fidelity: 'S0',
      camera: {
        systemId64: '99',
        focus: { kind: 'system', systemId64: '99' },
        semanticDistance: 24,
        bearingRad: 0,
        pitchRad: 0.5,
        revision: 21,
      },
      bodies: [],
      infrastructure: [],
      contributions: [],
    };

    expect(
      session.execute?.({ type: 'LOAD_SCENE', scene: contract }, events),
    ).toEqual({ status: 'executed' });
    expect(events).toHaveBeenCalledWith({
      type: 'CAMERA_CHANGED',
      camera: contract.camera,
    });
    expect(
      session.execute?.(
        {
          type: 'SET_CAMERA',
          camera: { ...contract.camera, semanticDistance: 18, revision: 22 },
        },
        events,
      ),
    ).toEqual({ status: 'executed' });

    session.dispose();
  });

  it('renders exactly the accepted catalogue cells and exposes a rendered-layer receipt', () => {
    const payload = buildFixtureCatalogueDensity(
      [
        { positionLy: { x: 10, y: -5, z: 20 } },
        { positionLy: { x: 14, y: -3, z: 25 } },
        { positionLy: { x: 420, y: 20, z: -200 } },
      ],
      {
        generationId: 'fixture:adapter-density-v1',
        pyramidVersion: 'fixture-pyramid-v1',
        level: 2,
        cellSizeLy: 100,
        cellOriginLy: { x: -1_000, y: -1_000, z: -1_000 },
        boundsLy: {
          min: { x: -1_000, y: -1_000, z: -1_000 },
          max: { x: 1_000, y: 1_000, z: 1_000 },
        },
        coverageAsOf: '2026-09-13T00:00:00Z',
      },
    );
    const sceneContract: GalaxySceneContract = {
      kind: 'galaxy',
      revision: 14,
      camera: {
        focusLy: { x: 0, y: 0, z: 0 },
        distanceLy: 2_500,
        bearingRad: 0,
        pitchRad: 0.5,
        projection: 'perspective',
        revision: 14,
      },
      selection: [],
      contributions: [createCatalogueDensityContribution(payload, 14)],
    };
    const engine = new NullEngine({
      renderWidth: 640,
      renderHeight: 360,
      textureSize: 512,
      deterministicLockstep: true,
      lockstepMaxSteps: 1,
    });

    const product = createBabylonGalaxyScene(engine, sceneContract);

    expect(product.densityMesh).not.toBeNull();
    expect(product.densityMesh?.thinInstanceCount).toBe(payload.cells.length);
    expect(product.densityMesh?.isPickable).toBe(false);
    expect(product.renderedLayers).toEqual([
      {
        contributionId: 'catalogue-density-base',
        contributionRevision: 14,
        layerId: 'catalogue-density',
        layerVersion: 1,
        representation: 'DERIVED',
        acceptedTargetCount: payload.cells.length,
        renderedTargetCount: payload.cells.length,
        sourceGeneration: 'fixture:adapter-density-v1',
      },
    ]);
    expect(product.densityMesh?.metadata).toMatchObject({
      spatialLayer: {
        id: 'catalogue-density',
        sourceSystemCount: 3,
        coveredSystemCount: 3,
        renderedCellCount: payload.cells.length,
        generatedOccupancy: false,
      },
    });
    expect(product.scene.getMeshByName('volumetric-galaxy')).toBeNull();
    expect(product.referenceGrid.spec.nominalPlaneY).toBe(0);
    expect(product.referenceGrid.spec.majorStepLy).toBe(
      product.referenceGrid.spec.minorStepLy * 5,
    );
    expect(product.referenceGrid.minorMesh?.metadata).toMatchObject({
      spatialLayer: {
        id: 'galaxy-reference-grid',
        representation: 'SCHEMATIC',
        affectsSystemPositions: false,
      },
    });

    product.scene.dispose();
    engine.dispose();
  });

  it('renders no density geometry when the factual layer is absent', () => {
    const engine = new NullEngine();
    const sceneContract: GalaxySceneContract = {
      kind: 'galaxy',
      revision: 15,
      camera: {
        focusLy: { x: 0, y: 0, z: 0 },
        distanceLy: 80,
        bearingRad: 0,
        pitchRad: 0.5,
        projection: 'perspective',
        revision: 15,
      },
      selection: [],
      contributions: [],
    };

    const product = createBabylonGalaxyScene(engine, sceneContract);

    expect(product.densityMesh).toBeNull();
    expect(product.renderedLayers).toEqual([]);
    expect(product.scene.getMeshByName('catalogue-density-cells')).toBeNull();

    product.scene.dispose();
    engine.dispose();
  });

  it('keeps stars fully opaque when zoomed out with no density layer (inert path)', () => {
    const engine = new NullEngine();
    const sceneContract: GalaxySceneContract = {
      kind: 'galaxy',
      revision: 1,
      camera: {
        focusLy: { x: 0, y: 0, z: 0 },
        distanceLy: DENSITY_CROSSFADE_FAR_LY + 1,
        bearingRad: 0,
        pitchRad: 0.5,
        projection: 'perspective',
        revision: 1,
      },
      selection: [],
      contributions: [],
    };

    const product = createBabylonGalaxyScene(engine, sceneContract);

    expect(product.densityMesh).toBeNull();
    expect(
      product.scene.getMeshByName('finder-system-instances')?.material?.alpha,
    ).toBeCloseTo(1, 5);

    product.scene.dispose();
    engine.dispose();
  });

  it('cross-fades density and star presentations as the camera zooms through the semantic band', () => {
    const payload = buildFixtureCatalogueDensity(
      [
        { positionLy: { x: 10, y: -5, z: 20 } },
        { positionLy: { x: 14, y: -3, z: 25 } },
      ],
      {
        generationId: 'fixture:adapter-crossfade-v1',
        pyramidVersion: 'fixture-pyramid-v1',
        level: 2,
        cellSizeLy: 100,
        cellOriginLy: { x: -1_000, y: -1_000, z: -1_000 },
        boundsLy: {
          min: { x: -1_000, y: -1_000, z: -1_000 },
          max: { x: 1_000, y: 1_000, z: 1_000 },
        },
        coverageAsOf: '2026-09-13T00:00:00Z',
      },
    );
    const baseCamera: GalaxySceneContract['camera'] = {
      focusLy: { x: 0, y: 0, z: 0 },
      distanceLy: 2_500,
      bearingRad: 0,
      pitchRad: 0.5,
      projection: 'perspective',
      revision: 1,
    };
    const sceneContract: GalaxySceneContract = {
      kind: 'galaxy',
      revision: 1,
      camera: baseCamera,
      selection: [],
      contributions: [createCatalogueDensityContribution(payload, 1)],
    };

    const engine = new NullEngine();
    const session = createBabylonSession(engine, 'WEBGL2');
    const events = vi.fn();

    expect(
      session.execute?.({ type: 'LOAD_SCENE', scene: sceneContract }, events),
    ).toEqual({ status: 'executed' });

    const scene = engine.scenes[engine.scenes.length - 1]!;
    const densityMesh = scene.getMeshByName('catalogue-density-cells');
    const starMesh = scene.getMeshByName('finder-system-instances');
    expect(densityMesh).not.toBeNull();
    expect(starMesh).not.toBeNull();

    const setDistance = (distanceLy: number, revision: number): void => {
      expect(
        session.execute?.(
          {
            type: 'SET_CAMERA',
            camera: { ...baseCamera, distanceLy, revision },
          },
          events,
        ),
      ).toEqual({ status: 'executed' });
    };

    setDistance(DENSITY_CROSSFADE_NEAR_LY - 1, 2);
    expect(densityMesh?.material?.alpha).toBeCloseTo(0, 5);
    expect(starMesh?.material?.alpha).toBeCloseTo(1, 5);

    setDistance((DENSITY_CROSSFADE_NEAR_LY + DENSITY_CROSSFADE_FAR_LY) / 2, 3);
    expect(densityMesh?.material?.alpha).toBeCloseTo(0.45, 5);
    expect(starMesh?.material?.alpha).toBeCloseTo(0.5, 5);

    setDistance(DENSITY_CROSSFADE_FAR_LY + 1, 4);
    expect(densityMesh?.material?.alpha).toBeCloseTo(0.9, 5);
    expect(starMesh?.material?.alpha).toBeCloseTo(0, 5);

    session.dispose();
    engine.dispose();
  });

  it('applies the density cross-fade immediately on LOAD_SCENE, without waiting for a camera move', () => {
    const payload = buildFixtureCatalogueDensity(
      [
        { positionLy: { x: 10, y: -5, z: 20 } },
        { positionLy: { x: 14, y: -3, z: 25 } },
      ],
      {
        generationId: 'fixture:adapter-crossfade-load-v1',
        pyramidVersion: 'fixture-pyramid-v1',
        level: 2,
        cellSizeLy: 100,
        cellOriginLy: { x: -1_000, y: -1_000, z: -1_000 },
        boundsLy: {
          min: { x: -1_000, y: -1_000, z: -1_000 },
          max: { x: 1_000, y: 1_000, z: 1_000 },
        },
        coverageAsOf: '2026-09-13T00:00:00Z',
      },
    );
    const midBandCamera: GalaxySceneContract['camera'] = {
      focusLy: { x: 0, y: 0, z: 0 },
      distanceLy: (DENSITY_CROSSFADE_NEAR_LY + DENSITY_CROSSFADE_FAR_LY) / 2,
      bearingRad: 0,
      pitchRad: 0.5,
      projection: 'perspective',
      revision: 1,
    };
    const sceneContract: GalaxySceneContract = {
      kind: 'galaxy',
      revision: 1,
      camera: midBandCamera,
      selection: [],
      contributions: [createCatalogueDensityContribution(payload, 1)],
    };

    const engine = new NullEngine();
    const session = createBabylonSession(engine, 'WEBGL2');
    const events = vi.fn();

    expect(
      session.execute?.({ type: 'LOAD_SCENE', scene: sceneContract }, events),
    ).toEqual({ status: 'executed' });

    const scene = engine.scenes[engine.scenes.length - 1]!;
    const densityMesh = scene.getMeshByName('catalogue-density-cells');
    const starMesh = scene.getMeshByName('finder-system-instances');

    expect(densityMesh?.material?.alpha).toBeCloseTo(0.45, 5);
    expect(starMesh?.material?.alpha).toBeCloseTo(0.5, 5);

    session.dispose();
    engine.dispose();
  });

  it('applies the density cross-fade immediately on PATCH_CONTRIBUTION, without waiting for a camera move', () => {
    const midBandCamera: GalaxySceneContract['camera'] = {
      focusLy: { x: 0, y: 0, z: 0 },
      distanceLy: (DENSITY_CROSSFADE_NEAR_LY + DENSITY_CROSSFADE_FAR_LY) / 2,
      bearingRad: 0,
      pitchRad: 0.5,
      projection: 'perspective',
      revision: 1,
    };
    const sceneContract: GalaxySceneContract = {
      kind: 'galaxy',
      revision: 1,
      camera: midBandCamera,
      selection: [],
      contributions: [],
    };

    const engine = new NullEngine();
    const session = createBabylonSession(engine, 'WEBGL2');
    const events = vi.fn();

    expect(
      session.execute?.({ type: 'LOAD_SCENE', scene: sceneContract }, events),
    ).toEqual({ status: 'executed' });

    const payload = buildFixtureCatalogueDensity(
      [
        { positionLy: { x: 10, y: -5, z: 20 } },
        { positionLy: { x: 14, y: -3, z: 25 } },
      ],
      {
        generationId: 'fixture:adapter-crossfade-patch-v1',
        pyramidVersion: 'fixture-pyramid-v1',
        level: 2,
        cellSizeLy: 100,
        cellOriginLy: { x: -1_000, y: -1_000, z: -1_000 },
        boundsLy: {
          min: { x: -1_000, y: -1_000, z: -1_000 },
          max: { x: 1_000, y: 1_000, z: 1_000 },
        },
        coverageAsOf: '2026-09-13T00:00:00Z',
      },
    );
    const contribution = createCatalogueDensityContribution(payload, 2);

    expect(
      session.execute?.({ type: 'PATCH_CONTRIBUTION', contribution }, events),
    ).toEqual({ status: 'executed' });

    const scene = engine.scenes[engine.scenes.length - 1]!;
    const densityMesh = scene.getMeshByName('catalogue-density-cells');
    const starMesh = scene.getMeshByName('finder-system-instances');

    expect(densityMesh?.material?.alpha).toBeCloseTo(0.45, 5);
    expect(starMesh?.material?.alpha).toBeCloseTo(0.5, 5);

    session.dispose();
    engine.dispose();
  });

  it('keeps finder search-result markers opaque through the density cross-fade at wide zoom', () => {
    const payload = buildFixtureCatalogueDensity(
      [
        { positionLy: { x: 10, y: -5, z: 20 } },
        { positionLy: { x: 14, y: -3, z: 25 } },
      ],
      {
        generationId: 'fixture:adapter-finder-preserve-v1',
        pyramidVersion: 'fixture-pyramid-v1',
        level: 2,
        cellSizeLy: 100,
        cellOriginLy: { x: -1_000, y: -1_000, z: -1_000 },
        boundsLy: {
          min: { x: -1_000, y: -1_000, z: -1_000 },
          max: { x: 1_000, y: 1_000, z: 1_000 },
        },
        coverageAsOf: '2026-09-13T00:00:00Z',
      },
    );
    const baseCamera: GalaxySceneContract['camera'] = {
      focusLy: { x: 0, y: 0, z: 0 },
      distanceLy: 2_500,
      bearingRad: 0,
      pitchRad: 0.5,
      projection: 'perspective',
      revision: 1,
    };
    const sceneContract: GalaxySceneContract = {
      kind: 'galaxy',
      revision: 1,
      camera: baseCamera,
      selection: [],
      contributions: [
        createCatalogueDensityContribution(payload, 1),
        {
          id: 'finder-results',
          owner: 'FINDER',
          revision: 1,
          layers: [
            {
              id: 'finder-systems',
              version: 1,
              representation: 'AUTHORITATIVE',
              targetCount: 1,
              truncated: false,
              payload: {
                systems: [
                  {
                    systemId64: '1',
                    name: 'Sol',
                    positionLy: { x: 0, y: 0, z: 0 },
                  },
                ],
              },
            },
          ],
        },
      ],
    };

    const engine = new NullEngine();
    const session = createBabylonSession(engine, 'WEBGL2');
    const events = vi.fn();

    expect(
      session.execute?.({ type: 'LOAD_SCENE', scene: sceneContract }, events),
    ).toEqual({ status: 'executed' });

    const scene = engine.scenes[engine.scenes.length - 1]!;
    const densityMesh = scene.getMeshByName('catalogue-density-cells');
    const starMesh = scene.getMeshByName('finder-system-instances');

    // Zoom fully out into the density-dominant band.
    expect(
      session.execute?.(
        {
          type: 'SET_CAMERA',
          camera: {
            ...baseCamera,
            distanceLy: DENSITY_CROSSFADE_FAR_LY + 1,
            revision: 2,
          },
        },
        events,
      ),
    ).toEqual({ status: 'executed' });

    // Density presents fully, but finder markers must NOT fade with catalogue
    // stars — they stay opaque so search results never vanish at wide zoom.
    expect(densityMesh?.material?.alpha).toBeCloseTo(0.9, 5);
    expect(starMesh?.material?.alpha).toBeCloseTo(1, 5);

    session.dispose();
    engine.dispose();
  });

  it('fades catalogue-only stars, their accent rings, and their pickability into the density field', () => {
    const payload = buildFixtureCatalogueDensity(
      [
        { positionLy: { x: 10, y: -5, z: 20 } },
        { positionLy: { x: 14, y: -3, z: 25 } },
      ],
      {
        generationId: 'fixture:adapter-catalogue-fade-v1',
        pyramidVersion: 'fixture-pyramid-v1',
        level: 2,
        cellSizeLy: 100,
        cellOriginLy: { x: -1_000, y: -1_000, z: -1_000 },
        boundsLy: {
          min: { x: -1_000, y: -1_000, z: -1_000 },
          max: { x: 1_000, y: 1_000, z: 1_000 },
        },
        coverageAsOf: '2026-09-13T00:00:00Z',
      },
    );
    const baseCamera: GalaxySceneContract['camera'] = {
      focusLy: { x: 0, y: 0, z: 0 },
      distanceLy: 2_500,
      bearingRad: 0,
      pitchRad: 0.5,
      projection: 'perspective',
      revision: 1,
    };
    const sceneContract: GalaxySceneContract = {
      kind: 'galaxy',
      revision: 1,
      camera: baseCamera,
      selection: [],
      contributions: [
        createCatalogueDensityContribution(payload, 1),
        {
          id: 'catalogue-viewport-stars',
          owner: 'CATALOGUE',
          revision: 1,
          layers: [
            {
              id: 'catalogue-systems',
              version: 1,
              representation: 'AUTHORITATIVE',
              targetCount: 1,
              truncated: false,
              payload: {
                systems: [
                  {
                    systemId64: '9',
                    name: 'Void',
                    positionLy: { x: 5, y: 0, z: 5 },
                    primaryStar: { type: 'Black Hole' },
                  },
                ],
              },
            },
          ],
        },
      ],
    };

    const engine = new NullEngine();
    const session = createBabylonSession(engine, 'WEBGL2');
    const events = vi.fn();

    expect(
      session.execute?.({ type: 'LOAD_SCENE', scene: sceneContract }, events),
    ).toEqual({ status: 'executed' });

    const scene = engine.scenes[engine.scenes.length - 1]!;
    const starMesh = scene.getMeshByName('finder-system-instances');
    const accentRing = scene.getMeshByName('stellar-icon-ring-9');
    expect(accentRing).not.toBeNull();

    const setDistance = (distanceLy: number, revision: number): void => {
      expect(
        session.execute?.(
          {
            type: 'SET_CAMERA',
            camera: { ...baseCamera, distanceLy, revision },
          },
          events,
        ),
      ).toEqual({ status: 'executed' });
    };

    // Star-dominant end: catalogue stars, accent rings and picking are live.
    setDistance(DENSITY_CROSSFADE_NEAR_LY - 1, 2);
    expect(starMesh?.material?.alpha).toBeCloseTo(1, 5);
    expect(accentRing?.material?.alpha).toBeCloseTo(1, 5);
    expect(starMesh?.isPickable).toBe(true);
    expect(
      (starMesh as unknown as { thinInstanceEnablePicking: boolean })
        .thinInstanceEnablePicking,
    ).toBe(true);

    // Density-dominant end: catalogue stars and their rings fade to nothing and
    // stop capturing picks so they cannot block region selection.
    setDistance(DENSITY_CROSSFADE_FAR_LY + 1, 3);
    expect(starMesh?.material?.alpha).toBeCloseTo(0, 5);
    expect(accentRing?.material?.alpha).toBeCloseTo(0, 5);
    expect(starMesh?.isPickable).toBe(false);
    expect(
      (starMesh as unknown as { thinInstanceEnablePicking: boolean })
        .thinInstanceEnablePicking,
    ).toBe(false);

    session.dispose();
    engine.dispose();
  });

  it('scales only star presentation radius as camera distance changes', () => {
    expect(galaxyStarMarkerSizeLy(100)).toBeCloseTo(0.6);
    expect(galaxyStarMarkerSizeLy(1_000)).toBeCloseTo(6);
    expect(() => galaxyStarMarkerSizeLy(0)).toThrow(/positive/u);
  });

  it('renders catalogue star classes as distinct icon colours and scales without moving them', () => {
    const engine = new NullEngine();
    const sceneContract: GalaxySceneContract = {
      kind: 'galaxy',
      revision: 16,
      camera: {
        focusLy: { x: 0, y: 0, z: 0 },
        distanceLy: 800,
        bearingRad: 0,
        pitchRad: 0.5,
        projection: 'perspective',
        revision: 16,
      },
      selection: [],
      contributions: [
        {
          id: 'finder-results',
          owner: 'FINDER',
          revision: 16,
          layers: [
            {
              id: 'finder-systems',
              version: 1,
              representation: 'AUTHORITATIVE',
              targetCount: 3,
              truncated: false,
              payload: {
                systems: [
                  {
                    systemId64: '1',
                    name: 'Golden One',
                    positionLy: { x: 11, y: -2, z: 35 },
                    primaryStar: { type: 'G', subtype: '2 V' },
                  },
                  {
                    systemId64: '2',
                    name: 'Blue Giant',
                    positionLy: { x: -14, y: 8, z: 120 },
                    primaryStar: { type: 'B', subtype: 'Ia Supergiant' },
                  },
                  {
                    systemId64: '3',
                    name: 'Dark Ring',
                    positionLy: { x: 70, y: 0, z: -9 },
                    primaryStar: { type: 'Black Hole' },
                  },
                ],
              },
            },
          ],
        },
      ],
    };

    const product = createBabylonGalaxyScene(engine, sceneContract);
    const matrixBuffer = product.starInstanceMatrices;
    const colourBuffer = product.starInstanceColours;

    expect(product.stellarPresentations.map(({ glyph }) => glyph)).toEqual([
      'main-sequence-g',
      'giant-blue',
      'black-hole',
    ]);
    expect(Array.from(colourBuffer.slice(0, 4))).not.toEqual(
      Array.from(colourBuffer.slice(4, 8)),
    );
    expect(product.stellarAccentMeshes).toHaveLength(1);
    expect(product.stellarAccentMeshes[0]?.metadata).toMatchObject({
      spatialLayer: { stellarGlyph: 'black-hole', presentationOnly: true },
    });
    [
      [11, -2, 35],
      [-14, 8, 120],
      [70, 0, -9],
    ].forEach((expected, index) => {
      const matrix = Matrix.FromArray(matrixBuffer, index * 16);
      expect(matrix.getTranslation().asArray()).toEqual(expected);
    });

    product.scene.dispose();
    engine.dispose();
  });

  it('renders journal visits in a separate non-pickable commander heatmap', () => {
    const engine = new NullEngine();
    const history = createCommanderHistoryContribution(
      'density',
      [
        {
          kind: 'density',
          x: 100,
          y: -50,
          z: 300,
          visitCount: 2,
          firstVisitedAt: '2025-01-01T00:00:00Z',
          lastVisitedAt: '2025-02-01T00:00:00Z',
          completionState: 'partial',
          cellSizeLy: 50,
        },
        {
          kind: 'density',
          x: 150,
          y: -50,
          z: 350,
          visitCount: 18,
          firstVisitedAt: '2025-01-01T00:00:00Z',
          lastVisitedAt: '2026-09-14T00:00:00Z',
          completionState: 'complete',
          cellSizeLy: 50,
        },
      ],
      22,
      false,
    );
    const sceneContract: GalaxySceneContract = {
      kind: 'galaxy',
      revision: 22,
      camera: {
        focusLy: { x: 100, y: -50, z: 300 },
        distanceLy: 500,
        bearingRad: 0,
        pitchRad: 0.6,
        projection: 'perspective',
        revision: 22,
      },
      selection: [],
      contributions: [history],
    };

    const product = createBabylonGalaxyScene(engine, sceneContract);

    expect(product.commanderHistoryMesh?.thinInstanceCount).toBe(2);
    expect(product.commanderHistoryMesh?.isPickable).toBe(false);
    expect(product.commanderHistoryMesh?.metadata).toMatchObject({
      spatialLayer: {
        id: 'commander-history-heatmap',
        owner: 'COMMANDER_HISTORY',
        source: 'journal-log',
        catalogueDensity: false,
      },
    });
    expect(product.renderedLayers).toContainEqual({
      contributionId: 'commander-history',
      contributionRevision: 22,
      layerId: 'commander-history-heatmap',
      layerVersion: 1,
      representation: 'DERIVED',
      acceptedTargetCount: 2,
      renderedTargetCount: 2,
    });
    expect(commanderHistoryHeatColour(2, 18)).not.toEqual(
      commanderHistoryHeatColour(18, 18),
    );

    product.scene.dispose();
    engine.dispose();
  });

  it('renders attributed nebula landmarks at their authoritative coordinates with schematic extents', () => {
    const payload: GalaxyNebulaePayload = {
      datasetId: 'fixture-nebulae',
      sourceUrl: 'https://edastro.com/mapcharts/files/nebulae-coordinates.csv',
      catalogueUrl: 'https://edastro.com/mapcharts/files.html',
      rightsNotice: 'Copyright © CMDR Orvidius — All Rights Reserved',
      usageBasis:
        'Purpose-published automation-ready CSV; non-commercial use accepted by the ED-Finder owner',
      attribution: 'EDAstro / CMDR Orvidius',
      sourceLastModified: 'Sun, 13 Sep 2026 15:00:58 GMT',
      sourceByteCount: 123,
      sourceSha256: 'a'.repeat(64),
      nebulae: [
        {
          id: 'GMP:1',
          source: 'GMP',
          sourceId: '1',
          name: 'Purple Cloud',
          systemName: 'Cloud AA-A h1',
          regionName: null,
          regionId: 18,
          kind: 'nebula',
          positionLy: {
            value: { x: 125, y: -34, z: 912 },
            representation: 'AUTHORITATIVE',
          },
          poiUrl: null,
        },
      ],
    };
    const engine = new NullEngine();
    const sceneContract: GalaxySceneContract = {
      kind: 'galaxy',
      revision: 17,
      camera: {
        focusLy: { x: 0, y: 0, z: 0 },
        distanceLy: 10_000,
        bearingRad: 0,
        pitchRad: 0.5,
        projection: 'perspective',
        revision: 17,
      },
      selection: [],
      contributions: [createGalaxyNebulaeContribution(payload, 17)],
    };

    const product = createBabylonGalaxyScene(engine, sceneContract);
    expect(product.nebulaMesh?.thinInstanceCount).toBe(1);
    expect(product.nebulaMesh?.isPickable).toBe(false);
    expect(product.nebulaMesh?.metadata).toMatchObject({
      spatialLayer: {
        id: 'galaxy-nebulae',
        coordinateRepresentation: 'AUTHORITATIVE',
        radiusMeaning: 'schematic-map-presentation-not-physical-extent',
        rightsNotice: 'Copyright © CMDR Orvidius — All Rights Reserved',
      },
    });
    const matrixData = product.nebulaMesh?.thinInstanceGetWorldMatrices()[0];
    expect(matrixData?.getTranslation().asArray()).toEqual([125, -34, 912]);
    expect(nebulaCloudRadiusLy('planetary-nebula')).toBeLessThan(
      nebulaCloudRadiusLy('nebula'),
    );
    expect(product.renderedLayers[0]).toMatchObject({
      layerId: 'galaxy-nebulae',
      representation: 'AMBIENT',
      acceptedTargetCount: 1,
      renderedTargetCount: 1,
    });

    product.scene.dispose();
    engine.dispose();
  });

  it('hides nebula landmark clouds at system-selection distance and shows them at galaxy-overview distance', () => {
    const payload: GalaxyNebulaePayload = {
      datasetId: 'fixture-nebulae',
      sourceUrl: 'https://edastro.com/mapcharts/files/nebulae-coordinates.csv',
      catalogueUrl: 'https://edastro.com/mapcharts/files.html',
      rightsNotice: 'Copyright © CMDR Orvidius — All Rights Reserved',
      usageBasis:
        'Purpose-published automation-ready CSV; non-commercial use accepted by the ED-Finder owner',
      attribution: 'EDAstro / CMDR Orvidius',
      sourceLastModified: 'Sun, 13 Sep 2026 15:00:58 GMT',
      sourceByteCount: 123,
      sourceSha256: 'a'.repeat(64),
      nebulae: [
        {
          id: 'GMP:1',
          source: 'GMP',
          sourceId: '1',
          name: 'Purple Cloud',
          systemName: 'Cloud AA-A h1',
          regionName: null,
          regionId: 18,
          kind: 'nebula',
          positionLy: {
            value: { x: 125, y: -34, z: 912 },
            representation: 'AUTHORITATIVE',
          },
          poiUrl: null,
        },
      ],
    };
    const buildContractAt = (distanceLy: number, revision: number) =>
      ({
        kind: 'galaxy',
        revision,
        camera: {
          focusLy: { x: 0, y: 0, z: 0 },
          distanceLy,
          bearingRad: 0,
          pitchRad: 0.5,
          projection: 'perspective',
          revision,
        },
        selection: [],
        contributions: [createGalaxyNebulaeContribution(payload, revision)],
      }) satisfies GalaxySceneContract;

    const closeEngine = new NullEngine();
    // ~400 ly matches ExploreWorkspace's system-selection camera target; the
    // camera sits inside several landmark clouds at this distance, so the
    // layer must be fully hidden.
    const closeProduct = createBabylonGalaxyScene(
      closeEngine,
      buildContractAt(400, 1),
    );
    expect(closeProduct.nebulaMesh?.isEnabled()).toBe(false);
    expect(closeProduct.nebulaMesh?.visibility).toBe(0);
    closeProduct.scene.dispose();
    closeEngine.dispose();

    const farEngine = new NullEngine();
    // Galaxy-overview scale (tens of thousands of ly): landmarks stay fully
    // visible, preserving this branch's existing overview appearance.
    const farProduct = createBabylonGalaxyScene(
      farEngine,
      buildContractAt(118_000, 2),
    );
    expect(farProduct.nebulaMesh?.isEnabled()).toBe(true);
    expect(farProduct.nebulaMesh?.visibility).toBe(1);
    farProduct.scene.dispose();
    farEngine.dispose();
  });

  it.each([
    ['WEBGPU', 'webgpu-device-lost', 'webgpu-device-restored'],
    ['WEBGL2', 'webgl2-context-lost', 'webgl2-context-restored'],
  ] as const)(
    'maps %s engine resource observables and removes both observers once',
    (backend, lostDetail, restoredDetail) => {
      let notifyLost: () => void = () => undefined;
      let notifyRestored: () => void = () => undefined;
      const removeLost = vi.fn();
      const removeRestored = vi.fn();
      const engine = {
        onContextLostObservable: {
          add: vi.fn((listener: () => void) => {
            notifyLost = listener;
            return { remove: removeLost };
          }),
        },
        onContextRestoredObservable: {
          add: vi.fn((listener: () => void) => {
            notifyRestored = listener;
            return { remove: removeRestored };
          }),
        },
      } as unknown as Parameters<typeof subscribeToBabylonResourceEvents>[0];
      const listener = vi.fn();

      const unsubscribe = subscribeToBabylonResourceEvents(
        engine,
        backend,
        listener,
      );
      notifyLost();
      notifyRestored();

      expect(listener.mock.calls.map(([event]) => event)).toEqual([
        { state: 'lost', detail: lostDetail },
        { state: 'recovered', detail: restoredDetail },
      ]);

      unsubscribe();
      unsubscribe();
      expect(removeLost).toHaveBeenCalledOnce();
      expect(removeRestored).toHaveBeenCalledOnce();
    },
  );

  it('uses a fresh canvas for WebGL2 after WebGPU initialization fails', async () => {
    const original = document.createElement('canvas');
    const replacement = document.createElement('canvas');
    const webGl2 = createSession('WEBGL2');
    const dependencies: BabylonRuntimeDependencies = {
      createWebGpu: vi
        .fn()
        .mockRejectedValue(new Error('initialization failed')),
      createWebGl2: vi.fn().mockReturnValue(webGl2),
      replaceCanvas: vi.fn().mockReturnValue(replacement),
    };
    const runtime = createBabylonSpatialRuntime(
      original,
      vi.fn(),
      dependencies,
    );

    await expect(runtime.start()).resolves.toEqual({
      state: 'ready',
      backend: 'WEBGL2',
    });

    expect(dependencies.replaceCanvas).toHaveBeenCalledWith(original);
    expect(dependencies.createWebGl2).toHaveBeenCalledWith(replacement);
  });

  it('keeps the original canvas when WebGPU is simply unsupported', async () => {
    const original = document.createElement('canvas');
    const webGl2 = createSession('WEBGL2');
    const dependencies: BabylonRuntimeDependencies = {
      createWebGpu: vi.fn().mockResolvedValue(null),
      createWebGl2: vi.fn().mockReturnValue(webGl2),
      replaceCanvas: vi.fn(),
    };
    const runtime = createBabylonSpatialRuntime(
      original,
      vi.fn(),
      dependencies,
    );

    await runtime.start();

    expect(dependencies.replaceCanvas).not.toHaveBeenCalled();
    expect(dependencies.createWebGl2).toHaveBeenCalledWith(original);
  });
});
