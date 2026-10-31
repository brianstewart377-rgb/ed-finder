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
  import { resultLabel } from './presentation';
  import PlanIcon from './PlanIcon.svelte';
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
    hidden = false,
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
    hidden?: boolean;
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
  function features(
    location: PlannerLocation,
  ): { marker: string; label: string }[] {
    if (location.belt)
      return [location.belt.ring_type, location.belt.reserve]
        .filter((item): item is string => !!item)
        .map((label) => ({ marker: label[0], label }));
    const body = location.body!;
    return [
      body.is_landable === true ? { marker: 'L', label: 'Landable' } : null,
      body.has_rings ? { marker: '◎', label: 'Rings' } : null,
      body.geological_signals
        ? {
            marker: `G${body.geological_signals}`,
            label: `Geological ${body.geological_signals}`,
          }
        : null,
      body.biological_signals
        ? {
            marker: `B${body.biological_signals}`,
            label: `Biological ${body.biological_signals}`,
          }
        : null,
      body.volcanism && body.volcanism.toLowerCase() !== 'no volcanism'
        ? { marker: 'V', label: `Volcanism: ${body.volcanism}` }
        : null,
      body.terraforming_state &&
      body.terraforming_state.toLowerCase() !== 'not terraformable'
        ? { marker: 'T', label: `Terraformable: ${body.terraforming_state}` }
        : null,
      body.atmosphere && body.atmosphere.toLowerCase() !== 'no atmosphere'
        ? { marker: 'A', label: `Atmosphere: ${body.atmosphere}` }
        : null,
    ].filter((item): item is { marker: string; label: string } => !!item);
  }
  function discSize(radius: number | null): number {
    return radius === null
      ? 24
      : Math.min(28, Math.max(16, 10 + Math.log10(Math.max(1, radius)) * 4));
  }
</script>

