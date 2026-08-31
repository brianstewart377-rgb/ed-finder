import type { CompactSceneBuffers } from './scene-data';
import type { PickCandidate, PickStrategy } from './contracts';

export function cpuSpatialCandidates(buffers: CompactSceneBuffers, xLy: number, zLy: number, radiusLy: number): PickCandidate[] {
  const result: PickCandidate[] = [];
  for (const index of buffers.selectableIndices) {
    const dx = buffers.positionsLy[index * 3]! - xLy;
    const dz = buffers.positionsLy[index * 3 + 2]! - zLy;
    const distance = Math.hypot(dx, dz);
    const targetId = buffers.targetIds[index];
    if (targetId && distance <= radiusLy) result.push({ targetId, distancePx: distance });
  }
  return result.sort((a, b) => a.distancePx - b.distancePx || a.targetId.localeCompare(b.targetId));
}

export type PickingEvidence = Readonly<{ strategy: PickStrategy; samples: number; medianMs: number | null; limitation: string | null }>;

export async function measurePickingCandidates(
  strategies: readonly PickStrategy[],
  sample: (strategy: PickStrategy) => Promise<void>,
  samples = 20,
): Promise<PickingEvidence[]> {
  const output: PickingEvidence[] = [];
  for (const strategy of strategies) {
    const timings: number[] = [];
    try {
      for (let index = 0; index < samples; index += 1) {
        const start = performance.now(); await sample(strategy); timings.push(performance.now() - start);
      }
      timings.sort((a, b) => a - b);
      output.push({ strategy, samples, medianMs: timings[Math.floor(timings.length / 2)] ?? null, limitation: strategy === 'gpu-id-buffer' ? 'Workbench prototype uses a deterministic emulation pending hardware bakeoff.' : null });
    } catch (error) {
      output.push({ strategy, samples: 0, medianMs: null, limitation: error instanceof Error ? error.message : 'unavailable' });
    }
  }
  return output;
}
