<script lang="ts">
  import { tick } from 'svelte';
  import type { SystemDetailStation } from '$lib/api/client';
  import type { Id64 } from '$lib/domain/id64';
  import {
    AVAILABILITY_LABELS,
    sourceDate,
    type RatingsSourceState,
  } from './source-freshness';

  let {
    systemId,
    sourceUpdatedAt,
    canonicalGenerationId,
    canonicalGenerationLabel,
    ratings,
    stations,
  }: {
    systemId: Id64;
    sourceUpdatedAt?: string | null;
    canonicalGenerationId?: string;
    canonicalGenerationLabel?: string;
    ratings: RatingsSourceState | null;
    /** Only stations whose economies this page actually displays. */
    stations: readonly SystemDetailStation[];
  } = $props();

  const id = $props.id();
  let openedFor = $state<Id64 | null>(null);
  const open = $derived(openedFor === systemId);
  let trigger = $state<HTMLButtonElement>();
  let panel = $state<HTMLDivElement>();
  let panelLeft = $state(8);
  let panelTop = $state(8);
  let panelMaxHeight = $state<number | null>(null);
  let panelMaxWidth = $state<number | null>(null);
  const catalogueDate = $derived(sourceDate(sourceUpdatedAt));
  const hasEconomies = $derived(
    stations.some((station) => station.economies.length > 0),
  );
  const latestObservation = $derived.by(() => {
    let latest: string | null = null;
    for (const station of stations) {
      const observed = station.lastObservedAt;
      if (
        observed &&
        sourceDate(observed) &&
        (latest === null || Date.parse(observed) > Date.parse(latest))
      )
        latest = observed;
    }
    return latest;
  });
  const undatedStations = $derived(
    stations.filter((station) => !sourceDate(station.lastObservedAt)).length,
  );

  // Match BodyFilters: a non-modal, viewport-bounded pop-out, including zoom
  // and the mobile visual viewport. It does not trap focus or block Inspect.
  function positionPanel() {
    if (!panel || !trigger) return;
    const anchor = trigger.getBoundingClientRect();
    const bounds = panel.getBoundingClientRect();
    const margin = 8;
    const viewport = window.visualViewport;
    const layoutWidth =
      document.documentElement.clientWidth || window.innerWidth;
    const layoutHeight =
      document.documentElement.clientHeight || window.innerHeight;
    const width = Math.min(viewport?.width ?? layoutWidth, layoutWidth);
    const height = Math.min(viewport?.height ?? layoutHeight, layoutHeight);
    const left = viewport?.offsetLeft ?? 0;
    const top = viewport?.offsetTop ?? 0;
    panelMaxHeight = Math.max(0, Math.floor(height - margin * 2));
    panelMaxWidth = Math.max(0, Math.floor(width - margin * 2));
    const maxLeft = Math.max(
      left + margin,
      left + width - bounds.width - margin,
    );
    const maxTop = Math.max(
      top + margin,
      top + height - bounds.height - margin,
    );
    if (width < 640) {
      panelLeft = Math.max(left + margin, left + (width - bounds.width) / 2);
      panelTop = Math.max(top + margin, top + (height - bounds.height) / 2);
      return;
    }
    panelLeft = Math.max(left + margin, Math.min(anchor.left, maxLeft));
    const below = anchor.bottom + margin;
    panelTop = Math.max(
      top + margin,
      Math.min(
        below <= maxTop ? below : anchor.top - bounds.height - margin,
        maxTop,
      ),
    );
  }

  function close() {
    openedFor = null;
    trigger?.focus({ preventScroll: true });
  }

  async function toggle() {
    if (open) {
      close();
      return;
    }
    openedFor = systemId;
    await tick();
    if (!open) return;
    positionPanel();
    panel?.focus({ preventScroll: true });
  }

  function keydown(event: KeyboardEvent) {
    if (open && event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      close();
    }
  }

  function outsideClick(event: MouseEvent) {
    if (
      open &&
      event.target instanceof Node &&
      !panel?.contains(event.target) &&
      !trigger?.contains(event.target)
    )
      close();
  }

  $effect.pre(() => {
    if (openedFor !== null && openedFor !== systemId) openedFor = null;
  });

  $effect(() => {
    if (!open) return;
    // Inspect can itself be inside SystemOverlay. Handle Escape in capture so
    // its window listener does not also close the underlying Inspect panel.
    window.addEventListener('keydown', keydown, true);
    return () => window.removeEventListener('keydown', keydown, true);
  });

  $effect(() => {
    const element = panel;
    if (!element) return;
    positionPanel();
    const observer =
      typeof ResizeObserver === 'undefined'
        ? undefined
        : new ResizeObserver(positionPanel);
    observer?.observe(element);
    const scroll = (event: Event) => {
      if (event.target instanceof Node && element.contains(event.target))
        return;
      positionPanel();
    };
    const viewport = window.visualViewport;
    window.addEventListener('scroll', scroll, true);
    window.addEventListener('resize', positionPanel);
    viewport?.addEventListener('resize', positionPanel);
    viewport?.addEventListener('scroll', positionPanel);
    return () => {
      observer?.disconnect();
      window.removeEventListener('scroll', scroll, true);
      window.removeEventListener('resize', positionPanel);
      viewport?.removeEventListener('resize', positionPanel);
      viewport?.removeEventListener('scroll', positionPanel);
    };
  });
