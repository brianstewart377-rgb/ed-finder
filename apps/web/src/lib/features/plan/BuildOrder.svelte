<script lang="ts">
  import type { PlanEvaluationV1, PlanFacilityV1 } from '$lib/api';
  import {
    facilityFitsLocation,
    shortBodyName,
    type PlannerLocation,
  } from './locations';
  import {
    canMoveSite,
    isProtectedPrimary,
    PRIMARY_PORT_PROTECTION,
    type PlannerModel,
    type PlannerSite,
  } from './model';
  import { resultIcon, resultLabel, statusIcon } from './presentation';

  let {
    model,
    facilities,
    locations,
    systemName,
    evaluation,
    stale,
    selectedBody,
    selectedSite,
    filter,
    onfilter,
    onwhy,
    onmove,
    onupdate,
    onremove,
  }: {
    model: PlannerModel;
    facilities: PlanFacilityV1[];
    locations: PlannerLocation[];
    systemName: string;
    evaluation: PlanEvaluationV1 | null;
    stale: boolean;
    selectedBody: string | null;
    selectedSite: string | null;
    filter: string;
    onfilter: (filter: string) => void;
    onwhy: (id: string) => void;
    onmove: (id: string, direction: 'up' | 'down') => void;
    onupdate: (id: string, patch: Partial<PlannerSite>) => void;
    onremove: (id: string) => void;
  } = $props();
  const steps = $derived(
    new Map(evaluation?.steps.map((step) => [step.site_id, step]) ?? []),
  );
  const facilityById = $derived(
    new Map(facilities.map((facility) => [facility.id, facility])),
  );
  const locationById = $derived(
    new Map(locations.map((location) => [location.body_ref, location])),
  );
  const visible = $derived(
    model.sites.filter(
      (site) =>
        filter === 'All' ||
        (filter === 'body'
          ? site.body_ref === selectedBody
          : steps.get(site.site_id)?.result === filter),
    ),
  );
  function name(site: PlannerSite): string {
    return (
      site.name || facilityById.get(site.facility_id)?.name || site.facility_id
    );
  }
  function moveOptions(site: PlannerSite): PlannerLocation[] {
    const facility = facilityById.get(site.facility_id);
    return locations.filter(
      (location) =>
        (site.slot_kind !== 'surface' || location.is_landable !== false) &&
        (!facility || facilityFitsLocation(facility, location)),
    );
  }
  function facilityOptions(site: PlannerSite, index: number): PlanFacilityV1[] {
    const location = site.body_ref
      ? locationById.get(site.body_ref)
      : undefined;
    return facilities.filter(
      (facility) =>
        facility.allowed_location.includes(site.slot_kind) &&
        (index !== 0 || facility.is_port) &&
        (!location || facilityFitsLocation(facility, location)),
    );
  }
</script>

<section
  class="plan-pane build-order-pane"
  aria-labelledby="plan-order-title"
  data-plan-build-order
