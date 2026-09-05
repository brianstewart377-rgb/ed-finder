<script lang="ts">
  import { createQuery } from '@tanstack/svelte-query';
  import { resolve } from '$app/paths';
  import { tick } from 'svelte';
  import { ArrowRight, LocateFixed, Search, Sparkles } from '@lucide/svelte';
  import {
    autocompleteSystems,
    searchExploreSystems,
    type AutocompleteSystem,
    type ExploreSearchRequest,
    type ExploreSystem,
  } from '$lib/api/client';
  import { queryKeys } from '$lib/api/query';
  import { parseId64, type Id64 } from '$lib/domain/id64';
  import { usePersistenceContext } from '$lib/persistence/context';
  import SpatialCanvas from '$lib/spatial/SpatialCanvas.svelte';
  import type { RuntimeEvent, SpatialTarget } from '$lib/spatial/contracts';
  import { buildExploreGalaxyScene } from '$lib/spatial/explore-scene';
  import WorkspaceHeader from '$lib/components/WorkspaceHeader.svelte';

  const { selectedSystem } = usePersistenceContext();
  let query = $state('');
  let activeSuggestion = $state(0);
  let autocompleteOpen = $state(false);
  let anchor = $state<AutocompleteSystem | null>(null);
  let selectionRevision = $state(0);
  let focusRevision = $state(0);
  let focusTarget = $state<SpatialTarget | null>(null);
  let lastPickedId64 = $state<Id64 | null>(null);
  let resultList = $state<HTMLDivElement>();
  let focusedResultSet = '';

  const normalizedQuery = $derived(query.trim());
  const suggestions = createQuery(() => ({
    queryKey: queryKeys.autocomplete(normalizedQuery.toLocaleLowerCase()),
    queryFn: ({ signal }) => autocompleteSystems(normalizedQuery, signal),
    enabled: normalizedQuery.length >= 2,
    staleTime: 60_000,
  }));
  const suggestionRows = $derived(suggestions.data?.results ?? []);

  const searchRequest = $derived.by((): ExploreSearchRequest => {
    if (
      anchor &&
      typeof anchor.x === 'number' &&
      typeof anchor.y === 'number' &&
      typeof anchor.z === 'number'
    ) {
      return {
        reference_coords: { x: anchor.x, y: anchor.y, z: anchor.z },
        filters: { distance: { min: 0, max: 500 }, economy: 'any' },
        sort_by: 'distance',
        size: 24,
        from: 0,
      };
    }
    return { galaxy_wide: true, sort_by: 'development', size: 24, from: 0 };
  });
  const results = createQuery(() => ({
    queryKey: queryKeys.explore(searchRequest),
    queryFn: ({ signal }) => searchExploreSystems(searchRequest, signal),
  }));
  const systems = $derived(results.data?.results ?? []);
  const scene = $derived(
    buildExploreGalaxyScene(
      systems,
      $selectedSystem.value,
      results.dataUpdatedAt + selectionRevision,
    ),
  );

  $effect(() => {
    if (!anchor || !results.data || results.isFetching) return;
    const resultSet = `${anchor.id64}:${results.dataUpdatedAt}`;
    if (resultSet === focusedResultSet) return;
    focusedResultSet = resultSet;
    void tick().then(() =>
      resultList
        ?.querySelector<HTMLButtonElement>('[data-result-select]')
        ?.focus({ preventScroll: true }),
    );
  });

  function chooseSuggestion(hit: AutocompleteSystem): void {
    anchor = hit;
    query = hit.name;
    autocompleteOpen = false;
    selectedSystem.set(hit.id64);
    selectionRevision += 1;
    focusTarget = { kind: 'system', systemId64: hit.id64 };
    focusRevision += 1;
  }

  function handleQueryInput(event: Event): void {
    anchor = null;
    autocompleteOpen =
      (event.currentTarget as HTMLInputElement).value.trim().length >= 2;
    activeSuggestion = 0;
  }

  function handleQueryKeydown(event: KeyboardEvent): void {
    if (!autocompleteOpen || !suggestionRows.length) {
      if (event.key === 'ArrowDown' && suggestionRows.length) {
        autocompleteOpen = true;
        event.preventDefault();
      }
      return;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      activeSuggestion = (activeSuggestion + 1) % suggestionRows.length;
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      activeSuggestion =
        (activeSuggestion - 1 + suggestionRows.length) % suggestionRows.length;
    } else if (event.key === 'Home') {
      event.preventDefault();
      activeSuggestion = 0;
    } else if (event.key === 'End') {
      event.preventDefault();
      activeSuggestion = suggestionRows.length - 1;
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const hit = suggestionRows[activeSuggestion];
      if (hit) chooseSuggestion(hit);
    } else if (event.key === 'Escape') {
      autocompleteOpen = false;
    }
  }

  function selectResult(system: ExploreSystem): void {
    selectedSystem.set(system.id64);
    selectionRevision += 1;
    focusTarget = { kind: 'system', systemId64: system.id64 };
    focusRevision += 1;
  }

  function handleRuntimeEvent(event: RuntimeEvent): void {
    if (event.type !== 'TARGET_PICKED' || event.target?.kind !== 'system')
      return;
    try {
      const picked = parseId64(event.target.systemId64);
      selectedSystem.set(picked);
      lastPickedId64 = picked;
      selectionRevision += 1;
    } catch {
      // Renderer events fail closed if an adapter ever emits a non-Id64 target.
    }
  }

  const population = (value: number | null | undefined) =>
    typeof value === 'number' && value > 0
      ? new Intl.NumberFormat(undefined, { notation: 'compact' }).format(value)
      : null;
</script>

<svelte:head>
  <title>Explore — ED-Finder V3</title>
  <meta
    name="description"
    content="Discover and inspect Elite Dangerous systems"
  />
