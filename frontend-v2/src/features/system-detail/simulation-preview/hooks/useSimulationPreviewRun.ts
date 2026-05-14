import { useCallback, useMemo, useState } from 'react';
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
  isResultStale: boolean;
  clearPreviewState: () => void;
  clearError: () => void;
  runSimulation: () => Promise<void>;
}

function previewInputFingerprint(targetArchetype: string, placements: SimulateBuildPlacement[]): string {
  return JSON.stringify({
    target_archetype: targetArchetype,
    placements: resequence(placements).map((placement) => ({
      facility_template_id: placement.facility_template_id,
      local_body_id: placement.local_body_id ?? null,
      is_primary_port: Boolean(placement.is_primary_port),
      build_order: placement.build_order,
    })),
  });
}

export function useSimulationPreviewRun({
  systemId64,
  targetArchetype,
  placements,
}: UseSimulationPreviewRunOptions): UseSimulationPreviewRunResult {
  const [result, setResult] = useState<SimulateBuildResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRunFingerprint, setLastRunFingerprint] = useState<string | null>(null);
  const canRun = placements.length > 0 && !running;
  const currentFingerprint = useMemo(
    () => previewInputFingerprint(targetArchetype, placements),
    [placements, targetArchetype],
  );
  const isResultStale = Boolean(result && lastRunFingerprint && currentFingerprint !== lastRunFingerprint);

  const clearPreviewState = useCallback(() => {
    setResult(null);
    setError(null);
    setLastRunFingerprint(null);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const runSimulation = useCallback(async () => {
    if (!canRun) return;
    const nextPlacements = resequence(placements);
    const runFingerprint = previewInputFingerprint(targetArchetype, nextPlacements);
    setRunning(true);
    setError(null);
    try {
      const response = await simulateBuild({
        system_id64: systemId64,
        target_archetype: targetArchetype,
        placements: nextPlacements,
      });
      setResult(response);
      setLastRunFingerprint(runFingerprint);
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
    isResultStale,
    clearPreviewState,
    clearError,
    runSimulation,
  };
}
