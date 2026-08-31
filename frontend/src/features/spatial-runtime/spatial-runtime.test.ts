import { describe, expect, it } from 'vitest';
import { isSelectableObject, spatialTargetId, type BodyRef, type RepresentationClass, type SpatialObject, type SystemSceneContract } from './contracts';
import { createSpatialFixture, FIXTURE_TIERS } from './fixtures';
import { applyRevisionedContribution, normalizeScene, selectLodIndices } from './scene-data';
import { cpuSpatialCandidates } from './picking';

describe('canonical renderer-neutral spatial contracts and buffers', () => {
  it('uses the one normative representation vocabulary and composite body identity', () => {
    const classes: RepresentationClass[] = ['AUTHORITATIVE', 'DERIVED', 'PLANNED', 'SCHEMATIC', 'AMBIENT'];
    const body: BodyRef = { systemId64: '10477373803', bodyId: 7 };
    expect(classes).toHaveLength(5); expect(body).toEqual({ systemId64: '10477373803', bodyId: 7 });
  });
  it('keeps ambient presentation non-selectable', () => {
    const ambient: SpatialObject = { id: 'dust', representation: 'AMBIENT', positionLy: { x: 1, y: 2, z: 3 }, color: [1, 1, 1, 1], importance: 1 };
    expect(isSelectableObject(ambient)).toBe(false);
  });
  it('represents System scale without renderer types', () => {
    const scene: SystemSceneContract = { kind: 'system', revision: 1, systemId64: '10477373803', fidelity: 'S0', camera: { systemId64: '10477373803', focus: { kind: 'body', ref: { systemId64: '10477373803', bodyId: 0 } }, semanticDistance: 5, bearingRad: 0, pitchRad: 1, revision: 1 }, bodies: [], infrastructure: [], contributions: [] };
    expect(scene.camera.focus.kind).toBe('body'); expect(normalizeScene(scene).targets).toEqual([]);
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
  it('round-trips canonical target identity through centralized CPU candidates', () => {
    const buffers = normalizeScene(createSpatialFixture(20_000)); const x = buffers.positionsLy[0]!; const z = buffers.positionsLy[2]!;
    expect(spatialTargetId(cpuSpatialCandidates(buffers, x, z, 0)[0]!.target)).toBe('system:10000000000000');
  });
});
