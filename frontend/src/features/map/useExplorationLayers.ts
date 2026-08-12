import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { CAMERA_VIEWPORT_HEIGHT_RATIO } from '@/features/map-foundation/camera';

const SETTLE_MS = 250;
const Y_HALF_LY = 12_000;
const MARGIN = 0.2;

interface ExplorationCamera {
  center: { x: number; z: number };
  zoom: number;
}

interface ExplorationViewport {
  width: number;
  height: number;
}

export function explorationViewportBox(camera: ExplorationCamera, viewport: ExplorationViewport) {
  const halfX = camera.zoom * viewport.width * CAMERA_VIEWPORT_HEIGHT_RATIO / 2 * (1 + MARGIN);
  const halfZ = camera.zoom * viewport.height * CAMERA_VIEWPORT_HEIGHT_RATIO / 2 * (1 + MARGIN);
  if (!Number.isFinite(halfX) || !Number.isFinite(halfZ)) return null;
  return {
    min_x: camera.center.x - halfX,
    max_x: camera.center.x + halfX,
    min_y: -Y_HALF_LY,
    max_y: Y_HALF_LY,
    min_z: camera.center.z - halfZ,
    max_z: camera.center.z + halfZ,
  };
}

export function useExplorationLayers(opts: {
  syncKey: string;
  camera: ExplorationCamera;
  viewport: ExplorationViewport;
  visitsEnabled: boolean;
  trailEnabled: boolean;
  summarySystemId64: number | null;
}) {
  const box = useMemo(
    () => explorationViewportBox(opts.camera, opts.viewport),
    [opts.camera, opts.viewport],
  );
  const [settledBox, setSettledBox] = useState(box);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettledBox(box), SETTLE_MS);
    return () => window.clearTimeout(timer);
  }, [box]);

  const viewportVisits = useQuery({
    queryKey: [
      'exploration', opts.syncKey, 'viewport-visits',
      settledBox?.min_x, settledBox?.max_x, settledBox?.min_z, settledBox?.max_z,
      opts.camera.zoom,
    ],
    queryFn: () => api.getExplorationViewportVisits(
      opts.syncKey,
      settledBox!,
      opts.camera.zoom,
      20_000,
    ),
    enabled: opts.visitsEnabled && settledBox != null,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  const trail = useQuery({
    queryKey: ['exploration', opts.syncKey, 'trail'],
    queryFn: () => api.getExplorationTrail(opts.syncKey, { limit: 1_000 }),
    enabled: opts.trailEnabled,
    staleTime: 30_000,
  });

  const summary = useQuery({
    queryKey: ['exploration', opts.syncKey, 'summary', opts.summarySystemId64],
    queryFn: () => api.getExplorationSummary(opts.syncKey, opts.summarySystemId64!),
    enabled: opts.summarySystemId64 != null,
    staleTime: 30_000,
  });

  const facts = useQuery({
    queryKey: ['exploration', opts.syncKey, 'facts', 'latest'],
    queryFn: () => api.getExplorationFacts(opts.syncKey, { limit: 1 }),
    enabled: opts.visitsEnabled || opts.trailEnabled || opts.summarySystemId64 != null,
    staleTime: 30_000,
  });

  return { facts, viewportVisits, trail, summary };
}
