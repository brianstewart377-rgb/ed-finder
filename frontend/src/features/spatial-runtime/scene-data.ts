import type { CameraState, GalaxySceneContract, SpatialContribution, SpatialObject, SpatialSceneContract, SpatialTarget, SpatialTargetId } from './contracts';
import { isSelectableObject, spatialTargetId } from './contracts';

export type CompactSceneBuffers = Readonly<{ positionsLy: Float64Array; colors: Uint8Array; importance: Float32Array; targets: readonly (SpatialTarget | null)[]; selectableIndices: Uint32Array; bytes: number }>;
export type SemanticLod = 'wide' | 'regional' | 'local';
export type SemanticLodPolicy = Readonly<{ level: SemanticLod; cap: number; enterImportance: number; exitImportance: number }>;
export type GpuSceneBuffers = Readonly<{ buffers: CompactSceneBuffers; sourceIndices: Uint32Array; policy: SemanticLodPolicy; truncated: boolean }>;

const SEMANTIC_LOD_POLICIES: readonly SemanticLodPolicy[] = [
  { level: 'wide', cap: 20_000, enterImportance: 0.5, exitImportance: 0.45 },
  { level: 'regional', cap: 40_000, enterImportance: 0.2, exitImportance: 0.15 },
  { level: 'local', cap: 100_000, enterImportance: 0, exitImportance: 0 },
];

function isSpatialObject(value: unknown): value is SpatialObject {
  if (!value || typeof value !== 'object') return false;
  const item = value as Partial<SpatialObject>;
  return typeof item.id === 'string' && typeof item.positionLy?.x === 'number' && typeof item.importance === 'number';
}
export function spatialObjects(scene: SpatialSceneContract): readonly SpatialObject[] {
  return scene.contributions.flatMap((contribution) => contribution.layers.flatMap((layer) => Array.isArray(layer.payload) ? layer.payload.filter(isSpatialObject) : []));
}
export function normalizeScene(scene: SpatialSceneContract): CompactSceneBuffers {
  const objects = spatialObjects(scene);
  const positionsLy = new Float64Array(objects.length * 3); const colors = new Uint8Array(objects.length * 4);
  const importance = new Float32Array(objects.length); const selectable: number[] = [];
  const targets = objects.map((object, index) => {
    positionsLy.set([object.positionLy.x, object.positionLy.y, object.positionLy.z], index * 3);
    colors.set(object.color.map((channel) => Math.round(Math.max(0, Math.min(1, channel)) * 255)), index * 4);
    importance[index] = object.importance; if (isSelectableObject(object)) selectable.push(index);
    return isSelectableObject(object) ? object.target : null;
  });
  const selectableIndices = Uint32Array.from(selectable);
  return { positionsLy, colors, importance, targets, selectableIndices, bytes: positionsLy.byteLength + colors.byteLength + importance.byteLength + selectableIndices.byteLength };
}
export function applyRevisionedContribution(scene: SpatialSceneContract, incoming: SpatialContribution): { scene: SpatialSceneContract; applied: boolean } {
  const current = scene.contributions.find((item) => item.id === incoming.id);
  if (current && incoming.revision <= current.revision) return { scene, applied: false };
  return { applied: true, scene: { ...scene, revision: scene.revision + 1, contributions: [...scene.contributions.filter((item) => item.id !== incoming.id), incoming] } };
}
export function selectLodIndices(buffers: CompactSceneBuffers, guaranteedIds: ReadonlySet<SpatialTargetId>, previousVisible: ReadonlySet<number>, enterImportance: number, exitImportance: number, cap: number): Uint32Array {
  const guaranteed = new Set<number>();
  buffers.targets.forEach((target, index) => { if (target && guaranteedIds.has(spatialTargetId(target))) guaranteed.add(index); });
  const candidates: number[] = [];
  for (let index = 0; index < buffers.importance.length; index += 1) { const threshold = previousVisible.has(index) ? exitImportance : enterImportance; if (buffers.importance[index]! >= threshold || guaranteed.has(index)) candidates.push(index); }
  candidates.sort((a, b) => Number(guaranteed.has(b)) - Number(guaranteed.has(a)) || buffers.importance[b]! - buffers.importance[a]! || a - b);
  const chosen = candidates.slice(0, Math.max(cap, guaranteed.size)); for (const index of guaranteed) if (!chosen.includes(index)) chosen.push(index);
  return Uint32Array.from(chosen);
}

