<script lang="ts">
  import { onMount } from 'svelte';

  import type {
    CameraState,
    RuntimeEvent,
    SpatialRuntime,
    SpatialRuntimeStatus,
    SpatialContribution,
    SpatialSceneContract,
    SpatialTarget,
    SystemCameraState,
  } from './contracts';
  import {
    orbitGalaxyCamera,
    panGalaxyCamera,
    topDownGalaxyCamera,
    zoomGalaxyCamera,
  } from './galaxy-camera';
  import { galaxyReferenceGrid } from './galaxy-grid';
  import { galaxyLabelCandidates, layoutGalaxyLabels } from './galaxy-labels';

  let {
    scene,
    focusTarget = null,
    focusRevision = 0,
    cameraRequest = null,
    cameraRequestRevision = 0,
    contributionPatch = null,
    contributionPatchRevision = 0,
    onRuntimeEvent,
  } = $props<{
    scene?: SpatialSceneContract;
    focusTarget?: SpatialTarget | null;
    focusRevision?: number;
    cameraRequest?: CameraState | null;
    cameraRequestRevision?: number;
    contributionPatch?: SpatialContribution | null;
    contributionPatchRevision?: number;
    onRuntimeEvent?: (event: RuntimeEvent) => void;
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
  let drag: {
    id: number;
    x: number;
    y: number;
    startX: number;
    startY: number;
    moved: boolean;
    orbit: boolean;
  } | null = null;
  let lastPickedId64 = $state<string | undefined>();
  let lastPickedRegionId = $state<string | undefined>();
  let lastHoveredRegionId = $state<string | undefined>();
  let lastAppliedSceneRevision = $state<number | undefined>();
  let lastAppliedContributionRevision = $state<number | undefined>();
  let renderedLayerIds = $state<string[]>([]);
  let pendingHoverPoint: { x: number; y: number } | null = null;
  let cameraTransitionActive = false;
  let pendingPickPoint: { screenX: number; screenY: number } | null = null;
  let hoverFrame: number | null = null;

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
  const visibleGalaxyLabels = $derived.by(() => {
    // Resize revision invalidates the CSS-pixel projection even when the
    // accepted scene and camera are unchanged.
    if (
      !canGalaxyNavigate ||
      scene?.kind !== 'galaxy' ||
      !currentCamera ||
      !host
    )
      return [];
    return layoutGalaxyLabels(
      galaxyLabelCandidates(scene, lastHoveredRegionId),
      currentCamera,
      {
        width: Math.max(1, host.clientWidth + resizeRevision * 0),
        height: Math.max(1, host.clientHeight),
      },
    );
  });
  const atlasRegionLabels = $derived(
    visibleGalaxyLabels.filter(
      (label) => label.kind === 'region' && label.placement !== 'map',
    ),
  );
  const currentGrid = $derived.by(() => {
    if (!canGalaxyNavigate || !currentCamera || !host) return null;
    return galaxyReferenceGrid(currentCamera, {
      width: Math.max(1, host.clientWidth + resizeRevision * 0),
      height: Math.max(1, host.clientHeight),
    });
  });

  function lightYearInterval(value: number | undefined): string {
    if (!value) return '—';
    return `${value.toLocaleString(undefined, {
      maximumFractionDigits: value < 1 ? 2 : 0,
    })} ly`;
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
    if (runtime.dispatch({ type: 'LOAD_SCENE', scene }).status === 'executed') {
      if (!homeCamera && scene.kind === 'galaxy') homeCamera = scene.camera;
      if (scene.kind === 'system') {
        homeSystemCamera = scene.camera;
        currentSystemCamera = scene.camera;
      }
      lastLoadedRevision = scene.revision;
    }
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

  function setCamera(camera: CameraState, animate = false): void {
    if (!runtime || status.state !== 'ready') return;
    const reducedMotion = window.matchMedia(
      '(prefers-reduced-motion: reduce)',
    ).matches;
    const result = runtime.dispatch({
      type: 'SET_CAMERA',
      camera,
      ...(animate ? { transition: { durationMs: 650, reducedMotion } } : {}),
    });
    if (result.status === 'executed' && (!animate || reducedMotion))
      currentCamera = camera;
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
      setCamera(panGalaxyCamera(currentCamera, x, y, viewport()));
  }

  function zoom(delta: number): void {
    if (currentCamera) setCamera(zoomGalaxyCamera(currentCamera, delta));
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
    if (!canNavigate) {
      pick(event);
      return;
    }
    if (event.button !== 0 && event.button !== 2) return;
    if (drag || status.state !== 'ready') return;
    // Keep keyboard focus on the semantic host; the browser's default pointer
    // focus would otherwise land on the hidden canvas and scroll the page.
    event.preventDefault();
    host.focus({ preventScroll: true });
    host.setPointerCapture?.(event.pointerId);
    clearHover();
    drag = {
      id: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      startX: event.clientX,
      startY: event.clientY,
      moved: false,
      orbit: canSystemNavigate || event.shiftKey || event.button === 2,
    };
  }

  function pointerMove(event: PointerEvent): void {
    if (!drag || drag.id !== event.pointerId) {
      hover(event);
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
    else if (drag.orbit) orbit(-deltaX * 0.006, deltaY * 0.004);
    else pan(-deltaX, -deltaY);
  }

  function pointerUp(event: PointerEvent): void {
    if (!drag || drag.id !== event.pointerId) return;
    const completed = drag;
    drag = null;
    if (host.hasPointerCapture?.(event.pointerId))
      host.releasePointerCapture(event.pointerId);
    if (!completed.moved && (canSystemNavigate || !completed.orbit))
      pick(event);
  }

  function cancelDrag(): void {
    drag = null;
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
    const result = runtime.dispatch({
      type: 'FLY_TO',
      target: focusTarget,
      reducedMotion,
    });
    if (result.status === 'executed') {
      lastFocusRevision = focusRevision;
      cameraTransitionActive = !reducedMotion;
    }
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
    pendingHoverPoint = null;
    if (hoverFrame !== null) {
      window.cancelAnimationFrame(hoverFrame);
      hoverFrame = null;
    }
    if (status.state === 'ready' && runtime) {
      runtime.dispatch({ type: 'CLEAR_HOVER' });
    }
  }

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
          currentCamera = event.camera;
        } else if (
          event.type === 'CAMERA_CHANGED' &&
          'systemId64' in event.camera
        ) {
          currentSystemCamera = event.camera;
        } else if (event.type === 'TRANSITION_FINISHED') {
          cameraTransitionActive = false;
          if (pendingPickPoint) {
            const point = pendingPickPoint;
            pendingPickPoint = null;
            runtime?.dispatch({ type: 'PICK', ...point });
          }
        } else if (event.type === 'RECOVERED' && scene) {
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
        else if (currentCamera) zoom(boundedPixels);
      };
      host.addEventListener('wheel', wheel, { passive: false });
      resize(host.clientWidth, host.clientHeight);
      void nextRuntime.start();
    };

    void startRuntime();

    return () => {
      mounted = false;
      clearHover();
      drag = null;
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
      lastAppliedSceneRevision = undefined;
      lastAppliedContributionRevision = undefined;
      cameraTransitionActive = false;
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
    </span>
  </div>
  <p class="camera-help">
    Drag to pan · Shift-drag to orbit · Scroll to zoom · Arrow keys to pan · Q/E
    to rotate
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
  onpointerup={pointerUp}
  onpointercancel={cancelDrag}
  onlostpointercapture={cancelDrag}
  oncontextmenu={(event) => {
    if (canNavigate) event.preventDefault();
  }}
  onpointerleave={clearHover}
  data-scene-target-count={sceneTargetCount}
  data-system-target-count={systemTargetCount}
  data-last-picked-id64={lastPickedId64}
  data-last-picked-region-id={lastPickedRegionId}
  data-last-hovered-region-id={lastHoveredRegionId}
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
    aria-hidden="true"
    data-visible-label-count={visibleGalaxyLabels.length}
  >
    {#each visibleGalaxyLabels as label (label.key)}
      <span
        class:galaxy-label--system={label.kind === 'system'}
        class:galaxy-label--region={label.kind === 'region'}
        class:galaxy-label--atlas={label.placement !== 'map'}
        class:galaxy-label--atlas-left={label.placement === 'atlas-left'}
        class:galaxy-label--atlas-right={label.placement === 'atlas-right'}
        class:is-selected={label.selected}
        class:is-hovered={label.hovered}
        class:is-current={label.current}
        class="galaxy-label"
        data-map-label-kind={label.kind}
        data-map-label-key={label.key}
        data-map-label-selected={label.selected || undefined}
        style:left={`${label.xPx}px`}
        style:top={`${label.yPx}px`}
      >
        {#if label.kind === 'system'}<span class="galaxy-label__beacon"
          ></span>{/if}
        <span>{label.text}</span>
      </span>
    {/each}
  </div>
</div>
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
  .spatial-canvas {
    position: relative;
    width: 100%;
    height: clamp(20rem, 58vh, 34rem);
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