{#snippet tiles(sites: PlannerSite[])}
  <div class="plan-tiles">
    {#each sites as site (site.site_id)}
      {@const siteIndex = model.sites.indexOf(site)}
      {@const step = steps.get(site.site_id)}
      {@const facility = facilityById.get(site.facility_id)}
      <button
        type="button"
        class="plan-tile"
        class:blocked={step?.result === 'BLOCKED'}
        class:stale
        title={`${facility?.name ?? site.facility_id}${showNames && site.name ? ` · ${site.name}` : ''}`}
        aria-label={`Step ${siteIndex + 1}: ${site.status}, ${facility?.name ?? site.facility_id}${showNames && site.name ? `, ${site.name}` : ''}${site.status === 'planned' && step ? `, ${resultLabel[step.result]}` : ''}${siteIndex === 0 ? ', Primary Port' : ''}`}
        onclick={() => onselectsite(site.site_id)}
      >
        <span class="tile-number"
          >{#if siteIndex === 0}<span aria-hidden="true"
              >★
            </span>{/if}{siteIndex + 1}</span
        ><PlanIcon kind={site.status} />
        <span class="tile-label"
          >{facility?.name ??
            site.facility_id}{#if showNames && site.name}<small>
              · {site.name}</small
            >{/if}</span
        >
        {#if facility}<span class="plan-chip">T{facility.tier}</span>{/if}
        {#if site.status === 'planned' && step}<PlanIcon
            kind={step.result}
          />{/if}
      </button>
    {/each}
  </div>
{/snippet}

<section
  class="plan-pane system-pane"
  aria-labelledby="plan-system-title"
  {hidden}
>
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
        <div class="body-heading compact-body-row">
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
            title={location.name}
            aria-pressed={selectedBody === location.body_ref}
            onclick={() => onselectbody(location.body_ref)}
            >{shortBodyName(location.name, systemName)}</button
          >
          <div class="body-features">
            {#each features(location) as feature, featureIndex (featureIndex)}<span
                class="body-feature"
                role="img"
                title={feature.label}
                aria-label={feature.label}>{feature.marker}</span
              >{/each}
          </div>
          <div class="body-slots">
            {#if !hidden}
              <SlotEditor
                label={location.name}
                kind="orbital"
                used={used.orbital_slots}
                value={model.slots[location.body_ref]?.orbital_slots ?? null}
                onchange={(value) =>
                  onslot(location.body_ref, 'orbital', value)}
              />
              {#if location.kind !== 'belt'}<SlotEditor
                  label={location.name}
                  kind="surface"
                  used={used.surface_slots}
                  value={model.slots[location.body_ref]?.surface_slots ?? null}
                  disabled={location.is_landable === false}
                  onchange={(value) =>
                    onslot(location.body_ref, 'surface', value)}
                />{/if}
            {/if}
          </div>
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

<style>
  .plan-body-tree {
    margin: 0.5rem 0 0;
  }
  .plan-body {
    position: relative;
    margin: 2px 0 2px calc(var(--body-depth) * 0.45rem);
    padding: 0 0 0 0.3rem;
    border-left: 1px solid transparent;
  }
  .plan-body.child {
    border-left-color: var(--line);
  }
  .plan-body.child::before {
    content: '';
    position: absolute;
    width: 0.3rem;
    border-top: 1px solid var(--line);
    top: 16px;
    left: 0;
  }
  .plan-body.selected {
    background: color-mix(in srgb, var(--color-cyan) 4%, var(--color-panel));
    border-left-color: var(--color-cyan);
    border-radius: 0.25rem;
  }
  .compact-body-row {
    display: flex;
    align-items: center;
    flex-wrap: nowrap;
    gap: 0.25rem;
    min-width: 0;
    height: 32px;
  }
  .body-disc {
    display: inline-block;
    width: var(--disc-size);
    height: var(--disc-size);
    flex: 0 0 var(--disc-size);
    border-radius: 50%;
    background: radial-gradient(
      circle at 30% 25%,
      var(--color-cyan),
      #365271 65%,
      #192d47
    );
    border: 1px solid var(--color-cyan);
  }
  .body-disc.star {
    background: radial-gradient(
      circle at 35% 30%,
      #fff3cb,
      #edb257 50%,
      #b85926
    );
    border-color: #edb257;
  }
  .body-disc.belt {
    background: repeating-radial-gradient(
      ellipse,
      var(--line) 0 2px,
      var(--muted) 3px 4px,
      transparent 5px 6px
    );
    transform: rotate(-25deg) scaleY(0.65);
    border: 2px dotted var(--muted);
  }
  :global(.plan-workspace) .body-name {
    min-width: 0;
    flex: 1;
    padding: 0.2rem 0;
    border: 0;
    background: transparent;
    text-align: left;
    font-size: 0.75rem;
    font-weight: 650;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .body-features,
  .body-slots {
    display: flex;
    flex: 0 0 auto;
    align-items: center;
    flex-wrap: nowrap;
    gap: 0.2rem;
  }
  .body-feature {
    color: var(--muted);
    font-size: 0.65rem;
    line-height: 1;
    white-space: nowrap;
  }
  :global(.plan-workspace) .add-build {
    flex: 0 0 24px;
    width: 24px;
    height: 24px;
    padding: 0;
    font-size: 1rem;
    line-height: 1;
  }
  .plan-tiles {
    display: flex;
    flex-wrap: wrap;
    gap: 2px 4px;
    padding-left: 1.8rem;
  }
  :global(.plan-workspace) .plan-tile {
    display: inline-flex;
    align-items: center;
    flex-wrap: nowrap;
    gap: 0.2rem;
    min-width: 0;
    max-width: calc(50% - 2px);
    height: 24px;
    padding: 0 0.3rem;
    text-align: left;
    font-size: 0.65rem;
    white-space: nowrap;
  }
  .tile-number {
    flex-shrink: 0;
    font-variant-numeric: tabular-nums;
  }
  .tile-label {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .plan-tile small {
    display: inline;
    color: var(--muted);
    font-size: inherit;
  }
  .plan-tile .plan-chip {
    flex-shrink: 0;
    padding: 0 0.15rem;
    font-size: 0.6rem;
    line-height: 1.25;
  }
  @media (max-width: 600px) {
    .plan-body {
      margin-left: calc(var(--body-depth) * 0.3rem);
    }
    .compact-body-row {
      gap: 0.2rem;
    }
    .body-features {
      gap: 0.12rem;
    }
    .body-feature {
      font-size: 0.6rem;
    }
    .plan-tiles {
      padding-left: 1rem;
    }
    :global(.plan-workspace) .plan-tile {
      max-width: 100%;
    }
  }
</style>
