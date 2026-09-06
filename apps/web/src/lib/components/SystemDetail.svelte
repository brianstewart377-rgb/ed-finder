<script lang="ts">
  import { createQuery } from '@tanstack/svelte-query';
  import { tick } from 'svelte';
  import { ApiError, getSystem } from '$lib/api/client';
  import { queryKeys } from '$lib/api/query';
  import type { Id64 } from '$lib/domain/id64';

  let {
    id64,
    headingId = 'system-detail-title',
    autofocusHeading = false,
  } = $props<{
    id64: Id64;
    headingId?: string;
    autofocusHeading?: boolean;
  }>();
  let heading = $state<HTMLHeadingElement>();
  let lastFocusedId: Id64 | null = null;

  const detail = createQuery(() => ({
    queryKey: queryKeys.system(id64),
    queryFn: ({ signal }) => getSystem(id64, signal),
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 404) && failureCount < 1,
  }));
  const notFound = $derived(
    detail.error instanceof ApiError && detail.error.status === 404,
  );
  const coordinates = $derived.by(() => {
    if (!detail.data) return null;
    const { x, y, z } = detail.data;
    return [x, y, z].every((value) => typeof value === 'number')
      ? `${x?.toFixed(2)}, ${y?.toFixed(2)}, ${z?.toFixed(2)} ly`
      : null;
  });

  $effect(() => {
    if (!autofocusHeading || !detail.data || lastFocusedId === id64) return;
    lastFocusedId = id64;
    void tick().then(() => heading?.focus({ preventScroll: true }));
  });

  const integer = (value: number | null | undefined) =>
    typeof value === 'number' ? new Intl.NumberFormat().format(value) : null;
</script>

<section
  class="system-detail"
  data-system-id64={id64}
  aria-busy={detail.isPending}
>
  {#if detail.isPending}
    <p class="eyebrow">Inspect</p>
    <h1 id={headingId}>Loading system…</h1>
    <p class="state-copy" role="status">
      Retrieving catalogue detail for <code>{id64}</code>.
    </p>
  {:else if detail.isError}
    <p class="eyebrow">Inspect</p>
    <h1 id={headingId}>
      {notFound ? 'System not found' : 'System detail unavailable'}
    </h1>
    <p class="state-copy" role="alert">
      {#if notFound}
        No catalogue system exists for the exact identifier <code>{id64}</code>.
      {:else}
        ED-Finder could not load this system. Your selected-system context is
        unchanged.
      {/if}
    </p>
    <button
      class="secondary-button"
      type="button"
      onclick={() => detail.refetch()}>Try again</button
    >
  {:else if detail.data}
    <p class="eyebrow">System detail</p>
    <h1 id={headingId} tabindex="-1" bind:this={heading}>
      {detail.data.name}
    </h1>
    <p class="system-identity">ID64 <code>{detail.data.id64}</code></p>

    <dl class="detail-grid">
      {#if coordinates}<div>
          <dt>Coordinates</dt>
          <dd>{coordinates}</dd>
        </div>{/if}
      {#if detail.data.population != null}<div>
          <dt>Population</dt>
          <dd>{integer(detail.data.population)}</dd>
        </div>{/if}
      {#if detail.data.primary_economy}<div>
          <dt>Primary economy</dt>
          <dd>{detail.data.primary_economy}</dd>
        </div>{/if}
      {#if detail.data.security}<div>
          <dt>Security</dt>
          <dd>{detail.data.security}</dd>
        </div>{/if}
      {#if detail.data.allegiance}<div>
          <dt>Allegiance</dt>
          <dd>{detail.data.allegiance}</dd>
        </div>{/if}
      {#if detail.data.government}<div>
          <dt>Government</dt>
          <dd>{detail.data.government}</dd>
        </div>{/if}
      {#if detail.data.main_star_type}<div>
          <dt>Main star</dt>
          <dd>
            {detail.data.main_star_type}{detail.data.main_star_subtype
              ? ` · ${detail.data.main_star_subtype}`
              : ''}
          </dd>
        </div>{/if}
      {#if detail.data.primary_archetype}<div>
          <dt>Development fit</dt>
          <dd>{detail.data.primary_archetype}</dd>
        </div>{/if}
      {#if detail.data.overall_development_potential != null}<div>
          <dt>Development potential</dt>
          <dd>{detail.data.overall_development_potential}</dd>
        </div>{/if}
      <div>
        <dt>Bodies returned</dt>
        <dd>{detail.data.bodies?.length ?? 0}</dd>
      </div>
      <div>
        <dt>Stations returned</dt>
        <dd>{detail.data.stations?.length ?? 0}</dd>
      </div>
    </dl>
  {/if}
</section>
