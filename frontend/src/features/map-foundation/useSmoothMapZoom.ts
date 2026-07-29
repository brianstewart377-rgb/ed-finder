import { useCallback, useEffect, useRef } from 'react';
import type { CameraState } from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import {
  easeInOutSine,
  MIN_ZOOM_LY_PER_PIXEL,
  ZOOM_TRANSITION_DURATION_MS,
  zoomLevelForDelta,
} from './camera';

type ZoomAnimation = {
  startTime: number;
  duration: number;
  fromLogZoom: number;
  targetLogZoom: number;
  startVelocityLogPerMs: number;
};

type ZoomAnimationSample = {
  logZoom: number;
  velocityLogPerMs: number;
  complete: boolean;
};

type SmoothMapZoomOptions = {
  camera: CameraState;
  onCameraChange: (camera: CameraState) => void;
  durationMs?: number;
};

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';
const EXTERNAL_ZOOM_EPSILON = 1e-9;
const VELOCITY_EPSILON = 1e-10;
const MAX_PENDING_EMISSIONS = 128;

export function sampleZoomAnimation(
  animation: ZoomAnimation,
  timestamp: number,
): ZoomAnimationSample {
  const progress = Math.max(
    0,
    Math.min(1, (timestamp - animation.startTime) / Math.max(1, animation.duration)),
  );
  if (progress >= 1) {
    return {
      logZoom: animation.targetLogZoom,
      velocityLogPerMs: 0,
      complete: true,
    };
  }

  const distance = animation.targetLogZoom - animation.fromLogZoom;
  if (Math.abs(animation.startVelocityLogPerMs) < VELOCITY_EPSILON) {
    const eased = easeInOutSine(progress);
    return {
      logZoom: animation.fromLogZoom + distance * eased,
      velocityLogPerMs: distance
        * 0.5
        * Math.PI
        * Math.sin(Math.PI * progress)
        / animation.duration,
      complete: false,
    };
  }

  // Preserve in-flight velocity when new wheel, pinch, or button input
  // retargets the active movement. This cubic Hermite continuation is the
  // smoothstep equivalent of the isolated sine ease and avoids a value snap or
  // a queue of stale destinations.
  const t2 = progress * progress;
  const t3 = t2 * progress;
  const h00 = 2 * t3 - 3 * t2 + 1;
  const h10 = t3 - 2 * t2 + progress;
  const h01 = -2 * t3 + 3 * t2;
  const startTangent = animation.startVelocityLogPerMs * animation.duration;
  const logZoom = h00 * animation.fromLogZoom
    + h10 * startTangent
    + h01 * animation.targetLogZoom;
  const derivative = (6 * t2 - 6 * progress) * animation.fromLogZoom
    + (3 * t2 - 4 * progress + 1) * startTangent
    + (-6 * t2 + 6 * progress) * animation.targetLogZoom;

  return {
    logZoom,
    velocityLogPerMs: derivative / animation.duration,
    complete: false,
  };
}

