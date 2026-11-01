<script lang="ts">
  import { untrack } from 'svelte';
  import { SvelteSet } from 'svelte/reactivity';
  import {
    type PlanBodiesV1,
    type PlanFacilityV1,
    type PlanRequestV1,
    type PlanStepV1,
  } from '$lib/api';
  import { facilityFitsLocation, type PlannerLocation } from './locations';
  import { toPlanRequest, MAX_SITES, type PlannerModel } from './model';
  import { evaluatePlanPreview } from './preview';

  let {
    location,
    facilities,
    model,
    bodies,
    onadd,
    onclose,
    titleId,
  }: {
    location: PlannerLocation;
    facilities: PlanFacilityV1[];
    model: PlannerModel;
    bodies: PlanBodiesV1;
    onadd: (facility: PlanFacilityV1) => void;
    onclose: () => void;
    titleId?: string;
  } = $props();

  type Tab = 'Both' | 'Orbital' | 'Surface';
  const tabs: Tab[] = ['Both', 'Orbital', 'Surface'];
  const sectionNames = [
    'Orbital starports',
    'Orbital outposts',
    'Orbital installations',
    'Surface ports',
    'Surface settlements',
    'Surface hubs',
  ];
  const starportOrder = [
    'coriolis_station',
    'asteroid_base',
    'dodecahedron_t3',
    'ocellus_station',
    'orbis_t3',
  ];
  const id = $props.id();
  let tab = $state<Tab>(
    untrack(() =>
      !model.sites.length || location.is_landable === false
        ? 'Orbital'
        : 'Both',
    ),
  );
  let search = $state('');
  let previews = $state<Record<string, PlanStepV1>>({});
  let previewErrors = $state<Record<string, boolean>>({});
  let scrollContainer = $state<HTMLDivElement>();
  let visibleIds = $state<string[]>([]);
  const atLimit = $derived(model.sites.length >= MAX_SITES);

  function sectionFor(facility: PlanFacilityV1): number {
    if (facility.allowed_location.includes('surface')) {
      if (facility.is_port) return 3;
      // Most catalogue categories describe economies, so the stable settlement
      // IDs distinguish settlements from hubs within those categories.
      return facility.category === 'settlement' ||
        facility.id.startsWith('surface_settlement_')
        ? 4
        : 5;
    }
    if (facility.is_port) return facility.tier > 1 ? 0 : 1;
    return 2;
  }

  function compareFacilities(a: PlanFacilityV1, b: PlanFacilityV1): number {
    if (sectionFor(a) === 0) {
      const orderA = starportOrder.indexOf(a.id);
      const orderB = starportOrder.indexOf(b.id);
      const fixedOrder =
        (orderA < 0 ? starportOrder.length : orderA) -
        (orderB < 0 ? starportOrder.length : orderB);
      if (fixedOrder) return fixedOrder;
    }
    return b.tier - a.tier || a.name.localeCompare(b.name);
  }

  const sections = $derived.by(() => {
    const matches = facilities.filter((facility) => {
      const surface = facility.allowed_location.includes('surface');
      return (
        facilityFitsLocation(facility, location) &&
        (tab === 'Both' || (tab === 'Surface' ? surface : !surface)) &&
        facility.name.toLowerCase().includes(search.toLowerCase())
      );
    });
    return sectionNames
      .map((name, index) => ({
        name,
        facilities: matches
          .filter((facility) => sectionFor(facility) === index)
          .sort(compareFacilities),
      }))
      .filter((section) => section.facilities.length);
  });
  const rows = $derived(sections.flatMap((section) => section.facilities));

  function selectTab(next: Tab) {
    tab = next;
    if (scrollContainer) scrollContainer.scrollTop = 0;
  }

  function navigateTabs(event: KeyboardEvent) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const available = tabs.filter(
      (item) => item !== 'Surface' || location.is_landable !== false,
    );
    const index = available.indexOf(tab);
    const next =
      event.key === 'Home'
        ? available[0]
        : event.key === 'End'
          ? available[available.length - 1]
          : available[
              (index +
                (event.key === 'ArrowRight' ? 1 : -1) +
                available.length) %
                available.length
            ];
    selectTab(next);
    document.getElementById(`${id}-tab-${next}`)?.focus();
  }

  function cpSummary(preview: PlanStepV1): string {
    return (
      [
        preview.cost_t3 ? `-${preview.cost_t3} T3` : '',
        preview.cost_t2 ? `-${preview.cost_t2} T2` : '',
        preview.reward_t3 ? `+${preview.reward_t3} T3` : '',
        preview.reward_t2 ? `+${preview.reward_t2} T2` : '',
      ]
        .filter(Boolean)
        .join(' · ') || '0 CP'
    );
  }

  type PreviewContext = {
    request: PlanRequestV1;
    bodyRef: string;
    controller: AbortController;
    candidates: PlanFacilityV1[];
    visible: Set<string>;
    requested: Set<string>;
    ready: boolean;
    timer?: ReturnType<typeof setTimeout>;
  };
  let context: PreviewContext | undefined;
  let inFlight = 0;

  function schedulePreviews(current: PreviewContext) {
    clearTimeout(current.timer);
    current.ready = false;
    current.timer = setTimeout(() => {
      current.ready = true;
      drainPreviews();
    }, 250);
  }

  // Preview the actual next step on the server, only for rows in view and at
  // most six outstanding requests. Catalogue constants never stand in for
  // escalating or Primary Port costs. Keep the shared evaluator's rate limit.
  function drainPreviews() {
    const current = context;
    if (!current?.ready || current.controller.signal.aborted) return;
    for (const facility of current.candidates) {
      if (inFlight >= 6) break;
      if (
        !current.visible.has(facility.id) ||
        current.requested.has(facility.id) ||
        (!current.request.sites.length && !facility.is_port)
      )
        continue;
      current.requested.add(facility.id);
      inFlight++;
      const siteId = `preview-${facility.id}`;
      void (async () => {
        try {
          const result = await evaluatePlanPreview(
            {
              ...current.request,
              sites: [
                ...current.request.sites,
                {
                  site_id: siteId,
                  facility_id: facility.id,
                  body_ref: current.bodyRef,
                  slot_kind: facility.allowed_location.includes('surface')
                    ? 'surface'
                    : 'orbital',
                  status: 'planned',
                  name: '',
                },
              ],
            },
            current.controller.signal,
          );
          const step = result.steps.find((entry) => entry.site_id === siteId);
          if (!step) throw new Error('The preview did not contain this site.');
          if (!current.controller.signal.aborted)
            previews = { ...previews, [facility.id]: step };
        } catch {
          if (!current.controller.signal.aborted)
            previewErrors = { ...previewErrors, [facility.id]: true };
        } finally {
          // Aborting a context does not free capacity until its outstanding
          // calls settle, including transports that cannot cancel immediately.
          inFlight--;
          drainPreviews();
        }
      })();
    }
  }

  $effect(() => {
    const current: PreviewContext = {
      request: toPlanRequest(model, bodies),
      bodyRef: location.body_ref,
      // rows depends on location, tab and search, invalidating stale previews.
      candidates: atLimit ? [] : rows,
      controller: new AbortController(),
      visible: new Set(untrack(() => visibleIds)),
      requested: new Set(),
      ready: false,
    };
    context = current;
    previews = {};
    previewErrors = {};
    schedulePreviews(current);
    return () => {
      clearTimeout(current.timer);
      current.controller.abort();
      if (context === current) context = undefined;
    };
  });

  $effect(() => {
    const root = scrollContainer;
    const candidates = rows;
    if (!root) return;
    if (typeof IntersectionObserver === 'undefined') {
      visibleIds = candidates.slice(0, 6).map((facility) => facility.id);
      return;
    }
    visibleIds = [];
    const intersecting = new SvelteSet<string>();
    let active = true;
    const observer = new IntersectionObserver(
      (entries) => {
        if (!active) return;
        for (const entry of entries) {
          const facilityId = (entry.target as HTMLElement).dataset.previewId;
          if (!facilityId) continue;
          if (entry.isIntersecting) intersecting.add(facilityId);
          else intersecting.delete(facilityId);
        }
        visibleIds = candidates
          .filter((facility) => intersecting.has(facility.id))
          .map((facility) => facility.id);
      },
      { root, threshold: 0 },
    );
    root
      .querySelectorAll('[data-preview-id]')
      .forEach((row) => observer.observe(row));
    return () => {
      active = false;
      observer.disconnect();
    };
  });

  $effect(() => {
    const visible = visibleIds;
    untrack(() => {
      if (!context) return;
      context.visible = new Set(visible);
      schedulePreviews(context);
    });
  });
