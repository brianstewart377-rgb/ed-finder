import type { SpatialContribution, SpatialSceneContract, SpatialTargetId } from './contracts';
import { isSelectableObject } from './contracts';

export type CompactSceneBuffers = Readonly<{
  positionsLy: Float64Array;
  colors: Uint8Array;
  importance: Float32Array;
  targetIds: readonly (SpatialTargetId | null)[];
  selectableIndices: Uint32Array;
  bytes: number;
}>;

export function normalizeScene(scene: SpatialSceneContract): CompactSceneBuffers {
  const objects = scene.contributions.flatMap((contribution) => contribution.objects);
  const positionsLy = new Float64Array(objects.length * 3);
  const colors = new Uint8Array(objects.length * 4);
  const importance = new Float32Array(objects.length);
  const selectable: number[] = [];
  const targetIds = objects.map((object, index) => {
    positionsLy.set(object.positionLy, index * 3);
    colors.set(object.color.map((channel) => Math.round(Math.max(0, Math.min(1, channel)) * 255)), index * 4);
    importance[index] = object.importance;
    if (isSelectableObject(object)) selectable.push(index);
    return isSelectableObject(object) ? object.targetId : null;
  });
  const selectableIndices = Uint32Array.from(selectable);
  return {
    positionsLy, colors, importance, targetIds, selectableIndices,
    bytes: positionsLy.byteLength + colors.byteLength + importance.byteLength + selectableIndices.byteLength,
  };
}

export function applyRevisionedContribution(
  scene: SpatialSceneContract,
  incoming: SpatialContribution,
): { scene: SpatialSceneContract; applied: boolean } {
  const current = scene.contributions.find((item) => item.id === incoming.id);
  if (current && incoming.revision <= current.revision) return { scene, applied: false };
  return {
    applied: true,
    scene: {
      ...scene,
      revision: scene.revision + 1,
      contributions: [...scene.contributions.filter((item) => item.id !== incoming.id), incoming],
    },
  };
}

export function selectLodIndices(
  buffers: CompactSceneBuffers,
  guaranteedIds: ReadonlySet<SpatialTargetId>,
  previousVisible: ReadonlySet<number>,
  enterImportance: number,
  exitImportance: number,
  cap: number,
): Uint32Array {
  const guaranteed = new Set<number>();
  buffers.targetIds.forEach((id, index) => { if (id && guaranteedIds.has(id)) guaranteed.add(index); });
  const candidates: number[] = [];
  for (let index = 0; index < buffers.importance.length; index += 1) {
    const threshold = previousVisible.has(index) ? exitImportance : enterImportance;
    if (buffers.importance[index]! >= threshold || guaranteed.has(index)) candidates.push(index);
  }
  candidates.sort((a, b) => Number(guaranteed.has(b)) - Number(guaranteed.has(a)) || buffers.importance[b]! - buffers.importance[a]! || a - b);
  const chosen = candidates.slice(0, Math.max(cap, guaranteed.size));
  for (const index of guaranteed) if (!chosen.includes(index)) chosen.push(index);
  return Uint32Array.from(chosen);
}
