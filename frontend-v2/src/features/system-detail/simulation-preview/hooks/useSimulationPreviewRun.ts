import { useCallback, useState } from 'react';
import { simulateBuild } from '@/lib/api';
import type { SimulateBuildPlacement, SimulateBuildResponse } from '@/types/api';
import { resequence } from '../utils/placementHelpers';

export interface UseSimulationPreviewRunOptions {
  systemId64: number;
  targetArchetype: string;
  placements: SimulateBuildPlacement[];
}

export interface UseSimulationPreviewRunResult {
  result: SimulateBuildResponse | null;
  running: boolean;
  error: string | null;
  canRun: boolean;
  clearPreviewState: () => void;
  clearError: () => void;
  runSimulation: () => Promise<void>;
}

export function useSimulationPreviewRun({
  systemId64,
  targetArchetype,
  placements,
}: UseSimulationPreviewRunOptions): UseSimulationPreviewRunResult {
  const [result, setResult] = useState<SimulateBuildResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canRun = placements.length > 0 && !running;

  const clearPreviewState = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const runSimulation = useCallback(async () => {
    if (!canRun) return;
    setRunning(true);
    setError(null);
    try {
      const response = await simulateBuild({
        system_id64: systemId64,
        target_archetype: targetArchetype,
        placements: resequence(placements),
      });
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Simulation failed');
    } finally {
      setRunning(false);
    }
  }, [canRun, placements, systemId64, targetArchetype]);

  return {
    result,
    running,
    error,
    canRun,
    clearPreviewState,
    clearError,
    runSimulation,
  };
}
