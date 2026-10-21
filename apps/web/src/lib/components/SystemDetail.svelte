<script lang="ts">
  import { createQuery } from '@tanstack/svelte-query';
  import { tick } from 'svelte';
  import { ApiError, getSystem, type SystemDetailBody } from '$lib/api/client';
  import { queryKeys } from '$lib/api/query';
  import type { Id64 } from '$lib/domain/id64';
  import SpatialCanvas from '$lib/spatial/SpatialCanvas.svelte';
  import type { RuntimeEvent } from '$lib/spatial/contracts';
  import {
    bodyTypeLabel,
    buildSystemScene,
    stellarClassification,
  } from '$lib/spatial/system-scene';

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
      !(error instanceof ApiError && isAbsent(error.status)) &&
      failureCount < 1,
  }));
  // 404: no such system in the published catalogue. 422: an id64 beyond the
  // catalogue's signed 64-bit key space, which therefore cannot exist there.
  function isAbsent(status: number): boolean {
    return status === 404 || status === 422;
  }
  const notFound = $derived(
    detail.error instanceof ApiError && isAbsent(detail.error.status),
  );
  const coordinates = $derived.by(() => {
    if (!detail.data) return null;
    const { x, y, z } = detail.data;
    return `${x.toFixed(2)}, ${y.toFixed(2)}, ${z.toFixed(2)} ly`;
  });
  const mainStar = $derived(
    detail.data?.bodies.find((body) => body.isMainStar === true) ?? null,
  );
  const bodyCount = $derived.by(() => {
    if (!detail.data) return null;
    const { bodies, sourceBodyCount } = detail.data;
    // Only flag an incomplete catalogue: the source's own body total can lag
    // behind the bodies actually loaded, which is not a gap.
    return sourceBodyCount != null && bodies.length < sourceBodyCount
      ? `${integer(bodies.length)} of ${integer(sourceBodyCount)} known`
      : integer(bodies.length);
  });
  const catalogueUpdated = $derived.by(() => {
    const value = detail.data?.sourceUpdatedAt;
    if (!value) return null;
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? null
      : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(
          date,
        );
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
    detail.data?.bodies.find((body) => body.id === selectedBodyId) ?? null,
  );
  const selectedRings = $derived(
    selectedBody?.rings.filter((ring) => ring.kind === 'RING').length ?? 0,
  );
  const selectedBelts = $derived(
    selectedBody?.rings.filter((ring) => ring.kind === 'BELT').length ?? 0,
  );

  $effect(() => {
    if (!autofocusHeading || !detail.data || lastFocusedId === id64) return;
    lastFocusedId = id64;
    void tick().then(() => heading?.focus({ preventScroll: true }));
  });

  const integer = (value: number | null | undefined) =>
    typeof value === 'number'
      ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(
          value,
        )
      : null;

  function bodyClass(body: SystemDetailBody): string {
    const label = bodyTypeLabel(body.bodyType) ?? 'Unknown body type';
    const classification = stellarClassification(body);
    return classification ? `${label} · ${classification}` : label;
  }

  function signalLabel(code: string): string {
    return code.replace(/^saa_signaltype_/u, '').replaceAll('_', ' ');
  }

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
      <div>
        <dt>Coordinates</dt>
        <dd>{coordinates}</dd>
      </div>
      {#if detail.data.lifecycleState !== 'ACTIVE'}<div
          data-system-lifecycle={detail.data.lifecycleState}
        >
          <dt>Catalogue status</dt>
          <dd>
            {detail.data.lifecycleState === 'RETIRED'
              ? 'Retired from the catalogue'
              : 'Missing from the latest catalogue source'}
          </dd>
        </div>{/if}
      <div>
        <dt>Main star</dt>
        <dd>
          {mainStar
            ? (stellarClassification(mainStar) ?? 'Star (class not recorded)')
            : 'Not recorded'}
        </dd>
      </div>
      <div>
        <dt>Bodies returned</dt>
        <dd>{bodyCount}</dd>
      </div>
      <div>
        <dt>Stations returned</dt>
        <dd>{integer(detail.data.stations.length)}</dd>
      </div>
      {#if catalogueUpdated}<div>
          <dt>Catalogue updated</dt>
          <dd>{catalogueUpdated}</dd>
        </div>{/if}
      <div class="detail-unavailable" data-unavailable-fields>
        <dt>Population, economy, security, allegiance, government</dt>
        <dd>Not available yet</dd>
      </div>
      <div class="detail-unavailable" data-unavailable-fields>
        <dt>Development fit</dt>
        <dd>Not available yet</dd>
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
            {#each detail.data.bodies as body (body.bodyKey)}
              {#if typeof body.id === 'number'}
                <li>
                  <button
                    type="button"
                    class:active={body.id === selectedBodyId}
                    aria-pressed={body.id === selectedBodyId}
                    onclick={() => selectBody(body.id as number)}
                  >
                    <strong>{body.name}</strong>
                    <span>{bodyClass(body)}</span>
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
              <h3>{selectedBody.name}</h3>
              <dl>
                <div>
                  <dt>Class</dt>
                  <dd>{bodyClass(selectedBody)}</dd>
                </div>
                {#if selectedBody.distanceFromArrivalLs != null}
                  <div>
                    <dt>Arrival distance</dt>
                    <dd>{integer(selectedBody.distanceFromArrivalLs)} ls</dd>
                  </div>
                {/if}
                {#if selectedBody.radiusKm != null}
                  <div>
                    <dt>Radius</dt>
                    <dd>{integer(selectedBody.radiusKm)} km</dd>
                  </div>
                {/if}
                <div>
                  <dt>Rings</dt>
                  <dd>
                    {selectedRings > 0
                      ? `${selectedRings} known`
                      : 'None recorded'}
                  </dd>
                </div>
                {#if selectedBelts > 0}
                  <div>
                    <dt>Belts</dt>
                    <dd>{selectedBelts} known</dd>
                  </div>
                {/if}
                {#if selectedBody.isLandable != null}
                  <div>
                    <dt>Landable</dt>
                    <dd>{selectedBody.isLandable ? 'Yes' : 'No'}</dd>
                  </div>
                {/if}
                <div>
                  <dt>Signals</dt>
                  <dd>
                    {selectedBody.signals.length > 0
                      ? selectedBody.signals
                          .map(
                            (signal) =>
                              `${signal.count} ${signalLabel(signal.signalType)}`,
                          )
                          .join(' · ')
                      : 'None recorded'}
                  </dd>
                </div>
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
