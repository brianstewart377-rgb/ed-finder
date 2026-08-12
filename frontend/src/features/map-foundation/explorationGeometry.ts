import * as THREE from 'three';
import type { ExplorationTrailPoint, ExplorationViewportVisit } from '@/lib/api';

export function buildExplorationVisitBuffers(
  visits: ExplorationViewportVisit[],
  showCompleteness: boolean,
): { positions: Float32Array; colors: Float32Array } {
  const positions = new Float32Array(visits.length * 3);
  const colors = new Float32Array(visits.length * 3);
  const color = new THREE.Color();
  visits.forEach((visit, index) => {
    positions.set([visit.x, visit.z, visit.y + 5], index * 3);
    if (visit.kind === 'density') color.set('#a66bff');
    else if (showCompleteness && visit.completion_state === 'complete') color.set('#3ddc84');
    else if (showCompleteness) color.set('#f2c94c');
    else color.set('#54d7ff');
    colors.set([color.r, color.g, color.b], index * 3);
  });
  return { positions, colors };
}

export function buildExplorationTrailBuffers(points: ExplorationTrailPoint[]): {
  positions: Float32Array;
  colors: Float32Array;
  arrowPositions: Float32Array;
} {
  const chronological = points
    .filter((point): point is ExplorationTrailPoint & { x: number; y: number; z: number } => (
      point.x != null && point.y != null && point.z != null
    ))
    .sort((left, right) => left.sequence - right.sequence);
  const segmentCount = Math.max(0, chronological.length - 1);
  const positions = new Float32Array(segmentCount * 6);
  const colors = new Float32Array(segmentCount * 6);
  const arrows: number[] = [];
  const color = new THREE.Color();
  const arrowEvery = Math.max(1, Math.ceil(segmentCount / 80));
  for (let index = 0; index < segmentCount; index += 1) {
    const from = chronological[index];
    const to = chronological[index + 1];
    positions.set([from.x, from.z, from.y + 3, to.x, to.z, to.y + 3], index * 6);
    const progress = segmentCount <= 1 ? 1 : index / (segmentCount - 1);
    color.setHSL(0.55 - progress * 0.43, 0.9, 0.62);
    colors.set([color.r, color.g, color.b, color.r, color.g, color.b], index * 6);

    if (index % arrowEvery === 0) {
      const dx = to.x - from.x;
      const dz = to.z - from.z;
      const length = Math.hypot(dx, dz);
      if (length > 0.001) {
        const ux = dx / length;
        const uz = dz / length;
        const size = Math.min(80, Math.max(5, length * 0.12));
        const tipX = from.x + dx * 0.62;
        const tipZ = from.z + dz * 0.62;
        const baseX = tipX - ux * size;
        const baseZ = tipZ - uz * size;
        const wing = size * 0.48;
        const height = from.y + (to.y - from.y) * 0.62 + 4;
        arrows.push(
          tipX, tipZ, height, baseX - uz * wing, baseZ + ux * wing, height,
          tipX, tipZ, height, baseX + uz * wing, baseZ - ux * wing, height,
        );
      }
    }
  }
  return { positions, colors, arrowPositions: new Float32Array(arrows) };
}
