import { Canvas } from '@react-three/fiber';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from 'react';
import type {
  CameraState,
  SystemRecord,
} from '../../../../artifacts/map-foundation/stage-26b/map-scene-contract';
import type {
  FoundationRendererProps,
} from './types';
import {
  clampCameraCenter,
  KEYBOARD_PAN_ACCELERATION_MS,
  KEYBOARD_PAN_DECELERATION_MS,
  MAX_CAMERA_PITCH_DEG,
  MIN_CAMERA_PITCH_DEG,
  sampleKeyboardPanTransition,
  type KeyboardPanTransition,
  type KeyboardPanVelocity,
  zoomCamera,
} from './camera';
import {
  regionLabelScale,
  safariGestureZoomDelta,
} from './map-presentation';
import {
  decodeAuthoritativeRegionLookup,
  findAuthoritativeRegionAt,
} from './authoritative-regions';
import {
  buildClusterGeometry,
  highlightedSystemIds,
  selectVisibleSystems,
} from './visibility';
import {
  GALACTIC_CORE_GLOW_HEIGHT_LY,
  GALAXY_CENTER,
  GALAXY_POINT_COUNT,
  galacticCoreGlowPresentation,
} from './GalaxyBackdrop';
import { rangeStepForView } from './SceneDecorations';
import {
  GpuTimingBridge,
  projectLabels,
  projectSystemLabels,
  projectWorldPoint,
  RendererSizeSync,
  SceneContents,
} from './SceneContents';

const KEYBOARD_PAN_PIXELS_PER_SECOND = 480;
const KEYBOARD_ZOOM_DELTA_PER_SECOND = 1_200;
const KEYBOARD_TAP_DURATION_SECONDS = 1 / 15;
const MAX_KEYBOARD_FRAME_SECONDS = 0.05;
const KEYBOARD_PAN_VELOCITY_EPSILON = 0.5;
const KEYBOARD_CAMERA_COMMIT_EPSILON = 1e-6;
const MAX_PENDING_KEYBOARD_CAMERAS = 128;
const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';
// WCAG 2.1.4: single-character shortcuts (W/A/S/D/Z/X) must be switchable,
// remappable, or active only while the affected component has focus. This
// listener is document-level by design (see the keyboard-focus fix above),
// so it satisfies 2.1.4 via an explicit off switch instead.
const MAP_KEYBOARD_SHORTCUTS_ENABLED_STORAGE_KEY = 'ed-finder:map-keyboard-shortcuts-enabled';

type MapControlKey = 'w' | 'a' | 's' | 'd' | 'z' | 'x';
type KeyboardPanPhase = 'idle' | 'accelerating' | 'steady' | 'decelerating' | 'reversing';

function mapControlKey(key: string): MapControlKey | null {
  const normalized = key.toLowerCase();
  return normalized === 'w'
    || normalized === 'a'
    || normalized === 's'
    || normalized === 'd'
    || normalized === 'z'
    || normalized === 'x'
    ? normalized
    : null;
}

function protectsFocusFromMap(element: Element | null): boolean {
  if (!(element instanceof HTMLElement)) return false;
  return element.isContentEditable || element.matches(
    'input, textarea, select, [role="textbox"], [role="searchbox"], [role="combobox"]',
  );
}

// A modal (e.g. the System Detail dialog) can be mounted above the map
// without moving focus onto an editable control inside it — focus may sit on
// the dialog itself or a plain button. protectsFocusFromMap alone would let
// W/A/S/D/Z/X leak through to the hidden map camera in that case.
function mapShortcutsSuspendedByOpenModal(): boolean {
  return document.querySelector('[aria-modal="true"]') !== null;
}

function readStoredMapKeyboardShortcutsEnabled(): boolean {
  if (typeof window === 'undefined') return true;
  try {
    return window.localStorage.getItem(MAP_KEYBOARD_SHORTCUTS_ENABLED_STORAGE_KEY) !== 'false';
  } catch {
    return true;
  }
}

function keyboardPanTarget(keys: ReadonlySet<MapControlKey>): KeyboardPanVelocity {
  const horizontal = Number(keys.has('d')) - Number(keys.has('a'));
  const forward = Number(keys.has('w')) - Number(keys.has('s'));
  const magnitude = Math.hypot(horizontal, forward);
  if (magnitude === 0) return { x: 0, z: 0 };
  return {
    x: horizontal / magnitude * KEYBOARD_PAN_PIXELS_PER_SECOND,
    z: forward / magnitude * KEYBOARD_PAN_PIXELS_PER_SECOND,
  };
}

