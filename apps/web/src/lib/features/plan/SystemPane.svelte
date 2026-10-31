<script lang="ts">
  import type {
    PlanBodiesV1,
    PlanEvaluationV1,
    PlanFacilityV1,
  } from '$lib/api';
  import {
    buildBodyTree,
    flattenBodyTree,
    shortBodyName,
    type PlannerLocation,
  } from './locations';
  import {
    countUsedSlots,
    MAX_SITES,
    type PlannerModel,
    type PlannerSite,
  } from './model';
  import { statusIcon, resultIcon, resultLabel } from './presentation';
  import SlotEditor from './SlotEditor.svelte';
  import FacilityPicker from './FacilityPicker.svelte';

  let {
    bodies,
    model,
    systemName,
    facilities,
    evaluation,
    selectedBody,
    stale,
    onselectbody,
    onselectsite,
    onslot,
    onadd,
  }: {
    bodies: PlanBodiesV1;
    model: PlannerModel;
    systemName: string;
    facilities: PlanFacilityV1[];
    evaluation: PlanEvaluationV1 | null;
    selectedBody: string | null;
    stale: boolean;
    onselectbody: (ref: string) => void;
    onselectsite: (id: string) => void;
    onslot: (
      ref: string,
      kind: 'orbital' | 'surface',
      value: number | null,
    ) => void;
    onadd: (facility: PlanFacilityV1, ref: string) => void;
  } = $props();
  let showNames = $state(true);
  let picker = $state<string | null>(null);
  const tree = $derived(flattenBodyTree(buildBodyTree(bodies)));
  const facilityById = $derived(
    new Map(facilities.map((facility) => [facility.id, facility])),
  );
  const steps = $derived(
    new Map(evaluation?.steps.map((step) => [step.site_id, step]) ?? []),
  );
  const unplaced = $derived(
    model.sites.filter(
      (site) =>
        site.body_ref === null ||
        !tree.some((body) => body.body_ref === site.body_ref),
    ),
  );
  function features(location: PlannerLocation): string[] {
    if (location.belt)
      return [location.belt.ring_type, location.belt.reserve].filter(
        (item): item is string => !!item,
      );
    const body = location.body!;
    return [
      body.is_landable === true ? 'Landable' : null,
      body.has_rings ? 'Rings' : null,
      body.geological_signals ? `Geological ${body.geological_signals}` : null,
      body.biological_signals ? `Biological ${body.biological_signals}` : null,
      body.volcanism && body.volcanism.toLowerCase() !== 'no volcanism'
        ? `Volcanism: ${body.volcanism}`
        : null,
      body.terraforming_state &&
      body.terraforming_state.toLowerCase() !== 'not terraformable'
        ? `Terraformable: ${body.terraforming_state}`
        : null,
      body.atmosphere && body.atmosphere.toLowerCase() !== 'no atmosphere'
        ? `Atmosphere: ${body.atmosphere}`
        : null,
    ].filter((item): item is string => !!item);
  }
  function discSize(radius: number | null): number {
    return radius === null
      ? 24
      : Math.min(38, Math.max(16, 10 + Math.log10(Math.max(1, radius)) * 4));
  }
</script>