</script>

<section class="facility-picker" aria-label={`Facilities for ${location.name}`}>
  <div class="picker-heading">
    <h3 id={titleId}>Add a facility on {location.name}</h3>
    <button type="button" onclick={onclose}>Close picker</button>
  </div>
  <div class="picker-tabs" role="tablist" aria-label="Facility location">
    {#each tabs as item (item)}
      <button
        id={`${id}-tab-${item}`}
        type="button"
        role="tab"
        aria-selected={tab === item}
        aria-controls={`${id}-list`}
        tabindex={tab === item ? 0 : -1}
        disabled={item === 'Surface' && location.is_landable === false}
        title={item === 'Surface' && location.is_landable === false
          ? 'Surface facilities require a landable body.'
          : undefined}
        onkeydown={navigateTabs}
        onclick={() => selectTab(item)}>{item}</button
      >
    {/each}
  </div>
  <label class="picker-search"
    >Find a facility <input
      type="search"
      value={search}
      oninput={(event) => {
        search = event.currentTarget.value;
        if (scrollContainer) scrollContainer.scrollTop = 0;
      }}
    /></label
  >
  {#if !model.sites.length}<p>Choose a port for the Primary Port first.</p>{/if}
  {#if atLimit}<p role="alert">
      A plan can contain at most 300 sites. Remove a site before adding another.
    </p>{/if}
  <div
    bind:this={scrollContainer}
    class="picker-list"
    id={`${id}-list`}
    role="tabpanel"
    aria-labelledby={`${id}-tab-${tab}`}
    tabindex="0"
  >
    {#each sections as section (section.name)}
      <h4>{section.name}</h4>
      <ul>
        {#each section.facilities as facility (facility.id)}
          {@const preview = previews[facility.id]}
          <li data-preview-id={facility.id}>
            <button
              type="button"
              data-facility-id={facility.id}
              aria-describedby={`${id}-tier-${facility.id} ${id}-cost-${facility.id}${facility.prerequisites.length ? ` ${id}-requires-${facility.id}` : ''}`}
              disabled={atLimit || (!model.sites.length && !facility.is_port)}
              onclick={() => onadd(facility)}>{facility.name}</button
            >
            <span class="plan-chip" id={`${id}-tier-${facility.id}`}
              >T{facility.tier}</span
            >
            <span class="picker-cost" id={`${id}-cost-${facility.id}`}
              >{preview
                ? cpSummary(preview)
                : !model.sites.length && !facility.is_port
                  ? 'Choose a Primary Port first'
                  : previewErrors[facility.id]
                    ? 'CP preview unavailable'
                    : 'Evaluating CP…'}</span
            >
            {#if facility.prerequisites.length}
              <span
                class="picker-prerequisites"
                id={`${id}-requires-${facility.id}`}
                >Requires: {facility.prerequisites
                  .map((group) =>
                    group
                      .map(
                        (prerequisiteId) =>
                          facilities.find((item) => item.id === prerequisiteId)
                            ?.name ?? prerequisiteId,
                      )
                      .join(' or '),
                  )
                  .join('; ')}</span
              >
            {/if}
          </li>
        {/each}
      </ul>
    {/each}
    {#if !rows.length}<p>No matching facilities.</p>{/if}
  </div>
  {#if Object.keys(previewErrors).length}<p role="status">
      Cost previews are temporarily unavailable. Adding a build still evaluates
      the whole plan.
    </p>{/if}
</section>

<style>
  .facility-picker {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-height: 0;
    padding: 0.75rem;
    overflow: hidden;
    background: var(--color-panel);
  }
  .picker-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    margin-bottom: 0.75rem;
  }
  .picker-heading h3 {
    margin: 0;
    font-size: 0.95rem;
  }
  .picker-heading button {
    flex-shrink: 0;
    font-size: 0.75rem;
  }
  .picker-tabs {
    display: flex;
    gap: 0.3rem;
    margin-bottom: 0.65rem;
  }
  .picker-tabs button {
    flex: 1;
    padding: 0.4rem 0.6rem;
    font-size: 0.8rem;
  }
  .picker-tabs button[aria-selected='true'] {
    border-color: var(--color-signal);
    background: color-mix(in srgb, var(--color-signal) 15%, var(--color-panel));
  }
  .picker-search {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.8rem;
  }
  .picker-search input {
    flex: 1;
    min-width: 0;
    width: 100%;
  }
  p {
    margin: 0.6rem 0;
    color: var(--muted);
    font-size: 0.75rem;
  }
  .picker-list {
    flex: 1 1 auto;
    min-height: 0;
    max-height: 28rem;
    overflow-y: auto;
    overscroll-behavior: contain;
    scrollbar-gutter: stable;
    margin-top: 0.4rem;
  }
  h4 {
    margin: 0.7rem 0 0.3rem;
    color: var(--muted);
    font-size: 0.72rem;
    font-weight: 600;
  }
  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  li {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto minmax(5rem, max-content);
    align-items: center;
    gap: 0.25rem 0.4rem;
    padding: 0.2rem 0;
  }
  li button {
    padding: 0.35rem 0.4rem;
    font-size: 0.8rem;
    text-align: left;
    overflow-wrap: anywhere;
  }
  .plan-chip {
    white-space: nowrap;
  }
  .picker-cost {
    max-width: 11rem;
    padding-right: 0.3rem;
    font-size: 0.7rem;
    font-variant-numeric: tabular-nums;
    color: var(--muted);
    text-align: right;
  }
  .picker-prerequisites {
    grid-column: 1 / -1;
    padding: 0 0.4rem 0.25rem;
    color: var(--muted);
    font-size: 0.7rem;
  }
  @media (max-width: 400px) {
    li {
      grid-template-columns: minmax(0, 1fr) auto;
    }
    .picker-cost {
      grid-column: 1 / -1;
      justify-self: end;
    }
  }
</style>
