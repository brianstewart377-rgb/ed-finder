import { describe, expect, it } from 'vitest';
import { isSelectableObject, type SpatialObject } from './contracts';
import { createSpatialFixture, FIXTURE_TIERS } from './fixtures';
import { applyRevisionedContribution, normalizeScene, selectLodIndices } from './scene-data';
import { cpuSpatialCandidates } from './picking';

describe('renderer-neutral spatial truth and buffers', () => {
  it('never turns ambient presentation into a factual/selectable target', () => {
    const ambient: SpatialObject = { id: 'dust', targetId: null, kind: 'ambient', truthClass: 'ambient', positionLy: [1, 2, 3], color: [1, 1, 1, 1], importance: 1 };
    expect(isSelectableObject(ambient)).toBe(false);
  });

  it.each(FIXTURE_TIERS)('normalizes deterministic %i tier into compact buffers in actual LY', (tier) => {
    const scene = createSpatialFixture(tier);
    const first = normalizeScene(scene); const second = normalizeScene(createSpatialFixture(tier));
    expect(first.targetIds).toHaveLength(tier);
    expect([...first.positionsLy.slice(0, 9)]).toEqual([...second.positionsLy.slice(0, 9)]);
    expect(first.positionsLy[0]).toBe(scene.contributions[0]!.objects[0]!.positionLy[0]);
    expect(first.bytes).toBe(tier * (3 * 8 + 4 + 4 + 4));
  });

  it('rejects stale revisions and guarantees semantic targets through LOD', () => {
    const scene = createSpatialFixture(20_000); const contribution = scene.contributions[0]!;
    expect(applyRevisionedContribution(scene, contribution).applied).toBe(false);
    const buffers = normalizeScene(scene);
    const visible = selectLodIndices(buffers, new Set(['system:fixture-19999']), new Set(), .9999, .99, 3);
    expect([...visible]).toContain(19_999);
  });

  it('round-trips stable target identity through centralized CPU candidates', () => {
    const buffers = normalizeScene(createSpatialFixture(20_000));
    const x = buffers.positionsLy[0]!; const z = buffers.positionsLy[2]!;
    expect(cpuSpatialCandidates(buffers, x, z, 0)[0]?.targetId).toBe('system:fixture-0');
  });
});
