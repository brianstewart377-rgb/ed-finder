<script lang="ts">
  import {
    type PlanBodiesV1,
    type PlanFacilityV1,
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
  }: {
    location: PlannerLocation;
    facilities: PlanFacilityV1[];
    model: PlannerModel;
    bodies: PlanBodiesV1;
    onadd: (facility: PlanFacilityV1) => void;
    onclose: () => void;
  } = $props();
  let pageNumber = $state(0);
  let search = $state('');
  let previews = $state<Record<string, PlanStepV1>>({});
  let previewError = $state('');
  const matches = $derived(
    facilities.filter(
      (facility) =>
        facilityFitsLocation(facility, location) &&
        facility.name.toLowerCase().includes(search.toLowerCase()),
    ),
  );
  const visible = $derived(matches.slice(pageNumber * 6, (pageNumber + 1) * 6));
  const atLimit = $derived(model.sites.length >= MAX_SITES);

  // Preview the actual next step on the server. Pagination bounds requests;
  // catalogue constants never stand in for escalating or Primary Port costs.
  $effect(() => {
    const candidates = visible;
    const request = toPlanRequest(model, bodies);
    const bodyRef = location.body_ref;
    const controller = new AbortController();
    let active = true;
    previews = {};
    previewError = '';
    const full = atLimit;
    const timer = setTimeout(() => {
      if (!full) {
        void Promise.allSettled(
          candidates.map(async (facility) => {
            if (!request.sites.length && !facility.is_port) return;
            const siteId = `preview-${facility.id}`;
            try {
              const result = await evaluatePlanPreview(
                {
                  ...request,
                  sites: [
                    ...request.sites,
                    {
                      site_id: siteId,
                      facility_id: facility.id,
                      body_ref: bodyRef,
                      slot_kind: facility.allowed_location.includes('surface')
                        ? 'surface'
                        : 'orbital',
                      status: 'planned',
                      name: '',
                    },
                  ],
                },
                controller.signal,
              );
              const step = result.steps.find(
                (entry) => entry.site_id === siteId,
              );
              if (active && step)
                previews = { ...previews, [facility.id]: step };
            } catch {
              if (active)
                previewError =
                  'Cost previews are temporarily unavailable. Adding a build still evaluates the whole plan.';
            }
          }),
        );
      }
    }, 250);
    return () => {
      active = false;
      clearTimeout(timer);
      controller.abort();
    };
  });
</script>

<section class="facility-picker" aria-label={`Facilities for ${location.name}`}>
  <div class="picker-heading">
    <h3>Add on {location.name}</h3>
    <button type="button" onclick={onclose}>Close picker</button>
  </div>
  <label
    >Find a facility <input
      type="search"
      value={search}
      oninput={(event) => {
        search = event.currentTarget.value;
        pageNumber = 0;
      }}
    /></label
  >
  {#if !model.sites.length}<p>Choose a port for the Primary Port first.</p>{/if}
  {#if atLimit}<p role="alert">
      A plan can contain at most 300 sites. Remove a site before adding another.
    </p>{/if}
  {#each ['orbital', 'surface'] as kind (kind)}
    {#if visible.some((facility) => facility.allowed_location.includes(kind))}
      <h4>{kind === 'orbital' ? 'Orbital' : 'Surface'}</h4>
      <ul>
        {#each visible.filter( (facility) => facility.allowed_location.includes(kind) ) as facility (facility.id)}
          {@const preview = previews[facility.id]}
          <li>
            <button
              type="button"
              data-facility-id={facility.id}
              disabled={atLimit || (!model.sites.length && !facility.is_port)}
              onclick={() => onadd(facility)}
            >
              <strong>{facility.name}</strong>
              <span class="plan-chip">T{facility.tier}</span>
              {#if preview}<span class="picker-cost"
                  >Cost {preview.cost_t2} T2 / {preview.cost_t3} T3 · Earns {preview.reward_t2}
                  T2 / {preview.reward_t3} T3</span
                >
              {:else}<span class="picker-cost"
                  >{!model.sites.length && !facility.is_port
                    ? 'Choose a Primary Port first'
                    : previewError
                      ? 'CP preview unavailable'
                      : 'Evaluating CP…'}</span
                >{/if}
              <span class="picker-cost"
                >Requires: {facility.prerequisites.length
                  ? facility.prerequisites
                      .map((group) =>
                        group
                          .map(
                            (id) =>
                              facilities.find((item) => item.id === id)?.name ??
                              id,
                          )
                          .join(' or '),
                      )
                      .join('; ')
                  : 'None'}</span
              >
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  {/each}
  {#if previewError}<p role="status">{previewError}</p>{/if}
  {#if !matches.length}<p>No matching facilities.</p>{/if}
  <div class="picker-pages">
    <button
      type="button"
      disabled={pageNumber === 0}
      onclick={() => pageNumber--}>Previous facilities</button
    ><span>{pageNumber + 1} / {Math.max(1, Math.ceil(matches.length / 6))}</span
    ><button
      type="button"
      disabled={(pageNumber + 1) * 6 >= matches.length}
      onclick={() => pageNumber++}>More facilities</button
    >
  </div>
</section>
