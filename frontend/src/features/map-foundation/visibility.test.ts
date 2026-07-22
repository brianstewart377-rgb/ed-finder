import { describe, expect, it } from 'vitest';
import type { ClusterRepresentation } from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import { toThreeJSR3F } from '../../../../artifacts/map-foundation/stage-26b/map-renderer-adapter';
import { createFoundationDemoScene } from './demo-scene';
import {
  buildClusterGeometry,
  clusterAnchorIdForSystem,
  findOverlappingSystemIds,
  guaranteedSystemIds,
  highlightedSystemIds,
  selectVisibleSystems,
} from './visibility';

describe('Stage 26C bounded visibility', () => {
  it('caps a 100k background deterministically and reports the aggregate remainder', () => {
    const scene = createFoundationDemoScene(100_000);
    const first = selectVisibleSystems(scene, { width: 1280, height: 720 });
    const second = selectVisibleSystems(scene, { width: 1280, height: 720 });

    expect(first.background).toHaveLength(25_000);
    expect(first.guaranteed).toHaveLength(5);
    expect(first.metadata.totalInViewBackground).toBeGreaterThan(25_000);
    expect(first.metadata.returnedBackground).toBe(25_000);
    expect(first.metadata.aggregateRemainder).toBe(first.metadata.totalInViewBackground - 25_000);
    expect(first.metadata.truncated).toBe(true);
    expect(first.metadata.guaranteedCount).toBe(5);
    expect(second.background.map((system) => system.id64)).toEqual(first.background.map((system) => system.id64));
  });

  it('retains selected and arbitrary highlighted systems outside the viewport', () => {
    const scene = createFoundationDemoScene(100_000);
    const distant = scene.systems.at(-1)!;
    scene.camera = { ...scene.camera, center: { x: -500_000, z: -500_000 }, zoom: 2 };
    scene.selectedSystemId64 = distant.id64;
    scene.highlights = [{ type: 'compare', leftId64: scene.systems[10]!.id64, rightId64: distant.id64 }];
    scene.clusters = [];
    scene.guaranteedSystemIds = [];

    const visible = selectVisibleSystems(scene, { width: 1280, height: 720 });
    expect(visible.background).toEqual([]);
    expect(visible.guaranteed.map((system) => system.id64)).toEqual([
      scene.systems[10]!.id64,
      distant.id64,
    ]);
    expect(guaranteedSystemIds(scene)).toEqual(new Set([scene.systems[10]!.id64, distant.id64]));
  });

  it('extracts every comparison and cluster highlight without a fixed-size limit', () => {
    const scene = createFoundationDemoScene(100_000);
    const ids = highlightedSystemIds(scene.highlights);
    expect(ids).toEqual(new Set(scene.guaranteedSystemIds));
    expect(clusterAnchorIdForSystem(scene, scene.systems[1]!.id64)).toBe(scene.systems[0]!.id64);
    expect(clusterAnchorIdForSystem(scene, scene.systems[4]!.id64)).toBeNull();
  });

  it('groups exact-coordinate overlap candidates for explicit choice', () => {
    const scene = createFoundationDemoScene(100_000);
    expect(findOverlappingSystemIds(scene.systems, 0)).toEqual([
      scene.systems[0]!.id64,
      scene.systems[1]!.id64,
    ]);
  });

  it('builds cluster edges and hull segments while preserving the anchor context', () => {
    const scene = createFoundationDemoScene(100_000);
    const base = scene.clusters[0]!;
    const hullCluster: ClusterRepresentation = {
      ...base,
      label: 'Hull fixture',
      hull: [{ x: 0, z: 0 }, { x: 10, z: 0 }, { x: 5, z: 10 }],
    };
    scene.clusters = [hullCluster];
    scene.highlights = [];

    const [geometry] = buildClusterGeometry(scene);
    expect(geometry?.anchor?.id64).toBe(hullCluster.anchorId64);
    expect(geometry?.members).toHaveLength(3);
    expect(geometry?.edgePositions).toHaveLength(12);
    expect(geometry?.hullPositions).toHaveLength(18);
  });

  it('rejects an invalid background cap', () => {
    const scene = createFoundationDemoScene(100_000);
    expect(() => selectVisibleSystems(scene, { width: 1280, height: 720 }, 0)).toThrow(
      'maxBackgroundPoints must be a positive integer',
    );
  });

  it('keeps the declared centre targeted when the R3F camera tilts and rotates', () => {
    const mapped = toThreeJSR3F({
      center: { x: 100, z: 200 },
      zoom: 64,
      pitchDeg: 30,
      bearingDeg: 90,
    }) as { position: [number, number, number]; rotation: [number, number, number]; zoom: number };
    expect(mapped.position[0]).toBeCloseTo(-400);
    expect(mapped.position[1]).toBeCloseTo(200);
    expect(mapped.position[2]).toBeCloseTo(866.025, 3);
    expect(mapped.rotation[0]).toBeCloseTo(Math.PI / 6);
    expect(mapped.rotation[2]).toBeCloseTo(-Math.PI / 2);
    expect(mapped.zoom).toBeCloseTo(1 / 64);
  });
});
