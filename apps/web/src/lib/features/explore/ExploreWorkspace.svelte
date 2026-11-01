<script lang="ts">
  import { createQuery } from '@tanstack/svelte-query';
  import { fromStore } from 'svelte/store';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { onMount, tick, untrack } from 'svelte';
  import { ArrowRight, LocateFixed, Search, Sparkles } from '@lucide/svelte';
  import {
    ApiError,
    autocompleteSystems,
    getCatalogueViewportSystems,
    getCommanderTravelHeatmap,
    getMapHeatmap,
    getArchetypeRankings,
    getSystem,
    searchExploreSystems,
    SOL_ID64,
    type AutocompleteSystem,
    type CatalogueViewportResponse,
    type DistanceAnchor,
    type ExploreSearchRequest,
    type ExploreSystem,
    type FinderPageEnvelope,
  } from '$lib/api/client';
  import { queryClient, queryKeys } from '$lib/api/query';
  import { auth } from '$lib/auth/auth';
  import { FINDER_F4_ENABLED } from '$lib/config';
  import { parseId64, type Id64 } from '$lib/domain/id64';
  import {
    DEFAULT_RANKING_STATE,
    hasRankingSearchParams,
    lastPageCorrection,
    normalizeRankingState,
    parseRankingSearchParams,
    selectFinderRequest,
    serializeRankingSearchParams,
    stripRankingSearchParams,
    type FinderRankingState,
  } from './ranking-state';
  import { archetypeLabel } from './archetypes';
  import {
    inspectHref,
    navigateWithAnchor,
    readExploreAnchor,
  } from './navigation';
  import ArchetypePicker from './ArchetypePicker.svelte';
  import ArchetypeExplanation from './ArchetypeExplanation.svelte';
  import FinderResultRanking from './FinderResultRanking.svelte';
  import BodyFilters from './BodyFilters.svelte';
  import {
    normalizeBodyFilters,
    type BodyFilterKey,
    type BodyFilterValues,
  } from './body-filters';
  import {
    parseExploreSearchParams,
    serializeExploreSearchParams,
  } from './search-state';
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
    createExploreSelectionContribution,
    mapExploreSelectedSystemPoint,
  } from '$lib/spatial/explore-scene';
  import { collectGalaxySpatialContributions } from '$lib/spatial/galaxy-overlays';
  import {
    densityContributionFrom,
    heatmapVoxelSizeForDistance,
  } from '$lib/spatial/galaxy-density-source';
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
  import SystemActions from './SystemActions.svelte';
  import WatchlistPanel from './WatchlistPanel.svelte';
  import ComparePanel from './ComparePanel.svelte';

  import { createCommanderHistoryContribution } from '$lib/spatial/commander-history';
  import {
    createCatalogueStarsContribution,
    galaxyStarViewport,
    withinGalaxyDisk,
  } from '$lib/spatial/galaxy-star-stream';

  const { selectedSystem, pins, compare } = usePersistenceContext();
  const session = fromStore(auth);
  // The travel heatmap is the signed-in account's own V3 journal travel; the
  // cache key carries the account so a sign-out/switch never reuses rows.
  const travelAccountId = $derived(
    session.current.loading ? null : (session.current.user?.account_id ?? null),
  );
  const reviewLabRun = import.meta.env.VITE_REVIEW_LAB === '1';
  let query = $state('');
  let activeSuggestion = $state(-1);
  let autocompleteOpen = $state(false);
  const parsedSearch = $derived(
    parseExploreSearchParams(page.url.searchParams),
  );
  const historyAnchor = $derived(readExploreAnchor(page.state));
  // Old history entries still carry coordinates. An explicit URL always wins,
  // including a malformed near parameter, which must not revive stale state.
  const nearId = $derived(
    parsedSearch.near ??
      (!page.url.searchParams.has('near')
        ? (historyAnchor?.id64 ?? null)
        : null),
  );
  const anchorDetail = createQuery(() => {
    const id64 = nearId;
    return {
      queryKey: [...queryKeys.all, 'explore', 'selected-point', id64],
      queryFn: ({ signal }: { signal: AbortSignal }) => {
        if (!id64) throw new Error('No search anchor');
        return getSystem(id64, signal);
      },
      enabled: id64 !== null && historyAnchor?.id64 !== id64,
      retry: 0,
    };
  });
  const anchor = $derived.by(() => {
    if (!nearId) return null;
    if (historyAnchor?.id64 === nearId) return historyAnchor;
    const detail = anchorDetail.data;
    if (detail?.id64 !== nearId) return null;
    // The legacy facade only guards unknown origins with F4 enabled. A near
    // anchor requires real coordinates in either build.
    if (
      detail.id64 !== SOL_ID64 &&
      detail.x === 0 &&
      detail.y === 0 &&
      detail.z === 0
    )
      return null;
    return readExploreAnchor({ anchor: detail });
  });
  const bodyFilters = $derived(parsedSearch.bodyFilters);
  let anchorSelectionRevision = $state(0);
  let focusedAnchorRevision = 0;
  let hydratedAnchorIdentity: string | undefined;
  let hydratedExploreUrl: string | undefined;
  let searchInput = $state<HTMLInputElement>();
  let rankingNotice = $state('');
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

  const parsedRanking = $derived(
    FINDER_F4_ENABLED ? parseRankingSearchParams(page.url.searchParams) : null,
  );
  const rankingState = $derived(parsedRanking?.state ?? DEFAULT_RANKING_STATE);
  const bodyFiltersPaused = $derived(
    !anchor || rankingState.archetype !== 'any',
  );
  const urlSelection = $derived.by((): Id64 | null => {
    if (!FINDER_F4_ENABLED) return null;
    const values = page.url.searchParams.getAll('selected');
    if (values.length !== 1) return null;
    try {
      return parseId64(values[0]);
    } catch {
      return null;
    }
  });
  const canonicalSearch = $derived.by(() => {
    let params = serializeExploreSearchParams(
      { near: nearId, bodyFilters },
      page.url.searchParams,
    );
    if (FINDER_F4_ENABLED) {
      params.delete('selected');
      if (urlSelection) params.set('selected', urlSelection);
      params = serializeRankingSearchParams(rankingState, params);
    } else {
      params = stripRankingSearchParams(params);
    }
    const serialized = params.toString();
    return serialized ? `?${serialized}` : '';
  });
  const invalidAnchorState = $derived(
    page.state?.anchor != null && historyAnchor === null,
  );
  const rankingUrlReady = $derived(
    page.url.search === canonicalSearch && !invalidAnchorState,
  );
  const hasResultsIntent = $derived(
    nearId !== null ||
      (FINDER_F4_ENABLED &&
        (rankingState.archetype !== 'any' ||
          hasRankingSearchParams(page.url.searchParams) ||
          page.state.finderRequested === true)),
  );
  const resultsEnabled = $derived(
    rankingUrlReady && hasResultsIntent && (!nearId || anchor !== null),
  );
  const finderRequest = $derived.by(() => {
    const selected = selectFinderRequest(
      rankingState,
      anchor ? { x: anchor.x, y: anchor.y, z: anchor.z } : null,
      { enabled: FINDER_F4_ENABLED },
    );
    if (
      selected.kind === 'any' &&
      !bodyFiltersPaused &&
      Object.keys(bodyFilters).length
    )
      return {
        ...selected,
        request: { ...selected.request, body_filters: bodyFilters },
      };
    return selected;
  });
  const anchorReference = $derived<DistanceAnchor | null>(
    anchor ? { id64: anchor.id64, name: anchor.name } : null,
  );
  const searchRequest = $derived<ExploreSearchRequest>(
    finderRequest.kind === 'any' ? finderRequest.request : {},
  );
  const finderQueryKey = $derived(
    finderRequest.kind === 'rankings'
      ? queryKeys.rankings(finderRequest.request)
      : queryKeys.explore(
          finderRequest.request,
          anchorReference,
          FINDER_F4_ENABLED ? finderRequest.pageSize : null,
        ),
  );
  const finderIdentity = $derived(JSON.stringify(finderQueryKey));
  type FinderResponse = {
    results: readonly ExploreSystem[];
    page: FinderPageEnvelope;
    finderState?: FinderRankingState;
    finderIdentity?: string;
  };
  const results = createQuery<FinderResponse>(() => {
    if (!FINDER_F4_ENABLED) {
      const request = searchRequest;
      const reference = anchorReference;
      return {
        queryKey: queryKeys.explore(request, reference),
        queryFn: ({ signal }) =>
          searchExploreSystems(request, signal, reference),
        enabled: resultsEnabled,
        retry: 0,
      };
    }
    // Capture the complete request identity with its envelope. Placeholder rows
    // keep their old mode, floor and offset until the replacement arrives.
    const request = finderRequest;
    const reference = anchorReference;
    const state = rankingState;
    const identity = finderIdentity;
    return {
      queryKey: finderQueryKey,
      queryFn: async ({ signal }: { signal: AbortSignal }) => ({
        ...(request.kind === 'rankings'
          ? await getArchetypeRankings(request.request, signal)
          : await searchExploreSystems(
              request.request,
              signal,
              reference,
              request.pageSize,
            )),
        finderState: state,
        finderIdentity: identity,
      }),
      enabled: resultsEnabled,
      staleTime: 0,
      placeholderData: (previous: FinderResponse | undefined) => previous,
      retry: 0,
    };
  });
  // Query data is immutable and structurally shared. A deep $state proxy here
  // would give retained rows a different identity and rebuild their map layer.
  let retainedResults = $state.raw<FinderResponse>();
  $effect(() => {
    if (!hasResultsIntent) retainedResults = undefined;
    else if (FINDER_F4_ENABLED && results.data && !results.isPlaceholderData) {
      retainedResults = results.data;
    }
  });
  const displayedResults = $derived(
    hasResultsIntent
      ? (results.data ?? (FINDER_F4_ENABLED ? retainedResults : undefined))
      : undefined,
  );
  const currentResponse = $derived(
    FINDER_F4_ENABLED &&
      resultsEnabled &&
      !results.isPlaceholderData &&
      results.data?.finderIdentity === finderIdentity &&
      results.data.page.page_size === rankingState.pageSize &&
      results.data.page.offset === rankingState.offset,
  );
  const pageCorrection = $derived(
    FINDER_F4_ENABLED && currentResponse && !results.isFetching && results.data
      ? lastPageCorrection(results.data.page)
      : null,
  );
  const updatingResults = $derived(
    FINDER_F4_ENABLED &&
      hasResultsIntent &&
      !results.isError &&
      (results.isFetching || !currentResponse || pageCorrection !== null),
  );
  const activeArchetypeLabel = $derived(archetypeLabel(rankingState.archetype));
  const rankingDataNotReady = $derived.by(() => {
    const error = results.error;
    if (!(error instanceof ApiError) || error.status !== 503) return false;
    const body = error.body;
    const problem =
      body &&
      typeof body === 'object' &&
      'detail' in body &&
      body.detail &&
      typeof body.detail === 'object'
        ? body.detail
        : body;
    return (
      !!problem &&
      typeof problem === 'object' &&
      'reason' in problem &&
      problem.reason === 'finder_products_not_ready'
    );
  });

  $effect(() => {
    const current = page.url;
    const restoredAnchor = anchor;
    const identity = restoredAnchor ? JSON.stringify(restoredAnchor) : '';
    if (
      identity !== hydratedAnchorIdentity ||
      current.href !== hydratedExploreUrl
    ) {
      hydratedAnchorIdentity = identity;
      hydratedExploreUrl = current.href;
      query = restoredAnchor?.name ?? '';
    }
    if (FINDER_F4_ENABLED && $selectedSystem.value !== urlSelection) {
      selectedSystem.set(urlSelection);
      untrack(() => {
        selectionRevision += 1;
      });
    }
    if (!rankingUrlReady) {
      if (parsedSearch.issues.length || parsedRanking?.issues.length)
        rankingNotice = parsedSearch.issues.length
          ? 'Invalid search link option removed.'
          : 'Unsupported link option removed.';
      void navigateWithAnchor(
        `${current.pathname}${canonicalSearch}${current.hash}`,
        {
          replaceState: true,
          state: {
            ...(invalidAnchorState ||
            (current.searchParams.has('near') && !parsedSearch.near)
              ? { anchor: null }
              : {}),
            // Explicit default/ignored URL parameters can canonicalize away.
            // Keep that link's search intent in its history entry.
            finderRequested:
              FINDER_F4_ENABLED &&
              (hasRankingSearchParams(current.searchParams) ||
                page.state.finderRequested === true),
          },
        },
      );
    }
  });

  $effect(() => {
    // A lookup can fail, return a different id, or lack usable coordinates.
    // Never let that turn an intended nearby search into a galaxy-wide one.
    if (
      !rankingUrlReady ||
      !nearId ||
      anchor ||
      anchorDetail.isPending ||
      anchorDetail.isFetching
    )
      return;
    rankingNotice =
      'Search anchor could not be restored; choose a system again.';
    void navigateWithAnchor(
      exploreDestination(
        serializeExploreSearchParams(
          { near: null, bodyFilters },
          page.url.searchParams,
        ),
      ),
      { replaceState: true, state: { anchor: null } },
    );
  });

  $effect(() => {
    if (pageCorrection === null) return;
    rankingNotice = 'Page reset to the last available results.';
    const params = serializeRankingSearchParams(
      { ...rankingState, offset: pageCorrection },
      page.url.searchParams,
    );
    void navigateWithAnchor(exploreDestination(params), {
      replaceState: true,
      state: { finderRequested: true },
    });
  });

  function exploreDestination(params: URLSearchParams): string {
    const search = params.toString();
    return `${page.url.pathname}${search ? `?${search}` : ''}${page.url.hash}`;
  }

  function commitRanking(
    patch: Partial<FinderRankingState>,
    resetOffset = true,
  ): void {
    rankingNotice = '';
    // A later picker/page action supersedes an unfinished anchor autofocus.
    focusedAnchorRevision = anchorSelectionRevision;
    const state = normalizeRankingState({
      ...rankingState,
      ...patch,
      ...(resetOffset ? { offset: 0 } : {}),
    });
    void navigateWithAnchor(
      exploreDestination(
        serializeRankingSearchParams(state, page.url.searchParams),
      ),
      {
        state: {
          // Paging back to defaults can remove the last URL parameter too.
          finderRequested:
            (patch.offset !== undefined || patch.pageSize !== undefined) &&
            hasResultsIntent,
        },
      },
    );
  }

  function commitSelection(id64: Id64): void {
    if (FINDER_F4_ENABLED) {
      const params = new URLSearchParams(page.url.searchParams);
      params.set('selected', id64);
      void navigateWithAnchor(
        exploreDestination(serializeRankingSearchParams(rankingState, params)),
      );
    } else {
      selectedSystem.set(id64);
      selectionRevision += 1;
    }
  }

  async function clearAnchor(): Promise<void> {
    autocompleteOpen = false;
    query = '';
    const params = serializeRankingSearchParams(
      { ...rankingState, offset: 0 },
      serializeExploreSearchParams(
        { near: null, bodyFilters },
        page.url.searchParams,
      ),
    );
    await navigateWithAnchor(exploreDestination(params), {
      state: { anchor: null, finderRequested: false },
    });
    rankingNotice = hasResultsIntent
      ? 'Anchor cleared; searching galaxy-wide.'
      : '';
    searchInput?.focus();
  }

  async function commitBodyFilters(value: BodyFilterValues): Promise<void> {
    focusedAnchorRevision = anchorSelectionRevision;
    const committed = normalizeBodyFilters(value);
    const params = serializeExploreSearchParams(
      { near: nearId, bodyFilters: committed },
      page.url.searchParams,
    );
    params.delete('offset');
    const destination = exploreDestination(
      FINDER_F4_ENABLED
        ? serializeRankingSearchParams({ ...rankingState, offset: 0 }, params)
        : stripRankingSearchParams(params),
    );
    // Applying the same draft still means one refresh. A changed query is
    // fetched by its observer exactly once after URL hydration.
    if (
      destination === `${page.url.pathname}${page.url.search}${page.url.hash}`
    ) {
      if (resultsEnabled && !bodyFiltersPaused) await results.refetch();
      return;
    }
    if (!bodyFiltersPaused) {
      const next = selectFinderRequest({ ...rankingState, offset: 0 }, anchor, {
        enabled: FINDER_F4_ENABLED,
      });
      if (next.kind === 'any') {
        const request = Object.keys(committed).length
          ? { ...next.request, body_filters: committed }
          : next.request;
        await queryClient.invalidateQueries({
          queryKey: queryKeys.explore(
            request,
            anchorReference,
            FINDER_F4_ENABLED ? next.pageSize : null,
          ),
          exact: true,
          refetchType: 'none',
        });
      }
    }
    await navigateWithAnchor(destination);
  }

  function removeBodyFilter(key: BodyFilterKey): void {
    const next = { ...bodyFilters };
    delete next[key];
    void commitBodyFilters(next);
  }

  function followInspect(event: MouseEvent, id64: Id64): void {
    if (
      !FINDER_F4_ENABLED ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    )
      return;
    event.preventDefault();
    void navigateWithAnchor(inspectHref(id64, page.url));
  }

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
    queryKey: queryKeys.commanderTravel(
      travelAccountId ?? '',
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
      return getCommanderTravelHeatmap(
        viewportRequest,
        starViewport.cameraDistanceLy,
        signal,
      );
    },
    enabled:
      showTravelHeatmap && viewportRequest !== null && travelAccountId !== null,
    staleTime: 20_000,
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 401) && failureCount < 1,
    // Keep the previous viewport's points while panning, but never carry one
    // account's travel into another account's view.
    placeholderData: (previousData, previousQuery) =>
      previousQuery?.queryKey[3] === travelAccountId ? previousData : undefined,
  }));
  const travelHeatmapState = $derived.by(
    ():
      | 'checking'
      | 'auth-error'
      | 'signed-out'
      | 'zoom'
      | 'loading'
      | 'error'
      | 'empty'
      | 'ready' => {
      if (session.current.loading) return 'checking';
      // A failed session check is not "signed out": the visitor may well be
      // signed in, so offer a retry rather than a sign-in prompt.
      if (travelAccountId === null)
        return session.current.error ? 'auth-error' : 'signed-out';
      if (!starViewport) return 'zoom';
      if (commanderVisits.isError)
        return commanderVisits.error instanceof ApiError &&
          commanderVisits.error.status === 401
          ? 'signed-out'
          : 'error';
      if (!commanderVisits.data) return 'loading';
      return commanderVisits.data.count === 0 ? 'empty' : 'ready';
    },
  );
  // Normalize the raw camera distance to the discrete voxel size once, then key
  // the query AND its request params by it, so several nearby zoom stops that
  // round to the same voxel size reuse one cached response instead of issuing a
  // fresh request (and burning the route's 30-req/min budget) on every settle.
  const heatmapVoxelSize = $derived(
    heatmapVoxelSizeForDistance(streamCamera?.distanceLy ?? 118_000),
  );
  const heatmap = createQuery(() => ({
    queryKey: ['map-heatmap', heatmapVoxelSize],
    queryFn: ({ signal }) =>
      getMapHeatmap(
        {
          voxel_size: heatmapVoxelSize,
          // The density swirl wants every occupied cell, so request the full
          // aggregate. The endpoint defaults to `min_systems: 5`, which would
          // drop sparse cells and make a non-truncated payload fail its
          // count-sum reconciliation against the generation-wide source count.
          min_systems: 1,
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
  // Reserve its overlay position before the first response. A late patch must
  // not append density after stars and make the next selection rebuild them.
  const emptyDensityContribution: SpatialContribution = {
    id: 'catalogue-density-base',
    owner: 'CATALOGUE',
    revision: 0,
    layers: [],
  };
  const legacyDensityContribution = $derived(
    densityContributionFrom(heatmap.data, heatmap.dataUpdatedAt),
  );
  let densityContribution = $state.raw<SpatialContribution | null>(null);
  let appliedDensityData: typeof heatmap.data;
  let densityRevision = 0;
  let densityRemovalRevision = $state(0);
  $effect(() => {
    // A placeholder is the already-applied density, not a new empty revision.
    if (!FINDER_F4_ENABLED || heatmap.isPlaceholderData) return;
    const data = heatmap.data;
    if (data === appliedDensityData) return;
    appliedDensityData = data;
    // Cached viewport responses can have older timestamps. The renderer's
    // patch revision must advance even when returning to one of those views.
    const replacement = densityContributionFrom(data, ++densityRevision);
    if (!replacement && untrack(() => densityContribution) !== null) {
      // A null contribution is not dispatched as a patch; reload to remove it.
      densityRemovalRevision = untrack(() => densityRemovalRevision) + 1;
    }
    densityContribution = replacement;
  });
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
    hasResultsIntent
      ? (displayedResults?.results ??
          (FINDER_F4_ENABLED || !anchor || Object.keys(bodyFilters).length
            ? []
            : viewportSystems))
      : [],
  );
  let finderSequence = 0;
  const finderRevision = $derived.by(() => {
    // Freshness, placeholder and retained-envelope changes do not change the
    // map. TanStack preserves the row array's identity when its data is equal.
    // Clearing must advance the revision even before a response has arrived.
    void systems;
    return ++finderSequence;
  });
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
    // Never render cached private travel once the query is failing (an expired
    // session keeps the last data alongside a 401).
    showTravelHeatmap &&
      travelAccountId !== null &&
      !commanderVisits.isError &&
      commanderVisits.data
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
  let retainedSelectedSystem = $state.raw<ExploreSystem | null>(null);
  const selectedId = $derived(
    FINDER_F4_ENABLED ? urlSelection : $selectedSystem.value,
  );
  const selectedOnPage = $derived(
    systems.find((system) => system.id64 === selectedId),
  );
  // F4 URL selection uses result pages or exact-system resolution, independent
  // of catalogue viewport response timing.
  const knownSelectedSystem = $derived(
    selectedOnPage ??
      (retainedSelectedSystem?.id64 === selectedId
        ? retainedSelectedSystem
        : null),
  );
  const needsSelectionResolution = $derived(
    FINDER_F4_ENABLED &&
      rankingUrlReady &&
      urlSelection !== null &&
      !selectedOnPage &&
      (retainedSelectedSystem?.id64 !== urlSelection ||
        !mapExploreSelectedSystemPoint(retainedSelectedSystem)) &&
      (!hasResultsIntent || !results.isPending),
  );
  const selectedDetail = FINDER_F4_ENABLED
    ? createQuery(() => {
        const id64 = urlSelection;
        return {
          queryKey: [...queryKeys.all, 'explore', 'selected-point', id64],
          queryFn: ({ signal }: { signal: AbortSignal }) => {
            if (!id64) throw new Error('No selected system');
            return getSystem(id64, signal);
          },
          enabled: needsSelectionResolution,
          retry: 0,
        };
      })
    : undefined;
  const selectedDetailData = $derived(selectedDetail?.data);
  const reconstructedSelection = $derived<ExploreSystem | null>(
    FINDER_F4_ENABLED &&
      selectedDetailData?.id64 === urlSelection &&
      selectedDetailData
      ? {
          id64: selectedDetailData.id64,
          name: selectedDetailData.name,
          coords: {
            x: selectedDetailData.x,
            y: selectedDetailData.y,
            z: selectedDetailData.z,
          },
        }
      : null,
  );
  const selectedMapSystem = $derived.by((): ExploreSystem | null => {
    if (FINDER_F4_ENABLED)
      return (
        knownSelectedSystem ??
        reconstructedSelection ??
        (urlSelection ? { id64: urlSelection } : null)
      );
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
  const selectedPoint = $derived(
    FINDER_F4_ENABLED && selectedMapSystem
      ? (mapExploreSelectedSystemPoint(selectedMapSystem) ??
          (retainedSelectedSystem?.id64 === urlSelection
            ? mapExploreSelectedSystemPoint(retainedSelectedSystem)
            : null) ??
          (reconstructedSelection
            ? mapExploreSelectedSystemPoint(reconstructedSelection)
            : null))
      : null,
  );
  let selectionSequence = 0;
  const selectionContribution = $derived(
    FINDER_F4_ENABLED
      ? createExploreSelectionContribution(
          selectedPoint,
          systems,
          ++selectionSequence,
        )
      : null,
  );
  $effect(() => {
    if (!FINDER_F4_ENABLED) return;
    // Retain a selected result or exact-system resolution across page changes.
    // Resolution is keyed by id, so late responses cannot move the selection.
    const selected = selectedOnPage ?? reconstructedSelection;
    if (
      selected &&
      (mapExploreSelectedSystemPoint(selected) ||
        retainedSelectedSystem?.id64 !== selected.id64)
    )
      retainedSelectedSystem = selected;
    else if (retainedSelectedSystem?.id64 !== urlSelection)
      retainedSelectedSystem = null;
  });
  const selectedStarPresentation = $derived(
    stellarPresentation({
      type: selectedMapSystem?.main_star_type,
      subtype: selectedMapSystem?.main_star_subtype,
    }),
  );
  let sceneSequence = 0;
  const scene = $derived.by(() => {
    if (FINDER_F4_ENABLED) {
      // Density patches and camera receipts have their own renderer updates.
      // Snapshot them only when visual scene inputs change. Neither timestamps
      // nor placeholder bookkeeping may rebuild all the scene contributions.
      void densityRemovalRevision;
      return buildExploreGalaxyScene(systems, selectedId, ++sceneSequence, {
        finderContribution,
        finderRevision,
        selectedPoint,
        selectionContribution,
        camera: untrack(() => retainedCamera?.camera ?? null),
        spatialContributions: collectGalaxySpatialContributions({
          regions: regionContribution,
          nebulae: nebulaContribution,
          density: untrack(
            () => densityContribution ?? emptyDensityContribution,
          ),
          catalogueStars: catalogueStarsContribution,
          commanderHistory: commanderHistoryContribution,
        }),
        selectedRegionId,
      });
    }
    return buildExploreGalaxyScene(
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
          density: legacyDensityContribution,
          catalogueStars: catalogueStarsContribution,
          commanderHistory: commanderHistoryContribution,
        }),
        selectedRegionId,
      },
    );
  });

  $effect(() => {
    if (!anchor || !results.data || results.isFetching) return;
    if (
      rankingState.archetype !== 'any' ||
      (FINDER_F4_ENABLED && !currentResponse) ||
      anchorSelectionRevision === 0 ||
      anchorSelectionRevision === focusedAnchorRevision
    )
      return;
    focusedAnchorRevision = anchorSelectionRevision;
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
    query = hit.name;
    autocompleteOpen = false;
    rankingNotice = '';
    const committedAnchor = readExploreAnchor({ anchor: hit });
    const params = serializeExploreSearchParams(
      { near: committedAnchor?.id64 ?? null, bodyFilters },
      page.url.searchParams,
    );
    if (FINDER_F4_ENABLED) params.set('selected', hit.id64);
    if (committedAnchor && rankingState.archetype === 'any')
      anchorSelectionRevision += 1;
    void navigateWithAnchor(
      exploreDestination(
        serializeRankingSearchParams({ ...rankingState, offset: 0 }, params),
      ),
      { state: { anchor: committedAnchor } },
    );
    if (!committedAnchor) return;
    if (!FINDER_F4_ENABLED) {
      selectedSystem.set(hit.id64);
      selectionRevision += 1;
    }
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
    if (!(event.currentTarget as HTMLInputElement).value.trim() && anchor)
      void clearAnchor();
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
    if (FINDER_F4_ENABLED) retainedSelectedSystem = system;
    commitSelection(system.id64);
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
          commitSelection(picked);
          lastPickedId64 = picked;
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
    // SET_CAMERA already knows its destination. Retain it when the flight
    // starts so the viewport debounce cannot load the pre-flight close view
    // and then switch back to the overview on settle. FLY_TO supplies its camera
    // only on completion; its in-flight samples are still ignored.
    if ((FINDER_F4_ENABLED || !active) && camera && 'focusLy' in camera) {
      retainCamera(camera);
    }
  }

  function overview(): void {
    if (!regions) return;
    const { origin, pixel_scale } = regions.lookup;
    const canvas = mapSection?.querySelector('canvas');
    requestView(
      fitGalaxyPlaneCamera(
        {
          ...(FINDER_F4_ENABLED
            ? (retainedCamera?.camera ?? scene.camera)
            : scene.camera),
          bearingRad: 0,
          pitchRad: Math.PI / 2,
        },
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
      requestView(
        focusGalaxyCamera(
          FINDER_F4_ENABLED
            ? (retainedCamera?.camera ?? scene.camera)
            : scene.camera,
          region.labelLy,
          18_000,
        ),
      );
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

  <nav class="shortlist-nav" aria-label="Your saved systems">
    <a href="#saved-systems"
      >Pinned and watched systems ({$pins.value.length} pinned)</a
    >
    <a href="#compare-systems">Compare ({$compare.value.length})</a>
  </nav>

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
          bind:this={searchInput}
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

  {#snippet bodyFilterTools()}
    <BodyFilters
      value={bodyFilters}
      disabled={bodyFiltersPaused}
      paused={bodyFiltersPaused}
      onapply={(value) => void commitBodyFilters(value)}
      onremove={removeBodyFilter}
      onclear={() => void commitBodyFilters({})}
    />
  {/snippet}

  {#if anchor}
    <p class="committed-anchor">
      Search anchor: {anchor.name}
      <button
        type="button"
        aria-label={`Clear anchor ${anchor.name}`}
        onclick={clearAnchor}>Clear</button
      >
    </p>
    {#if FINDER_F4_ENABLED && rankingState.archetype !== 'any'}
      <p>
        Archetype ranking is galaxy-wide today; choose Any to search around {anchor.name}.
      </p>
    {/if}
  {/if}
  {#if FINDER_F4_ENABLED}
    <ArchetypePicker
      archetype={rankingState.archetype}
      minimumTier={rankingState.minimumTier}
      onArchetypeChange={(archetype) =>
        commitRanking({ archetype, minimumTier: null })}
      onMinimumTierChange={(minimumTier) => commitRanking({ minimumTier })}
      rankingTools={bodyFilterTools}
    />
    <label class="page-size"
      >Results per page
      <input
        type="number"
        min="1"
        max="50"
        step="1"
        value={rankingState.pageSize}
        onchange={(event) =>
          commitRanking({ pageSize: event.currentTarget.valueAsNumber })}
      />
    </label>
  {:else}
    {@render bodyFilterTools()}
  {/if}

  {#if rankingNotice}
    <p role="status" class="ranking-status">{rankingNotice}</p>
  {/if}

  <div class="explore-grid">
    <section
      class="results-panel"
      aria-labelledby="results-title"
      aria-busy={hasResultsIntent &&
        (FINDER_F4_ENABLED
          ? updatingResults
          : results.isFetching || catalogueStars.isFetching)}
    >
      <div class="panel-heading">
        <div>
          <p class="eyebrow">Catalogue results</p>
          <h2 id="results-title">
            {FINDER_F4_ENABLED && rankingState.archetype !== 'any'
              ? `Galaxy-wide ${activeArchetypeLabel} ranking`
              : anchor
                ? `Near ${anchor.name}`
                : hasResultsIntent
                  ? 'Galaxy-wide opportunities'
                  : 'Systems'}
          </h2>
        </div>
        {#if FINDER_F4_ENABLED && displayedResults}
          <FinderResultRanking
            variant="summary"
            page={displayedResults.page}
            archetype={displayedResults.finderState!.archetype}
          />
        {:else}<span>{systems.length} shown</span>{/if}
      </div>

      {#if FINDER_F4_ENABLED && hasResultsIntent}
        <div role="status" aria-live="polite" class="ranking-status">
          {#if updatingResults}
            <p>
              {displayedResults ? 'Updating… ' : ''}{rankingState.archetype ===
              'any'
                ? 'Searching systems…'
                : `Ranking systems for ${activeArchetypeLabel}…`}
            </p>
          {:else if currentResponse && displayedResults && !results.isError}
            <span
              >{displayedResults.page.count}
              {displayedResults.page.count === 1 ? 'result' : 'results'} on this page.</span
            >
          {/if}
        </div>
        {#if results.isError}
          <div class="state-card error" role="alert">
            <h3>
              {rankingDataNotReady
                ? 'Ranking data not ready'
                : 'Ranking temporarily unavailable'}
            </h3>
            <p>
              {rankingDataNotReady
                ? 'Archetype rankings are unavailable until Finder ranking data is published.'
                : rankingState.archetype !== 'any'
                  ? 'Archetype rankings are temporarily unavailable. Try again shortly.'
                  : 'Discovery results could not be loaded. Try again shortly.'}
            </p>
            <button type="button" onclick={() => results.refetch()}
              >Retry</button
            >
            {#if rankingState.archetype !== 'any'}
              <button
                type="button"
                onclick={() => commitRanking({ archetype: 'any' })}
                >Choose Any</button
              >
            {/if}
          </div>
        {:else if currentResponse && !results.isFetching && results.data?.page.total === 0}
          <div class="state-card">
            <p>
              {rankingState.archetype === 'any'
                ? 'No systems match this discovery area. Choose another anchor.'
                : `No systems meet minimum tier ${rankingState.minimumTier} for ${activeArchetypeLabel}.`}
            </p>
            {#if rankingState.archetype !== 'any'}
              {#if rankingState.minimumTier !== 'B'}
                <button
                  type="button"
                  onclick={() => commitRanking({ minimumTier: 'B' })}
                  >Reset to tier B</button
                >
              {/if}
              <button
                type="button"
                onclick={() => commitRanking({ archetype: 'any' })}
                >Choose Any</button
              >
            {/if}
          </div>
        {/if}
      {/if}

      {#if !hasResultsIntent}
        <div class="state-card">
          <p>Search for a system above to see what is near it.</p>
        </div>
      {:else if !FINDER_F4_ENABLED && results.isPending && catalogueStars.isPending}
        <div class="state-card" role="status">
          <Sparkles aria-hidden="true" />
          <p>Building a real-system shortlist…</p>
        </div>
      {:else if !FINDER_F4_ENABLED && results.isError && (reviewLabRun || systems.length === 0)}
        <div class="state-card error" role="alert">
          <p>Discovery results could not be loaded.</p>
          <button
            class="secondary-button"
            type="button"
            onclick={() => results.refetch()}>Retry search</button
          >
        </div>
      {:else if !FINDER_F4_ENABLED && reviewLabRun && results.data?.results.length === 0}
        <div class="state-card" role="status">
          <p>No systems match this discovery area.</p>
        </div>
      {:else if !FINDER_F4_ENABLED && systems.length === 0}
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
                  ><strong
                    id={FINDER_F4_ENABLED
                      ? `finder-result-heading-${system.id64}`
                      : undefined}
                    >{system.name ?? `System ${system.id64}`}</strong
                  ><code>{system.id64}</code></span
                >
                {#if FINDER_F4_ENABLED && displayedResults && !(rankingState.archetype === 'any' && displayedResults.finderState!.archetype !== 'any')}
                  <FinderResultRanking
                    variant="row"
                    {system}
                    archetype={displayedResults.finderState!.archetype}
                  />
                {/if}
                <span class="result-facts">
                  {#if system.distance != null}<span
                      >{FINDER_F4_ENABLED
                        ? `${system.distance.toFixed(2)} LY`
                        : `${system.distance.toFixed(1)} ly`}</span
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
              <!-- eslint-disable svelte/no-navigation-without-resolve -- inspectHref resolves the Inspect route -->
              <a
                class="inspect-link"
                href={FINDER_F4_ENABLED
                  ? inspectHref(system.id64, page.url)
                  : resolve(`/inspect?system=${system.id64}`)}
                onclick={FINDER_F4_ENABLED
                  ? (event) => followInspect(event, system.id64)
                  : undefined}
                aria-label={`Inspect ${system.name ?? system.id64}`}
              >
                Inspect <ArrowRight aria-hidden="true" size={16} />
              </a>
              <!-- eslint-enable svelte/no-navigation-without-resolve -->
              {#if FINDER_F4_ENABLED && displayedResults && !(rankingState.archetype === 'any' && displayedResults.finderState!.archetype !== 'any')}
                <ArchetypeExplanation
                  {system}
                  expected={system.ranking_provenance ?? null}
                  archetype={displayedResults.finderState!.archetype}
                  headingId={`finder-result-heading-${system.id64}`}
                />
              {/if}
              <div class="finder-actions"><SystemActions {system} /></div>
            </li>
          {/each}
        </ul>
      {/if}
      {#if FINDER_F4_ENABLED && displayedResults}
        <nav class="result-paging" aria-label="Result pages">
          <button
            type="button"
            class="quiet-button"
            disabled={!currentResponse ||
              updatingResults ||
              displayedResults.page.offset === 0}
            onclick={() =>
              commitRanking(
                {
                  offset: Math.max(
                    0,
                    displayedResults!.page.offset -
                      displayedResults!.page.page_size,
                  ),
                },
                false,
              )}>Previous</button
          >
          <button
            type="button"
            class="quiet-button"
            disabled={!currentResponse ||
              updatingResults ||
              displayedResults.page.offset + displayedResults.page.page_size >=
                displayedResults.page.navigable_total}
            onclick={() =>
              commitRanking(
                {
                  offset:
                    displayedResults!.page.offset +
                    displayedResults!.page.page_size,
                },
                false,
              )}>Next</button
          >
        </nav>
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
          {#if FINDER_F4_ENABLED ? densityContribution : legacyDensityContribution}
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
            data-commander-history-state={travelHeatmapState}
          >
            {#if travelHeatmapState === 'checking'}
              Checking your sign-in…
            {:else if travelHeatmapState === 'auth-error'}
              Account check unavailable · <button
                type="button"
                onclick={() => void auth.bootstrap()}>Retry</button
              >
            {:else if travelHeatmapState === 'signed-out'}
              <a href={resolve('/account')}>Sign in and import your journals</a> to
              see your travel heatmap
            {:else if travelHeatmapState === 'zoom'}
              Travel history appears when individual-star range is active
            {:else if travelHeatmapState === 'loading'}
              Reading imported journal visits…
            {:else if travelHeatmapState === 'error'}
              Travel heatmap unavailable · <button
                type="button"
                onclick={() => commanderVisits.refetch()}>Retry</button
              >
            {:else if travelHeatmapState === 'empty'}
              No imported journal travel in this view
            {:else}
              {(commanderVisits.data?.count ?? 0).toLocaleString()} visited
              {commanderVisits.data?.mode === 'density'
                ? ' cells'
                : ' systems'}{commanderVisits.data?.truncated
                ? ' · bounded view'
                : ''}
            {/if}
          </span>{/if}
      </div>
      <SpatialCanvas
        {scene}
        {cameraRequest}
        {cameraRequestRevision}
        {focusTarget}
        {focusRevision}
        contributionPatch={FINDER_F4_ENABLED ? densityContribution : null}
        contributionPatchRevision={FINDER_F4_ENABLED
          ? (densityContribution?.revision ?? 0)
          : 0}
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
            <!-- eslint-disable svelte/no-navigation-without-resolve -- inspectHref resolves the Inspect route -->
            <a
              href={FINDER_F4_ENABLED
                ? inspectHref(selectedMapSystem.id64, page.url)
                : resolve(`/inspect?system=${selectedMapSystem.id64}`)}
              onclick={FINDER_F4_ENABLED
                ? (event) => followInspect(event, selectedMapSystem!.id64)
                : undefined}>Open System Map</a
            >
            <!-- eslint-enable svelte/no-navigation-without-resolve -->
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
  <div id="saved-systems"><WatchlistPanel /></div>
  <div id="compare-systems"><ComparePanel /></div>
</main>

<style>
  .committed-anchor,
  .result-paging {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }
  .page-size {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-block: 1rem;
  }
  .page-size input {
    width: 5rem;
  }
  .ranking-status,
  .result-paging {
    padding-inline: 1.15rem;
  }
  .ranking-status {
    color: var(--muted);
  }
  .result-paging {
    margin-top: 1rem;
    padding-bottom: 1rem;
  }
  .shortlist-nav {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem 1.5rem;
    margin-block: 1rem;
  }
  .finder-actions {
    grid-column: 1 / -1;
    padding: 0 1rem 0.75rem;
  }
  #saved-systems,
  #compare-systems {
    margin-top: 1.5rem;
    scroll-margin-top: 5rem;
  }
</style>
