import type { CompactSceneBuffers } from './scene-data';
import type { PickCandidate, PickResult, PickStrategy } from './contracts';
import { spatialTargetId } from './contracts';

export function cpuSpatialCandidates(buffers: CompactSceneBuffers, xLy: number, zLy: number, radiusLy: number): PickCandidate[] {
  const result: PickCandidate[] = [];
  for (const index of buffers.selectableIndices) {
    const dx = buffers.positionsLy[index * 3]! - xLy;
    const dz = buffers.positionsLy[index * 3 + 2]! - zLy;
    const distance = Math.hypot(dx, dz);
    const target = buffers.targets[index];
    if (target && distance <= radiusLy) result.push({ target, distancePx: distance });
  }
  return result.sort((a, b) => a.distancePx - b.distancePx || spatialTargetId(a.target).localeCompare(spatialTargetId(b.target)));
}

export function boundPickCandidates(candidates: readonly PickCandidate[], limit = 16, latencyMs = 0): PickResult {
  const boundedLimit = Math.max(1, Math.floor(limit));
  return { candidates: candidates.slice(0, boundedLimit), truncated: candidates.length > boundedLimit, totalCandidates: candidates.length, latencyMs };
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
