import { useMemo } from 'react';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import * as THREE from 'three';
import { api } from '@/lib/api';
import type { MapSystemsResponse, MapViewportBox, MapViewportSystem } from '@/lib/api';
import { spectralStarColor } from '@/lib/starColor';
import { CAMERA_VIEWPORT_HEIGHT_RATIO } from '@/features/map-foundation/camera';

// Real-star viewport lane: turn the current camera into a bounding box to fetch
// individual systems for, but only when zoomed in enough (otherwise the map
// stays on the aggregate heatmap). The fetched box is expanded by a margin (so
// panning shows already-loaded stars) and rounded to a grid (so small camera
// moves reuse the same request), and kept under the server's `too_wide` guard.

const MARGIN = 0.25;
const GRID_LY = 250;
// Half the galaxy's vertical (y / depth) thickness to include — the disk is
// thin, so this covers virtually all systems while staying under the guard.
export const REAL_STAR_Y_HALF_LY = 6_000;
// The fetched (margined) box must stay under the server's MAX_MAP_VIEWPORT_LY
// (15_000). Above that we return null and the map stays on the heatmap.
const SERVER_MAX_LY = 14_500;
const REAL_STAR_LIMIT = 40_000;

interface ViewportCamera {
  center: { x: number; z: number };
  zoom: number; // LY per pixel
}
interface ViewportSize {
  width: number;
  height: number;
}

const roundTo = (value: number, step: number) => Math.round(value / step) * step;

/**
 * The bounding box to fetch real stars for, or `null` when the view is too wide
 * (the client should stay on the aggregate heatmap).
 */
export function realStarViewportBox(camera: ViewportCamera, viewport: ViewportSize): MapViewportBox | null {
  const halfX = (camera.zoom * viewport.width * CAMERA_VIEWPORT_HEIGHT_RATIO / 2) * (1 + MARGIN);
  const halfZ = (camera.zoom * viewport.height * CAMERA_VIEWPORT_HEIGHT_RATIO / 2) * (1 + MARGIN);
  if (!Number.isFinite(halfX) || !Number.isFinite(halfZ)) return null;
  if (halfX * 2 > SERVER_MAX_LY || halfZ * 2 > SERVER_MAX_LY) return null;
  return {
    min_x: roundTo(camera.center.x - halfX, GRID_LY),
    max_x: roundTo(camera.center.x + halfX, GRID_LY),
    min_z: roundTo(camera.center.z - halfZ, GRID_LY),
    max_z: roundTo(camera.center.z + halfZ, GRID_LY),
    min_y: -REAL_STAR_Y_HALF_LY,
    max_y: REAL_STAR_Y_HALF_LY,
  };
}

/** Position + spectral-color buffers for a real-star point cloud. */
export function buildRealStarBuffers(systems: MapViewportSystem[]): { positions: Float32Array; colors: Float32Array } {
  const positions = new Float32Array(systems.length * 3);
  const colors = new Float32Array(systems.length * 3);
  const color = new THREE.Color();
  systems.forEach((system, index) => {
    // Galaxy (x, y, z) -> three (x, z, y), matching the existing map layers.
    positions.set([system.x, system.z, system.y], index * 3);
    color.set(spectralStarColor(system.star));
    colors.set([color.r, color.g, color.b], index * 3);
  });
  return { positions, colors };
}

export interface UseViewportSystemsResult {
  /** Fetched systems when zoomed in, else null (stay on the heatmap). */
  systems: MapViewportSystem[] | null;
  /** The server capped the result (only the brightest N shown). */
  truncated: boolean;
}

export function useViewportSystems(opts: {
  camera: ViewportCamera;
  viewport: ViewportSize;
  enabled?: boolean;
}): UseViewportSystemsResult {
  const box = useMemo(
    () => realStarViewportBox(opts.camera, opts.viewport),
    [opts.camera, opts.viewport],
  );

  const query = useQuery<MapSystemsResponse, Error>({
    // Key on the rounded box values so small camera moves reuse the request.
    queryKey: ['map', 'systems', box?.min_x, box?.max_x, box?.min_z, box?.max_z],
    queryFn: () => api.mapSystems(box as MapViewportBox, REAL_STAR_LIMIT),
    enabled: (opts.enabled ?? true) && box != null,
    staleTime: 60_000,
    gcTime: 300_000,
    placeholderData: keepPreviousData,
  });

  return {
    systems: box ? (query.data?.systems ?? null) : null,
    truncated: query.data?.truncated ?? false,
  };
}
