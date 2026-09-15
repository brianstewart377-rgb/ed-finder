import type { Bounds3Ly, CameraState, Vec3Ly } from './contracts';

export const GALAXY_CAMERA_FOV_RAD = 0.72;
export const GALAXY_CAMERA_MIN_DISTANCE_LY = 2;
export const GALAXY_CAMERA_MAX_DISTANCE_LY = 250_000;
export const GALAXY_CAMERA_MIN_PITCH_RAD = 0.12;
export const GALAXY_CAMERA_MAX_PITCH_RAD = Math.PI / 2;
export const GALAXY_CAMERA_ZOOM_SENSITIVITY = 0.001;
export const GALAXY_CAMERA_TRANSITION_MS = 500;

export type GalaxyCameraViewport = Readonly<{ width: number; height: number }>;
export type GalaxyCameraPose = Readonly<{
  positionLy: Vec3Ly;
  targetLy: Vec3Ly;
  /** Unit screen-up direction, including at the exact top-down pole. */
  up: Vec3Ly;
}>;

function finite(value: number, name: string): number {
  if (!Number.isFinite(value)) throw new RangeError(`${name} must be finite`);
  return value;
}

function coordinates(value: Vec3Ly): Vec3Ly {
  return {
    x: finite(value.x, 'focus x'),
    y: finite(value.y, 'focus y'),
    z: finite(value.z, 'focus z'),
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function wrapBearing(value: number): number {
  const turn = Math.PI * 2;
  return ((((value + Math.PI) % turn) + turn) % turn) - Math.PI;
}

function validateViewport(viewport: GalaxyCameraViewport): void {
  if (
    !Number.isFinite(viewport.width) ||
    viewport.width <= 0 ||
    !Number.isFinite(viewport.height) ||
    viewport.height <= 0
  ) {
    throw new RangeError(
      'Camera viewport must have finite positive dimensions',
    );
  }
}

/**
 * Coordinates remain canonical Elite light-years. Invalid input fails closed;
 * finite distance/pitch are clamped and bearing is wrapped to [-pi, pi).
 * Pitch measures elevation above the x/z plane: pi/2 is exact top-down.
 */
export function normalizeGalaxyCamera(camera: CameraState): CameraState {
  if (!Number.isSafeInteger(camera.revision) || camera.revision < 0) {
    throw new RangeError('Camera revision must be a non-negative safe integer');
  }
  if (
    camera.projection !== 'perspective' &&
    camera.projection !== 'orthographic'
  ) {
    throw new RangeError('Unsupported Galaxy camera projection');
  }
  return {
    focusLy: coordinates(camera.focusLy),
    distanceLy: clamp(
      finite(camera.distanceLy, 'distance'),
      GALAXY_CAMERA_MIN_DISTANCE_LY,
      GALAXY_CAMERA_MAX_DISTANCE_LY,
    ),
    bearingRad: wrapBearing(finite(camera.bearingRad, 'bearing')),
    pitchRad: clamp(
      finite(camera.pitchRad, 'pitch'),
      GALAXY_CAMERA_MIN_PITCH_RAD,
      GALAXY_CAMERA_MAX_PITCH_RAD,
    ),
    projection: camera.projection,
    revision: camera.revision,
  };
}

/** Bearing zero looks towards +z from -z; positive bearing orbits towards +x. */
export function galaxyCameraPose(camera: CameraState): GalaxyCameraPose {
  const state = normalizeGalaxyCamera(camera);
  const sinBearing = Math.sin(state.bearingRad);
  const cosBearing = Math.cos(state.bearingRad);
  const sinPitch = Math.sin(state.pitchRad);
  // Avoid even a tiny horizontal offset at the pole. A world-Y up vector would
  // be collinear here, so derive screen-up from the same spherical basis.
  const cosPitch =
    state.pitchRad === Math.PI / 2 ? 0 : Math.cos(state.pitchRad);
  const horizontalDistance = state.distanceLy * cosPitch;
  return {
    positionLy: coordinates({
      x: state.focusLy.x + sinBearing * horizontalDistance,
      y: state.focusLy.y + sinPitch * state.distanceLy,
      z: state.focusLy.z - cosBearing * horizontalDistance,
    }),
    targetLy: state.focusLy,
    up: {
      x: -sinBearing * sinPitch,
      y: cosPitch,
      z: cosBearing * sinPitch,
    },
  };
}

/**
 * Move focus screen-right/down by pixels on the plane through focusLy.y.
 * Negate pointer-drag deltas for grab-to-pan. The distance/FOV scale also
 * defines the orthographic focus-plane span; browser adapters must match it.
 */
export function panGalaxyCamera(
  camera: CameraState,
  deltaXPx: number,
  deltaYPx: number,
  viewport: GalaxyCameraViewport,
): CameraState {
  const state = normalizeGalaxyCamera(camera);
  validateViewport(viewport);
  const lyPerPixel =
    (2 * state.distanceLy * Math.tan(GALAXY_CAMERA_FOV_RAD / 2)) /
    viewport.height;
  const rightLy = finite(deltaXPx, 'horizontal pan') * lyPerPixel;
  const upLy =
    (-finite(deltaYPx, 'vertical pan') * lyPerPixel) / Math.sin(state.pitchRad);
  const sinBearing = Math.sin(state.bearingRad);
  const cosBearing = Math.cos(state.bearingRad);
  return normalizeGalaxyCamera({
    ...state,
    focusLy: {
      x: state.focusLy.x + cosBearing * rightLy - sinBearing * upLy,
      y: state.focusLy.y,
      z: state.focusLy.z + sinBearing * rightLy + cosBearing * upLy,
    },
    revision: state.revision + 1,
  });
}

/** Positive wheel delta increases viewing distance without moving focus. */
export function zoomGalaxyCamera(
  camera: CameraState,
  delta: number,
): CameraState {
  const state = normalizeGalaxyCamera(camera);
  const logDistance = clamp(
    Math.log(state.distanceLy) +
      finite(delta, 'zoom delta') * GALAXY_CAMERA_ZOOM_SENSITIVITY,
    Math.log(GALAXY_CAMERA_MIN_DISTANCE_LY),
    Math.log(GALAXY_CAMERA_MAX_DISTANCE_LY),
  );
  return normalizeGalaxyCamera({
    ...state,
    distanceLy: Math.exp(logDistance),
    revision: state.revision + 1,
  });
}

export function orbitGalaxyCamera(
  camera: CameraState,
  deltaBearingRad: number,
  deltaPitchRad: number,
): CameraState {
  const state = normalizeGalaxyCamera(camera);
  return normalizeGalaxyCamera({
    ...state,
    bearingRad: state.bearingRad + finite(deltaBearingRad, 'bearing delta'),
    pitchRad: state.pitchRad + finite(deltaPitchRad, 'pitch delta'),
    revision: state.revision + 1,
  });
}

/** Top-down preserves bearing and focus so orientation does not unexpectedly spin. */
export function topDownGalaxyCamera(camera: CameraState): CameraState {
  const state = normalizeGalaxyCamera(camera);
  return normalizeGalaxyCamera({
    ...state,
    pitchRad: GALAXY_CAMERA_MAX_PITCH_RAD,
    revision: state.revision + 1,
  });
}

export function focusGalaxyCamera(
  camera: CameraState,
  focusLy: Vec3Ly,
  distanceLy = camera.distanceLy,
): CameraState {
  const state = normalizeGalaxyCamera(camera);
  return normalizeGalaxyCamera({
    ...state,
    focusLy,
    distanceLy,
    revision: state.revision + 1,
  });
}

/** Fit the bounds' enclosing sphere, subject to the navigation distance limit. */
export function fitGalaxyCamera(
  camera: CameraState,
  bounds: Bounds3Ly,
  viewport: GalaxyCameraViewport,
  padding = 1.15,
): CameraState {
  const state = normalizeGalaxyCamera(camera);
  validateViewport(viewport);
  const min = coordinates(bounds.min);
  const max = coordinates(bounds.max);
  if (min.x > max.x || min.y > max.y || min.z > max.z) {
    throw new RangeError('Galaxy camera bounds must be ordered');
  }
  if (!Number.isFinite(padding) || padding < 1) {
    throw new RangeError(
      'Galaxy camera fit padding must be finite and at least one',
    );
  }
  const focusLy = {
    x: min.x / 2 + max.x / 2,
    y: min.y / 2 + max.y / 2,
    z: min.z / 2 + max.z / 2,
  };
  const radius = Math.hypot(
    max.x / 2 - min.x / 2,
    max.y / 2 - min.y / 2,
    max.z / 2 - min.z / 2,
  );
  const verticalHalfFov = GALAXY_CAMERA_FOV_RAD / 2;
  const horizontalHalfFov = Math.atan(
    (Math.tan(verticalHalfFov) * viewport.width) / viewport.height,
  );
  const halfFov = Math.min(verticalHalfFov, horizontalHalfFov);
  const divisor =
    state.projection === 'perspective' ? Math.sin(halfFov) : Math.tan(halfFov);
  return focusGalaxyCamera(
    state,
    focusLy,
    Math.min(GALAXY_CAMERA_MAX_DISTANCE_LY, (radius * padding) / divisor),
  );
}

/**
 * Fit a flat x/z map in an exact top-down view. Unlike the general enclosing
 * sphere fit, this does not reserve empty depth for the corners of a planar
 * source and therefore uses the viewport much more effectively.
 */
export function fitGalaxyPlaneCamera(
  camera: CameraState,
  bounds: Bounds3Ly,
  viewport: GalaxyCameraViewport,
  padding = 1.1,
): CameraState {
  const state = normalizeGalaxyCamera(camera);
  validateViewport(viewport);
  const min = coordinates(bounds.min);
  const max = coordinates(bounds.max);
  if (min.x > max.x || min.z > max.z) {
    throw new RangeError('Galaxy camera bounds must be ordered');
  }
  if (!Number.isFinite(padding) || padding < 1) {
    throw new RangeError(
      'Galaxy camera fit padding must be finite and at least one',
    );
  }
  const halfX = (max.x - min.x) / 2;
  const halfZ = (max.z - min.z) / 2;
  const sinBearing = Math.abs(Math.sin(state.bearingRad));
  const cosBearing = Math.abs(Math.cos(state.bearingRad));
  const horizontalExtent = cosBearing * halfX + sinBearing * halfZ;
  const verticalExtent = sinBearing * halfX + cosBearing * halfZ;
  const verticalTangent = Math.tan(GALAXY_CAMERA_FOV_RAD / 2);
  const horizontalTangent =
    verticalTangent * (viewport.width / viewport.height);
  const distanceLy =
    Math.max(
      horizontalExtent / horizontalTangent,
      verticalExtent / verticalTangent,
      GALAXY_CAMERA_MIN_DISTANCE_LY,
    ) * padding;
  return normalizeGalaxyCamera({
    ...state,
    focusLy: {
      x: min.x / 2 + max.x / 2,
      y: min.y / 2 + max.y / 2,
      z: min.z / 2 + max.z / 2,
    },
    distanceLy,
    pitchRad: GALAXY_CAMERA_MAX_PITCH_RAD,
    revision: state.revision + 1,
  });
}

/**
 * Sample a cancellable transition: sine easing, logarithmic distance and the
 * shortest bearing turn. Endpoints retain their exact normalized states;
 * interior samples use the destination revision and the source projection.
 */
export function interpolateGalaxyCamera(
  from: CameraState,
  to: CameraState,
  progress: number,
): CameraState {
  const source = normalizeGalaxyCamera(from);
  const target = normalizeGalaxyCamera(to);
  const t = clamp(finite(progress, 'transition progress'), 0, 1);
  if (t === 0) return source;
  if (t === 1) return target;
  const eased = 0.5 - 0.5 * Math.cos(Math.PI * t);
  const mix = (a: number, b: number) => a * (1 - eased) + b * eased;
  return normalizeGalaxyCamera({
    focusLy: {
      x: mix(source.focusLy.x, target.focusLy.x),
      y: mix(source.focusLy.y, target.focusLy.y),
      z: mix(source.focusLy.z, target.focusLy.z),
    },
    distanceLy: Math.exp(
      mix(Math.log(source.distanceLy), Math.log(target.distanceLy)),
    ),
    bearingRad:
      source.bearingRad +
      wrapBearing(target.bearingRad - source.bearingRad) * eased,
    pitchRad: mix(source.pitchRad, target.pitchRad),
    projection: source.projection,
    revision: target.revision,
  });
}
