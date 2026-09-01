import { describe, expect, it } from 'vitest';
import { isSelectableObject, spatialTargetId, type BodyRef, type RepresentationClass, type RingDescriptor, type SpatialObject, type SystemSceneContract } from './contracts';
import { createSpatialFixture, FIXTURE_TIERS } from './fixtures';
import { applyRevisionedContribution, normalizeScene, selectGpuSceneBuffers, selectLodIndices, semanticLodPolicy } from './scene-data';
import { boundPickCandidates, buildCpuSpatialPickIndex, cpuSpatialCandidates, cpuSpatialIndexCandidates } from './picking';

describe('canonical renderer-neutral spatial contracts and buffers', () => {
  it('uses the one normative representation vocabulary and composite body identity', () => {
    const classes: RepresentationClass[] = ['AUTHORITATIVE', 'DERIVED', 'PLANNED', 'SCHEMATIC', 'AMBIENT'];
    const body: BodyRef = { systemId64: '10477373803', bodyId: 7 };
    expect(classes).toHaveLength(5); expect(body).toEqual({ systemId64: '10477373803', bodyId: 7 });
  });
  it('serializes facility identity with its system and body scope', () => {
    const first = { kind: 'facility', ref: { owner: 'EDFINDER', facilityId: 'port', systemId64: '10', body: { systemId64: '10', bodyId: 2 } } } as const;
    const second = { kind: 'facility', ref: { owner: 'EDFINDER', facilityId: 'port', systemId64: '11', body: { systemId64: '11', bodyId: 2 } } } as const;
    expect(spatialTargetId(first)).toBe('facility:EDFINDER:10:10:2:port');
    expect(spatialTargetId(second)).not.toBe(spatialTargetId(first));
    expect(spatialTargetId({ ...first, ref: { ...first.ref, body: { systemId64: '99', bodyId: 2 } } })).not.toBe(spatialTargetId(first));
  });
  it('keeps ambient presentation non-selectable', () => {
    const ambient: SpatialObject = { id: 'dust', representation: 'AMBIENT', positionLy: { x: 1, y: 2, z: 3 }, color: [1, 1, 1, 1], importance: 1 };
    expect(isSelectableObject(ambient)).toBe(false);
  });
  it('represents System scale without renderer types', () => {
    const selected = { kind: 'body', ref: { systemId64: '10477373803', bodyId: 1 } } as const;
    const scene: SystemSceneContract = { kind: 'system', revision: 1, systemId64: '10477373803', fidelity: 'S0', camera: { systemId64: '10477373803', focus: { kind: 'body', ref: { systemId64: '10477373803', bodyId: 0 } }, semanticDistance: 5, bearingRad: 0, pitchRad: 1, revision: 1 }, selection: [selected], bodies: [], infrastructure: [], contributions: [] };
    expect(scene.camera.focus).not.toEqual(scene.selection[0]); expect(normalizeScene(scene).targets).toEqual([]);
  });
  it.each(FIXTURE_TIERS)('normalizes deterministic %i tier into compact buffers in actual LY', (tier) => {
    const scene = createSpatialFixture(tier); const first = normalizeScene(scene); const second = normalizeScene(createSpatialFixture(tier));
    expect(first.targets).toHaveLength(tier); expect([...first.positionsLy.slice(0, 9)]).toEqual([...second.positionsLy.slice(0, 9)]);
    const firstObject = scene.contributions[0]!.layers[0]!.payload as SpatialObject[];
    expect(first.positionsLy[0]).toBe(firstObject[0]!.positionLy.x); expect(first.bytes).toBe(tier * (3 * 8 + 4 + 4 + 4));
  });
  it('rejects stale revisions and guarantees semantic targets through LOD', () => {
    const scene = createSpatialFixture(20_000); const contribution = scene.contributions[0]!;
    expect(applyRevisionedContribution(scene, contribution).applied).toBe(false);
    const visible = selectLodIndices(normalizeScene(scene), new Set(['system:10000000019999']), new Set(), .9999, .99, 3);
    expect([...visible]).toContain(19_999);
  });
  it('bounds wide GPU buffers before upload and preserves selected targets beyond the cap', () => {
    const scene = createSpatialFixture(500_000);
    const selectedTarget = { kind: 'system', systemId64: '10000000499999' } as const;
    const selectedScene = { ...scene, selection: [selectedTarget] };
    const gpu = selectGpuSceneBuffers(selectedScene, normalizeScene(selectedScene));
    expect(gpu.policy.level).toBe('wide');
    expect(gpu.buffers.targets.length).toBe(20_000);
    expect(gpu.truncated).toBe(true);
    expect(gpu.buffers.targets.some((target) => target && spatialTargetId(target) === spatialTargetId(selectedTarget))).toBe(true);
  });
  it('applies exit hysteresis to objects that were previously visible', () => {
    const scene = createSpatialFixture(20_000);
    const buffers = normalizeScene(scene);
    buffers.importance[10] = 0.47;
    expect([...selectGpuSceneBuffers(scene, buffers).sourceIndices]).not.toContain(10);
    expect([...selectGpuSceneBuffers(scene, buffers, new Set([10])).sourceIndices]).toContain(10);
  });
  it('uses distinct enter and exit boundaries for semantic zoom levels', () => {
    const camera = createSpatialFixture(20_000).camera;
    expect(semanticLodPolicy({ ...camera, distanceLy: 19_000 }, 'wide').level).toBe('wide');
    expect(semanticLodPolicy({ ...camera, distanceLy: 19_000 }, 'regional').level).toBe('regional');
    expect(semanticLodPolicy({ ...camera, distanceLy: 1_900 }, 'regional').level).toBe('regional');
    expect(semanticLodPolicy({ ...camera, distanceLy: 1_700 }, 'regional').level).toBe('local');
    expect(semanticLodPolicy({ ...camera, distanceLy: 2_100 }, 'local').level).toBe('local');
  });
  it('round-trips canonical target identity through centralized CPU candidates', () => {
    const buffers = normalizeScene(createSpatialFixture(20_000)); const x = buffers.positionsLy[0]!; const z = buffers.positionsLy[2]!;
    expect(spatialTargetId(cpuSpatialCandidates(buffers, x, z, 0)[0]!.target)).toBe('system:10000000000000');
  });
  it('uses a real spatial index with results equivalent to the bounded linear reference', () => {
    const buffers = normalizeScene(createSpatialFixture(20_000));
    const x = buffers.positionsLy[0]!; const z = buffers.positionsLy[2]!; const radius = 2_000;
    const expected = cpuSpatialCandidates(buffers, x, z, radius);
    const actual = cpuSpatialIndexCandidates(buildCpuSpatialPickIndex(buffers, 1_000), buffers, x, z, radius);
    expect(actual).toEqual(expected);
  });
  it('returns every candidate up to the bound and reports truncation explicitly', () => {
    const candidates = Array.from({ length: 18 }, (_, index) => ({ target: { kind: 'system' as const, systemId64: String(index) }, distancePx: index }));
    expect(boundPickCandidates(candidates, 16)).toEqual({ candidates: candidates.slice(0, 16), truncated: true, totalCandidates: 18, latencyMs: 0 });
    expect(boundPickCandidates(candidates.slice(0, 2), 16)).toEqual({ candidates: candidates.slice(0, 2), truncated: false, totalCandidates: 2, latencyMs: 0 });
  });
  it('models ring truth without contradictory bands', () => {
    const absent: RingDescriptor = { state: 'ABSENT' };
    const present: RingDescriptor = { state: 'PRESENT', bands: [{ id: 'A Ring' }] };
    expect(absent).toEqual({ state: 'ABSENT' }); expect(present.bands).toHaveLength(1);
  });
});