export function R3FMapFoundation(props: FoundationRendererProps) {
  const { onInteraction, onVisibilityChange, onZoomIntent } = props;
  const pointer = useRef<{ x: number; y: number; camera: CameraState } | null>(null);
  const rendererRef = useRef<HTMLDivElement>(null);
  const pressedMapKeys = useRef(new Set<MapControlKey>());
  const [shortcutsEnabled, setShortcutsEnabled] = useState(readStoredMapKeyboardShortcutsEnabled);
  const keyboardFrame = useRef<number | null>(null);
  const keyboardPreviousTime = useRef<number | null>(null);
  const keyboardPanVelocity = useRef<KeyboardPanVelocity>({ x: 0, z: 0 });
  const keyboardPanTransition = useRef<KeyboardPanTransition | null>(null);
  const keyboardPanPhase = useRef<KeyboardPanPhase>('idle');
  const keyboardPanTraceStart = useRef<number | null>(null);
  const pendingKeyboardCameras = useRef<CameraState[]>([]);
  const keyboardPanTrace = useRef<Array<{
    tMs: number;
    centerX: number;
    centerZ: number;
    velocityX: number;
    velocityZ: number;
    phase: KeyboardPanPhase;
  }>>([]);
  const cameraRef = useRef(props.scene.camera);
  const reducedMotion = useRef(
    typeof window !== 'undefined'
      && typeof window.matchMedia === 'function'
      && window.matchMedia(REDUCED_MOTION_QUERY).matches,
  );
  const visible = useMemo(
    () => selectVisibleSystems(props.scene, props.viewport, props.maxBackgroundPoints),
    [props.maxBackgroundPoints, props.scene, props.viewport],
  );
  const labelScale = regionLabelScale(props.scene.camera.zoom);
  const spatial = props.scene.camera.pitchDeg > 4;
  const galacticCoreGlow = galacticCoreGlowPresentation(props.scene.camera.zoom, spatial);
  const decodedRegionLookup = useMemo(
    () => props.viewPreset === 'galaxy' && props.regions.lookup
      ? decodeAuthoritativeRegionLookup(props.regions.lookup)
      : null,
    [props.regions.lookup, props.viewPreset],
  );
  const currentRegion = useMemo(
    () => decodedRegionLookup
      ? findAuthoritativeRegionAt(decodedRegionLookup, props.scene.camera.center)
      : null,
    [decodedRegionLookup, props.scene.camera.center],
  );
  const labels = useMemo(
    () => projectLabels(props, currentRegion?.id),
    [currentRegion?.id, props],
  );
  const galacticCoreProjection = useMemo(() => {
    const centre = projectWorldPoint(
      props.scene.camera,
      props.viewport,
      [GALAXY_CENTER.x, GALAXY_CENTER.z, GALACTIC_CORE_GLOW_HEIGHT_LY],
    );
    const edge = projectWorldPoint(
      props.scene.camera,
      props.viewport,
      [
        GALAXY_CENTER.x + galacticCoreGlow.radiusLy,
        GALAXY_CENTER.z,
        GALACTIC_CORE_GLOW_HEIGHT_LY,
      ],
    );
    return {
      ...centre,
      radius: Math.hypot(edge.x - centre.x, edge.y - centre.y),
    };
  }, [galacticCoreGlow.radiusLy, props.scene.camera, props.viewport]);
  const safariGesture = useRef<{
    startScale: number;
    scale: number;
    camera: CameraState;
  } | null>(null);
  const highlightedIds = useMemo(() => highlightedSystemIds(props.scene.highlights), [props.scene.highlights]);
  const clusters = useMemo(() => buildClusterGeometry(props.scene), [props.scene]);
  const systemLabels = useMemo(() => {
    const byId = new Map<number, SystemRecord>();
    [...visible.background, ...visible.guaranteed].forEach((system) => byId.set(system.id64, system));
    return projectSystemLabels(props, [...byId.values()]);
  }, [props, visible.background, visible.guaranteed]);
  const viewPreset = props.viewPreset ?? 'results';
  const reference = props.reference ?? {
    name: 'Origin',
    x: props.scene.origin.x,
    z: props.scene.origin.z,
  };
  const rangeStep = rangeStepForView(props.scene.camera, props.viewport);
  const rangeLabels = useMemo(() => {
    if (viewPreset === 'galaxy' || spatial) return [];
    const centreX = props.viewport.width / 2
      + (reference.x - props.scene.camera.center.x) / props.scene.camera.zoom;
    const centreY = props.viewport.height / 2
      - (reference.z - props.scene.camera.center.z) / props.scene.camera.zoom;
    return Array.from({ length: 5 }, (_, index) => {
      const distance = rangeStep * (index + 1);
      return {
        distance,
        x: centreX + distance / props.scene.camera.zoom,
        y: centreY,
      };
    });
  }, [
    props.scene.camera,
    props.viewport.height,
    props.viewport.width,
    rangeStep,
    reference.x,
    reference.z,
    spatial,
    viewPreset,
  ]);

  useEffect(() => onVisibilityChange?.(visible.metadata), [onVisibilityChange, visible.metadata]);

  useEffect(() => {
    const camera = props.scene.camera;
    const emittedIndex = pendingKeyboardCameras.current.findIndex((pending) => (
      Math.abs(pending.center.x - camera.center.x) <= KEYBOARD_CAMERA_COMMIT_EPSILON
      && Math.abs(pending.center.z - camera.center.z) <= KEYBOARD_CAMERA_COMMIT_EPSILON
      && Math.abs(pending.zoom - camera.zoom) <= KEYBOARD_CAMERA_COMMIT_EPSILON
    ));
    if (emittedIndex >= 0) {
      pendingKeyboardCameras.current.splice(0, emittedIndex + 1);
      cameraRef.current = {
        ...camera,
        // A parent commit can trail a newer animation-frame emission. Keep the
        // latest locally accumulated centre until that newer commit arrives.
        center: { ...cameraRef.current.center },
      };
      return;
    }
    pendingKeyboardCameras.current = [];
    cameraRef.current = camera;
  }, [props.scene.camera]);

  const emitCamera = useCallback((camera: CameraState) => {
    cameraRef.current = camera;
    onInteraction({ type: 'cameraChanged', camera });
  }, [onInteraction]);

  const emitKeyboardCamera = useCallback((camera: CameraState) => {
    const lastPending = pendingKeyboardCameras.current.at(-1);
    if (
      !lastPending
      || Math.abs(lastPending.center.x - camera.center.x) > KEYBOARD_CAMERA_COMMIT_EPSILON
      || Math.abs(lastPending.center.z - camera.center.z) > KEYBOARD_CAMERA_COMMIT_EPSILON
      || Math.abs(lastPending.zoom - camera.zoom) > KEYBOARD_CAMERA_COMMIT_EPSILON
    ) {
      pendingKeyboardCameras.current.push(camera);
      if (pendingKeyboardCameras.current.length > MAX_PENDING_KEYBOARD_CAMERAS) {
        pendingKeyboardCameras.current.shift();
      }
    }
    cameraRef.current = camera;
    onInteraction({ type: 'cameraChanged', camera });
  }, [onInteraction]);

  const publishKeyboardPanTelemetry = useCallback((
    velocity: KeyboardPanVelocity,
    phase: KeyboardPanPhase,
  ) => {
    const renderer = rendererRef.current;
    if (!renderer) return;
    keyboardPanPhase.current = phase;
    renderer.dataset.keyboardPanVelocityX = velocity.x.toFixed(3);
    renderer.dataset.keyboardPanVelocityZ = velocity.z.toFixed(3);
    renderer.dataset.keyboardPanPhase = phase;
  }, []);

  const sampleKeyboardPan = useCallback((timestamp: number): KeyboardPanVelocity => {
    const transition = keyboardPanTransition.current;
    if (!transition) return keyboardPanVelocity.current;
    const sample = sampleKeyboardPanTransition(transition, timestamp);
    keyboardPanVelocity.current = sample.velocity;
    if (sample.complete) {
      keyboardPanTransition.current = null;
      const stopped = Math.hypot(sample.velocity.x, sample.velocity.z)
        <= KEYBOARD_PAN_VELOCITY_EPSILON;
      if (stopped) keyboardPanVelocity.current = { x: 0, z: 0 };
      publishKeyboardPanTelemetry(
        keyboardPanVelocity.current,
        stopped ? 'idle' : 'steady',
      );
    } else {
      publishKeyboardPanTelemetry(sample.velocity, keyboardPanPhase.current);
    }
    return keyboardPanVelocity.current;
  }, [publishKeyboardPanTelemetry]);

  const retargetKeyboardPan = useCallback((timestamp: number) => {
    const current = sampleKeyboardPan(timestamp);
    const target = keyboardPanTarget(pressedMapKeys.current);
    const targetMagnitude = Math.hypot(target.x, target.z);
    const currentMagnitude = Math.hypot(current.x, current.z);
    if (
      targetMagnitude > KEYBOARD_PAN_VELOCITY_EPSILON
      && currentMagnitude <= KEYBOARD_PAN_VELOCITY_EPSILON
      && keyboardPanTraceStart.current == null
    ) {
      keyboardPanTraceStart.current = timestamp;
      keyboardPanTrace.current = [];
    }
    if (reducedMotion.current) {
      keyboardPanTransition.current = null;
      keyboardPanVelocity.current = target;
      publishKeyboardPanTelemetry(target, targetMagnitude > 0 ? 'steady' : 'idle');
      return;
    }
    if (
      Math.abs(current.x - target.x) <= KEYBOARD_PAN_VELOCITY_EPSILON
      && Math.abs(current.z - target.z) <= KEYBOARD_PAN_VELOCITY_EPSILON
    ) {
      keyboardPanTransition.current = null;
      keyboardPanVelocity.current = target;
      publishKeyboardPanTelemetry(target, targetMagnitude > 0 ? 'steady' : 'idle');
      return;
    }
    const reversing = currentMagnitude > KEYBOARD_PAN_VELOCITY_EPSILON
      && targetMagnitude > KEYBOARD_PAN_VELOCITY_EPSILON
      && current.x * target.x + current.z * target.z < 0;
    keyboardPanTransition.current = {
      startTime: timestamp,
      duration: targetMagnitude === 0
        ? KEYBOARD_PAN_DECELERATION_MS
        : KEYBOARD_PAN_ACCELERATION_MS,
      from: { ...current },
      target,
    };
    publishKeyboardPanTelemetry(
      current,
      targetMagnitude === 0 ? 'decelerating' : reversing ? 'reversing' : 'accelerating',
    );
  }, [publishKeyboardPanTelemetry, sampleKeyboardPan]);

  const recordKeyboardPanFrame = useCallback((
    timestamp: number,
    velocity: KeyboardPanVelocity,
  ) => {
    const traceStart = keyboardPanTraceStart.current;
    if (traceStart == null) return;
    const camera = cameraRef.current;
    keyboardPanTrace.current.push({
      tMs: Number((timestamp - traceStart).toFixed(1)),
      centerX: Number(camera.center.x.toFixed(3)),
      centerZ: Number(camera.center.z.toFixed(3)),
      velocityX: Number(velocity.x.toFixed(3)),
      velocityZ: Number(velocity.z.toFixed(3)),
      phase: keyboardPanPhase.current,
    });
    if (keyboardPanTrace.current.length > 180) keyboardPanTrace.current.shift();
    if (
      keyboardPanPhase.current === 'idle'
      && Math.hypot(velocity.x, velocity.z) <= KEYBOARD_PAN_VELOCITY_EPSILON
    ) {
      const renderer = rendererRef.current;
      if (renderer) {
        renderer.dataset.keyboardPanLastTrace = JSON.stringify(keyboardPanTrace.current);
      }
      keyboardPanTraceStart.current = null;
      keyboardPanTrace.current = [];
    }
  }, []);

  const applyKeyboardPan = useCallback((durationSeconds: number, timestamp: number) => {
    const velocity = sampleKeyboardPan(timestamp);
    recordKeyboardPanFrame(timestamp, velocity);
    if (Math.hypot(velocity.x, velocity.z) <= KEYBOARD_PAN_VELOCITY_EPSILON) return;
    const camera = cameraRef.current;
    const screenX = velocity.x * camera.zoom * durationSeconds;
    const screenZ = velocity.z * camera.zoom * durationSeconds;
    const bearing = camera.bearingDeg * Math.PI / 180;
    const center = clampCameraCenter({
      x: camera.center.x
        + screenX * Math.cos(bearing)
        + screenZ * Math.sin(bearing),
      z: camera.center.z
        - screenX * Math.sin(bearing)
        + screenZ * Math.cos(bearing),
    }, camera.zoom, props.viewport, props.galaxyBounds);
    emitKeyboardCamera({
      ...camera,
      center,
    });
  }, [
    emitKeyboardCamera,
    props.galaxyBounds,
    props.viewport,
    recordKeyboardPanFrame,
    sampleKeyboardPan,
  ]);

  const applyKeyboardZoom = useCallback((durationSeconds: number) => {
    const zoomDirection = Number(pressedMapKeys.current.has('x'))
      - Number(pressedMapKeys.current.has('z'));
    if (zoomDirection === 0) return;
    const deltaY = zoomDirection * KEYBOARD_ZOOM_DELTA_PER_SECOND * durationSeconds;
    if (onZoomIntent) {
      onZoomIntent(deltaY);
      return;
    }
    const camera = cameraRef.current;
    emitCamera(zoomCamera(
      camera,
      deltaY,
      props.viewport,
      props.galaxyBounds,
    ));
  }, [
    emitCamera,
    onZoomIntent,
    props.galaxyBounds,
    props.viewport,
  ]);

  const applyKeyboardInput = useCallback((durationSeconds: number, timestamp: number) => {
    applyKeyboardPan(durationSeconds, timestamp);
    applyKeyboardZoom(durationSeconds);
  }, [applyKeyboardPan, applyKeyboardZoom]);

  const keyboardMotionActive = useCallback(() => (
    keyboardPanTransition.current != null
    || Math.hypot(keyboardPanVelocity.current.x, keyboardPanVelocity.current.z)
      > KEYBOARD_PAN_VELOCITY_EPSILON
    || pressedMapKeys.current.has('z')
    || pressedMapKeys.current.has('x')
  ), []);

  const cancelKeyboardFrame = useCallback(() => {
    keyboardPreviousTime.current = null;
    if (keyboardFrame.current != null) {
      window.cancelAnimationFrame(keyboardFrame.current);
      keyboardFrame.current = null;
    }
  }, []);

  const keyboardTick = useRef<(timestamp: number) => void>(() => undefined);
  keyboardTick.current = (timestamp: number) => {
    if (!keyboardMotionActive()) {
      cancelKeyboardFrame();
      return;
    }
    const previousTime = keyboardPreviousTime.current ?? timestamp;
    const elapsedSeconds = Math.min(
      MAX_KEYBOARD_FRAME_SECONDS,
      Math.max(0, (timestamp - previousTime) / 1_000),
    );
    keyboardPreviousTime.current = timestamp;
    if (elapsedSeconds > 0) applyKeyboardInput(elapsedSeconds, timestamp);
    if (!keyboardMotionActive()) {
      cancelKeyboardFrame();
      return;
    }
    keyboardFrame.current = window.requestAnimationFrame(keyboardTick.current);
  };

  const ensureKeyboardFrame = useCallback(() => {
    if (keyboardFrame.current == null && keyboardMotionActive()) {
      keyboardPreviousTime.current = performance.now();
      keyboardFrame.current = window.requestAnimationFrame(keyboardTick.current);
    }
  }, [keyboardMotionActive]);

  const stopKeyboardInput = useCallback(() => {
    pressedMapKeys.current.clear();
    keyboardPanTransition.current = null;
    keyboardPanVelocity.current = { x: 0, z: 0 };
    keyboardPanTraceStart.current = null;
    keyboardPanTrace.current = [];
    publishKeyboardPanTelemetry(keyboardPanVelocity.current, 'idle');
    cancelKeyboardFrame();
  }, [cancelKeyboardFrame, publishKeyboardPanTelemetry]);

  useEffect(() => {
    publishKeyboardPanTelemetry(keyboardPanVelocity.current, 'idle');
  }, [publishKeyboardPanTelemetry]);

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined;
    const preference = window.matchMedia(REDUCED_MOTION_QUERY);
    const onPreferenceChange = (event: MediaQueryListEvent) => {
      reducedMotion.current = event.matches;
      retargetKeyboardPan(performance.now());
      ensureKeyboardFrame();
    };
    reducedMotion.current = preference.matches;
    preference.addEventListener?.('change', onPreferenceChange);
    return () => preference.removeEventListener?.('change', onPreferenceChange);
  }, [ensureKeyboardFrame, retargetKeyboardPan]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const key = mapControlKey(event.key);
      if (
        !key
        || !shortcutsEnabled
        || event.altKey
        || event.ctrlKey
        || event.metaKey
        || protectsFocusFromMap(document.activeElement)
        || mapShortcutsSuspendedByOpenModal()
      ) return;
      event.preventDefault();
      if (pressedMapKeys.current.has(key)) return;
      pressedMapKeys.current.add(key);
      if (key === 'w' || key === 'a' || key === 's' || key === 'd') {
        retargetKeyboardPan(performance.now());
      } else {
        applyKeyboardZoom(KEYBOARD_TAP_DURATION_SECONDS);
      }
      ensureKeyboardFrame();
    };
    const handleKeyUp = (event: KeyboardEvent) => {
      const key = mapControlKey(event.key);
      // Release a key that this map claimed even if focus moved into a field
      // while it was held, otherwise the camera could keep moving indefinitely.
      if (!key || !pressedMapKeys.current.has(key)) return;
      event.preventDefault();
      pressedMapKeys.current.delete(key);
      if (key === 'w' || key === 'a' || key === 's' || key === 'd') {
        retargetKeyboardPan(performance.now());
      }
      if (keyboardMotionActive()) {
        ensureKeyboardFrame();
      } else {
        cancelKeyboardFrame();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('keyup', handleKeyUp);
    window.addEventListener('blur', stopKeyboardInput);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('keyup', handleKeyUp);
      window.removeEventListener('blur', stopKeyboardInput);
      stopKeyboardInput();
    };
  }, [
    applyKeyboardZoom,
    cancelKeyboardFrame,
    ensureKeyboardFrame,
    keyboardMotionActive,
    retargetKeyboardPan,
    shortcutsEnabled,
    stopKeyboardInput,
  ]);

  const toggleMapKeyboardShortcuts = useCallback(() => {
    setShortcutsEnabled((current) => {
      const next = !current;
      if (!next) stopKeyboardInput();
      try {
        window.localStorage.setItem(MAP_KEYBOARD_SHORTCUTS_ENABLED_STORAGE_KEY, String(next));
      } catch {
        // Storage unavailable (private browsing, quota) -- preference just
        // won't persist across reloads; the in-memory toggle still works.
      }
      return next;
    });
  }, [stopKeyboardInput]);

  const handleWheel = useCallback((event: WheelEvent) => {
    event.preventDefault();
    if (onZoomIntent) {
      onZoomIntent(event.deltaY);
      return;
    }
    emitCamera(zoomCamera(
      props.scene.camera,
      event.deltaY,
      props.viewport,
      props.galaxyBounds,
    ));
  }, [
    emitCamera,
    onZoomIntent,
    props.galaxyBounds,
    props.scene.camera,
    props.viewport,
  ]);

  useEffect(() => {
    const element = rendererRef.current;
    if (!element) return undefined;
    const handleGestureStart = (event: Event) => {
      const gesture = event as Event & { scale?: number };
      event.preventDefault();
      const scale = gesture.scale ?? 1;
      safariGesture.current = {
        startScale: scale,
        scale,
        camera: props.scene.camera,
      };
    };
    const handleGestureChange = (event: Event) => {
      if (!safariGesture.current) return;
      const gesture = event as Event & { scale?: number };
      event.preventDefault();
      const nextScale = gesture.scale ?? safariGesture.current.scale;
      const deltaY = safariGestureZoomDelta(safariGesture.current.scale, nextScale);
      safariGesture.current.scale = nextScale;
      if (onZoomIntent) {
        onZoomIntent(deltaY);
        return;
      }
      emitCamera(zoomCamera(
        safariGesture.current.camera,
        safariGestureZoomDelta(safariGesture.current.startScale, nextScale),
        props.viewport,
        props.galaxyBounds,
      ));
    };
    const handleGestureEnd = () => {
      safariGesture.current = null;
    };
    element.addEventListener('wheel', handleWheel, { passive: false, capture: true });
    element.addEventListener('gesturestart', handleGestureStart, { passive: false });
    element.addEventListener('gesturechange', handleGestureChange, { passive: false });
    element.addEventListener('gestureend', handleGestureEnd);
    return () => {
      element.removeEventListener('wheel', handleWheel, { capture: true });
      element.removeEventListener('gesturestart', handleGestureStart);
      element.removeEventListener('gesturechange', handleGestureChange);
      element.removeEventListener('gestureend', handleGestureEnd);
    };
  }, [
    emitCamera,
    handleWheel,
    onZoomIntent,
    props.galaxyBounds,
    props.scene.camera,
    props.viewport,
  ]);

  return <div
    ref={rendererRef}
    className="map-foundation-renderer"
    role="region"
    tabIndex={0}
    aria-label="Interactive galaxy map. Use W A S D to pan, Z to zoom in, and X to zoom out."
    aria-keyshortcuts={shortcutsEnabled ? 'W A S D Z X' : undefined}
    data-keyboard-controls="WASD pan; Z zoom in; X zoom out"
    data-keyboard-pan-acceleration-ms={KEYBOARD_PAN_ACCELERATION_MS}
    data-keyboard-pan-deceleration-ms={KEYBOARD_PAN_DECELERATION_MS}
    data-projection="perspective"
    data-camera-view={spatial ? 'tilted' : 'top-down'}
    data-view-preset={viewPreset}
    data-camera-bearing={props.scene.camera.bearingDeg}
    data-camera-pitch={props.scene.camera.pitchDeg}
    data-camera-zoom={props.scene.camera.zoom}
    data-camera-center-x={props.scene.camera.center.x}
    data-camera-center-z={props.scene.camera.center.z}
    data-current-region-id={currentRegion?.id}
    data-current-region-name={currentRegion?.name}
    data-galactic-core-world-x={GALAXY_CENTER.x}
    data-galactic-core-world-z={GALAXY_CENTER.z}
    data-galactic-core-radius-ly={galacticCoreGlow.radiusLy}
    data-galactic-core-opacity={galacticCoreGlow.opacity}
    data-galactic-core-screen-x={galacticCoreProjection.x}
    data-galactic-core-screen-y={galacticCoreProjection.y}
    data-galactic-core-screen-radius={galacticCoreProjection.radius}
    data-galactic-core-screen-depth={galacticCoreProjection.depth}
    data-galaxy-point-count={GALAXY_POINT_COUNT}
    onPointerDownCapture={(event) => {
      // Let the keyboard-shortcuts toggle (and any other interactive
      // descendant added later) receive its own click normally instead of
      // having pointer capture redirected to the renderer.
      if (
        event.target instanceof Element
        && event.target.closest('.map-foundation-keyboard-shortcuts-toggle')
      ) return;
      event.currentTarget.focus({ preventScroll: true });
      pointer.current = { x: event.clientX, y: event.clientY, camera: props.scene.camera };
      event.currentTarget.setPointerCapture(event.pointerId);
    }}
    onPointerMove={(event) => {
      if (!pointer.current || event.buttons !== 1) return;
      const dx = event.clientX - pointer.current.x;
      const dy = event.clientY - pointer.current.y;
      if (event.shiftKey) {
        emitCamera({
          ...pointer.current.camera,
          bearingDeg: 0,
          pitchDeg: Math.max(
            MIN_CAMERA_PITCH_DEG,
            Math.min(MAX_CAMERA_PITCH_DEG, pointer.current.camera.pitchDeg + dy * 0.2),
          ),
        });
      } else {
        const bearing = pointer.current.camera.bearingDeg * Math.PI / 180;
        const screenX = -dx * pointer.current.camera.zoom;
        const screenZ = dy * pointer.current.camera.zoom;
        const center = clampCameraCenter({
          x: pointer.current.camera.center.x + screenX * Math.cos(bearing) + screenZ * Math.sin(bearing),
          z: pointer.current.camera.center.z - screenX * Math.sin(bearing) + screenZ * Math.cos(bearing),
        }, pointer.current.camera.zoom, props.viewport, props.galaxyBounds);
        emitCamera({
          ...pointer.current.camera,
          center,
        });
      }
    }}
    onPointerUp={() => { pointer.current = null; }}
    onPointerCancel={() => { pointer.current = null; }}>
    <Canvas
      frameloop="demand"
      dpr={[1, 2]}
      camera={{ fov: 42, near: 0.1, far: 500_000 }}
      gl={{ antialias: true, powerPreference: 'high-performance' }}
      onCreated={({ gl }) => {
        const canvas = gl.domElement;
        canvas.addEventListener('webglcontextlost', (event) => {
          event.preventDefault();
          props.onInteraction({ type: 'contextStateChanged', state: 'lost' });
        });
        canvas.addEventListener('webglcontextrestored', () => {
          props.onInteraction({ type: 'contextStateChanged', state: 'restored' });
        });
        props.onReady?.();
      }}>
      <color attach="background" args={['#010306']} />
      <RendererSizeSync viewport={props.viewport} />
      <GpuTimingBridge onReady={props.onGpuTimerReady} />
      <SceneContents {...props} visible={visible} />
    </Canvas>
    <div className="map-foundation-map-readout" aria-hidden="true">
      <strong>
        {viewPreset === 'galaxy'
          ? 'Whole galaxy'
          : viewPreset === 'reference'
            ? `${reference.name} origin chart`
            : 'Finder result chart'}
      </strong>
      <span>
        {viewPreset === 'galaxy'
          ? `${props.regions.labels.length} named regions · galactic plane`
          : `${rangeStep.toLocaleString()} LY rings · ${reference.name} at centre`}
      </span>
      <span className="map-foundation-control-hint">
        <b>Controls</b>
        {' · Drag or W/A/S/D to pan · Shift-drag to tilt · Scroll, pinch, +/−, or Z in / X out'}
      </span>
    </div>
    {/* Not aria-hidden: WCAG 2.1.4 requires a way to turn off single-character
        keyboard shortcuts (W/A/S/D/Z/X) since they are active document-wide,
        not only while the renderer has focus. */}
    <button
      type="button"
      className="map-foundation-keyboard-shortcuts-toggle"
      aria-pressed={shortcutsEnabled}
      onClick={toggleMapKeyboardShortcuts}
    >
      {shortcutsEnabled ? 'Disable map keyboard shortcuts' : 'Enable map keyboard shortcuts'}
    </button>
    <div className="map-foundation-labels" aria-hidden="true">
      {labels.filter((label) => label.visible).map((label) => <span key={label.id}
        className={label.id === currentRegion?.id ? 'is-current-region' : undefined}
        data-region-name={label.name}
        data-current-region-id={label.id === currentRegion?.id ? label.id : undefined}
        style={{
          left: label.screen.x,
          top: label.screen.z,
          '--region-label-scale': labelScale,
        } as CSSProperties}>{label.name}</span>)}
    </div>
    <div className="map-foundation-range-labels" aria-hidden="true">
      {rangeLabels.map((label) => <span
        key={label.distance}
        style={{ left: label.x, top: label.y }}
      >
        {label.distance.toLocaleString()} LY
      </span>)}
    </div>
    <div className="map-foundation-system-labels" aria-hidden="true">
      {systemLabels.map((label) => <span
        key={label.id}
        className={label.selected ? 'is-selected' : undefined}
        style={{ left: label.screen.x, top: label.screen.z }}
      >
        {label.name}
      </span>)}
    </div>
    <div className="map-foundation-cluster-labels" aria-hidden="true">
      {clusters.flatMap(({ cluster, anchor }) => {
        if (!anchor) return [];
        const label = projectLabels({
          ...props,
          viewPreset: 'galaxy',
          regions: {
            boundaries: [],
            labels: [{
              id: cluster.anchorId64,
              name: cluster.label,
              position: [
                anchor.coords.x,
                anchor.coords.z,
                anchor.coords.y,
              ],
            }],
          },
        })[0];
        return label?.visible ? [<span key={`${cluster.anchorId64}:${cluster.label}`}
          style={{ left: label.screen.x, top: label.screen.z - 18 }}>{cluster.label}</span>] : [];
      })}
    </div>
    <output className="map-foundation-render-stats" aria-label="Renderer draw summary">
      {(visible.metadata.returnedBackground + visible.metadata.guaranteedCount).toLocaleString()}
      {' Finder systems · '}{highlightedIds.size} highlighted
      {props.productionOverlays?.heatmap && ` · ${props.productionOverlays.heatmap.cellCount.toLocaleString()} heatmap`}
      {props.productionOverlays?.aggregateHulls && ` · ${props.productionOverlays.aggregateHulls.hullCount.toLocaleString()} aggregate hulls`}
    </output>
  </div>;
}
