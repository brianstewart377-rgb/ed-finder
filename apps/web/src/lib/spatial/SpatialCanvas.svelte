<script lang="ts">
  import { onMount, tick, untrack } from 'svelte';
  import { SvelteMap } from 'svelte/reactivity';
  import { resolve } from '$app/paths';
  import { FINDER_F4_ENABLED } from '$lib/config';

  import type {
    Bounds3Ly,
    BodyRef,
    BodyVisualDescriptor,
    CameraState,
    GalaxySystemPoint,
    Provenance,
    RuntimeEvent,
    SpatialRuntime,
    SpatialRuntimeStatus,
    SpatialContribution,
    SpatialSceneContract,
    SpatialTarget,
    SystemCameraState,
  } from './contracts';
  import {
    GALAXY_CAMERA_NAVIGATION_BOUNDS_LY,
    elevateGalaxyCameraByPixels,
    elevateGalaxyCameraStep,
    orbitGalaxyCamera,
    panGalaxyCamera,
    pinchGalaxyCamera,
    topDownGalaxyCamera,
    zoomGalaxyCamera,
    zoomGalaxyCameraTowards,
    type GalaxyCameraPoint,
  } from './galaxy-camera';
  import {
    CATALOGUE_DENSITY_LAYER_ID,
    catalogueDensitySceneLayer,
  } from './galaxy-density';
  import { galaxyReferenceGrid } from './galaxy-grid';
  import {
    galaxyLabelCandidates,
    galaxySystemPointIndex,
    layoutGalaxyLabels,
    projectGalaxyLabel,
    type GalaxyLabelCandidate,
    type ProjectedGalaxyLabel,
  } from './galaxy-labels';
  import GalaxySystemHoverCard from './GalaxySystemHoverCard.svelte';
  import SystemBodyLegend from './SystemBodyLegend.svelte';

  let {
    scene,
    focusTarget = null,
    focusRevision = 0,
    cameraRequest = null,
    cameraRequestRevision = 0,
    contributionPatch = null,
    contributionPatchRevision = 0,
    onRuntimeEvent,
    onTransitionChange,
    anchorPoint = null,
    onSystemSelect,
    systemInspectHref,
    onSystemInspect,
  } = $props<{
    scene?: SpatialSceneContract;
    focusTarget?: SpatialTarget | null;
    focusRevision?: number;
    cameraRequest?: CameraState | null;
    cameraRequestRevision?: number;
    contributionPatch?: SpatialContribution | null;
    contributionPatchRevision?: number;
    onRuntimeEvent?: (event: RuntimeEvent) => void;
    anchorPoint?: GalaxySystemPoint | null;
    onSystemSelect?: (system: GalaxySystemPoint) => void;
    systemInspectHref?: (system: GalaxySystemPoint) => string;
    onSystemInspect?: (event: MouseEvent, system: GalaxySystemPoint) => void;
    onTransitionChange?: (
      active: boolean,
      camera?: CameraState | SystemCameraState | null,
    ) => void;
  }>();

  let canvas: HTMLCanvasElement;
  let host: HTMLDivElement;
  let runtime: SpatialRuntime | null = null;
  let status = $state<SpatialRuntimeStatus>({ state: 'created' });
  let resizeRevision = $state(0);
  let lastLoadedRevision = $state(-1);
  let lastFocusRevision = -1;
  let lastCameraRequestRevision = -1;
  let lastContributionPatchRevision = -1;
  let currentCamera = $state<CameraState | null>(null);
  let currentSystemCamera = $state<SystemCameraState | null>(null);
  let homeCamera: CameraState | null = null;
  let homeSystemCamera: SystemCameraState | null = null;
  const canGalaxyNavigate = $derived(scene?.kind === 'galaxy');
  const canSystemNavigate = $derived(scene?.kind === 'system');
  const canNavigate = $derived(canGalaxyNavigate || canSystemNavigate);
  const cameraDensityContribution = $derived.by(() => {
    if (scene?.kind !== 'galaxy') return undefined;
    const contributions: readonly SpatialContribution[] = scene.contributions;
    for (const part of contributions) {
      // F4 reserves an empty contribution until its first density patch.
      const contribution: SpatialContribution =
        contributionPatch?.id === part.id &&
        part.revision < contributionPatch.revision
          ? contributionPatch
          : part;
      if (
        contribution.layers.some(
          (layer) => layer.id === CATALOGUE_DENSITY_LAYER_ID,
        )
      )
        return contribution;
    }
    return undefined;
  });
  const cameraDensity = $derived.by(() => {
    const contribution = cameraDensityContribution;
    if (!contribution) return undefined;
    // Camera receipts replace the scene object. Validate density only when
    // the contribution changes, so a drag never rescans its catalogue cells.
    const galaxyScene = untrack(() => scene);
    if (galaxyScene?.kind !== 'galaxy') return undefined;
    return catalogueDensitySceneLayer({
      ...galaxyScene,
      contributions: [contribution],
    })?.payload;
  });
  let cameraBounds = $state<Bounds3Ly | undefined>();
  let cameraBoundsGeneration: string | undefined;
  $effect(() => {
    const density = cameraDensity;
    if (!density) return;
    if (density.generationId !== cameraBoundsGeneration) {
      cameraBoundsGeneration = density.generationId;
      cameraBounds = undefined;
    }
    // Truncated responses describe only the densest cells. Retain the last
    // complete catalogue extent while a finer level refreshes this generation.
    if (density.complete) cameraBounds = density.boundsLy;
  });
  type ActivePointer = {
    id: number;
    pointerType: string;
    x: number;
    y: number;
    startX: number;
    startY: number;
    moved: boolean;
    mode: 'pan' | 'orbit' | 'elevate';
  };
  const activePointers = new SvelteMap<number, ActivePointer>();
  let removeWindowDragListeners: (() => void) | null = null;
  let lastPickedId64 = $state<string | undefined>();
  let lastPickedRegionId = $state<string | undefined>();
  let lastHoveredRegionId = $state<string | undefined>();
  let lastHoveredBodyRef = $state<BodyRef | undefined>();
  const hoveredBody = $derived(
    scene?.kind === 'system' &&
      scene.systemId64 === lastHoveredBodyRef?.systemId64
      ? scene.bodies.find(
          (body: BodyVisualDescriptor) =>
            body.ref.bodyId === lastHoveredBodyRef?.bodyId,
        )
      : undefined,
  );
  $effect.pre(() => {
    if (
      scene?.kind !== 'system' ||
      scene.systemId64 !== lastHoveredBodyRef?.systemId64
    )
      lastHoveredBodyRef = undefined;
  let cameraTransitionActive = $state(false);
  let hoveredSystemId64 = $state<string | undefined>();
  let hoverPosition = $state({ x: 16, y: 16 });
  let hoverClearTimeout: number | null = null;
  let tooltipHost = $state<HTMLDivElement>();
  let nearbyOpen = $state(false);
  const componentId = $props.id();
  const tooltipId = `${componentId}-system-tooltip`;
  const systemKeyboardHelpId = `${componentId}-system-keyboard-help`;
  let hoverOpener: HTMLElement | null = null;
  let restoringHoverFocus = false;
  let focusCardRequested = $state(false);
  const pointIndex = $derived(
    scene?.kind === 'galaxy' ? galaxySystemPointIndex(scene) : null,
  );
  const hoveredSystem = $derived(
    hoveredSystemId64
      ? (pointIndex?.get(hoveredSystemId64) ??
          (anchorPoint?.systemId64 === hoveredSystemId64 ? anchorPoint : null))
      : null,
  );
  let labelCandidates = $state.raw<GalaxyLabelCandidate[]>([]);
  let visibleGalaxyLabels = $state.raw<ProjectedGalaxyLabel[]>([]);
  let labelCamera = $state.raw<CameraState | null>(null);
  const labelsMoving = $derived(
    cameraTransitionActive || labelCamera !== currentCamera,
  );
  const nearbySystems = $derived(
    labelCandidates
      .filter((label) => label.kind === 'system' && label.point)
      // Priority chooses membership/placement. Stable DOM order keeps Tab and
      // existing keyboard focus predictable when hover changes that priority.
      .sort(
        (left, right) =>
          left.text.localeCompare(right.text) ||
          left.key.localeCompare(right.key),
      ),
  );
  const renderedGalaxyLabels = $derived(
    [...visibleGalaxyLabels].sort((left, right) =>
      left.key.localeCompare(right.key),
    ),
  );
  $effect(() => {
    if (!focusCardRequested || !hoveredSystem || labelsMoving) return;
    void tick().then(() => {
      tooltipHost?.querySelector<HTMLButtonElement>('button')?.focus();
      focusCardRequested = false;
    });
  });
  $effect(() => {
    // A pointer no longer identifies the same star once the camera moves.
    // Keyboard-triggered cards instead remain associated with their trigger.
    void currentCamera;
    untrack(() => {
      if (!hoverOpener) dismissHover();
    });
  });
  let lastSettledFocusId64 = $state<string | undefined>();
  let lastSettledFocusBodyId = $state<number | undefined>();
  let lastAppliedSceneRevision = $state<number | undefined>();
  let lastAppliedContributionRevision = $state<number | undefined>();
  let renderedLayerIds = $state<string[]>([]);
  let pendingHoverPoint: { x: number; y: number } | null = null;
  let transitionCamera: CameraState | SystemCameraState | null = null;
  let pendingPickPoint: { screenX: number; screenY: number } | null = null;
  type PendingCameraMove =
    | { type: 'SET_CAMERA'; camera: CameraState; animate: boolean }
    | { type: 'FLY_TO'; target: SpatialTarget; reducedMotion: boolean };
  let pendingCameraMove: PendingCameraMove | null = null;
  let pendingScene: SpatialSceneContract | null = null;
  let recoverCurrentCamera = false;
  let hoverFrame: number | null = null;

  function setCameraTransitionActive(
    active: boolean,
    camera?: CameraState | SystemCameraState | null,
  ): void {
    cameraTransitionActive = active;
    onTransitionChange?.(active, camera);
  }

  function dispatchPendingFocus(): void {
    if (
      status.state !== 'ready' ||
      !runtime ||
      !focusTarget ||
      focusRevision === lastFocusRevision ||
      scene?.revision !== lastLoadedRevision
    ) {
      return;
    }
    const reducedMotion = window.matchMedia(
      '(prefers-reduced-motion: reduce)',
    ).matches;
    const result = runtime.dispatch({
      type: 'FLY_TO',
      target: focusTarget,
      reducedMotion,
    });
    if (result.status === 'executed') {
      lastFocusRevision = focusRevision;
      setCameraTransitionActive(!reducedMotion);
    }
  }

  function targetCount(value: SpatialSceneContract | undefined): number {
    return layerTargetCount(value, 'finder-systems');
  }

  function layerTargetCount(
    value: SpatialSceneContract | undefined,
    layerId: string,
  ): number {
    return (
      value?.contributions.reduce(
        (total, contribution) =>
          total +
          contribution.layers.reduce(
            (layerTotal, layer) =>
              layerTotal + (layer.id === layerId ? layer.targetCount : 0),
            0,
          ),
        0,
      ) ?? 0
    );
  }

  const statusLabel = $derived.by(() => {
    switch (status.state) {
      case 'ready':
        return `Renderer ready (${status.backend})`;
      case 'failed':
        return `Renderer unavailable (${status.failure})`;
      case 'disposed':
        return 'Renderer disposed';
      default:
        return 'Renderer starting';
    }
  });

  const statusBackend = $derived(
    status.state === 'ready' ? status.backend : undefined,
  );
  const sceneTargetCount = $derived(targetCount(scene));
  const systemTargetCount = $derived(layerTargetCount(scene, 'finder-systems'));
  $effect(() => {
    // Like viewport streaming, labels use the settled view. Never rank or solve
    // overlap on CAMERA_CHANGED animation frames or during a held drag.
    void resizeRevision;
    const nextScene = scene;
    const camera = currentCamera;
    const regionId = lastHoveredRegionId;
    const systemId = hoveredSystemId64;
    const reference = anchorPoint;
    if (nextScene?.kind !== 'galaxy' || !camera || !host) {
      labelCandidates = [];
      visibleGalaxyLabels = [];
      return;
    }
    if (cameraTransitionActive) return;
    const timeout = window.setTimeout(() => {
      const size = viewport();
      labelCandidates = galaxyLabelCandidates(
        { ...nextScene, camera },
        regionId,
        {
          hoveredSystemId64: systemId,
          anchor: reference ?? undefined,
          viewport: size,
        },
      );
      visibleGalaxyLabels = layoutGalaxyLabels(labelCandidates, camera, size);
      labelCamera = camera;
    }, 180);
    return () => window.clearTimeout(timeout);
  });
  const atlasRegionLabels = $derived(
    visibleGalaxyLabels.filter(
      (label) => label.kind === 'region' && label.placement !== 'map',
    ),
  );
  const currentGrid = $derived.by(() => {
    // Keep resizeRevision a reactive dependency (see visibleGalaxyLabels).
    void resizeRevision;
    if (!canGalaxyNavigate || !currentCamera || !host) return null;
    return galaxyReferenceGrid(currentCamera, {
      width: Math.max(1, host.clientWidth),
      height: Math.max(1, host.clientHeight),
    });
  });

  function lightYearInterval(value: number | undefined): string {
    if (!value) return '—';
    return `${value.toLocaleString(undefined, {
      maximumFractionDigits: value < 1 ? 2 : 0,
    })} ly`;
  }

  function applyScene(nextScene: SpatialSceneContract): void {
    if (!runtime || status.state !== 'ready') return;
    if (FINDER_F4_ENABLED && recoverCurrentCamera) {
      // F4 camera receipts do not rebuild the parent's scene snapshot. A
      // context recovery must resume the view currently owned by the canvas.
      const camera = untrack(() =>
        nextScene.kind === 'galaxy' ? currentCamera : currentSystemCamera,
      );
      if (nextScene.kind === 'galaxy' && camera && 'focusLy' in camera) {
        nextScene = { ...nextScene, camera };
      } else if (
        nextScene.kind === 'system' &&
        camera &&
        'systemId64' in camera &&
        camera.systemId64 === nextScene.systemId64
      ) {
        nextScene = { ...nextScene, camera };
      }
    }
    // Density can be patched while a scene waits for a camera flight to settle,
    // or after the parent last built a scene that must now be recovered. Keep
    // that newer contribution in its reserved position without a second patch
    // dispatch or making patch receipts a scene-effect dependency.
    const latestPatch = FINDER_F4_ENABLED
      ? untrack(() => contributionPatch)
      : null;
    if (
      latestPatch &&
      nextScene.contributions.some(
        (part) =>
          part.id === latestPatch.id && part.revision < latestPatch.revision,
      )
    ) {
      nextScene = {
        ...nextScene,
        contributions: nextScene.contributions.map((part) =>
          part.id === latestPatch.id ? latestPatch : part,
        ),
      };
    }
    if (
      runtime.dispatch({ type: 'LOAD_SCENE', scene: nextScene }).status ===
      'executed'
    ) {
      if (!homeCamera && nextScene.kind === 'galaxy')
        homeCamera = nextScene.camera;
      if (nextScene.kind === 'system') {
        homeSystemCamera = nextScene.camera;
        currentSystemCamera = nextScene.camera;
      }
      lastLoadedRevision = nextScene.revision;
      recoverCurrentCamera = false;
    }
  }

  $effect(() => {
    if (
      status.state !== 'ready' ||
      !runtime ||
      !scene ||
      scene.revision === lastLoadedRevision
    ) {
      return;
    }
    if (cameraTransitionActive) {
      pendingScene = scene;
      return;
    }
    applyScene(scene);
  });

  $effect(() => {
    if (
      status.state !== 'ready' ||
      !runtime ||
      !contributionPatch ||
      contributionPatchRevision === lastContributionPatchRevision ||
      scene?.revision !== lastLoadedRevision
    ) {
      return;
    }
    const result = runtime.dispatch({
      type: 'PATCH_CONTRIBUTION',
      contribution: contributionPatch,
    });
    if (result.status !== 'ignored' || result.reason !== 'inactive') {
      lastContributionPatchRevision = contributionPatchRevision;
    }
  });

  function dispatchCameraMove(move: PendingCameraMove): void {
    if (!runtime || status.state !== 'ready') return;

    if (move.type === 'SET_CAMERA') {
      const { camera, animate } = move;
      const reducedMotion = window.matchMedia(
        '(prefers-reduced-motion: reduce)',
      ).matches;
      const result = runtime.dispatch({
        type: 'SET_CAMERA',
        camera,
        ...(animate ? { transition: { durationMs: 650, reducedMotion } } : {}),
      });
      if (result.status === 'executed') {
        currentCamera = camera;
        if (animate && !reducedMotion) {
          transitionCamera = camera;
          setCameraTransitionActive(true, camera);
        }
      }
      return;
    }

    const { target, reducedMotion } = move;
    const result = runtime.dispatch({
      type: 'FLY_TO',
      target,
      reducedMotion,
    });
    if (result.status === 'executed') {
      setCameraTransitionActive(!reducedMotion);
    }
  }

  function setCamera(camera: CameraState, animate = false): void {
    if (!runtime || status.state !== 'ready') return;
    if (cameraTransitionActive) {
      pendingCameraMove = { type: 'SET_CAMERA', camera, animate };
      return;
    }
    dispatchCameraMove({ type: 'SET_CAMERA', camera, animate });
  }

  function setSystemCamera(camera: SystemCameraState): void {
    if (!runtime || status.state !== 'ready') return;
    if (runtime.dispatch({ type: 'SET_CAMERA', camera }).status === 'executed')
      currentSystemCamera = camera;
  }

  $effect(() => {
    if (
      status.state !== 'ready' ||
      !runtime ||
      !cameraRequest ||
      cameraRequestRevision === lastCameraRequestRevision ||
      scene?.revision !== lastLoadedRevision
    )
      return;
    setCamera(cameraRequest, true);
    lastCameraRequestRevision = cameraRequestRevision;
  });

  $effect(() => {
    if (scene?.kind === 'galaxy' && currentCamera === null)
      currentCamera = scene.camera;
    if (scene?.kind === 'system' && currentSystemCamera === null)
      currentSystemCamera = scene.camera;
  });

  function viewport(): { width: number; height: number } {
    return {
      width: Math.max(1, host.clientWidth),
      height: Math.max(1, host.clientHeight),
    };
  }

  function pan(x: number, y: number): void {
    if (currentCamera)
      setCamera(
        panGalaxyCamera(
          currentCamera,
          x,
          y,
          viewport(),
          cameraBounds ?? GALAXY_CAMERA_NAVIGATION_BOUNDS_LY,
        ),
      );
  }

  function zoom(delta: number): void {
    if (currentCamera) setCamera(zoomGalaxyCamera(currentCamera, delta));
  }

  function elevate(direction: 1 | -1): void {
    if (currentCamera)
      setCamera(
        elevateGalaxyCameraStep(currentCamera, direction, cameraBounds),
      );
  }

  function orbit(bearing: number, pitch = 0): void {
    if (currentCamera)
      setCamera(orbitGalaxyCamera(currentCamera, bearing, pitch));
  }

  function orbitSystem(bearing: number, pitch = 0): void {
    if (!currentSystemCamera) return;
    setSystemCamera({
      ...currentSystemCamera,
      bearingRad: currentSystemCamera.bearingRad + bearing,
      pitchRad: Math.max(
        0.08,
        Math.min(1.42, currentSystemCamera.pitchRad + pitch),
      ),
      revision: currentSystemCamera.revision + 1,
    });
  }

  function zoomSystem(delta: number): void {
    if (!currentSystemCamera) return;
    setSystemCamera({
      ...currentSystemCamera,
      semanticDistance: Math.max(
        6,
        Math.min(
          120,
          currentSystemCamera.semanticDistance * Math.exp(delta * 0.0014),
        ),
      ),
      revision: currentSystemCamera.revision + 1,
    });
  }

  function resetCamera(): void {
    if (canSystemNavigate && homeSystemCamera) {
      setSystemCamera({
        ...homeSystemCamera,
        revision: (currentSystemCamera?.revision ?? 0) + 1,
      });
    } else if (homeCamera)
      setCamera(
        { ...homeCamera, revision: (currentCamera?.revision ?? 0) + 1 },
        true,
      );
  }

  function cameraKey(event: KeyboardEvent): void {
    if (
      !canNavigate ||
      event.target !== host ||
      event.altKey ||
      event.metaKey ||
      event.ctrlKey
    )
      return;
    const step = event.shiftKey ? 80 : 32;
    if (canSystemNavigate) {
      switch (event.key) {
        case 'ArrowLeft':
          orbitSystem(-0.12);
          break;
        case 'ArrowRight':
          orbitSystem(0.12);
          break;
        case 'ArrowUp':
          orbitSystem(0, 0.09);
          break;
        case 'ArrowDown':
          orbitSystem(0, -0.09);
          break;
        case '+':
        case '=':
          zoomSystem(-180);
          break;
        case '-':
        case '_':
          zoomSystem(180);
          break;
        case 'Home':
          resetCamera();
          break;
        default:
          return;
      }
      event.preventDefault();
      return;
    }
    switch (event.key) {
      case 'ArrowLeft':
        pan(-step, 0);
        break;
      case 'ArrowRight':
        pan(step, 0);
        break;
      case 'ArrowUp':
        pan(0, -step);
        break;
      case 'ArrowDown':
        pan(0, step);
        break;
      case '+':
      case '=':
        zoom(-200);
        break;
      case '-':
      case '_':
        zoom(200);
        break;
      case 'q':
      case 'Q':
        orbit(-0.12);
        break;
      case 'e':
      case 'E':
        orbit(0.12);
        break;
      case 'Home':
        resetCamera();
        break;
      default:
        return;
    }
    event.preventDefault();
  }

  function pointerDown(event: PointerEvent): void {
    if ((event.target as Element).closest('[data-map-interactive]')) return;
    if (!canNavigate) {
      pick(event);
      return;
    }
    if (event.button !== 0 && event.button !== 2) return;
    if (status.state !== 'ready' || activePointers.has(event.pointerId)) return;
    // A second touch joins a Galaxy gesture. Other additional pointers never
    // replace an active drag or change the System map's existing controls.
    if (
      activePointers.size > 0 &&
      (!canGalaxyNavigate ||
        event.pointerType !== 'touch' ||
        activePointers.size >= 2 ||
        [...activePointers.values()].some(
          (pointer) => pointer.pointerType !== 'touch',
        ))
    )
      return;
    // Keep keyboard focus on the semantic host; the browser's default pointer
    // focus would otherwise land on the hidden canvas and scroll the page.
    event.preventDefault();
    host.focus({ preventScroll: true });
    clearHover();
    activePointers.set(event.pointerId, {
      id: event.pointerId,
      pointerType: event.pointerType,
      x: event.clientX,
      y: event.clientY,
      startX: event.clientX,
      startY: event.clientY,
      moved: false,
      mode:
        canSystemNavigate || event.shiftKey || event.button === 2
          ? 'orbit'
          : event.altKey
            ? 'elevate'
            : 'pan',
    });
    if (activePointers.size === 2) {
      // Neither finger may become a click after participating in a gesture.
      for (const pointer of activePointers.values()) pointer.moved = true;
    }
    try {
      host.setPointerCapture?.(event.pointerId);
    } catch (error) {
      // Synthetic PointerEvents have no browser-owned active pointer to
      // capture. The window listeners still complete and cancel that gesture.
      if (!(error instanceof DOMException) || error.name !== 'NotFoundError')
        throw error;
    }
    if (!removeWindowDragListeners) installWindowDragListeners();
  }

  function installWindowDragListeners(): void {
    removeWindowDragListeners?.();
    const move = (event: PointerEvent): void => windowPointerMove(event);
    const up = (event: PointerEvent): void => windowPointerUp(event);
    const cancel = (event: PointerEvent): void => windowPointerCancel(event);
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', cancel);
    removeWindowDragListeners = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', cancel);
      removeWindowDragListeners = null;
    };
  }

  function pointerMove(event: PointerEvent): void {
    if (
      activePointers.size > 0 ||
      (event.target as Element).closest('[data-map-interactive]')
    )
      return;
    hover(event);
  }

  function canvasPoint(point: GalaxyCameraPoint): GalaxyCameraPoint {
    const bounds = (
      host.querySelector('canvas') ?? host
    ).getBoundingClientRect();
    return { x: point.x - bounds.left, y: point.y - bounds.top };
  }

  function windowPointerMove(event: PointerEvent): void {
    const drag = activePointers.get(event.pointerId);
    if (!drag) return;
    if (activePointers.size === 2 && canGalaxyNavigate && currentCamera) {
      const [first, second] = [...activePointers.values()] as [
        ActivePointer,
        ActivePointer,
      ];
      const previous = [canvasPoint(first), canvasPoint(second)] as const;
      drag.x = event.clientX;
      drag.y = event.clientY;
      setCamera(
        pinchGalaxyCamera(
          currentCamera,
          previous,
          [canvasPoint(first), canvasPoint(second)],
          viewport(),
          cameraBounds,
        ),
      );
      return;
    }
    const deltaX = event.clientX - drag.x;
    const deltaY = event.clientY - drag.y;
    if (
      Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) <
        4 &&
      !drag.moved
    )
      return;
    drag.moved = true;
    drag.x = event.clientX;
    drag.y = event.clientY;
    if (canSystemNavigate) orbitSystem(-deltaX * 0.006, deltaY * 0.004);
    else if (drag.mode === 'orbit') orbit(-deltaX * 0.006, deltaY * 0.004);
    else if (drag.mode === 'elevate' && currentCamera)
      setCamera(
        elevateGalaxyCameraByPixels(
          currentCamera,
          -deltaY,
          viewport(),
          cameraBounds,
        ),
      );
    else pan(-deltaX, -deltaY);
  }

  function releasePointerCapture(id: number): void {
    if (host.hasPointerCapture?.(id)) host.releasePointerCapture(id);
  }

  function windowPointerUp(event: PointerEvent): void {
    const completed = activePointers.get(event.pointerId);
    if (!completed) return;
    activePointers.delete(event.pointerId);
    releasePointerCapture(event.pointerId);
    if (activePointers.size === 0) removeWindowDragListeners?.();
    if (!completed.moved && (canSystemNavigate || completed.mode === 'pan'))
      pick(event);
  }

  function windowPointerCancel(event?: PointerEvent): void {
    if (event && !activePointers.has(event.pointerId)) return;
    const ids = [...activePointers.keys()];
    activePointers.clear();
    removeWindowDragListeners?.();
    for (const id of ids) releasePointerCapture(id);
    clearHover();
  }

  $effect(() => {
    if (
      status.state !== 'ready' ||
      !runtime ||
      !focusTarget ||
      focusRevision === lastFocusRevision ||
      scene?.revision !== lastLoadedRevision
    ) {
      return;
    }
    const reducedMotion = window.matchMedia(
      '(prefers-reduced-motion: reduce)',
    ).matches;
    if (cameraTransitionActive) {
      pendingCameraMove = {
        type: 'FLY_TO',
        target: focusTarget,
        reducedMotion,
      };
      lastFocusRevision = focusRevision;
      return;
    }
    dispatchPendingFocus();
  });

  function pick(event: PointerEvent): void {
    if (event.button !== 0 || status.state !== 'ready' || !runtime) return;
    const activeCanvas = host.querySelector('canvas');
    if (!activeCanvas) return;
    const bounds = activeCanvas.getBoundingClientRect();
    const point = {
      screenX: event.clientX - bounds.left,
      screenY: event.clientY - bounds.top,
    };
    if (cameraTransitionActive) {
      pendingPickPoint = point;
      return;
    }
    runtime.dispatch({ type: 'PICK', ...point });
  }

  function hover(event: PointerEvent): void {
    if (event.pointerType === 'touch' || status.state !== 'ready' || !runtime) {
      return;
    }
    const activeCanvas = host.querySelector('canvas');
    if (!activeCanvas) return;
    const bounds = activeCanvas.getBoundingClientRect();
    pendingHoverPoint = {
      x: event.clientX - bounds.left,
      y: event.clientY - bounds.top,
    };
    if (hoverFrame !== null) return;
    hoverFrame = window.requestAnimationFrame(() => {
      hoverFrame = null;
      const point = pendingHoverPoint;
      pendingHoverPoint = null;
      if (!point || status.state !== 'ready' || !runtime) return;
      runtime.dispatch({ type: 'HOVER', screenX: point.x, screenY: point.y });
    });
  }

  function clearHover(): void {
    lastHoveredBodyRef = undefined;
    pendingHoverPoint = null;
    if (hoverFrame !== null) {
      window.cancelAnimationFrame(hoverFrame);
      hoverFrame = null;
    }
    if (status.state === 'ready' && runtime) {
      runtime.dispatch({ type: 'CLEAR_HOVER' });
    }
    scheduleHoverClear();
  }

  function keepHover(): void {
    if (hoverClearTimeout !== null) window.clearTimeout(hoverClearTimeout);
    hoverClearTimeout = null;
  }

  function dismissHover(): void {
    keepHover();
    if (!hoveredSystemId64) return;
    focusCardRequested = false;
    if (tooltipHost?.contains(document.activeElement)) {
      restoringHoverFocus = true;
      (hoverOpener?.isConnected ? hoverOpener : host).focus({
        preventScroll: true,
      });
      restoringHoverFocus = false;
    }
    hoveredSystemId64 = undefined;
    onRuntimeEvent?.({
      type: 'TARGET_HOVERED',
      target: lastHoveredRegionId
        ? { kind: 'region', id: lastHoveredRegionId }
        : undefined,
    });
  }

  function scheduleHoverClear(): void {
    keepHover();
    // Allow crossing the short gap between a star/label and its card. Focus
    // within either the trigger or card keeps it open; Tab is never captured.
    hoverClearTimeout = window.setTimeout(() => {
      hoverClearTimeout = null;
      if (tooltipHost?.contains(document.activeElement)) return;
      const focused = document.activeElement as HTMLElement | null;
      if (
        hoveredSystemId64 &&
        focused?.dataset.systemId64 === hoveredSystemId64
      )
        return;
      dismissHover();
    }, 220);
  }

  function showSystem(
    system: GalaxySystemPoint,
    event?: PointerEvent | FocusEvent,
  ): void {
    if (restoringHoverFocus) return;
    keepHover();
    lastHoveredRegionId = undefined;
    hoveredSystemId64 = system.systemId64;
    hoverOpener =
      event && !('clientX' in event)
        ? (event.currentTarget as HTMLElement)
        : null;
    if (event && 'clientX' in event) {
      const bounds = host.getBoundingClientRect();
      hoverPosition = {
        x: event.clientX - bounds.left,
        y: event.clientY - bounds.top,
      };
    } else {
      const projected = currentCamera
        ? projectGalaxyLabel(system.positionLy, currentCamera, viewport())
        : null;
      hoverPosition = { x: projected?.xPx ?? 16, y: projected?.yPx ?? 16 };
    }
    onRuntimeEvent?.({
      type: 'TARGET_HOVERED',
      target: {
        kind: 'system',
        systemId64: system.systemId64,
        name: system.name,
      },
    });
  }

  function systemKey(event: KeyboardEvent, system: GalaxySystemPoint): void {
    if (event.key !== 'ArrowRight') return;
    event.preventDefault();
    event.stopPropagation();
    showSystem(system);
    hoverOpener = event.currentTarget as HTMLElement;
    focusCardRequested = true;
  }

  function selectSystem(system: GalaxySystemPoint): void {
    if (
      tooltipHost?.contains(document.activeElement) ||
      document.activeElement?.classList.contains('galaxy-label--system')
    ) {
      // The flight hides map overlays. Keep keyboard focus on the persistent
      // canvas host before removing a focused card or hiding a label.
      host.focus({ preventScroll: true });
      hoverOpener = null;
      dismissHover();
    }
    if (onSystemSelect) onSystemSelect(system);
    else {
      const target = { kind: 'system', systemId64: system.systemId64 } as const;
      onRuntimeEvent?.({ type: 'TARGET_PICKED', target });
      dispatchCameraMove({
        type: 'FLY_TO',
        target,
        reducedMotion: window.matchMedia('(prefers-reduced-motion: reduce)')
          .matches,
      });
    }
  }

  const cardPosition = $derived.by(() => {
    void resizeRevision;
    const width = host?.clientWidth ?? 640;
    const height = host?.clientHeight ?? 360;
    return {
      x: Math.max(8, Math.min(hoverPosition.x + 14, width - 292)),
      y: Math.max(8, Math.min(hoverPosition.y + 14, height - 240)),
    };
  });

  onMount(() => {
    let mounted = true;
    let activeRuntime: SpatialRuntime | null = null;
    let observer: ResizeObserver | null = null;
    let unsubscribe = (): void => undefined;
    let wheel: ((event: WheelEvent) => void) | null = null;

    const loadBabylonAdapter = async (): Promise<
      typeof import('./babylon/adapter')
    > => {
      let lastError: unknown;
      for (let attempt = 0; attempt < 2; attempt += 1) {
        try {
          return await import('./babylon/adapter');
        } catch (error) {
          lastError = error;
          if (attempt === 0) {
            await new Promise((resolve) => window.setTimeout(resolve, 80));
          }
        }
      }
      throw lastError;
    };

    const startRuntime = async (): Promise<void> => {
      let adapter: typeof import('./babylon/adapter');
      try {
        adapter = await loadBabylonAdapter();
      } catch (error) {
        if (mounted) {
          status = { state: 'failed', failure: 'INITIALIZATION_FAILED' };
          console.error('Failed to load the Babylon spatial adapter', error);
        }
        return;
      }
      if (!mounted) return;

      const nextRuntime = adapter.createBabylonSpatialRuntime(
        canvas,
        (nextStatus) => {
          if (mounted) status = nextStatus;
        },
      );
      activeRuntime = nextRuntime;
      runtime = nextRuntime;
      unsubscribe = nextRuntime.subscribe((event) => {
        if (!mounted) return;
        if (event.type === 'TARGET_PICKED') {
          lastPickedId64 =
            event.target?.kind === 'system'
              ? event.target.systemId64
              : undefined;
          lastPickedRegionId =
            event.target?.kind === 'region' ? event.target.id : undefined;
        } else if (event.type === 'TARGET_HOVERED') {
          lastHoveredRegionId =
            event.target?.kind === 'region' ? event.target.id : undefined;
          lastHoveredBodyRef =
            event.target?.kind === 'body' ? event.target.ref : undefined;
          if (event.target?.kind === 'system') {
            keepHover();
            hoverOpener = null;
            hoveredSystemId64 = event.target.systemId64;
            hoverPosition = { x: event.screenX ?? 16, y: event.screenY ?? 16 };
          } else scheduleHoverClear();
        } else if (event.type === 'SCENE_APPLIED') {
          lastAppliedSceneRevision = event.sceneRevision;
          renderedLayerIds = event.renderedLayers.map((layer) => layer.layerId);
        } else if (event.type === 'CONTRIBUTION_APPLIED') {
          lastAppliedContributionRevision = event.contributionRevision;
          renderedLayerIds = event.renderedLayers.map((layer) => layer.layerId);
        } else if (
          event.type === 'CAMERA_CHANGED' &&
          'focusLy' in event.camera
        ) {
          if (cameraTransitionActive) transitionCamera = event.camera;
          else currentCamera = event.camera;
        } else if (
          event.type === 'CAMERA_CHANGED' &&
          'systemId64' in event.camera
        ) {
          if (cameraTransitionActive) transitionCamera = event.camera;
          else currentSystemCamera = event.camera;
        } else if (event.type === 'TRANSITION_FINISHED') {
          if (event.target?.kind === 'system') {
            lastSettledFocusId64 = event.target.systemId64;
          } else if (event.target?.kind === 'body') {
            lastSettledFocusBodyId = event.target.ref.bodyId;
          }
          if (transitionCamera && 'focusLy' in transitionCamera) {
            currentCamera = transitionCamera;
          } else if (transitionCamera && 'systemId64' in transitionCamera) {
            currentSystemCamera = transitionCamera;
          }
          const settledCamera =
            transitionCamera ??
            (event.target?.kind === 'body'
              ? currentSystemCamera
              : currentCamera);
          setCameraTransitionActive(false, settledCamera);
          transitionCamera = null;
          const queuedMove = pendingCameraMove;
          pendingCameraMove = null;
          const nextScene = pendingScene;
          pendingScene = null;
          if (nextScene) {
            // Finder/refetch updates queued during a flight still carry the
            // parent's pre-flight camera. Its settle callback cannot update
            // that snapshot synchronously: loading it as-is would undo the
            // completed move. Keep the new contributions at the settled view;
            // an intentional change of scene kind or system owns its camera.
            if (
              FINDER_F4_ENABLED &&
              nextScene.kind === 'galaxy' &&
              settledCamera &&
              'focusLy' in settledCamera
            ) {
              applyScene({ ...nextScene, camera: settledCamera });
            } else if (
              FINDER_F4_ENABLED &&
              nextScene.kind === 'system' &&
              settledCamera &&
              'systemId64' in settledCamera &&
              nextScene.systemId64 === settledCamera.systemId64
            ) {
              applyScene({ ...nextScene, camera: settledCamera });
            } else {
              applyScene(nextScene);
            }
          }
          if (queuedMove) {
            dispatchCameraMove(queuedMove);
          }
          if (!cameraTransitionActive) {
            dispatchPendingFocus();
          }
          if (!cameraTransitionActive && pendingPickPoint) {
            const point = pendingPickPoint;
            pendingPickPoint = null;
            runtime?.dispatch({ type: 'PICK', ...point });
          }
        } else if (event.type === 'RECOVERED' && scene) {
          recoverCurrentCamera = FINDER_F4_ENABLED;
          lastLoadedRevision = -1;
        }
        onRuntimeEvent?.(event);
      });

      const resize = (width: number, height: number): void => {
        if (!activeRuntime) return;
        const viewport = {
          width: Math.max(1, Math.round(width)),
          height: Math.max(1, Math.round(height)),
          dpr: Math.min(2, Math.max(1, window.devicePixelRatio || 1)),
        };
        activeRuntime.dispatch({ type: 'RESIZE', ...viewport });
        resizeRevision += 1;
        host
          .querySelector('canvas')
          ?.setAttribute('data-resize-revision', String(resizeRevision));
      };

      observer = new ResizeObserver(([entry]) => {
        if (!entry) return;
        resize(entry.contentRect.width, entry.contentRect.height);
      });
      observer.observe(host);
      wheel = (event: WheelEvent): void => {
        if (!canNavigate) return;
        event.preventDefault();
        const pixels =
          event.deltaY *
          (event.deltaMode === 1
            ? 16
            : event.deltaMode === 2
              ? host.clientHeight
              : 1);
        const boundedPixels = Math.max(-400, Math.min(400, pixels));
        if (canSystemNavigate) zoomSystem(boundedPixels);
        else if (currentCamera)
          setCamera(
            zoomGalaxyCameraTowards(
              currentCamera,
              boundedPixels,
              canvasPoint({ x: event.clientX, y: event.clientY }),
              viewport(),
              cameraBounds,
            ),
          );
      };
      host.addEventListener('wheel', wheel, { passive: false });
      resize(host.clientWidth, host.clientHeight);
      void nextRuntime.start();
    };

    void startRuntime();

    return () => {
      mounted = false;
      clearHover();
      keepHover();
      windowPointerCancel();
      if (wheel) host.removeEventListener('wheel', wheel);
      observer?.disconnect();
      unsubscribe();
      activeRuntime?.dispose();
      runtime = null;
      lastLoadedRevision = -1;
      lastFocusRevision = -1;
      lastCameraRequestRevision = -1;
      lastContributionPatchRevision = -1;
      lastPickedRegionId = undefined;
      lastHoveredRegionId = undefined;
      lastHoveredBodyRef = undefined;
      lastSettledFocusId64 = undefined;
      lastSettledFocusBodyId = undefined;
      lastAppliedSceneRevision = undefined;
      lastAppliedContributionRevision = undefined;
      cameraTransitionActive = false;
      transitionCamera = null;
      pendingCameraMove = null;
      pendingScene = null;
      pendingPickPoint = null;
      renderedLayerIds = [];
    };
  });
