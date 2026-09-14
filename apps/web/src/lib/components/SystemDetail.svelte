<script lang="ts">
  import { createQuery } from '@tanstack/svelte-query';
  import { tick } from 'svelte';
  import { ApiError, getSystem } from '$lib/api/client';
  import { queryKeys } from '$lib/api/query';
  import type { Id64 } from '$lib/domain/id64';
  import SpatialCanvas from '$lib/spatial/SpatialCanvas.svelte';
  import type { RuntimeEvent } from '$lib/spatial/contracts';
  import { buildSystemScene } from '$lib/spatial/system-scene';

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
  let selectedBodyId = $state<number | undefined>();
  let systemMapRevision = $state(0);

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
  const systemScene = $derived(
    detail.data
      ? buildSystemScene(
          detail.data,
          detail.dataUpdatedAt + systemMapRevision,
          selectedBodyId,
        )
      : null,
  );
  const selectedBody = $derived(
    detail.data?.bodies?.find((body) => body.id === selectedBodyId) ?? null,
  );

  $effect(() => {
    if (!autofocusHeading || !detail.data || lastFocusedId === id64) return;
    lastFocusedId = id64;
    void tick().then(() => heading?.focus({ preventScroll: true }));
  });

  const integer = (value: number | null | undefined) =>
    typeof value === 'number' ? new Intl.NumberFormat().format(value) : null;

  function selectBody(bodyId: number): void {
    selectedBodyId = bodyId;
    systemMapRevision += 1;
  }

  function handleSystemMapEvent(event: RuntimeEvent): void {
    if (event.type === 'TARGET_PICKED' && event.target?.kind === 'body') {
      selectBody(event.target.ref.bodyId);
    }
  }
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

    {#if systemScene && systemScene.bodies.length > 0}
      <section class="system-map-panel" aria-labelledby={`${headingId}-map`}>
        <div class="system-map-heading">
          <div>
            <p class="eyebrow">3D system map</p>
            <h2 id={`${headingId}-map`}>Explore {detail.data.name}</h2>
          </div>
          <span>{systemScene.bodies.length} catalogue bodies</span>
        </div>
        <p class="system-map-truth-note">
          Body classes, radii, arrival distances, and known ring state come from
          the catalogue. Orbit positions and display sizes are a semantic 3D
          layout—not physical scale or observed orbital phase.
        </p>
        <SpatialCanvas
          scene={systemScene}
          onRuntimeEvent={handleSystemMapEvent}
        />
        <div class="system-map-browser">
          <ol aria-label="System bodies">
            {#each detail.data.bodies ?? [] as body, index (`body-${body.id ?? index}`)}
              {#if typeof body.id === 'number'}
                <li>
                  <button
                    type="button"
                    class:active={body.id === selectedBodyId}
                    aria-pressed={body.id === selectedBodyId}
                    onclick={() => selectBody(body.id as number)}
                  >
                    <strong>{body.name ?? `Body ${body.id}`}</strong>
                    <span
                      >{body.subtype ??
                        body.body_type ??
                        'Unknown body type'}</span
                    >
                  </button>
                </li>
              {/if}
            {/each}
          </ol>
          {#if selectedBody}
            <article
              class="system-body-card"
              aria-live="polite"
              data-selected-body-id={selectedBody.id}
            >
              <p class="eyebrow">Selected body</p>
              <h3>{selectedBody.name ?? `Body ${selectedBody.id}`}</h3>
              <dl>
                <div>
                  <dt>Class</dt>
                  <dd>
                    {selectedBody.subtype ??
                      selectedBody.body_type ??
                      'Unknown'}
                  </dd>
                </div>
                {#if selectedBody.distance_from_star != null}
                  <div>
                    <dt>Arrival distance</dt>
                    <dd>{integer(selectedBody.distance_from_star)} ls</dd>
                  </div>
                {/if}
                {#if selectedBody.radius != null}
                  <div>
                    <dt>Radius</dt>
                    <dd>{integer(selectedBody.radius)} m</dd>
                  </div>
                {/if}
                <div>
                  <dt>Rings</dt>
                  <dd>
                    {selectedBody.ring_state === 'ringed'
                      ? `${selectedBody.ring_count ?? selectedBody.rings?.length ?? 1} known`
                      : selectedBody.ring_state === 'not_ringed'
                        ? 'None recorded'
                        : 'Unknown'}
                  </dd>
                </div>
                {#if selectedBody.is_landable != null}
                  <div>
                    <dt>Landable</dt>
                    <dd>{selectedBody.is_landable ? 'Yes' : 'No'}</dd>
                  </div>
                {/if}
                {#if selectedBody.bio_signal_count != null || selectedBody.geo_signal_count != null}
                  <div>
                    <dt>Signals</dt>
                    <dd>
                      {selectedBody.bio_signal_count ?? 0} biological ·
                      {selectedBody.geo_signal_count ?? 0} geological
                    </dd>
                  </div>
                {/if}
              </dl>
            </article>
          {:else}
            <p class="system-body-empty">
              Select a body in the 3D map or the catalogue list for details.
            </p>
          {/if}
        </div>
      </section>
    {/if}
  {/if}
</section>
