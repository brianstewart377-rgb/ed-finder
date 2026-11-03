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
    <div>
      <p class="eyebrow">Galaxy workspace</p>
      <h2 id={`${id}-title`}>Map window</h2>
    </div>
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
    <SpatialCanvas {...canvasProps} />
    {@render afterCanvas?.()}
  </div>
</div>

<style>
  .explore-map-window {
    position: relative;
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    height: min(70rem, calc(100dvh - 2rem));
    align-self: start;
    border: 1px solid var(--line);
    border-radius: var(--radius-lg);
    background: var(--panel);
    background-image: var(--panel-gloss);
    box-shadow: var(--shadow-panel);
    color: var(--text);
  }
  .map-window-heading {
    display: flex;
    flex-shrink: 0;
    justify-content: space-between;
    align-items: center;
    gap: 0.75rem;
    padding: 1rem;
    border-bottom: 1px solid var(--line);
  }
  .map-window-heading h2 {
    margin: 0;
    font-family: var(--font-hud);
    font-size: 1.15rem;
  }
  .eyebrow {
    margin: 0 0 0.25rem;
    color: var(--text-muted);
  }
  .map-window-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  .map-window-content {
    min-height: 0;
    overflow: auto;
    overscroll-behavior: contain;
    padding: 0.75rem;
  }
  .map-window-content :global(.spatial-canvas) {
    height: clamp(16rem, 45dvh, 42rem);
  }
  .explore-map-window[data-expanded='true'] :global(.spatial-canvas) {
    height: clamp(20rem, 65dvh, 56rem);
  }
  .quiet-button {
    min-height: 2.75rem;
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
    .map-window-heading {
      flex-wrap: wrap;
    }
    .map-window-content {
      padding: 0.5rem;
    }
    .explore-map-window :global(.spatial-canvas),
    .explore-map-window[data-expanded='true'] :global(.spatial-canvas) {
      height: clamp(16rem, 45dvh, 42rem);
    }
  }
</style>
