import { describe, expect, it } from 'vitest';
import { NullEngine } from '@babylonjs/core/Engines/nullEngine.js';
import { ImageProcessingConfiguration } from '@babylonjs/core/Materials/imageProcessingConfiguration.js';

import { buildAuthoritativeGalaxyRegionsAsset } from '../../../vite.galaxy-regions';
import {
  createBabylonGalaxyScene,
  updateGalaxyRegionFillAppearance,
} from './babylon/adapter';
import type { GalaxySceneContract } from './contracts';
import {
  buildGalaxyRegionFillGeometry,
  createGalaxyRegionsContribution,
  findGalaxyRegionAt,
  GALAXY_REGION_ASSET_BUDGET_BYTES,
  GALAXY_REGION_BOUNDARY_LIMIT,
  GALAXY_REGION_COUNT,
  GALAXY_REGION_FILL_RECTANGLE_LIMIT,
  GALAXY_REGION_FILL_Y_LY,
  GALAXY_REGION_NAMES,
  GALAXY_REGION_SOURCE_SHA256,
  galaxyRegionsSceneLayer,
  validateGalaxyRegionsPayload,
} from './galaxy-regions';

describe('authoritative Galaxy regions', () => {
  const assetBody = buildAuthoritativeGalaxyRegionsAsset();
  const payload = validateGalaxyRegionsPayload(
    JSON.parse(assetBody) as unknown,
  );

  it('builds the pinned source into all exact 42 regions within the asset budget', () => {
    expect(new TextEncoder().encode(assetBody).byteLength).toBeLessThanOrEqual(
      GALAXY_REGION_ASSET_BUDGET_BYTES,
    );
    expect(payload.source.sha256).toBe(GALAXY_REGION_SOURCE_SHA256);
    expect(payload.regions).toHaveLength(GALAXY_REGION_COUNT);
    expect(payload.regions.map((region) => region.name)).toEqual(
      GALAXY_REGION_NAMES,
    );
    expect(payload.boundaries).toHaveLength(22_595);
    expect(payload.boundaries.length).toBeLessThanOrEqual(
      GALAXY_REGION_BOUNDARY_LIMIT,
    );
  });

  it('keeps every deterministic label anchor inside the matching lookup region', () => {
    for (const region of payload.regions) {
      expect(findGalaxyRegionAt(payload.lookup, region.labelLy)).toMatchObject({
        id: region.id,
        name: region.name,
      });
    }
    expect(
      findGalaxyRegionAt(payload.lookup, { x: -100_000, z: -100_000 }),
    ).toBeNull();
  });

  it('builds exact, bounded fills that reconcile to every non-zero RLE cell', () => {
    const geometry = buildGalaxyRegionFillGeometry(payload.lookup);
    const sourceCellCounts = new Uint32Array(GALAXY_REGION_COUNT + 1);
    for (const row of payload.lookup.regionmap) {
      for (const [length, regionId] of row) {
        sourceCellCounts[regionId] += length;
      }
    }

    expect(geometry).toHaveLength(GALAXY_REGION_COUNT);
    expect(
      geometry.reduce((total, region) => total + region.rectangleCount, 0),
    ).toBeLessThanOrEqual(GALAXY_REGION_FILL_RECTANGLE_LIMIT);

    let invalidRendererOffsets = 0;
    let lookupMismatches = 0;
    for (const region of geometry) {
      expect(region.rectangleCount).toBeGreaterThan(0);
      expect(region.positions).toHaveLength(region.rectangleCount * 12);
      expect(region.indices).toHaveLength(region.rectangleCount * 6);
      expect(region.sourceCellCount).toBe(sourceCellCounts[region.region.id]);

      for (let offset = 0; offset < region.positions.length; offset += 12) {
        const rectangle = region.positions.slice(offset, offset + 12);
        if (
          [rectangle[1], rectangle[4], rectangle[7], rectangle[10]].some(
            (y) => y !== GALAXY_REGION_FILL_Y_LY,
          )
        ) {
          invalidRendererOffsets += 1;
        }
        const identity = findGalaxyRegionAt(payload.lookup, {
          x: (rectangle[0]! + rectangle[3]!) / 2,
          z: (rectangle[2]! + rectangle[8]!) / 2,
        });
        if (
          identity?.id !== region.region.id ||
          identity.name !== region.region.name
        ) {
          lookupMismatches += 1;
        }
      }
    }
    expect(invalidRendererOffsets).toBe(0);
    expect(lookupMismatches).toBe(0);
  });

  it('rejects altered ID/name mappings even when the region count remains 42', () => {
    const altered = {
      ...payload,
      regions: payload.regions.map((region, index) =>
        index === 0 ? { ...region, name: 'Generated Core' } : region,
      ),
    };

    expect(() => validateGalaxyRegionsPayload(altered)).toThrow(/ID\/name/);
  });

  it('requires one complete spatial-platform-owned authoritative layer', () => {
    const contribution = createGalaxyRegionsContribution(payload, 7);
    const scene: GalaxySceneContract = {
      kind: 'galaxy',
      revision: 7,
      camera: {
        focusLy: { x: 0, y: 0, z: 0 },
        distanceLy: 80_000,
        bearingRad: 0,
        pitchRad: 0.5,
        projection: 'perspective',
        revision: 7,
      },
      selection: [],
      contributions: [contribution],
    };

    expect(galaxyRegionsSceneLayer(scene)).toMatchObject({
      contributionId: 'authoritative-galaxy-regions',
      contributionRevision: 7,
      payload: { regions: expect.any(Array) },
    });
    expect(() =>
      galaxyRegionsSceneLayer({
        ...scene,
        contributions: [{ ...contribution, owner: 'FINDER' }],
      }),
    ).toThrow(/SPATIAL_PLATFORM/);
  });

  it('renders the complete accepted region set from canonical x/z coordinates', () => {
    const revision = 8;
    const scene: GalaxySceneContract = {
      kind: 'galaxy',
      revision,
      camera: {
        focusLy: { x: 0, y: 0, z: 25_000 },
        distanceLy: 120_000,
        bearingRad: 0,
        pitchRad: 0.5,
        projection: 'perspective',
        revision,
      },
      selection: [],
      contributions: [createGalaxyRegionsContribution(payload, revision)],
    };
    const engine = new NullEngine();

    const product = createBabylonGalaxyScene(engine, scene);

    expect(product.regionBoundaryMesh).not.toBeNull();
    expect(product.regionBoundaryMesh?.metadata).toMatchObject({
      spatialLayer: {
        id: 'galaxy-regions',
        sourceSha256: GALAXY_REGION_SOURCE_SHA256,
        regionCount: 42,
        boundaryCount: 22_595,
        lookupWidth: 2_048,
        lookupHeight: 2_048,
        pickableRegionCount: 42,
      },
    });
    expect(product.regionFillMeshes).toHaveLength(GALAXY_REGION_COUNT);
    expect(product.visualGlow.intensity).toBe(0.42);
    expect(product.visualGlow.blurKernelSize).toBe(32);
    expect(product.scene.imageProcessingConfiguration.toneMappingType).toBe(
      ImageProcessingConfiguration.TONEMAPPING_ACES,
    );
    expect(product.scene.metadata.spatialScene.visualProfile).toMatchObject({
      toneMapping: 'ACES',
      emissiveGlow: true,
      ambientDensitySubstitute: false,
    });
    expect(product.regionFillMeshes.every((fill) => fill.mesh.isPickable)).toBe(
      true,
    );
    expect(
      product.regionFillMeshes.reduce(
        (total, fill) =>
          total + Number(fill.mesh.metadata.spatialLayer.sourceCellCount ?? 0),
        0,
      ),
    ).toBeGreaterThan(0);
    expect(product.renderedLayers).toEqual([
      expect.objectContaining({
        layerId: 'galaxy-regions',
        acceptedTargetCount: 42,
        renderedTargetCount: 42,
      }),
    ]);
    const positions = product.regionBoundaryMesh?.getVerticesData('position');
    expect(positions?.length).toBeGreaterThan(0);
    expect(
      positions
        ?.filter((_value, index) => index % 3 === 1)
        .every((y) => y === 0),
    ).toBe(true);

    product.scene.dispose();
    engine.dispose();
  });

  it('renders semantic region selection with a distinct exact-fill treatment', () => {
    const revision = 9;
    const scene: GalaxySceneContract = {
      kind: 'galaxy',
      revision,
      camera: {
        focusLy: { x: 0, y: 0, z: 0 },
        distanceLy: 120_000,
        bearingRad: 0,
        pitchRad: 0.5,
        projection: 'perspective',
        revision,
      },
      selection: [{ kind: 'region', id: '18' }],
      contributions: [createGalaxyRegionsContribution(payload, revision)],
    };
    const engine = new NullEngine();

    const product = createBabylonGalaxyScene(engine, scene);
    const selected = product.regionFillMeshes.find(
      (fill) => fill.regionId === 18,
    );
    const neighbour = product.regionFillMeshes.find(
      (fill) => fill.regionId === 17,
    );

    expect(product.selectedRegionId).toBe(18);
    expect(selected?.regionName).toBe('Inner Orion Spur');
    expect(selected?.material.alpha).toBeGreaterThan(neighbour!.material.alpha);
    expect(selected?.material.alpha).toBeGreaterThanOrEqual(0.3);
    expect(selected?.material.emissiveColor.asArray()).not.toEqual(
      neighbour?.material.emissiveColor.asArray(),
    );
    expect(product.visualGlow.hasMesh(selected!.mesh)).toBe(false);

    product.scene.dispose();
    engine.dispose();
  });

  it('lights the exact hovered region and restores it when hover clears', () => {
    const revision = 10;
    const scene: GalaxySceneContract = {
      kind: 'galaxy',
      revision,
      camera: {
        focusLy: { x: 0, y: 0, z: 0 },
        distanceLy: 120_000,
        bearingRad: 0,
        pitchRad: 0.5,
        projection: 'perspective',
        revision,
      },
      selection: [],
      contributions: [createGalaxyRegionsContribution(payload, revision)],
    };
    const engine = new NullEngine();
    const product = createBabylonGalaxyScene(engine, scene);
    const hovered = product.regionFillMeshes.find(
      (fill) => fill.regionId === 18,
    )!;
    const neighbour = product.regionFillMeshes.find(
      (fill) => fill.regionId === 17,
    )!;
    const baseAlpha = hovered.material.alpha;
    const baseEmissive = hovered.material.emissiveColor.asArray();

    expect(product.visualGlow.hasMesh(hovered.mesh)).toBe(false);
    updateGalaxyRegionFillAppearance(product, hovered.regionId);

    expect(hovered.material.alpha).toBeGreaterThan(baseAlpha);
    expect(hovered.material.alpha).toBeGreaterThan(neighbour.material.alpha);
    expect(hovered.material.alpha).toBeGreaterThanOrEqual(0.25);
    expect(hovered.material.emissiveColor.asArray()).not.toEqual(baseEmissive);
    expect(product.visualGlow.hasMesh(hovered.mesh)).toBe(false);
    expect(product.visualGlow.hasMesh(neighbour.mesh)).toBe(false);

    updateGalaxyRegionFillAppearance(product, null);

    expect(hovered.material.alpha).toBe(baseAlpha);
    expect(hovered.material.emissiveColor.asArray()).toEqual(baseEmissive);
    expect(product.visualGlow.hasMesh(hovered.mesh)).toBe(false);

    product.scene.dispose();
    engine.dispose();
  });
});
