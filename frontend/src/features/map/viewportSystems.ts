import { useEffect, useMemo, useState, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as THREE from 'three';
import { api } from '@/lib/api';
import type { MapViewportResponse, MapViewportBox, MapViewportSystem } from '@/lib/api';
import { spectralStarColor } from '@/lib/starColor';
import { CAMERA_VIEWPORT_HEIGHT_RATIO } from '@/features/map-foundation/camera';

// Real-star viewport lane: turn the current camera into a bounding box to fetch
// individual systems for, but only when zoomed in enough (otherwise the map
// stays on the aggregate heatmap). The fetched box is expanded by a margin (so
// panning shows already-loaded stars) and rounded to a grid (so small camera
// moves reuse the same request), and kept under the server's too_wide guard.

const MARGIN = 0.25;
const GRID_LY = 250;
// Half the galaxy's vertical (y / depth) thickness to include — the disk is
// thin, so this covers virtually all systems while staying under the guard.
export const REAL_STAR_Y_HALF_LY = 6_000;
// Separate enter and exit thresholds prevent repeated heatmap/detail toggles at
// the LOD boundary. Thresholds tuned to enable real-star detail at reasonable zoom
// levels (roughly 40-50 LY/px). Values account for the viewport span calculation
// which includes margin (1.25x) and pitch footprint scaling.
export const REAL_STAR_ENTER_MAX_LY = 120_000;
export const REAL_STAR_EXIT_MAX_LY = 150_000;
const REAL_STAR_LIMIT = 40_000;
// Wait for the camera to settle before issuing a viewport query, so smooth
// zoom / continuous panning (which change the box every animation frame) can't
// spawn a request per frame and exhaust the endpoint's per-minute rate limit.
const SETTLE_MS = 250;

interface ViewportCamera {
  center: { x: number; z: number };
  zoom: number; // LY per pixel
  pitchDeg?: number;
}
interface ViewportSize {
  width: number;
  height: number;
}

// Snap the lower bound down and the upper bound up to the grid. Rounding both
// with Math.round would collapse the box to zero width at deep zoom (when the
// whole raw span sits inside a single grid cell), so the server would match
// only systems on the exact coordinate plane and the layer would go empty
// precisely when zoomed in most. floor/ceil guarantees at least one full grid
// cell per axis while still snapping to the grid (so small pans reuse the box).
const floorTo = (value: number, step: number) => Math.floor(value / step) * step;
const ceilTo = (value: number, step: number) => Math.ceil(value / step) * step;

function pitchFootprintScale(pitchDeg = 0.5): number {
  const pitch = Math.max(0.5, Math.min(72, pitchDeg)) * Math.PI / 180;
  const halfFov = 21 * Math.PI / 180;
  // Once the upper ray crosses the horizon the ground footprint is unbounded;
  // remain on the aggregate layer rather than fetching a knowingly partial box.
  if (pitch + halfFov >= Math.PI / 2) return Number.POSITIVE_INFINITY;

  // Normalise visible height to one. Intersect the upper and lower frustum rays
  // with the galaxy plane and use the furthest extent as a conservative scale
  // for both world axes (bearing can rotate that extent onto either axis).
  const distance = 1 / (2 * Math.tan(halfFov));
  const cameraHeight = distance * Math.cos(pitch);
  const cameraOffset = distance * Math.sin(pitch);
  const farExtent = Math.abs(
    -cameraOffset + cameraHeight * Math.tan(pitch + halfFov),
  );
  const nearExtent = Math.abs(
    -cameraOffset + cameraHeight * Math.tan(pitch - halfFov),
  );
  return Math.max(farExtent, nearExtent) / 0.5;
}

export function realStarViewportSpan(
  camera: ViewportCamera,
  viewport: ViewportSize,
): { halfX: number; halfZ: number; maxSpan: number } {
  const footprintScale = pitchFootprintScale(camera.pitchDeg);
  const halfX = (
    camera.zoom * viewport.width * CAMERA_VIEWPORT_HEIGHT_RATIO / 2
  ) * (1 + MARGIN) * footprintScale;
  const halfZ = (
    camera.zoom * viewport.height * CAMERA_VIEWPORT_HEIGHT_RATIO / 2
  ) * (1 + MARGIN) * footprintScale;
  return { halfX, halfZ, maxSpan: Math.max(halfX * 2, halfZ * 2) };
}

export function shouldEnableRealStarDetail(
  camera: ViewportCamera,
  viewport: ViewportSize,
  wasEnabled: boolean,
): boolean {
  const { maxSpan } = realStarViewportSpan(camera, viewport);
  if (!Number.isFinite(maxSpan)) return false;
  return maxSpan <= (
    wasEnabled ? REAL_STAR_EXIT_MAX_LY : REAL_STAR_ENTER_MAX_LY
  );
}

/**
 * The bounding box to fetch real stars for, or null when the view is too wide
 * (the client should stay on the aggregate heatmap).
 */
export function realStarViewportBox(camera: ViewportCamera, viewport: ViewportSize): MapViewportBox | null {
  const { halfX, halfZ, maxSpan } = realStarViewportSpan(camera, viewport);
  if (!Number.isFinite(maxSpan) || maxSpan > REAL_STAR_EXIT_MAX_LY) return null;
  return {
    min_x: floorTo(camera.center.x - halfX, GRID_LY),
    max_x: ceilTo(camera.center.x + halfX, GRID_LY),
    min_z: floorTo(camera.center.z - halfZ, GRID_LY),
    max_z: ceilTo(camera.center.z + halfZ, GRID_LY),
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
    color.set(spectralStarColor(system.main_star_class));
    colors.set([color.r, color.g, color.b], index * 3);
  });
  return { positions, colors };
}

