import type { CameraState, GalaxyCoord } from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import type { ViewportSize } from './types';

export const DEFAULT_CAMERA_PITCH_DEG = 42;
export const MIN_CAMERA_PITCH_DEG = 0.5;
export const MAX_CAMERA_PITCH_DEG = 72;
export const CAMERA_VIEWPORT_HEIGHT_RATIO = 0.78;
export const MIN_ZOOM_LY_PER_PIXEL = 0.01;
export const MAX_ZOOM_LY_PER_PIXEL = 4_096;
export const ZOOM_TRANSITION_DURATION_MS = 500;
export const KEYBOARD_PAN_ACCELERATION_MS = 260;
export const KEYBOARD_PAN_DECELERATION_MS = 320;

export type KeyboardPanVelocity = {
  x: number;
  z: number;
};

export type KeyboardPanTransition = {
  startTime: number;
  duration: number;
  from: KeyboardPanVelocity;
  target: KeyboardPanVelocity;
};

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
    x: clampAxis(
      center.x,
      bounds.minX,
      bounds.maxX,
      zoom * viewport.width * CAMERA_VIEWPORT_HEIGHT_RATIO / 2,
    ),
    z: clampAxis(
      center.z,
      bounds.minZ,
      bounds.maxZ,
      zoom * viewport.height * CAMERA_VIEWPORT_HEIGHT_RATIO / 2,
    ),
  };
}

export function snapCameraTopDown(camera: CameraState): CameraState {
  return {
    ...camera,
    bearingDeg: 0,
    pitchDeg: MIN_CAMERA_PITCH_DEG,
  };
}

export function zoomLevelForDelta(zoom: number, deltaY: number): number {
  return Math.max(
    MIN_ZOOM_LY_PER_PIXEL,
    Math.min(MAX_ZOOM_LY_PER_PIXEL, zoom * Math.exp(deltaY * 0.001)),
  );
}

export function easeInOutSine(progress: number): number {
  const boundedProgress = Math.max(0, Math.min(1, progress));
  return 0.5 - 0.5 * Math.cos(Math.PI * boundedProgress);
}

export function interpolateZoomLog(
  fromZoom: number,
  toZoom: number,
  progress: number,
): number {
  const easedProgress = easeInOutSine(progress);
  const fromLog = Math.log(Math.max(MIN_ZOOM_LY_PER_PIXEL, fromZoom));
  const toLog = Math.log(Math.max(MIN_ZOOM_LY_PER_PIXEL, toZoom));
  return Math.exp(fromLog + (toLog - fromLog) * easedProgress);
}

export function sampleKeyboardPanTransition(
  transition: KeyboardPanTransition,
  timestamp: number,
): { velocity: KeyboardPanVelocity; complete: boolean } {
  const progress = Math.max(
    0,
    Math.min(1, (timestamp - transition.startTime) / Math.max(1, transition.duration)),
  );
  const easedProgress = easeInOutSine(progress);
  return {
    velocity: {
      x: transition.from.x
        + (transition.target.x - transition.from.x) * easedProgress,
      z: transition.from.z
        + (transition.target.z - transition.from.z) * easedProgress,
    },
    complete: progress >= 1,
  };
}

export function zoomCamera(
  camera: CameraState,
  deltaY: number,
  viewport: ViewportSize,
  bounds?: GalaxyBounds,
): CameraState {
  const zoom = zoomLevelForDelta(camera.zoom, deltaY);
  return {
    ...camera,
    zoom,
    center: clampCameraCenter(camera.center, zoom, viewport, bounds),
  };
}

export function cameraDistanceForView(camera: CameraState, size: ViewportSize): number {
  const visibleHeight = Math.max(
    20,
    camera.zoom * size.height * CAMERA_VIEWPORT_HEIGHT_RATIO,
  );
  return visibleHeight / (2 * Math.tan((42 * Math.PI / 180) / 2));
}

export function attenuatedPointSize(zoom: number, pixels: number): number {
  return Math.max(0.12, zoom * pixels * 0.78);
}