export function useSmoothMapZoom({
  camera,
  onCameraChange,
  durationMs = ZOOM_TRANSITION_DURATION_MS,
}: SmoothMapZoomOptions) {
  const cameraRef = useRef(camera);
  const onCameraChangeRef = useRef(onCameraChange);
  const animationRef = useRef<ZoomAnimation | null>(null);
  const targetLogZoomRef = useRef(Math.log(camera.zoom));
  const frameRef = useRef<number | null>(null);
  const pendingEmittedZoomsRef = useRef<number[]>([]);
  const reducedMotionRef = useRef(
    typeof window !== 'undefined'
      && typeof window.matchMedia === 'function'
      && window.matchMedia(REDUCED_MOTION_QUERY).matches,
  );

  const cancelFrame = useCallback(() => {
    if (frameRef.current != null) {
      window.cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
  }, []);

  const cancel = useCallback(() => {
    cancelFrame();
    animationRef.current = null;
    targetLogZoomRef.current = Math.log(cameraRef.current.zoom);
    pendingEmittedZoomsRef.current = [];
  }, [cancelFrame]);

  useEffect(() => {
    cameraRef.current = camera;
    const animation = animationRef.current;
    const emittedIndex = pendingEmittedZoomsRef.current.findIndex(
      (emittedZoom) => Math.abs(Math.log(camera.zoom / emittedZoom)) <= EXTERNAL_ZOOM_EPSILON,
    );
    if (emittedIndex >= 0) {
      // React may commit an earlier animation frame after a newer frame has
      // already been emitted. Accept any still-pending value from this hook,
      // while retaining newer values for the commits that follow.
      pendingEmittedZoomsRef.current.splice(0, emittedIndex + 1);
    }
    if (!animation) {
      if (emittedIndex < 0) {
        targetLogZoomRef.current = Math.log(camera.zoom);
        pendingEmittedZoomsRef.current = [];
      }
      return;
    }

    if (emittedIndex < 0) {
      cancel();
    }
  }, [camera, cancel]);

  useEffect(() => {
    onCameraChangeRef.current = onCameraChange;
  }, [onCameraChange]);

  const emitLogZoom = useCallback((logZoom: number) => {
    const zoom = Math.max(MIN_ZOOM_LY_PER_PIXEL, Math.exp(logZoom));
    pendingEmittedZoomsRef.current.push(zoom);
    if (pendingEmittedZoomsRef.current.length > MAX_PENDING_EMISSIONS) {
      pendingEmittedZoomsRef.current.shift();
    }
    onCameraChangeRef.current({
      ...cameraRef.current,
      // Zoom changes deliberately preserve the current camera centre. The
      // scene scales around the existing focal point instead of drifting while
      // bounds and visible extents change.
      center: { ...cameraRef.current.center },
      zoom,
    });
  }, []);

  const tickRef = useRef<(timestamp: number) => void>(() => undefined);
  tickRef.current = (timestamp: number) => {
    const animation = animationRef.current;
    if (!animation) {
      frameRef.current = null;
      return;
    }
    const sample = sampleZoomAnimation(animation, timestamp);
    emitLogZoom(sample.complete ? animation.targetLogZoom : sample.logZoom);
    if (sample.complete) {
      animationRef.current = null;
      targetLogZoomRef.current = animation.targetLogZoom;
      frameRef.current = null;
      return;
    }
    frameRef.current = window.requestAnimationFrame(tickRef.current);
  };

  const ensureFrame = useCallback(() => {
    if (frameRef.current == null) {
      frameRef.current = window.requestAnimationFrame(tickRef.current);
    }
  }, []);

  const requestDelta = useCallback((deltaY: number) => {
    if (!Number.isFinite(deltaY) || deltaY === 0) return;
    const now = performance.now();
    const activeAnimation = animationRef.current;
    const currentSample = activeAnimation
      ? sampleZoomAnimation(activeAnimation, now)
      : {
          logZoom: Math.log(cameraRef.current.zoom),
          velocityLogPerMs: 0,
          complete: true,
        };
    const baseTargetZoom = Math.exp(
      activeAnimation ? targetLogZoomRef.current : currentSample.logZoom,
    );
    const targetZoom = zoomLevelForDelta(baseTargetZoom, deltaY);
    const targetLogZoom = Math.log(targetZoom);
    targetLogZoomRef.current = targetLogZoom;

    if (reducedMotionRef.current) {
      cancelFrame();
      animationRef.current = null;
      emitLogZoom(targetLogZoom);
      return;
    }

    animationRef.current = {
      startTime: now,
      duration: durationMs,
      fromLogZoom: currentSample.logZoom,
      targetLogZoom,
      startVelocityLogPerMs: currentSample.velocityLogPerMs,
    };
    ensureFrame();
  }, [cancelFrame, durationMs, emitLogZoom, ensureFrame]);

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined;
    const preference = window.matchMedia(REDUCED_MOTION_QUERY);
    const onPreferenceChange = (event: MediaQueryListEvent) => {
      reducedMotionRef.current = event.matches;
      const animation = animationRef.current;
      if (event.matches && animation) {
        cancelFrame();
        animationRef.current = null;
        emitLogZoom(animation.targetLogZoom);
      }
    };
    reducedMotionRef.current = preference.matches;
    preference.addEventListener?.('change', onPreferenceChange);
    return () => preference.removeEventListener?.('change', onPreferenceChange);
  }, [cancelFrame, emitLogZoom]);

  useEffect(() => cancel, [cancel]);

  return { requestDelta, cancel };
}
