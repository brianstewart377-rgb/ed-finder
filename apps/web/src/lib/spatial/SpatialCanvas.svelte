<script lang="ts">
  import { onMount } from 'svelte';

  import { createBabylonSpatialRuntime } from './babylon/adapter';
  import type { SpatialRuntimeStatus } from './contracts';

  let canvas: HTMLCanvasElement;
  let host: HTMLDivElement;
  let status = $state<SpatialRuntimeStatus>({ state: 'created' });
  let resizeRevision = $state(0);

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

  onMount(() => {
    let mounted = true;
    const runtime = createBabylonSpatialRuntime(canvas, (nextStatus) => {
      if (mounted) status = nextStatus;
    });

    const resize = (width: number, height: number): void => {
      const viewport = {
        width: Math.max(1, Math.round(width)),
        height: Math.max(1, Math.round(height)),
        dpr: Math.min(2, Math.max(1, window.devicePixelRatio || 1)),
      };
      runtime.dispatch({ type: 'RESIZE', ...viewport });
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
    void runtime.start();

    return () => {
      mounted = false;
      observer.disconnect();
      runtime.dispose();
    };
  });
</script>

<div class="spatial-canvas" bind:this={host}>
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
