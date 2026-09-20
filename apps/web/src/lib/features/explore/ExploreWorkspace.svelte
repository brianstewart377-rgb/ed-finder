<script lang="ts">
  import { createQuery } from '@tanstack/svelte-query';
  import { resolve } from '$app/paths';
  import { onMount, tick } from 'svelte';
  import { ArrowRight, LocateFixed, Search, Sparkles } from '@lucide/svelte';
  import {
    autocompleteSystems,
    getCatalogueViewportSystems,
    getCommanderViewportVisits,
    getMapHeatmap,
    searchExploreSystems,
    type AutocompleteSystem,
    type CatalogueViewportResponse,
    type ExploreSearchRequest,
    type ExploreSystem,
  } from '$lib/api/client';
  import { queryKeys } from '$lib/api/query';
  import { parseId64, type Id64 } from '$lib/domain/id64';
  import { usePersistenceContext } from '$lib/persistence/context';
  import SpatialCanvas from '$lib/spatial/SpatialCanvas.svelte';
  import type {
    CameraState,
    RuntimeEvent,
    SpatialContribution,
    SpatialTarget,
    SystemCameraState,
  } from '$lib/spatial/contracts';
  import {
    buildExploreGalaxyScene,
    createExploreFinderContribution,
  } from '$lib/spatial/explore-scene';
  import { collectGalaxySpatialContributions } from '$lib/spatial/galaxy-overlays';
  import { densityContributionFrom } from '$lib/spatial/galaxy-density-source';
  import { DENSITY_CROSSFADE_NEAR_LY } from '$lib/spatial/galaxy-density-crossfade';
  import {
    fitGalaxyPlaneCamera,
    focusGalaxyCamera,
  } from '$lib/spatial/galaxy-camera';
  import {
    createGalaxyRegionsContribution,
    fetchAuthoritativeGalaxyRegions,
    type GalaxyRegionsPayload,
  } from '$lib/spatial/galaxy-regions';
  import {
    createGalaxyNebulaeContribution,
    fetchGalaxyNebulae,
    type GalaxyNebulaePayload,
  } from '$lib/spatial/galaxy-nebulae';
  import { stellarPresentation } from '$lib/spatial/stellar-presentation';
  import WorkspaceHeader from '$lib/components/WorkspaceHeader.svelte';

  import { createCommanderHistoryContribution } from '$lib/spatial/commander-history';
  import {
    createCatalogueStarsContribution,
    galaxyStarViewport,
    withinGalaxyDisk,
  } from '$lib/spatial/galaxy-star-stream';

  const { selectedSystem, syncKey } = usePersistenceContext();
  const reviewLabRun = import.meta.env.VITE_REVIEW_LAB === '1';
  let query = $state('');
  let activeSuggestion = $state(-1);
  let autocompleteOpen = $state(false);
  let anchor = $state<AutocompleteSystem | null>(null);
  let selectionRevision = $state(0);
  let focusRevision = $state(0);
  let focusTarget = $state<SpatialTarget | null>(null);
  let lastPickedId64 = $state<Id64 | null>(null);
  let regions = $state<GalaxyRegionsPayload | null>(null);
  let regionContribution = $state<SpatialContribution | null>(null);
  let regionState = $state<'loading' | 'ready' | 'failed'>('loading');
  let regionResourceRevision = $state(0);
  let selectedRegionId = $state<string | null>(null);
  let hoveredRegionId = $state<string | null>(null);
  let cameraRequest = $state<CameraState | null>(null);
  let cameraRequestRevision = $state(0);
  let spatialCameraTransitionActive = $state(false);
  let retainedCamera = $state<{
    finderRevision: number;
    camera: CameraState;
  } | null>(null);
  let regionLoadAttempt = 0;
  let mapSection = $state<HTMLElement>();
  let resultList = $state<HTMLUListElement>();
  let focusedResultSet = '';
  let initialGalaxyViewRequested = false;
  let streamCamera = $state<CameraState | null>({
    focusLy: { x: 0, y: 0, z: 0 },
    distanceLy: 118_000,
    bearingRad: 0,
    pitchRad: 0.55,
    projection: 'perspective',
    revision: 0,
  });
  let streamRevision = $state(0);
  let viewportCameraTimeout: number | null = null;
  let pendingViewportCamera: CameraState | null = null;
  let appliedCataloguePacket = $state<CatalogueViewportResponse | null>(null);
  let appliedCatalogueRevision = $state(0);
  let layerToggleRevision = $state(0);
  let showTravelHeatmap = $state(false);
  let showNebulae = $state(true);
  let nebulae = $state<GalaxyNebulaePayload | null>(null);
  let nebulaState = $state<'loading' | 'ready' | 'failed'>('loading');
  let nebulaResourceRevision = $state(0);
  let nebulaLoadAttempt = 0;

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
    retry: 0,
  }));

  const starViewport = $derived(galaxyStarViewport(streamCamera));
  const viewportRequest = $derived(
    starViewport
      ? {
          minX: starViewport.minX,
          maxX: starViewport.maxX,
          minY: starViewport.minY,
          maxY: starViewport.maxY,
          minZ: starViewport.minZ,
          maxZ: starViewport.maxZ,
          limit: starViewport.limit,
        }
      : null,
  );
  const catalogueStars = createQuery(() => ({
    queryKey: queryKeys.catalogueViewport(
      viewportRequest ?? {
        minX: 0,
        maxX: 0,
        minY: 0,
        maxY: 0,
        minZ: 0,
        maxZ: 0,
        limit: 1,
      },
    ),
    queryFn: ({ signal }) => {
      if (!viewportRequest) throw new Error('No exact-star viewport requested');
      return getCatalogueViewportSystems(viewportRequest, signal);
    },
    enabled: viewportRequest !== null,
    staleTime: 20_000,
    // Keep the previous star sample on screen while the next viewport loads so
    // the layer does not blink out and back in on every pan/zoom settle.
    placeholderData: (previousData) => previousData,
  }));
  $effect(() => {
    if (
      catalogueStars.data &&
      !catalogueStars.isPlaceholderData &&
      catalogueStars.dataUpdatedAt !== appliedCatalogueRevision
    ) {
      appliedCataloguePacket = catalogueStars.data;
      appliedCatalogueRevision = catalogueStars.dataUpdatedAt;
    }
  });
  const commanderVisits = createQuery(() => ({
    queryKey: queryKeys.commanderViewport(
      $syncKey.value.state.syncKey,
      viewportRequest ?? {
        minX: 0,
        maxX: 0,
        minY: 0,
        maxY: 0,
        minZ: 0,
        maxZ: 0,
        limit: 1,
      },
    ),
    queryFn: ({ signal }) => {
      if (!viewportRequest || !starViewport)
        throw new Error('No commander-history viewport requested');
      return getCommanderViewportVisits(
        $syncKey.value.state.syncKey,
        viewportRequest,
        starViewport.cameraDistanceLy,
        signal,
      );
    },
    enabled: showTravelHeatmap && viewportRequest !== null,
    staleTime: 20_000,
    placeholderData: (previousData) => previousData,
  }));
  const heatmap = createQuery(() => ({
    queryKey: ['map-heatmap', streamCamera?.distanceLy ?? 0],
    queryFn: ({ signal }) =>
      getMapHeatmap(
        {
          voxel_size: Math.max(
            200,
            Math.round((streamCamera?.distanceLy ?? 118_000) / 200),
          ),
          max_cells: 40_000,
        },
        signal,
      ),
    // Enabled across the zoomed-out + overlap band; below `nearLy` density is
    // fully faded so no fetch needed.
    enabled: (streamCamera?.distanceLy ?? 0) >= DENSITY_CROSSFADE_NEAR_LY,
    staleTime: 60_000,
    placeholderData: (previousData) => previousData,
  }));
  const densityContribution = $derived(
    densityContributionFrom(heatmap.data, heatmap.dataUpdatedAt),
  );
  const densityCellCount = $derived(
    heatmap.data && heatmap.data.source === 'pyramid' ? heatmap.data.count : 0,
  );
  const densityTruncated = $derived(
    heatmap.data && heatmap.data.source === 'pyramid'
      ? heatmap.data.truncated
      : false,
  );
  const cataloguePacketIsCurrent = $derived(
    catalogueStars.data === appliedCataloguePacket &&
      !catalogueStars.isPlaceholderData,
  );
  const filteredCatalogueSystems = $derived(
    (appliedCataloguePacket?.systems ?? []).filter((system) => {
      if (!starViewport || !streamCamera) return true;
      // Wide galaxy scale: shape the axis-aligned API sample into the
      // canonical galactic disk so it reads as a swirling star field rather
      // than a rectangular slab, and feather the rim so nothing clips square.
      if (starViewport.wide) return withinGalaxyDisk(system.x, system.z);
      if (!cataloguePacketIsCurrent) return true;
      const focus = streamCamera.focusLy;
      const horizontalRadius = (starViewport.maxX - starViewport.minX) / 2;
      const verticalRadius = (starViewport.maxY - starViewport.minY) / 2;
      if (horizontalRadius <= 0 || verticalRadius <= 0) return true;
      const dx = (system.x - focus.x) / horizontalRadius;
      const dz = (system.z - focus.z) / horizontalRadius;
      const dy = (system.y - focus.y) / verticalRadius;
      return dx * dx + dz * dz <= 1 && Math.abs(dy) <= 1;
    }),
  );
  const viewportSystems = $derived(
    filteredCatalogueSystems.map((system): ExploreSystem => ({
      id64: system.id64,
      name: system.name,
      coords: { x: system.x, y: system.y, z: system.z },
      main_star_type: system.mainStarClass,
    })),
  );
  const systems = $derived(
    results.data ? results.data.results : viewportSystems,
  );
  const finderRevision = $derived(
    results.dataUpdatedAt || appliedCatalogueRevision,
  );
  const finderContribution = $derived(
    createExploreFinderContribution(systems, finderRevision),
  );
  const catalogueStarsContribution = $derived(
    appliedCataloguePacket
      ? createCatalogueStarsContribution(
          filteredCatalogueSystems,
          appliedCatalogueRevision,
          appliedCataloguePacket.truncated,
        )
      : null,
  );
  const commanderHistoryContribution = $derived(
    showTravelHeatmap && commanderVisits.data
      ? createCommanderHistoryContribution(
          commanderVisits.data.mode,
          commanderVisits.data.visits,
          commanderVisits.dataUpdatedAt,
          commanderVisits.data.truncated,
        )
      : null,
  );
  const nebulaContribution = $derived(
    showNebulae && nebulae
      ? createGalaxyNebulaeContribution(nebulae, nebulaResourceRevision)
      : null,
  );
  const selectedMapSystem = $derived.by(() => {
    const finder = systems.find(
      (system) => system.id64 === $selectedSystem.value,
    );
    if (finder)
      return {
        id64: finder.id64,
        name: finder.name,
        main_star_type: finder.main_star_type,
        main_star_subtype: finder.main_star_subtype,
        distance: finder.distance,
        population: finder.population,
        primaryEconomy: finder.primaryEconomy,
        allegiance: finder.allegiance,
        security: finder.security,
      };
    const catalogue = catalogueStars.data?.systems.find(
      (system) => system.id64 === $selectedSystem.value,
    );
    return catalogue
      ? {
          id64: catalogue.id64,
          name: catalogue.name,
          main_star_type: catalogue.mainStarClass,
          main_star_subtype: null,
          distance: null,
          population: null,
          primaryEconomy: null,
          allegiance: null,
          security: null,
        }
      : null;
  });
  const selectedStarPresentation = $derived(
    stellarPresentation({
      type: selectedMapSystem?.main_star_type,
      subtype: selectedMapSystem?.main_star_subtype,
    }),
  );
  const scene = $derived(
    buildExploreGalaxyScene(
      systems,
      $selectedSystem.value,
      finderRevision +
        selectionRevision +
        regionResourceRevision +
        streamRevision +
        layerToggleRevision +
        appliedCatalogueRevision +
        commanderVisits.dataUpdatedAt +
        nebulaResourceRevision +
        (heatmap.dataUpdatedAt ?? 0),
      {
        finderContribution,
        finderRevision,
        camera: retainedCamera?.camera ?? null,
        spatialContributions: collectGalaxySpatialContributions({
          regions: regionContribution,
          nebulae: nebulaContribution,
          density: densityContribution,
          catalogueStars: catalogueStarsContribution,
          commanderHistory: commanderHistoryContribution,
        }),
        selectedRegionId,
      },
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
    if (viewportCameraTimeout !== null) {
      window.clearTimeout(viewportCameraTimeout);
      viewportCameraTimeout = null;
    }
    pendingViewportCamera = null;
    anchor = hit;
    query = hit.name;
    autocompleteOpen = false;
    selectedSystem.set(hit.id64);
    selectionRevision += 1;
    streamRevision += 1;
    streamCamera = {
      focusLy: {
        x: hit.x ?? 0,
        y: hit.y ?? 0,
        z: hit.z ?? 0,
      },
      distanceLy: 400,
      bearingRad: 0,
      pitchRad: 0.55,
      projection: 'perspective',
      revision: streamRevision,
    };
    focusTarget = { kind: 'system', systemId64: hit.id64 };
    focusRevision += 1;
  }

  function handleQueryInput(event: Event): void {
    anchor = null;
    autocompleteOpen =
      (event.currentTarget as HTMLInputElement).value.trim().length >= 2;
    activeSuggestion = -1;
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
        activeSuggestion <= 0
          ? suggestionRows.length - 1
          : activeSuggestion - 1;
    } else if (event.key === 'Home') {
      event.preventDefault();
      activeSuggestion = 0;
    } else if (event.key === 'End') {
      event.preventDefault();
      activeSuggestion = suggestionRows.length - 1;
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const hit = suggestionRows[Math.max(0, activeSuggestion)];
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

  function handleResultKeydown(
    event: KeyboardEvent,
    system: ExploreSystem,
  ): void {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    selectResult(system);
  }

  function retainCamera(camera: CameraState): void {
    retainedCamera = { finderRevision, camera };
    pendingViewportCamera = camera;
    if (viewportCameraTimeout !== null) {
      window.clearTimeout(viewportCameraTimeout);
    }
    viewportCameraTimeout = window.setTimeout(() => {
      viewportCameraTimeout = null;
      const nextCamera = pendingViewportCamera;
      pendingViewportCamera = null;
      if (nextCamera) streamCamera = nextCamera;
    }, 180);
  }

  function handleRuntimeEvent(event: RuntimeEvent): void {
    if (event.type === 'CAMERA_CHANGED' && 'focusLy' in event.camera) {
      if (spatialCameraTransitionActive) return;
      retainCamera(event.camera);
    } else if (event.type === 'TARGET_HOVERED') {
      hoveredRegionId =
        event.target?.kind === 'region' ? event.target.id : null;
    } else if (event.type === 'TARGET_PICKED') {
      if (event.target?.kind === 'region') {
        selectRegion(event.target.id);
      } else if (event.target?.kind === 'system') {
        try {
          const picked = parseId64(event.target.systemId64);
          selectedSystem.set(picked);
          lastPickedId64 = picked;
          selectionRevision += 1;
        } catch {
          // Renderer events fail closed if an adapter emits a non-Id64 target.
        }
      }
    }
  }

  function toggleTravelHeatmap(): void {
    showTravelHeatmap = !showTravelHeatmap;
    layerToggleRevision += 1;
  }

  function toggleNebulae(): void {
    showNebulae = !showNebulae;
    layerToggleRevision += 1;
  }

  function regionName(regionId: string | null): string {
    if (!regionId || !regions) return 'None';
    return (
      regions.regions.find((region) => String(region.id) === regionId)?.name ??
      'Unknown'
    );
  }

  function selectRegion(regionId: string | null): void {
    if (regionId === selectedRegionId || !regions) return;
    selectedRegionId = regionId;
    selectionRevision += 1;
  }

  function requestView(camera: CameraState): void {
    cameraRequest = camera;
    cameraRequestRevision += 1;
  }

  function handleCameraTransitionChange(
    active: boolean,
    camera?: CameraState | SystemCameraState | null,
  ): void {
    spatialCameraTransitionActive = active;
    if (!active && camera && 'focusLy' in camera) {
      retainCamera(camera);
    }
  }

  function overview(): void {
    if (!regions) return;
    const { origin, pixel_scale } = regions.lookup;
    const canvas = mapSection?.querySelector('canvas');
    requestView(
      fitGalaxyPlaneCamera(
        { ...scene.camera, bearingRad: 0, pitchRad: Math.PI / 2 },
        {
          min: { x: origin.x, y: 0, z: origin.z },
          max: {
            x: origin.x + regions.source.width * pixel_scale,
            y: 0,
            z: origin.z + regions.source.height * pixel_scale,
          },
        },
        {
          width: canvas?.clientWidth || 1000,
          height: canvas?.clientHeight || 500,
        },
      ),
    );
  }

  function viewSelectedRegion(): void {
    const region = regions?.regions.find(
      (candidate) => String(candidate.id) === selectedRegionId,
    );
    if (region)
      requestView(focusGalaxyCamera(scene.camera, region.labelLy, 18_000));
  }

  async function loadRegions(): Promise<void> {
    const attempt = ++regionLoadAttempt;
    regionState = 'loading';
    try {
      const accepted = await fetchAuthoritativeGalaxyRegions();
      if (attempt !== regionLoadAttempt) return;
      regions = accepted;
      regionContribution = createGalaxyRegionsContribution(accepted, 1);
      regionResourceRevision += 1;
      regionState = 'ready';
      if (!initialGalaxyViewRequested) {
        initialGalaxyViewRequested = true;
        void tick().then(() => overview());
      }
    } catch {
      if (attempt !== regionLoadAttempt) return;
      regions = null;
      regionContribution = null;
      regionState = 'failed';
    }
  }

  async function loadNebulae(): Promise<void> {
    const attempt = ++nebulaLoadAttempt;
    nebulaState = 'loading';
    try {
      const accepted = await fetchGalaxyNebulae();
      if (attempt !== nebulaLoadAttempt) return;
      nebulae = accepted;
      nebulaResourceRevision += 1;
      nebulaState = 'ready';
    } catch {
      if (attempt !== nebulaLoadAttempt) return;
      nebulae = null;
      nebulaState = 'failed';
    }
  }

  onMount(() => {
    void loadRegions();
    void loadNebulae();
    return () => {
      regionLoadAttempt += 1;
      nebulaLoadAttempt += 1;
      // Cancel a pending viewport-camera debounce so it can't fire after teardown.
      if (viewportCameraTimeout !== null) {
        window.clearTimeout(viewportCameraTimeout);
        viewportCameraTimeout = null;
      }
    };
  });

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
      aria-busy={results.isFetching || catalogueStars.isFetching}
    >
      <div class="panel-heading">
        <div>
          <p class="eyebrow">Catalogue results</p>
          <h2 id="results-title">
            {anchor ? `Near ${anchor.name}` : 'Near Sol'}
          </h2>
        </div>
        <span>{systems.length} shown</span>
      </div>

      {#if results.isPending && catalogueStars.isPending}
        <div class="state-card" role="status">
          <Sparkles aria-hidden="true" />
          <p>Building a real-system shortlist…</p>
        </div>
      {:else if results.isError && (reviewLabRun || systems.length === 0)}
        <div class="state-card error" role="alert">
          <p>Discovery results could not be loaded.</p>
          <button
            class="secondary-button"
            type="button"
            onclick={() => results.refetch()}>Retry search</button
          >
        </div>
      {:else if reviewLabRun && results.data?.results.length === 0}
        <div class="state-card" role="status">
          <p>No systems match this discovery area.</p>
        </div>
      {:else if systems.length === 0}
        <div class="state-card">
          <p>No systems match this discovery area. Choose another anchor.</p>
        </div>
      {:else}
        <ul
          class="result-list"
          bind:this={resultList}
          aria-label="System results"
        >
          {#each systems as system (system.id64)}
            <li
              class:selected={$selectedSystem.value === system.id64}
              data-system-result={system.id64}
            >
              <button
                class="result-select"
                type="button"
                data-result-select
                aria-pressed={$selectedSystem.value === system.id64}
                onclick={() => selectResult(system)}
                onkeydown={(event) => handleResultKeydown(event, system)}
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
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    <section
      class="map-panel"
      aria-labelledby="map-title"
      bind:this={mapSection}
    >
      <div class="panel-heading">
        <div>
          <p class="eyebrow">Galaxy presentation</p>
          <h2 id="map-title">Spatial results</h2>
        </div>
        <span data-region-resource-state={regionState}
          ><LocateFixed aria-hidden="true" size={15} />
          {regionState === 'ready' ? '42/42 regions' : 'canonical ly'}</span
        >
      </div>
      <p class="map-note">
        Stars use exact catalogue coordinates and class-specific presentation.
        Amber marks active selections. Region geometry is the pinned in-game
        source; no synthetic geography, stars, or density are substituted.
      </p>
      {#if regionState === 'loading'}
        <p class="region-load-state" role="status">
          Loading all 42 authoritative regions…
        </p>
      {:else if regionState === 'failed'}
        <div class="region-load-state error" role="alert">
          <span>The authoritative region resource failed validation.</span>
          <button type="button" onclick={loadRegions}>Retry regions</button>
        </div>
      {:else if regions}
        <div class="product-region-controls">
          <label for="explore-region-picker">
            <span>Galactic region</span>
            <select
              id="explore-region-picker"
              value={selectedRegionId ?? ''}
              onchange={(event) =>
                selectRegion(event.currentTarget.value || null)}
            >
              <option value="">No region selected</option>
              {#each regions.regions as region (region.id)}
                <option
                  value={String(region.id)}
                  data-galaxy-region-option={region.id}
                >
                  {region.id}. {region.name}
                </option>
              {/each}
            </select>
          </label>
          <div
            class="product-region-actions"
            role="group"
            aria-label="Map views"
          >
            <button type="button" onclick={overview}>All 42 regions</button>
            <button
              type="button"
              disabled={!selectedRegionId}
              onclick={viewSelectedRegion}>View selected</button
            >
          </div>
          <div class="product-region-status" aria-live="polite">
            <span
              >Selected: <strong
                data-selected-region-id={selectedRegionId ?? ''}
                >{regionName(selectedRegionId)}</strong
              ></span
            >
            <span
              >Hovered: <strong data-hovered-region-id={hoveredRegionId ?? ''}
                >{regionName(hoveredRegionId)}</strong
              ></span
            >
          </div>
        </div>
      {/if}
      <div class="map-layer-controls" aria-label="Map layers">
        <button
          type="button"
          aria-pressed={showNebulae}
          data-nebula-toggle
          onclick={toggleNebulae}
        >
          {showNebulae ? 'Hide' : 'Show'} nebulae
        </button>
        <button
          type="button"
          aria-pressed={showTravelHeatmap}
          data-commander-history-toggle
          onclick={toggleTravelHeatmap}
        >
          {showTravelHeatmap ? 'Hide' : 'Show'} my travel heatmap
        </button>
        <span data-nebula-resource-state={nebulaState}>
          {#if nebulaState === 'loading'}
            Loading complete nebula inventory…
          {:else if nebulaState === 'failed'}
            Nebula layer unavailable · <button
              type="button"
              onclick={loadNebulae}>Retry</button
            >
          {:else if nebulae}
            {nebulae.nebulae.length.toLocaleString()} EDAstro nebula landmarks ·
            <a
              href="https://edastro.com/mapcharts/files.html"
              target="_blank"
              rel="noreferrer">{nebulae.attribution}</a
            >
            ·
            <a
              href="https://edastro.com/mapcharts/files/nebulae-coordinates.csv"
              target="_blank"
              rel="noreferrer">source CSV</a
            >
            · {nebulae.rightsNotice}
          {/if}
        </span>
        <span
          data-catalogue-star-count={appliedCataloguePacket?.systems.length ??
            0}
          data-density-cell-count={densityCellCount}
        >
          {#if densityContribution}
            {densityCellCount.toLocaleString()} density cells{densityTruncated
              ? ' · bounded view'
              : ''}
          {:else if !starViewport}
            Known-system density · zoom in for individual stars
          {:else if catalogueStars.isPending}
            Loading exact catalogue stars…
          {:else if catalogueStars.isError}
            Exact-star layer unavailable
          {:else}
            {(catalogueStars.data?.systems.length ?? 0).toLocaleString()} exact stars{catalogueStars
              .data?.truncated
              ? ' · bounded view'
              : ''}
          {/if}
        </span>
        {#if showTravelHeatmap}<span
            data-commander-history-count={commanderVisits.data?.count ?? 0}
          >
            {#if !starViewport}
              Travel history appears when individual-star range is active
            {:else if commanderVisits.isPending}
              Reading imported journal visits…
            {:else if commanderVisits.isError}
              No journal heatmap is available for this local profile
            {:else}
              {(commanderVisits.data?.count ?? 0).toLocaleString()} visited
              {commanderVisits.data?.mode === 'density' ? ' cells' : ' systems'}
            {/if}
          </span>{/if}
      </div>
      <SpatialCanvas
        {scene}
        {cameraRequest}
        {cameraRequestRevision}
        {focusTarget}
        {focusRevision}
        onRuntimeEvent={handleRuntimeEvent}
        onTransitionChange={handleCameraTransitionChange}
      />
      {#if selectedMapSystem}
        <article
          class="map-system-card"
          aria-labelledby="map-system-card-title"
          data-selected-system-card={selectedMapSystem.id64}
        >
          <div class="map-system-card__identity">
            <span
              class="stellar-glyph"
              data-stellar-glyph={selectedStarPresentation.glyph}
              style:--stellar-core={`rgb(${selectedStarPresentation.coreRgb.map((channel) => Math.round(channel * 255)).join(', ')})`}
              style:--stellar-halo={`rgb(${selectedStarPresentation.haloRgb.map((channel) => Math.round(channel * 255)).join(', ')})`}
              aria-hidden="true"
            ></span>
            <div>
              <p class="eyebrow">Selected system</p>
              <h3 id="map-system-card-title">
                {selectedMapSystem.name ?? `System ${selectedMapSystem.id64}`}
              </h3>
              <code>{selectedMapSystem.id64}</code>
            </div>
          </div>
          <dl class="map-system-card__facts">
            <div>
              <dt>Primary star</dt>
              <dd>
                {selectedMapSystem.main_star_type ??
                  'Unknown'}{selectedMapSystem.main_star_subtype
                  ? ` · ${selectedMapSystem.main_star_subtype}`
                  : ''}
              </dd>
            </div>
            {#if selectedMapSystem.distance != null}<div>
                <dt>Distance</dt>
                <dd>{selectedMapSystem.distance.toFixed(1)} ly</dd>
              </div>{/if}
            {#if selectedMapSystem.population != null}<div>
                <dt>Population</dt>
                <dd>{population(selectedMapSystem.population) ?? '0'}</dd>
              </div>{/if}
            {#if selectedMapSystem.primaryEconomy}<div>
                <dt>Economy</dt>
                <dd>{selectedMapSystem.primaryEconomy}</dd>
              </div>{/if}
            {#if selectedMapSystem.allegiance}<div>
                <dt>Allegiance</dt>
                <dd>{selectedMapSystem.allegiance}</dd>
              </div>{/if}
            {#if selectedMapSystem.security}<div>
                <dt>Security</dt>
                <dd>{selectedMapSystem.security}</dd>
              </div>{/if}
          </dl>
          <nav
            class="map-system-card__actions"
            aria-label="Selected system actions"
          >
            <a href={resolve(`/inspect?system=${selectedMapSystem.id64}`)}
              >Open System Map</a
            >
            <a href={resolve(`/plan?system=${selectedMapSystem.id64}`)}
              >Plan here <ArrowRight aria-hidden="true" size={15} /></a
            >
          </nav>
        </article>
      {/if}
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