/** Resolve semantic zoom before allocating/uploading GPU instance arrays. */
export function semanticLodPolicy(camera: CameraState, previousLevel?: SemanticLod): SemanticLodPolicy {
  if (previousLevel === 'wide') {
    if (camera.distanceLy >= 18_000) return SEMANTIC_LOD_POLICIES[0]!;
    return camera.distanceLy >= 2_000 ? SEMANTIC_LOD_POLICIES[1]! : SEMANTIC_LOD_POLICIES[2]!;
  }
  if (previousLevel === 'regional') {
    if (camera.distanceLy >= 22_000) return SEMANTIC_LOD_POLICIES[0]!;
    return camera.distanceLy >= 1_800 ? SEMANTIC_LOD_POLICIES[1]! : SEMANTIC_LOD_POLICIES[2]!;
  }
  if (previousLevel === 'local') {
    if (camera.distanceLy >= 22_000) return SEMANTIC_LOD_POLICIES[0]!;
    return camera.distanceLy >= 2_200 ? SEMANTIC_LOD_POLICIES[1]! : SEMANTIC_LOD_POLICIES[2]!;
  }
  if (camera.distanceLy >= 20_000) return SEMANTIC_LOD_POLICIES[0]!;
  if (camera.distanceLy >= 2_000) return SEMANTIC_LOD_POLICIES[1]!;
  return SEMANTIC_LOD_POLICIES[2]!;
}

export function selectGpuSceneBuffers(
  scene: GalaxySceneContract,
  source: CompactSceneBuffers,
  previousVisible: ReadonlySet<number> = new Set(),
  previousLevel?: SemanticLod,
): GpuSceneBuffers {
  const policy = semanticLodPolicy(scene.camera, previousLevel);
  const guaranteedIds = new Set(scene.selection.map(spatialTargetId));
  const sourceIndices = selectLodIndices(source, guaranteedIds, previousVisible, policy.enterImportance, policy.exitImportance, policy.cap);
  const positionsLy = new Float64Array(sourceIndices.length * 3);
  const colors = new Uint8Array(sourceIndices.length * 4);
  const importance = new Float32Array(sourceIndices.length);
  const targets: (SpatialTarget | null)[] = [];
  const selectableIndices: number[] = [];
  sourceIndices.forEach((sourceIndex, gpuIndex) => {
    positionsLy.set(source.positionsLy.subarray(sourceIndex * 3, sourceIndex * 3 + 3), gpuIndex * 3);
    colors.set(source.colors.subarray(sourceIndex * 4, sourceIndex * 4 + 4), gpuIndex * 4);
    importance[gpuIndex] = source.importance[sourceIndex]!;
    const target = source.targets[sourceIndex] ?? null;
    targets.push(target);
    if (target) selectableIndices.push(gpuIndex);
  });
  const compactSelectable = Uint32Array.from(selectableIndices);
  return {
    buffers: {
      positionsLy,
      colors,
      importance,
      targets,
      selectableIndices: compactSelectable,
      bytes: positionsLy.byteLength + colors.byteLength + importance.byteLength + compactSelectable.byteLength,
    },
    sourceIndices,
    policy,
    truncated: sourceIndices.length < source.targets.length,
  };
}

export function isGalaxyScene(scene: SpatialSceneContract): scene is GalaxySceneContract { return scene.kind === 'galaxy'; }