</svelte:head>

<WorkspaceHeader />
<main class="explore-page product-page">
  <header class="product-intro">
    <div>
      <p class="eyebrow">Explore · Finder</p>
      <h1>Chart a promising system.</h1>
    </div>
    <p>
      Search the catalogue, compare real nearby results, and carry one exact
      system into Inspect.
    </p>
  </header>

  <section class="finder-bar" aria-labelledby="finder-title">
    <div>
      <p class="eyebrow">Discovery anchor</p>
      <h2 id="finder-title">Find systems near a known star</h2>
    </div>
    <div class="combobox-wrap">
      <label for="system-search">System name</label>
      <div class="search-control">
        <Search aria-hidden="true" size={19} />
        <input
          id="system-search"
          type="search"
          placeholder="Try Sol, Achenar, Lave…"
          autocomplete="off"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={autocompleteOpen && normalizedQuery.length >= 2}
          aria-controls="system-suggestions"
          aria-activedescendant={autocompleteOpen &&
          suggestionRows[activeSuggestion]
            ? `suggestion-${activeSuggestion}`
            : undefined}
          bind:value={query}
          oninput={handleQueryInput}
          onfocus={() => (autocompleteOpen = normalizedQuery.length >= 2)}
          onkeydown={handleQueryKeydown}
        />
      </div>
      {#if autocompleteOpen && normalizedQuery.length >= 2}
        <div
          id="system-suggestions"
          class="suggestions"
          role="listbox"
          aria-label="System suggestions"
        >
          {#if suggestions.isPending}
            <p role="status">Searching catalogue…</p>
          {:else if suggestions.isError}
            <div role="alert">
              <p>Typeahead is unavailable.</p>
              <button type="button" onclick={() => suggestions.refetch()}
                >Retry</button
              >
            </div>
          {:else if suggestionRows.length === 0}
            <p>No matching systems.</p>
          {:else}
            {#each suggestionRows as hit, index (hit.id64)}
              <button
                id={`suggestion-${index}`}
                type="button"
                role="option"
                aria-selected={index === activeSuggestion}
                class:active={index === activeSuggestion}
                onmousedown={(event) => event.preventDefault()}
                onclick={() => chooseSuggestion(hit)}
              >
                <span>{hit.name}</span><code>{hit.id64}</code>
              </button>
            {/each}
          {/if}
        </div>
      {/if}
    </div>
  </section>

  <div class="explore-grid">
    <section
      class="results-panel"
      aria-labelledby="results-title"
      aria-busy={results.isFetching}
    >
      <div class="panel-heading">
        <div>
          <p class="eyebrow">Catalogue results</p>
          <h2 id="results-title">
            {anchor ? `Near ${anchor.name}` : 'Galaxy-wide shortlist'}
          </h2>
        </div>
        {#if results.data}<span
            >{results.data.count ?? systems.length} shown</span
          >{/if}
      </div>

      {#if results.isPending}
        <div class="state-card" role="status">
          <Sparkles aria-hidden="true" />
          <p>Building a real-system shortlist…</p>
        </div>
      {:else if results.isError}
        <div class="state-card error" role="alert">
          <p>Discovery results could not be loaded.</p>
          <button
            class="secondary-button"
            type="button"
            onclick={() => results.refetch()}>Retry search</button
          >
        </div>
      {:else if systems.length === 0}
        <div class="state-card">
          <p>No systems match this discovery area. Choose another anchor.</p>
        </div>
      {:else}
        <div
          class="result-list"
          bind:this={resultList}
          role="list"
          aria-label="System results"
        >
          {#each systems as system (system.id64)}
            <article
              class:selected={$selectedSystem.value === system.id64}
              data-system-result={system.id64}
              role="listitem"
            >
              <button
                class="result-select"
                type="button"
                data-result-select
                aria-pressed={$selectedSystem.value === system.id64}
                onclick={() => selectResult(system)}
              >
                <span class="result-title"
                  ><strong>{system.name ?? `System ${system.id64}`}</strong
                  ><code>{system.id64}</code></span
                >
                <span class="result-facts">
                  {#if system.distance != null}<span
                      >{system.distance.toFixed(1)} ly</span
                    >{/if}
                  {#if system.primaryEconomy}<span>{system.primaryEconomy}</span
                    >{/if}
                  {#if population(system.population)}<span
                      >{population(system.population)} population</span
                    >{/if}
                  {#if system.main_star_type}<span
                      >{system.main_star_type} star</span
                    >{/if}
                </span>
              </button>
              <a
                class="inspect-link"
                href={resolve(`/inspect?system=${system.id64}`)}
                aria-label={`Inspect ${system.name ?? system.id64}`}
              >
                Inspect <ArrowRight aria-hidden="true" size={16} />
              </a>
            </article>
          {/each}
        </div>
      {/if}
    </section>

    <section class="map-panel" aria-labelledby="map-title">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">Galaxy presentation</p>
          <h2 id="map-title">Spatial results</h2>
        </div>
        <span><LocateFixed aria-hidden="true" size={15} /> canonical ly</span>
      </div>
      <p class="map-note">
        Cyan signals are catalogue systems. The amber reticle marks your active
        selection.
      </p>
      <SpatialCanvas
        {scene}
        {focusTarget}
        {focusRevision}
        onRuntimeEvent={handleRuntimeEvent}
      />
      <p
        class="selection-status"
        aria-live="polite"
        data-last-picked-id64={lastPickedId64}
      >
        {#if lastPickedId64}Spatial pick selected <code>{lastPickedId64}</code
          >.{:else if $selectedSystem.value}Active system <code
            >{$selectedSystem.value}</code
          >.{:else}Select a result to focus the map.{/if}
      </p>
    </section>
  </div>
</main>
