import type { CameraState, GalaxyCoord } from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import type { ViewportSize } from './types';

export const DEFAULT_CAMERA_PITCH_DEG = 42;
export const MIN_CAMERA_PITCH_DEG = 0.5;
export const MAX_CAMERA_PITCH_DEG = 72;
export const CAMERA_VIEWPORT_HEIGHT_RATIO = 0.78;
export const MIN_ZOOM_LY_PER_PIXEL = 0.01;
export const MAX_ZOOM_LY_PER_PIXEL = 4_096;

export type GalaxyBounds = {
  minX: number;
  maxX: number;
  minZ: number;
  maxZ: number;
};

function clampAxis(
  value: number,
  minimum: number,
  maximum: number,
  visibleHalfExtent: number,
): number {
  const span = maximum - minimum;
  const margin = Math.max(1_000, span * 0.04);
  const boundedMinimum = minimum - margin;
  const boundedMaximum = maximum + margin;
  if (visibleHalfExtent * 2 >= boundedMaximum - boundedMinimum) {
    return (minimum + maximum) / 2;
  }
  return Math.max(
    boundedMinimum + visibleHalfExtent,
    Math.min(boundedMaximum - visibleHalfExtent, value),
  );
}

export function clampCameraCenter(
  center: GalaxyCoord,
  zoom: number,
  viewport: ViewportSize,
  bounds?: GalaxyBounds,
): GalaxyCoord {
  if (!bounds) return center;
  return {
    x: clampAxis(center.x, bounds.minX, bounds.maxX, zoom * viewport.width / 2),
    z: clampAxis(center.z, bounds.minZ, bounds.maxZ, zoom * viewport.height / 2),
  };
}

export function snapCameraTopDown(camera: CameraState): CameraState {
  return {
    ...camera,
    bearingDeg: 0,
    pitchDeg: MIN_CAMERA_PITCH_DEG,
  };
}

export function zoomCamera(
  camera: CameraState,
  deltaY: number,
  viewport: ViewportSize,
  bounds?: GalaxyBounds,
): CameraState {
  const zoom = Math.max(
    MIN_ZOOM_LY_PER_PIXEL,
    Math.min(MAX_ZOOM_LY_PER_PIXEL, camera.zoom * Math.exp(deltaY * 0.001)),
  );
  return {
    ...camera,
    zoom,
    center: clampCameraCenter(camera.center, zoom, viewport, bounds),
  };
}
