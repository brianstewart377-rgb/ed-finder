import type { RegionBoundary, RegionLabel, ViewportSize } from './types';

type Point3 = [number, number, number];

type ScreenLabel = RegionLabel & {
  screen: { x: number; z: number };
  depthVisible: boolean;
};

function pointKey(point: Point3): string {
  return point.join(',');
}

/**
 * Join the authoritative grid edges into continuous paths. Junctions terminate
 * a path so a Line2 never invents a connection between unrelated regions.
 */
export function buildBoundaryPolylines(boundaries: RegionBoundary[]): Float32Array[] {
  if (boundaries.length === 0) return [];

  const adjacency = new Map<string, number[]>();
  const points = new Map<string, Point3>();
  boundaries.forEach((boundary, index) => {
    [boundary.source, boundary.target].forEach((point) => {
      const key = pointKey(point);
      points.set(key, point);
      const edges = adjacency.get(key) ?? [];
      edges.push(index);
      adjacency.set(key, edges);
    });
  });

  const used = new Uint8Array(boundaries.length);
  const paths: Float32Array[] = [];

  const trace = (startKey: string, firstEdge: number) => {
    const path: number[] = [...points.get(startKey)!];
    let currentKey = startKey;
    let edgeIndex = firstEdge;

    while (!used[edgeIndex]) {
      used[edgeIndex] = 1;
      const edge = boundaries[edgeIndex]!;
      const sourceKey = pointKey(edge.source);
      const nextPoint = sourceKey === currentKey ? edge.target : edge.source;
      const nextKey = pointKey(nextPoint);
      path.push(...nextPoint);

      const incident = adjacency.get(nextKey) ?? [];
      const remaining = incident.filter((candidate) => used[candidate] === 0);
      if (incident.length !== 2 || remaining.length !== 1) break;
      currentKey = nextKey;
      edgeIndex = remaining[0]!;
    }

    paths.push(new Float32Array(path));
  };

  adjacency.forEach((edges, key) => {
    if (edges.length === 2) return;
    edges.forEach((edgeIndex) => {
      if (!used[edgeIndex]) trace(key, edgeIndex);
    });
  });

  boundaries.forEach((boundary, edgeIndex) => {
    if (!used[edgeIndex]) trace(pointKey(boundary.source), edgeIndex);
  });

  return paths;
}

export function declutterRegionLabels(
  labels: ScreenLabel[],
  viewport: ViewportSize,
  zoom: number,
  persistentRegionId?: number,
  safeArea: Partial<{
    top: number;
    right: number;
    bottom: number;
    left: number;
  }> = {},
): Array<ScreenLabel & { visible: boolean }> {
  const horizontalMargin = Math.min(150, Math.max(72, viewport.width * 0.075));
  const leftMargin = Math.max(horizontalMargin, safeArea.left ?? 0);
  const rightMargin = Math.max(horizontalMargin, safeArea.right ?? 0);
  const topMargin = Math.max(28, safeArea.top ?? 0);
  const bottomMargin = Math.max(28, safeArea.bottom ?? 0);
  const persistent = labels.find((label) => label.id === persistentRegionId);
  const persistentScreen = persistent ? {
    x: Number.isFinite(persistent.screen.x)
      ? Math.max(leftMargin, Math.min(viewport.width - rightMargin, persistent.screen.x))
      : viewport.width / 2,
    z: Number.isFinite(persistent.screen.z)
      ? Math.max(topMargin, Math.min(viewport.height - bottomMargin, persistent.screen.z))
      : viewport.height / 2,
  } : null;
  const positioned = labels.map((label) => (
    label.id === persistentRegionId && persistentScreen
      ? { ...label, screen: persistentScreen, depthVisible: true }
      : label
  ));
  const inFrame = positioned.filter((label) => (
    label.depthVisible
    && label.screen.x >= leftMargin
    && label.screen.x <= viewport.width - rightMargin
    && label.screen.z >= topMargin
    && label.screen.z <= viewport.height - bottomMargin
  ));
  const centre = { x: viewport.width / 2, z: viewport.height / 2 };
  const sorted = [...inFrame].sort((left, right) => {
    if (left.id === persistentRegionId) return -1;
    if (right.id === persistentRegionId) return 1;
    if (left.name === 'Galactic Centre') return -1;
    if (right.name === 'Galactic Centre') return 1;
    const leftDistance = Math.hypot(left.screen.x - centre.x, left.screen.z - centre.z);
    const rightDistance = Math.hypot(right.screen.x - centre.x, right.screen.z - centre.z);
    return leftDistance - rightDistance;
  });

  const scale = regionLabelScale(zoom);
  const minX = 56 * Math.min(1.45, scale);
  const minZ = 18 * Math.min(1.35, scale);
  const accepted: ScreenLabel[] = [];
  sorted.forEach((label) => {
    const collides = accepted.some((candidate) => (
      Math.abs(candidate.screen.x - label.screen.x) < minX
      && Math.abs(candidate.screen.z - label.screen.z) < minZ
    ));
    if (!collides) accepted.push(label);
  });
  const visibleIds = new Set(accepted.map((label) => label.id));

  return positioned.map((label) => ({ ...label, visible: visibleIds.has(label.id) }));
}

export function regionLabelScale(zoom: number): number {
  return Math.max(0.9, Math.min(2.35, Math.sqrt(150 / Math.max(zoom, 0.01))));
}

export function safariGestureZoomDelta(initialScale: number, nextScale: number): number {
  if (initialScale <= 0 || nextScale <= 0) return 0;
  return -Math.log(nextScale / initialScale) * 1_000;
}
