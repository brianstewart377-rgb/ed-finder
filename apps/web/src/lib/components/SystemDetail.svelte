<script lang="ts">
  import { createQuery } from '@tanstack/svelte-query';
  import { tick } from 'svelte';
  import {
    ApiError,
    getSystem,
    type SystemDetailBody,
    type SystemDetailRing,
    type SystemDetailStation,
  } from '$lib/api/client';
  import { queryKeys } from '$lib/api/query';
  import type { Id64 } from '$lib/domain/id64';
  import SpatialCanvas from '$lib/spatial/SpatialCanvas.svelte';
  import type { RuntimeEvent } from '$lib/spatial/contracts';
  import {
    bodyTypeLabel,
    buildSystemScene,
    stellarClassification,
  } from '$lib/spatial/system-scene';
  import SystemRatings from './SystemRatings.svelte';
  import {
    hotspotSummary,
    isFleetCarrier,
    percent,
    titleFromCode,
  } from './system-detail-format';

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
  let selection = $state<{
    systemId: Id64;
    bodyId: number;
    name: string;
  }>();
  const selectionAnnouncement = $derived(
    selection && selection.systemId === id64
      ? `Selected ${selection.name}`
      : '',
  );
  let systemMapRevision = $state(0);

  const detail = createQuery(() => ({
    queryKey: queryKeys.system(id64),
    queryFn: ({ signal }) => getSystem(id64, signal),
    retry: (failureCount, error) =>
      !(error instanceof ApiError && isAbsent(error.status)) &&
      failureCount < 1,
  }));
  // Frontier BodyIDs are local to a system. Guard both consumers before any
  // render, including while the query is switching to the next system.
  const selectedBodyId = $derived(
    selection && selection.systemId === id64 && detail.data?.id64 === id64
      ? selection.bodyId
      : undefined,
  );
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
    if (x == null || y == null || z == null) return 'Coordinates unavailable';
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
  const bodyNames = $derived(
    new Map(
      (detail.data?.bodies ?? []).map((body) => [body.bodyKey, body.name]),
    ),
  );
  // Busy systems can hold dozens of fleet carriers, and the catalogue only has
  // a snapshot of where they were, so they sit behind a toggle.
  const ports = $derived(
    (detail.data?.stations ?? []).filter(
      (station) => !isFleetCarrier(station.stationType),
    ),
  );
  const carriers = $derived(
    (detail.data?.stations ?? []).filter((station) =>
      isFleetCarrier(station.stationType),
    ),
  );

  $effect.pre(() => {
    // Leaving a system ends the visit; returning must not restore its pick.
    // Refetches of the same system leave the selection intact.
    if (selection && selection.systemId !== id64) selection = undefined;
  });

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

  /** `Metallic · Pristine reserves`; null when neither is catalogued. */
  function ringFacts(ring: SystemDetailRing): string | null {
    const reserve = titleFromCode(ring.reserveLevel);
    const facts = [
      titleFromCode(ring.ringType),
      reserve ? `${reserve} reserves` : null,
    ].filter((fact): fact is string => fact !== null);
    return facts.length > 0 ? facts.join(' · ') : null;
  }

  function ringHotspots(ring: SystemDetailRing): string {
    const summary = hotspotSummary(ring.hotspots);
    if (summary) return `Hotspots: ${summary}`;
    return ring.signalsComplete === true
      ? 'No hotspots'
      : 'Hotspots not recorded';
  }

  /** `Coriolis Starport · 500 ls · Reference System 3`. */
  function stationFacts(station: SystemDetailStation): string {
    const body = station.bodyKey ? bodyNames.get(station.bodyKey) : undefined;
    return [
      titleFromCode(station.stationType) ?? 'Type not recorded',
      station.distanceFromArrivalLs != null
        ? `${integer(station.distanceFromArrivalLs)} ls`
        : null,
      body ?? null,
    ]
      .filter((fact): fact is string => fact !== null)
      .join(' · ');
  }

  /**
   * `Extraction (primary) · Refinery (secondary)`; null when none is
   * catalogued. A share appears only if the catalogue holds one: the Spansh
   * import deliberately stores designations without shares.
   */
  function stationEconomies(station: SystemDetailStation): string | null {
    if (station.economies.length === 0) return null;
    return station.economies
      .map((economy) => {
        const name = titleFromCode(economy.economy) ?? economy.economy;
        const share =
          economy.weight != null ? ` ${percent(economy.weight)}` : '';
        const role = economy.isPrimary
          ? ' (primary)'
          : economy.isSecondary
            ? ' (secondary)'
            : '';
        return `${name}${share}${role}`;
      })
      .join(' · ');
  }

  function selectBody(bodyId: number): void {
    const system = detail.data;
    if (!system || system.id64 !== id64) return;
    const body = system.bodies.find((body) => body.id === bodyId);
    if (!body) return;
    // Capture the announcement on selection, not on catalogue refetches.
    selection = { systemId: id64, bodyId, name: body.name };
    systemMapRevision += 1;
  }

  function handleSystemMapEvent(event: RuntimeEvent): void {
    if (
      event.type === 'TARGET_PICKED' &&
      event.target?.kind === 'body' &&
      event.target.ref.systemId64 === id64
    ) {
      selectBody(event.target.ref.bodyId);
    }
  }
</script>

<section
  class="system-detail"
  data-system-id64={id64}
  aria-busy={detail.isPending}
>
  <p class="system-detail-announcement" aria-live="polite" aria-atomic="true">
    {selectionAnnouncement}
  </p>
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

    <SystemRatings {id64} bodies={detail.data.bodies} {headingId} />

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
                {#if selectedBody.rings.length > 0}
                  <div class="body-ring-list">
                    <dt>Rings, belts and hotspots</dt>
                    <dd>
                      <ul>
                        {#each selectedBody.rings as ring (ring.ringKey)}
                          {@const facts = ringFacts(ring)}
                          <li data-ring-key={ring.ringKey}>
                            <p class="ring-name">{ring.name}</p>
                            {#if facts}
                              <p>{facts}</p>
                            {/if}
                            <p>{ringHotspots(ring)}</p>
                          </li>
                        {/each}
                      </ul>
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

    {#if detail.data.stations.length > 0}
      <section
        class="system-stations"
        aria-labelledby={`${headingId}-stations`}
      >
        <p class="eyebrow">Catalogue</p>
        <h2 id={`${headingId}-stations`}>Stations</h2>
        {#if ports.length > 0}
          <ul>
            {#each ports as station (station.stationKey)}
              {@const economies = stationEconomies(station)}
              <li data-station-key={station.stationKey}>
                <p class="station-name">{station.name}</p>
                <p>{stationFacts(station)}</p>
                <p>{economies ?? 'Economy not recorded'}</p>
              </li>
            {/each}
          </ul>
        {/if}
        {#if carriers.length > 0}
          <details class="station-carriers">
            <summary>
              {carriers.length === 1
                ? '1 fleet carrier'
                : `${integer(carriers.length)} fleet carriers`}
            </summary>
            <p class="station-carriers-note">
              Carriers can move at any time; this is where the catalogue last
              saw them.
            </p>
            <ul>
              {#each carriers as station (station.stationKey)}
                <li data-station-key={station.stationKey}>
                  <p class="station-name">{station.name}</p>
                  <p>{stationFacts(station)}</p>
                </li>
              {/each}
            </ul>
          </details>
        {/if}
      </section>
    {/if}
  {/if}
</section>