>
  <div class="pane-heading">
    <h2 id="plan-order-title">Build order</h2>
    <span>{model.sites.length} sites</span>
  </div>
  <div class="plan-filters" role="group" aria-label="Filter build order">
    {#each [['All', 'All'], ['BLOCKED', 'Blocked'], ['NEEDS_INFO', 'Needs info'], ['body', `On ${selectedBody ? shortBodyName(locationById.get(selectedBody)?.name ?? selectedBody, systemName) : 'selected body'}`]] as [value, label] (value)}
      <button
        type="button"
        aria-pressed={filter === value}
        disabled={value === 'body' && selectedBody === null}
        onclick={() => onfilter(value)}>{label}</button
      >
    {/each}
  </div>
  {#if !model.sites.length}<p class="plan-empty">
      Start with a Primary Port. Use + beside a body to choose a build.
    </p>{/if}
  <ol class="build-order-list">
    {#each visible as site (site.site_id)}
      {@const index = model.sites.indexOf(site)}
      {@const step = steps.get(site.site_id)}
      {@const facility = facilityById.get(site.facility_id)}
      {@const locked = isProtectedPrimary(model, site.site_id)}
      <li
        value={index + 1}
        class="build-step"
        class:selected={selectedSite === site.site_id}
        class:blocked={step?.result === 'BLOCKED'}
        id={`plan-step-${site.site_id}`}
        data-plan-site={site.site_id}
        tabindex="-1"
      >
        <div class="step-title">
          <span class="step-number">{index + 1}</span>
          <h3>{name(site)}</h3>
          {#if index === 0}<span class="plan-chip primary-label"
              >Primary Port</span
            >{/if}
        </div>
        <p class="plan-muted">
          {facility?.name ?? site.facility_id} · {site.slot_kind} · {site.body_ref &&
          locationById.has(site.body_ref)
            ? shortBodyName(locationById.get(site.body_ref)!.name, systemName)
            : 'Unplaced'}
        </p>
        <p class="step-state">
          <span
            ><span aria-hidden="true">{statusIcon[site.status]}</span>
            {site.status}</span
          >
          {#if step}<span
              class="plan-chip evaluation-value"
              class:stale
              data-result={step.result}
              >{resultIcon[step.result]} {resultLabel[step.result]}</span
            >{:else}<span class="plan-muted">Awaiting evaluation</span>{/if}
        </p>
        {#if step}
          <div class="step-budget" class:stale>
            <span class="plan-chip"
              >Cost {step.cost_t2} T2 / {step.cost_t3} T3</span
            >
            <span class="plan-chip"
              >Earns {step.reward_t2} T2 / {step.reward_t3} T3</span
            >
            {#if step.counted_port_number !== null}<span class="plan-chip"
                >port #{step.counted_port_number}</span
              >{/if}
            <span class:negative={step.t2_after < 0 || step.t3_after < 0}
              >After: {step.t2_after} T2 / {step.t3_after} T3</span
            >
          </div>
        {/if}
        <div class="step-actions">
          {#if locked}<p class="plan-muted">{PRIMARY_PORT_PROTECTION}</p>{:else}
            <button
              type="button"
              aria-label={`Move up ${name(site)}`}
              disabled={!canMoveSite(model, site.site_id, 'up')}
              onclick={() => onmove(site.site_id, 'up')}>↑ Move up</button
            >
            <button
              type="button"
              aria-label={`Move down ${name(site)}`}
              disabled={!canMoveSite(model, site.site_id, 'down')}
              onclick={() => onmove(site.site_id, 'down')}>↓ Move down</button
            >
          {/if}
          <button
            type="button"
            aria-label={`Why? ${name(site)}`}
            disabled={!step}
            onclick={() => onwhy(site.site_id)}>Why?</button
          >
        </div>
        <details class="step-edit">
          <summary>Edit {name(site)}</summary>
          <label
            >Facility <select
              aria-label={`Facility for step ${index + 1}`}
              value={site.facility_id}
              disabled={locked}
              onchange={(event) =>
                onupdate(site.site_id, {
                  facility_id: event.currentTarget.value,
                })}
            >
              {#if !facilityOptions(site, index).some((item) => item.id === site.facility_id)}<option
                  value={site.facility_id}
                  disabled
                  >{facility?.name ?? site.facility_id} — choose a valid facility</option
                >{/if}
              {#each facilityOptions(site, index) as option (option.id)}<option
                  value={option.id}>{option.name}</option
                >{/each}
            </select></label
          >
          <label
            >Name <input
              maxlength="64"
              aria-label={`Name for step ${index + 1}`}
              value={site.name}
              oninput={(event) =>
                onupdate(site.site_id, { name: event.currentTarget.value })}
            /></label
          >
          <label
            >Status <select
              aria-label={`Status for step ${index + 1}`}
              disabled={locked}
              value={site.status}
              onchange={(event) =>
                onupdate(site.site_id, {
                  status: event.currentTarget.value as PlannerSite['status'],
                })}
            >
              {#each ['planned', 'building', 'complete', 'demolished'] as status (status)}<option
                  value={status}>{status}</option
                >{/each}
            </select></label
          >
          <label
            >Move to body <select
              aria-label={`Body for step ${index + 1}`}
              disabled={locked}
              value={site.body_ref ?? ''}
              onchange={(event) =>
                onupdate(site.site_id, {
                  body_ref: event.currentTarget.value || null,
                })}
            >
              <option value="">Unplaced</option
              >{#each moveOptions(site) as location (location.body_ref)}<option
                  value={location.body_ref}
                  >{shortBodyName(location.name, systemName)}</option
                >{/each}
            </select></label
          >
          {#if locked}<p>{PRIMARY_PORT_PROTECTION}</p>{:else}<button
              type="button"
              class="remove-build"
              aria-label={`Remove ${name(site)}`}
              onclick={() => onremove(site.site_id)}>Remove build</button
            >{/if}
        </details>
      </li>
    {/each}
  </ol>
  {#if model.sites.length && !visible.length}<p>
      No builds match this filter.
    </p>{/if}
</section>
