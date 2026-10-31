<script lang="ts">
  import { createQuery } from '@tanstack/svelte-query';
  import { onDestroy, tick } from 'svelte';
  import { resolve } from '$app/paths';
  import {
    ApiError,
    evaluateV3Plan,
    getV3PlanCatalogue,
    listV3PlanBodies,
    getPlanSystem,
    type PlanEvaluationV1,
    type PlanFacilityV1,
    type PlanInvalidV1,
  } from '$lib/api';
  import type { Id64 } from '$lib/domain/id64';
  import { colonyProjects } from '$lib/persistence/stores';
  import { resolvePlanLocations } from './locations';
  import {
    emptyPlan,
    recordToPlanner,
    plannerToRecord,
    findPlannerProject,
    toPlanRequest,
    addSite,
    insertSiteBefore,
    moveSite,
    removeSite,
    updateSite,
    setSlotCount,
    findFreeLocation,
    exportPlan,
    importPlan,
    replacePlan,
    rejectInvalidLocations,
    unplaceMissingLocations,
    MAX_SITES,
    MAX_IMPORT_BYTES,
    type PlannerModel,
    type PlannerSite,
  } from './model';
  import SystemPane from './SystemPane.svelte';
  import BuildOrder from './BuildOrder.svelte';
  import SummaryPane from './SummaryPane.svelte';
  import WhyDrawer from './WhyDrawer.svelte';
  import './plan.css';

  let { systemId }: { systemId: Id64 } = $props();
  const catalogue = createQuery(() => ({
    queryKey: ['ed-finder', 'plan-catalogue'],
    queryFn: ({ signal }) => getV3PlanCatalogue(signal),
    staleTime: Infinity,
    gcTime: Infinity,
    retry: false,
  }));
  const bodies = createQuery(() => ({
    queryKey: ['ed-finder', 'plan-bodies', systemId],
    queryFn: ({ signal }) => listV3PlanBodies(systemId, signal),
    retry: false,
  }));
  const identity = createQuery(() => ({
    queryKey: ['ed-finder', 'plan-system', systemId],
    queryFn: ({ signal }) => getPlanSystem(systemId, signal),
    staleTime: Infinity,
    retry: false,
  }));
  const record = $derived(
    findPlannerProject($colonyProjects.value.state.projects, systemId),
  );
  const model = $derived(
    record ? recordToPlanner(record) : emptyPlan(systemId),
  );
  const systemName = $derived(
    identity.data?.name ??
      (typeof record?.system_name === 'string'
        ? record.system_name
        : `System ${systemId}`),
  );
  const facilities = $derived(catalogue.data?.facilities ?? []);
  const locations = $derived(
    bodies.data ? resolvePlanLocations(bodies.data) : [],
  );
  const older = $derived(
    record?.build_plan_placements.filter(
      (item) => item.schema !== 'cpe_site_v1',
    ) ?? [],
  );
  let evaluation = $state<PlanEvaluationV1 | null>(null);
  let evaluatedRequest = $state('');
  let evaluationError = $state('');
  let actionError = $state('');
  let pending = $state(false);
  let announcement = $state('');
  let view = $state<'now' | 'after_plan'>('after_plan');
  let selectedBody = $state<string | null>(null);
  let selectedSite = $state<string | null>(null);
  let whySite = $state<string | null>(null);
  let filter = $state('All');
  let fileInput = $state<HTMLInputElement>();
  let active = true;
  onDestroy(() => {
    active = false;
  });
  const request = $derived(
    bodies.data ? toPlanRequest(model, bodies.data) : null,
  );
  const requestKey = $derived(request ? JSON.stringify(request) : '');
  const stale = $derived(requestKey !== evaluatedRequest || !!evaluationError);
  const whyStep = $derived(
    evaluation?.steps.find((step) => step.site_id === whySite),
  );
  const whyBuild = $derived(
    model.sites.find((site) => site.site_id === whySite),
  );

  $effect(() => {
    const snapshot = request;
    const fingerprint = requestKey;
    if (!snapshot || !$colonyProjects.hydrated) return;
    if (snapshot.sites.length === 0) {
      pending = false;
      evaluationError = '';
      announcement = '';
      return;
    }
    const controller = new AbortController();
    let current = true;
    pending = true;
    evaluationError = '';
    announcement = '';
    const timer = setTimeout(() => {
      void evaluateV3Plan(snapshot, controller.signal)
        .then((result) => {
          if (!current) return;
          evaluation = result;
          evaluatedRequest = fingerprint;
          announcement = `${result.summary.BLOCKED} blocked steps. ${result.summary.NEEDS_INFO} steps need information.`;
        })
        .catch((error: unknown) => {
          if (!current) return;
          const invalid =
            error instanceof ApiError && error.status === 400
              ? (error.body as PlanInvalidV1)
              : null;
          evaluationError =
            invalid?.error === 'plan_invalid' && Array.isArray(invalid.issues)
              ? invalid.issues.map((issue) => issue.message).join(' ')
              : 'The plan could not be evaluated. Try again shortly.';
        })
        .finally(() => {
          if (current) pending = false;
        });
    }, 250);
    return () => {
      current = false;
      clearTimeout(timer);
      controller.abort();
    };
  });

  function change(action: (current: PlannerModel) => PlannerModel): void {
    try {
      const next = action(model);
      const projects = $colonyProjects.value;
      const nextRecord = plannerToRecord(next, record, { systemName });
      const saved = colonyProjects.set({
        ...projects,
        state: {
          ...projects.state,
          projects: { ...projects.state.projects, [nextRecord.id]: nextRecord },
        },
      });
      actionError = saved
        ? ''
        : 'This browser could not save the plan. Export a copy before leaving.';
    } catch (error) {
      actionError =
        error instanceof Error
          ? error.message
          : 'The plan could not be changed.';
    }
  }
  function makeSite(facility: PlanFacilityV1, ref: string | null): PlannerSite {
    return {
      schema: 'cpe_site_v1',
      site_id: crypto.randomUUID(),
      facility_id: facility.id,
      body_ref: ref,
      slot_kind: facility.allowed_location.includes('surface')
        ? 'surface'
        : 'orbital',
      status: 'planned',
      name: '',
    };
  }
  function add(facility: PlanFacilityV1, ref: string): void {
    const site = makeSite(facility, ref);
    change((current) => addSite(current, site));
    selectedSite = site.site_id;
  }
  function isPort(facilityId: string): boolean {
    return facilities.some(
      (facility) => facility.id === facilityId && facility.is_port,
    );
  }
  function remove(id: string): void {
    change((current) => {
      if (current.sites[0]?.site_id === id && !catalogue.data)
        throw new Error(
          'Wait for the facility list to load before removing the Primary Port.',
        );
      return removeSite(current, id, isPort);
    });
  }
  async function jumpToStep(id: string): Promise<void> {
    selectedSite = id;
    filter = 'All';
    await tick();
    document.getElementById(`plan-step-${id}`)?.focus();
  }
  function showWhy(id: string): void {
    selectedSite = id;
    filter = 'All';
    whySite = id;
  }
  async function selectBody(ref: string): Promise<void> {
    selectedBody = ref;
    await tick();
    const row = [
      ...document.querySelectorAll<HTMLElement>('[data-plan-body]'),
    ].find((element) => element.dataset.planBody === ref);
    row?.querySelector<HTMLElement>('.body-name')?.focus();
  }
  function insertPayer(facilityId: string): void {
    const facility = facilities.find((item) => item.id === facilityId);
    if (!facility || !whySite) return;
    const before = whySite;
    change((current) =>
      insertSiteBefore(
        current,
        makeSite(facility, findFreeLocation(current, locations, facility)),
        before,
      ),
    );
  }
  function download(): void {
    const url = URL.createObjectURL(
      new Blob([exportPlan(model)], { type: 'application/json' }),
    );
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `colony-plan-${systemId}.json`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function upload(event: Event): Promise<void> {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    try {
      if (file.size > MAX_IMPORT_BYTES)
        throw new Error('Plan files must be no larger than 2 MB.');
      const text = await file.text();
      if (!active) return;
      // Validate the entire file before presenting a replacement confirmation.
      let candidate = importPlan(text, systemId, { confirmOtherSystem: true });
      const source = (JSON.parse(text) as { system_id64: string }).system_id64;
      if (!bodies.data)
        throw new Error(
          'Wait for the system bodies to load before importing a plan.',
        );
      if (candidate.sites[0] && !isPort(candidate.sites[0].facility_id))
        throw new Error(
          "This plan's first site is not a port, so it cannot be the Primary Port.",
        );
      if (source !== systemId) {
        if (
          !window.confirm(
            `This file belongs to system ${source}. Import its sites and slot counts into ${systemName} (${systemId})? Missing locations will become Unplaced. A completed Primary Port without a location here will stay editable until you give it one.`,
          )
        )
          return;
        candidate = unplaceMissingLocations(candidate, bodies.data);
      }
      rejectInvalidLocations(candidate, bodies.data);
      if (
        !window.confirm(
          `Replace this system's planner sites and slot counts with ${candidate.sites.length} imported sites? Older plan items will be kept.`,
        )
      )
        return;
      change((current) => replacePlan(current, candidate));
    } catch (error) {
      actionError =
        error instanceof Error
          ? error.message
          : 'The plan file could not be read.';
    }
  }
</script>

<main class="plan-workspace product-page">
  <header class="plan-header">
    <nav aria-label="Planner breadcrumbs">
      <a href={resolve('/explore')}>Explore</a><span aria-hidden="true">›</span
      ><a href={resolve(`/inspect?system=${systemId}`)}>Inspect</a><span
        aria-hidden="true">›</span
      ><span aria-current="page">Plan</span>
    </nav>
    <div class="plan-title">
      <div>
        <p class="eyebrow">Colony planner</p>
        <h1>{systemName}</h1>
        <p class="plan-muted">
          ID64 <code>{systemId}</code> · Kept in this browser
        </p>
      </div>
      <div class="plan-header-actions">
        <div class="plan-view" role="group" aria-label="Points view">
          <button
            type="button"
            aria-pressed={view === 'now'}
            onclick={() => (view = 'now')}>Now</button
          ><button
            type="button"
            aria-pressed={view === 'after_plan'}
            onclick={() => (view = 'after_plan')}>After the plan</button
          >
        </div>
        <button type="button" onclick={download}>Export plan</button><button
          type="button"
          onclick={() => fileInput?.click()}>Import plan</button
        ><input
          bind:this={fileInput}
          type="file"
          accept="application/json,.json"
          aria-label="Import plan file"
          class="plan-file-input"
          onchange={upload}
        />
      </div>
    </div>
  </header>
  <p class="plan-sr-only" aria-live="polite" aria-atomic="true">
    {announcement}
  </p>
  {#if actionError}<p class="plan-error" role="alert">{actionError}</p>{/if}
  {#if $colonyProjects.diagnostic}<p class="plan-error" role="alert">
      Browser storage: {$colonyProjects.diagnostic.detail}. Export your plan to
      keep a copy.
    </p>{/if}
  {#if bodies.isPending || catalogue.isPending}<p role="status">
      Loading planner catalogue and system bodies…
    </p>
  {:else if bodies.isError || catalogue.isError}<section class="plan-pane">
      <h2>Planner data unavailable</h2>
      <p role="alert">The catalogue or system bodies could not be loaded.</p>
      <button
        type="button"
        onclick={() => {
          void bodies.refetch();
          void catalogue.refetch();
        }}>Try again</button
      >
    </section>
  {:else if bodies.data}
    <div class="plan-columns">
      <SystemPane
        bodies={bodies.data}
        {model}
        {systemName}
        {facilities}
        {evaluation}
        {selectedBody}
        {stale}
        onselectbody={(ref) => (selectedBody = ref)}
        onselectsite={showWhy}
        onslot={(ref, kind, value) =>
          change((current) => setSlotCount(current, ref, kind, value))}
        onadd={add}
      />
      <BuildOrder
        {model}
        {facilities}
        {locations}
        {systemName}
        {evaluation}
        {stale}
        {selectedBody}
        {selectedSite}
        {filter}
        onfilter={(value) => (filter = value)}
        onwhy={showWhy}
        onmove={(id, direction) =>
          change((current) => moveSite(current, id, direction))}
        onupdate={(id, patch) =>
          change((current) => updateSite(current, id, patch))}
        onremove={remove}
      />
      <SummaryPane
        {model}
        {facilities}
        {locations}
        {evaluation}
        {view}
        error={evaluationError}
        {pending}
        {stale}
        onstep={jumpToStep}
        onbody={selectBody}
        onwhy={showWhy}
      />
    </div>
  {/if}
  {#if older.length}<details class="plan-pane older-items">
      <summary>Older plan items (read-only) · {older.length}</summary>
      <ul>
        {#each older as item, index (index)}<li>
            <strong>Older item {index + 1}</strong>
            <pre>{JSON.stringify(item, null, 2)}</pre>
          </li>{/each}
      </ul>
    </details>{/if}
  {#if whyStep && whyBuild && evaluation}
    <WhyDrawer
      step={whyStep}
      index={model.sites.indexOf(whyBuild)}
      name={whyBuild.name ||
        facilities.find((item) => item.id === whyBuild.facility_id)?.name ||
        whyBuild.facility_id}
      {evaluation}
      {facilities}
      {stale}
      onclose={() => (whySite = null)}
      oninsert={insertPayer}
      canInsert={!stale &&
        model.sites.length < MAX_SITES &&
        model.sites.indexOf(whyBuild) > 0}
    />
  {/if}
</main>
