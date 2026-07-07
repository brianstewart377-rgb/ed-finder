import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type {
  MapRegionsResponse,
  MapClusterHullsResponse,
  MapHeatmapResponse,
  MapTimelineResponse,
} from '@/lib/api';

/** Per-layer toggle and option bag. */
export interface MapLayerOptions {
  /** Fetch this layer? Default false so the hook is lazy by default. */
  enabled?: boolean;
}

export interface UseMapLayersOptions {
  regions?:    MapLayerOptions;
  clusters?:    MapLayerOptions & { min_count?: number; max_hulls?: number };
  heatmap?:    MapLayerOptions & { voxel_size?: number; min_systems?: number; economy?: string | null };
  timeline?:   MapLayerOptions & { bucket?: 'day' | 'week' | 'month' | 'quarter' | 'year' };
  /** Stale time shared across all layer queries (default 5 minutes). */
  staleTimeMs?: number;
}

export interface UseMapLayersResult {
  regions:    { data?: MapRegionsResponse;    isLoading: boolean; isError: boolean; error: Error | null };
  clusters:   { data?: MapClusterHullsResponse; isLoading: boolean; isError: boolean; error: Error | null };
  heatmap:    { data?: MapHeatmapResponse;     isLoading: boolean; isError: boolean; error: Error | null };
  timeline:   { data?: MapTimelineResponse;    isLoading: boolean; isError: boolean; error: Error | null };
  /** True when at least one enabled layer is loading. */
  isLoading:  boolean;
  /** True when at least one enabled layer errored. */
  isError:    boolean;
}

const STALE_TIME = 5 * 60 * 1000; // 5 minutes

/**
 * Fetch map-owned layer data via TanStack Query.
 *
 * Each layer is independent: enabling one does not cause others to fetch.
 * Query keys are stable and include any option params so changing options
 * invalidates the cache correctly.
 *
 * Not wired into any UI component yet — import and spread the result into
 * whatever renderer needs it.
 */
export function useMapLayers(opts: UseMapLayersOptions = {}): UseMapLayersResult {
  const staleTime = opts.staleTimeMs ?? STALE_TIME;

  const regionsQuery = useQuery<MapRegionsResponse, Error>({
    queryKey: ['map', 'regions'],
    queryFn:  () => api.mapRegions(),
    enabled:  opts.regions?.enabled ?? false,
    staleTime,
  });

  const clustersQuery = useQuery<MapClusterHullsResponse, Error>({
    queryKey: ['map', 'clusters', opts.clusters?.min_count, opts.clusters?.max_hulls],
    queryFn:  () => api.mapClusterHulls({
      min_count: opts.clusters?.min_count,
      max_hulls: opts.clusters?.max_hulls,
    }),
    enabled: opts.clusters?.enabled ?? false,
    staleTime,
  });

  const heatmapQuery = useQuery<MapHeatmapResponse, Error>({
    queryKey: ['map', 'heatmap', opts.heatmap?.voxel_size, opts.heatmap?.min_systems, opts.heatmap?.economy],
    queryFn:  () => api.mapHeatmap({
      voxel_size: opts.heatmap?.voxel_size,
      min_systems: opts.heatmap?.min_systems,
      economy: opts.heatmap?.economy,
    }),
    enabled: opts.heatmap?.enabled ?? false,
    staleTime,
  });

  const timelineQuery = useQuery<MapTimelineResponse, Error>({
    queryKey: ['map', 'timeline', opts.timeline?.bucket],
    queryFn:  () => api.mapTimeline({ bucket: opts.timeline?.bucket }),
    enabled:  opts.timeline?.enabled ?? false,
    staleTime,
  });

  const isLoading = Boolean(
    (opts.regions?.enabled  && regionsQuery.isLoading)  ||
    (opts.clusters?.enabled && clustersQuery.isLoading) ||
    (opts.heatmap?.enabled  && heatmapQuery.isLoading)  ||
    (opts.timeline?.enabled && timelineQuery.isLoading)
  );

  const isError = Boolean(
    (opts.regions?.enabled  && regionsQuery.isError)  ||
    (opts.clusters?.enabled && clustersQuery.isError) ||
    (opts.heatmap?.enabled  && heatmapQuery.isError)  ||
    (opts.timeline?.enabled && timelineQuery.isError)
  );

  return {
    regions:  { data: regionsQuery.data,  isLoading: regionsQuery.isLoading,  isError: regionsQuery.isError,  error: regionsQuery.error },
    clusters: { data: clustersQuery.data, isLoading: clustersQuery.isLoading, isError: clustersQuery.isError, error: clustersQuery.error },
    heatmap:  { data: heatmapQuery.data,  isLoading: heatmapQuery.isLoading,  isError: heatmapQuery.isError,  error: heatmapQuery.error },
    timeline: { data: timelineQuery.data, isLoading: timelineQuery.isLoading, isError: timelineQuery.isError, error: timelineQuery.error },
    isLoading,
    isError,
  };
}
