import type {
  ClusterRepresentation,
  HighlightSet,
  MapSceneState,
  SystemRecord,
} from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import type { ClusterGeometry, ViewportSize, VisibleScene } from './types';

export const DEFAULT_MAX_BACKGROUND_POINTS = 25_000;

export function guaranteedSystemIds(scene: MapSceneState): Set<number> {
  const ids = new Set(scene.guaranteedSystemIds);
  if (scene.selectedSystemId64 != null) ids.add(scene.selectedSystemId64);
  for (const highlight of scene.highlights) {
    if (highlight.type === 'compare') {
      ids.add(highlight.leftId64);
      ids.add(highlight.rightId64);
    } else {
      ids.add(highlight.cluster.anchorId64);
      highlight.cluster.memberIds.forEach((id) => ids.add(id));
    }
  }
  for (const cluster of scene.clusters) {
    ids.add(cluster.anchorId64);
    cluster.memberIds.forEach((id) => ids.add(id));
  }
  return ids;
}

export function highlightedSystemIds(highlights: HighlightSet[]): Set<number> {
  const ids = new Set<number>();
  for (const highlight of highlights) {
    if (highlight.type === 'compare') {
      ids.add(highlight.leftId64);
      ids.add(highlight.rightId64);
    } else {
      ids.add(highlight.cluster.anchorId64);
      highlight.cluster.memberIds.forEach((id) => ids.add(id));
    }
  }
  return ids;
}

export function clusterAnchorIdForSystem(scene: MapSceneState, systemId64: number): number | null {
  const clusters = [
    ...scene.clusters,
    ...scene.highlights.flatMap((highlight) => highlight.type === 'cluster' ? [highlight.cluster] : []),
  ];
  const cluster = clusters.find((candidate) => (
    candidate.anchorId64 === systemId64 || candidate.memberIds.includes(systemId64)
  ));
  return cluster?.anchorId64 ?? null;
}

function deterministicSample<T>(values: T[], limit: number): T[] {
  if (values.length <= limit) return values;
  return Array.from({ length: limit }, (_, index) => values[Math.floor(index * values.length / limit)]!);
}

export function selectVisibleSystems(
  scene: MapSceneState,
  viewport: ViewportSize,
  maxBackgroundPoints = DEFAULT_MAX_BACKGROUND_POINTS,
): VisibleScene {
  if (!Number.isInteger(maxBackgroundPoints) || maxBackgroundPoints < 1) {
    throw new Error('maxBackgroundPoints must be a positive integer');
  }
  const guaranteedIds = guaranteedSystemIds(scene);
  const guaranteed: SystemRecord[] = [];
  const inViewBackground: SystemRecord[] = [];
  const halfWidthLy = viewport.width * scene.camera.zoom / 2;
  const halfHeightLy = viewport.height * scene.camera.zoom / 2;

  for (const system of scene.systems) {
    if (guaranteedIds.has(system.id64)) {
      guaranteed.push(system);
      continue;
    }
    if (
      Math.abs(system.coords.x - scene.camera.center.x) <= halfWidthLy
      && Math.abs(system.coords.z - scene.camera.center.z) <= halfHeightLy
    ) {
      inViewBackground.push(system);
    }
  }

  const background = deterministicSample(inViewBackground, maxBackgroundPoints);
  return {
    background,
    guaranteed,
    metadata: {
      totalInViewBackground: inViewBackground.length,
      returnedBackground: background.length,
      aggregateRemainder: inViewBackground.length - background.length,
      truncated: background.length < inViewBackground.length,
      guaranteedCount: guaranteed.length,
    },
  };
}

export function findOverlappingSystemIds(systems: SystemRecord[], selectedIndex: number): number[] {
  const selected = systems[selectedIndex];
  if (!selected) return [];
  return systems
    .filter((system) => system.coords.x === selected.coords.x && system.coords.z === selected.coords.z)
    .map((system) => system.id64);
}

function edgePositions(cluster: ClusterRepresentation, systemsById: Map<number, SystemRecord>): Float32Array {
  const coordinates: number[] = [];
  for (const edge of cluster.edges) {
    const from = systemsById.get(edge.fromId64);
    const to = systemsById.get(edge.toId64);
    if (from && to) coordinates.push(from.coords.x, from.coords.z, 2, to.coords.x, to.coords.z, 2);
  }
  return new Float32Array(coordinates);
}

export function buildClusterGeometry(scene: MapSceneState): ClusterGeometry[] {
  const systemsById = new Map(scene.systems.map((system) => [system.id64, system]));
  const clusters = new Map<string, ClusterRepresentation>();
  scene.clusters.forEach((cluster) => clusters.set(`${cluster.anchorId64}:${cluster.label}`, cluster));
  scene.highlights.forEach((highlight) => {
    if (highlight.type === 'cluster') {
      clusters.set(`${highlight.cluster.anchorId64}:${highlight.cluster.label}`, highlight.cluster);
    }
  });

  return [...clusters.values()].map((cluster) => ({
    cluster,
    anchor: systemsById.get(cluster.anchorId64) ?? null,
    members: cluster.memberIds.flatMap((id) => {
      const system = systemsById.get(id);
      return system ? [system] : [];
    }),
    edgePositions: edgePositions(cluster, systemsById),
    hullPositions: cluster.hull
      ? new Float32Array(cluster.hull.flatMap((point, index, hull) => {
        const next = hull[(index + 1) % hull.length]!;
        return [point.x, point.z, 2, next.x, next.z, 2];
      }))
      : null,
  }));
}