export interface UseViewportSystemsResult {
  /** Fetched systems for the current settled viewport, else null. */
  systems: MapViewportSystem[] | null;
  /** The server capped the result (only the brightest N shown). */
  truncated: boolean;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
}

function boxesEqual(
  left: MapViewportBox | null,
  right: MapViewportBox | null,
): boolean {
  return left != null
    && right != null
    && left.min_x === right.min_x
    && left.max_x === right.max_x
    && left.min_z === right.min_z
    && left.max_z === right.max_z
    && left.min_y === right.min_y
    && left.max_y === right.max_y;
}

export function useViewportSystems(opts: {
  camera: ViewportCamera;
  viewport: ViewportSize;
  enabled?: boolean;
}): UseViewportSystemsResult {
  const enabled = opts.enabled ?? true;
  const [detailEnabled, setDetailEnabled] = useState(false);
  const detailEnabledRef = useRef(false);
  const lastCameraKeyRef = useRef<string>('');
  const optsRef = useRef(opts);

  // Keep the ref up to date with latest props so RAF can read them
  useEffect(() => {
    optsRef.current = opts;
  }, [opts.camera, opts.viewport, opts.enabled]);

  // Keep detailEnabled ref in sync for RAF closure
  useEffect(() => {
    detailEnabledRef.current = detailEnabled;
  }, [detailEnabled]);

  // Monitor camera changes via requestAnimationFrame (outside Canvas context)
  useEffect(() => {
    let animId: number;
    const checkCameraChange = () => {
      const current = optsRef.current;
      const cameraKey = `${current.camera.center.x}|${current.camera.center.z}|${current.camera.zoom}|${current.camera.pitchDeg ?? 0}`;

      if (cameraKey !== lastCameraKeyRef.current) {
        lastCameraKeyRef.current = cameraKey;
        const currentEnabled = current.enabled ?? true;
        const span = realStarViewportSpan(current.camera, current.viewport);
        const shouldEnable = currentEnabled && shouldEnableRealStarDetail(current.camera, current.viewport, detailEnabledRef.current);

        if (shouldEnable !== detailEnabledRef.current) {
          console.log('[viewport-systems] zoom detected, detail toggle:', {
            zoom: current.camera.zoom,
            span: span.maxSpan,
            from: detailEnabledRef.current,
            to: shouldEnable,
          });
          setDetailEnabled(shouldEnable);
        }
      }

      animId = requestAnimationFrame(checkCameraChange);
    };
    animId = requestAnimationFrame(checkCameraChange);
    return () => cancelAnimationFrame(animId);
  }, []);

  const box = useMemo(
    () => detailEnabled ? realStarViewportBox(opts.camera, opts.viewport) : null,
    [detailEnabled, opts.camera.center.x, opts.camera.center.z, opts.camera.zoom, opts.camera.pitchDeg, opts.viewport.width, opts.viewport.height],
  );

  // Debounce: wait for camera to settle before issuing a query. Smooth zoom/pan
  // changes the box every frame; without this the endpoint's rate limit gets exhausted.
  const [settledBox, setSettledBox] = useState<MapViewportBox | null>(null);
  useEffect(() => {
    if (box == null) {
      setSettledBox(null);
      return undefined;
    }
    const timer = setTimeout(() => {
      console.log('[viewport-systems] settle timer fired, issuing query');
      setSettledBox(box);
    }, SETTLE_MS);
    return () => clearTimeout(timer);
  }, [box]);

  const query = useQuery<MapViewportResponse, Error>({
    // Key on the settled box so the request is stable once camera settles.
    queryKey: ['map', 'systems', settledBox?.min_x, settledBox?.max_x, settledBox?.min_z, settledBox?.max_z],
    queryFn: () => api.mapSystems(settledBox as MapViewportBox, REAL_STAR_LIMIT),
    enabled: enabled && settledBox != null,
    staleTime: 60_000,
    gcTime: 300_000,
  });

  // Never display data, truncation, or an error from the previous viewport
  // while a new pan/zoom box is settling or loading.
  const queryMatchesViewport = boxesEqual(box, settledBox);
  return {
    systems: queryMatchesViewport ? (query.data?.systems ?? null) : null,
    truncated: queryMatchesViewport ? (query.data?.truncated ?? false) : false,
    isLoading: detailEnabled && (
      !queryMatchesViewport || query.isLoading || query.isFetching
    ),
    isError: queryMatchesViewport && query.isError,
    error: queryMatchesViewport ? query.error : null,
  };
}
