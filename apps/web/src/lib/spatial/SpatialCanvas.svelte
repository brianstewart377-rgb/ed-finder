<script lang="ts">
  import { onMount } from 'svelte';

  import { createBabylonSpatialRuntime } from './babylon/adapter';
  import type {
    RuntimeEvent,
    SpatialRuntime,
    SpatialRuntimeStatus,
    SpatialSceneContract,
    SpatialTarget,
  } from './contracts';

  let {
    scene,
    focusTarget = null,
    focusRevision = 0,
    onRuntimeEvent,
  } = $props<{
    scene?: SpatialSceneContract;
    focusTarget?: SpatialTarget | null;
    focusRevision?: number;
    onRuntimeEvent?: (event: RuntimeEvent) => void;
  }>();

  let canvas: HTMLCanvasElement;
  let host: HTMLDivElement;
  let runtime: SpatialRuntime | null = null;
  let status = $state<SpatialRuntimeStatus>({ state: 'created' });
  let resizeRevision = $state(0);
  let lastLoadedRevision = $state(-1);
  let lastFocusRevision = -1;
  let lastPickedId64 = $state<string | undefined>();

  function targetCount(value: SpatialSceneContract | undefined): number {
    return (
      value?.contributions.reduce(
        (total, contribution) =>
          total +
          contribution.layers.reduce(
            (layerTotal, layer) => layerTotal + layer.targetCount,
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
      lastLoadedRevision = scene.revision;
    }
  });

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
    if (
      runtime.dispatch({ type: 'FLY_TO', target: focusTarget, reducedMotion })
        .status === 'executed'
    ) {
      lastFocusRevision = focusRevision;
    }
  });

  function pick(event: PointerEvent): void {
    if (event.button !== 0 || status.state !== 'ready' || !runtime) return;
    const activeCanvas = host.querySelector('canvas');
    if (!activeCanvas) return;
    const bounds = activeCanvas.getBoundingClientRect();
    runtime.dispatch({
      type: 'PICK',
      screenX: event.clientX - bounds.left,
      screenY: event.clientY - bounds.top,
    });
  }

  onMount(() => {
    let mounted = true;
    runtime = createBabylonSpatialRuntime(canvas, (nextStatus) => {
      if (mounted) status = nextStatus;
    });
    const activeRuntime = runtime;
    const unsubscribe = activeRuntime.subscribe((event) => {
      if (!mounted) return;
      if (event.type === 'TARGET_PICKED') {
        lastPickedId64 =
          event.target?.kind === 'system' ? event.target.systemId64 : undefined;
      } else if (event.type === 'RECOVERED' && scene) {
        lastLoadedRevision = -1;
      }
      onRuntimeEvent?.(event);
    });

    const resize = (width: number, height: number): void => {
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

    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      resize(entry.contentRect.width, entry.contentRect.height);
    });
    observer.observe(host);
    resize(host.clientWidth, host.clientHeight);
    void activeRuntime.start();

    return () => {
      mounted = false;
      observer.disconnect();
      unsubscribe();
      activeRuntime.dispose();
      runtime = null;
      lastLoadedRevision = -1;
      lastFocusRevision = -1;
    };
  });
</script>

<div
  class="spatial-canvas"
  bind:this={host}
  role="presentation"
  onpointerdown={pick}
  data-scene-target-count={sceneTargetCount}
  data-last-picked-id64={lastPickedId64}
>
  <canvas
    bind:this={canvas}
    data-spatial-canvas
    data-resize-revision={resizeRevision}
    aria-hidden="true"
  ></canvas>
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
    width: 100%;
    height: clamp(20rem, 58vh, 34rem);
    overflow: hidden;
    border: 1px solid #344253;
    background: #040508;
  }

  canvas {
    display: block;
    width: 100%;
    height: 100%;
  }

  .renderer-status {
    min-height: 1.5rem;
    margin: 0.75rem 0 0;
    color: #bbc5d0;
  }
</style>