</script>

{#if canGalaxyNavigate}
  <div class="camera-toolbar" role="group" aria-label="Galaxy camera controls">
    <button type="button" aria-label="Zoom in" onclick={() => zoom(-240)}
      >+</button
    >
    <button type="button" aria-label="Zoom out" onclick={() => zoom(240)}
      >−</button
    >
    <button type="button" aria-label="Rotate left" onclick={() => orbit(-0.25)}
      >↶</button
    >
    <button type="button" aria-label="Rotate right" onclick={() => orbit(0.25)}
      >↷</button
    >
    <button type="button" aria-label="Move up" onclick={() => elevate(1)}
      >Up</button
    >
    <button type="button" aria-label="Move down" onclick={() => elevate(-1)}
      >Down</button
    >
    <button
      type="button"
      onclick={() =>
        currentCamera && setCamera(topDownGalaxyCamera(currentCamera), true)}
      >Top down</button
    >
    <button
      type="button"
      onclick={() =>
        currentCamera &&
        setCamera(
          {
            ...currentCamera,
            pitchRad: 0.55,
            revision: currentCamera.revision + 1,
          },
          true,
        )}>Tilted</button
    >
    <button type="button" onclick={resetCamera}>Reset view</button>
    <span
      class="camera-distance"
      data-camera-distance={currentCamera?.distanceLy}
      data-grid-step-ly={currentGrid?.minorStepLy}
    >
      <span
        >Range {Math.round(currentCamera?.distanceLy ?? 0).toLocaleString()} ly</span
      >
      <span>Grid {lightYearInterval(currentGrid?.minorStepLy)}</span>
      <span role="group" aria-label="Focus coordinates"
        >X {Math.round(currentCamera?.focusLy.x ?? 0).toLocaleString()} / Y {Math.round(
          currentCamera?.focusLy.y ?? 0,
        ).toLocaleString()} / Z {Math.round(
          currentCamera?.focusLy.z ?? 0,
        ).toLocaleString()} LY</span
      >
    </span>
  </div>
  <p class="camera-help">
    Drag to pan · Shift-drag to orbit · Alt/Option-drag to move up/down · Scroll
    or pinch to zoom · Two-finger drag to pan · Arrow keys to pan · Q/E to
    rotate
  </p>
{:else if canSystemNavigate}
  <div class="camera-toolbar" role="group" aria-label="System camera controls">
    <button type="button" aria-label="Zoom in" onclick={() => zoomSystem(-220)}
      >+</button
    >
    <button type="button" aria-label="Zoom out" onclick={() => zoomSystem(220)}
      >−</button
    >
    <button
      type="button"
      aria-label="Rotate left"
      onclick={() => orbitSystem(-0.25)}>↶</button
    >
    <button
      type="button"
      aria-label="Rotate right"
      onclick={() => orbitSystem(0.25)}>↷</button
    >
    <button type="button" onclick={resetCamera}>Reset view</button>
    <span
      class="camera-distance"
      data-system-camera-distance={currentSystemCamera?.semanticDistance}
      >Semantic range {Math.round(
        currentSystemCamera?.semanticDistance ?? 0,
      )}</span
    >
  </div>
  <p class="camera-help">
    Drag to orbit · Scroll to zoom · Arrow keys rotate · Click a body for facts
  </p>
{/if}

<div class="map-systems-surface">
  {#if canGalaxyNavigate}
    <p id={systemKeyboardHelpId} class="system-keyboard-help">
      Press Right arrow for system card actions. Enter selects and focuses the
      system. Escape closes the card.
    </p>
  {/if}
  <!-- The Galaxy canvas implements keyboard navigation and has parallel native controls. -->
  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <div
    class="spatial-canvas"
    bind:this={host}
    role={canNavigate ? 'application' : 'presentation'}
    aria-label={canGalaxyNavigate
      ? 'Interactive Galaxy map. Arrow keys pan, plus and minus zoom, Q and E rotate, Home resets.'
      : canSystemNavigate
        ? 'Interactive 3D system map. Arrow keys rotate, plus and minus zoom, Home resets, and bodies can be selected.'
        : undefined}
    tabindex={canNavigate ? 0 : -1}
    onkeydown={cameraKey}
    onpointerdown={pointerDown}
    onpointermove={pointerMove}
    onlostpointercapture={windowPointerCancel}
    oncontextmenu={(event) => {
      if (canNavigate) event.preventDefault();
    }}
    onpointerleave={clearHover}
    data-scene-target-count={sceneTargetCount}
    data-system-target-count={systemTargetCount}
    data-camera-transition-active={cameraTransitionActive}
    data-last-picked-id64={lastPickedId64}
    data-last-picked-region-id={lastPickedRegionId}
    data-last-hovered-region-id={lastHoveredRegionId}
    data-last-hovered-system-id={hoveredSystemId64}
    data-last-settled-focus-id64={lastSettledFocusId64}
    data-last-settled-focus-body-id={lastSettledFocusBodyId}
    data-applied-scene-revision={lastAppliedSceneRevision}
    data-applied-contribution-revision={lastAppliedContributionRevision}
    data-camera-revision={canGalaxyNavigate
      ? currentCamera?.revision
      : currentSystemCamera?.revision}
    data-camera-bearing={canGalaxyNavigate
      ? currentCamera?.bearingRad
      : currentSystemCamera?.bearingRad}
    data-camera-pitch={canGalaxyNavigate
      ? currentCamera?.pitchRad
      : currentSystemCamera?.pitchRad}
    data-rendered-layer-ids={renderedLayerIds.join(',')}
  >
    <canvas
      bind:this={canvas}
      data-spatial-canvas
      data-resize-revision={resizeRevision}
      tabindex="-1"
      aria-hidden="true"
    ></canvas>
    {#if hoveredBody}
      <div
        class="system-body-hover"
        data-hovered-body-id={hoveredBody.ref.bodyId}
      >
        <strong>{hoveredBody.name ?? `Body ${hoveredBody.ref.bodyId}`}</strong>
        <span
          >{hoveredBody.bodyClass?.value ??
            hoveredBody.class?.value ??
            'Unknown body type'}</span
        >
        {#if hoveredBody.bodyClass?.provenance?.some((entry: Provenance) => entry.source === 'ratings-v4-derived')}
          <small>Source: Ratings V4 derived catalogue</small>
        {/if}
      </div>
    {/if}
    <svg
      class="galaxy-label-leaders"
      aria-hidden="true"
      data-atlas-region-leader-count={atlasRegionLabels.length}
    >
      {#each atlasRegionLabels as label (label.key)}
        <polyline
          class:is-selected={label.selected}
          class:is-hovered={label.hovered}
          points={`${label.anchorXPx},${label.anchorYPx} ${label.leaderEndXPx},${label.yPx}`}
        ></polyline>
        <circle
          class:is-selected={label.selected}
          class:is-hovered={label.hovered}
          cx={label.anchorXPx}
          cy={label.anchorYPx}
          r={label.selected || label.hovered ? 2.5 : 1.35}
        ></circle>
      {/each}
    </svg>
    <div
      class="galaxy-label-layer"
      class:labels-moving={labelsMoving}
      data-visible-label-count={visibleGalaxyLabels.length}
    >
      {#each renderedGalaxyLabels as label (label.key)}
        {#if label.kind === 'system' && label.point}
          <button
            type="button"
            class="galaxy-label galaxy-label--system"
            class:is-selected={label.selected}
            class:is-hovered={label.hovered}
            data-map-interactive
            data-system-id64={label.point.systemId64}
            data-map-label-kind={label.kind}
            data-map-label-key={label.key}
            data-map-label-selected={label.selected || undefined}
            data-map-label-anchor-x={label.anchorXPx}
            data-map-label-anchor-y={label.anchorYPx}
            aria-label={`Select ${label.text}`}
            aria-describedby={`${systemKeyboardHelpId}${hoveredSystemId64 === label.point.systemId64 ? ` ${tooltipId}` : ''}`}
            aria-keyshortcuts="ArrowRight"
            onkeydown={(event) => systemKey(event, label.point!)}
            style:left={`${label.xPx}px`}
            style:top={`${label.yPx}px`}
            onpointerenter={(event) => showSystem(label.point!, event)}
            onpointerleave={scheduleHoverClear}
            onfocus={(event) => showSystem(label.point!, event)}
            onblur={scheduleHoverClear}
            onclick={() => selectSystem(label.point!)}
          >
            <span class="galaxy-label__beacon" aria-hidden="true"></span>
            <span class="galaxy-label__name">{label.text}</span>
          </button>
        {:else}
          <span
            aria-hidden="true"
            class="galaxy-label galaxy-label--region"
            class:galaxy-label--atlas={label.placement !== 'map'}
            class:galaxy-label--atlas-left={label.placement === 'atlas-left'}
            class:galaxy-label--atlas-right={label.placement === 'atlas-right'}
            class:is-selected={label.selected}
            class:is-hovered={label.hovered}
            class:is-current={label.current}
            data-map-label-kind={label.kind}
            data-map-label-key={label.key}
            data-map-label-selected={label.selected || undefined}
            data-map-label-anchor-x={label.anchorXPx}
            data-map-label-anchor-y={label.anchorYPx}
            style:left={`${label.xPx}px`}
            style:top={`${label.yPx}px`}>{label.text}</span
          >
        {/if}
      {/each}
    </div>
  </div>
  {#if canGalaxyNavigate}
    <details class="nearby-systems" bind:open={nearbyOpen}>
      <summary>Nearby systems ({nearbySystems.length})</summary>
      {#if nearbyOpen}
        {#if nearbySystems.length}
          <ul aria-label="Nearby systems">
            {#each nearbySystems as candidate (candidate.key)}
              <li>
                <button
                  type="button"
                  data-system-id64={candidate.point!.systemId64}
                  aria-describedby={`${systemKeyboardHelpId}${hoveredSystemId64 === candidate.point!.systemId64 ? ` ${tooltipId}` : ''}`}
                  aria-keyshortcuts="ArrowRight"
                  onkeydown={(event) => systemKey(event, candidate.point!)}
                  onfocus={(event) => showSystem(candidate.point!, event)}
                  onblur={scheduleHoverClear}
                  onclick={() => selectSystem(candidate.point!)}
                  >{candidate.text}</button
                >
              </li>
            {/each}
          </ul>
        {:else}
          <p>Zoom in or search to find nearby systems.</p>
        {/if}
      {/if}
    </details>
  {/if}
  {#if hoveredSystem && !labelsMoving}
    <div
      class="system-hover-position"
      bind:this={tooltipHost}
      role="presentation"
      onpointerenter={keepHover}
      onpointerleave={scheduleHoverClear}
      onfocusin={keepHover}
      onfocusout={scheduleHoverClear}
      style:left={`${cardPosition.x}px`}
      style:top={`${cardPosition.y}px`}
    >
      <GalaxySystemHoverCard
        id={tooltipId}
        system={hoveredSystem}
        anchor={anchorPoint}
        onSelect={selectSystem}
        inspectHref={systemInspectHref?.(hoveredSystem) ??
          resolve(
            `/inspect?system=${encodeURIComponent(hoveredSystem.systemId64)}`,
          )}
        onInspect={onSystemInspect}
        onDismiss={dismissHover}
      />
    </div>
  {/if}
</div>
{#if scene?.kind === 'system'}
  <SystemBodyLegend bodies={scene.bodies} />
{/if}
<p
  class="renderer-status"
  role="status"
  aria-live="polite"
  data-renderer-state={status.state}
  data-renderer-backend={statusBackend}
>
  {statusLabel}
</p>

<style>
  .system-keyboard-help {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
  .galaxy-label__name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .map-systems-surface {
    position: relative;
  }
  .system-hover-position {
    position: absolute;
    z-index: 5;
    max-width: calc(100% - 16px);
  }
  .nearby-systems {
    margin-top: 0.75rem;
    color: #dbedf7;
  }
  .nearby-systems summary {
    cursor: pointer;
    padding: 0.4rem 0;
  }
  .nearby-systems ul {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    padding: 0;
    list-style: none;
  }
  .nearby-systems button {
    border: 1px solid #344c61;
    border-radius: 0.4rem;
    background: #101e2c;
    color: #dbedf7;
    padding: 0.4rem 0.7rem;
    cursor: pointer;
  }
  .nearby-systems button:focus-visible,
  .nearby-systems summary:focus-visible,
  .galaxy-label--system:focus-visible {
    outline: 2px solid #77d5ee;
    outline-offset: 2px;
  }
  .labels-moving {
    visibility: hidden;
  }

  .system-body-hover {
    position: absolute;
    top: 0.75rem;
    right: 0.75rem;
    display: grid;
    gap: 0.25rem;
    max-width: min(20rem, calc(100% - 1.5rem));
    padding: 0.6rem 0.8rem;
    border: 1px solid #344c61;
    border-radius: 0.4rem;
    background: #101e2cee;
    color: #dbedf7;
    font-size: 0.8rem;
    pointer-events: none;
  }
  .system-body-hover span,
  .system-body-hover small {
    color: #b3c5d2;
  }
  .spatial-canvas {
    position: relative;
    width: 100%;
    height: clamp(32rem, 76vh, 68rem);
    overflow: hidden;
    border: 1px solid #344253;
    background: #040508;
    touch-action: none;
    cursor: grab;
    border-radius: 0.65rem;
  }

  .spatial-canvas:active {
    cursor: grabbing;
  }
  .spatial-canvas:focus-visible {
    outline: 2px solid #77d5ee;
    outline-offset: 3px;
  }
  .camera-toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.4rem;
  }
  .camera-toolbar button {
    border: 1px solid #344c61;
    border-radius: 0.4rem;
    background: #101e2c;
    padding: 0.45rem 0.75rem;
    color: #dbedf7;
    cursor: pointer;
  }
  .camera-toolbar button:hover {
    background: #1c3547;
    border-color: #73c2de;
  }
  .camera-toolbar button:focus-visible {
    outline: 2px solid #77d5ee;
    outline-offset: 2px;
  }
  .camera-distance {
    margin-left: auto;
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 0.25rem 0.7rem;
    color: #b2d9e6;
    font-variant-numeric: tabular-nums;
    font-size: 0.8rem;
  }
  .camera-distance span:last-child {
    color: #7797a7;
  }
  .camera-help {
    color: #95a9ba;
    font-size: 0.75rem;
    margin: 0.6rem 0;
  }

  canvas {
    display: block;
    width: 100%;
    height: 100%;
    touch-action: none;
  }

  .galaxy-label-layer {
    position: absolute;
    z-index: 2;
    inset: 0;
    overflow: hidden;
    pointer-events: none;
  }
  .galaxy-label-leaders {
    position: absolute;
    z-index: 1;
    inset: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    pointer-events: none;
  }
  .galaxy-label-leaders polyline {
    fill: none;
    stroke: rgba(64, 163, 208, 0.2);
    stroke-width: 0.75;
    vector-effect: non-scaling-stroke;
  }
  .galaxy-label-leaders circle {
    fill: rgba(89, 194, 231, 0.62);
  }
  .galaxy-label-leaders .is-hovered {
    stroke: rgba(89, 218, 255, 0.78);
    fill: rgba(118, 229, 255, 0.96);
  }
  .galaxy-label-leaders .is-selected {
    stroke: rgba(255, 151, 61, 0.66);
    fill: rgba(255, 151, 61, 0.92);
  }
  .galaxy-label {
    position: absolute;
    display: inline-flex;
    align-items: center;
    max-width: 14rem;
    transform: translate(-50%, -50%);
    transform-origin: center;
    text-align: center;
    text-wrap: balance;
    line-height: 1.18;
    will-change: left, top;
    transition:
      left 90ms ease-out,
      top 90ms ease-out;
  }
  .galaxy-label--region {
    justify-content: center;
    color: rgba(175, 212, 232, 0.8);
    font-size: 0.63rem;
    font-weight: 620;
    letter-spacing: 0.055em;
    text-transform: uppercase;
    text-shadow:
      0 1px 2px #000,
      0 0 6px #000,
      0 0 14px rgba(21, 101, 153, 0.26);
  }
  .galaxy-label--region.is-hovered {
    color: #c9f7ff;
    font-weight: 720;
    text-shadow:
      0 1px 3px #000,
      0 0 8px #000,
      0 0 17px rgba(74, 211, 255, 0.52);
  }
  .galaxy-label--region.is-current,
  .galaxy-label--region.is-selected {
    color: #f8d5a6;
    font-weight: 720;
    text-shadow:
      0 1px 3px #000,
      0 0 8px #000,
      0 0 15px rgba(255, 135, 46, 0.38);
  }
  .galaxy-label--region.galaxy-label--atlas {
    width: min(13.8rem, 21vw);
    max-width: 13.8rem;
    color: rgba(166, 207, 228, 0.78);
    font-size: clamp(0.5rem, 1.1vh, 0.61rem);
    line-height: 1;
    white-space: nowrap;
    text-wrap: nowrap;
  }
  /* The atlas rule follows the generic state rules in source order, so repeat
     the interactive states with the atlas qualifier. Hover/selection must be
     conspicuous without removing or dimming any of the other 41 names. */
  .galaxy-label--region.galaxy-label--atlas.is-hovered {
    color: #d8fbff;
    font-weight: 760;
    text-shadow:
      0 1px 3px #000,
      0 0 9px #000,
      0 0 19px rgba(66, 218, 255, 0.82);
  }
  .galaxy-label--region.galaxy-label--atlas.is-current,
  .galaxy-label--region.galaxy-label--atlas.is-selected {
    color: #ffe0b8;
    font-weight: 760;
    text-shadow:
      0 1px 3px #000,
      0 0 9px #000,
      0 0 18px rgba(255, 135, 46, 0.68);
  }
  .galaxy-label--atlas-left {
    justify-content: flex-end;
    text-align: right;
  }
  .galaxy-label--atlas-right {
    justify-content: flex-start;
    text-align: left;
  }
  .galaxy-label--system {
    pointer-events: auto;
    cursor: pointer;
    font-family: inherit;
    gap: 0.38rem;
    padding: 0.28rem 0.52rem 0.3rem;
    border: 1px solid rgba(87, 190, 226, 0.34);
    border-radius: 0.4rem;
    color: #dff7ff;
    background: linear-gradient(
      120deg,
      rgba(7, 20, 31, 0.94),
      rgba(8, 15, 25, 0.82)
    );
    box-shadow:
      0 5px 18px rgba(0, 0, 0, 0.42),
      inset 0 1px rgba(255, 255, 255, 0.04);
    font:
      650 0.68rem ui-monospace,
      SFMono-Regular,
      Consolas,
      monospace;
    letter-spacing: 0.025em;
    white-space: nowrap;
  }
  .galaxy-label--system.is-selected {
    border-color: rgba(255, 170, 88, 0.8);
    color: #fff4e6;
    background: linear-gradient(
      120deg,
      rgba(66, 30, 10, 0.94),
      rgba(18, 19, 25, 0.9)
    );
    box-shadow:
      0 5px 20px rgba(0, 0, 0, 0.5),
      0 0 18px rgba(255, 121, 31, 0.18),
      inset 0 1px rgba(255, 222, 190, 0.08);
  }
  .galaxy-label__beacon {
    width: 0.35rem;
    height: 0.35rem;
    flex: 0 0 auto;
    border-radius: 50%;
    background: #7de5ff;
    box-shadow: 0 0 8px rgba(66, 214, 255, 0.86);
  }
  .is-selected .galaxy-label__beacon {
    background: #ff9d45;
    box-shadow: 0 0 9px rgba(255, 126, 37, 0.92);
  }

  .renderer-status {
    min-height: 1.5rem;
    margin: 0.75rem 0 0;
    color: #bbc5d0;
  }
</style>
