<script lang="ts">
  import { onMount, tick, type ComponentProps, type Snippet } from 'svelte';
  import {
    isTopmostPopout,
    registerPopout,
  } from '$lib/components/popout-stack';
  import SpatialCanvas from '$lib/spatial/SpatialCanvas.svelte';

  let {
    canvasProps,
    expanded,
    onExpand,
    onClose,
    opener = null,
    fallbackFocus = null,
    hoveredSystemId = null,
    id = 'explore-map-window',
    element = $bindable(),
    beforeCanvas,
    afterCanvas,
    selectedSystemName = null,
  }: {
    canvasProps: ComponentProps<typeof SpatialCanvas>;
    expanded: boolean;
    onExpand: () => void;
    onClose: () => void;
    opener?: HTMLElement | null;
    fallbackFocus?: HTMLElement | null;
    hoveredSystemId?: string | null;
    id?: string;
    element?: HTMLDivElement;
    beforeCanvas?: Snippet;
    afterCanvas?: Snippet;
    selectedSystemName?: string | null;
  } = $props();

  let layer = $state(30);
  let closeButton: HTMLButtonElement;
  let closing = false;

  async function close() {
    if (closing) return;
    closing = true;
    const returnTarget = opener;
    const fallback = fallbackFocus;
    onClose();
    // The results rail can be hidden while expanded or at phone width. Wait
    // for its previous layout before restoring the opening control's focus.
    await tick();
    const target = returnTarget?.isConnected ? returnTarget : fallback;
    if (target?.isConnected) target.focus({ preventScroll: true });
  }

  function keydown(event: KeyboardEvent) {
    if (
      event.key !== 'Escape' ||
      event.defaultPrevented ||
      !isTopmostPopout(element)
    )
      return;
    // Finder stays usable behind this non-modal window. Its autocomplete
    // consumes Escape first; the window owns it once suggestions are closed.
    if (
      event.target instanceof Element &&
      event.target.closest('[role="combobox"][aria-expanded="true"]')
    )
      return;
    // The existing keyboard card owns its first Escape and restores focus to
    // its map label. The next Escape closes this enclosing non-modal window.
    if (element?.querySelector('[role="tooltip"]')) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    void close();
  }

  onMount(() => {
    closeButton.focus({ preventScroll: true });
    let resizeFrame = 0;
    const keepWindowVisible = () => {
      cancelAnimationFrame(resizeFrame);
      resizeFrame = requestAnimationFrame(() => {
        // Reflow above this in-document window can move it as the viewport
        // changes. Clamp after layout without moving focus or its camera.
        const bounds = element?.getBoundingClientRect();
        if (bounds && (bounds.top < 0 || bounds.bottom > window.innerHeight))
          element?.scrollIntoView?.({ behavior: 'instant', block: 'start' });
      });
    };
    window.addEventListener('resize', keepWindowVisible);
    return () => {
      window.removeEventListener('resize', keepWindowVisible);
      cancelAnimationFrame(resizeFrame);
    };
  });

  $effect(() => {
    if (!element) return;
    const unregister = registerPopout(element, (value) => (layer = value));
    window.addEventListener('keydown', keydown, true);
    return () => {
      window.removeEventListener('keydown', keydown, true);
      unregister();
    };
  });
</script>

<div
  bind:this={element}
  {id}
  class="map-panel explore-map-window"
  role="dialog"
  aria-modal="false"
  aria-labelledby={`${id}-title`}
  tabindex="-1"
  data-explore-map-window
  data-expanded={expanded}
  data-hovered-system-id={hoveredSystemId ?? ''}
  style:z-index={layer}
>
  <header class="map-window-heading">
    <h2 id={`${id}-title`}>
      {selectedSystemName ? `${selectedSystemName} · Galaxy map` : 'Galaxy map'}
    </h2>
    <div class="map-window-actions">
      <button
        type="button"
        class="quiet-button"
        data-map-window-expand
        aria-pressed={expanded}
        onclick={onExpand}>{expanded ? 'Restore size' : 'Expand'}</button
      >
      <button
        bind:this={closeButton}
        type="button"
        class="quiet-button"
        data-map-window-close
        aria-label="Close map"
        onclick={() => void close()}>Close</button
      >
    </div>
  </header>
  <div class="map-window-content">
    {@render beforeCanvas?.()}
    <SpatialCanvas {...canvasProps} controlsBelow />
  </div>
  <footer class="map-window-footer">
    <button
      type="button"
      class="quiet-button"
      data-map-window-back
      onclick={() => void close()}>Back to results</button
    >
    {@render afterCanvas?.()}
  </footer>
</div>

<style>
  .explore-map-window {
    position: relative;
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    height: calc(100dvh - 1rem);
    align-self: start;
    border: 1px solid var(--neon);
    border-radius: var(--radius-lg);
    background: var(--panel);
    background-image: var(--panel-gloss);
    box-shadow: var(--line-glow), var(--shadow-panel);
    color: var(--text);
    scroll-margin-top: 0.5rem;
  }
  .map-window-heading {
    display: flex;
    flex-shrink: 0;
    justify-content: space-between;
    align-items: center;
    gap: 0.75rem;
    padding: 0.35rem 0.75rem;
    border-bottom: 1px solid var(--line);
  }
  .map-window-heading h2 {
    margin: 0;
    font-family: var(--font-hud);
    font-size: 1.15rem;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .map-window-actions {
    display: flex;
    flex-shrink: 0;
    gap: 0.5rem;
  }
  .map-window-content {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-height: 0;
    padding: 0.5rem 0.75rem 0;
    gap: 0.25rem;
  }
  .map-window-content :global(.map-systems-surface) {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  .map-window-content :global(.spatial-canvas) {
    flex: 1;
    min-height: 0;
    height: auto;
    border: 1px solid var(--line);
  }
  .map-window-content :global(.nearby-systems) {
    margin: 0;
    font-size: 0.75rem;
    max-height: 25%;
    overflow: auto;
  }
  .map-window-content :global(.nearby-systems summary) {
    padding: 0.15rem 0;
  }
  .map-window-content :global(.renderer-status) {
    min-height: 0;
    margin: 0;
    padding: 0;
    font-size: 0.7rem;
  }
  .map-window-footer {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    flex-shrink: 0;
    gap: 0.35rem 0.6rem;
    margin-top: 0.35rem;
    padding: 0.35rem 0.75rem;
    border-top: 1px solid var(--line);
    background-image: var(--panel-gloss);
  }
  .quiet-button {
    min-height: 2.25rem;
    padding: 0.35rem 0.6rem;
    border: 1px solid var(--line);
    border-radius: var(--radius-pill);
    background: var(--panel-raised);
    color: var(--text);
    cursor: pointer;
  }
  .quiet-button:focus-visible,
  .explore-map-window:focus-visible {
    outline: 2px solid var(--focus);
    outline-offset: 2px;
  }
  @media (max-width: 700px) {
    .map-window-heading h2 {
      font-size: 1rem;
    }
    .map-window-heading,
    .map-window-footer {
      padding: 0.4rem 0.5rem;
      gap: 0.3rem;
    }
    .map-window-actions {
      gap: 0.25rem;
    }
    .map-window-content {
      padding: 0.35rem 0.5rem 0;
    }
    .quiet-button {
      font-size: 0.75rem;
    }
  }
</style>