</script>

<svelte:window onclick={outsideClick} />

<button
  bind:this={trigger}
  class="sources-trigger"
  type="button"
  aria-haspopup="dialog"
  aria-expanded={open}
  aria-controls={open ? `${id}-dialog` : undefined}
  onclick={toggle}>Sources &amp; freshness</button
>

{#if open}
  <div
    bind:this={panel}
    id={`${id}-dialog`}
    class="sources-dialog"
    role="dialog"
    aria-modal="false"
    aria-labelledby={`${id}-title`}
    aria-describedby={`${id}-help`}
    tabindex="-1"
    style:left={`${panelLeft}px`}
    style:top={`${panelTop}px`}
    style:max-height={panelMaxHeight === null
      ? undefined
      : `${panelMaxHeight}px`}
    style:max-width={panelMaxWidth === null ? undefined : `${panelMaxWidth}px`}
  >
    <header>
      <h2 id={`${id}-title`}>Sources &amp; freshness</h2>
      <button type="button" onclick={close}>Close</button>
    </header>
    <p id={`${id}-help`} class="hint">
      Each source has its own update history. The catalogue date applies only to
      catalogue facts; it does not date ratings or observations.
    </p>
    <dl class="source-products">
      <div data-source-product="canonical">
        <dt>Canonical catalogue</dt>
        <dd>
          <p>
            Bodies, stations list and coordinates from the Spansh-derived
            catalogue.
          </p>
          <p>
            <strong>Available</strong> — catalogue facts loaded for this system.
          </p>
          <p>
            Updated:
            {#if catalogueDate && sourceUpdatedAt}
              <time datetime={sourceUpdatedAt}>{catalogueDate}</time>
            {:else}
              <span data-unavailable-fields data-availability="unknown"
                >Unknown</span
              >
              — no update time supplied.
            {/if}
          </p>
          {#if canonicalGenerationLabel || canonicalGenerationId}
            <p class="source-identity">
              Generation {canonicalGenerationLabel ?? canonicalGenerationId}
              {#if canonicalGenerationLabel && canonicalGenerationId}
                ({canonicalGenerationId})
              {/if}
            </p>
          {/if}
        </dd>
      </div>
      <div data-source-product="ratings">
        <dt>Ratings V4 potentials</dt>
        <dd>
          <p>Seven economy potentials from a published derived generation.</p>
          {#if !ratings || ratings.status === 'loading'}
            <p role="status">
              <strong>Loading</strong> — retrieving published ratings.
            </p>
          {:else if ratings.status === 'available'}
            <p>
              <strong>Available</strong> — published potentials loaded for this system.
            </p>
          {:else}
            <p data-unavailable-fields data-availability={ratings.status}>
              <strong>{AVAILABILITY_LABELS[ratings.status]}</strong> —
              {ratings.status === 'unknown'
                ? 'the published source has no ratings for this system.'
                : 'the ratings request failed.'}
            </p>
            {#if ratings.status === 'unavailable'}
              <button type="button" onclick={ratings.retry}>Retry</button>
            {/if}
          {/if}
          {#if ratings?.identity}
            <p class="source-identity">
              Generation {ratings.identity.derivedGenerationId}
            </p>
            <p>
              Publication {ratings.identity.publicationSequence} · Scorer {ratings
                .identity.scorerVersion}
            </p>
            <p>
              Published: Unknown — the response supplies an identity, but no
              publication time.
            </p>
          {/if}
        </dd>
      </div>
      {#if stations.length > 0}
        <div data-source-product="station-observations">
          <dt>Station economies / observations</dt>
          <dd>
            <p>
              Economies for the stations shown on this page; observation history
              is separate from the body catalogue.
            </p>
            {#if hasEconomies}
              <p>
                <strong>Available</strong> — station economy values were returned.
              </p>
            {:else}
              <p data-unavailable-fields data-availability="unknown">
                <strong>Unknown</strong> — the source has no economy value for these
                stations.
              </p>
            {/if}
            {#if latestObservation}
              <p>
                Last observed: <time datetime={latestObservation}
                  >{sourceDate(latestObservation)}</time
                >
              </p>
              <p class="hint">
                Latest dated station observation; other stations may be older.
              </p>
              {#if undatedStations > 0}
                <p class="hint">
                  {undatedStations} stations have no observation time supplied.
                </p>
              {/if}
            {:else}
              <p>No observation yet</p>
              <p class="hint">
                No observation time is supplied for these stations; returned
                economy values may still be known.
              </p>
            {/if}
          </dd>
        </div>
      {/if}
      <div data-source-product="commander">
        <dt>Commander data</dt>
        <dd>
          <p>
            Population, economy, security, allegiance, government and
            Development fit.
          </p>
          <p data-unavailable-fields data-availability="not-integrated">
            <strong>Not integrated yet</strong> — ED-Finder does not read these fields
            yet.
          </p>
        </dd>
      </div>
    </dl>
  </div>
{/if}

<style>
  button {
    padding: 0.35rem 0.55rem;
    border: 1px solid var(--line);
    border-radius: 0.4rem;
    background: var(--panel-raised);
    color: inherit;
    font: inherit;
    cursor: pointer;
  }
  button:focus-visible,
  .sources-dialog:focus-visible {
    outline: 2px solid var(--color-cyan);
    outline-offset: 2px;
  }
  .sources-trigger {
    margin-left: 0.45rem;
    font-size: 0.75rem;
    vertical-align: middle;
  }
  .sources-dialog {
    position: fixed;
    z-index: 30;
    box-sizing: border-box;
    width: min(32rem, calc(100% - 1rem));
    max-height: calc(100dvh - 1rem);
    overflow-y: auto;
    overscroll-behavior: contain;
    padding: 0.9rem;
    border: 1px solid var(--color-cyan);
    border-radius: 0.7rem;
    background: var(--color-panel);
    box-shadow: 0 0.6rem 2rem #0008;
    font-size: 0.85rem;
    font-weight: normal;
    line-height: 1.45;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    margin-bottom: 0.65rem;
  }
  h2 {
    margin: 0;
    font-size: 1.05rem;
  }
  .hint {
    color: var(--muted);
  }
  .source-products {
    display: grid;
    gap: 0.75rem;
    margin: 0.8rem 0 0;
  }
  .source-products > div {
    padding-top: 0.7rem;
    border-top: 1px solid var(--line);
  }
  .source-products dt {
    margin: 0 0 0.3rem;
    color: inherit;
    font-size: 0.9rem;
    font-weight: 600;
    letter-spacing: normal;
    text-transform: none;
  }
  .source-products dd {
    margin: 0;
  }
  p {
    margin: 0.25rem 0;
  }
  .source-identity {
    overflow-wrap: anywhere;
  }
</style>
