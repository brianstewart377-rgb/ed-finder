import { createQueries, useQueryClient } from '@tanstack/svelte-query';
import { untrack } from 'svelte';
import {
  getCatalogueViewportSystems,
  type CatalogueViewportResponse,
} from '$lib/api/client';
import { queryKeys } from '$lib/api/query';
import type { Vec3Ly } from './contracts';
import {
  GalaxyStarCellCache,
  MAX_GALAXY_STAR_ACTIVE_CELLS,
  planGalaxyStarCells,
  type GalaxyStarCell,
} from './galaxy-star-cells';
import { GalaxyStarRequests } from './galaxy-star-requests';
import {
  sampleCatalogueCellSystems,
  type GalaxyStarViewport,
} from './galaxy-star-stream';
import { LOCAL_STAR_CLOSE_LIMIT } from './galaxy-detail-policy';

/** Cell queries own cached packets; camera bounds are never part of their keys. */
export function createGalaxyStarQuery(
  getViewport: () => GalaxyStarViewport | null,
  getFocus: () => Vec3Ly,
) {
  const client = useQueryClient();
  const cache = new GalaxyStarCellCache();
  const requests = new GalaxyStarRequests();
  let previousCells: readonly GalaxyStarCell[] = [];
  const cells = $derived.by(() => {
    const viewport = getViewport();
    previousCells = viewport
      ? planGalaxyStarCells(viewport, previousCells)
      : [];
    return previousCells;
  });
  const cellKey = (cell: GalaxyStarCell) =>
    [...queryKeys.all, 'map', 'catalogue-stars', cell.key] as const;
  const queries = createQueries(() => ({
    queries: cells.map((cell) => ({
      queryKey: cellKey(cell),
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        requests.run(signal, async (requestSignal) => {
          const packet = await getCatalogueViewportSystems(
            cell.request,
            requestSignal,
          );
          // Keep twice a cell's share of the rendered band budget for overscan,
          // and at least the full close-view budget. A dense 40k band therefore
          // retains <=5k rows/cell (<=320k across the cache), not 2.56m rows.
          const retainedLimit = Math.max(
            LOCAL_STAR_CLOSE_LIMIT,
            Math.ceil((2 * cell.request.limit) / MAX_GALAXY_STAR_ACTIVE_CELLS),
          );
          const systems = sampleCatalogueCellSystems(
            packet.systems,
            retainedLimit,
          );
          return {
            systems,
            truncated:
              packet.truncated || systems.length < packet.systems.length,
          };
        }),
      staleTime: Infinity,
      gcTime: Infinity,
      retry: 0,
    })),
  }));
  $effect(() => {
    const evicted = cache.retain(cells, getFocus());
    untrack(() => {
      for (const cell of evicted)
        client.removeQueries({ queryKey: cellKey(cell), exact: true });
    });
  });
  $effect(() => () => {
    requests.dispose();
    // The cache is scoped to this page. Neither inactive cells nor unresolved
    // requests survive unmount and accumulate in the application QueryClient.
    client.removeQueries({
      queryKey: [...queryKeys.all, 'map', 'catalogue-stars'],
    });
  });
  let assembledPackets: readonly (CatalogueViewportResponse | undefined)[] = [];
  let assembledData: CatalogueViewportResponse | undefined;
  const data = $derived.by((): CatalogueViewportResponse | undefined => {
    if (!getViewport() || queries.length !== cells.length) return undefined;
    // Keep the accepted view while its replacement loads, then publish all
    // successful cells even if a sibling failed. One failed cell must not
    // strand the camera on its old packet indefinitely.
    if (queries.some((query) => query.isPending)) return undefined;
    if (queries.length && queries.every((query) => !query.data))
      return undefined;
    const packets = queries.map((query) => query.data);
    if (
      assembledData &&
      packets.length === assembledPackets.length &&
      packets.every((packet, index) => packet === assembledPackets[index])
    )
      return assembledData;
    // This is a transient assembly index, not reactive application state.
    // eslint-disable-next-line svelte/prefer-svelte-reactivity
    const systems = new Map<
      string,
      CatalogueViewportResponse['systems'][number]
    >();
    for (const query of queries) {
      for (const system of query.data?.systems ?? [])
        systems.set(system.id64, system);
    }
    assembledPackets = packets;
    assembledData = {
      systems: [...systems.values()],
      truncated: queries.some((query) => !query.data || query.data.truncated),
    };
    return assembledData;
  });
  return {
    get data() {
      return data;
    },
    get isPending() {
      return queries.some((query) => query.isPending);
    },
    get isFetching() {
      return queries.some((query) => query.isFetching);
    },
    get isError() {
      return queries.some((query) => query.isError);
    },
  };
}