{#snippet tiles(sites: PlannerSite[])}
  <div class="plan-tiles">
    {#each sites as site (site.site_id)}
      {@const step = steps.get(site.site_id)}
      {@const facility = facilityById.get(site.facility_id)}
      <button
        type="button"
        class="plan-tile"
        class:blocked={step?.result === 'BLOCKED'}
        class:stale
        aria-label={`Step ${model.sites.indexOf(site) + 1}: ${site.status}, ${facility?.name ?? site.facility_id}${showNames && site.name ? `, ${site.name}` : ''}${site.status === 'planned' && step ? `, ${resultLabel[step.result]}` : ''}`}
        onclick={() => onselectsite(site.site_id)}
      >
        <span>{model.sites.indexOf(site) + 1}</span><span aria-hidden="true"
          >{statusIcon[site.status]}</span
        >
        <span
          >{facility?.name ??
            site.facility_id}{#if showNames && site.name}<small
              >{site.name}</small
            >{/if}</span
        >
        {#if facility}<span class="plan-chip">T{facility.tier}</span>{/if}
        {#if site.status === 'planned' && step}<span aria-hidden="true"
            >{resultIcon[step.result]}</span
          >{/if}
      </button>
    {/each}
  </div>
{/snippet}

<section class="plan-pane system-pane" aria-labelledby="plan-system-title">
  <div class="pane-heading">
    <h2 id="plan-system-title">System</h2>
    <button
      type="button"
      aria-pressed={showNames}
      onclick={() => (showNames = !showNames)}
      >{showNames ? 'Types + names' : 'Types only'}</button
    >
  </div>
  <p class="plan-muted">
    Slots are entered by you. Unknown totals are shown as ?.
  </p>
  <ul class="plan-body-tree">
    {#each tree as location (location.body_ref)}
      {@const used = countUsedSlots(model.sites, location.body_ref)}
      <li
        class="plan-body"
        class:selected={selectedBody === location.body_ref}
        class:child={location.depth > 0}
        style={`--body-depth: ${Math.min(location.depth, 4)}`}
        data-plan-body={location.body_ref}
      >
        <div class="body-heading">
          <span
            class="body-disc"
            class:star={location.body?.body_type?.toLowerCase() === 'star'}
            class:belt={location.kind === 'belt'}
            style={`--disc-size: ${discSize(location.radius_km)}px`}
            aria-hidden="true"
          ></span>
          <button
            type="button"
            class="body-name"
            aria-pressed={selectedBody === location.body_ref}
            onclick={() => onselectbody(location.body_ref)}
            >{shortBodyName(location.name, systemName)}</button
          >
          <button
            type="button"
            class="add-build"
            aria-label={`Add a build on ${location.name}`}
            aria-expanded={picker === location.body_ref}
            disabled={model.sites.length >= MAX_SITES}
            onclick={() => {
              onselectbody(location.body_ref);
              picker = picker === location.body_ref ? null : location.body_ref;
            }}>+</button
          >
        </div>
        <div class="body-features">
          {#each features(location) as feature, featureIndex (featureIndex)}<span
              class="plan-chip"
              title={feature}
              aria-label={feature}>{feature}</span
            >{/each}
        </div>
        <div class="body-slots">
          <SlotEditor
            label={location.name}
            kind="orbital"
            used={used.orbital_slots}
            value={model.slots[location.body_ref]?.orbital_slots ?? null}
            onchange={(value) => onslot(location.body_ref, 'orbital', value)}
          />
          {#if location.kind !== 'belt'}<SlotEditor
              label={location.name}
              kind="surface"
              used={used.surface_slots}
              value={model.slots[location.body_ref]?.surface_slots ?? null}
              disabled={location.is_landable === false}
              onchange={(value) => onslot(location.body_ref, 'surface', value)}
            />{/if}
        </div>
        {@render tiles(
          model.sites.filter((site) => site.body_ref === location.body_ref),
        )}
        {#if picker === location.body_ref}
          <FacilityPicker
            {location}
            {facilities}
            {model}
            {bodies}
            onclose={() => (picker = null)}
            onadd={(facility) => {
              onadd(facility, location.body_ref);
              picker = null;
            }}
          />
        {/if}
      </li>
    {/each}
  </ul>
  {#if !tree.length}<p>No bodies are recorded for this system.</p>{/if}
  {#if unplaced.length}<h3>Unplaced</h3>
    <p class="plan-muted">
      Choose a recorded location in the build's edit row.
    </p>
    {@render tiles(unplaced)}{/if}
  {#if model.sites.length >= MAX_SITES}<p role="status">
      300-site limit reached. Remove a site before adding another.
    </p>{/if}
</section>
